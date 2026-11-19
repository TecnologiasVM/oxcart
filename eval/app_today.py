"""The app as it is today, as an arm of the eval: POST /api/query, nothing changed.

    python -m eval.app_today --split dev        # the catalogue questions through the running app

The app answers every question about one issue (config.ISSUE_ID). This arm is the "before"
row of every table. OXCART_API names the backend (default http://127.0.0.1:8090).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from eval import split, stores

API = os.environ.get("OXCART_API", "http://127.0.0.1:8090")
QUESTIONS = stores.data_file("questions_catalogue.jsonl")


def ask(question: str, timeout: float = 180.0) -> dict:
    request = urllib.request.Request(
        API.rstrip("/") + "/api/query", data=json.dumps({"question": question}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def passages(response: dict) -> list[dict]:
    """What the app shows, in its order: the graph's passages first, then the keyword tail."""
    out = []
    for source, items in (("graph", response.get("lexical") or []), ("weaviate", response.get("weaviate") or [])):
        for item in items:
            out.append({"doc_id": item.get("doc_id"), "page": item.get("page"), "chunk_id": item.get("chunk_id"),
                        "score": item.get("score"), "via": source})
    return out


def _norm(value) -> str:
    return " ".join(str(value).lower().split())


def catalogue_check(question: dict, response: dict) -> dict:
    """Is the app's domain card about the gold issue, and does it hold the gold value?
    The value check is lenient (the value appears anywhere in the card); it can only pass
    for the one issue the app knows."""
    domain = response.get("domain") or {}
    right_issue = bool(domain.get("found")) and domain.get("issue_id") == question["issue_ids"][0]
    card_text = _norm(json.dumps(domain, ensure_ascii=False, default=str))
    value_there = right_issue and all(_norm(v) in card_text for v in question["gold"]["value"])
    return {"issue_right": right_issue, "fact_found": bool(value_there), "graph_error": domain.get("error")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    args = ap.parse_args()
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    sides = split.assign(questions)
    rows = []
    for q in questions:
        if args.split != "all" and sides[q["id"]] != args.split:
            continue
        t0 = time.time()
        try:
            row = catalogue_check(q, ask(q["question"]))
        except (urllib.error.URLError, TimeoutError) as exc:
            row = {"issue_right": False, "fact_found": False, "http_error": type(exc).__name__}
        row.update(id=q["id"], lang=q["lang"], fact=q["fact"], seconds=round(time.time() - t0, 2))
        rows.append(row)
    out = stores.REPO / "local-data" / "eval" / "results" / f"app_today_catalogue_{args.split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"split": args.split, "api": "local", "rows": rows}, indent=1), encoding="utf-8")
    n = len(rows)
    scored = [r for r in rows if not r.get("http_error") and not r.get("graph_error")]
    seconds = sorted(r["seconds"] for r in rows)
    print(f"app today, catalogue questions, split={args.split}: {n} asked, {len(scored)} answered with the graph half")
    print(f"  right issue: {sum(r['issue_right'] for r in scored)} of {len(scored)}; "
          f"fact found: {sum(r['fact_found'] for r in scored)} of {len(scored)}")
    print(f"  not scored: {n - len(scored)} (graph error or no answer); "
          f"seconds per question: median {seconds[n // 2]:.1f}, max {seconds[-1]:.1f}")
    for r in scored:
        if r["issue_right"]:
            print("   ", r["id"], "fact found" if r["fact_found"] else "issue right, value not in the card")


if __name__ == "__main__":
    main()
