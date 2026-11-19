"""
Graph-first context bundle for a First Issue question (read-only), ready to paste
into an LLM. The GRAPH is the knowledge base and gets predominance:

    DOMAIN facts  ->  RELATED graph entities  ->  ranked SOURCE DOCS  ->
    ALL good LEXICAL passages (quality-gated, deduped, full text)  ->
    thin WEAVIATE backup (slow/heavy; capped, only fills gaps).

Cheap Cypher does the heavy lifting; Weaviate is a small backup tail.

Usage:
    python -m oxcart.examples_runner --demo
    python -m oxcart.examples_runner --q "the first issue plate crack and its positions" --stamp 1
    ... --q "..." --max-lexical 0 --min-link 6 --k-weaviate 5 --width 1200

Knobs:
    --max-lexical N   max graph passages (0 = ALL good ones).        default 0
    --min-link F      quality gate on the MENTIONS score.            default 6
    --include-competing  keep COMPETING-flagged chunks too.          default off
    --k-weaviate N    Weaviate BACKUP passages (clamped to <=25).    default 5
    --stamp C         scope to a Mena stamp (1=1/2r, 2=2r, 3=4r, 4=1p).
    --width N         characters per passage; 0 = FULL text (no truncation). default 0
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from oxcart import retrieve

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Every run writes a transcript here (created on demand).
OUT_DIR = Path(__file__).resolve().parent / "results"


@contextlib.contextmanager
def _tee_stdout(buf: io.StringIO):
    """Temporarily mirror everything printed to both the real stdout and ``buf``."""
    real = sys.stdout

    class _Tee:
        def write(self, s: str) -> int:
            real.write(s)
            buf.write(s)
            return len(s)

        def flush(self) -> None:
            real.flush()

    sys.stdout = _Tee()
    try:
        yield
    finally:
        sys.stdout = real


def _slug(question: str, stamp: Optional[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (question or "").lower()).strip("_")[:50] or "query"
    if stamp:
        base += f"_s{stamp}"
    return f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

DEMO = [
    ("How many covers exist of the 1 peso of the first issue?", "4"),
    ("What are the main varieties of the first issue?", None),
    ("the first issue plate crack and its positions", "1"),
    ("What is the 4 reales double transfer at plate position 8?", "3"),
]


def _wrap(text: str, width: int) -> str:
    """Collapse whitespace. ``width <= 0`` -> FULL text (no truncation) — the
    default, so the saved transcript is complete for LLM hand-off."""
    s = " ".join((text or "").split())
    if width and width > 0:
        return textwrap.shorten(s, width=width, placeholder=" …")
    return s


def _fmt_score(v: Any) -> str:
    return f"{v:.2f}" if isinstance(v, (int, float)) else "n/a"


def run(question: str, stamp: Optional[str], max_lexical: int, min_link: float,
        k_weaviate: int, width: int, include_competing: bool) -> None:
    print("\n" + "#" * 90)
    print(f"# QUESTION: {question}")
    print(f"# scope: stamp={stamp or 'all'} | min_link={min_link} | "
          f"max_lexical={'ALL' if not max_lexical else max_lexical} | "
          f"competing={'kept' if include_competing else 'excluded'} | k_weaviate<=25={k_weaviate}")
    print("#" * 90)

    b = retrieve.context_bundle(
        question, stamp=stamp, max_lexical=max_lexical, k_weaviate=k_weaviate,
        min_link_score=min_link, exclude_competing=not include_competing,
    )
    d = b["domain"]
    rel = b["related"]
    sources = b["sources"]
    lexical = b["lexical"]
    weav = b["weaviate"]

    # 1) DOMAIN FACTS
    print("\n=== 1) DOMAIN FACTS (graph — authoritative) ===")
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

    # 2) RELATED graph entities (cheap one-hop expansion)
    print("\n=== 2) RELATED GRAPH ENTITIES (cheap Cypher) ===")
    for sv in rel.get("stamp_varieties", []):
        vs = ", ".join(sv.get("varieties") or []) or "(none)"
        print(f"  Mena {sv.get('stamp')} varieties: {vs}")
    if rel.get("proofs"):
        print(f"  Proofs ({len(rel['proofs'])}): {', '.join(rel['proofs'])}")
    if rel.get("plates"):
        print(f"  Plates: {', '.join(str(p) for p in rel['plates'])}")

    # 3) SOURCE DOCUMENTS that reference this (ranked by quality)
    print(f"\n=== 3) SOURCE DOCUMENTS referencing this query ({len(sources)} docs, ranked) ===")
    for s in sources:
        pages = ", ".join(f"p.{p}" for p in s.get("pages", []))
        print(f"  {s['doc_id']:<24} chunks={s['chunks']:<3} "
              f"best_ft={_fmt_score(s.get('best_score'))} best_link={_fmt_score(s.get('best_link'))}  [{pages}]")

    # 4) LEXICAL passages (the graph evidence — ALL good, deduped, full text)
    print(f"\n=== 4) LEXICAL EVIDENCE — graph passages ({len(lexical)} good, deduped, full text) ===")
    for i, c in enumerate(lexical, 1):
        print(f"\n  [{i}] {c.get('doc_id')} p.{c.get('page')} "
              f"(link_score {_fmt_score(c.get('link_score'))}, ft {_fmt_score(c.get('score'))}, via {c.get('via')})")
        print(f"      {_wrap(c.get('text'), width)}")

    # 5) WEAVIATE backup
    print(f"\n=== 5) WEAVIATE BACKUP ({len(weav)}, slow/heavy — gap-filler only) ===")
    if not weav:
        print("  (none needed — the graph covered it)")
    for i, c in enumerate(weav, 1):
        print(f"  [{i}] {c.get('doc_id')} p.{c.get('page')} (score {_fmt_score(c.get('score'))}, via {c.get('via')})")
        print(f"      {_wrap(c.get('snippet'), width)}")

    print(f"\n--- counts: {b['counts']} ---")


def main() -> int:
    ap = argparse.ArgumentParser(description="Graph-first First Issue context bundle (read-only).")
    ap.add_argument("--q")
    ap.add_argument("--stamp", help="Mena catalog_no to scope (1=1/2r, 2=2r, 3=4r, 4=1p).")
    ap.add_argument("--max-lexical", type=int, default=0, help="Max graph passages (0 = ALL good).")
    ap.add_argument("--min-link", type=float, default=6.0, help="Quality gate on MENTIONS score.")
    ap.add_argument("--k-weaviate", type=int, default=5, help="Weaviate backup passages (<=25).")
    ap.add_argument("--include-competing", action="store_true", help="Keep COMPETING-flagged chunks.")
    ap.add_argument("--width", type=int, default=0,
                    help="Characters per passage; 0 = FULL text, no truncation (default — best for LLM hand-off).")
    ap.add_argument("--demo", action="store_true", help="Run the four canned demo questions.")
    args = ap.parse_args()

    jobs = DEMO if args.demo else ([(args.q, args.stamp)] if args.q else None)
    if jobs is None:
        ap.error("provide --q or --demo")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for q, stamp in jobs:
        buf = io.StringIO()
        with _tee_stdout(buf):
            run(q, stamp, args.max_lexical, args.min_link, args.k_weaviate, args.width, args.include_competing)
        out_path = OUT_DIR / _slug(q, stamp)
        out_path.write_text(buf.getvalue(), encoding="utf-8")
        print(f"\n[saved] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
