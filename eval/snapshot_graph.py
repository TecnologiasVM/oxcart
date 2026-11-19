"""Read-only snapshot of the catalogue facts in the graph, for building and checking the test set.

    python -m eval.snapshot_graph            # writes local-data/eval/catalogue_snapshot.json

One driver, a handful of reads, a few spaced attempts (new connections to a hosted
instance can fail). The snapshot holds catalogue facts only: issues, stamps, printers,
authorizing acts, varieties, Scott equivalents. No embeddings, no raw catalogue text.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eval import stores

OUT = stores.REPO / "local-data" / "eval" / "catalogue_snapshot.json"

QUERIES = {
    "issues": """
        MATCH (i:Issue)
        RETURN i.issue_id AS issue_id, i.title AS title, i.section AS section,
               i.issue_dates AS issue_dates, i.perforation AS perforation
        ORDER BY i.issue_id""",
    "stamps": """
        MATCH (i:Issue)-[:HAS_STAMP]->(s:Stamp)
        RETURN i.issue_id AS issue_id, s.catalog_no AS catalog_no, s.denomination_value AS value,
               s.denomination_unit AS unit, s.color AS color, s.quantity_reported AS quantity,
               s.status AS status, s.perforation AS perforation
        ORDER BY i.issue_id, s.catalog_no""",
    "printers": """
        MATCH (i:Issue)-[:PRINTED_BY]->(p:Printer)
        RETURN i.issue_id AS issue_id, p.name AS name ORDER BY i.issue_id, p.name""",
    "acts": """
        MATCH (i:Issue)-[:AUTHORIZED_BY]->(a:LegalAct)
        RETURN i.issue_id AS issue_id, a.type AS type, a.id AS id, a.date AS date
        ORDER BY i.issue_id, a.date, a.id""",
    "varieties": """
        MATCH (s:Stamp)-[:HAS_VARIETY]->(v:Variety)
        RETURN s.issue_id AS issue_id, s.catalog_no AS catalog_no, v.suffix AS suffix, v.type AS type,
               v.description AS description
        ORDER BY s.issue_id, s.catalog_no, v.suffix""",
    "scott": """
        MATCH (s:Stamp)-[:EQUIVALENT_TO]->(sc:ScottStamp)
        RETURN s.issue_id AS issue_id, s.catalog_no AS catalog_no, sc.scott_number AS scott_number
        ORDER BY s.issue_id, s.catalog_no""",
}


def read_all() -> dict:
    driver, database = stores.neo4j_session_factory()
    with driver, driver.session(database=database, default_access_mode="READ") as session:
        out = {name: [dict(r) for r in session.run(q)] for name, q in QUERIES.items()}
    for issue in out["issues"]:
        raw = issue.get("issue_dates")
        try:
            issue["issue_dates"] = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except ValueError:
            issue["issue_dates"] = {}
    return out


def main(out_path: Path = OUT, attempts: int = 4, pause: float = 20.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            data = read_all()
            break
        except Exception as exc:  # the class only: a driver message can hold the address
            if type(exc).__name__ in ("CypherSyntaxError", "ClientError") or attempt == attempts:
                raise
            print(f"attempt {attempt} of {attempts} failed: {type(exc).__name__}; retrying in {pause:.0f} s")
            time.sleep(pause)
    data["snapshot_date"] = time.strftime("%Y-%m-%d")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print({k: len(v) for k, v in data.items() if isinstance(v, list)}, "->", out_path.relative_to(stores.REPO))


if __name__ == "__main__":
    main()
