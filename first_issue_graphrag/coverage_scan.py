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

    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\coverage_scan.py --all
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\coverage_scan.py --sample 80
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\coverage_scan.py --docs OXCART03 OXCART75
"""

from __future__ import annotations

import argparse
import re
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

_FINAL_RE = re.compile(r"^(OXCART[^_]*)_final\.json$", re.IGNORECASE)

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
def list_all_docs() -> List[str]:
    """Every doc_id that has a results/final_jsons/<doc>_final.json file."""
    docs: List[str] = []
    if not FINAL_JSONS_DIR.exists():
        return docs
    for p in sorted(FINAL_JSONS_DIR.glob("OXCART*_final.json")):
        m = _FINAL_RE.match(p.name)
        if m:
            docs.append(m.group(1))
    return docs


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


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


def scan_doc(doc_id: str) -> Dict[str, Any]:
    """
    Sanitize a doc in-memory, score every chunk, return only the LINKED chunks
    (deduped by normalized text), in reading order, plus per-doc scan counts.
    """
    try:
        patched = sanitize_chunks.sanitize_doc(doc_id)
    except FileNotFoundError:
        return {"doc_id": doc_id, "scanned": 0, "linked": [], "missing": True}

    chunks = patched.get("chunks", [])
    linked: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for ch in sorted(chunks, key=_ro_start):
        text = ch.get("text") or ""
        link = lexicon.score_chunk(text)
        if not link.linked:
            continue
        key = _norm(text)
        if not key or key in seen:
            continue  # dedupe near-identical repeated passages within the doc
        seen.add(key)
        stamps = [
            {"mena": s.mena, "scott": s.scott, "confidence": s.confidence, "signals": list(s.signals)}
            for s in link.stamps
            if s.confidence >= FIRST_ISSUE_STAMP_MIN_CONF
        ]
        linked.append(
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
    return {"doc_id": doc_id, "scanned": len(chunks), "linked": linked, "missing": False}


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
def coverage_scan(
    docs: Optional[Sequence[str]] = None,
    sample: Optional[int] = None,
    reset: bool = True,
    weaviate_xval: bool = True,
    driver: Optional[Any] = None,
) -> Dict[str, Any]:
    if docs:
        doc_list = list(docs)
    else:
        doc_list = list_all_docs()
        if sample:
            # Evenly spread the sample across the (numerically sorted) collection.
            step = max(1, len(doc_list) // sample)
            doc_list = doc_list[::step][:sample]

    owns = driver is None
    drv = driver if driver is not None else neo4j_driver()
    stats: Dict[str, Any] = {
        "docs_scanned": 0, "docs_missing": 0, "docs_with_first_issue": 0,
        "chunks_scanned": 0, "chunks_linked": 0, "chunks_after_dedupe": 0,
        "mentions_issue": 0, "mentions_stamp": 0, "per_doc": [],
    }
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
    g.add_argument("--all", action="store_true", help="Scan every OXCART*_final.json (the full collection).")
    g.add_argument("--sample", type=int, metavar="N", help="Scan N docs spread across the collection.")
    g.add_argument("--docs", nargs="+", metavar="DOC_ID", help="Scan these specific docs.")
    ap.add_argument("--no-reset", action="store_true", help="Do not clear existing prototype chunks first.")
    ap.add_argument("--no-weaviate", action="store_true", help="Skip the Weaviate BM25 cross-check.")
    return ap.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    docs = args.docs if args.docs else None
    sample = args.sample if args.sample else None
    if not docs and not sample and not args.all:
        sample = 80  # sensible default: a wide sample
        print("No scope given; defaulting to --sample 80 (use --all for the full collection).")

    print("Scanning collection (Approach A: materialize first-issue hits only)...")
    result = coverage_scan(
        docs=docs, sample=sample, reset=not args.no_reset, weaviate_xval=not args.no_weaviate,
    )
    s = result["stats"]
    print("\n== coverage_scan stats ==")
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
