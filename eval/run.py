"""Run the passage-search arms on the test set and score them.

    python -m eval.run --label collapsed [--split dev] [--k 20] [--app-today]

The Weaviate target comes from the environment (eval/stores.py); --label names it in the
output. Questions come from local-data/eval/: questions_literature.jsonl (judged, from
eval/judgments.py) and drafts_out_of_scope.jsonl. Until judged questions exist the run
still records what each arm returns for the drafts, without scoring.

Writes local-data/eval/results/run_<label>_<split>.json (ids, pages, ranks, scores and
timings only: no passage text) and prints the tables.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from eval import app_today, arms, embed, split, stores
from eval.scoring import score, top_scores

DATA = stores.REPO / "local-data" / "eval"
ALPHAS = (0.25, 0.35, 0.5, 0.75)


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def questions_for(which: str) -> tuple[list[dict], bool]:
    """(questions, judged). Literature questions carry gold only once a reviewer has judged them."""
    literature = load(stores.data_file("questions_literature.jsonl"))
    judged = bool(literature)
    if not judged:
        literature = [dict(q, type="literature") for q in load(stores.data_file("drafts_literature.jsonl"))]
    everything = literature + load(stores.data_file("questions_out_of_scope.jsonl"))
    sides = split.assign(everything)
    for q in everything:
        q["split"] = sides[q["id"]]
    return [q for q in everything if which == "all" or q["split"] == which], judged


def run_arms(questions: list[dict], k: int, with_app: bool) -> tuple[dict, dict]:
    vectors, embedding = embed.question_vectors([q["question"] for q in questions])
    client, name, target, where = stores.weaviate_target()
    results: dict[str, dict] = {}
    try:
        coll = client.collections.get(name)
        count = coll.aggregate.over_all(total_count=True).total_count
        dims = int(target[1:]) if target and target[1:].isdigit() else None
        table = arms.all_arms(alphas=ALPHAS)
        for q in questions:
            v = embed.cut(vectors[q["question"]], dims)
            per_arm = {}
            for arm, fn in table.items():
                t0 = time.time()
                hits = fn(coll, q["question"], v, k, target)
                per_arm[arm] = {"seconds": round(time.time() - t0, 4), "hits": hits}
            if with_app:
                t0 = time.time()
                try:
                    hits = app_today.passages(app_today.ask(q["question"]))[:k]
                    per_arm["app-today"] = {"seconds": round(time.time() - t0, 3), "hits": hits}
                except Exception as exc:
                    per_arm["app-today"] = {"seconds": round(time.time() - t0, 3), "hits": [], "error": type(exc).__name__}
            results[q["id"]] = per_arm
    finally:
        client.close()
    return results, {"collection": name, "vector": target, "where": where, "objects": count, "embedding": embedding}


def print_tables(label: str, which: str, info: dict, judged: bool, scored: dict, tops: dict) -> None:
    print(f"\n{label} | split={which} | {info['collection']} ({info['objects']} objects, vector {info['vector'] or 'default'}, "
          f"{info['where']}) | embedding {info['embedding']}")
    if judged and scored["n"]:
        print(f"\nLiterature questions with gold: {scored['n']}")
        print(f"{'arm':<13}{'answer@5':>16}{'answer@1':>10}{'hit@5':>7}{'recall@10':>11}{'ndcg@10':>9}{'pages@5':>9}{'p50 ms':>8}{'p95 ms':>8}   by language (answer@5)")
        for arm, a in scored["arms"].items():
            h = a["measures"]["answer@5"]
            langs = "  ".join(f"{lang} {v['answer@5']:.0%}" for lang, v in sorted(a["by_lang"].items()))
            cell = f"{h['mean']:.0%} [{h['lo']:.0%}-{h['hi']:.0%}]"
            print(f"{arm:<13}{cell:>16}"
                  f"{a['measures']['answer@1']['mean']:>10.0%}{a['measures']['hit@5']['mean']:>7.0%}"
                  f"{a['measures']['recall@10']['mean']:>11.0%}"
                  f"{a['measures']['ndcg@10']['mean']:>9.2f}{a['distinct_pages_in_top5']:>9.1f}"
                  f"{a['latency']['p50'] * 1000:>8.0f}{a['latency']['p95'] * 1000:>8.0f}   {langs}")
    else:
        print("\nNo judged literature questions yet: the arms ran on the drafts, nothing is scored.")
    print("\nBest score per question, by kind (separation = how often an in-scope question outscores one of that kind; 0.5 = no better than chance)")
    for arm, row in tops.items():
        parts = [f"{k}: median {v['median']:.3f} (n={v['n']})" for k, v in row["groups"].items()]
        sep = "  ".join(f"{k} {v:.2f}" for k, v in row.get("separation", {}).items())
        print(f"  {arm:<13}" + " | ".join(parts) + (f"   separation: {sep}" if sep else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    ap.add_argument("--k", type=int, default=20)
    ap.add_argument("--app-today", action="store_true", help="also ask the running app (OXCART_API)")
    args = ap.parse_args()
    questions, judged = questions_for(args.split)
    results, info = run_arms(questions, args.k, args.app_today)
    scored = score(questions, results) if judged else {"n": 0, "arms": {}}
    tops = top_scores(questions, results)
    out = DATA / "results" / f"run_{args.label}_{args.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"label": args.label, "split": args.split, "judged": judged, "info": info,
                               "questions": [{k: q[k] for k in ("id", "lang", "type", "split") if k in q} for q in questions],
                               "results": results, "scored": scored, "top_scores": tops}, default=str), encoding="utf-8")
    print_tables(args.label, args.split, info, judged, scored, tops)
    print(f"\nwritten: {out.relative_to(stores.REPO)}")


if __name__ == "__main__":
    main()
