"""Question embeddings for the eval, made once and cached. Standard library only.

The collection's passages were embedded with text-embedding-3-large (3,072 numbers). Each
question is embedded at full size once; shorter vectors are the first N numbers,
normalized again (OpenAI's embeddings guide allows this for the -3 models; checked on
this corpus: cosine similarity 0.9999 against the API's own `dimensions=1024`).

The cache holds vectors only, keyed by a hash of the model and the question. It lives in
local-data/, which is git-ignored. The key is read from OPENAI_API_KEY in this process
and is never written or printed.
"""

from __future__ import annotations

import array
import base64
import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "text-embedding-3-large"
FULL = 3072
DEFAULT_CACHE = Path(__file__).resolve().parent.parent / "local-data" / "eval" / "question_vectors.json"


def _key(text: str) -> str:
    return hashlib.sha256(f"{MODEL}\n{text}".encode("utf-8")).hexdigest()


def _pack(vec: list[float]) -> str:
    return base64.b64encode(array.array("f", vec).tobytes()).decode("ascii")


def _unpack(blob: str) -> list[float]:
    a = array.array("f")
    a.frombytes(base64.b64decode(blob))
    return a.tolist()


def cut(vec: list[float], dimensions: int | None) -> list[float]:
    """First N numbers of a vector, normalized to unit length."""
    v = vec if not dimensions or dimensions >= len(vec) else vec[:dimensions]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v] if norm else list(v)


def _request(texts: list[str]) -> tuple[list[list[float]], int]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set and some questions are not in the cache. "
                         "Start the run through scripts/with-key.sh, or export the variable.")
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": MODEL, "input": texts}).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = re.sub(r"sk-[\w\-*.]{4,}", "sk-<redacted>", exc.read().decode("utf-8", "replace")[:400])
        raise SystemExit(f"embeddings request failed, HTTP {exc.code}: {detail}") from None
    rows = sorted(payload["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in rows], int(payload["usage"]["total_tokens"])


def question_vectors(questions: list[str], cache_path: Path = DEFAULT_CACHE, batch: int = 100) -> tuple[dict, dict]:
    """Return ({question: full vector}, {"embedded": n, "cached": n, "tokens": n})."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    missing = [q for q in dict.fromkeys(questions) if _key(q) not in cache]
    tokens = 0
    for i in range(0, len(missing), batch):
        part = missing[i:i + batch]
        vectors, used = _request(part)
        tokens += used
        for q, v in zip(part, vectors):
            if len(v) != FULL:
                raise SystemExit(f"the API returned {len(v)} numbers, expected {FULL}")
            cache[_key(q)] = _pack(v)
    if missing:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    out = {q: _unpack(cache[_key(q)]) for q in questions}
    return out, {"embedded": len(missing), "cached": len(set(questions)) - len(missing), "tokens": tokens}
