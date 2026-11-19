"""Score stored runs again with the current gold, without searching again.

    python -m eval.table run_a.json [run_b.json ...] [--split dev|heldout|all] [--arms keyword vector]

Gold grows when more pages are judged; the passages each arm returned do not change. This
reads the runs written by eval/run.py and the current questions_literature.jsonl, and
prints one line per collection and arm.

Two denominators. A draft question entered the set only when the pooled results already held
a page that answers it, so the drafts that were left out are the ones retrieval may have
failed on. Beside answer@5 over the questions in the set, the table gives the same count over
ALL drafts, the left-out ones counted as misses. The true figure lies between the two.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from eval import scoring, split, stores

GOLD = stores.data_file("questions_literature.jsonl")
DRAFTS = stores.data_file("drafts_literature.jsonl")


def left_out_sides(drafts: list[dict], sides: dict[str, str]) -> dict[str, str]:
    """A side for each draft that is not in the set, without moving any question that is.

    A left-out draft whose other-language version is in the set takes that version's side.
    The others are shuffled with the split's seed and shared out in the split's proportion.
    """
    by_pair = {}
    for d in drafts:
        if d["id"] in sides and d.get("pair"):
            by_pair[d["pair"]] = sides[d["id"]]
    out, alone = {}, []
    for d in drafts:
        if d["id"] in sides:
            continue
        if d.get("pair") in by_pair:
            out[d["id"]] = by_pair[d["pair"]]
        else:
            alone.append(d["id"])
    alone.sort()
    random.Random(f"{split.SEED}:left-out").shuffle(alone)
    n_dev = round(len(alone) * split.DEV_SHARE)
    for i, qid in enumerate(alone):
        out[qid] = "dev" if i < n_dev else "heldout"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    ap.add_argument("--arms", nargs="*")
    args = ap.parse_args()
    literature = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    extra = stores.data_file("questions_out_of_scope.jsonl")
    everything = literature + [json.loads(line) for line in extra.read_text(encoding="utf-8").splitlines() if line.strip()]
    sides = split.assign(everything)
    chosen = [q for q in literature if args.split == "all" or sides[q["id"]] == args.split]
    drafts = [json.loads(line) for line in DRAFTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    left_out = left_out_sides(drafts, {q["id"]: sides[q["id"]] for q in literature})
    missing = sorted(qid for qid, side in left_out.items() if args.split == "all" or side == args.split)
    every = len(chosen) + len(missing)
    print(f"split={args.split}: {len(chosen)} literature questions; gold pages {sum(len(s['pages']) for q in chosen for s in q['gold']['sources'])}")
    print(f"drafts left out of the set on this side, counted as misses in 'of all drafts': {len(missing)} {missing}")
    print(f"{'collection':<12}{'objects':>8}  {'arm':<12}{'answer@5':>17}{'of all drafts':>16}{'answer@1':>10}{'hit@5':>7}{'recall@10':>11}{'ndcg@10':>9}{'pages@5':>9}{'en':>6}{'es':>6}")
    for path in args.runs:
        run = json.loads(path.read_text(encoding="utf-8"))
        usable = [q for q in chosen if q["id"] in run["results"]]
        scored = scoring.score(usable, {q["id"]: run["results"][q["id"]] for q in usable})
        for arm, a in scored["arms"].items():
            if args.arms and arm not in args.arms:
                continue
            h = a["measures"]["answer@5"]
            cell = f"{h['mean']:.0%} [{h['lo']:.0%}-{h['hi']:.0%}]"
            answered = round(h["mean"] * len(usable))
            wide = f"{answered}/{every} {answered / every:.0%}" if len(usable) == len(chosen) else "n/a"
            langs = a["by_lang"]
            print(f"{run['label']:<12}{run['info']['objects']:>8}  {arm:<12}{cell:>17}{wide:>16}{a['measures']['answer@1']['mean']:>10.0%}"
                  f"{a['measures']['hit@5']['mean']:>7.0%}{a['measures']['recall@10']['mean']:>11.0%}"
                  f"{a['measures']['ndcg@10']['mean']:>9.2f}{a['distinct_pages_in_top5']:>9.1f}"
                  f"{langs.get('en', {}).get('answer@5', float('nan')):>6.0%}{langs.get('es', {}).get('answer@5', float('nan')):>6.0%}")
        if len(usable) != len(chosen):
            print(f"  ({len(chosen) - len(usable)} questions are not in {path.name})")


if __name__ == "__main__":
    main()
