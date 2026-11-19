"""Agreement between two judges on the same pages. Standard library only.

    python -m eval.agreement <judge dir A> <judge dir B>

Each directory is a judge directory of eval/model_judge.py (inputs/ and outputs/). Pages
are matched by question id and page key. Prints, over the pages both judged: how often the
two gave the same grade, how often they agree on "helps or not" (grade above 0), Cohen's
kappa for both, and how often they agree that a question has at least one answering page.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def kappa(pairs: list[tuple]) -> float:
    """Cohen's kappa for two raters over the same items."""
    n = len(pairs)
    if n == 0:
        return float("nan")
    observed = sum(1 for a, b in pairs if a == b) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def load(directory: Path) -> dict[str, dict[str, int]]:
    out = {}
    for f in sorted((directory / "outputs").glob("*.json")):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
            out[f.stem] = {p["key"]: int(p["grade"]) for p in a["pages"]}
        except (ValueError, KeyError):
            continue
    return out


def compare(a: dict, b: dict) -> dict:
    pairs, per_question = [], []
    for qid in sorted(set(a) & set(b)):
        keys = sorted(set(a[qid]) & set(b[qid]))
        pairs += [(a[qid][k], b[qid][k]) for k in keys]
        per_question.append((any(a[qid][k] == 2 for k in keys), any(b[qid][k] == 2 for k in keys),
                             any(a[qid][k] > 0 for k in keys), any(b[qid][k] > 0 for k in keys)))
    binary = [(x > 0, y > 0) for x, y in pairs]
    n = len(pairs)
    return {
        "questions": len(per_question), "pages": n,
        "same_grade": sum(1 for x, y in pairs if x == y) / n if n else None,
        "kappa_grade": kappa(pairs),
        "same_helps_or_not": sum(1 for x, y in binary if x == y) / n if n else None,
        "kappa_helps_or_not": kappa(binary),
        "off_by_two": sum(1 for x, y in pairs if abs(x - y) == 2),
        "questions_agree_on_an_answering_page": sum(1 for q in per_question if q[0] == q[1]),
        "questions_agree_on_any_support": sum(1 for q in per_question if q[2] == q[3]),
        "confusion": {f"{x}->{y}": c for (x, y), c in sorted(collections.Counter(pairs).items())},
    }


if __name__ == "__main__":
    result = compare(load(Path(sys.argv[1])), load(Path(sys.argv[2])))
    print(json.dumps(result, indent=1))
