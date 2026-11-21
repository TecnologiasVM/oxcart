"""Ask the test set through POST /api/chat and report on the written answers.

    OXCART_API=https://<backend> OXCART_EVAL_KEY=<secret> python -m eval.chat_arm run --label <name> [--pace 0.5]
    python -m eval.chat_arm table --label <name> [--grades <judge dir>/grades.json] [--asked <dir>/asked.json] [--publish]

`run` asks every question once (catalogue, literature, out of scope) and the follow-up
threads, and keeps what came back under local-data/eval/chat/<label>/:

    answers.jsonl    one line per question: the evidence line and the answer line as received.
                     THIS FILE HOLDS TEXT OF THE LITERATURE (passages, and answers written from them).

It also writes the two files eval/ask_arm.py writes, from the evidence of the chat route,
so the retrieval counts of the two routes can be compared with the same scorer.

`table` prints, from that file and the judge's grades when they are given:

- retrieval through this route (it must equal the question path's);
- how each question ended (answered, not covered, or the reason nothing was written), by
  part and by language;
- the share of the answers' sentences that carried no citation;
- when grades are given: supported and correct, by part and language, literature over
  both denominators;
- the follow-up threads: is the issue of the first question among the issues returned
  for the follow-up, with the conversation and with the follow-up asked alone;
- tokens and cost per question (mean and maximum), and the waits.

`--publish` writes eval/outcomes/answers_<label>.json: ids, states, counts, token counts
and grades. No question's answer and no passage.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

from eval import ask_arm, catalogue_arm, measures, stores

API = os.environ.get("OXCART_API", "http://127.0.0.1:8090").rstrip("/")
OUT = stores.REPO / "local-data" / "eval" / "chat"
OUTCOMES = stores.REPO / "eval" / "outcomes"

# claude-haiku-5-5, prompts up to 100,000 tokens, USD per million tokens (Anthropic's price list, 2026-11-20)
USD_PER_MTOK_IN, USD_PER_MTOK_OUT = 0.10, 0.50
DRAFTS_LEFT_OUT = 8          # literature drafts with no page that answers them: counted as misses in the second denominator


def cost(calls: list) -> float:
    return sum(c["input_tokens"] * USD_PER_MTOK_IN + c["output_tokens"] * USD_PER_MTOK_OUT for c in calls) / 1e6


def chat(question: str, thread: list | None = None, timeout: float = 120.0, attempts: int = 6) -> dict:
    """{"evidence": .., "rewritten": .., "answer": .., "calls": .., "first_seconds": .., "seconds": ..} or {"error": ..}."""
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OXCART_EVAL_KEY"):
        headers["X-Oxcart-Eval"] = os.environ["OXCART_EVAL_KEY"]
    body = json.dumps({"question": question, "thread": thread or []}).encode("utf-8")
    error = None
    for _ in range(attempts):
        request = urllib.request.Request(API + "/api/chat", data=body, headers=headers)
        t0, first, lines = time.time(), None, []
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                for raw in response:
                    if first is None:
                        first = time.time() - t0
                    lines.append(json.loads(raw))
            by_type = {line["type"]: line for line in lines}
            return {"evidence": by_type["evidence"]["evidence"], "rewritten": by_type["evidence"]["rewritten"],
                    "answer": by_type["answer"]["answer"], "calls": by_type["answer"].get("calls", []),
                    "first_seconds": round(first or 0.0, 3), "seconds": round(time.time() - t0, 3)}
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}"
            if exc.code == 429:
                time.sleep(min(int(exc.headers.get("Retry-After") or 5), 65))
            elif exc.code in (502, 503, 504):
                time.sleep(3)
            else:
                break
        except Exception as exc:
            error = type(exc).__name__
            time.sleep(3)
    return {"error": error}


def text_of(answer: dict) -> str:
    return " ".join(sentence["text"] for sentence in answer.get("sentences", []))


# --------------------------------------------------------------------------- run
def run(args) -> None:
    folder = OUT / args.label
    folder.mkdir(parents=True, exist_ok=True)
    parts = {"catalogue": ask_arm.load("questions_catalogue.jsonl"), "literature": ask_arm.load("questions_literature.jsonl"),
             "out_of_scope": ask_arm.load("questions_out_of_scope.jsonl")}
    by_id = {q["id"]: q for rows in parts.values() for q in rows}
    threads = ask_arm.load("threads.jsonl")
    wanted = [args.only] if args.only else ["catalogue", "literature", "out_of_scope", "threads"]
    path = folder / "answers.jsonl"
    done = {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() and args.resume else set()
    with path.open("a" if args.resume else "w", encoding="utf-8") as out:
        def keep(row: dict) -> None:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()

        for part in ("catalogue", "literature", "out_of_scope"):
            if part not in wanted:
                continue
            for q in parts[part]:
                if q["id"] in done:
                    continue
                keep({"id": q["id"], "part": part, "lang": q["lang"], **chat(q["question"])})
                time.sleep(args.pace)
            print(f"{part}: {len(parts[part])} asked")
        if "threads" in wanted:
            for t in threads:
                if t["id"] in done:
                    continue
                first = by_id[t["first"]]
                opening = chat(first["question"])
                turn = [{"question": first["question"], "answer": text_of(opening.get("answer", {}))[:1200]}]
                followed = chat(t["follow_up"], turn)
                alone, _, error = ask_arm.ask(t["follow_up"])
                keep({"id": t["id"], "part": "threads", "lang": t["lang"], "gold_issue": first["issue_ids"][0],
                      "opening_state": opening.get("answer", {}).get("state", opening.get("error")),
                      "alone_issues": [i["issue_id"] for i in (alone or {}).get("issues", [])], **followed})
                time.sleep(args.pace)
            print(f"threads: {len(threads)} asked")
    print(f"-> {path}")


# --------------------------------------------------------------------------- table
def _load(label: str) -> list:
    path = OUT / label / "answers.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _retrieval(label: str, rows: list) -> None:
    """The question path's own scoring, on the evidence this route returned."""
    by_id = {r["id"]: r for r in rows if "evidence" in r}
    literature = ask_arm.load("questions_literature.jsonl")
    answered = sum(1 for q in literature if q["id"] in by_id and measures.answer_at(
        [{"doc_id": p["doc_id"], "page": p["page"]} for p in by_id[q["id"]]["evidence"]["passages"]], q["gold"]["sources"], 5))
    asked = sum(1 for q in literature if q["id"] in by_id)
    print(f"literature: a page that answers in the first five: {answered} of {len(literature)} "
          f"({answered} of {len(literature) + DRAFTS_LEFT_OUT} drafts); asked {asked}")
    first = three = n = 0
    for q in ask_arm.load("questions_catalogue.jsonl"):
        if q["id"] not in by_id:
            continue
        n += 1
        issues = by_id[q["id"]]["evidence"]["issues"]
        ids = [i["issue_id"] for i in issues]
        rank = ids.index(q["issue_ids"][0]) + 1 if q["issue_ids"][0] in ids else None
        found = bool(rank and catalogue_arm.fact_in_card(q, issues[rank - 1]["card"]))
        first += bool(rank == 1 and found)
        three += found
    print(f"catalogue: the issue first with the fact in its card: {first} of {n}; in the first three: {three} of {n}")


def _share(count: int, of: int) -> str:
    return f"{count} of {of}" + (f" ({100 * count / of:.0f}%)" if of else "")


def table(args) -> None:
    rows = _load(args.label)
    grades = {}
    if args.grades:
        grades = {g["id"]: g for g in json.loads(Path(args.grades).read_text(encoding="utf-8"))["answers"]}
    asked = {}
    if getattr(args, "asked", None):
        asked = {g["id"]: g["asked"] for g in json.loads(Path(args.asked).read_text(encoding="utf-8"))["answers"]}
    single = [r for r in rows if r["part"] != "threads"]
    print(f"# Written answers, run '{args.label}': {len(single)} questions, {sum(1 for r in rows if r['part'] == 'threads')} threads\n")
    print("## Retrieval through this route\n")
    _retrieval(args.label, single)

    print("\n## How each question ended\n")
    for part in ("catalogue", "literature", "out_of_scope"):
        for lang in ("all", "en", "es"):
            mine = [r for r in single if r["part"] == part and lang in ("all", r["lang"])]
            states = collections.Counter(r.get("answer", {}).get("state", f"no reply ({r.get('error')})") for r in mine)
            print(f"{part:<12} {lang:<3} n={len(mine):<3} " + ", ".join(f"{s} {c}" for s, c in states.most_common()))

    print("\n## Sentences with no citation (before the rule removes them)\n")
    for part in ("catalogue", "literature"):
        for lang in ("all", "en", "es"):
            counts = [r["answer"]["counts"] for r in single if r["part"] == part and lang in ("all", r["lang"])
                      and r.get("answer", {}).get("counts")]
            total = sum(c["sentences"] for c in counts)
            print(f"{part:<12} {lang:<3} {_share(sum(c['sentences_without_citation'] for c in counts), total)} sentences; "
                  f"answers that lost at least one: {_share(sum(1 for c in counts if c['sentences_without_citation']), len(counts))}; "
                  f"citations that did not hold: {sum(c['citations_that_do_not_hold'] for c in counts)} of {sum(c['citations'] for c in counts)}")

    if grades:
        print("\n## Grades by the judge (a model; no person has checked them)\n")
        print("supported = every shown sentence is stated by the sources it cites. correct = the answer gives the gold value")
        print("(catalogue) or agrees with the reference answer (literature). Both are counted over ALL questions of the part:")
        print("a question with no written answer is neither.\n")
        for part in ("catalogue", "literature"):
            for lang in ("all", "en", "es"):
                mine = [r for r in single if r["part"] == part and lang in ("all", r["lang"])]
                written = [r for r in mine if r.get("answer", {}).get("state") == "ok"]
                judged = [grades[r["id"]] for r in written if r["id"] in grades]
                supported = sum(1 for g in judged if all(s["supported"] == "yes" for s in g["sentences"]))
                correct = sum(1 for g in judged if g["correct"] == "yes")
                partly = sum(1 for g in judged if g["correct"] == "partly")
                both = sum(1 for g in judged if g["correct"] == "yes" and all(s["supported"] == "yes" for s in g["sentences"]))
                other = sum(1 for g in judged if g["language"] != "same")
                extra = ""
                if part == "literature" and lang == "all":
                    extra = f" | of all {len(mine) + DRAFTS_LEFT_OUT} drafts: correct {correct}, supported and correct {both}"
                print(f"{part:<12} {lang:<3} n={len(mine):<3} written {len(written)}, judged {len(judged)}: "
                      f"supported {_share(supported, len(mine))}; correct {_share(correct, len(mine))} (partly {partly}); "
                      f"supported and correct {_share(both, len(mine))}; in another language {other}{extra}")
        sentences = [s for g in grades.values() for s in g["sentences"]]
        marks = collections.Counter(s["supported"] for s in sentences)
        print(f"\nshown sentences: {len(sentences)}; supported yes {marks['yes']}, partly {marks['partly']}, no {marks['no']}")
        scope = [r for r in single if r["part"] == "out_of_scope"]
        written = [r for r in scope if r.get("answer", {}).get("state") == "ok"]
        print(f"out of scope: {len(scope) - len(written)} of {len(scope)} got no written answer; {len(written)} got one")

    if asked:
        print("\n## Gives what the question asks (the judge's second pass; a model; no person has checked it)\n")
        print("yes = the answer states the thing asked and it agrees with the reference; detail the question did not ask")
        print("for does not count. Counted over ALL questions of the part: a question with no written answer is a no.\n")
        for part in ("catalogue", "literature"):
            for lang in ("all", "en", "es"):
                mine = [r for r in single if r["part"] == part and lang in ("all", r["lang"])]
                marks = collections.Counter(asked[r["id"]] for r in mine if r["id"] in asked)
                extra = f" | of all {len(mine) + DRAFTS_LEFT_OUT} drafts: yes {marks['yes']}" if part == "literature" and lang == "all" else ""
                print(f"{part:<12} {lang:<3} n={len(mine):<3} judged {sum(marks.values())}: yes {_share(marks['yes'], len(mine))}; "
                      f"partly {marks['partly']}; no {marks['no']}; not written {len(mine) - sum(marks.values())}{extra}")

    threads = [r for r in rows if r["part"] == "threads"]
    if threads:
        print("\n## Follow-ups: is the first question's issue among the issues returned for the follow-up\n")
        def rank(ids, gold):
            return ids.index(gold) + 1 if gold in ids else None
        with_thread = [rank([i["issue_id"] for i in r.get("evidence", {}).get("issues", [])], r["gold_issue"]) for r in threads]
        alone = [rank(r.get("alone_issues", []), r["gold_issue"]) for r in threads]
        n = len(threads)
        print(f"with the conversation: first {sum(1 for x in with_thread if x == 1)} of {n}, in the first three {sum(1 for x in with_thread if x)} of {n}"
              f" (rewritten: {sum(1 for r in threads if r.get('rewritten'))} of {n})")
        print(f"the follow-up alone:   first {sum(1 for x in alone if x == 1)} of {n}, in the first three {sum(1 for x in alone if x)} of {n}")

    print("\n## Tokens, cost and waits\n")
    for name, mine in (("a first question", single), ("a follow-up (rewrite and answer)", threads)):
        costs = [cost(r.get("calls", [])) for r in mine if r.get("calls")]
        if not costs:
            continue
        tokens_in = [sum(c["input_tokens"] for c in r["calls"]) for r in mine if r.get("calls")]
        tokens_out = [sum(c["output_tokens"] for c in r["calls"]) for r in mine if r.get("calls")]
        print(f"{name}: n={len(costs)}; input tokens mean {statistics.mean(tokens_in):.0f}, max {max(tokens_in)}; "
              f"output tokens mean {statistics.mean(tokens_out):.0f}, max {max(tokens_out)}; "
              f"cost mean {statistics.mean(costs):.5f} USD, max {max(costs):.5f} USD; total {sum(costs):.3f} USD")
    for name, key in (("evidence", "first_seconds"), ("answer", "seconds")):
        waits = [r[key] for r in single if key in r]
        if waits:
            s = measures.latency_summary(waits)
            print(f"wait for the {name}: median {s['p50']:.2f} s, 95th percentile {s['p95']:.2f} s (n={s['n']})")

    if args.publish:
        OUTCOMES.mkdir(parents=True, exist_ok=True)
        public = []
        for r in rows:
            g = grades.get(r["id"])
            public.append({"id": r["id"], "part": r["part"], "lang": r["lang"],
                           "state": r.get("answer", {}).get("state"), "counts": r.get("answer", {}).get("counts"),
                           "rewritten": r.get("rewritten"),
                           "calls": [{k: c[k] for k in ("purpose", "state", "input_tokens", "output_tokens")} for c in r.get("calls", [])],
                           **({"supported": [s["supported"] for s in g["sentences"]], "correct": g["correct"],
                               "language": g["language"]} if g else {}),
                           **({"asked": asked[r["id"]]} if r["id"] in asked else {}),
                           **({"gold_issue_rank_with_thread": ([i["issue_id"] for i in r.get("evidence", {}).get("issues", [])].index(r["gold_issue"]) + 1
                                                                if r["gold_issue"] in [i["issue_id"] for i in r.get("evidence", {}).get("issues", [])] else None),
                               "gold_issue_rank_alone": (r["alone_issues"].index(r["gold_issue"]) + 1 if r["gold_issue"] in r.get("alone_issues", []) else None)}
                              if r["part"] == "threads" else {})})
        path = OUTCOMES / f"answers_{args.label}.json"
        path.write_text(json.dumps({"label": args.label, "model": "claude-haiku-5-5", "judge": args.judge,
                                    "usd_per_mtok": {"input": USD_PER_MTOK_IN, "output": USD_PER_MTOK_OUT},
                                    "rows": public}, indent=1), encoding="utf-8")
        print(f"\n-> {path.relative_to(stores.REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--pace", type=float, default=0.0, help="seconds to wait between questions")
    r.add_argument("--only", choices=["catalogue", "literature", "out_of_scope", "threads"])
    r.add_argument("--resume", action="store_true", help="keep the answers already in the file and ask the rest")
    r.set_defaults(fn=run)
    t = sub.add_parser("table")
    t.add_argument("--label", required=True)
    t.add_argument("--grades")
    t.add_argument("--asked", help="asked.json of the judge's second pass (eval.answer_judge collect-asked)")
    t.add_argument("--judge", default="", help="the judge's name, for the published file")
    t.add_argument("--publish", action="store_true")
    t.set_defaults(fn=table)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
