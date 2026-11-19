"""
Ground-truth + coverage evaluation for the First Issue lexical graph.

READ-ONLY. Connects to Neo4j (and optionally Weaviate) and prints:
  1. Coverage stats (documents, chunks, linked chunks, stamp mentions, per-doc spread).
  2. link_score distribution (so we can see how strong each link is).
  3. A PRECISION SAMPLE: the strongest-linked and the weakest-linked chunks with
     their actual text + the signals that fired — so a human can judge whether the
     passage is genuinely about the 1863 First Issue (real) or a false positive.
  4. Per-stamp mention breakdown (Mena 1/2/3/4).
  5. Domain join (Issue -> Mena Stamp -> EQUIVALENT_TO -> Scott).

Usage:
    python first_issue_graphrag/evaluate.py
    python first_issue_graphrag/evaluate.py --top 20 --weak 20 --snippet 400
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from config import ISSUE_ID, PROTOTYPE_TAG, NEO4J_DATABASE, neo4j_driver

# Windows consoles default to cp1252 and choke on ½ / ⁄ etc. in chunk text.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover - older/odd stdouts
    pass


def _read(session, cypher: str, **params):
    return session.execute_read(lambda tx: list(tx.run(cypher, **params)))


def _snip(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return textwrap.shorten(text, width=n, placeholder=" …")


def coverage(session) -> None:
    print("=" * 78)
    print("COVERAGE")
    print("=" * 78)
    rows = _read(session, "MATCH (d:Document {prototype:$t}) RETURN count(d) AS n", t=PROTOTYPE_TAG)
    docs = rows[0]["n"]
    chunks = _read(session, "MATCH (c:Chunk {prototype:$t}) RETURN count(c) AS n", t=PROTOTYPE_TAG)[0]["n"]
    linked = _read(
        session,
        "MATCH (c:Chunk)-[:MENTIONS]->(:Issue {issue_id:$iid}) RETURN count(DISTINCT c) AS n",
        iid=ISSUE_ID,
    )[0]["n"]
    mstamp = _read(
        session,
        "MATCH (:Chunk)-[m:MENTIONS_STAMP]->(:Stamp {issue_id:$iid}) RETURN count(m) AS n",
        iid=ISSUE_ID,
    )[0]["n"]
    print(f"Documents (prototype):        {docs}")
    print(f"Chunk nodes (prototype):      {chunks}")
    print(f"Chunks linked to First Issue: {linked}  ({(100*linked/chunks if chunks else 0):.1f}% of materialized chunks)")
    print(f"MENTIONS_STAMP edges:         {mstamp}")

    print("\nPer-document linked-chunk counts:")
    rows = _read(
        session,
        """MATCH (c:Chunk)-[:MENTIONS]->(:Issue {issue_id:$iid})
           RETURN c.doc_id AS doc, count(*) AS n ORDER BY n DESC""",
        iid=ISSUE_ID,
    )
    for r in rows:
        print(f"   {r['doc']:<16} {r['n']}")


def score_distribution(session) -> None:
    print("\n" + "=" * 78)
    print("link_score DISTRIBUTION (linked chunks)")
    print("=" * 78)
    rows = _read(
        session,
        """MATCH (c:Chunk)-[:MENTIONS]->(:Issue {issue_id:$iid})
           WITH c.link_score AS s
           RETURN
             CASE
               WHEN s >= 12 THEN '12+  (very strong)'
               WHEN s >= 8  THEN '8-11 (strong)'
               WHEN s >= 6  THEN '6-7  (solid)'
               WHEN s >= 4  THEN '4-5  (threshold)'
               ELSE '<4   (phrase-gated)'
             END AS bucket, count(*) AS n
           ORDER BY bucket DESC""",
        iid=ISSUE_ID,
    )
    for r in rows:
        print(f"   {r['bucket']:<22} {r['n']}")


def stamp_breakdown(session) -> None:
    print("\n" + "=" * 78)
    print("PER-STAMP MENTIONS (Mena catalog_no)")
    print("=" * 78)
    rows = _read(
        session,
        """MATCH (:Chunk)-[m:MENTIONS_STAMP]->(s:Stamp {issue_id:$iid})
           RETURN s.catalog_no AS mena, s.denomination_value AS val, s.denomination_unit AS unit,
                  s.color AS color, count(*) AS mentions, avg(m.confidence) AS avg_conf
           ORDER BY mentions DESC""",
        iid=ISSUE_ID,
    )
    for r in rows:
        print(f"   Mena {r['mena']:<4} {str(r['val'])+' '+str(r['unit']):<10} {str(r['color']):<10} "
              f"mentions={r['mentions']:<4} avg_conf={r['avg_conf']:.2f}")


def domain_join(session) -> None:
    print("\n" + "=" * 78)
    print("DOMAIN JOIN  (Issue -> Mena Stamp -> EQUIVALENT_TO -> Scott)")
    print("=" * 78)
    rows = _read(
        session,
        """MATCH (i:Issue {issue_id:$iid})-[:HAS_SCOTT_STAMP]->(ss:ScottStamp)
           OPTIONAL MATCH (st:Stamp {issue_id:$iid})-[:EQUIVALENT_TO]->(ss)
           OPTIONAL MATCH (ss)-[:DEPICTS]->(ill:Illustration)
           RETURN ss.scott_number AS scott, st.catalog_no AS mena,
                  ss.denomination AS denom, ss.color AS color,
                  ss.mint_value AS mint, ss.used_value AS used, ill.design_name AS design
           ORDER BY scott""",
        iid=ISSUE_ID,
    )
    for r in rows:
        print(f"   Scott {str(r['scott']):<4} <= Mena {str(r['mena']):<4} "
              f"{str(r['denom']):<5} {str(r['color']):<8} mint={r['mint']} used={r['used']} design={r['design']}")


def precision_sample(session, top: int, weak: int, snippet: int) -> None:
    print("\n" + "=" * 78)
    print(f"PRECISION SAMPLE — TOP {top} STRONGEST-LINKED CHUNKS (judge: real first-issue content?)")
    print("=" * 78)
    rows = _read(
        session,
        """MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:$iid})
           OPTIONAL MATCH (c)-[:MENTIONS_STAMP]->(s:Stamp {issue_id:$iid})
           WITH c, m, collect(DISTINCT s.catalog_no) AS stamps
           RETURN c.doc_id AS doc, c.page AS page, c.link_score AS score,
                  m.signals AS signals, stamps, c.text AS text
           ORDER BY c.link_score DESC LIMIT $lim""",
        iid=ISSUE_ID, lim=top,
    )
    for i, r in enumerate(rows, 1):
        print(f"\n[{i}] {r['doc']} p.{r['page']}  score={r['score']}  stamps={r['stamps']}  signals={r['signals']}")
        print("    " + _snip(r["text"], snippet))

    print("\n" + "=" * 78)
    print(f"WEAKEST {weak} LINKED CHUNKS (borderline — most likely false positives)")
    print("=" * 78)
    rows = _read(
        session,
        """MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:$iid})
           RETURN c.doc_id AS doc, c.page AS page, c.link_score AS score,
                  m.signals AS signals, c.text AS text
           ORDER BY c.link_score ASC LIMIT $lim""",
        iid=ISSUE_ID, lim=weak,
    )
    for i, r in enumerate(rows, 1):
        print(f"\n[{i}] {r['doc']} p.{r['page']}  score={r['score']}  signals={r['signals']}")
        print("    " + _snip(r["text"], snippet))


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the First Issue lexical graph (read-only).")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--weak", type=int, default=15)
    ap.add_argument("--snippet", type=int, default=360)
    args = ap.parse_args()

    with neo4j_driver() as drv, drv.session(database=NEO4J_DATABASE) as session:
        coverage(session)
        score_distribution(session)
        stamp_breakdown(session)
        domain_join(session)
        precision_sample(session, args.top, args.weak, args.snippet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
