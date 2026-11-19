"""Regression checks for the Mena Catalogue backend (data + service + HTTP).

Run directly (loose harness, no pytest):

    cd first_issue_graphrag/backend
    python test_mena_backend.py

Data-dependent assertions (Scott match counts, stamp rosters) are CONDITIONAL on
the match-catalogue files being present; the pure-Python and graph-backed checks
always run. Requires Neo4j up for the service/HTTP sections; Weaviate is optional
(evidence degrades to an empty list when it is down).
"""

from __future__ import annotations

import json

from app import mena_data, mena_service as ms

PASS = 0
FAIL = 0


def check(label: str, ok: bool, extra: str = "") -> None:
    global PASS, FAIL
    mark = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{mark}] {label}{(' — ' + extra) if extra else ''}")


def main() -> None:
    print("== mena_data (file-backed; degrades to empty) ==")
    stats = mena_data.match_stats()
    check("match_stats returns int dict", isinstance(stats, dict) and all(isinstance(v, int) for v in stats.values()), str(stats))
    check("scott_match_for(missing) == []", mena_data.scott_match_for("CR-NOPE") == [])
    has_data = stats["issues_with_match"] > 0
    if has_data:
        rows = mena_data.scott_match_for("CR-1863-FIRST-ISSUE")
        check("First Issue has 5 Scott matches", len(rows) == 5, f"{len(rows)} rows")
        check("matches are enriched with scott_detail", all("scott_detail" in r for r in rows))
        check("confidence kept as string", all(isinstance(r["confidence"], (str, type(None))) for r in rows))
    else:
        print("  (match files absent — skipping value assertions)")

    print("== mena_service.parse_year (pure) ==")
    check("CR-1863-... -> 1863", ms.parse_year("CR-1863-FIRST-ISSUE") == "1863")
    check("CR-GUANACASTE-1885-1892 -> Undated", ms.parse_year("CR-GUANACASTE-1885-1892") == "Undated")
    check("CR-RADIOGRAM-SEALS -> Undated", ms.parse_year("CR-RADIOGRAM-SEALS") == "Undated")
    check("_parse_issue_dates parses JSON string", isinstance(ms._parse_issue_dates('{"a": 1}'), dict))
    check("_parse_issue_dates passes non-JSON through", ms._parse_issue_dates("nope") == "nope")

    print("== mena_service (live Neo4j) ==")
    import config

    driver = config.neo4j_driver()
    try:
        years = ms.list_surface_mail(driver)
        total = sum(y["count"] for y in years)
        check("list_surface_mail returns issues", total > 100, f"{total} issues / {len(years)} years")
        check("Undated bucket sorts last", years[-1]["year"] == "Undated" if any(y["year"] == "Undated" for y in years) else True)

        detail = ms.issue_detail(driver, "CR-1863-FIRST-ISSUE")
        check("issue_detail(First Issue) found", detail is not None)
        if detail:
            check("First Issue has stamps", len(detail["stamps"]) >= 5, f"{len(detail['stamps'])} stamps")
            check("issue_dates parsed to object", isinstance(detail["issue"].get("issue_dates"), (dict, list, type(None))))
            blob = json.dumps(detail, default=str).lower()
            leaked = [x for x in ("embedding", "vector", "search_corpus", "pictures_raw") if x in blob]
            check("no embedding/vector/noise leak in detail", not leaked, f"leaked: {leaked}" if leaked else "")

        check("issue_detail(missing) is None", ms.issue_detail(driver, "DOES-NOT-EXIST") is None)
        check("issue_exists(missing) is False", ms.issue_exists(driver, "DOES-NOT-EXIST") is False)

        graph = ms.issue_graph(driver, "CR-1863-FIRST-ISSUE")
        types = {n.type for n in graph.nodes}
        check("issue_graph has nodes", len(graph.nodes) > 0, f"{len(graph.nodes)} nodes")
        check("issue_graph excludes Chunk/Document", not ({"Chunk", "Document"} & types), f"types={sorted(types)}")

        ev = ms.issue_evidence(driver, "CR-1863-FIRST-ISSUE", k=3)
        check("issue_evidence returns dict with query+passages", set(ev) == {"query", "passages"})
        check("issue_evidence respects k cap", len(ev["passages"]) <= 3, f"{len(ev['passages'])} passages")
    finally:
        driver.close()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
