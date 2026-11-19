"""
Link the prototype *lexical graph* (Document/Chunk) to the *domain graph*
(the existing Mena Issue/Stamp catalog) for the Costa Rica 1863 First Issue.

For every prototype ``Chunk`` we run the LLM-free ``lexicon.score_chunk`` over
its clean text. When the chunk links to the First Issue we add namespaced,
additive relationships into the existing domain graph:

    (Chunk)-[:MENTIONS {confidence, signals, score}]->(Issue {issue_id:ISSUE_ID})
    (Chunk)-[:MENTIONS_STAMP {confidence, signals}]->(Stamp {issue_id:ISSUE_ID, catalog_no:<mena>})

and record ``Chunk.link_score`` for later ranking.

A READ-ONLY Weaviate cross-validation step then runs a BM25 query against the
existing "Oxcart" collection and reports how much its top results overlap with
the chunks our deterministic lexicon linked — a sanity check that our linking
is finding the same evidence a lexical search engine surfaces.

Owner constraints honored here:
  * NO direct LLM API calls. The lexicon is pure regex; Weaviate BM25 needs no
    API key and uses no vectorizer (lexical only).
  * Weaviate is strictly READ-ONLY (a single BM25 query, then ``client.close()``).
  * Neo4j writes are ADDITIVE + NAMESPACED. Every relationship we create carries
    ``prototype = config.PROTOTYPE_TAG``. We never modify existing Issue/Stamp
    nodes (we only MATCH them and MERGE an edge from our prototype Chunk).

Run (always via the repo venv, from the repo root)::

    python pipeline/first_issue_graph/link_lexical_to_domain.py
    python pipeline/first_issue_graph/link_lexical_to_domain.py --docs OXCART03 OXCART50

Importable API::

    from link_lexical_to_domain import link_lexical_to_domain
    stats = link_lexical_to_domain(docs=["OXCART03"])  # -> {"stats": {...}}
"""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional, Sequence, Set

import lexicon
from oxcart.config import (
    FIRST_ISSUE_STAMP_MIN_CONF,
    ISSUE_ID,
    NEO4J_DATABASE,
    OXCART_COLLECTION,
    PROTOTYPE_TAG,
    neo4j_driver,
    weaviate_client,
)

# BM25 cross-validation query (the canonical First Issue lexical signal).
CROSS_VALIDATION_QUERY = "first issue 1863 medio real dos reales"
CROSS_VALIDATION_LIMIT = 50


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def _confidence_from_score(score: float) -> float:
    """
    Map a lexicon signal score (roughly 0..10) to a 0..1 confidence for the edge.

    The score is an unbounded sum of signal weights; we squash it into [0,1]
    with a simple linear cap at 10 so the edge carries a comparable confidence
    alongside ``score`` (the raw value is also stored).
    """
    if score <= 0:
        return 0.0
    return min(1.0, round(score / 10.0, 4))


# --------------------------------------------------------------------------- #
# Neo4j read/write units
# --------------------------------------------------------------------------- #
def _read_chunks(tx, docs: Optional[Sequence[str]]) -> List[Dict[str, Any]]:
    """Return prototype chunks (chunk_id, doc_id, text, page), optionally per-doc."""
    if docs:
        cypher = """
            MATCH (c:Chunk {prototype: $proto})
            WHERE c.doc_id IN $docs
            RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id,
                   c.text AS text, c.page AS page
            ORDER BY c.doc_id, c.chunk_id
        """
        records = tx.run(cypher, proto=PROTOTYPE_TAG, docs=list(docs))
    else:
        cypher = """
            MATCH (c:Chunk {prototype: $proto})
            RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id,
                   c.text AS text, c.page AS page
            ORDER BY c.doc_id, c.chunk_id
        """
        records = tx.run(cypher, proto=PROTOTYPE_TAG)
    return [dict(r) for r in records]


def _link_chunk(
    tx,
    chunk_id: str,
    score: float,
    confidence: float,
    signals: List[str],
    stamps: List[Dict[str, Any]],
) -> Dict[str, int]:
    """
    Attach one linked chunk to the Issue (+ matching Stamps) and set link_score.

    Returns ``{"mentions_issue": 0|1, "mentions_stamp": <n>}``.
    """
    # Always record the link score on the chunk (even if Issue match is absent).
    tx.run(
        """
        MATCH (c:Chunk {chunk_id: $chunk_id, prototype: $proto})
        SET c.link_score = $score
        """,
        chunk_id=chunk_id,
        proto=PROTOTYPE_TAG,
        score=score,
    )

    issue_edges = 0
    issue_rec = tx.run(
        """
        MATCH (c:Chunk {chunk_id: $chunk_id, prototype: $proto})
        MATCH (i:Issue {issue_id: $issue_id})
        MERGE (c)-[r:MENTIONS]->(i)
        ON CREATE SET r.prototype = $proto,
                      r.confidence = $confidence,
                      r.signals = $signals,
                      r.score = $score
        ON MATCH  SET r.prototype = $proto,
                      r.confidence = $confidence,
                      r.signals = $signals,
                      r.score = $score
        RETURN count(r) AS n
        """,
        chunk_id=chunk_id,
        proto=PROTOTYPE_TAG,
        issue_id=ISSUE_ID,
        confidence=confidence,
        signals=signals,
        score=score,
    ).single()
    if issue_rec and issue_rec["n"]:
        issue_edges = 1

    stamp_edges = 0
    for stamp in stamps:
        rec = tx.run(
            """
            MATCH (c:Chunk {chunk_id: $chunk_id, prototype: $proto})
            MATCH (st:Stamp {issue_id: $issue_id, catalog_no: $catalog_no})
            MERGE (c)-[r:MENTIONS_STAMP]->(st)
            ON CREATE SET r.prototype = $proto,
                          r.confidence = $confidence,
                          r.signals = $signals
            ON MATCH  SET r.prototype = $proto,
                          r.confidence = $confidence,
                          r.signals = $signals
            RETURN count(r) AS n
            """,
            chunk_id=chunk_id,
            proto=PROTOTYPE_TAG,
            issue_id=ISSUE_ID,
            catalog_no=stamp["mena"],
            confidence=stamp["confidence"],
            signals=stamp["signals"],
        ).single()
        if rec and rec["n"]:
            stamp_edges += 1

    return {"mentions_issue": issue_edges, "mentions_stamp": stamp_edges}


# --------------------------------------------------------------------------- #
# Weaviate cross-validation (READ-ONLY)
# --------------------------------------------------------------------------- #
def _weaviate_bm25_chunk_ids(
    query: str = CROSS_VALIDATION_QUERY,
    limit: int = CROSS_VALIDATION_LIMIT,
) -> List[str]:
    """
    Run a single READ-ONLY BM25 query over the Oxcart collection and return the
    ``chunk_id`` of each hit. Always closes the client. BM25 uses no vectorizer
    and needs no API key.
    """
    import weaviate.classes as wvc

    chunk_ids: List[str] = []
    client = weaviate_client()
    try:
        collection = client.collections.get(OXCART_COLLECTION)
        resp = collection.query.bm25(
            query=query,
            query_properties=["text"],
            limit=limit,
            return_properties=["chunk_id"],
            return_metadata=wvc.query.MetadataQuery(score=True),
        )
        for obj in resp.objects or []:
            props = obj.properties or {}
            cid = props.get("chunk_id")
            if cid:
                chunk_ids.append(str(cid))
    finally:
        client.close()
    return chunk_ids


def _cross_validate(linked_chunk_ids: Set[str]) -> Dict[str, Any]:
    """
    Compare our graph-linked chunk_ids against Weaviate BM25's top results.

    Returns overlap stats. On any Weaviate error the step degrades gracefully
    (it is a sanity check, not a hard dependency of the linking).
    """
    try:
        weaviate_ids = _weaviate_bm25_chunk_ids()
    except Exception as exc:  # pragma: no cover - network/availability dependent
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "query": CROSS_VALIDATION_QUERY,
        }

    weaviate_set = set(weaviate_ids)
    overlap = sorted(linked_chunk_ids & weaviate_set)
    return {
        "available": True,
        "query": CROSS_VALIDATION_QUERY,
        "weaviate_hits": len(weaviate_ids),
        "weaviate_unique": len(weaviate_set),
        "graph_linked": len(linked_chunk_ids),
        "overlap_count": len(overlap),
        "overlap_chunk_ids": overlap[:25],
        "overlap_pct_of_weaviate": (
            round(len(overlap) / len(weaviate_set), 4) if weaviate_set else 0.0
        ),
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def link_lexical_to_domain(
    docs: Optional[Sequence[str]] = None,
    driver: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Score every prototype Chunk, link the relevant ones to the First Issue
    (and to specific Stamps), then cross-validate against Weaviate BM25.

    Args:
        docs: optional list of doc_ids to limit linking to. Defaults to all
            prototype chunks.
        driver: optional pre-opened Neo4j driver. If omitted, one is created via
            ``config.neo4j_driver()`` and closed before returning.

    Returns:
        ``{"stats": {"mentions_issue", "mentions_stamp", "chunks_scored",
        "weaviate_overlap"}, "examples": [...]}``
    """
    owns_driver = driver is None
    drv = driver if driver is not None else neo4j_driver()

    stats = {
        "mentions_issue": 0,
        "mentions_stamp": 0,
        "chunks_scored": 0,
        "chunks_linked": 0,
    }
    examples: List[Dict[str, Any]] = []
    linked_chunk_ids: Set[str] = set()

    try:
        with drv.session(database=NEO4J_DATABASE) as session:
            chunks = session.execute_read(_read_chunks, docs)
            stats["chunks_scored"] = len(chunks)

            for chunk in chunks:
                text = chunk.get("text") or ""
                link = lexicon.score_chunk(text)
                if not link.linked:
                    continue

                signals = link.signal_summary()
                confidence = _confidence_from_score(link.score)
                stamps = [
                    {
                        "mena": s.mena,
                        "scott": s.scott,
                        "label": s.label,
                        "confidence": s.confidence,
                        "signals": list(s.signals),
                    }
                    for s in link.stamps
                    if s.confidence >= FIRST_ISSUE_STAMP_MIN_CONF
                ]

                result = session.execute_write(
                    _link_chunk,
                    chunk["chunk_id"],
                    link.score,
                    confidence,
                    signals,
                    stamps,
                )

                stats["mentions_issue"] += result["mentions_issue"]
                stats["mentions_stamp"] += result["mentions_stamp"]
                stats["chunks_linked"] += 1
                linked_chunk_ids.add(str(chunk["chunk_id"]))

                if len(examples) < 8:
                    examples.append(
                        {
                            "doc_id": chunk.get("doc_id"),
                            "chunk_id": chunk.get("chunk_id"),
                            "page": chunk.get("page"),
                            "score": link.score,
                            "signals": signals,
                            "stamps": sorted({s["mena"] for s in stamps}),
                        }
                    )
    finally:
        if owns_driver:
            drv.close()

    # READ-ONLY Weaviate cross-validation against the linked set.
    weaviate_overlap = _cross_validate(linked_chunk_ids)
    stats["weaviate_overlap"] = weaviate_overlap

    return {"stats": stats, "examples": examples}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Link prototype Chunks to the First Issue domain graph (Neo4j) "
        "and cross-validate against Weaviate BM25 (read-only).",
    )
    parser.add_argument(
        "--docs",
        nargs="+",
        metavar="DOC_ID",
        help="Limit linking to these doc_ids (default: all prototype chunks).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    docs = args.docs
    label = ", ".join(docs) if docs else "all prototype chunks"
    print(f"Linking chunks: {label}")

    result = link_lexical_to_domain(docs=docs)
    stats = result["stats"]
    overlap = stats.get("weaviate_overlap", {})

    print("\n== link_lexical_to_domain stats ==")
    print(f"  chunks_scored  : {stats['chunks_scored']}")
    print(f"  chunks_linked  : {stats['chunks_linked']}")
    print(f"  mentions_issue : {stats['mentions_issue']}")
    print(f"  mentions_stamp : {stats['mentions_stamp']}")

    print("\n== weaviate BM25 cross-validation (read-only) ==")
    if overlap.get("available"):
        print(f"  query          : {overlap['query']}")
        print(f"  weaviate_hits  : {overlap['weaviate_hits']} ({overlap['weaviate_unique']} unique)")
        print(f"  graph_linked   : {overlap['graph_linked']}")
        print(f"  overlap_count  : {overlap['overlap_count']}")
        print(f"  overlap_pct    : {overlap['overlap_pct_of_weaviate']}")
    else:
        print(f"  unavailable    : {overlap.get('error')}")

    if result["examples"]:
        print("\n== example linked chunks ==")
        for ex in result["examples"]:
            print(
                f"  {ex['doc_id']} chunk={ex['chunk_id']} page={ex['page']} "
                f"score={ex['score']} stamps={ex['stamps']} signals={ex['signals']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
