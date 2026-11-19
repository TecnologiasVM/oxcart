"""Find pages that reached the first results of some run and were never judged.

    python -m eval.unjudged --judgments j1.json [j2.json ...] --runs run_a.json run_b.json \
        --out local-data/eval/pool_unjudged.json [--k 5]

Gold built from a pool favours the arms that made the pool: a page another arm or another
collection brings up was never shown to the judge and would silently count as a miss.
This lists every such page, as a pool file eval/model_judge.py (or the review sheet) can
take, so it gets judged too. Run it after new runs and before reporting numbers.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def judged_pages(files: list[Path]) -> dict[str, set]:
    seen: dict[str, set] = collections.defaultdict(set)
    for f in files:
        for q in json.loads(f.read_text(encoding="utf-8"))["questions"]:
            for p in q.get("pages") or []:
                seen[q["id"]].add((p["doc_id"], p["page"]))
    return seen


def chunk_index(export: Path, wanted: set) -> dict[str, str]:
    """chunk_id -> uuid for the chunk ids asked for (the app's answers carry chunk ids, not uuids)."""
    out = {}
    with (export / "objects.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            o = json.loads(line)
            if o.get("chunk_id") in wanted:
                out[o["chunk_id"]] = o["uuid"]
    return out


def find(judged: dict[str, set], runs: list[dict], k: int, by_chunk: dict[str, str] | None = None) -> list[dict]:
    rows, taken = [], set()
    by_chunk = by_chunk or {}
    for run in runs:
        for qid, per_arm in run["results"].items():
            if qid not in judged:          # not a judged literature question
                continue
            for arm, data in per_arm.items():
                for rank, hit in enumerate(data["hits"][:k], start=1):
                    page = (hit.get("doc_id"), hit.get("page"))
                    uuid = hit.get("uuid") or by_chunk.get(hit.get("chunk_id"))
                    if page in judged[qid] or not uuid:
                        continue
                    key = (qid, page, uuid)
                    if key in taken:
                        continue
                    taken.add(key)
                    rows.append({"id": qid, "arm": f"{run['label']}:{arm}", "rank": rank, "doc_id": page[0],
                                 "page": page[1], "uuid": uuid, "chunk_type": hit.get("chunk_type")})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judgments", required=True, nargs="+", type=Path)
    ap.add_argument("--runs", required=True, nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--export", type=Path, help="the local export, to resolve hits that carry a chunk id and no uuid")
    args = ap.parse_args()
    judged = judged_pages(args.judgments)
    runs = [json.loads(r.read_text(encoding="utf-8")) for r in args.runs]
    by_chunk = {}
    if args.export:
        wanted = {h.get("chunk_id") for run in runs for per_arm in run["results"].values() for data in per_arm.values()
                  for h in data["hits"][:args.k] if not h.get("uuid") and h.get("chunk_id")}
        by_chunk = chunk_index(args.export, wanted) if wanted else {}
    rows = find(judged, runs, args.k, by_chunk)
    args.out.write_text(json.dumps({"label": "unjudged", "k": args.k, "rows": rows}), encoding="utf-8")
    pages = {(r["id"], r["doc_id"], r["page"]) for r in rows}
    print(f"{len(pages)} unjudged pages in the first {args.k} of some arm, over {len({r['id'] for r in rows})} questions -> {args.out}")


if __name__ == "__main__":
    main()
