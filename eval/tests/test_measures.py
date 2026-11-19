"""Tests for eval/measures.py. Standard library only.

    python -m unittest discover -s eval/tests -t .
"""

import math
import unittest

from eval import measures as m

GOLD = [
    {"doc_id": "A", "pages": [12, 13], "grade": 2},
    {"doc_id": "B", "pages": [4], "grade": 1},
]


def r(doc, page):
    return {"doc_id": doc, "page": page}


class Match(unittest.TestCase):
    def test_document_and_page_must_both_match(self):
        self.assertEqual(m.match(r("A", 13), GOLD), 0)
        self.assertEqual(m.match(r("B", 4), GOLD), 1)
        self.assertIsNone(m.match(r("A", 14), GOLD))
        self.assertIsNone(m.match(r("C", 12), GOLD))

    def test_a_gold_source_without_pages_accepts_any_page(self):
        self.assertEqual(m.match(r("A", 99), [{"doc_id": "A", "grade": 1}]), 0)


class Ranking(unittest.TestCase):
    results = [r("X", 1), r("A", 12), r("A", 12), r("B", 4), r("A", 13)]

    def test_hit_at(self):
        self.assertEqual(m.hit_at(self.results, GOLD, 1), 0.0)
        self.assertEqual(m.hit_at(self.results, GOLD, 2), 1.0)

    def test_answer_at_needs_a_page_graded_two(self):
        self.assertEqual(m.answer_at([r("B", 4)], GOLD, 5), 0.0)      # B is a supporting page only
        self.assertEqual(m.answer_at([r("B", 4), r("A", 13)], GOLD, 5), 1.0)
        self.assertEqual(m.answer_at([r("B", 4), r("A", 13)], GOLD, 1), 0.0)
        self.assertEqual(m.answer_at([r("B", 4)], [{"doc_id": "B", "pages": [4], "grade": 1}], 5), 0.0)

    def test_recall_counts_gold_sources_not_passages(self):
        self.assertEqual(m.recall_at(self.results, GOLD, 3), 0.5)  # A twice is still one source
        self.assertEqual(m.recall_at(self.results, GOLD, 4), 1.0)
        self.assertEqual(m.recall_at(self.results, [], 4), 0.0)

    def test_mrr(self):
        self.assertEqual(m.mrr_at(self.results, GOLD, 10), 0.5)
        self.assertEqual(m.mrr_at([r("X", 1)], GOLD, 10), 0.0)
        self.assertEqual(m.mrr_at(self.results, GOLD, 1), 0.0)

    def test_ndcg_counts_a_source_once_and_uses_the_grades(self):
        got = m.ndcg_at(self.results, GOLD, 10)
        dcg = 3 / math.log2(3) + 1 / math.log2(5)   # A at rank 2 (grade 2), B at rank 4 (grade 1)
        idcg = 3 / math.log2(2) + 1 / math.log2(3)
        self.assertAlmostEqual(got, dcg / idcg)
        self.assertAlmostEqual(m.ndcg_at([r("A", 12), r("B", 4)], GOLD, 10), 1.0)
        self.assertEqual(m.ndcg_at([r("X", 1)], GOLD, 10), 0.0)

    def test_first_hit_rank_and_distinct_pages(self):
        self.assertEqual(m.first_hit_rank(self.results, GOLD), 2)
        self.assertIsNone(m.first_hit_rank([r("X", 1)], GOLD))
        self.assertEqual(m.distinct_pages(self.results, 3), 2)


class Uncertainty(unittest.TestCase):
    def test_percentile(self):
        self.assertEqual(m.percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5), 3.0)
        self.assertAlmostEqual(m.percentile([1.0, 2.0], 0.5), 1.5)

    def test_bootstrap_mean_brackets_the_mean_and_is_repeatable(self):
        values = [0.0, 1.0] * 20
        a, b = m.bootstrap_mean(values), m.bootstrap_mean(values)
        self.assertEqual(a, b)
        self.assertEqual(a["mean"], 0.5)
        self.assertLess(a["lo"], 0.5)
        self.assertGreater(a["hi"], 0.5)

    def test_constant_values_give_a_zero_width_interval(self):
        out = m.bootstrap_mean([1.0] * 10)
        self.assertEqual((out["lo"], out["hi"]), (1.0, 1.0))

    def test_paired_difference(self):
        a = [1.0, 1.0, 0.0, 1.0]
        b = [1.0, 0.0, 0.0, 1.0]
        out = m.paired_difference(a, b)
        self.assertEqual((out["better"], out["worse"]), (1, 0))
        self.assertAlmostEqual(out["mean"], 0.25)
        self.assertTrue(out["includes_zero"])
        with self.assertRaises(ValueError):
            m.paired_difference([1.0], [1.0, 0.0])

    def test_latency_summary(self):
        out = m.latency_summary([0.3, 0.1, 0.2])
        self.assertEqual((out["n"], out["p50"]), (3, 0.2))


if __name__ == "__main__":
    unittest.main()
