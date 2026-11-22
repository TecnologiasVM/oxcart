"""The graph arm on the catalogue questions: is the right issue found, and is the fact there?

    python -m eval.catalogue_arm --split dev          # development questions only (tuning is done here)
    python -m eval.catalogue_arm --split heldout      # once, for the report

For each question: the lookup's ranked issues, the rank of the gold issue, and whether the
gold value is in that issue's facts at the place the question asks about. Results hold ids,
ranks and booleans only.
"""

from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

from eval import embed, graph_conn, measures, split, stores
from oxcart import catalogue_lookup

QUESTIONS = stores.data_file("questions_catalogue.jsonl")
OUT_DIR = stores.REPO / "local-data" / "eval" / "results"


def _norm(value) -> str:
    return " ".join(str(value).lower().split())


def fact_in_card(question: dict, card: dict | None) -> bool:
    """Is the gold value in the card, at the place this kind of question asks about?"""
    if not card:
        return False
    gold = question["gold"]["value"]
    kind = question["fact"]
    number = (question["gold"]["params"].get("catalog_no") or "").upper()
    stamp = next((s for s in card["stamps"] if (s.get("catalog_no") or "").upper() == number), None)
    if kind == "date_on_sale":
        return card["dates"].get("placed_on_sale") == gold[0]
    if kind == "printer":
        return {_norm(p) for p in card["printers"]} >= {_norm(g) for g in gold}
    if kind == "legal_act":
        return any(_norm(a.get("id")) == _norm(gold[0]) and str(a.get("date")) == gold[1] for a in card["acts"])
    if stamp is None:
        return False
    if kind == "stamp_colour":
        return _norm(stamp.get("color")) == _norm(gold[0])
    if kind == "stamp_quantity":
        return stamp.get("quantity") == gold[0]
    if kind == "varieties":
        have = {_norm(f"{v.get('suffix')}: {v.get('description')}") for v in stamp["varieties"]}
        return have >= {_norm(g) for g in gold}
    if kind == "scott_equivalent":
        return {_norm(s) for s in stamp["scott"]} >= {_norm(g) for g in gold}
    raise ValueError(f"unknown fact kind {kind!r}")


MODES = {"text": (True, False), "vector": (False, True), "both": (True, True)}   # (full-text, vector index)


def run(which: str, k: int = 3, mode: str = "text", only: list[str] | None = None, short: bool = False) -> dict:
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    sides = split.assign(questions)
    chosen = [q for q in questions if which == "all" or sides[q["id"]] == which]
    if only:
        chosen = [q for q in chosen if q["id"] in set(only)]
    use_text, use_vector = MODES[mode]
    vectors, embedded = ({}, {"embedded": 0, "tokens": 0})
    if use_vector:
        vectors, embedded = embed.question_vectors([q["question"] for q in chosen])
    rows = []
    with graph_conn.Graph() as graph:
        for q in chosen:
            t0 = time.time()
            try:
                hits = graph.read("catalogue_lookup", lambda s: catalogue_lookup.lookup(
                    s, q["question"], k=k, question_vector=vectors.get(q["question"]), use_text=use_text, use_short=short))
            except graph_conn.InfrastructureError as exc:
                rows.append({"id": q["id"], "lang": q["lang"], "fact": q["fact"], "infrastructure_error": str(exc)})
                continue
            ids = [h["issue_id"] for h in hits]
            gold_issue = q["issue_ids"][0]
            rank = ids.index(gold_issue) + 1 if gold_issue in ids else None
            card = hits[rank - 1]["card"] if rank else None
            rows.append({
                "id": q["id"], "lang": q["lang"], "fact": q["fact"], "rank": rank, "returned": ids,
                "matched_by": hits[0]["matched_by"] if hits else [],
                "fact_found_top1": bool(rank == 1 and fact_in_card(q, card)),
                "fact_found_top3": bool(rank and fact_in_card(q, card)),
                "seconds": round(time.time() - t0, 3),
            })
    return {"split": which, "k": k, "mode": mode + (" + short vector" if short else ""), "embedding": embedded, "rows": rows}


def table(result: dict) -> str:
    rows = [r for r in result["rows"] if "infrastructure_error" not in r]
    errors = len(result["rows"]) - len(rows)
    lines = [f"catalogue questions, split={result['split']}, lookup={result['mode']}: {len(rows)} scored, "
             f"{errors} infrastructure errors; embedding {result['embedding']}", ""]
    lines.append(f"{'group':<22}{'n':>4}{'issue@1':>10}{'issue@3':>10}{'fact@1':>9}{'fact@3':>9}")
    groups = collections.OrderedDict()
    groups["all"] = rows
    for lang in ("en", "es"):
        groups[lang] = [r for r in rows if r["lang"] == lang]
    for fact in dict.fromkeys(r["fact"] for r in rows):
        groups[fact] = [r for r in rows if r["fact"] == fact]
    for name, g in groups.items():
        if not g:
            continue
        n = len(g)
        lines.append(f"{name:<22}{n:>4}"
                     f"{sum(r['rank'] == 1 for r in g) / n:>10.0%}{sum(bool(r['rank']) for r in g) / n:>10.0%}"
                     f"{sum(r['fact_found_top1'] for r in g) / n:>9.0%}{sum(r['fact_found_top3'] for r in g) / n:>9.0%}")
    if rows:
        ci = measures.bootstrap_mean([1.0 if r["rank"] == 1 else 0.0 for r in rows])
        lat = measures.latency_summary(r["seconds"] for r in rows)
        lines += ["", f"issue@1 = {ci['mean']:.0%} (95% interval {ci['lo']:.0%} to {ci['hi']:.0%}); "
                      f"latency p50 {lat['p50']:.2f} s, p95 {lat['p95']:.2f} s (one driver, reused)"]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    ap.add_argument("--mode", choices=list(MODES), default="text")
    ap.add_argument("--short", action="store_true",
                    help="also ask the short vector index (the graph must hold it: scripts/issue_short_vectors.py)")
    ap.add_argument("--misses", action="store_true", help="list the questions whose issue was not ranked first")
    ap.add_argument("--label", default="", help="added to the result file's name (a run against another instance)")
    ap.add_argument("--only", nargs="+", metavar="ID",
                    help="these questions only: to finish a run whose other questions were already scored")
    args = ap.parse_args()
    result = run(args.split, mode=args.mode, only=args.only, short=args.short)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"catalogue_{args.split}_{args.mode}" + ("_short" if args.short else "") + (f"_{args.label}" if args.label else "")
    (OUT_DIR / f"{name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(table(result))
    if args.misses:
        for r in result["rows"]:
            if r.get("rank") != 1:
                print("  miss:", r["id"], r.get("rank"), r.get("matched_by"), (r.get("returned") or [])[:3])
    print("graph connections:", json.dumps(graph_conn.summary()))
