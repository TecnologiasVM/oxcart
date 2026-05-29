"""
Read-only demo runner: shows the REAL context bundle retrieve.py would hand an
LLM for a given First Issue question, with FULL passage text (not truncated
snippets) so it reflects a realistic GraphRAG context.

Usage:
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\examples_runner.py --demo
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\examples_runner.py --q "..." --stamp 4
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from typing import Any, Dict, List, Optional

import retrieve
from config import ISSUE_ID, NEO4J_DATABASE, PROTOTYPE_TAG, neo4j_driver

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

DEMO = [
    ("How many covers exist of the 1 peso of the first issue?", "4"),
    ("What are the main varieties of the first issue?", None),
    ("What is the crack plate of the first issue half real?", "1"),
    ("What is the 4 reales double transfer at plate position 8?", "3"),
]


def _wrap(text: str, width: int = 1000) -> str:
    flat = " ".join((text or "").split())
    return textwrap.shorten(flat, width=width, placeholder=" …")


def _full_text(session, chunk_ids: List[str]) -> Dict[str, str]:
    if not chunk_ids:
        return {}
    rows = session.execute_read(
        lambda tx: list(tx.run(
            "MATCH (c:Chunk) WHERE c.chunk_id IN $ids "
            "RETURN c.chunk_id AS id, c.text AS text", ids=chunk_ids))
    )
    return {r["id"]: r["text"] for r in rows}


def _stamp_scoped(session, catalog_no: str, k: int) -> List[Dict[str, Any]]:
    rows = session.execute_read(
        lambda tx: list(tx.run(
            """
            MATCH (c:Chunk {prototype:$tag})-[ms:MENTIONS_STAMP]->(s:Stamp {issue_id:$iid, catalog_no:$cno})
            RETURN c.doc_id AS doc, c.page AS page, c.chunk_id AS id,
                   ms.confidence AS conf, c.link_score AS score, c.text AS text
            ORDER BY ms.confidence DESC, c.link_score DESC
            LIMIT $k
            """, tag=PROTOTYPE_TAG, iid=ISSUE_ID, cno=catalog_no, k=k))
    )
    return [dict(r) for r in rows]


def run(question: str, k: int, stamp: Optional[str], textwidth: int) -> None:
    print("\n" + "#" * 88)
    print(f"# QUESTION: {question}")
    if stamp:
        print(f"# (stamp-scoped to Mena catalog_no '{stamp}')")
    print("#" * 88)

    ctx = retrieve.answer(question, k=k)
    d = ctx["domain"]

    print("\n--- DOMAIN FACTS (Neo4j structured) ---")
    print(f"Issue: {d.get('title')} ({d.get('country')}), perf {d.get('perforation')}")
    if d.get("issue_dates"):
        print(f"Dates: {d.get('issue_dates')}")
    for s in d.get("stamps", []):
        eq = "; ".join(
            f"Scott {x.get('scott_number')} ({x.get('color')}, mint {x.get('mint_value')}, used {x.get('used_value')})"
            for x in s.get("equivalent_scott", [])
        )
        print(f"  - Mena {s.get('catalog_no')}: {s.get('denomination_value')} {s.get('denomination_unit')} "
              f"{s.get('color')} | qty {s.get('quantity_reported')} -> {eq}")

    with neo4j_driver() as drv, drv.session(database=NEO4J_DATABASE) as session:
        n4 = ctx["neo4j_evidence"]
        full = _full_text(session, [c.get("chunk_id") for c in n4 if c.get("chunk_id")])
        print(f"\n--- NEO4J LEXICAL EVIDENCE (top {len(n4)}, FULL text) ---")
        seen = set()
        for c in n4:
            cid = c.get("chunk_id")
            body = _wrap(full.get(cid, c.get("snippet", "")), textwidth)
            key = body[:80]
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{c.get('doc_id')} p.{c.get('page')}] (score {c.get('score')}, via {c.get('via')})")
            print(f"     {body}")

        if stamp:
            ss = _stamp_scoped(session, stamp, k)
            print(f"\n--- STAMP-SCOPED EVIDENCE (chunks that MENTIONS_STAMP Mena {stamp}, FULL text) ---")
            seen = set()
            for r in ss:
                body = _wrap(r["text"], textwidth)
                key = body[:80]
                if key in seen:
                    continue
                seen.add(key)
                print(f"  [{r['doc']} p.{r['page']}] (conf {r['conf']}, link_score {r['score']})")
                print(f"     {body}")

    wv = ctx["weaviate_evidence"]
    print(f"\n--- WEAVIATE BASELINE (top {len(wv)}, snippet prefers text_original) ---")
    seen = set()
    for c in wv:
        body = _wrap(c.get("snippet", ""), textwidth)
        key = body[:80]
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{c.get('doc_id')} p.{c.get('page')}] (score {c.get('score')}, via {c.get('via')})")
        print(f"     {body}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Show the real GraphRAG context bundle for a question (read-only).")
    ap.add_argument("--q")
    ap.add_argument("--stamp", help="Mena catalog_no to scope stamp evidence (1,2,3,4).")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--demo", action="store_true", help="Run the four canned demo questions.")
    args = ap.parse_args()

    if args.demo:
        for q, stamp in DEMO:
            run(q, args.k, stamp, args.width)
    elif args.q:
        run(args.q, args.k, args.stamp, args.width)
    else:
        ap.error("provide --q or --demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
