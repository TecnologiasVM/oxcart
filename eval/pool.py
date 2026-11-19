"""Pool the first results of every arm for draft literature questions, for human judging.

    python -m eval.pool --drafts drafts.jsonl --label full --out local-data/eval/pool_full.json

Runs keyword, vector and hybrid search for each draft question on the Weaviate target the
environment names (see eval/stores.py) and keeps the first K results of each. Run it once
per collection; eval/review_sheet.py merges the pools into one sheet. The output holds ids,
pages and ranks only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval import arms, embed, stores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", required=True, type=Path)
    ap.add_argument("--label", required=True, help="a name for this collection, e.g. full or collapsed")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--alpha", type=float, default=0.35)
    args = ap.parse_args()

    drafts = [json.loads(line) for line in args.drafts.read_text(encoding="utf-8").splitlines() if line.strip()]
    vectors, info = embed.question_vectors([d["question"] for d in drafts])
    client, name, target, where = stores.weaviate_target()
    rows = []
    try:
        coll = client.collections.get(name)
        dims = int(target[1:]) if target and target[1:].isdigit() else None
        for d in drafts:
            v = embed.cut(vectors[d["question"]], dims)
            for arm, fn in arms.all_arms(alphas=(args.alpha,)).items():
                for rank, hit in enumerate(fn(coll, d["question"], v, args.k, target), start=1):
                    rows.append({"id": d["id"], "arm": arm, "rank": rank, "doc_id": hit["doc_id"],
                                 "page": hit["page"], "uuid": hit["uuid"], "chunk_type": hit["chunk_type"]})
    finally:
        client.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"label": args.label, "collection": name, "where": where, "k": args.k,
                                    "embedding": info, "rows": rows}), encoding="utf-8")
    pages = {(r["id"], r["doc_id"], r["page"]) for r in rows}
    print(f"{args.label}: {len(drafts)} questions, {len(rows)} results, {len(pages)} distinct question-pages; embedding {info}")


if __name__ == "__main__":
    main()
