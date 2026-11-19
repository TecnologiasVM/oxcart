"""Scoring of a run: pure functions over questions and results. Standard library only."""

from __future__ import annotations

from eval import measures


def score(questions: list[dict], results: dict, baseline: str = "keyword") -> dict:
    """Per arm: every measure with its interval, by language, plus the paired difference to the baseline arm."""
    literature = [q for q in questions if q["type"] == "literature" and q.get("gold", {}).get("sources")]
    arm_names = list(next(iter(results.values())).keys()) if results else []
    out = {"n": len(literature), "arms": {}}
    per_arm_values: dict[str, dict[str, list[float]]] = {}
    for arm in arm_names:
        values = {m: [] for m in measures.MEASURES}
        by_lang: dict[str, dict[str, list[float]]] = {}
        distinct, seconds = [], []
        for q in literature:
            hits = results[q["id"]][arm]["hits"]
            gold = q["gold"]["sources"]
            for m, fn in measures.MEASURES.items():
                x = fn(hits, gold)
                values[m].append(x)
                by_lang.setdefault(q["lang"], {k: [] for k in measures.MEASURES})[m].append(x)
            distinct.append(measures.distinct_pages(hits, 5))
            seconds.append(results[q["id"]][arm]["seconds"])
        per_arm_values[arm] = values
        out["arms"][arm] = {
            "measures": {m: measures.bootstrap_mean(v) for m, v in values.items()},
            "by_lang": {lang: {m: (sum(v) / len(v) if v else None) for m, v in ms.items()} for lang, ms in by_lang.items()},
            "distinct_pages_in_top5": (sum(distinct) / len(distinct)) if distinct else None,
            "latency": measures.latency_summary(seconds),
        }
    if baseline in per_arm_values:
        for arm in arm_names:
            if arm != baseline:
                out["arms"][arm]["vs_" + baseline] = {
                    m: measures.paired_difference(per_arm_values[arm][m], per_arm_values[baseline][m])
                    for m in ("answer@5", "ndcg@10")}
    return out


def top_scores(questions: list[dict], results: dict) -> dict:
    """Best score of each arm per question, grouped by kind of question: can a threshold tell
    the questions the sources cover from the ones they do not?"""
    groups: dict[str, list[dict]] = {}
    for q in questions:
        key = "in scope (literature)" if q["type"] == "literature" else q.get("category", q["type"])
        groups.setdefault(key, []).append(q)
    out: dict[str, dict] = {}
    arm_names = [a for a in (next(iter(results.values())).keys() if results else []) if a != "app-today"]
    for arm in arm_names:
        per_group = {}
        for key, qs in groups.items():
            tops = sorted((results[q["id"]][arm]["hits"][0]["score"] or 0.0) if results[q["id"]][arm]["hits"] else 0.0 for q in qs)
            per_group[key] = {"n": len(tops), "min": tops[0], "median": measures.percentile(tops, 0.5), "max": tops[-1],
                              "values": tops}
        inside = per_group.get("in scope (literature)", {}).get("values", [])
        row = {"groups": {k: {x: v[x] for x in ("n", "min", "median", "max")} for k, v in per_group.items()}}
        for key, v in per_group.items():
            if key != "in scope (literature)" and inside and v["values"]:
                wins = sum((a > b) + 0.5 * (a == b) for a in inside for b in v["values"])
                row.setdefault("separation", {})[key] = round(wins / (len(inside) * len(v["values"])), 3)
        out[arm] = row
    return out
