"""The written answers' eval tools. Every text is made up."""

import json

import pytest

from eval import answer_judge, chat_arm


def test_cost_adds_every_call_at_the_listed_prices():
    calls = [{"input_tokens": 1_000_000, "output_tokens": 0}, {"input_tokens": 0, "output_tokens": 1_000_000}]
    assert chat_arm.cost(calls) == pytest.approx(chat_arm.USD_PER_MTOK_IN + chat_arm.USD_PER_MTOK_OUT)
    assert chat_arm.cost([]) == 0


def test_the_text_of_an_answer_is_its_sentences():
    assert chat_arm.text_of({"sentences": [{"text": "One."}, {"text": "Two."}]}) == "One. Two."
    assert chat_arm.text_of({"state": "not_covered"}) == ""


def test_judge_inputs_are_written_under_local_data_only(tmp_path):
    args = type("Args", (), {"dir": str(tmp_path / "judge"), "label": "x", "references": None})()
    with pytest.raises(SystemExit):
        answer_judge.prepare(args)


def test_collect_keeps_marks_only_and_refuses_a_grade_that_does_not_match_its_input(tmp_path, capsys):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "outputs").mkdir()
    for name, reference in (("cat-1", {"kind": "printer", "gold_value": ["A printer"]}), ("lit-1", None), ("lit-2", None), ("lit-3", None)):
        (tmp_path / "inputs" / f"{name}.json").write_text(json.dumps(
            {"id": name, "part": name[:3], "lang": "en", "question": "A question?", "reference": reference,
             "sentences": [{"n": 1, "text": "One.", "cites": [1]}, {"n": 2, "text": "Two.", "cites": [1]}], "sources": []}))
    grade = {"sentences": [{"n": 1, "supported": "yes", "reason": "a made-up reason"}, {"n": 2, "supported": "partly", "reason": "r"}],
             "correct": "yes", "correct_reason": "another made-up reason", "language": "same"}
    (tmp_path / "outputs" / "cat-1.json").write_text(json.dumps({"id": "cat-1", **grade}))
    (tmp_path / "outputs" / "lit-1.json").write_text(json.dumps({"id": "lit-1", **grade}))
    (tmp_path / "outputs" / "lit-2.json").write_text(json.dumps({"id": "lit-2", **grade, "sentences": grade["sentences"][:1]}))
    answer_judge.collect(type("Args", (), {"dir": str(tmp_path)})())
    graded = json.loads((tmp_path / "grades.json").read_text())["answers"]
    assert [g["id"] for g in graded] == ["cat-1", "lit-1"]
    assert graded[0] == {"id": "cat-1", "part": "cat", "lang": "en", "correct": "yes", "language": "same",
                         "sentences": [{"n": 1, "supported": "yes"}, {"n": 2, "supported": "partly"}]}
    assert graded[1]["correct"] == "no reference"            # no reference to compare with: not counted as correct
    assert "made-up reason" not in (tmp_path / "grades.json").read_text()
    out = capsys.readouterr().out
    assert "lit-2: the grade does not match its input" in out and "lit-3: no grade" in out


def test_the_first_pass_is_told_what_it_was_told_before_the_second_measure_existed():
    # Runs graded before and after must stay comparable: the first pass's instructions are fixed.
    import hashlib
    assert hashlib.sha256(answer_judge.PROMPT.encode()).hexdigest() == "825affb99423b87fb797fa8b8fffd14b0a856ad9babee529fd817c27fdf74e4f"
    assert set(answer_judge.SCHEMA["required"]) == {"id", "sentences", "correct", "correct_reason", "language"}


def test_the_second_pass_keeps_its_mark_only_and_refuses_a_grade_that_does_not_match(tmp_path, capsys):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "outputs").mkdir()
    for name, reference in (("cat-1", {"kind": "printer", "gold_value": ["A printer"]}), ("lit-1", {"reference_answer": "A made-up reference."}),
                            ("lit-2", None), ("lit-3", {"reference_answer": "r"}), ("lit-4", {"reference_answer": "r"})):
        (tmp_path / "inputs" / f"{name}.json").write_text(json.dumps(
            {"id": name, "part": "catalogue" if name.startswith("cat") else "literature", "lang": "en",
             "question": "A question?", "answer": "A made-up answer.", "reference": reference}))
    (tmp_path / "outputs" / "cat-1.json").write_text(json.dumps({"id": "cat-1", "asked": "yes", "reason": "a made-up reason"}))
    (tmp_path / "outputs" / "lit-1.json").write_text(json.dumps({"id": "lit-1", "asked": "partly", "reason": "r"}))
    (tmp_path / "outputs" / "lit-2.json").write_text(json.dumps({"id": "lit-2", "asked": "yes", "reason": "r"}))
    (tmp_path / "outputs" / "lit-3.json").write_text(json.dumps({"id": "lit-9", "asked": "yes", "reason": "r"}))
    answer_judge.collect_asked(type("Args", (), {"dir": str(tmp_path)})())
    text = (tmp_path / "asked.json").read_text()
    graded = {a["id"]: a["asked"] for a in json.loads(text)["answers"]}
    assert graded == {"cat-1": "yes", "lit-1": "partly", "lit-2": "no reference"}
    assert "made-up" not in text
    out = capsys.readouterr().out
    assert "PROBLEM lit-3" in out and "PROBLEM lit-4" in out


def test_the_second_pass_writes_under_local_data_only(tmp_path):
    args = type("Args", (), {"dir": str(tmp_path / "judge"), "label": "x", "references": None})()
    with pytest.raises(SystemExit):
        answer_judge.prepare_asked(args)


def test_a_row_is_one_line_even_when_its_text_holds_other_line_characters(tmp_path):
    path = tmp_path / "answers.jsonl"
    rows = [{"id": "a", "text": "a form feed \x0c and a line separator \u2028 inside a made-up passage"}, {"id": "b", "text": "plain"}]
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    assert chat_arm._rows(path) == rows


def test_ranking_cases_are_well_formed_and_their_place_is_read_from_the_issues():
    from eval import ask_arm, ranking_cases
    cases = ask_arm.load("ranking_cases.jsonl")
    assert cases and len({c["id"] for c in cases}) == len(cases)
    assert all(c["type"] == "ranking" and c["question"].strip() and all(i.startswith("CR-") for i in c["issue_ids"]) for c in cases)
    case = {"issue_ids": ["CR-9999-MADE-UP"]}
    assert ranking_cases.place(case, [{"issue_id": "CR-1"}, {"issue_id": "CR-9999-MADE-UP"}]) == 2
    assert ranking_cases.place(case, [{"issue_id": "CR-1"}]) is None
    several = {"issue_ids": ["CR-A", "CR-B"]}
    assert ranking_cases.place(several, [{"issue_id": "CR-1"}, {"issue_id": "CR-B"}, {"issue_id": "CR-A"}]) == 2
    assert ranking_cases.place({"issue_ids": []}, [{"issue_id": "CR-1"}]) is None
