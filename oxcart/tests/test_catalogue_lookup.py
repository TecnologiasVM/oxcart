"""Tests for catalogue_lookup's question reading and query building. No database.

    python -m unittest discover -s oxcart/tests -p "test_catalogue_lookup.py"
"""

import unittest

from oxcart import catalogue_lookup as cl


class FakeSession:
    """Answers the lookup's four queries from small tables."""

    def __init__(self, by_mena=(), by_scott=(), by_text=(), by_year=(), by_vector=(), by_short=()):
        self.tables = {"mena": by_mena, "scott": by_scott, "text": by_text, "year": by_year, "vector": by_vector,
                       "short": by_short}
        self.calls = []

    def run(self, query, **params):
        for name, marker in (("mena", "toUpper(s.catalog_no)"), ("scott", "toUpper(sc.scott_number)"),
                             ("text", "issue_text_idx"), ("vector", "issue_vec_idx"), ("short", "issue_short_vec_idx"),
                             ("year", "i.issue_id CONTAINS")):
            if marker in query:
                self.calls.append((name, params))
                return list(self.tables[name])
        raise AssertionError("unexpected query")


class Parse(unittest.TestCase):
    def test_mena_numbers_in_english_and_spanish(self):
        self.assertEqual(cl.parse("How many copies were printed of the stamp with Mena number A317?").mena_numbers, ["A317"])
        self.assertEqual(cl.parse("¿Cuántos ejemplares se imprimieron del sello número 17 del catálogo Mena?").mena_numbers, ["17"])
        self.assertEqual(cl.parse("Mena #1a and Mena 069").mena_numbers, ["1A", "069"])
        self.assertEqual(cl.parse("the Mena catalogue lists many stamps").mena_numbers, [])

    def test_scott_number_is_not_taken_from_the_words_around_it(self):
        p = cl.parse("What is the Scott number of the stamp with Mena number 1A, from the 1863 First Issue?")
        self.assertEqual((p.scott_numbers, p.mena_numbers, p.years), ([], ["1A"], [1863]))
        self.assertEqual(cl.parse("Scott 16 and Scott No. C45").scott_numbers, ["16", "C45"])
        self.assertEqual(cl.parse("¿Cuál es el número 3 del catálogo Scott?").scott_numbers, ["3"])

    def test_years(self):
        self.assertEqual(cl.parse("the 1946 hospital issue and the 2011 stadium").years, [1946, 2011])
        self.assertEqual(cl.parse("300000 copies, perf 12").years, [])
        self.assertEqual(cl.parse("los resellos de 1930-32").years, [1930])

    def test_terms_drop_question_words_numbers_and_shared_vocabulary(self):
        p = cl.parse("Who printed the 1946 San Juan de Dios Hospital issue?")
        self.assertEqual(p.terms, ["san", "juan", "dios", "hospital"])
        p = cl.parse("¿Quién imprimió la emisión del Hospital San Juan de Dios de 1946?")
        self.assertEqual(p.terms, ["hospital", "san", "juan", "dios"])


class ShortText(unittest.TestCase):
    def test_title_years_and_section(self):
        self.assertEqual(cl.short_text("CR-1936-COCO-ISLAND", "Coco Island issue", '{"placed_on_sale": "1937-01-05"}', "Airmail"),
                         "Coco Island issue. Costa Rica, 1936, 1937. Airmail")
        self.assertEqual(cl.short_text("CR-SEALS", None, None, None), ". Costa Rica, .")


class Query(unittest.TestCase):
    def test_title_is_weighted_and_specials_are_escaped(self):
        self.assertEqual(cl.lucene_query(["coco", "island"]), "title:(coco OR island)^3 OR (coco OR island)")
        self.assertEqual(cl.lucene_query([]), "")
        self.assertIn(r"a\-b", cl.lucene_query(["a-b"]))


class FindIssues(unittest.TestCase):
    def test_a_catalogue_number_outranks_text(self):
        session = FakeSession(
            by_mena=[{"issue_id": "CR-1960-ROME", "title": "Rome Olympics issue", "number": "A317"}],
            by_text=[{"issue_id": "CR-1980-OTHER", "title": "Olympics issue", "issue_dates": "{}", "score": 9.0}])
        hits = cl.find_issues(session, "Olympics: how many copies of Mena A317?")
        self.assertEqual([h["issue_id"] for h in hits], ["CR-1960-ROME", "CR-1980-OTHER"])
        self.assertEqual(hits[0]["matched_by"], ["Mena A317"])

    def test_the_year_breaks_a_tie_between_text_hits(self):
        session = FakeSession(
            by_text=[{"issue_id": "CR-1936-COCO-ISLAND", "title": "Coco Island issue", "issue_dates": "{}", "score": 5.0},
                     {"issue_id": "CR-2003-COCO-ISLAND-25TH", "title": "Coco Island 25th", "issue_dates": "{}", "score": 5.0}],
            by_year=[{"issue_id": "CR-2003-COCO-ISLAND-25TH", "title": "Coco Island 25th"},
                     {"issue_id": "CR-2003-SOMETHING-ELSE", "title": "Something else"}])
        hits = cl.find_issues(session, "Which act authorized the 2003 Coco Island issue?", k=3)
        self.assertEqual(hits[0]["issue_id"], "CR-2003-COCO-ISLAND-25TH")
        self.assertEqual(hits[0]["score"], cl.TEXT_WEIGHT + cl.YEAR_WEIGHT)   # the year counted once
        self.assertEqual({h["issue_id"] for h in hits[1:]}, {"CR-1936-COCO-ISLAND", "CR-2003-SOMETHING-ELSE"})

    def test_a_year_found_only_in_the_dates_counts(self):
        session = FakeSession(by_text=[{"issue_id": "CR-SEALS", "title": "Seals", "score": 2.0,
                                        "issue_dates": '{"placed_on_sale": "1911-05-01"}'}])
        hits = cl.find_issues(session, "the 1911 seals")
        self.assertEqual(hits[0]["matched_by"], ["text", "year"])

    def test_the_vector_index_finds_what_the_words_do_not(self):
        # a Spanish question: its words match the wrong English titles, its meaning the right one
        session = FakeSession(
            by_text=[{"issue_id": "CR-1946-ELECTORAL", "title": "Electoral stamps", "issue_dates": "{}", "score": 3.0}],
            by_vector=[{"issue_id": "CR-1999-SUPREME-COURT-OF-ELECTIONS", "title": "Supreme Court of Elections issue",
                        "issue_dates": "{}", "score": 0.91},
                       {"issue_id": "CR-1946-ELECTORAL", "title": "Electoral stamps", "issue_dates": "{}", "score": 0.80}],
            by_year=[{"issue_id": "CR-1999-SUPREME-COURT-OF-ELECTIONS", "title": "Supreme Court of Elections issue"}])
        question = "¿Cuándo se puso a la venta la emisión del Tribunal Supremo de Elecciones de 1999?"
        without = cl.find_issues(session, question)
        self.assertEqual(without[0]["issue_id"], "CR-1946-ELECTORAL")
        session.calls.clear()
        with_vector = cl.find_issues(session, question, question_vector=[0.1, 0.2])
        self.assertEqual(with_vector[0]["issue_id"], "CR-1999-SUPREME-COURT-OF-ELECTIONS")
        self.assertEqual(with_vector[0]["matched_by"], ["vector", "year"])
        self.assertEqual(with_vector[0]["score"], cl.VECTOR_WEIGHT + cl.YEAR_WEIGHT)
        self.assertNotIn("text", [c[0] for c in session.calls])       # with a vector, the words are left out
        both = cl.find_issues(session, question, question_vector=[0.1, 0.2], use_text=True)
        self.assertIn("text", both[1]["matched_by"])

    def test_the_short_vector_lifts_the_issue_the_question_names(self):
        # the long vector puts a commemorative first, because its catalogue text tells the older issue's story
        long_rows = [{"issue_id": "CR-1963-CENTENARY", "title": "Centenary of the first stamp", "issue_dates": "{}", "score": 0.70},
                     {"issue_id": "CR-1950-FAIR", "title": "Fair issue", "issue_dates": "{}", "score": 0.66},
                     {"issue_id": "CR-1863-FIRST", "title": "First issue", "issue_dates": "{}", "score": 0.60}]
        short_rows = [{"issue_id": "CR-1863-FIRST", "title": "First issue", "issue_dates": "{}", "score": 0.80},
                      {"issue_id": "CR-1963-CENTENARY", "title": "Centenary of the first stamp", "issue_dates": "{}", "score": 0.62},
                      {"issue_id": "CR-1901-OTHER", "title": "Another issue", "issue_dates": "{}", "score": 0.50}]
        session = FakeSession(by_vector=long_rows, by_short=short_rows)
        today = cl.find_issues(session, "what was the first stamp?", question_vector=[0.1])
        self.assertEqual(today[0]["issue_id"], "CR-1963-CENTENARY")
        self.assertNotIn("short", [c[0] for c in session.calls])        # not asked unless the caller says so
        both = cl.find_issues(session, "what was the first stamp?", question_vector=[0.1], use_short=True)
        self.assertEqual([h["issue_id"] for h in both], ["CR-1963-CENTENARY", "CR-1863-FIRST", "CR-1950-FAIR"])
        self.assertEqual(both[1]["matched_by"], ["vector", "title"])
        self.assertEqual(both[1]["score"], cl.SHORT_VECTOR_WEIGHT)       # last of the long hits, first of the short ones
        self.assertAlmostEqual(both[0]["score"], cl.VECTOR_WEIGHT + cl.SHORT_VECTOR_WEIGHT * 0.4)

    def test_the_short_vector_needs_the_question_vector(self):
        session = FakeSession(by_short=[{"issue_id": "CR-1863-FIRST", "title": "First issue", "issue_dates": "{}", "score": 0.8}])
        self.assertEqual(cl.find_issues(session, "what is it?", use_short=True), [])
        self.assertEqual(session.calls, [])

    def test_no_signal_returns_nothing_and_asks_nothing(self):
        session = FakeSession()
        self.assertEqual(cl.find_issues(session, "what is it?"), [])
        self.assertEqual(session.calls, [])


class CardSession:
    """Answers the card query with one made-up record."""

    def __init__(self, record):
        self.record = record

    def run(self, query, **params):
        assert "HAS_STAMP" in query and params["issue_id"] == self.record["issue_id"]
        return type("Result", (), {"single": lambda _self: dict(self.record)})()


def card_record(issue_id, stamps):
    return {"issue_id": issue_id, "title": "A made-up issue", "section": None, "issue_dates": "{}", "perforation": None,
            "printers": [], "acts": [], "stamps": [{"varieties": [], "scott": [], "color": None, "quantity": None,
                                                    "perforation": None, "status": None, **s} for s in stamps]}


class Denomination(unittest.TestCase):
    def test_mena_1a_of_the_first_issue_is_the_half_real_on_the_card_and_no_other_value_changes(self):
        stamps = [{"catalog_no": "1A", "value": 1.5, "unit": "real"}, {"catalog_no": "2", "value": 2, "unit": "reales"}]
        card = cl.issue_card(CardSession(card_record(cl.FIRST_ISSUE_ID, stamps)), cl.FIRST_ISSUE_ID)
        self.assertEqual([(s["catalog_no"], s["value"], s["unit"]) for s in card["stamps"]],
                         [("1A", 0.5, "real"), ("2", 2, "reales")])

    def test_a_stamp_numbered_1a_of_another_issue_keeps_its_value(self):
        stamps = [{"catalog_no": "1A", "value": 1.5, "unit": "made-up unit"}]
        card = cl.issue_card(CardSession(card_record("CR-1999-MADE-UP", stamps)), "CR-1999-MADE-UP")
        self.assertEqual((card["stamps"][0]["value"], card["stamps"][0]["unit"]), (1.5, "made-up unit"))

    def test_the_first_issue_is_the_one_the_explorer_shows(self):
        from oxcart import config

        self.assertEqual(cl.FIRST_ISSUE_ID, config.ISSUE_ID)


if __name__ == "__main__":
    unittest.main()
