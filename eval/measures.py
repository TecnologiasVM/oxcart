"""Retrieval measures for the test set. Pure functions, standard library only.

A *hit* is a returned passage whose document and page fall inside one of the question's
gold sources. Gold is document and page, never a chunk id: chunk ids change between
subsets of the collection, pages do not.

    gold source   {"doc_id": "...", "pages": [12, 13], "grade": 2}
                  grade 2 = the page answers the question, 1 = it supports the answer
    result        {"doc_id": "...", "page": 12, ...}   in rank order, best first
"""

from __future__ import annotations

import math
import random
from typing import Callable, Iterable, Sequence


def match(result: dict, gold: Sequence[dict]) -> int | None:
    """Index of the gold source this result falls in, or None."""
    for i, source in enumerate(gold):
        if result.get("doc_id") != source["doc_id"]:
            continue
        pages = source.get("pages")
        if not pages or result.get("page") in pages:
            return i
    return None


def hit_at(results: Sequence[dict], gold: Sequence[dict], k: int) -> float:
    """1.0 when at least one of the first k results is a hit."""
    return 1.0 if any(match(r, gold) is not None for r in results[:k]) else 0.0


def answer_at(results: Sequence[dict], gold: Sequence[dict], k: int) -> float:
    """1.0 when at least one of the first k results is a page graded 2 (it answers the question)."""
    answering = [s for s in gold if s.get("grade", 1) >= 2]
    return hit_at(results, answering, k) if answering else 0.0


def recall_at(results: Sequence[dict], gold: Sequence[dict], k: int) -> float:
    """Share of the gold sources found in the first k results."""
    if not gold:
        return 0.0
    found = {match(r, gold) for r in results[:k]} - {None}
    return len(found) / len(gold)


def mrr_at(results: Sequence[dict], gold: Sequence[dict], k: int = 10) -> float:
    """1 / rank of the first hit in the first k results, 0.0 when there is none."""
    for rank, r in enumerate(results[:k], start=1):
        if match(r, gold) is not None:
            return 1.0 / rank
    return 0.0


def ndcg_at(results: Sequence[dict], gold: Sequence[dict], k: int = 10) -> float:
    """nDCG with the gold grades. A gold source counts once, at its first hit:
    a second passage from the same page adds nothing."""
    if not gold:
        return 0.0
    seen: set[int] = set()
    dcg = 0.0
    for rank, r in enumerate(results[:k], start=1):
        i = match(r, gold)
        if i is None or i in seen:
            continue
        seen.add(i)
        dcg += (2 ** gold[i].get("grade", 1) - 1) / math.log2(rank + 1)
    ideal = sorted((s.get("grade", 1) for s in gold), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(rank + 1) for rank, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


def first_hit_rank(results: Sequence[dict], gold: Sequence[dict]) -> int | None:
    for rank, r in enumerate(results, start=1):
        if match(r, gold) is not None:
            return rank
    return None


def distinct_pages(results: Sequence[dict], k: int) -> int:
    """How many different (document, page) pairs fill the first k places."""
    return len({(r.get("doc_id"), r.get("page")) for r in results[:k]})


MEASURES: dict[str, Callable[[Sequence[dict], Sequence[dict]], float]] = {
    "answer@5": lambda r, g: answer_at(r, g, 5),      # the headline: a page that answers, in the first five
    "answer@1": lambda r, g: answer_at(r, g, 1),
    "hit@5": lambda r, g: hit_at(r, g, 5),            # any gold page, supporting ones included
    "recall@5": lambda r, g: recall_at(r, g, 5),
    "recall@10": lambda r, g: recall_at(r, g, 10),
    "recall@20": lambda r, g: recall_at(r, g, 20),
    "mrr@10": lambda r, g: mrr_at(r, g, 10),
    "ndcg@10": lambda r, g: ndcg_at(r, g, 10),
}


# --------------------------------------------------------------------------- uncertainty
def percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_mean(values: Sequence[float], rounds: int = 2000, seed: int = 7) -> dict:
    """Mean with a 95% interval, resampling questions with replacement."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = random.Random(seed)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(rounds))
    return {"n": n, "mean": sum(values) / n, "lo": percentile(means, 0.025), "hi": percentile(means, 0.975)}


def paired_difference(a: Sequence[float], b: Sequence[float], rounds: int = 2000, seed: int = 7) -> dict:
    """Mean of (a - b) on the same questions, with a 95% interval, plus the questions won and lost."""
    if len(a) != len(b):
        raise ValueError("paired comparison needs the same questions on both sides")
    diff = [x - y for x, y in zip(a, b)]
    out = bootstrap_mean(diff, rounds, seed)
    out.update({"better": sum(1 for d in diff if d > 0), "worse": sum(1 for d in diff if d < 0)})
    out["includes_zero"] = bool(diff) and out["lo"] <= 0.0 <= out["hi"]
    return out


def latency_summary(seconds: Iterable[float]) -> dict:
    values = sorted(seconds)
    return {"n": len(values), "p50": percentile(values, 0.5), "p95": percentile(values, 0.95)}
