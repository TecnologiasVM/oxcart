"""Build the page-judging sheet for the literature questions: one self-contained HTML file.

    python -m eval.review_sheet --drafts drafts.jsonl --pools pool_full.json pool_collapsed.json \
        --export local-data/stage2/export --out local-data/eval/review/literature_review.html

The reviewer opens the file in a browser, edits or drops each draft question, marks each
pooled page (0 = does not help, 1 = supports the answer, 2 = answers the question), writes
the expected answer in their own words, and downloads a JSON file with the judgments.

THE OUTPUT CONTAINS PASSAGES OF THE LITERATURE. It is written under local-data/ and must
stay private: never commit it, never attach it to a public place. This script itself holds
no text.
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import time
from pathlib import Path

PAGE_STYLE = """
body{font:17px/1.5 Georgia,serif;margin:0;background:#f6f4ef;color:#1d1b16}
header{position:sticky;top:0;background:#1d1b16;color:#f6f4ef;padding:10px 20px;display:flex;gap:16px;align-items:center;z-index:5}
header input{font:inherit;padding:4px 8px;width:14em}
header button{font:inherit;padding:6px 14px;cursor:pointer}
main{max-width:60em;margin:0 auto;padding:16px 20px 80px}
section{background:#fff;border:1px solid #d8d2c4;border-radius:6px;padding:16px 18px;margin:18px 0}
section.drop{opacity:.45}
h2{font-size:1em;margin:0 0 8px;color:#6b6456}
textarea,input.q{font:inherit;width:100%;box-sizing:border-box;padding:6px 8px}
.row{display:flex;gap:18px;align-items:center;margin:8px 0;flex-wrap:wrap}
.page{border-top:1px solid #e6e1d5;padding:10px 0}
.page b{font-family:Helvetica,Arial,sans-serif;font-size:.85em}
.arms{color:#6b6456;font:.8em Helvetica,Arial,sans-serif}
.grade label{margin-right:14px;font:.9em Helvetica,Arial,sans-serif;cursor:pointer}
.text{white-space:pre-wrap;background:#faf8f3;border-left:3px solid #d8d2c4;padding:6px 10px;margin:6px 0;font-size:.92em}
details summary{cursor:pointer;color:#6b6456;font:.85em Helvetica,Arial,sans-serif}
.help{background:#fffbe6;border:1px solid #e9dc9c;border-radius:6px;padding:12px 16px}
"""

SCRIPT = r"""
const DATA = JSON.parse(document.getElementById('data').textContent);
const KEY = 'oxcart-literature-review-v1';
let state = JSON.parse(localStorage.getItem(KEY) || '{}');
function save(){ localStorage.setItem(KEY, JSON.stringify(state)); progress(); }
function q(id){ return state[id] = state[id] || {status:'not reviewed', pages:{}}; }
function progress(){
  const done = DATA.questions.filter(x => (state[x.id]||{}).status && state[x.id].status !== 'not reviewed').length;
  document.getElementById('progress').textContent = done + ' of ' + DATA.questions.length + ' questions reviewed';
}
function bind(){
  document.getElementById('reviewer').value = state.__reviewer || '';
  document.getElementById('reviewer').addEventListener('input', e => { state.__reviewer = e.target.value; save(); });
  document.querySelectorAll('section[data-id]').forEach(sec => {
    const id = sec.dataset.id, s = q(id);
    const qi = sec.querySelector('input.q'), st = sec.querySelector('select'), an = sec.querySelector('textarea.answer'),
          ex = sec.querySelector('textarea.extra');
    if (s.question) qi.value = s.question;
    st.value = s.status; an.value = s.answer || ''; ex.value = s.extra || '';
    sec.classList.toggle('drop', s.status === 'drop');
    qi.addEventListener('input', () => { s.question = qi.value; save(); });
    st.addEventListener('change', () => { s.status = st.value; sec.classList.toggle('drop', s.status === 'drop'); save(); });
    an.addEventListener('input', () => { s.answer = an.value; save(); });
    ex.addEventListener('input', () => { s.extra = ex.value; save(); });
    sec.querySelectorAll('.page').forEach(p => {
      const key = p.dataset.key;
      p.querySelectorAll('input[type=radio]').forEach(r => {
        if (String(s.pages[key] ?? 0) === r.value) r.checked = true;
        r.addEventListener('change', () => { s.pages[key] = Number(r.value); if (s.status === 'not reviewed') { s.status = 'keep'; st.value = 'keep'; } save(); });
      });
    });
  });
  document.getElementById('download').addEventListener('click', () => {
    const out = {reviewer: state.__reviewer || '', exported: new Date().toISOString(), sheet: DATA.built, questions: []};
    DATA.questions.forEach(x => {
      const s = q(x.id);
      out.questions.push({id: x.id, pair: x.pair, lang: x.lang, status: s.status, question: s.question || x.question,
        draft_question: x.question, answer: s.answer || '', extra_pages: s.extra || '',
        pages: x.pages.map(p => ({doc_id: p.doc_id, page: p.page, grade: s.pages[p.key] ?? 0}))});
    });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: 'application/json'}));
    a.download = 'literature_judgments.json'; a.click();
  });
  progress();
}
bind();
"""


def passages_for(pools: list[dict], export: Path) -> dict[str, dict]:
    wanted = {r["uuid"] for pool in pools for r in pool["rows"]}
    found: dict[str, dict] = {}
    with (export / "objects.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            uuid = line[10:46]  # {"uuid": "<36 chars>"
            if uuid in wanted:
                o = json.loads(line)
                found[o["uuid"]] = {"text": o.get("text_original") or o.get("text") or "", "type": o.get("chunk_type")}
    return found


def build(drafts: list[dict], pools: list[dict], export: Path, max_passages: int = 2, max_chars: int = 1400) -> str:
    texts = passages_for(pools, export)
    per_question: dict[str, dict] = collections.defaultdict(dict)
    for pool in pools:
        for r in pool["rows"]:
            page = per_question[r["id"]].setdefault((r["doc_id"], r["page"]), {"found_by": [], "uuids": [], "best": 99})
            tag = f"{pool['label']} {r['arm']} #{r['rank']}"
            if tag not in page["found_by"]:
                page["found_by"].append(tag)
            if r["uuid"] not in page["uuids"]:
                page["uuids"].append(r["uuid"])
            page["best"] = min(page["best"], r["rank"])

    data_questions, body = [], []
    for d in drafts:
        pages = sorted(per_question.get(d["id"], {}).items(), key=lambda kv: (-len(kv[1]["found_by"]), kv[1]["best"]))
        entries, blocks = [], []
        for n, ((doc_id, page_no), info) in enumerate(pages):
            key = f"p{n}"
            entries.append({"key": key, "doc_id": doc_id, "page": page_no})
            shown, seen_prefix = [], set()
            for uuid in sorted(info["uuids"], key=lambda u: -len(texts.get(u, {}).get("text", ""))):
                text = texts.get(uuid, {}).get("text", "")
                prefix = " ".join(text.lower().split())[:100]
                if not text or prefix in seen_prefix:
                    continue
                seen_prefix.add(prefix)
                shown.append(text)
                if len(shown) == max_passages:
                    break
            passages = ""
            for text in shown:
                head, tail = text[:max_chars], text[max_chars:]
                passages += f'<div class="text">{html.escape(head)}'
                if tail:
                    passages += f'<details><summary>rest of the passage ({len(tail)} more characters)</summary>{html.escape(tail)}</details>'
                passages += "</div>"
            radios = "".join(
                f'<label><input type="radio" name="{html.escape(d["id"])}-{key}" value="{g}"> {label}</label>'
                for g, label in ((0, "0 · does not help"), (1, "1 · supports the answer"), (2, "2 · answers the question")))
            blocks.append(
                f'<div class="page" data-key="{key}"><b>{html.escape(str(doc_id))} · page {html.escape(str(page_no))}</b> '
                f'<span class="arms">found by: {html.escape(", ".join(info["found_by"]))}</span>'
                f'<div class="grade">{radios}</div>{passages}</div>')
        data_questions.append({"id": d["id"], "pair": d.get("pair"), "lang": d["lang"], "question": d["question"], "pages": entries})
        body.append(
            f'<section data-id="{html.escape(d["id"])}"><h2>{html.escape(d["id"])} · {html.escape(d["lang"])}'
            f'{" · pair " + html.escape(d["pair"]) if d.get("pair") else ""}</h2>'
            f'<input class="q" value="{html.escape(d["question"], quote=True)}">'
            f'<div class="row"><label>This question: <select><option>not reviewed</option><option>keep</option>'
            f'<option>drop</option></select></label></div>'
            f'<textarea class="answer" rows="2" placeholder="The answer in one or two sentences, in your own words"></textarea>'
            f'{"".join(blocks) or "<p>No page was found for this question.</p>"}'
            f'<textarea class="extra" rows="1" placeholder="Pages that answer it and are not listed: document, page (one per line)"></textarea>'
            f'</section>')

    payload = json.dumps({"built": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "questions": data_questions},
                         ensure_ascii=False).replace("</", "<\\/")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Oxcart · literature questions review</title>'
        f"<style>{PAGE_STYLE}</style>"
        '<header><strong>Oxcart · literature questions</strong><input id="reviewer" placeholder="Your name">'
        '<span id="progress"></span><button id="download">Download judgments</button></header><main>'
        '<div class="help"><b>PRIVATE: this page contains passages of the literature. Do not share or upload it.</b><br>'
        "For each question: fix the wording if needed (or choose <i>drop</i>), mark each page "
        "(0 does not help, 1 supports the answer, 2 answers the question), and write the answer in your own words. "
        "Your marks are saved in this browser as you go. When you finish, press <i>Download judgments</i> and send the file.</div>"
        + "".join(body) +
        f'</main><script id="data" type="application/json">{payload}</script><script>{SCRIPT}</script></html>')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", required=True, type=Path)
    ap.add_argument("--pools", required=True, nargs="+", type=Path)
    ap.add_argument("--export", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    if "local-data" not in args.out.resolve().parts:
        raise SystemExit("the sheet contains literature text: write it under local-data/")
    drafts = [json.loads(line) for line in args.drafts.read_text(encoding="utf-8").splitlines() if line.strip()]
    pools = [json.loads(p.read_text(encoding="utf-8")) for p in args.pools]
    page = build(drafts, pools, args.export)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"{args.out}: {len(drafts)} questions, {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
