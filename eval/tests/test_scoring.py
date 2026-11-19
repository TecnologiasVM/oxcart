"""Tests for eval/scoring.py and eval/judgments.py. Standard library only."""

import unittest

from eval import judgments, scoring, split


def hit(doc, page, score=1.0):
    return {"doc_id": doc, "page": page, "score": score}


QUESTIONS = [
    {"id": "lit-1-en", "lang": "en", "type": "literature", "gold": {"sources": [{"doc_id": "A", "pages": [3], "grade": 2}]}},
    {"id": "lit-2-es", "lang": "es", "type": "literature", "gold": {"sources": [{"doc_id": "B", "pages": [7, 8], "grade": 1}]}},
    {"id": "oos-1", "lang": "en", "type": "out_of_scope", "category": "not_stamps"},
]
RESULTS = {
    "lit-1-en": {"keyword": {"seconds": 0.01, "hits": [hit("A", 3, 9.0), hit("A", 3, 8.0), hit("X", 1, 7.0)]},
                 "vector": {"seconds": 0.02, "hits": [hit("X", 1, 0.6), hit("A", 3, 0.5)]}},
    "lit-2-es": {"keyword": {"seconds": 0.03, "hits": [hit("X", 1, 5.0)]},
                 "vector": {"seconds": 0.02, "hits": [hit("B", 8, 0.7)]}},
    "oos-1": {"keyword": {"seconds": 0.01, "hits": [hit("X", 1, 6.0)]},
              "vector": {"seconds": 0.01, "hits": [hit("X", 2, 0.2)]}},
}


class Score(unittest.TestCase):
    def test_only_questions_with_gold_are_scored(self):
        out = scoring.score(QUESTIONS, RESULTS)
        self.assertEqual(out["n"], 2)
        self.assertEqual(out["arms"]["keyword"]["measures"]["hit@5"]["mean"], 0.5)
        self.assertEqual(out["arms"]["vector"]["measures"]["hit@5"]["mean"], 1.0)
        self.assertEqual(out["arms"]["keyword"]["by_lang"], {"en": out["arms"]["keyword"]["by_lang"]["en"],
                                                             "es": out["arms"]["keyword"]["by_lang"]["es"]})
        self.assertEqual(out["arms"]["keyword"]["by_lang"]["es"]["hit@5"], 0.0)
        # lit-2-es has only a supporting page (grade 1): the vector arm finds it, but nothing answers
        self.assertEqual(out["arms"]["vector"]["measures"]["answer@5"]["mean"], 0.5)
        self.assertEqual(out["arms"]["keyword"]["distinct_pages_in_top5"], 1.5)   # (2 + 1) / 2

    def test_paired_difference_against_the_baseline_arm(self):
        out = scoring.score(QUESTIONS, RESULTS)
        diff = out["arms"]["vector"]["vs_keyword"]["answer@5"]
        self.assertEqual((diff["better"], diff["worse"]), (0, 0))
        self.assertNotIn("vs_keyword", out["arms"]["keyword"])

    def test_top_scores_separation(self):
        tops = scoring.top_scores(QUESTIONS, RESULTS)
        self.assertEqual(tops["keyword"]["groups"]["not_stamps"]["median"], 6.0)
        self.assertEqual(tops["keyword"]["separation"]["not_stamps"], 0.5)   # 9 beats 6, 5 does not
        self.assertEqual(tops["vector"]["separation"]["not_stamps"], 1.0)


class Judgments(unittest.TestCase):
    def test_gold_sources_group_pages_by_document_and_grade(self):
        pages = [{"doc_id": "A", "page": 3, "grade": 2}, {"doc_id": "A", "page": 4, "grade": 2},
                 {"doc_id": "A", "page": 9, "grade": 1}, {"doc_id": "B", "page": 1, "grade": 0}]
        self.assertEqual(judgments.gold_sources(pages), [
            {"doc_id": "A", "pages": [3, 4], "grade": 2}, {"doc_id": "A", "pages": [9], "grade": 1}])

    def test_pages_typed_by_the_reviewer_count_as_answers(self):
        got = judgments.gold_sources([], "OXCART 44, 15\nRepertorio Filatelico 23; p. 3\nnot a page line")
        self.assertEqual(got, [{"doc_id": "OXCART 44", "pages": [15], "grade": 2},
                               {"doc_id": "Repertorio Filatelico 23", "pages": [3], "grade": 2}])


    def test_files_are_merged_page_by_page(self):
        import json
        import tempfile
        from pathlib import Path

        first = {"reviewer": "judge A", "exported": "2026-11-18T10:00:00", "questions": [
            {"id": "lit-1", "lang": "en", "status": "keep", "question": "Q?", "answer": "A.",
             "pages": [{"doc_id": "D", "page": 1, "grade": 2}, {"doc_id": "D", "page": 2, "grade": 0}]}]}
        second = {"reviewer": "judge A", "exported": "2026-11-19T10:00:00", "questions": [
            {"id": "lit-1", "lang": "en", "status": "drop", "question": "Q?", "answer": "from the extra pages", "pages_only": True,
             "pages": [{"doc_id": "E", "page": 9, "grade": 1}, {"doc_id": "D", "page": 2, "grade": 2}]}]}
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for n, data in enumerate((first, second)):
                paths.append(Path(d) / f"{n}.json")
                paths[-1].write_text(json.dumps(data))
            questions, notes = judgments.convert(paths)
        self.assertEqual(notes, [])
        q = questions[0]
        self.assertEqual(q["gold"]["sources"], [{"doc_id": "D", "pages": [1, 2], "grade": 2},
                                                {"doc_id": "E", "pages": [9], "grade": 1}])
        self.assertEqual((q["gold"]["answer"], q["judged_by"], q["pages_judged"]), ("A.", "judge A", 3))


class Split(unittest.TestCase):
    def test_pairs_stay_together_and_the_split_is_repeatable(self):
        qs = [{"id": f"lit-{n:03d}-{lang}", "pair": f"lit-{n:03d}", "lang": lang, "type": "literature"}
              for n in range(20) for lang in ("en", "es")]
        a, b = split.assign(qs), split.assign(list(reversed(qs)))
        self.assertEqual(a, b)
        for n in range(20):
            self.assertEqual(a[f"lit-{n:03d}-en"], a[f"lit-{n:03d}-es"])
        self.assertEqual(sum(1 for v in a.values() if v == "dev"), 24)   # 12 of 20 pairs



class Agreement(unittest.TestCase):
    def test_kappa_and_counts(self):
        from eval import agreement

        a = {"q1": {"p0": 2, "p1": 0, "p2": 1}, "q2": {"p0": 0, "p1": 0}}
        b = {"q1": {"p0": 2, "p1": 0, "p2": 0}, "q2": {"p0": 0, "p1": 2}, "q3": {"p0": 1}}
        out = agreement.compare(a, b)
        self.assertEqual((out["questions"], out["pages"]), (2, 5))
        self.assertEqual(out["same_grade"], 0.6)
        self.assertEqual(out["same_helps_or_not"], 0.6)
        self.assertEqual(out["off_by_two"], 1)
        self.assertEqual(out["questions_agree_on_an_answering_page"], 1)
        self.assertEqual(agreement.kappa([(0, 0), (1, 1), (2, 2)]), 1.0)
        self.assertAlmostEqual(agreement.kappa([(0, 0), (0, 1), (1, 0), (1, 1)]), 0.0)


if __name__ == "__main__":
    unittest.main()
