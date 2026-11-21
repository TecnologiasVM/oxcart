"""Ranking cases: questions seen to bring up the wrong catalogue issue first.

    OXCART_API=https://<backend> OXCART_EVAL_KEY=<secret> python -m eval.ranking_cases

Each line of eval/data/ranking_cases.jsonl is a question and the issue that should come
first. They are development questions: kept to see whether a later change moves them, and
not counted in the catalogue part's 80. Nothing is tuned on one of them alone.
Prints, for each case, the place of the wanted issue among the issues returned.
"""

from __future__ import annotations

from eval import ask_arm


def place(case: dict, issues: list) -> int | None:
    """1 for first; None when the wanted issue is not among the issues returned."""
    ids = [issue.get("issue_id") for issue in issues]
    return ids.index(case["issue_ids"][0]) + 1 if case["issue_ids"][0] in ids else None


def main() -> None:
    cases = ask_arm.load("ranking_cases.jsonl")
    first = 0
    for case in cases:
        answer, _, error = ask_arm.ask(case["question"])
        where = place(case, (answer or {}).get("issues", [])) if answer else None
        first += where == 1
        print(f"{case['id']}: wanted {case['issue_ids'][0]}: " + (f"no reply ({error})" if answer is None else
              f"place {where}" if where else f"not among the {len(answer.get('issues', []))} issues returned"))
    print(f"the wanted issue first: {first} of {len(cases)}")


if __name__ == "__main__":
    main()
