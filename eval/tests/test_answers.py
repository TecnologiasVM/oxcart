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


# --------------------------------------------------------------------------- the published summary
LIT_Q = [{"id": "lit-1", "gold": {"sources": [{"doc_id": "DOC A", "pages": [3], "grade": 2}]}},
         {"id": "lit-2", "gold": {"sources": [{"doc_id": "DOC B", "pages": [9], "grade": 2}]}},
         {"id": "lit-3", "gold": {"sources": [{"doc_id": "DOC C", "pages": [1], "grade": 1}]}}]
CAT_Q = [{"id": "cat-1", "issue_ids": ["I-1"], "fact": "printer", "gold": {"value": ["A printer"], "params": {}}},
         {"id": "cat-2", "issue_ids": ["I-2"], "fact": "printer", "gold": {"value": ["A printer"], "params": {}}},
         {"id": "cat-3", "issue_ids": ["I-3"], "fact": "printer", "gold": {"value": ["A printer"], "params": {}}}]
CARD = {"printers": ["A printer"], "stamps": [], "dates": {}, "acts": []}


def _row(qid, part, passages=(), issues=(), first=1.0, seconds=3.0):
    return {"id": qid, "part": part, "lang": "en", "first_seconds": first, "seconds": seconds,
            "evidence": {"passages": [{"doc_id": d, "page": p, "text": "A made-up passage."} for d, p in passages],
                         "issues": [{"issue_id": i, "card": CARD} for i in issues]},
            "answer": {"state": "ok", "sentences": [{"text": "A made-up sentence.", "cites": [1]}],
                       "counts": {"sentences": 1, "sentences_without_citation": 0, "citations": 1, "citations_that_do_not_hold": 0}},
            "calls": [{"purpose": "write", "state": "ok", "input_tokens": 10, "output_tokens": 2, "seconds": 1.0}]}


RUN = [_row("lit-1", "literature", [("DOC X", 1), ("DOC A", 3)], first=1.0, seconds=2.0),
       _row("lit-2", "literature", [("DOC B", 8)], first=2.0, seconds=4.0),
       _row("lit-3", "literature", [("DOC C", 1)], first=3.0, seconds=6.0),
       _row("cat-1", "catalogue", issues=["I-1", "I-9"], first=4.0, seconds=8.0),
       _row("cat-2", "catalogue", issues=["I-9", "I-2"], first=5.0, seconds=10.0),
       # cat-3 got no reply: it is not counted as asked
       {"id": "cat-3", "part": "catalogue", "lang": "en", "error": "HTTP 500"},
       {"id": "thr-1", "part": "threads", "lang": "en", "first_seconds": 99.0, "seconds": 99.0, "gold_issue": "I-1",
        "alone_issues": [], "evidence": {"issues": [], "passages": []}, "answer": {"state": "ok"}, "calls": []}]


def test_retrieval_counts_a_page_graded_2_in_the_first_five_and_the_issue_with_its_fact():
    counts = chat_arm.retrieval_counts([r for r in RUN if r["part"] != "threads"], LIT_Q, CAT_Q, drafts_left_out=2)
    # lit-1: a page graded 2 at rank 2; lit-2: another page of the gold document; lit-3: graded 1 only
    assert counts["literature"] == {"k": 5, "answered_in_first_k": 1, "questions": 3, "asked": 3, "drafts": 5}
    # cat-1 first, cat-2 second, cat-3 not asked
    assert counts["catalogue"] == {"issue_first_with_fact": 1, "issue_in_first_three_with_fact": 2, "asked": 2}


def test_the_waits_are_of_the_questions_asked_once_and_leave_out_the_threads():
    waits = chat_arm.wait_summary(RUN)
    assert waits["evidence"] == {"n": 5, "median": 3.0, "p95": 4.8}
    assert waits["answer"] == {"n": 5, "median": 6.0, "p95": 9.6}
    assert chat_arm.wait_summary([]) == {}


def test_the_published_file_has_the_summary_and_no_text(tmp_path, monkeypatch):
    label = "made-up"
    (tmp_path / "chat" / label).mkdir(parents=True)
    (tmp_path / "chat" / label / "answers.jsonl").write_text("\n".join(json.dumps(r) for r in RUN) + "\n", encoding="utf-8")
    monkeypatch.setattr(chat_arm, "OUT", tmp_path / "chat")
    monkeypatch.setattr(chat_arm, "OUTCOMES", tmp_path / "outcomes")
    monkeypatch.setattr(chat_arm, "DRAFTS_LEFT_OUT", 2)
    monkeypatch.setattr(chat_arm.ask_arm, "load", lambda name: {"questions_literature.jsonl": LIT_Q,
                                                                 "questions_catalogue.jsonl": CAT_Q}.get(name, []))
    monkeypatch.setattr(chat_arm.stores, "REPO", tmp_path)
    args = type("Args", (), {"label": label, "grades": None, "asked": None, "judge": "a judge", "publish": True})()
    chat_arm.table(args)
    text = (tmp_path / "outcomes" / f"answers_{label}.json").read_text(encoding="utf-8")
    published = json.loads(text)
    assert published["summary"]["retrieval"]["literature"]["answered_in_first_k"] == 1
    assert published["summary"]["retrieval"]["catalogue"]["issue_first_with_fact"] == 1
    assert published["summary"]["waits"]["answer"]["median"] == 6.0
    assert len(published["rows"]) == len(RUN)
    for made_up in ("A made-up passage.", "A made-up sentence.", "DOC A", "first_seconds"):
        assert made_up not in text


def test_each_published_row_says_whether_its_answer_carried_a_web_ticket_and_never_the_ticket(tmp_path, monkeypatch):
    label = "made-up-tickets"
    rows = [dict(RUN[0], answer=dict(RUN[0]["answer"], web={"ticket": "a-made-up-ticket-value", "expires_in": 120})),
            dict(RUN[1]),
            {"id": "cat-3", "part": "catalogue", "lang": "en", "error": "HTTP 500"}]
    (tmp_path / "chat" / label).mkdir(parents=True)
    (tmp_path / "chat" / label / "answers.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(chat_arm, "OUT", tmp_path / "chat")
    monkeypatch.setattr(chat_arm, "OUTCOMES", tmp_path / "outcomes")
    monkeypatch.setattr(chat_arm.ask_arm, "load", lambda name: {"questions_literature.jsonl": LIT_Q,
                                                                 "questions_catalogue.jsonl": CAT_Q}.get(name, []))
    monkeypatch.setattr(chat_arm.stores, "REPO", tmp_path)
    chat_arm.table(type("Args", (), {"label": label, "grades": None, "asked": None, "judge": "", "publish": True})())
    text = (tmp_path / "outcomes" / f"answers_{label}.json").read_text(encoding="utf-8")
    published = json.loads(text)["rows"]
    assert [r["web_ticket"] for r in published] == [True, False, False]
    assert "a-made-up-ticket-value" not in text and "expires_in" not in text
