"""Unit tests for :mod:`figure_refs` (no Neo4j / no LLM / no network).

The project has no pytest harness — run this file directly with the project venv::

    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\tests\\test_figure_refs.py

It is also pytest-compatible if pytest is installed. The module under test only
reads ``config.FIGURES_DIR``; the tests point that at a temporary directory of
dummy ``.png`` files, so they run fully offline.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Bootstrap: add the package dir (parent of tests/) so `import figure_refs`
# works standalone, exactly as test_sanitize.py does for `import sanitize_chunks`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import figure_refs  # noqa: E402

_FIGURE_NAMES = [
    "OXCART05_page_017_figure_000.png",
    "OXCART05_page_017_figure_002.png",
    "OXCART05_page_042_figure_002.png",
    "OXCART03_page_036_figure_001.png",
    "CRF 05_page_006_figure_006.jpg",  # doc_id with a space, alt extension
    "not_a_figure_file.png",  # must be ignored (no _page_/_figure_ structure)
]


class FigureRefsTest(unittest.TestCase):
    def setUp(self) -> None:
        """Create a temp figures dir of empty files and point config + cache at it."""
        self._tmp = tempfile.TemporaryDirectory()
        d = Path(self._tmp.name) / "figures"
        d.mkdir()
        for name in _FIGURE_NAMES:
            (d / name).write_bytes(b"")
        self._orig_dir = config.FIGURES_DIR
        config.FIGURES_DIR = d
        figure_refs.reset_cache()

    def tearDown(self) -> None:
        config.FIGURES_DIR = self._orig_dir
        figure_refs.reset_cache()
        self._tmp.cleanup()

    # ----- figures_for_page ------------------------------------------------ #
    def test_figures_for_page_matches_doc_and_page(self) -> None:
        self.assertEqual(
            figure_refs.figures_for_page("OXCART05", 17),
            ("OXCART05_page_017_figure_000.png", "OXCART05_page_017_figure_002.png"),
        )

    def test_figures_for_page_string_page_and_doc_with_space(self) -> None:
        self.assertEqual(
            figure_refs.figures_for_page("OXCART05", "42"),
            ("OXCART05_page_042_figure_002.png",),
        )
        self.assertEqual(
            figure_refs.figures_for_page("CRF 05", 6),
            ("CRF 05_page_006_figure_006.jpg",),
        )

    def test_figures_for_page_unknown_returns_empty(self) -> None:
        self.assertEqual(figure_refs.figures_for_page("OXCART05", 999), ())
        self.assertEqual(figure_refs.figures_for_page("OXCART05", None), ())
        self.assertEqual(figure_refs.figures_for_page(None, 17), ())

    # ----- figure_url ------------------------------------------------------ #
    def test_figure_url_encodes_spaces(self) -> None:
        self.assertEqual(
            figure_refs.figure_url("OXCART05_page_017_figure_000.png"),
            "/api/figures/OXCART05_page_017_figure_000.png",
        )
        self.assertEqual(
            figure_refs.figure_url("CRF 05_page_006_figure_006.jpg"),
            "/api/figures/CRF%2005_page_006_figure_006.jpg",
        )

    # ----- figures_for_query ----------------------------------------------- #
    def test_figures_for_query_orders_dedupes_and_caps(self) -> None:
        lexical = [
            {"chunk_id": "c1", "doc_id": "OXCART05", "page": 17, "link_score": 9.0, "score": 5.0},
            {"chunk_id": "c2", "doc_id": "OXCART05", "page": 17, "link_score": 8.0},  # dup page
            {"chunk_id": "c3", "doc_id": "OXCART03", "page": 36, "link_score": 7.0},
        ]
        figs = figure_refs.figures_for_query(lexical, max_figures=10)
        self.assertEqual(
            [f["filename"] for f in figs],
            [
                "OXCART05_page_017_figure_000.png",
                "OXCART05_page_017_figure_002.png",
                "OXCART03_page_036_figure_001.png",
            ],
        )
        first = figs[0]
        self.assertEqual(first["doc_id"], "OXCART05")
        self.assertEqual(first["page"], 17)
        self.assertEqual(first["url"], "/api/figures/OXCART05_page_017_figure_000.png")
        self.assertEqual(first["chunk_id"], "c1")
        self.assertEqual(first["link_score"], 9.0)
        self.assertEqual(first["score"], 5.0)
        self.assertEqual(len(figure_refs.figures_for_query(lexical, max_figures=2)), 2)

    def test_figures_for_query_skips_bad_pages(self) -> None:
        lexical = [
            {"chunk_id": "c1", "doc_id": "OXCART05", "page": None},
            {"chunk_id": "c2", "doc_id": "OXCART05", "page": 999},
            {"chunk_id": "c3", "doc_id": "OXCART03", "page": 36, "link_score": 7.0},
        ]
        figs = figure_refs.figures_for_query(lexical, max_figures=10)
        self.assertEqual([f["filename"] for f in figs], ["OXCART03_page_036_figure_001.png"])

    def test_figures_for_query_min_link_gate(self) -> None:
        lexical = [
            {"chunk_id": "c1", "doc_id": "OXCART05", "page": 17, "link_score": 3.0},
            {"chunk_id": "c2", "doc_id": "OXCART03", "page": 36, "link_score": 8.0},
        ]
        figs = figure_refs.figures_for_query(lexical, max_figures=10, min_link_score=6.0)
        self.assertEqual([f["doc_id"] for f in figs], ["OXCART03"])

    def test_figures_for_query_empty_input(self) -> None:
        self.assertEqual(figure_refs.figures_for_query([], max_figures=10), [])
        self.assertEqual(figure_refs.figures_for_query(None, max_figures=10), [])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
