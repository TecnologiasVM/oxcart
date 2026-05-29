"""
Teardown for the First Issue GraphRAG prototype.

Removes ONLY data created by this prototype — every node we create carries the
property ``prototype = config.PROTOTYPE_TAG``. ``DETACH DELETE`` on those nodes
also drops the relationships we created (MENTIONS, MENTIONS_STAMP, DEPICTS,
VARIETY_OF, HAS_SCOTT_STAMP, EQUIVALENT_TO, HAS_CHUNK, NEXT), because each of
those edges has at least one prototype-tagged endpoint.

The existing Mena domain graph (Issue / Stamp / Variety / Proof / Plate) is
NEVER touched: those nodes do not carry our prototype tag, and we only ever
match nodes by ``prototype = PROTOTYPE_TAG``.

Safety:
  * Without ``--yes`` this is a DRY RUN: it prints per-label counts of what
    WOULD be deleted and deletes nothing.
  * With ``--yes`` it performs the deletion.
  * ``--drop-indexes`` additionally drops the prototype's fulltext index
    (``chunk_text_fts``) and the prototype unique constraints.

Run from repo root (the package dir is sys.path[0], so bare imports work):
    # dry run (default — shows counts, deletes nothing):
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\teardown.py
    # actually delete prototype nodes/edges:
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\teardown.py --yes
    # also drop the prototype index + constraints:
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\teardown.py --yes --drop-indexes

Public API:
    plan(driver=None) -> dict           # counts that WOULD be deleted (dry run)
    teardown(drop_indexes=False, driver=None) -> dict   # deleted counts
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import config

# Labels we own. Every node of these labels created by the prototype carries
# prototype = PROTOTYPE_TAG; we only ever delete nodes that carry the tag.
PROTOTYPE_LABELS: List[str] = ["ScottStamp", "Illustration", "Document", "Chunk"]

# Indexes / constraints the prototype creates (dropped only with --drop-indexes).
PROTOTYPE_FULLTEXT_INDEXES: List[str] = ["chunk_text_fts"]
PROTOTYPE_CONSTRAINTS: Dict[str, str] = {
    # constraint name (best-effort) : DROP-by-pattern fallback DDL
    "scott_stamp_scott_number": "FOR (n:ScottStamp) REQUIRE n.scott_number IS UNIQUE",
    "illustration_illustration_number": "FOR (n:Illustration) REQUIRE n.illustration_number IS UNIQUE",
    "document_doc_id": "FOR (n:Document) REQUIRE n.doc_id IS UNIQUE",
    "chunk_chunk_id": "FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE",
}


# --------------------------------------------------------------------------- #
# Driver lifecycle helper
# --------------------------------------------------------------------------- #
@contextmanager
def _driver_session(driver: Optional[Any] = None) -> Iterator[Any]:
    """
    Yield a Neo4j session. If ``driver`` is provided it is used as-is and left
    open for the caller (we only close drivers we create here).
    """
    owns_driver = driver is None
    drv = driver if driver is not None else config.neo4j_driver()
    try:
        with drv.session(database=config.NEO4J_DATABASE) as session:
            yield session
    finally:
        if owns_driver:
            drv.close()


# --------------------------------------------------------------------------- #
# Counting (dry run)
# --------------------------------------------------------------------------- #
def _count_nodes_by_label(session: Any) -> Dict[str, int]:
    """Count prototype-tagged nodes per owned label."""
    counts: Dict[str, int] = {}
    for label in PROTOTYPE_LABELS:
        # Label is from a fixed allow-list constant (never user input), so it is
        # safe to interpolate; the value filter remains parameterized.
        cypher = f"MATCH (n:{label}) WHERE n.prototype = $tag RETURN count(n) AS n"
        record = session.run(cypher, tag=config.PROTOTYPE_TAG).single()
        counts[label] = int(record["n"]) if record and record["n"] is not None else 0
    return counts


def _count_relationships(session: Any) -> int:
    """
    Count relationships incident to any prototype-tagged node (these are the
    edges DETACH DELETE will remove). A relationship can touch two prototype
    nodes, so we count distinct relationships.
    """
    cypher = (
        "MATCH (n)-[r]-() "
        "WHERE n.prototype = $tag "
        "RETURN count(DISTINCT r) AS n"
    )
    record = session.run(cypher, tag=config.PROTOTYPE_TAG).single()
    return int(record["n"]) if record and record["n"] is not None else 0


def plan(driver: Optional[Any] = None) -> Dict[str, Any]:
    """
    DRY RUN. Return the counts of nodes (per label) and relationships that
    ``teardown()`` WOULD delete. Deletes nothing.
    """
    with _driver_session(driver) as session:
        node_counts = _count_nodes_by_label(session)
        rel_count = _count_relationships(session)
    total_nodes = sum(node_counts.values())
    return {
        "prototype_tag": config.PROTOTYPE_TAG,
        "nodes_by_label": node_counts,
        "total_nodes": total_nodes,
        "relationships_incident": rel_count,
        "dry_run": True,
    }


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #
def _delete_label(session: Any, label: str) -> int:
    """
    DETACH DELETE all prototype-tagged nodes of ``label``. Returns nodes deleted.
    Batched to avoid large transactions.
    """
    cypher = (
        f"MATCH (n:{label}) WHERE n.prototype = $tag "
        "WITH n LIMIT $batch "
        "DETACH DELETE n "
        "RETURN count(n) AS deleted"
    )

    def _tx(tx: Any) -> int:
        return int(tx.run(cypher, tag=config.PROTOTYPE_TAG, batch=10_000).single()["deleted"])

    total = 0
    while True:
        deleted = session.execute_write(_tx)
        total += deleted
        if deleted == 0:
            break
    return total


def _drop_fulltext_indexes(session: Any) -> List[str]:
    """Drop the prototype fulltext index(es) IF EXISTS. Returns names dropped."""
    dropped: List[str] = []
    for name in PROTOTYPE_FULLTEXT_INDEXES:
        # Index name is a fixed constant (never user input).
        session.run(f"DROP INDEX {name} IF EXISTS")
        dropped.append(name)
    return dropped


def _drop_constraints(session: Any) -> List[str]:
    """
    Drop the prototype's unique constraints. We match by the constraint
    definition (label + property + uniqueness) discovered via SHOW CONSTRAINTS,
    so we never accidentally drop a domain constraint with a different name.
    """
    dropped: List[str] = []
    owned_props = {
        "ScottStamp": "scott_number",
        "Illustration": "illustration_number",
        "Document": "doc_id",
        "Chunk": "chunk_id",
    }
    records = list(session.run("SHOW CONSTRAINTS"))
    for record in records:
        data = record.data()
        labels = data.get("labelsOrTypes") or []
        props = data.get("properties") or []
        ctype = (data.get("type") or "").upper()
        name = data.get("name")
        if not name or "UNIQUE" not in ctype:
            continue
        for label, prop in owned_props.items():
            if label in labels and props == [prop]:
                # Constraint name comes from the DB catalog, not user input.
                session.run(f"DROP CONSTRAINT {name} IF EXISTS")
                dropped.append(name)
                break
    return dropped


def teardown(drop_indexes: bool = False, driver: Optional[Any] = None) -> Dict[str, Any]:
    """
    Delete ONLY prototype data (nodes tagged ``prototype = PROTOTYPE_TAG`` plus
    their incident relationships, removed via DETACH DELETE).

    Args:
        drop_indexes: if True, also drop the prototype fulltext index
            (``chunk_text_fts``) and the prototype unique constraints.
        driver: optional pre-built Neo4j driver (left open by this function).
            When omitted, a driver is created and closed internally.

    Returns:
        dict with deleted counts:
            {
              "prototype_tag": str,
              "deleted_nodes_by_label": {label: int},
              "deleted_nodes_total": int,
              "relationships_incident_before": int,
              "dropped_indexes": [str],
              "dropped_constraints": [str],
              "dry_run": False,
            }
    """
    with _driver_session(driver) as session:
        # Snapshot incident relationships before deletion (informational).
        rel_before = _count_relationships(session)

        deleted_by_label: Dict[str, int] = {}
        for label in PROTOTYPE_LABELS:
            deleted_by_label[label] = _delete_label(session, label)

        dropped_indexes: List[str] = []
        dropped_constraints: List[str] = []
        if drop_indexes:
            dropped_indexes = _drop_fulltext_indexes(session)
            dropped_constraints = _drop_constraints(session)

    return {
        "prototype_tag": config.PROTOTYPE_TAG,
        "deleted_nodes_by_label": deleted_by_label,
        "deleted_nodes_total": sum(deleted_by_label.values()),
        "relationships_incident_before": rel_before,
        "dropped_indexes": dropped_indexes,
        "dropped_constraints": dropped_constraints,
        "dry_run": False,
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _render_plan(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("FIRST ISSUE GRAPHRAG — TEARDOWN (DRY RUN)")
    lines.append("=" * 64)
    lines.append(f"prototype tag: {result['prototype_tag']}")
    lines.append("")
    lines.append("Nodes that WOULD be deleted (DETACH DELETE):")
    for label, n in result["nodes_by_label"].items():
        lines.append(f"  {label:<14} {n}")
    lines.append(f"  {'TOTAL':<14} {result['total_nodes']}")
    lines.append("")
    lines.append(f"Relationships incident to prototype nodes: {result['relationships_incident']}")
    lines.append("  (removed automatically by DETACH DELETE)")
    lines.append("")
    lines.append("NOTHING WAS DELETED. Re-run with --yes to perform the teardown.")
    lines.append("Existing Issue / Stamp / Variety nodes are never touched.")
    lines.append("=" * 64)
    return "\n".join(lines)


def _render_teardown(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 64)
    lines.append("FIRST ISSUE GRAPHRAG — TEARDOWN (DELETED)")
    lines.append("=" * 64)
    lines.append(f"prototype tag: {result['prototype_tag']}")
    lines.append("")
    lines.append("Deleted nodes:")
    for label, n in result["deleted_nodes_by_label"].items():
        lines.append(f"  {label:<14} {n}")
    lines.append(f"  {'TOTAL':<14} {result['deleted_nodes_total']}")
    lines.append("")
    lines.append(f"Relationships incident before deletion: {result['relationships_incident_before']}")
    lines.append("  (removed by DETACH DELETE)")
    if result["dropped_indexes"] or result["dropped_constraints"]:
        lines.append("")
        lines.append(f"Dropped indexes:     {', '.join(result['dropped_indexes']) or '(none)'}")
        lines.append(f"Dropped constraints: {', '.join(result['dropped_constraints']) or '(none)'}")
    lines.append("")
    lines.append("Existing Issue / Stamp / Variety nodes were NOT touched.")
    lines.append("=" * 64)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove ONLY First Issue GraphRAG prototype data from Neo4j.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag the command is a dry run and deletes nothing.",
    )
    parser.add_argument(
        "--drop-indexes",
        action="store_true",
        help="Also drop the prototype fulltext index (chunk_text_fts) and prototype unique constraints.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    if not args.yes:
        result = plan()
        print(_render_plan(result))
        return 0

    result = teardown(drop_indexes=args.drop_indexes)
    print(_render_teardown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
