"""Associate retrieved chunks with their page figures (LLM-free, deterministic).

The Dolphin parser cropped every page figure to ``results/markdown/figures/``,
named ``<doc_id>_page_<NNN>_figure_<MMM>.png``. The sanitized chunks that feed
the lexical graph have their inline ``![Figure](figures/...)`` markdown embeds
*stripped* (see ``sanitize_chunks.clean_text``), so figure references cannot be
read back out of chunk ``text``.

Instead we associate figures by **(doc_id, page)**: every figure cropped from a
page that a retrieved chunk grounds to is "related" to the query. The source
chunk's link/relevance score rides along as the figure's confidence, and figures
are returned in the chunk ranking order (best evidence first), de-duplicated by
filename and capped (default 10).

No LLM calls, no network — this only reads the local figures directory. The
directory listing is scanned once and cached for the process.

Public API::

    from figure_refs import figures_for_query
    figs = figures_for_query(bundle["lexical"], max_figures=10)
    # -> [{"filename","doc_id","page","url","chunk_id","link_score","score"}, ...]
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import config

# Supported raster extensions Dolphin emits for figure crops.
_FIGURE_EXT_RE = r"(?:png|jpg|jpeg|webp)"

# ``<doc_id>_page_<page>_figure_<idx>.<ext>`` — doc_id may contain spaces/dots
# (e.g. ``CRF 05``), so capture greedily up to the ``_page_<digits>`` anchor.
_FIGURE_NAME_RE = re.compile(
    rf"^(?P<doc_id>.+)_page_(?P<page>\d+)_figure_(?P<idx>\d+)\.{_FIGURE_EXT_RE}$",
    re.IGNORECASE,
)

# URL prefix the backend serves the figures directory under (StaticFiles mount in
# app.main). The Next.js dev proxy forwards ``/api/*`` to FastAPI, so the browser
# can load ``/api/figures/<file>`` from its own origin.
_FIGURE_URL_PREFIX = "/api/figures"


def _coerce_page(value: Any) -> Optional[int]:
    """Best-effort int coercion for a chunk ``page`` value (int/str/float)."""
    if isinstance(value, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


@lru_cache(maxsize=1)
def _figure_index() -> Dict[Tuple[str, int], Tuple[str, ...]]:
    """Scan the figures dir once -> ``{(doc_id, page): (filename, ...)}``.

    Filenames are sorted within each page so figure order is stable. The result
    is cached for the process; call :func:`reset_cache` after the directory
    changes (only relevant in tests).
    """
    index: Dict[Tuple[str, int], List[str]] = {}
    figures_dir = config.FIGURES_DIR
    if not figures_dir.is_dir():
        return {}
    for entry in sorted(p.name for p in figures_dir.iterdir() if p.is_file()):
        match = _FIGURE_NAME_RE.match(entry)
        if not match:
            continue
        key = (match.group("doc_id"), int(match.group("page")))
        index.setdefault(key, []).append(entry)
    return {key: tuple(names) for key, names in index.items()}


def reset_cache() -> None:
    """Clear the cached figures index (tests that mutate the directory)."""
    _figure_index.cache_clear()


def figures_for_page(doc_id: Optional[str], page: Any) -> Tuple[str, ...]:
    """Return the figure filenames cropped from ``(doc_id, page)`` (or empty)."""
    if not doc_id:
        return ()
    page_int = _coerce_page(page)
    if page_int is None:
        return ()
    return _figure_index().get((str(doc_id), page_int), ())


def figure_url(filename: str) -> str:
    """Build the browser-facing URL for a figure filename (spaces encoded)."""
    from urllib.parse import quote

    return f"{_FIGURE_URL_PREFIX}/{quote(filename)}"


def figures_for_query(
    lexical_hits: List[Dict[str, Any]],
    max_figures: int = 10,
    min_link_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """Collect page figures related to a query from its ranked lexical hits.

    Walks ``lexical_hits`` in their existing rank order (the bundle ranks them by
    fulltext relevance, then link strength), and for each hit grounded to a
    ``(doc_id, page)`` adds that page's figures. Figures are de-duplicated by
    filename (the first, best-ranked occurrence wins) and the list is capped at
    ``max_figures``.

    Parameters
    ----------
    lexical_hits:
        The bundle's ``lexical`` list. Each item needs ``doc_id`` and ``page``;
        ``chunk_id``/``link_score``/``score`` are carried through when present.
    max_figures:
        Hard cap on returned figures (default 10). ``<= 0`` disables the cap.
    min_link_score:
        Skip hits whose ``link_score`` is below this (or missing, when the gate is
        active). The lexical set is already quality-gated upstream, so the default
        (0.0) disables this gate and keeps everything.

    Returns
    -------
    list of dict
        ``{filename, doc_id, page, url, chunk_id, link_score, score}`` ordered by
        source-chunk rank, de-duplicated by filename.
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for hit in lexical_hits or []:
        if not isinstance(hit, dict):
            continue
        link_score = hit.get("link_score")
        # When a gate is active, require a numeric link_score at/above it. A hit
        # with a missing/non-numeric link_score cannot be confirmed to pass, so it
        # is skipped (the default min_link_score=0 disables the gate entirely).
        if min_link_score:
            if not isinstance(link_score, (int, float)) or float(link_score) < min_link_score:
                continue

        doc_id = hit.get("doc_id")
        page_int = _coerce_page(hit.get("page"))
        if page_int is None:
            continue

        for filename in figures_for_page(doc_id, page_int):
            if filename in seen:
                continue
            seen.add(filename)
            out.append(
                {
                    "filename": filename,
                    "doc_id": str(doc_id),
                    "page": page_int,
                    "url": figure_url(filename),
                    "chunk_id": hit.get("chunk_id"),
                    "link_score": (
                        float(link_score) if isinstance(link_score, (int, float)) else None
                    ),
                    "score": (
                        float(hit["score"])
                        if isinstance(hit.get("score"), (int, float))
                        else None
                    ),
                }
            )
            if 0 < max_figures <= len(out):
                return out

    return out
