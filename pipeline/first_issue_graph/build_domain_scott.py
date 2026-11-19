"""
Extend the EXISTING Neo4j domain graph with the *Scott* layer for the First Issue.

This script is purely ADDITIVE and NAMESPACED. Every node and relationship it
creates carries ``prototype = config.PROTOTYPE_TAG`` so ``teardown.py`` can remove
only our data without touching the pre-existing Mena domain graph.

What it does (idempotently — safe to run repeatedly):
  * Loads ``config.SCOTT_DETAILS_PATH`` (scott_first_issue.json) and
    ``config.SCOTT_EQUIV_PATH`` (scott_equivalences.json).
  * Creates uniqueness constraints (IF NOT EXISTS) for ScottStamp.scott_number
    and Illustration.illustration_number.
  * MERGEs Illustration nodes from ``illustrations[]``.
  * MERGEs ScottStamp nodes from ``stamps[]`` (sets all present props + tag).
  * For stamps with ``variety_of``: MERGE (child)-[:VARIETY_OF]->(parent).
  * MERGE (Issue {issue_id:ISSUE_ID})-[:HAS_SCOTT_STAMP]->(ScottStamp) for every
    Scott stamp, and (ScottStamp)-[:DEPICTS]->(Illustration) when an
    illustration is set.
  * From ``equivalences[]`` ({mena, scott, confidence}): MATCH the existing
    domain Stamp {issue_id:ISSUE_ID, catalog_no:mena}; if the mena value carries
    a letter suffix (e.g. "1A") and no exact Stamp exists, fall back to the
    matching Variety and use its parent Stamp. MERGE
    (Stamp)-[:EQUIVALENT_TO {confidence, source:"user_provided"}]->(ScottStamp).
    If no Stamp can be resolved, the HAS_SCOTT_STAMP edge still exists and a note
    is recorded.

Run conventions (always the repo venv, from repo root)::

    python pipeline/first_issue_graph/build_domain_scott.py
    python pipeline/first_issue_graph/build_domain_scott.py --verify-only

Public API::

    from build_domain_scott import build_domain_scott
    stats = build_domain_scott()            # opens + closes its own driver
    stats = build_domain_scott(driver=drv)  # reuse a caller-owned driver
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from oxcart.config import (
    ISSUE_ID,
    NEO4J_DATABASE,
    PROTOTYPE_TAG,
    SCOTT_DETAILS_PATH,
    SCOTT_EQUIV_PATH,
    neo4j_driver,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
# Properties on a ScottStamp node that we set when present in the source JSON.
SCOTT_PROP_KEYS: Tuple[str, ...] = (
    "denomination",
    "color",
    "mint_value",
    "used_value",
    "perforation",
    "illustration",
    "variety_of",
    "description",
)

# Split a mena catalog number like "1A" into ("1", "A"); "1" -> ("1", None).
_MENA_SUFFIX_RE = re.compile(r"^\s*(\d+)\s*([A-Za-z])?\s*$")


# --------------------------------------------------------------------------- #
# Data loading (pure)
# --------------------------------------------------------------------------- #
def _load_json(path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_scott_details() -> Dict[str, Any]:
    """Load scott_first_issue.json (stamps[], illustrations[], header, notes[])."""
    return _load_json(SCOTT_DETAILS_PATH)


def load_scott_equivalences() -> List[Dict[str, Any]]:
    """Return the equivalences list for ISSUE_ID from scott_equivalences.json."""
    raw = _load_json(SCOTT_EQUIV_PATH)
    issue_block = raw.get(ISSUE_ID, {}) if isinstance(raw, dict) else {}
    equivs = issue_block.get("equivalences", []) or []
    return [e for e in equivs if isinstance(e, dict)]


def split_mena_number(mena: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a mena catalog number into (digits, suffix-letter).

    >>> split_mena_number("1A")
    ('1', 'A')
    >>> split_mena_number("2")
    ('2', None)
    >>> split_mena_number("")
    (None, None)
    """
    if not mena:
        return None, None
    m = _MENA_SUFFIX_RE.match(str(mena))
    if not m:
        return None, None
    digits, suffix = m.group(1), m.group(2)
    return digits, (suffix or None)


def _scott_props(stamp: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the present, non-null Scott properties from a source stamp dict."""
    return {k: stamp[k] for k in SCOTT_PROP_KEYS if k in stamp and stamp[k] is not None}


# --------------------------------------------------------------------------- #
# Write transaction functions (all parameterized, all idempotent)
# --------------------------------------------------------------------------- #
def _create_constraints(tx) -> None:
    tx.run(
        "CREATE CONSTRAINT scottstamp_number IF NOT EXISTS "
        "FOR (s:ScottStamp) REQUIRE s.scott_number IS UNIQUE"
    ).consume()
    tx.run(
        "CREATE CONSTRAINT illustration_number IF NOT EXISTS "
        "FOR (i:Illustration) REQUIRE i.illustration_number IS UNIQUE"
    ).consume()


def _merge_illustration(tx, illustration: Dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (ill:Illustration {illustration_number: $illustration_number})
        SET ill.design_name        = $design_name,
            ill.design_description = $design_description,
            ill.denomination       = $denomination,
            ill.prototype          = $prototype
        """,
        illustration_number=illustration.get("illustration_number"),
        design_name=illustration.get("design_name"),
        design_description=illustration.get("design_description"),
        denomination=illustration.get("denomination"),
        prototype=PROTOTYPE_TAG,
    ).consume()


def _merge_scott_stamp(tx, scott_number: str, props: Dict[str, Any]) -> None:
    """MERGE a ScottStamp on its unique key; SET all present props + tag.

    ``props`` is applied via ``SET s += $props`` so only present keys are written.
    """
    tx.run(
        """
        MERGE (s:ScottStamp {scott_number: $scott_number})
        SET s += $props,
            s.prototype = $prototype
        """,
        scott_number=scott_number,
        props=props,
        prototype=PROTOTYPE_TAG,
    ).consume()


def _link_issue_has_scott_stamp(tx, scott_number: str) -> None:
    tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id})
        MATCH (s:ScottStamp {scott_number: $scott_number})
        MERGE (i)-[r:HAS_SCOTT_STAMP]->(s)
        SET r.prototype = $prototype
        """,
        issue_id=ISSUE_ID,
        scott_number=scott_number,
        prototype=PROTOTYPE_TAG,
    ).consume()


def _link_scott_depicts(tx, scott_number: str, illustration_number: str) -> None:
    tx.run(
        """
        MATCH (s:ScottStamp {scott_number: $scott_number})
        MATCH (ill:Illustration {illustration_number: $illustration_number})
        MERGE (s)-[r:DEPICTS]->(ill)
        SET r.prototype = $prototype
        """,
        scott_number=scott_number,
        illustration_number=illustration_number,
        prototype=PROTOTYPE_TAG,
    ).consume()


def _link_scott_variety_of(tx, child_scott: str, parent_scott: str) -> None:
    tx.run(
        """
        MATCH (child:ScottStamp {scott_number: $child})
        MATCH (parent:ScottStamp {scott_number: $parent})
        MERGE (child)-[r:VARIETY_OF]->(parent)
        SET r.prototype = $prototype
        """,
        child=child_scott,
        parent=parent_scott,
        prototype=PROTOTYPE_TAG,
    ).consume()


def _link_equivalent_to(
    tx,
    mena: str,
    scott_number: str,
    confidence: Any,
) -> str:
    """Resolve the domain Stamp for ``mena`` and MERGE EQUIVALENT_TO to ScottStamp.

    Resolution strategy:
      1. Exact ``Stamp {issue_id, catalog_no: mena}``.
      2. If mena has a letter suffix (e.g. "1A") and no exact stamp exists,
         OPTIONAL MATCH a ``Variety {issue_id, base_catalog_no: <digits>,
         suffix: <letter>}`` (case-insensitive on the suffix) and use its parent
         Stamp (via HAS_VARIETY).

    Returns a short status string: "exact" | "variety_parent" | "missing".
    The ScottStamp must already exist (created earlier); we only add the edge
    from a resolved Stamp. If no Stamp resolves, the edge is skipped (the
    HAS_SCOTT_STAMP edge created earlier is the durable link).
    """
    digits, suffix = split_mena_number(mena)
    suffix_upper = suffix.upper() if suffix else None
    suffix_lower = suffix.lower() if suffix else None

    record = tx.run(
        """
        // ScottStamp is guaranteed to exist by this point.
        MATCH (sc:ScottStamp {scott_number: $scott_number})

        // 1) Try an exact Stamp match on catalog_no == mena.
        OPTIONAL MATCH (exact:Stamp {issue_id: $issue_id, catalog_no: $mena})

        // 2) Fall back to the parent Stamp of a matching Variety (suffix case-insensitive).
        OPTIONAL MATCH (parent:Stamp {issue_id: $issue_id})-[:HAS_VARIETY]->
                       (v:Variety {issue_id: $issue_id, base_catalog_no: $digits})
            WHERE $suffix_upper IS NOT NULL
              AND (v.suffix = $suffix_upper OR v.suffix = $suffix_lower)

        WITH sc, coalesce(exact, parent) AS stamp,
             CASE WHEN exact IS NOT NULL THEN 'exact'
                  WHEN parent IS NOT NULL THEN 'variety_parent'
                  ELSE 'missing' END AS status
        FOREACH (_ IN CASE WHEN stamp IS NULL THEN [] ELSE [1] END |
            MERGE (stamp)-[r:EQUIVALENT_TO {scott_number: $scott_number}]->(sc)
            SET r.confidence = $confidence,
                r.source     = 'user_provided',
                r.mena       = $mena,
                r.prototype  = $prototype
        )
        RETURN status AS status
        """,
        issue_id=ISSUE_ID,
        scott_number=scott_number,
        mena=str(mena),
        digits=digits,
        suffix_upper=suffix_upper,
        suffix_lower=suffix_lower,
        confidence=confidence,
        prototype=PROTOTYPE_TAG,
    ).single()
    return record["status"] if record else "missing"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def build_domain_scott(driver: Optional[Any] = None) -> Dict[str, Any]:
    """Build/refresh the Scott layer on the existing First Issue domain graph.

    Args:
        driver: An open ``neo4j.Driver``. If ``None``, one is opened via
            ``config.neo4j_driver()`` and closed before returning.

    Returns:
        A stats dict with counts and notes (also useful for tests/CLI readout).
    """
    details = load_scott_details()
    equivalences = load_scott_equivalences()

    stamps: List[Dict[str, Any]] = details.get("stamps", []) or []
    illustrations: List[Dict[str, Any]] = details.get("illustrations", []) or []

    stats: Dict[str, Any] = {
        "issue_id": ISSUE_ID,
        "prototype": PROTOTYPE_TAG,
        "illustrations_merged": 0,
        "scott_stamps_merged": 0,
        "has_scott_stamp_links": 0,
        "depicts_links": 0,
        "variety_of_links": 0,
        "equivalent_to_exact": 0,
        "equivalent_to_variety_parent": 0,
        "equivalent_to_missing": 0,
        "notes": [],
    }

    owns_driver = driver is None
    drv = driver or neo4j_driver()
    try:
        with drv.session(database=NEO4J_DATABASE) as session:
            # 1) Constraints (DDL) — must be its own transaction.
            session.execute_write(_create_constraints)

            # 2) Illustrations.
            for ill in illustrations:
                if not ill.get("illustration_number"):
                    stats["notes"].append("skipped illustration without illustration_number")
                    continue
                session.execute_write(_merge_illustration, ill)
                stats["illustrations_merged"] += 1

            # 3) ScottStamps (+ HAS_SCOTT_STAMP, + DEPICTS).
            for stamp in stamps:
                scott_number = stamp.get("scott_number")
                if not scott_number:
                    stats["notes"].append("skipped stamp without scott_number")
                    continue
                session.execute_write(_merge_scott_stamp, scott_number, _scott_props(stamp))
                stats["scott_stamps_merged"] += 1

                session.execute_write(_link_issue_has_scott_stamp, scott_number)
                stats["has_scott_stamp_links"] += 1

                illustration_number = stamp.get("illustration")
                if illustration_number:
                    session.execute_write(
                        _link_scott_depicts, scott_number, illustration_number
                    )
                    stats["depicts_links"] += 1

            # 4) VARIETY_OF edges (second pass: parents are guaranteed merged).
            for stamp in stamps:
                child = stamp.get("scott_number")
                parent = stamp.get("variety_of")
                if child and parent:
                    session.execute_write(_link_scott_variety_of, child, parent)
                    stats["variety_of_links"] += 1

            # 5) EQUIVALENT_TO edges from user-provided equivalences.
            for equiv in equivalences:
                mena = equiv.get("mena")
                scott_number = equiv.get("scott")
                confidence = equiv.get("confidence")
                if not mena or not scott_number:
                    stats["notes"].append(f"skipped malformed equivalence: {equiv!r}")
                    continue
                status = session.execute_write(
                    _link_equivalent_to, mena, scott_number, confidence
                )
                if status == "exact":
                    stats["equivalent_to_exact"] += 1
                elif status == "variety_parent":
                    stats["equivalent_to_variety_parent"] += 1
                else:
                    stats["equivalent_to_missing"] += 1
                    stats["notes"].append(
                        f"no domain Stamp for mena={mena!r} (scott={scott_number}); "
                        "HAS_SCOTT_STAMP retained, EQUIVALENT_TO skipped"
                    )
    finally:
        if owns_driver:
            drv.close()

    return stats


# --------------------------------------------------------------------------- #
# Verification readout
# --------------------------------------------------------------------------- #
def _verify_read(tx) -> List[Dict[str, Any]]:
    """Return the Issue's ScottStamps with equivalence + illustration context."""
    result = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id})-[:HAS_SCOTT_STAMP]->(s:ScottStamp)
        OPTIONAL MATCH (s)-[:DEPICTS]->(ill:Illustration)
        OPTIONAL MATCH (s)-[:VARIETY_OF]->(parent:ScottStamp)
        OPTIONAL MATCH (m:Stamp)-[eq:EQUIVALENT_TO]->(s)
        RETURN s.scott_number     AS scott_number,
               s.denomination     AS denomination,
               s.color            AS color,
               s.description       AS description,
               parent.scott_number AS variety_of,
               ill.illustration_number AS illustration,
               ill.design_name     AS design_name,
               collect(DISTINCT {
                   mena: m.catalog_no,
                   confidence: eq.confidence,
                   source: eq.source
               })                  AS equivalents
        ORDER BY scott_number
        """,
        issue_id=ISSUE_ID,
    )
    return [record.data() for record in result]


def verify_readout(driver: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Query and return the Issue + ScottStamps + EQUIVALENT_TO + Illustration."""
    owns_driver = driver is None
    drv = driver or neo4j_driver()
    try:
        with drv.session(database=NEO4J_DATABASE) as session:
            return session.execute_read(_verify_read)
    finally:
        if owns_driver:
            drv.close()


def _print_verification(rows: List[Dict[str, Any]]) -> None:
    print(f"\nVerification readout for Issue {ISSUE_ID}")
    print("=" * 70)
    if not rows:
        print("  (no ScottStamps found — has the build run? is Neo4j reachable?)")
        return
    for row in rows:
        head = f"  Scott {row['scott_number']}"
        denom = row.get("denomination")
        color = row.get("color")
        if denom or color:
            head += f"  [{denom or ''} {color or ''}]".rstrip()
        if row.get("variety_of"):
            head += f"  (variety of {row['variety_of']})"
        print(head)
        if row.get("description"):
            print(f"      desc: {row['description']}")
        if row.get("illustration"):
            print(
                f"      depicts: {row['illustration']} "
                f"({row.get('design_name') or 'unnamed'})"
            )
        equivalents = [e for e in (row.get("equivalents") or []) if e.get("mena")]
        if equivalents:
            for e in equivalents:
                print(
                    f"      EQUIVALENT_TO Mena {e['mena']} "
                    f"(confidence={e.get('confidence')}, source={e.get('source')})"
                )
        else:
            print("      EQUIVALENT_TO: (no domain Stamp linked)")


def _print_stats(stats: Dict[str, Any]) -> None:
    print("Scott layer build complete")
    print("-" * 70)
    for key in (
        "illustrations_merged",
        "scott_stamps_merged",
        "has_scott_stamp_links",
        "depicts_links",
        "variety_of_links",
        "equivalent_to_exact",
        "equivalent_to_variety_parent",
        "equivalent_to_missing",
    ):
        print(f"  {key:32s}: {stats[key]}")
    if stats.get("notes"):
        print("  notes:")
        for note in stats["notes"]:
            print(f"    - {note}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add the Scott layer to the existing First Issue Neo4j domain graph "
            "(additive, namespaced, idempotent)."
        )
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip the build; only print the verification readout.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Run the build but skip the verification readout.",
    )
    args = parser.parse_args(argv)

    # One driver for the whole CLI run (build + verify share it).
    with neo4j_driver() as drv:
        if not args.verify_only:
            stats = build_domain_scott(driver=drv)
            _print_stats(stats)
        if not args.no_verify:
            rows = verify_readout(driver=drv)
            _print_verification(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
