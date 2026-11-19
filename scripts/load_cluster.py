"""Rebuild Oxcart's vector store on a Weaviate Cloud cluster from one export.

    python scripts/load_cluster.py <export folder> [--candidate K] [--dims 3072] [--name Oxcart] [--replace]

The export folder holds objects.jsonl.gz, vectors.f32.npy and manifest.json. The export is
not in this repository: it holds the literature's text and is kept in a private place. The
cluster's address and an ADMIN key come from the environment, set for this process only
(scripts/with-key.sh does that from the machine's secret store):

    WEAVIATE_URL, WEAVIATE_API_KEY

Needs Python 3.10+, numpy and weaviate-client 4.24 or newer:
    uv run --with numpy --with "weaviate-client>=4.24" python scripts/load_cluster.py <folder> --replace

What it does:
- checks the two data files against the manifest's sha256 (skip with --no-checksum);
- creates the collection with the manifest's properties and keyword settings, no vectorizer,
  and one vector named "default" (the index and compression are the cluster's own choice);
- loads the passages of the chosen candidate with their stored vectors, cut to --dims and
  normalized again when --dims is below 3,072;
- refuses to pass 100,000 objects, refuses to touch an existing collection without --replace,
  stops at the first failed batch, and checks the final count.

It prints counts, timings and error classes. It never prints the address, the key, or a passage.
No embedding is made: nothing is sent to OpenAI.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path

LIMIT = 100_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--candidate", choices=list("IJK"))
    ap.add_argument("--dims", type=int, default=3072)
    ap.add_argument("--name")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--no-checksum", action="store_true")
    ap.add_argument("--batch", type=int, default=100)
    args = ap.parse_args()

    manifest = json.loads((args.folder / "manifest.json").read_text(encoding="utf-8"))
    candidate = args.candidate or manifest["loaded_in_the_cluster"]
    name = args.name or manifest["collection"]["name"]
    expected = manifest["candidates"][candidate]["objects"]
    if expected > LIMIT:
        print(f"candidate {candidate} has {expected} objects: over the {LIMIT} limit")
        return 2
    if not args.no_checksum:
        for file_name, info in manifest["files"].items():
            if sha256(args.folder / file_name) != info["sha256"]:
                print(f"{file_name}: sha256 does not match the manifest")
                return 2
        print("checksums match the manifest", flush=True)

    url, key = os.environ.get("WEAVIATE_URL", ""), os.environ.get("WEAVIATE_API_KEY", "")
    if not url or not key:
        print("WEAVIATE_URL and WEAVIATE_API_KEY are not set")
        return 2

    import numpy as np
    import weaviate
    from weaviate.classes.init import AdditionalConfig, Auth, Timeout

    vectors = np.load(args.folder / "vectors.f32.npy", mmap_mode="r")
    if args.dims > vectors.shape[1]:
        print(f"stored vectors have {vectors.shape[1]} numbers")
        return 2

    def cut(row):
        v = np.asarray(row[:args.dims], dtype=np.float64)
        n = np.linalg.norm(v)
        return (v / n if n else v).astype(np.float32).tolist()

    print(f"candidate {candidate}: {expected} objects, {args.dims} dimensions -> collection {name}", flush=True)
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=url, auth_credentials=Auth.api_key(key),
        additional_config=AdditionalConfig(timeout=Timeout(init=30, query=60, insert=120)))
    t0 = time.time()
    try:
        existing = sorted(client.collections.list_all(simple=True).keys())
        if existing:
            if not args.replace:
                print(f"the cluster already holds {existing}: use --replace to delete {name!r} first")
                return 2
            if existing != [name]:
                print(f"the cluster holds another collection ({existing}): not touching it")
                return 2
            client.collections.delete(name)
            print(f"deleted the existing {name}", flush=True)
        definition = {"class": name, "properties": manifest["collection"]["properties"],
                      "invertedIndexConfig": manifest["collection"]["invertedIndexConfig"],
                      "vectorConfig": {manifest["collection"]["vector_name"]: {"vectorizer": {"none": {}}}}}
        for attempt in range(1, 13):   # after a delete the cluster's collection counter can lag
            try:
                client.collections.create_from_dict(definition)
                break
            except Exception as exc:
                if "USAGE_LIMIT_EXCEEDED" not in str(exc) or attempt == 12:
                    print(f"create FAILED ({type(exc).__name__})")
                    return 1
                print(f"create refused by the collection limit (attempt {attempt}); waiting 30 s", flush=True)
                time.sleep(30)
        coll = client.collections.get(name)
        sent = 0
        vector_name = manifest["collection"]["vector_name"]
        with coll.batch.fixed_size(batch_size=args.batch, concurrent_requests=2) as batch:
            with gzip.open(args.folder / "objects.jsonl.gz", "rt", encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    o = json.loads(line)
                    if candidate not in o.pop("_candidates"):
                        continue
                    uuid = o.pop("uuid")
                    batch.add_object(properties={k: v for k, v in o.items() if v is not None}, uuid=uuid,
                                     vector={vector_name: cut(vectors[i])})
                    sent += 1
                    if sent % 5000 == 0:
                        print(f"{sent} sent, {time.time() - t0:.0f} s", flush=True)
                    if batch.number_errors > 0:
                        break
        failed = coll.batch.failed_objects
        total = coll.aggregate.over_all(total_count=True).total_count
        print(f"objects in {name}: {total} of {expected} expected; {len(failed)} failed; {time.time() - t0:.0f} s")
        return 0 if total == expected and not failed else 1
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
