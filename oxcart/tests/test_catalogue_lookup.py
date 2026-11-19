"""Tests for catalogue_lookup's question reading and query building. No database.

    python -m unittest discover -s oxcart/tests -p "test_catalogue_lookup.py"
"""

import unittest

from oxcart import catalogue_lookup as cl


class FakeSession:
    """Answers the lookup's four queries from small tables."""

    def __init__(self, by_mena=(), by_scott=(), by_text=(), by_year=(), by_vector=()):
        self.tables = {"mena": by_mena, "scott": by_scott, "text": by_text, "year": by_year, "vector": by_vector}
        self.calls = []

    def run(self, query, **params):
        for name, marker in (("mena", "toUpper(s.catalog_no)"), ("scott", "toUpper(sc.scott_number)"),
                             ("text", "issue_text_idx"), ("vector", "issue_vec_idx"),
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

    def test_no_signal_returns_nothing_and_asks_nothing(self):
        session = FakeSession()
        self.assertEqual(cl.find_issues(session, "what is it?"), [])
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
