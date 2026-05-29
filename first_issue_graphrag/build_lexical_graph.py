"""
Build the *lexical graph* layer of the First Issue GraphRAG prototype in Neo4j.

This module ingests the sanitized ("patched") OXCART chunks produced by
``sanitize_chunks.py`` and materializes them as a navigable document graph:

    (Document {doc_id})-[:HAS_CHUNK]->(Chunk {chunk_id})
    (Chunk)-[:NEXT]->(Chunk)            # reading-order chain within a doc

It also installs the supporting schema objects (uniqueness constraints +
a fulltext index over ``Chunk.text``) that the downstream linking and
retrieval steps depend on.

Owner constraints honored here:
  * NO direct LLM API calls. This module only talks to Neo4j and the local
    filesystem.
  * Neo4j writes are ADDITIVE + NAMESPACED. Every ``Document`` and ``Chunk``
    node we create carries ``prototype = config.PROTOTYPE_TAG`` so that
    ``teardown.py`` can remove only the prototype's data.

Run (always via the repo venv, from the repo root)::

    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\build_lexical_graph.py
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\build_lexical_graph.py --docs OXCART03 OXCART50
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\build_lexical_graph.py --all-patched

Importable API::

    from build_lexical_graph import build_lexical_graph
    stats = build_lexical_graph(docs=["OXCART03"])  # -> {"documents":..,"chunks":..,"next_edges":..}
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional, Sequence

import sanitize_chunks
from config import NEO4J_DATABASE, PROTOTYPE_TAG, PATCH_DIR, neo4j_driver

# --------------------------------------------------------------------------- #
# Schema DDL (idempotent, Neo4j 5.x syntax)
# --------------------------------------------------------------------------- #
CONSTRAINTS: List[str] = [
    """CREATE CONSTRAINT first_issue_document_id IF NOT EXISTS
       FOR (d:Document) REQUIRE d.doc_id IS UNIQUE""",
    """CREATE CONSTRAINT first_issue_chunk_id IF NOT EXISTS
       FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE""",
]

FULLTEXT_INDEX: str = (
    "CREATE FULLTEXT INDEX chunk_text_fts IF NOT EXISTS "
    "FOR (c:Chunk) ON EACH [c.text]"
)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def _reading_order_start(chunk: Dict[str, Any], fallback: int) -> tuple:
    """
    Sort key for a chunk within a document.

    Primary key: the ``reading_order`` start index (chunks with a real
    reading-order sort first, in order). Chunks lacking reading-order fall back
    to their original file position so the NEXT chain is still deterministic.
    """
    ro = chunk.get("reading_order")
    if isinstance(ro, (list, tuple)) and ro and isinstance(ro[0], (int, float)):
        # (0, start) groups chunks with a real reading-order ahead of the rest.
        return (0, int(ro[0]), fallback)
    return (1, fallback, fallback)


def _order_chunks(chunks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return chunks ordered by reading-order start, falling back to file order."""
    indexed = list(enumerate(chunks))
    indexed.sort(key=lambda pair: _reading_order_start(pair[1], pair[0]))
    return [chunk for _, chunk in indexed]


def _chunk_props(chunk: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
    """Project a patched chunk dict to the Neo4j Chunk node property bag."""
    ro = chunk.get("reading_order")
    reading_order = json.dumps(ro) if ro is not None else None
    return {
        "chunk_id": chunk.get("chunk_id"),
        "doc_id": doc_id,
        "text": chunk.get("text") or "",
        "page": chunk.get("page"),
        "reading_order": reading_order,
    }


# --------------------------------------------------------------------------- #
# Transactional write units (retried by execute_write)
# --------------------------------------------------------------------------- #
def _write_schema(tx) -> None:
    for ddl in CONSTRAINTS:
        tx.run(ddl)
    tx.run(FULLTEXT_INDEX)


def _write_document(tx, doc_id: str, chunk_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Upsert one Document plus its ordered Chunk chain in a single transaction.

    Returns per-document counts: chunks created/merged and NEXT edges created.
    """
    tx.run(
        """
        MERGE (d:Document {doc_id: $doc_id})
        ON CREATE SET d.prototype = $proto
        ON MATCH  SET d.prototype = $proto
        """,
        doc_id=doc_id,
        proto=PROTOTYPE_TAG,
    )

    for row in chunk_rows:
        tx.run(
            """
            MATCH (d:Document {doc_id: $doc_id})
            MERGE (c:Chunk {chunk_id: $chunk_id})
            ON CREATE SET c.doc_id = $doc_id,
                          c.text = $text,
                          c.page = $page,
                          c.reading_order = $reading_order,
                          c.prototype = $proto
            ON MATCH  SET c.doc_id = $doc_id,
                          c.text = $text,
                          c.page = $page,
                          c.reading_order = $reading_order,
                          c.prototype = $proto
            MERGE (d)-[:HAS_CHUNK]->(c)
            """,
            doc_id=doc_id,
            chunk_id=row["chunk_id"],
            text=row["text"],
            page=row["page"],
            reading_order=row["reading_order"],
            proto=PROTOTYPE_TAG,
        )

    next_edges = 0
    for prev_row, next_row in zip(chunk_rows, chunk_rows[1:]):
        tx.run(
            """
            MATCH (a:Chunk {chunk_id: $a_id})
            MATCH (b:Chunk {chunk_id: $b_id})
            MERGE (a)-[r:NEXT]->(b)
            ON CREATE SET r.prototype = $proto
            ON MATCH  SET r.prototype = $proto
            """,
            a_id=prev_row["chunk_id"],
            b_id=next_row["chunk_id"],
            proto=PROTOTYPE_TAG,
        )
        next_edges += 1

    return {"chunks": len(chunk_rows), "next_edges": next_edges}


# --------------------------------------------------------------------------- #
# Patched-file availability
# --------------------------------------------------------------------------- #
def _ensure_patched(doc_id: str) -> None:
    """Write the patched file for ``doc_id`` if it is missing."""
    patched_path = PATCH_DIR / f"{doc_id}_patched.json"
    if not patched_path.exists():
        print(f"  [patch] {doc_id}: patched file missing -> sanitize_chunks.write_patched")
        sanitize_chunks.write_patched(doc_id)


def _all_patched_docs() -> List[str]:
    """Every doc_id that already has a patched file in PATCH_DIR."""
    if not PATCH_DIR.exists():
        return []
    docs = [p.name[: -len("_patched.json")] for p in PATCH_DIR.glob("*_patched.json")]
    return sorted(docs)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_lexical_graph(
    docs: Optional[Sequence[str]] = None,
    driver: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Create Document + Chunk nodes (prototype-tagged) with HAS_CHUNK and NEXT
    edges in reading order, plus the schema constraints and fulltext index.

    Args:
        docs: doc_ids to ingest. Defaults to ``sanitize_chunks.FIRST_ISSUE_DOCS``.
        driver: optional pre-opened Neo4j driver. If omitted, one is created via
            ``config.neo4j_driver()`` and closed before returning.

    Returns:
        ``{"stats": {"documents": int, "chunks": int, "next_edges": int}}``
    """
    doc_ids: List[str] = list(docs) if docs is not None else list(sanitize_chunks.FIRST_ISSUE_DOCS)

    # Make sure a patched file exists for each requested doc before reading.
    for doc_id in doc_ids:
        _ensure_patched(doc_id)

    # Group patched chunks by document, preserving file order for the fallback.
    # ``iter_patched_chunks`` takes a single doc_id and returns that doc's chunks
    # (which do not carry a per-chunk doc_id), so iterate per doc and key by it.
    grouped: Dict[str, List[Dict[str, Any]]] = {doc_id: [] for doc_id in doc_ids}
    for doc_id in doc_ids:
        for chunk in sanitize_chunks.iter_patched_chunks(doc_id):
            grouped[doc_id].append(chunk)

    owns_driver = driver is None
    drv = driver if driver is not None else neo4j_driver()

    stats = {"documents": 0, "chunks": 0, "next_edges": 0}
    try:
        with drv.session(database=NEO4J_DATABASE) as session:
            session.execute_write(_write_schema)

            for doc_id in doc_ids:
                chunks = grouped.get(doc_id, [])
                if not chunks:
                    print(f"  [skip] {doc_id}: no patched chunks")
                    continue

                ordered = _order_chunks(chunks)
                chunk_rows = [_chunk_props(c, doc_id) for c in ordered if c.get("chunk_id")]
                if not chunk_rows:
                    print(f"  [skip] {doc_id}: no chunks with a chunk_id")
                    continue

                result = session.execute_write(_write_document, doc_id, chunk_rows)
                stats["documents"] += 1
                stats["chunks"] += result["chunks"]
                stats["next_edges"] += result["next_edges"]
                print(
                    f"  [doc] {doc_id}: {result['chunks']} chunks, "
                    f"{result['next_edges']} NEXT edges"
                )
    finally:
        if owns_driver:
            drv.close()

    return {"stats": stats}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the prototype lexical graph (Document/Chunk + NEXT) in Neo4j.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--docs",
        nargs="+",
        metavar="DOC_ID",
        help="doc_ids to ingest (default: sanitize_chunks.FIRST_ISSUE_DOCS).",
    )
    group.add_argument(
        "--all-patched",
        action="store_true",
        help="Ingest every *_patched.json found in results/oxcarts-patch.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)

    if args.all_patched:
        docs: Optional[List[str]] = _all_patched_docs()
        if not docs:
            print("No patched files found in results/oxcarts-patch; nothing to ingest.")
            return 1
        print(f"Ingesting all patched docs ({len(docs)}): {', '.join(docs)}")
    else:
        docs = args.docs  # None -> default FIRST_ISSUE_DOCS inside build_lexical_graph
        label = ", ".join(docs) if docs else "FIRST_ISSUE_DOCS (default)"
        print(f"Ingesting docs: {label}")

    result = build_lexical_graph(docs=docs)
    stats = result["stats"]
    print("\n== build_lexical_graph stats ==")
    print(f"  documents : {stats['documents']}")
    print(f"  chunks    : {stats['chunks']}")
    print(f"  next_edges: {stats['next_edges']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
