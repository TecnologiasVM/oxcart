"""Give every catalogue issue a second, short vector, and take it away again.

    python scripts/issue_short_vectors.py status
    python scripts/issue_short_vectors.py apply [--write]
    python scripts/issue_short_vectors.py undo  [--write]

An issue's first vector (``Issue.embedding``, index ``issue_vec_idx``) is made from its title
and its whole catalogue text. This adds a second one made from a short text: the title, the
years and the section (``oxcart.catalogue_lookup.short_text``). The lookup uses it only when
it is asked to (``use_short``; the backend's setting is ``ASK_SHORT_VECTOR``).

What ``apply`` writes, and nothing else:
    Issue.short_text        the text that was embedded
    Issue.embedding_short   its text-embedding-3-large vector, 3,072 numbers
    index issue_short_vec_idx on Issue.embedding_short (cosine)
It embeds only issues whose stored ``short_text`` is missing or no longer what the issue's
title, years and section give, so it can be run again after it was interrupted.

``undo`` drops that index and removes those two properties from every issue. Nothing else
was written, so nothing else is touched.

Both verbs change nothing without ``--write``: they print what they would do. With it, each
proves what it did: a digest of every other property of every issue is taken before and
after and must be equal, the counts of nodes and relationships must be equal, and ``apply``
asks the new index for every issue by its own vector, forty hits as the lookup asks, and expects
each back among the first three (two issues can share a title).

The graph's address and login come from the environment, set for this process only
(``scripts/with-key.sh`` does that from the machine's secret store):
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE, and for ``apply`` OPENAI_API_KEY
The login must be allowed to write. Prints counts, digests and error classes; never the
address, a key, or the catalogue's text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from oxcart.catalogue_lookup import short_text  # noqa: E402

MODEL, DIMENSIONS = "text-embedding-3-large", 3072
INDEX, VECTOR, TEXT = "issue_short_vec_idx", "embedding_short", "short_text"
OURS = (VECTOR, TEXT)

_ISSUES = f"""
MATCH (i:Issue)
RETURN i.issue_id AS issue_id, i.title AS title, i.issue_dates AS issue_dates, i.section AS section,
       i.{TEXT} AS stored_text, i.{VECTOR} IS NOT NULL AS has_vector
ORDER BY issue_id
"""
_CREATE_INDEX = f"""
CREATE VECTOR INDEX {INDEX} IF NOT EXISTS FOR (i:Issue) ON (i.{VECTOR})
OPTIONS {{indexConfig: {{`vector.dimensions`: {DIMENSIONS}, `vector.similarity_function`: 'cosine'}}}}
"""
_SET = f"UNWIND $rows AS row MATCH (i:Issue {{issue_id: row.issue_id}}) SET i.{VECTOR} = row.vector, i.{TEXT} = row.text"
_REMOVE = f"MATCH (i:Issue) WHERE i.{VECTOR} IS NOT NULL OR i.{TEXT} IS NOT NULL REMOVE i.{VECTOR}, i.{TEXT} RETURN count(i) AS n"
# The index is approximate, and what it returns depends on how many hits are asked for. So it is
# checked the way the lookup asks it: forty hits. (Asked for one hit, the scratch copy returned an
# issue's own vector for 712 of 819; asked for forty, 818 first and one second, a twin title.)
_SELF = f"""
MATCH (i:Issue)
CALL (i) {{
  CALL db.index.vector.queryNodes('{INDEX}', 40, i.{VECTOR}) YIELD node, score
  WITH node ORDER BY score DESC, node.issue_id
  RETURN collect(node.issue_id) AS found
}}
RETURN i.issue_id AS issue_id, found
"""


def own_places(session) -> tuple:
    """Each issue asked for by its own short vector: how many come back first, second or third, or not at all."""
    first = near = 0
    total = 0
    for record in session.run(_SELF):
        total += 1
        place = record["found"].index(record["issue_id"]) + 1 if record["issue_id"] in record["found"] else None
        first += place == 1
        near += place in (2, 3)
    return total, first, near


def plain(value):
    return value if isinstance(value, (str, int, float, bool, list, type(None))) else str(value)


def rest_digest(session) -> str:
    """One digest over every property of every issue except the two this script owns."""
    digest = hashlib.sha256()
    for record in session.run("MATCH (i:Issue) RETURN i.issue_id AS issue_id, properties(i) AS p ORDER BY issue_id"):
        rest = {key: plain(value) for key, value in record["p"].items() if key not in OURS}
        digest.update(json.dumps([record["issue_id"], rest], sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()[:16]


def sizes(session) -> tuple:
    nodes = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
    relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
    return nodes, relationships


def index_state(session) -> str:
    record = session.run("SHOW INDEXES YIELD name, state WHERE name = $name RETURN state", name=INDEX).single()
    return record["state"] if record else "absent"


def plan(session) -> dict:
    """Every issue with its short text, and which of them need a vector made."""
    issues = []
    for record in session.run(_ISSUES):
        text = short_text(record["issue_id"], record["title"], record["issue_dates"], record["section"])
        issues.append({"issue_id": record["issue_id"], "text": text,
                       "current": bool(record["has_vector"]) and record["stored_text"] == text,
                       "has_any": bool(record["has_vector"]) or record["stored_text"] is not None})
    return {"issues": issues, "todo": [i for i in issues if not i["current"]]}


def embed(texts: list) -> tuple:
    """Vectors for the texts, in order, and the tokens used. The key is read here and never printed."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set: start through scripts/with-key.sh")
    vectors, tokens = [], 0
    for start in range(0, len(texts), 100):
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"model": MODEL, "input": texts[start:start + 100]}).encode("utf-8"),
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = re.sub(r"sk-[\w\-*.]{4,}", "sk-<redacted>", exc.read().decode("utf-8", "replace")[:300])
            raise SystemExit(f"embeddings request failed, HTTP {exc.code}: {detail}") from None
        rows = sorted(payload["data"], key=lambda d: d["index"])
        if any(len(d["embedding"]) != DIMENSIONS for d in rows):
            raise SystemExit(f"the API returned vectors that are not {DIMENSIONS} numbers long")
        vectors += [d["embedding"] for d in rows]
        tokens += int(payload["usage"]["total_tokens"])
    return vectors, tokens


def status(session) -> None:
    found = plan(session)
    with_any = sum(i["has_any"] for i in found["issues"])
    nodes, relationships = sizes(session)
    print(f"issues: {len(found['issues'])}; with a current short vector: {len(found['issues']) - len(found['todo'])}; "
          f"with a short vector or text of any age: {with_any}")
    print(f"index {INDEX}: {index_state(session)}")
    print(f"graph: {nodes} nodes, {relationships} relationships; digest of every other issue property: {rest_digest(session)}")


def apply(session, write: bool) -> int:
    found = plan(session)
    todo = found["todo"]
    distinct = list(dict.fromkeys(i["text"] for i in todo))
    print(f"issues: {len(found['issues'])}; to embed: {len(todo)} ({len(distinct)} distinct texts, "
          f"{sum(len(t) for t in distinct)} characters); index {INDEX}: {index_state(session)}")
    if not write:
        print("nothing written: add --write to do it")
        return 0
    before, size_before = rest_digest(session), sizes(session)
    if todo:
        vectors, tokens = embed(distinct)
        by_text = dict(zip(distinct, vectors))
        print(f"embedded {len(distinct)} texts, {tokens} tokens")
        rows = [{"issue_id": i["issue_id"], "text": i["text"], "vector": by_text[i["text"]]} for i in todo]
        for start in range(0, len(rows), 50):
            session.execute_write(lambda tx, part=rows[start:start + 50]: tx.run(_SET, rows=part).consume())
    session.run(_CREATE_INDEX).consume()
    session.run("CALL db.awaitIndex($name, 300)", name=INDEX).consume()
    after, size_after = rest_digest(session), sizes(session)
    left = plan(session)["todo"]
    total, first, near = own_places(session)
    ok = not left and before == after and size_before == size_after and first + near == total and index_state(session) == "ONLINE"
    print(f"written: {len(todo)} issues; without a current short vector now: {len(left)}; index {INDEX}: {index_state(session)}")
    print(f"every other issue property: digest {before} before, {after} after ({'equal' if before == after else 'DIFFERENT'})")
    print(f"nodes and relationships: {size_before} before, {size_after} after")
    print(f"asked the index for each of {total} issues by its own vector: {first} came back first, "
          f"{near} second or third, {total - first - near} not among the first three")
    print("OK" if ok else "FAILED: run `undo --write` to take the change away")
    return 0 if ok else 1


def undo(session, write: bool) -> int:
    found = plan(session)
    with_any = sum(i["has_any"] for i in found["issues"])
    print(f"issues: {len(found['issues'])}; with a short vector or text: {with_any}; index {INDEX}: {index_state(session)}")
    if not write:
        print("nothing removed: add --write to do it")
        return 0
    before, size_before = rest_digest(session), sizes(session)
    session.run(f"DROP INDEX {INDEX} IF EXISTS").consume()
    removed = session.execute_write(lambda tx: tx.run(_REMOVE).single()["n"])
    after, size_after = rest_digest(session), sizes(session)
    left = sum(i["has_any"] for i in plan(session)["issues"])
    ok = not left and before == after and size_before == size_after and index_state(session) == "absent"
    print(f"removed from {removed} issues; with a short vector or text now: {left}; index {INDEX}: {index_state(session)}")
    print(f"every other issue property: digest {before} before, {after} after ({'equal' if before == after else 'DIFFERENT'})")
    print(f"nodes and relationships: {size_before} before, {size_after} after")
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("verb", choices=["status", "apply", "undo"])
    parser.add_argument("--write", action="store_true", help="make the change; without it the verb only reports")
    args = parser.parse_args()
    uri, user, password = (os.environ.get(name, "") for name in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"))
    if not (uri and user and password):
        print("NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD are not set")
        return 2
    from neo4j import GraphDatabase

    try:
        with GraphDatabase.driver(uri, auth=(user, password), notifications_min_severity="OFF") as driver, \
                driver.session(database=os.environ.get("NEO4J_DATABASE") or None,
                               default_access_mode="WRITE" if args.write and args.verb != "status" else "READ") as session:
            if args.verb == "status":
                status(session)
                return 0
            return apply(session, args.write) if args.verb == "apply" else undo(session, args.write)
    except SystemExit:
        raise
    except Exception as exc:   # the message can hold the address: the class name only
        print(f"FAILED ({type(exc).__name__})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
