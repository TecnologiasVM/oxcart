"""
Full-collection coverage scan (Approach A): scan EVERY chunk of many OXCART docs
with the LLM-free lexicon, but materialize into Neo4j ONLY the chunks that link
to the 1863 First Issue (plus their domain edges). This keeps the lexical graph
clean and grounded while still *covering* the whole corpus during the scan.

Why this and not build_lexical_graph.py + link_lexical_to_domain.py:
  Those two ingest ALL chunks of the selected docs (fine for a 10-doc demo, but
  ~193k Chunk nodes for the full corpus). This scanner is the prototype-correct
  path for wide coverage: sanitize in-memory, score, and only write the hits.
  It also DEDUPES near-identical chunks within a doc (the corpus has the same
  passage chunked several times with different chunk_ids — a known chunking
  artifact that otherwise inflates counts).

Owner constraints honored: no direct LLM calls (lexicon is pure regex; Weaviate
cross-check is BM25, read-only); Neo4j writes are additive + prototype-tagged.
The ``--reset`` default clears ONLY prototype Chunk/Document nodes (and their
edges) before rebuilding; it never touches the Mena Issue/Stamp domain graph or
the ScottStamp/Illustration layer.

Run (always via the repo venv, from the repo root)::

    python first_issue_graphrag/coverage_scan.py --all
    python first_issue_graphrag/coverage_scan.py --sample 80
    python first_issue_graphrag/coverage_scan.py --docs OXCART03 OXCART75
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import lexicon
import sanitize_chunks
from config import (
    FINAL_JSONS_DIR,
    FIRST_ISSUE_STAMP_MIN_CONF,
    ISSUE_ID,
    NEO4J_DATABASE,
    OXCART_COLLECTION,
    PROTOTYPE_TAG,
    neo4j_driver,
    weaviate_client,
)

# Match ANY ``<doc_id>_final.json`` (the corpus is no longer OXCART-only).
_FINAL_RE = re.compile(r"^(.+)_final\.json$", re.IGNORECASE)

# Documents excluded from broad (--all/--sample) scans, matched case-insensitively
# against the file name:
#   * Boletín Correos  -- 526 government postal bulletins, no first-issue value.
#   * Mena / Scott catalogs -- already represented in the Neo4j DOMAIN graph
#     (Mena 2018 + the Scott layer); re-ingesting them as lexical chunks would be
#     redundant with the structured catalog (owner decision).
# The ``^mena``/``^scott``/``^catálogo scott`` anchors only match the actual
# catalog FILES, never a journal that merely *cites* Scott/Mena numbers.
_EXCLUDE_RE = re.compile(
    r"(?i)(?:boletin correos|boletín correos|^mena\b|^scott\b|^cat[aá]logo scott)"
)

# Where --dry-run dumps its linked/near-miss report (alongside examples_runner output).
_DRYRUN_DIR = Path(__file__).resolve().parent / "results"


def _is_excluded(name: str) -> bool:
    return bool(_EXCLUDE_RE.search(name))

# --------------------------------------------------------------------------- #
# Schema (DDL must be auto-commit on Neo4j 5.x — run via session.run, not execute_write)
# --------------------------------------------------------------------------- #
_DDL = [
    "CREATE CONSTRAINT first_issue_document_id IF NOT EXISTS "
    "FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
    "CREATE CONSTRAINT first_issue_chunk_id IF NOT EXISTS "
    "FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE FULLTEXT INDEX chunk_text_fts IF NOT EXISTS "
    "FOR (c:Chunk) ON EACH [c.text]",
]


def _ensure_schema(session) -> None:
    for ddl in _DDL:
        session.run(ddl)


def _reset_lexical(session) -> Dict[str, int]:
    """DETACH DELETE only prototype Chunk + Document (keeps ScottStamp/Illustration)."""
    rec = session.run(
        "MATCH (c:Chunk {prototype:$t}) WITH c LIMIT 1000000 "
        "DETACH DELETE c RETURN count(c) AS n",
        t=PROTOTYPE_TAG,
    ).single()
    chunks = rec["n"] if rec else 0
    rec = session.run(
        "MATCH (d:Document {prototype:$t}) DETACH DELETE d RETURN count(d) AS n",
        t=PROTOTYPE_TAG,
    ).single()
    docs = rec["n"] if rec else 0
    return {"chunks_deleted": chunks, "documents_deleted": docs}


# --------------------------------------------------------------------------- #
# Discovery + per-doc scan
# --------------------------------------------------------------------------- #
def list_all_docs(include_excluded: bool = False) -> List[str]:
    """
    Every doc_id that has a results/final_jsons/<doc>_final.json file.

    By default this now spans the WHOLE corpus (not just OXCART), minus the
    excluded Boletín Correos bulletins. Pass ``include_excluded=True`` to include
    those too.
    """
    docs: List[str] = []
    if not FINAL_JSONS_DIR.exists():
        return docs
    for p in sorted(FINAL_JSONS_DIR.glob("*_final.json")):
        if not include_excluded and _is_excluded(p.name):
            continue
        m = _FINAL_RE.match(p.name)
        if m:
            docs.append(m.group(1))
    return docs


def _read_docs_file(path: str) -> List[str]:
    """Read explicit doc_ids (one per line) from a UTF-8 file.

    Only ``\\r``/``\\n`` are stripped, so doc_ids with significant trailing
    spaces (e.g. ``Mena 2018 CRPC ``) round-trip exactly. Blank lines are skipped.
    """
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            doc = line.rstrip("\r\n")
            if doc.strip():
                out.append(doc)
    return out


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


# Nested/overlapping chunks (the parse layer emits the SAME passage at several
# growing lengths) share a long common head. Dedupe by a normalized prefix so a
# passage is materialized once. 200 chars is enough to separate distinct passages
# while collapsing the nested family.
_PREFIX_LEN = 200

# Minimum substantive length for a LINKED chunk. A heading/byline fragment
# (e.g. a 100-char article title) carries no retrievable content and is already
# represented by the full passage it leads.
_MIN_LINK_CHARS = 140


def _prefix_key(text: str) -> str:
    return _norm(text)[:_PREFIX_LEN]


def _confidence_from_score(score: float) -> float:
    return 0.0 if score <= 0 else min(1.0, round(score / 10.0, 4))


def _ro_start(chunk: Dict[str, Any]) -> int:
    ro = chunk.get("reading_order")
    if isinstance(ro, (list, tuple)) and ro:
        try:
            return int(ro[0])
        except (TypeError, ValueError):
            return 1_000_000
    return 1_000_000


def scan_doc(doc_id: str, collect_near: bool = False, near_min: float = 2.0) -> Dict[str, Any]:
    """
    Sanitize a doc in-memory, score every chunk, return only the LINKED chunks
    (deduped by normalized text), in reading order, plus per-doc scan counts.

    When ``collect_near`` is set, also return ``near`` — chunks that did NOT link
    but scored at least ``near_min``. These borderline misses are the recall-audit
    population (used by --dry-run to find Spanish first-issue mentions the lexicon
    currently fails to capture).
    """
    try:
        patched = sanitize_chunks.sanitize_doc(doc_id)
    except FileNotFoundError:
        return {"doc_id": doc_id, "scanned": 0, "linked": [], "near": [], "missing": True}
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"  [warn] skip {doc_id}: {type(exc).__name__}: {exc}")
        return {"doc_id": doc_id, "scanned": 0, "linked": [], "near": [], "missing": True}

    chunks = patched.get("chunks", [])
    candidates: List[Dict[str, Any]] = []
    near: List[Dict[str, Any]] = []
    seen_near: set[str] = set()

    for ch in sorted(chunks, key=_ro_start):
        text = ch.get("text") or ""
        link = lexicon.score_chunk(text)
        if not link.linked:
            if collect_near and link.score >= near_min:
                key = _prefix_key(text)
                if key and key not in seen_near:
                    seen_near.add(key)
                    near.append(
                        {
                            "chunk_id": ch.get("chunk_id"),
                            "text": text,
                            "page": ch.get("page"),
                            "score": link.score,
                            "signals": link.signal_summary(),
                        }
                    )
            continue
        if len(_norm(text)) < _MIN_LINK_CHARS:
            continue  # heading/byline fragment — no retrievable content
        stamps = [
            {"mena": s.mena, "scott": s.scott, "confidence": s.confidence, "signals": list(s.signals)}
            for s in link.stamps
            if s.confidence >= FIRST_ISSUE_STAMP_MIN_CONF
        ]
        candidates.append(
            {
                "chunk_id": ch.get("chunk_id"),
                "text": text,
                "page": ch.get("page"),
                "reading_order": ch.get("reading_order"),
                "score": link.score,
                "confidence": _confidence_from_score(link.score),
                "signals": link.signal_summary(),
                "stamps": stamps,
            }
        )

    # Collapse nested/near-duplicate passages: group by normalized text prefix and
    # keep the LONGEST (most complete) representative of each group. This removes
    # the "same passage chunked at 15 growing lengths" artifact.
    best: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        key = _prefix_key(c["text"])
        if not key:
            continue
        if key not in best or len(c["text"]) > len(best[key]["text"]):
            best[key] = c
    linked = sorted(best.values(), key=_ro_start)

    return {"doc_id": doc_id, "scanned": len(chunks), "linked": linked, "near": near, "missing": False}


# --------------------------------------------------------------------------- #
# Materialize one doc's linked chunks (batched UNWIND, idempotent, namespaced)
# --------------------------------------------------------------------------- #
_MATERIALIZE = """
MERGE (d:Document {doc_id: $doc_id})
  ON CREATE SET d.prototype = $proto
  ON MATCH  SET d.prototype = $proto
WITH d
UNWIND $rows AS row
MERGE (c:Chunk {chunk_id: row.chunk_id})
  ON CREATE SET c.prototype=$proto, c.doc_id=$doc_id, c.text=row.text,
                c.page=row.page, c.reading_order=row.reading_order, c.link_score=row.score
  ON MATCH  SET c.prototype=$proto, c.doc_id=$doc_id, c.text=row.text,
                c.page=row.page, c.reading_order=row.reading_order, c.link_score=row.score
MERGE (d)-[hc:HAS_CHUNK]->(c)
  ON CREATE SET hc.prototype=$proto
  ON MATCH  SET hc.prototype=$proto
WITH c, row
MATCH (i:Issue {issue_id: $issue_id})
MERGE (c)-[m:MENTIONS]->(i)
  ON CREATE SET m.prototype=$proto, m.confidence=row.confidence, m.signals=row.signals, m.score=row.score
  ON MATCH  SET m.prototype=$proto, m.confidence=row.confidence, m.signals=row.signals, m.score=row.score
WITH c, row
UNWIND row.stamps AS st
MATCH (s:Stamp {issue_id: $issue_id, catalog_no: st.mena})
MERGE (c)-[ms:MENTIONS_STAMP]->(s)
  ON CREATE SET ms.prototype=$proto, ms.confidence=st.confidence, ms.signals=st.signals
  ON MATCH  SET ms.prototype=$proto, ms.confidence=st.confidence, ms.signals=st.signals
RETURN count(DISTINCT c) AS chunks
"""

_NEXT = """
UNWIND $pairs AS p
MATCH (a:Chunk {chunk_id: p.a}), (b:Chunk {chunk_id: p.b})
MERGE (a)-[r:NEXT]->(b)
  ON CREATE SET r.prototype=$proto
  ON MATCH  SET r.prototype=$proto
"""


def _materialize(session, doc_id: str, linked: List[Dict[str, Any]]) -> int:
    if not linked:
        return 0
    rows = [
        {
            "chunk_id": c["chunk_id"], "text": c["text"], "page": c["page"],
            "reading_order": c["reading_order"], "score": c["score"],
            "confidence": c["confidence"], "signals": c["signals"],
            "stamps": c["stamps"],
        }
        for c in linked
    ]

    def _w(tx):
        tx.run(_MATERIALIZE, doc_id=doc_id, proto=PROTOTYPE_TAG, issue_id=ISSUE_ID, rows=rows).consume()
        pairs = [{"a": linked[i]["chunk_id"], "b": linked[i + 1]["chunk_id"]} for i in range(len(linked) - 1)]
        if pairs:
            tx.run(_NEXT, pairs=pairs, proto=PROTOTYPE_TAG).consume()

    session.execute_write(_w)
    return len(linked)


# --------------------------------------------------------------------------- #
# Weaviate cross-validation (READ-ONLY, BM25 over clean text_original)
# --------------------------------------------------------------------------- #
def _weaviate_overlap(linked_chunk_ids: set[str], limit: int = 100) -> Dict[str, Any]:
    import weaviate.classes as wvc

    client = None
    try:
        client = weaviate_client()
        coll = client.collections.get(OXCART_COLLECTION)
        resp = coll.query.bm25(
            query="first issue 1863 medio real dos reales coat of arms ABNCo",
            query_properties=["text_original", "text"],
            limit=limit,
            return_properties=["chunk_id"],
            return_metadata=wvc.query.MetadataQuery(score=True),
        )
        wv = {str((o.properties or {}).get("chunk_id")) for o in (resp.objects or []) if (o.properties or {}).get("chunk_id")}
        overlap = linked_chunk_ids & wv
        return {
            "available": True, "weaviate_hits": len(wv), "graph_linked": len(linked_chunk_ids),
            "overlap_count": len(overlap),
            "overlap_pct_of_weaviate": round(len(overlap) / len(wv), 4) if wv else 0.0,
        }
    except Exception as exc:  # pragma: no cover - availability dependent
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if client is not None:
            client.close()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _empty_stats() -> Dict[str, Any]:
    return {
        "docs_scanned": 0, "docs_missing": 0, "docs_with_first_issue": 0,
        "chunks_scanned": 0, "chunks_linked": 0, "chunks_after_dedupe": 0,
        "mentions_issue": 0, "mentions_stamp": 0, "per_doc": [],
    }


def _dry_run(doc_list: Sequence[str], dump_path: Optional[str]) -> Dict[str, Any]:
    """
    Score every doc WITHOUT touching Neo4j or Weaviate. Dumps linked + near-miss
    chunks (with full text) to a JSON report for offline precision/recall audit.
    This is the DB-safe path used to validate a lexicon change before committing
    it to the graph.
    """
    stats = _empty_stats()
    linked_out: List[Dict[str, Any]] = []
    near_out: List[Dict[str, Any]] = []
    t0 = time.time()

    for i, doc_id in enumerate(doc_list, 1):
        res = scan_doc(doc_id, collect_near=True)
        if res["missing"]:
            stats["docs_missing"] += 1
            continue
        stats["docs_scanned"] += 1
        stats["chunks_scanned"] += res["scanned"]
        for c in res["near"]:
            near_out.append({"doc": doc_id, **c})
        linked = res["linked"]
        if linked:
            stats["docs_with_first_issue"] += 1
            stats["chunks_after_dedupe"] += len(linked)
            for c in linked:
                linked_out.append({"doc": doc_id, **c})
                stats["mentions_issue"] += 1
                stats["mentions_stamp"] += len(c["stamps"])
            stats["per_doc"].append({"doc": doc_id, "linked": len(linked)})
        if i % 25 == 0:
            print(f"  ...[dry] scanned {i}/{len(doc_list)} docs, "
                  f"{stats['chunks_after_dedupe']} linked / {len(near_out)} near-miss so far")

    stats["chunks_linked"] = stats["chunks_after_dedupe"]
    stats["elapsed_sec"] = round(time.time() - t0, 1)
    stats["per_doc"].sort(key=lambda d: d["linked"], reverse=True)

    _DRYRUN_DIR.mkdir(parents=True, exist_ok=True)
    path = Path(dump_path) if dump_path else _DRYRUN_DIR / f"_dryrun_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"stats": stats, "linked": linked_out, "near_miss": near_out}, fh, ensure_ascii=False, indent=2)
    print(f"[dry-run] no Neo4j/Weaviate writes. report -> {path}")
    return {"stats": stats, "dump_path": str(path)}


def coverage_scan(
    docs: Optional[Sequence[str]] = None,
    sample: Optional[int] = None,
    reset: bool = True,
    weaviate_xval: bool = True,
    driver: Optional[Any] = None,
    include_excluded: bool = False,
    dry_run: bool = False,
    dump_path: Optional[str] = None,
) -> Dict[str, Any]:
    if docs:
        doc_list = list(docs)
    else:
        doc_list = list_all_docs(include_excluded=include_excluded)
        if sample:
            # Evenly spread the sample across the (numerically sorted) collection.
            step = max(1, len(doc_list) // sample)
            doc_list = doc_list[::step][:sample]

    if dry_run:
        return _dry_run(doc_list, dump_path)

    owns = driver is None
    drv = driver if driver is not None else neo4j_driver()
    stats: Dict[str, Any] = _empty_stats()
    linked_ids: set[str] = set()

    try:
        with drv.session(database=NEO4J_DATABASE) as session:
            if reset:
                stats["reset"] = _reset_lexical(session)
            _ensure_schema(session)

            for i, doc_id in enumerate(doc_list, 1):
                res = scan_doc(doc_id)
                if res["missing"]:
                    stats["docs_missing"] += 1
                    continue
                stats["docs_scanned"] += 1
                stats["chunks_scanned"] += res["scanned"]
                linked = res["linked"]
                if linked:
                    stats["docs_with_first_issue"] += 1
                    stats["chunks_after_dedupe"] += len(linked)
                    _materialize(session, doc_id, linked)
                    for c in linked:
                        linked_ids.add(str(c["chunk_id"]))
                        stats["mentions_issue"] += 1
                        stats["mentions_stamp"] += len(c["stamps"])
                    stats["per_doc"].append({"doc": doc_id, "linked": len(linked)})
                if i % 50 == 0:
                    print(f"  ...scanned {i}/{len(doc_list)} docs, "
                          f"{stats['chunks_after_dedupe']} linked chunks so far")
    finally:
        if owns:
            drv.close()

    stats["chunks_linked"] = stats["chunks_after_dedupe"]
    stats["per_doc"].sort(key=lambda d: d["linked"], reverse=True)
    if weaviate_xval:
        stats["weaviate_overlap"] = _weaviate_overlap(linked_ids)
    return {"stats": stats}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Full-collection First Issue coverage scan (materialize hits only).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true",
                   help="Scan every *_final.json (whole corpus, minus excluded Boletín Correos).")
    g.add_argument("--sample", type=int, metavar="N", help="Scan N docs spread across the collection.")
    g.add_argument("--docs", nargs="+", metavar="DOC_ID", help="Scan these specific docs.")
    g.add_argument("--docs-file", metavar="PATH",
                   help="Scan the doc_ids listed (one per line, UTF-8) in this file.")
    ap.add_argument("--include-boletines", action="store_true",
                    help="Do NOT exclude Boletín Correos bulletins (excluded by default).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Score only; write NO Neo4j/Weaviate data. Dump linked+near-miss chunks to results/.")
    ap.add_argument("--dump", metavar="PATH", help="Explicit output path for the --dry-run report JSON.")
    ap.add_argument("--no-reset", action="store_true", help="Do not clear existing prototype chunks first.")
    ap.add_argument("--no-weaviate", action="store_true", help="Skip the Weaviate BM25 cross-check.")
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    if args.docs:
        docs = args.docs
    elif args.docs_file:
        docs = _read_docs_file(args.docs_file)
        print(f"Loaded {len(docs)} doc_ids from {args.docs_file}")
    else:
        docs = None
    sample = args.sample if args.sample else None
    if not docs and not sample and not args.all:
        sample = 80  # sensible default: a wide sample
        print("No scope given; defaulting to --sample 80 (use --all for the full collection).")

    mode = "DRY-RUN (no writes)" if args.dry_run else "Approach A: materialize first-issue hits only"
    print(f"Scanning collection ({mode})...")
    result = coverage_scan(
        docs=docs, sample=sample, reset=not args.no_reset, weaviate_xval=not args.no_weaviate,
        include_excluded=args.include_boletines, dry_run=args.dry_run, dump_path=args.dump,
    )
    s = result["stats"]
    print("\n== coverage_scan stats ==")
    if "elapsed_sec" in s:
        print(f"  elapsed         : {s['elapsed_sec']}s")
    if result.get("dump_path"):
        print(f"  report          : {result['dump_path']}")
    if "reset" in s:
        print(f"  reset           : deleted {s['reset']['chunks_deleted']} chunks, {s['reset']['documents_deleted']} documents")
    print(f"  docs_scanned    : {s['docs_scanned']}  (missing: {s['docs_missing']})")
    print(f"  chunks_scanned  : {s['chunks_scanned']}")
    print(f"  docs_with_FI    : {s['docs_with_first_issue']}")
    print(f"  chunks_linked   : {s['chunks_linked']}  (after dedupe)")
    print(f"  mentions_issue  : {s['mentions_issue']}")
    print(f"  mentions_stamp  : {s['mentions_stamp']}")
    wv = s.get("weaviate_overlap", {})
    if wv.get("available"):
        print(f"  weaviate_overlap: {wv['overlap_count']}/{wv['weaviate_hits']} BM25 hits "
              f"({wv['overlap_pct_of_weaviate']*100:.0f}% of Weaviate top-{wv['weaviate_hits']})")
    print("\n  top docs by linked chunks:")
    for d in s["per_doc"][:20]:
        print(f"     {d['doc']:<16} {d['linked']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
