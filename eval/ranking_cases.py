"""Ranking cases: questions seen to bring up the wrong catalogue issue first.

    OXCART_API=https://<backend> OXCART_EVAL_KEY=<secret> python -m eval.ranking_cases

Each line of eval/data/ranking_cases.jsonl is a question and the issues that answer it (any
one of them counts; an empty list says the catalogue has no card for it). They are
development questions: kept to see whether a later change moves them, and not counted in
the catalogue part's 80. Nothing is tuned on one of them alone.
Prints, for each case, the best place of a wanted issue among the issues returned.
"""

from __future__ import annotations

from eval import ask_arm


def place(case: dict, issues: list) -> int | None:
    """1 for first; None when no wanted issue is among the issues returned (or the case has none)."""
    ids = [issue.get("issue_id") for issue in issues]
    places = [ids.index(wanted) + 1 for wanted in case["issue_ids"] if wanted in ids]
    return min(places) if places else None


def main() -> None:
    cases = ask_arm.load("ranking_cases.jsonl")
    first = shown = with_card = 0
    for case in cases:
        if not case["issue_ids"]:
            print(f"{case['id']}: no card in the catalogue; not counted")
            continue
        with_card += 1
        answer, _, error = ask_arm.ask(case["question"])
        where = place(case, (answer or {}).get("issues", [])) if answer else None
        first += where == 1
        shown += where is not None
        wanted = case["issue_ids"][0] + (f" or {len(case['issue_ids']) - 1} more" if len(case["issue_ids"]) > 1 else "")
        print(f"{case['id']}: wanted {wanted}: " + (f"no reply ({error})" if answer is None else
              f"place {where}" if where else f"not among the {len(answer.get('issues', []))} issues returned"))
    print(f"a wanted issue first: {first} of {with_card}; among the issues returned: {shown} of {with_card}")


if __name__ == "__main__":
    main()
