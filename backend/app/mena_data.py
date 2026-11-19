"""File-backed Mena<->Scott match data (load-once, degrade-to-empty).

This module loads two read-only artifacts produced by the cross-catalogue
matcher and caches them as module-level singletons at import time:

* ``results/match_catalogues/mena_match_results_{1-100,101-200,201-300}.json``
  -- dict keyed by ``issue_id`` -> ``{issue_id, equivalences:[{mena,scott,confidence}]}``.
  Merged into ``_MATCH_INDEX: {issue_id -> [equivalence, ...]}``.
* ``results/parsed_catalogues/scott_parse_results_ALL.json`` -- a list of
  stamp-group dicts; every ``group["stamps"][]`` row is flattened into
  ``_SCOTT_INDEX: {scott_number -> stamp_detail}`` (first occurrence wins).

Contracts:
* READ-ONLY. No file is written. No DB. No LLM.
* MUST NOT raise at import when a file is missing -> the loaders degrade to an
  empty index so the app still boots and ``/api/health`` stays green.
* ``confidence`` is a categorical STRING ("high"/"medium") -- it is kept as-is
  and NEVER coerced to a number.
* Values returned are plain JSON scalars (safe to merge into a sanitized
  payload); the service still re-sanitizes defensively.

Paths resolve off ``config.RESULTS_DIR`` (== repo-root ``results/``); no absolute
literals. Encoding is always UTF-8.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

# Importing settings first bootstraps sys.path so ``import config`` resolves to
# the prototype's config module (same pattern as graph_service / deps).
from app import settings  # noqa: F401  (side effect: sys.path bootstrap)

import config

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
_MATCH_DIR: Path = config.RESULTS_DIR / "match_catalogues"
_MATCH_FILES: tuple[str, ...] = (
    "mena_match_results_1-100.json",
    "mena_match_results_101-200.json",
    "mena_match_results_201-300.json",
)
_SCOTT_PARSE_PATH: Path = config.RESULTS_DIR / "parsed_catalogues" / "scott_parse_results_ALL.json"

# Scott stamp-detail fields kept (clean, display-friendly). Mojibake (e.g. the
# half-real glyph) is left untouched -- the matcher is the source of truth.
_SCOTT_DETAIL_KEYS: tuple[str, ...] = (
    "scott_number",
    "denomination",
    "color",
    "mint_value",
    "used_value",
    "description",
    "variety_of",
    "perforation",
    "illustration",
)


# --------------------------------------------------------------------------- #
# Loaders (degrade to empty; warn once if a present file yields nothing)
# --------------------------------------------------------------------------- #
def _load_json(path: Path) -> Any:
    """Read+parse a UTF-8 JSON file. Returns None on any failure (never raises)."""
    try:
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:  # missing / unreadable / malformed
        logger.warning("could not load %s: %s: %s", path.name, type(exc).__name__, exc)
        return None


def _load_match_index() -> dict[str, list[dict[str, Any]]]:
    """Merge the 3 match shards into ``{issue_id -> [equivalence, ...]}``.

    Each equivalence is normalized to ``{mena, scott, confidence}`` with string
    values (``confidence`` kept verbatim). A shard that exists but parses to zero
    equivalences is logged (a key-name drift smell), per the design review.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for name in _MATCH_FILES:
        path = _MATCH_DIR / name
        data = _load_json(path)
        if data is None:
            continue  # absent shard -> skip silently (degrade-to-empty)
        if not isinstance(data, dict):
            logger.warning("%s: unexpected top-level type %s; skipped", name, type(data).__name__)
            continue
        added = 0
        for issue_id, payload in data.items():
            if not isinstance(payload, dict):
                continue
            equivalences = payload.get("equivalences") or []
            rows: list[dict[str, Any]] = []
            for eq in equivalences:
                if not isinstance(eq, dict):
                    continue
                rows.append(
                    {
                        "mena": _as_str(eq.get("mena")),
                        "scott": _as_str(eq.get("scott")),
                        "confidence": _as_str(eq.get("confidence")),
                    }
                )
            if rows:
                index[str(issue_id)] = rows
                added += len(rows)
        if added == 0:
            # File present but yielded nothing -> likely a field-name drift.
            logger.warning("%s present but produced 0 equivalences (schema drift?)", name)
    return index


def _load_scott_index() -> dict[str, dict[str, Any]]:
    """Flatten ``scott_parse_results_ALL.json`` into ``{scott_number -> detail}``."""
    data = _load_json(_SCOTT_PARSE_PATH)
    if data is None:
        return {}
    groups = data if isinstance(data, list) else [data]
    index: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        for stamp in group.get("stamps") or []:
            if not isinstance(stamp, dict):
                continue
            scott_number = stamp.get("scott_number")
            if scott_number is None:
                continue
            key = str(scott_number)
            if key in index:  # first occurrence wins
                continue
            index[key] = {k: stamp.get(k) for k in _SCOTT_DETAIL_KEYS if stamp.get(k) is not None}
    if isinstance(data, list) and data and not index:
        logger.warning("scott_parse_results_ALL.json present but produced 0 stamps (schema drift?)")
    return index


def _as_str(value: Any) -> Optional[str]:
    """Coerce a scalar to ``str`` (preserving None)."""
    if value is None:
        return None
    return str(value)


# --------------------------------------------------------------------------- #
# Module-level caches (built once at import; immutable after)
# --------------------------------------------------------------------------- #
_MATCH_INDEX: dict[str, list[dict[str, Any]]] = _load_match_index()
_SCOTT_INDEX: dict[str, dict[str, Any]] = _load_scott_index()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def scott_detail(scott_number: Any) -> Optional[dict[str, Any]]:
    """Return the Scott catalogue detail for ``scott_number`` (None if unknown)."""
    if scott_number is None:
        return None
    detail = _SCOTT_INDEX.get(str(scott_number))
    return dict(detail) if detail else None


def scott_match_for(issue_id: str) -> list[dict[str, Any]]:
    """Return Mena->Scott equivalences for ``issue_id``, enriched with Scott detail.

    Each row is ``{mena, scott, confidence, scott_detail}``. Returns ``[]`` for an
    issue with no recorded match (the common case beyond the matched ~299 issues).
    """
    rows = _MATCH_INDEX.get(str(issue_id)) or []
    return [{**row, "scott_detail": scott_detail(row.get("scott"))} for row in rows]


def match_stats() -> dict[str, int]:
    """Non-secret cache sizes for health/diagnostics and tests."""
    return {"issues_with_match": len(_MATCH_INDEX), "scott_entries": len(_SCOTT_INDEX)}
