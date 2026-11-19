"""Development / held-out split of the test set. Pure function, standard library only.

Settings are chosen on the development questions; the headline numbers are the held-out
ones. The split is fixed by a seed, stratified by question type (and, for catalogue
questions, by fact kind), and keeps the Spanish and English versions of one question on
the same side: otherwise tuning on one would leak into the other.
"""

from __future__ import annotations

import collections
import random

SEED = 20261118
DEV_SHARE = 0.6


def assign(questions: list[dict], seed: int = SEED, dev_share: float = DEV_SHARE) -> dict[str, str]:
    """Return {question id: "dev" | "heldout"}."""
    units: dict[tuple, list[str]] = collections.defaultdict(list)   # stratum -> unit keys (pair or id)
    members: dict[str, list[str]] = collections.defaultdict(list)
    for q in questions:
        unit = q.get("pair") or q["id"]
        stratum = (q["type"], q.get("fact") or q.get("category") or "")
        if unit not in members:
            units[stratum].append(unit)
        members[unit].append(q["id"])
    out: dict[str, str] = {}
    for stratum in sorted(units):
        keys = sorted(units[stratum])
        random.Random(f"{seed}:{stratum}").shuffle(keys)
        n_dev = round(len(keys) * dev_share)
        for i, unit in enumerate(keys):
            side = "dev" if i < n_dev else "heldout"
            for qid in members[unit]:
                out[qid] = side
    return out
