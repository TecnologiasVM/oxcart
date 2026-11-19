"""Ask the test set through a running backend (POST /api/ask) and score what comes back.

    OXCART_API=https://<backend> OXCART_EVAL_KEY=<secret> python -m eval.ask_arm --label hosted [--split all] [--pace 0.5]

The numbers in EVALUATION.md describe search arms called directly. This asks the same
questions the way a visitor's page does, so the numbers describe the demo: the backend
makes the embedding, runs the catalogue lookup and the literature search, and answers
with the first passages and issues.

- Literature questions: the returned passages (document and page) are written as a run
  file that eval/table.py scores with the same gold and both denominators.
- Catalogue questions: the rank of the gold issue among the returned issues, and whether
  the gold value is in its card, as eval/catalogue_arm.py does.
- Also reported: which mode answered each question, and the time of each block.

The eval's way in is a secret header (OXCART_EVAL_KEY); it is read from the environment
and never printed. Results hold ids, ranks, modes and timings only.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from eval import catalogue_arm, measures, split, stores

API = os.environ.get("OXCART_API", "http://127.0.0.1:8090")
OUT_DIR = stores.REPO / "local-data" / "eval" / "results"


def load(name: str) -> list[dict]:
    path = stores.data_file(name)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def ask(question: str, timeout: float = 90.0, attempts: int = 6) -> tuple[dict | None, float, str | None]:
    """(answer, seconds, error). A 429 is waited out; other failures are returned as an error name."""
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OXCART_EVAL_KEY"):
        headers["X-Oxcart-Eval"] = os.environ["OXCART_EVAL_KEY"]
    body = json.dumps({"question": question}).encode("utf-8")
    error = None
    for _ in range(attempts):
        request = urllib.request.Request(API.rstrip("/") + "/api/ask", data=body, headers=headers)
        t0 = time.time()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read()), time.time() - t0, None
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}"
            if exc.code == 429:
                time.sleep(min(int(exc.headers.get("Retry-After") or 5), 65))
                continue
            if exc.code in (502, 503, 504):
                time.sleep(3)
                continue
            return None, time.time() - t0, error
        except Exception as exc:
            error = type(exc).__name__
            time.sleep(3)
    return None, 0.0, error


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    ap.add_argument("--pace", type=float, default=0.0, help="seconds to wait between questions")
    ap.add_argument("--only", choices=["literature", "catalogue"], help="one part of the test set")
    args = ap.parse_args()

    literature = load("questions_literature.jsonl")
    catalogue = load("questions_catalogue.jsonl")
    lit_sides = split.assign(literature + load("questions_out_of_scope.jsonl"))
    cat_sides = split.assign(catalogue)
    literature = [q for q in literature if args.split == "all" or lit_sides[q["id"]] == args.split]
    catalogue = [q for q in catalogue if args.split == "all" or cat_sides[q["id"]] == args.split]
    if args.only == "literature":
        catalogue = []
    if args.only == "catalogue":
        literature = []

    modes: collections.Counter = collections.Counter()
    blocks: dict[str, list[float]] = collections.defaultdict(list)
    failed: list[str] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def record(answer: dict) -> None:
        modes[json.dumps(answer["mode"], sort_keys=True)] += 1
        for name, ms in answer.get("timings", {}).items():
            blocks[name].append(ms / 1000.0)

    results = {}
    for q in literature:
        answer, seconds, error = ask(q["question"])
        if answer is None:
            failed.append(f"{q['id']} ({error})")
        else:
            record(answer)
            results[q["id"]] = {"ask": {"hits": [{"doc_id": p["doc_id"], "page": p["page"], "chunk_type": p.get("chunk_type"),
                                                  "score": p.get("score")} for p in answer["passages"]],
                                        "seconds": round(seconds, 3), "mode": answer["mode"]}}
        time.sleep(args.pace)
    if literature:
        run = {"label": args.label, "info": {"objects": "-", "through": "POST /api/ask"}, "split": args.split, "results": results}
        path = OUT_DIR / f"run_{args.label}_{args.split}.json"
        path.write_text(json.dumps(run), encoding="utf-8")
        answered = sum(1 for q in literature if q["id"] in results and
                       measures.answer_at(results[q["id"]]["ask"]["hits"], q["gold"]["sources"], 5))
        print(f"literature, split={args.split}: {len(results)} of {len(literature)} asked got an answer; "
              f"a page that answers in the first five: {answered} of {len(literature)} -> {path.name}")

    rows = []
    for q in catalogue:
        answer, seconds, error = ask(q["question"])
        if answer is None or answer["mode"]["catalogue"] == "unavailable":
            rows.append({"id": q["id"], "lang": q["lang"], "fact": q["fact"], "infrastructure_error": error or "catalogue unavailable"})
        else:
            record(answer)
            ids = [i["issue_id"] for i in answer["issues"]]
            gold_issue = q["issue_ids"][0]
            rank = ids.index(gold_issue) + 1 if gold_issue in ids else None
            card = answer["issues"][rank - 1]["card"] if rank else None
            rows.append({"id": q["id"], "lang": q["lang"], "fact": q["fact"], "rank": rank, "returned": ids,
                         "matched_by": answer["issues"][0]["matched_by"] if answer["issues"] else [],
                         "fact_found_top1": bool(rank == 1 and catalogue_arm.fact_in_card(q, card)),
                         "fact_found_top3": bool(rank and catalogue_arm.fact_in_card(q, card)),
                         "seconds": round(seconds, 3), "mode": answer["mode"]})
        time.sleep(args.pace)
    if catalogue:
        result = {"split": args.split, "k": 3, "mode": f"ask:{args.label}", "embedding": {}, "rows": rows}
        (OUT_DIR / f"catalogue_{args.split}_ask_{args.label}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(catalogue_arm.table(result))

    print("\nmodes:", {k: v for k, v in modes.most_common()})
    for name in ("total_ms", "embedding_ms", "catalogue_ms", "literature_ms"):
        if blocks[name]:
            s = measures.latency_summary(blocks[name])
            print(f"  {name[:-3]:<11} median {s['p50']:.2f} s, 95th percentile {s['p95']:.2f} s (n={s['n']}), as the backend timed it")
    if failed:
        print("no answer for:", failed)


if __name__ == "__main__":
    main()
