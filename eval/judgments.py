"""Turn the reviewer's downloaded judgments into the literature part of the test set.

    python -m eval.judgments literature_judgments.json [more.json ...]

Reads the file(s) the review sheet downloads and writes local-data/eval/questions_literature.jsonl:
one question per line with its gold sources (document, pages, grade), the reviewer's short
answer, and who judged it. A question enters the test set only when at least one page was
graded 2 (it answers the question); the others are listed and left out. With several files the judgments are merged page by page.
"""

from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

from eval import stores

OUT = stores.REPO / "local-data" / "eval" / "questions_literature.jsonl"


def gold_sources(pages: list[dict], extra: str = "") -> list[dict]:
    """Group graded pages by document and grade: [{"doc_id", "pages": [...], "grade"}]."""
    by: dict[tuple, set] = collections.defaultdict(set)
    for p in pages:
        if p.get("grade", 0) > 0 and p.get("doc_id") and p.get("page") is not None:
            by[(p["doc_id"], int(p["grade"]))].add(int(p["page"]))
    for line in (extra or "").splitlines():   # "document, page" typed by the reviewer: taken as grade 2
        m = re.match(r"^\s*(.+?)\s*[,;]\s*(?:p(?:age|ág|ag)?\.?\s*)?(\d+)\s*$", line, re.IGNORECASE)
        if m:
            by[(m.group(1), 2)].add(int(m.group(2)))
    return [{"doc_id": doc, "pages": sorted(pages_), "grade": grade}
            for (doc, grade), pages_ in sorted(by.items(), key=lambda kv: (-kv[0][1], kv[0][0]))]


def convert(files: list[Path]) -> tuple[list[dict], list[str]]:
    """Merge the files question by question and PAGE BY PAGE: a later file adds pages to a
    question (or regrades a page) without discarding what an earlier file judged."""
    latest: dict[str, dict] = {}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        reviewer = data.get("reviewer") or "unnamed"
        for q in data["questions"]:
            if q.get("status") not in ("keep", "drop"):
                continue
            prior = latest.get(q["id"])
            pages = {(p["doc_id"], p["page"]): p for p in (prior or {}).get("pages", [])}
            pages.update({(p["doc_id"], p["page"]): p for p in q.get("pages") or []})
            merged = dict(prior or {}, **q)
            merged["pages"] = list(pages.values())
            if prior:
                if q.get("pages_only"):   # a top-up of extra pages: the wording and the answer stay as they were
                    merged["question"], merged["answer"] = prior["question"], prior.get("answer", "")
                    merged.pop("pages_only", None)
                else:
                    merged["answer"] = q.get("answer") or prior.get("answer", "")
                merged["status"] = "keep" if "keep" in (prior["status"], q["status"]) else "drop"
                reviewers = prior["reviewer"].split(" + ")
                merged["reviewer"] = " + ".join(reviewers + ([reviewer] if reviewer not in reviewers else []))
            else:
                merged["reviewer"] = reviewer
            merged["reviewed"] = (data.get("exported") or "")[:10]
            latest[q["id"]] = merged
    questions, notes = [], []
    for qid in sorted(latest):
        q = latest[qid]
        if q["status"] == "drop":
            notes.append(f"{qid}: dropped by {q['reviewer']}")
            continue
        sources = gold_sources(q.get("pages") or [], q.get("extra_pages") or "")
        if not any(s["grade"] >= 2 for s in sources):
            notes.append(f"{qid}: no page graded 2 (no page answers it): left out")
            continue
        questions.append({
            "id": qid, "pair": q.get("pair"), "lang": q["lang"], "type": "literature", "question": q["question"].strip(),
            "gold": {"sources": sources, "answer": (q.get("answer") or "").strip()},
            "judged_by": q["reviewer"], "reviewed": q["reviewed"],
            "pages_judged": len(q.get("pages") or []),
        })
    return questions, notes


def main() -> None:
    files = [Path(a) for a in sys.argv[1:]]
    if not files:
        raise SystemExit("usage: python -m eval.judgments literature_judgments.json [...]")
    questions, notes = convert(files)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions), encoding="utf-8")
    by_judge = collections.Counter(q["judged_by"] for q in questions)
    by_lang = collections.Counter(q["lang"] for q in questions)
    print(f"{len(questions)} literature questions -> {OUT.relative_to(stores.REPO)}")
    print("judged by:", dict(by_judge), "| languages:", dict(by_lang),
          "| with a written answer:", sum(1 for q in questions if q["gold"]["answer"]))
    for n in notes:
        print(" ", n)


if __name__ == "__main__":
    main()
