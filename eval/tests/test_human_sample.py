"""The human sample: the draw is seeded and balanced, the page hides the model's grade, the score is right."""

import json

from eval import human_sample, table


def _pages(n_per_grade=20):
    return [{"dir": "d", "id": f"q{g}-{i % 5}", "key": f"p{i}", "lang": "en", "question": f"question {i}?",
             "doc_id": f"doc{g}", "page": i, "passages": [f"passage {g}-{i}"], "grade": g, "reason": f"SECRET-REASON-{g}"}
            for g in (0, 1, 2) for i in range(n_per_grade)]


def test_draw_is_balanced_and_repeatable():
    a = human_sample.draw(_pages(), 15, 7)
    b = human_sample.draw(_pages(), 15, 7)
    assert [(x["id"], x["key"], x["grade"]) for x in a] == [(x["id"], x["key"], x["grade"]) for x in b]
    assert sorted(x["grade"] for x in a) == [0] * 15 + [1] * 15 + [2] * 15
    assert [x["grade"] for x in a] != sorted(x["grade"] for x in a)      # shuffled: position does not give the grade
    assert human_sample.draw(_pages(), 15, 8) != a


def test_page_does_not_show_the_models_grade_or_reason():
    items = human_sample.draw(_pages(), 15, 7)
    page = human_sample.page_html(items, 7)
    assert "SECRET-REASON" not in page
    assert page.count("<section data-id=") == 45
    data = json.loads(page.split('id="data">')[1].split("</script>")[0])
    assert data == {"seed": 7, "yes_no": False, "items": [f"s{n:02d}" for n in range(1, 46)]}   # no grade travels in the page


def test_the_short_sheet_draws_answering_pages_only_and_asks_yes_or_no():
    items = human_sample.draw(_pages(), 10, 9, grades=(2,))
    assert [x["grade"] for x in items] == [2] * 10
    page = human_sample.page_html(items, 9, yes_no=True)
    assert page.count("<section data-id=") == 10
    assert page.count('value="2"> Yes') == 10 and page.count('value="1"') == 0
    assert "SECRET-REASON" not in page


def test_compare_counts_agreement():
    key = {"population": {"0": 60, "1": 20, "2": 20},
           "items": {"s01": {"grade": 2}, "s02": {"grade": 2}, "s03": {"grade": 1}, "s04": {"grade": 0}}}
    answers = {"grades": {"s01": 2, "s02": 1, "s03": 1, "s04": 0}}
    r = human_sample.compare(key, answers)
    assert r["items_graded"] == 4
    assert r["same_grade"] == 0.75
    assert r["same_answers_or_not"] == 0.75
    assert r["model_said_2_person_did_not"] == 1 and r["person_said_2_model_did_not"] == 0
    assert abs(r["same_grade_weighted"] - (0.6 * 1 + 0.2 * 1 + 0.2 * 0.5)) < 1e-9
    assert r["table_person_by_model"]["person 1, model 2"] == 1


def test_left_out_drafts_follow_their_pair_and_move_nothing():
    drafts = [{"id": "a-en", "pair": "a"}, {"id": "a-es", "pair": "a"}, {"id": "b-en"}, {"id": "c-es"}, {"id": "d-en"}]
    sides = {"a-en": "heldout", "d-en": "dev"}
    out = table.left_out_sides(drafts, sides)
    assert out["a-es"] == "heldout"
    assert set(out) == {"a-es", "b-en", "c-es"}
    assert sorted(out[q] for q in ("b-en", "c-es")) == ["dev", "heldout"]
    assert out == table.left_out_sides(drafts, sides)
