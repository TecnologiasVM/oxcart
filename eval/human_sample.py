"""A person checks a sample of the model judge's page grades, blind.

    python -m eval.human_sample build --dirs local-data/eval/judge/literature local-data/eval/judge/extra1 ... \
        --out local-data/eval/review/human_sample.html --key local-data/eval/human_sample_key.json
    ... the reviewer opens the page, grades every item, downloads human_sample_answers.json ...
    python -m eval.human_sample score --key local-data/eval/human_sample_key.json --answers human_sample_answers.json

`build` draws the same number of pages for each grade the model gave (15 by default, fixed
seed), shuffles them, and writes one self-contained page showing, for each item, the question
and exactly the passages the model judge was shown. The model's grade and reason are NOT in
the page: they go to the key file, which stays with whoever scores the sample.

`score` reports how often the person and the model gave the same grade, how often they agree
on "answers the question or not" (grade 2 against the rest), Cohen's kappa for both, and the
table of grades against grades. The sample holds equal numbers of each grade, so the figures
are also given weighted back to the shares of each grade among all judged pages.

A shorter sheet for later: `build --grades 2 --per-grade 10 --yes-no --seed <another seed>` draws
pages the model said answer the question and asks one thing, yes or no. `score` then counts
how many the person confirms.

THE PAGE CONTAINS PASSAGES OF THE LITERATURE. It is written under local-data/ and must stay
private. The key file holds no text. This script holds no text.
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import random
import time
from pathlib import Path

from eval.agreement import kappa

SEED = 20261119
THRESHOLD = 0.85    # agreement on "answers or not" below this: stop and report

RUBRIC = [
    ("2", "the passages contain the specific answer to the question, or a clear, direct part of it"),
    ("1", "the passages are about what the question asks and support or narrow the answer, but do not state it"),
    ("0", "anything else: a different subject, or the question's words appear without helping to answer it "
          "(an index line, a list of titles, a price list, a header)"),
]

STYLE = """
body{font:17px/1.5 Georgia,serif;margin:0;background:#f6f4ef;color:#1d1b16}
header{position:sticky;top:0;background:#1d1b16;color:#f6f4ef;padding:10px 20px;display:flex;gap:16px;align-items:center;z-index:5}
header input{font:inherit;padding:4px 8px;width:14em}
header button{font:inherit;padding:6px 14px;cursor:pointer}
main{max-width:60em;margin:0 auto;padding:16px 20px 80px}
section{background:#fff;border:1px solid #d8d2c4;border-radius:6px;padding:16px 18px;margin:18px 0}
section.done{border-left:6px solid #4d7c4d}
h2{font-size:1em;margin:0 0 8px;color:#6b6456;font-family:Helvetica,Arial,sans-serif}
.question{font-size:1.1em;font-weight:bold;margin:4px 0 10px}
.where{color:#6b6456;font:.8em Helvetica,Arial,sans-serif}
.grade label{margin-right:18px;font:.95em Helvetica,Arial,sans-serif;cursor:pointer}
.text{white-space:pre-wrap;background:#faf8f3;border-left:3px solid #d8d2c4;padding:6px 10px;margin:8px 0;font-size:.92em}
.help{background:#fffbe6;border:1px solid #e9dc9c;border-radius:6px;padding:12px 16px}
"""

SCRIPT = r"""
const DATA = JSON.parse(document.getElementById('data').textContent);
const KEY = 'oxcart-human-sample-' + DATA.seed + (DATA.yes_no ? '-yes-no' : '');
let state = JSON.parse(localStorage.getItem(KEY) || '{"grades":{}}');
function save(){ localStorage.setItem(KEY, JSON.stringify(state)); progress(); }
function progress(){
  const done = DATA.items.filter(x => state.grades[x] !== undefined).length;
  document.getElementById('progress').textContent = done + ' of ' + DATA.items.length + ' graded';
  document.querySelectorAll('section[data-id]').forEach(sec =>
    sec.classList.toggle('done', state.grades[sec.dataset.id] !== undefined));
}
document.getElementById('reviewer').value = state.reviewer || '';
document.getElementById('reviewer').addEventListener('input', e => { state.reviewer = e.target.value; save(); });
document.querySelectorAll('section[data-id]').forEach(sec => {
  const id = sec.dataset.id;
  sec.querySelectorAll('input[type=radio]').forEach(r => {
    if (state.grades[id] === Number(r.value)) r.checked = true;
    r.addEventListener('change', () => { state.grades[id] = Number(r.value); save(); });
  });
});
document.getElementById('download').addEventListener('click', () => {
  const missing = DATA.items.filter(x => state.grades[x] === undefined).length;
  const note = document.getElementById('note');
  if (!state.reviewer) { note.textContent = 'Write your name first.'; return; }
  note.textContent = missing ? missing + ' items are not graded yet; the file holds the ones you did.' : 'All graded. File downloaded.';
  const out = {reviewer: state.reviewer, exported: new Date().toISOString(), seed: DATA.seed, grades: state.grades};
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: 'application/json'}));
  a.download = DATA.yes_no ? 'human_short_answers.json' : 'human_sample_answers.json';
  a.click();
});
progress();
"""


def judged_pages(dirs: list[Path]) -> list[dict]:
    """Every page the model judge graded, with the passages it was shown."""
    out, seen = [], set()
    for base in dirs:
        for inp in sorted((base / "inputs").glob("*.json")):
            ans = base / "outputs" / inp.name
            if not ans.exists():
                continue
            q = json.loads(inp.read_text(encoding="utf-8"))
            a = json.loads(ans.read_text(encoding="utf-8"))
            by_key = {p["key"]: p for p in a.get("pages", [])}
            for p in q["pages"]:
                page = (q["id"], p["doc_id"], p["page"])
                if p["key"] not in by_key or page in seen or not p["passages"]:
                    continue
                seen.add(page)
                out.append({"dir": base.name, "id": q["id"], "key": p["key"], "lang": q["lang"],
                            "question": q["question"], "doc_id": p["doc_id"], "page": p["page"],
                            "passages": p["passages"], "grade": int(by_key[p["key"]]["grade"]),
                            "reason": by_key[p["key"]].get("reason", "")})
    return out


def draw(pages: list[dict], per_grade: int, seed: int, grades: tuple = (0, 1, 2)) -> list[dict]:
    chosen = []
    for grade in grades:
        mine = sorted((p for p in pages if p["grade"] == grade), key=lambda p: (p["dir"], p["id"], p["key"]))
        if len(mine) < per_grade:
            raise SystemExit(f"only {len(mine)} pages with grade {grade}")
        chosen += random.Random(f"{seed}:{grade}").sample(mine, per_grade)
    random.Random(f"{seed}:order").shuffle(chosen)
    return chosen


def page_html(items: list[dict], seed: int, yes_no: bool = False) -> str:
    parts = []
    for n, item in enumerate(items, start=1):
        sid = f"s{n:02d}"
        texts = "".join(f'<div class="text">{html.escape(t)}</div>' for t in item["passages"])
        if yes_no:
            radios = (f'<label><input type="radio" name="{sid}" value="2"> Yes</label>'
                      f'<label><input type="radio" name="{sid}" value="0"> No</label>')
        else:
            radios = "".join(f'<label><input type="radio" name="{sid}" value="{g}"> {g}</label>' for g in (0, 1, 2))
        parts.append(
            f'<section data-id="{sid}"><h2>{n} of {len(items)}</h2>'
            f'<div class="question">{html.escape(item["question"])}</div>'
            f'<div class="where">{html.escape(str(item["doc_id"]))}, page {html.escape(str(item["page"]))}</div>'
            f'{texts}<div class="grade">{"Do these passages answer the question?" if yes_no else "Grade:"} {radios}</div></section>')
    rubric = "".join(f"<li><b>{g}</b>: {html.escape(text)}</li>" for g, text in RUBRIC)
    data = json.dumps({"seed": seed, "yes_no": yes_no, "items": [f"s{n:02d}" for n in range(1, len(items) + 1)]}).replace("</", "<\\/")
    if yes_no:
        guide = ("<p><b>Yes</b>: the passages contain the specific answer to the question, or a clear, direct part of it. "
                 "<b>No</b>: anything else, including passages about the same subject that do not answer <i>this</i> "
                 "question. Your marks are kept in this browser; when you finish, press <b>Download my grades</b> and "
                 "send the file.</p>")
    else:
        guide = (f"<ul>{rubric}</ul><p>Be strict with 2: a passage about the same issue or stamp that does not answer "
                 "<i>this</i> question is a 1 at most. Your marks are kept in this browser; when you finish, press "
                 "<b>Download my grades</b> and send the file.</p>")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Oxcart: page grades, human sample</title>'
        f"<style>{STYLE}</style></head><body>"
        '<header><span>Your name <input id="reviewer"></span><span id="progress"></span>'
        '<button id="download">Download my grades</button><span id="note"></span></header><main>'
        '<div class="help"><p>Each item is one question and the passages a search returned from one page. '
        "Grade the page <b>only from the passages shown</b>: do not use what you know about the subject and do not "
        "guess what the rest of the page says. The language of the question and of the passages does not matter.</p>"
        f"{guide}</div>"
        f'{"".join(parts)}</main><script type="application/json" id="data">{data}</script>'
        f"<script>{SCRIPT}</script></body></html>")


def build(args) -> None:
    out, key_path = Path(args.out), Path(args.key)
    if "local-data" not in out.resolve().parts:
        raise SystemExit("the page contains literature text: write it under local-data/")
    pages = judged_pages([Path(d) for d in args.dirs])
    items = draw(pages, args.per_grade, args.seed, tuple(args.grades))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html(items, args.seed, args.yes_no), encoding="utf-8")
    population = collections.Counter(p["grade"] for p in pages)
    key = {"seed": args.seed, "per_grade": args.per_grade, "grades": list(args.grades), "yes_no": args.yes_no, "built": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "judged_pages": len(pages), "population": {str(g): population[g] for g in (0, 1, 2)},
           "items": {f"s{n:02d}": {k: item[k] for k in ("dir", "id", "key", "lang", "doc_id", "page", "grade", "reason")}
                     for n, item in enumerate(items, start=1)}}
    key_path.write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(items)} items ({args.per_grade} per grade, grades {list(args.grades)}) drawn from {len(pages)} judged pages "
          f"(grades {dict(sorted(population.items()))}), over {len({i['id'] for i in items})} questions; seed {args.seed}")
    print(f"page -> {out} ({out.stat().st_size / 1e3:.0f} kB); key -> {key_path}")


def compare(key: dict, answers: dict) -> dict:
    pairs = [(int(answers["grades"][sid]), item["grade"]) for sid, item in key["items"].items()
             if sid in answers.get("grades", {})]       # (person, model)
    n = len(pairs)
    table = collections.Counter(pairs)
    population = {int(g): c for g, c in key["population"].items()}
    total = sum(population.values())

    def weighted(same) -> float:
        """Agreement weighted back to the grade shares among all judged pages."""
        value = 0.0
        for grade, count in population.items():
            mine = [(h, m) for h, m in pairs if m == grade]
            if mine:
                value += (count / total) * sum(1 for h, m in mine if same(h, m)) / len(mine)
        return value

    same_grade = lambda h, m: h == m                      # noqa: E731
    same_answers = lambda h, m: (h == 2) == (m == 2)      # noqa: E731
    return {
        "items_graded": n, "items_in_sample": len(key["items"]),
        "same_grade": sum(1 for h, m in pairs if same_grade(h, m)) / n if n else None,
        "same_grade_kappa": kappa(pairs),
        "same_answers_or_not": sum(1 for h, m in pairs if same_answers(h, m)) / n if n else None,
        "same_answers_or_not_kappa": kappa([(h == 2, m == 2) for h, m in pairs]),
        "same_grade_weighted": weighted(same_grade), "same_answers_or_not_weighted": weighted(same_answers),
        "model_said_2_person_did_not": sum(c for (h, m), c in table.items() if m == 2 and h != 2),
        "person_said_2_model_did_not": sum(c for (h, m), c in table.items() if h == 2 and m != 2),
        "table_person_by_model": {f"person {h}, model {m}": table[(h, m)] for h in (0, 1, 2) for m in (0, 1, 2)},
    }


def score(args) -> None:
    key = json.loads(Path(args.key).read_text(encoding="utf-8"))
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    if answers.get("seed") != key["seed"]:
        raise SystemExit("the answers file belongs to another sample (different seed)")
    result = compare(key, answers)
    print(f"reviewer: {answers.get('reviewer')}; graded {result['items_graded']} of {result['items_in_sample']}")
    if key.get("yes_no"):
        yes = sum(1 for sid, item in key["items"].items() if answers["grades"].get(sid) == 2 and item["grade"] == 2)
        asked = sum(1 for item in key["items"].values() if item["grade"] == 2)
        print(f"pages the model said answer the question, confirmed by the person: {yes} of {asked}")
        if args.out:
            Path(args.out).write_text(json.dumps({"reviewer": answers.get("reviewer"), "confirmed": yes, "asked": asked}, indent=1),
                                      encoding="utf-8")
        return
    print(f"same grade:           {result['same_grade']:.0%} (kappa {result['same_grade_kappa']:.2f}); "
          f"weighted to all judged pages {result['same_grade_weighted']:.0%}")
    print(f"same 'answers or not': {result['same_answers_or_not']:.0%} (kappa {result['same_answers_or_not_kappa']:.2f}); "
          f"weighted {result['same_answers_or_not_weighted']:.0%}")
    print(f"model said 'answers', the person did not: {result['model_said_2_person_did_not']}; "
          f"the person said 'answers', the model did not: {result['person_said_2_model_did_not']}")
    for name, count in result["table_person_by_model"].items():
        print(f"  {name}: {count}")
    if result["items_graded"] < result["items_in_sample"]:
        print("NOT COMPLETE: some items are not graded")
    if result["same_answers_or_not"] is not None and result["same_answers_or_not"] < THRESHOLD:
        print(f"STOP: agreement on 'answers or not' is under {THRESHOLD:.0%}. Report before using the gold.")
    if args.out:
        Path(args.out).write_text(json.dumps({"reviewer": answers.get("reviewer"), **result}, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dirs", required=True, nargs="+")
    b.add_argument("--out", required=True)
    b.add_argument("--key", required=True)
    b.add_argument("--per-grade", type=int, default=15)
    b.add_argument("--seed", type=int, default=SEED)
    b.add_argument("--grades", type=int, nargs="+", default=[0, 1, 2], help="draw from pages the model gave these grades")
    b.add_argument("--yes-no", action="store_true", help="ask one thing per page: does it answer the question?")
    b.set_defaults(fn=build)
    s = sub.add_parser("score")
    s.add_argument("--key", required=True)
    s.add_argument("--answers", required=True)
    s.add_argument("--out")
    s.set_defaults(fn=score)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
