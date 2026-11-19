"""Compare two runs of the same questions: what changed between two collections or two instances.

    python -m eval.compare run_A.json run_B.json [--arm keyword]

Per arm: how often both runs return the same first passage and the same first five, the
overlap of the first 5 and 20, and the latency of each. When the runs are scored (judged
literature questions), also the paired difference of B against A on hit-in-top-5 and nDCG,
and the fit rule's verdict for B as a candidate against A as the reference:
    passes when "an answering page in the first five" drops by at most one question (net) and
    the paired interval of the difference is not wholly below zero.
Passages are matched by document and page when ids differ between collections.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from eval import measures, split, stores


def key_of(hit: dict, by_page: bool):
    return (hit.get("doc_id"), hit.get("page")) if by_page else hit.get("uuid") or hit.get("chunk_id")


def overlap(a: dict, b: dict, arm: str, by_page: bool) -> dict:
    top1 = same5 = 0
    o5, o20, sa, sb = [], [], [], []
    ids = [q for q in a["results"] if q in b["results"] and arm in a["results"][q] and arm in b["results"][q]]
    for qid in ids:
        ha = [key_of(h, by_page) for h in a["results"][qid][arm]["hits"]]
        hb = [key_of(h, by_page) for h in b["results"][qid][arm]["hits"]]
        top1 += ha[:1] == hb[:1]
        same5 += set(ha[:5]) == set(hb[:5])
        o5.append(len(set(ha[:5]) & set(hb[:5])) / max(1, len(set(ha[:5]))))
        o20.append(len(set(ha[:20]) & set(hb[:20])) / max(1, len(set(ha[:20]))))
        sa.append(a["results"][qid][arm]["seconds"])
        sb.append(b["results"][qid][arm]["seconds"])
    n = len(ids)
    return {"n": n, "same_top1": top1 / n, "same_top5": same5 / n, "overlap5": statistics.mean(o5),
            "overlap20": statistics.mean(o20), "a": measures.latency_summary(sa), "b": measures.latency_summary(sb)}


def fit_rule(a: dict, b: dict, arm: str, gold: dict) -> dict | None:
    """Paired difference of B against A on the judged questions, and the fit rule's verdict."""
    ids = [q for q in gold if q in a["results"] and q in b["results"]]
    if not ids:
        return None
    out = {}
    for name in ("answer@5", "ndcg@10"):
        fn = measures.MEASURES[name]
        va = [fn(a["results"][q][arm]["hits"], gold[q]) for q in ids]
        vb = [fn(b["results"][q][arm]["hits"], gold[q]) for q in ids]
        out[name] = measures.paired_difference(vb, va)
    lost = out["answer@5"]["worse"] - out["answer@5"]["better"]
    out["questions_lost_net"] = lost
    # "not worse": at most one question lost net, and the interval of the difference not wholly below zero.
    # A candidate that is clearly BETTER than the reference passes.
    out["passes"] = lost <= 1 and out["answer@5"]["hi"] >= 0
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--by-page", action="store_true", help="match passages by document and page, not by id")
    ap.add_argument("--gold", type=Path, help="questions_literature.jsonl, for the paired difference and the fit rule")
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="all", help="which judged questions to compare on")
    args = ap.parse_args()
    a, b = json.loads(args.a.read_text()), json.loads(args.b.read_text())
    gold = {}
    if args.gold and args.gold.exists():
        literature = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines() if line.strip()]
        other = stores.data_file("questions_out_of_scope.jsonl")
        everything = literature + ([json.loads(line) for line in other.read_text(encoding="utf-8").splitlines() if line.strip()]
                                   if other.exists() else [])
        sides = split.assign(everything)
        for q in literature:
            if args.split == "all" or sides[q["id"]] == args.split:
                gold[q["id"]] = q["gold"]["sources"]
    print(f"A = {a['label']} ({a['info']['collection']}, {a['info']['objects']} objects, {a['info']['where']})")
    print(f"B = {b['label']} ({b['info']['collection']}, {b['info']['objects']} objects, {b['info']['where']})")
    print(f"\n{'arm':<13}{'n':>4}{'same #1':>9}{'same top 5':>12}{'overlap@5':>11}{'overlap@20':>12}"
          f"{'A p50 ms':>10}{'B p50 ms':>10}{'B p95 ms':>10}")
    arms = [x for x in next(iter(a["results"].values())) if x in next(iter(b["results"].values()))]
    for arm in arms:
        o = overlap(a, b, arm, args.by_page)
        print(f"{arm:<13}{o['n']:>4}{o['same_top1']:>9.0%}{o['same_top5']:>12.0%}{o['overlap5']:>11.0%}{o['overlap20']:>12.0%}"
              f"{o['a']['p50'] * 1000:>10.0f}{o['b']['p50'] * 1000:>10.0f}{o['b']['p95'] * 1000:>10.0f}")
    if gold:
        n = len([q for q in gold if q in a["results"] and q in b["results"]])
        print(f"\nB against A on {n} judged questions, split={args.split} (difference = B minus A):")
        for arm in arms:
            r = fit_rule(a, b, arm, gold)
            if r:
                h, d = r["answer@5"], r["ndcg@10"]
                print(f"  {arm:<13} answer@5 {h['mean']:+.3f} [{h['lo']:+.3f}, {h['hi']:+.3f}] better {h['better']} worse {h['worse']} | "
                      f"ndcg@10 {d['mean']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}] | fit rule: {'PASS' if r['passes'] else 'FAIL'}")


if __name__ == "__main__":
    main()
