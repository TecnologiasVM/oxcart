"""
Regression tests for chunk sanitization (the de-hallucination crux).

This exercises ``sanitize_chunks.sanitize_doc`` against the REAL
``results/final_jsons/OXCART03_final.json`` and asserts that the patched output
(a) matches the PATCHED CHUNK JSON SHAPE, (b) drops the hallucinated philatelic
metadata (entities/topics/quality_score), (c) preserves clean article text such
as the masthead/subscription chunk, (d) reports internally-consistent summary
counts, (e) carries a list-typed ``clean_meta`` on every chunk, and (f) recovers
at least one real first-issue year into ``clean_meta.years``.

Run directly (no pytest harness required):
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\tests\\test_sanitize.py
Also pytest-compatible.

If OXCART03 source data is unavailable the test SKIPs gracefully (prints SKIP and
returns success) rather than failing — the data file is a precondition, not a
behavior under test.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

# Bootstrap: add the package dir (parent of tests/) so `import sanitize_chunks`
# works standalone, exactly as test_lexicon.py does for `import lexicon`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sanitize_chunks as sc  # noqa: E402

DOC_ID = "OXCART03"

# Top-level keys required by the PATCHED CHUNK JSON SHAPE.
EXPECTED_TOP_KEYS = {"doc_id", "source_markdown", "chunk_count", "summary", "chunks"}
EXPECTED_SUMMARY_KEYS = {"total", "kept", "dropped_caption", "figure_noise_stripped"}
EXPECTED_CHUNK_KEYS = {
    "chunk_id",
    "chunk_type",
    "text",
    "page",
    "reading_order",
    "clean_meta",
    "removed",
}
EXPECTED_CLEAN_META_KEYS = {"years", "denominations", "colors", "catalog_refs"}

# Hallucinated metadata that MUST NOT survive on any chunk (flat or nested).
BANNED_CHUNK_KEYS = {"entities", "topics", "quality_score"}

# A stable, clean fragment of the OXCART03 masthead/subscription chunk. This
# text is legitimate article content and must be preserved after sanitization.
MASTHEAD_FRAGMENT = "Published quarterly at San Francisco"


def _check(name: str, cond: bool) -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    return cond


def _source_available() -> bool:
    """True only if the real OXCART03 final JSON is present on disk."""
    try:
        from config import FINAL_JSONS_DIR  # local import keeps skip path cheap
    except Exception:
        return False
    return (FINAL_JSONS_DIR / f"{DOC_ID}_final.json").is_file()


def _contamination_keys(obj: Any) -> list[str]:
    """Recursively collect any banned hallucinated-metadata keys found in ``obj``."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in BANNED_CHUNK_KEYS:
                found.append(key)
            found.extend(_contamination_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_contamination_keys(item))
    return found


def run() -> int:
    if not _source_available():
        print("test_sanitize")
        print(f"  [SKIP] {DOC_ID}_final.json not found — skipping sanitize regression")
        return 0

    failures = 0

    print("test_sanitize_doc_returns_patched_shape")
    patched: Dict[str, Any] = sc.sanitize_doc(DOC_ID)
    failures += not _check("returns a dict", isinstance(patched, dict))

    # (a) PATCHED CHUNK JSON SHAPE — top-level keys.
    failures += not _check(
        "top-level keys match patched shape",
        EXPECTED_TOP_KEYS.issubset(patched.keys()),
    )
    failures += not _check("doc_id echoes OXCART03", patched.get("doc_id") == DOC_ID)
    failures += not _check(
        "summary keys match patched shape",
        isinstance(patched.get("summary"), dict)
        and EXPECTED_SUMMARY_KEYS.issubset(patched["summary"].keys()),
    )

    chunks = patched.get("chunks")
    failures += not _check("chunks is a non-empty list", isinstance(chunks, list) and bool(chunks))
    chunks = chunks if isinstance(chunks, list) else []

    failures += not _check(
        "every chunk has the patched-shape keys",
        all(isinstance(c, dict) and EXPECTED_CHUNK_KEYS.issubset(c.keys()) for c in chunks),
    )

    print("test_no_chunk_retains_hallucinated_metadata")
    # (b) NO chunk retains entities/topics/quality_score (nested anywhere).
    contaminated = _contamination_keys(chunks)
    failures += not _check(
        "no entities/topics/quality_score anywhere in chunks",
        not contaminated,
    )
    if contaminated:
        print(f"        leaked keys: {sorted(set(contaminated))}")

    print("test_masthead_text_preserved")
    # (c) The masthead/subscription chunk's clean text is preserved.
    failures += not _check(
        "masthead/subscription clean text kept",
        any(MASTHEAD_FRAGMENT in (c.get("text") or "") for c in chunks),
    )

    print("test_summary_counts_internally_consistent")
    # (d) summary counts are internally consistent (kept == len(chunks)).
    summary = patched.get("summary") or {}
    kept = summary.get("kept")
    total = summary.get("total")
    dropped = summary.get("dropped_caption")
    failures += not _check("summary.kept == len(chunks)", kept == len(chunks))
    failures += not _check("chunk_count == len(chunks)", patched.get("chunk_count") == len(chunks))
    failures += not _check(
        "kept + dropped_caption == total (counts reconcile)",
        isinstance(kept, int)
        and isinstance(total, int)
        and isinstance(dropped, int)
        and (kept + dropped == total),
    )

    print("test_clean_meta_present_with_list_fields")
    # (e) clean_meta present on every chunk with list-typed fields.
    def _clean_meta_ok(c: Dict[str, Any]) -> bool:
        meta = c.get("clean_meta")
        if not isinstance(meta, dict) or not EXPECTED_CLEAN_META_KEYS.issubset(meta.keys()):
            return False
        return all(isinstance(meta.get(field), list) for field in EXPECTED_CLEAN_META_KEYS)

    failures += not _check(
        "clean_meta present with list-typed fields on every chunk",
        all(_clean_meta_ok(c) for c in chunks),
    )

    print("test_at_least_one_chunk_has_years")
    # (f) at least one chunk recovered a non-empty years list.
    failures += not _check(
        "at least one chunk has a non-empty clean_meta.years",
        any(
            isinstance(c.get("clean_meta"), dict)
            and isinstance(c["clean_meta"].get("years"), list)
            and len(c["clean_meta"]["years"]) > 0
            for c in chunks
        ),
    )

    print("test_removed_block_shape")
    # Sanity: the per-chunk `removed` provenance block has the patched shape too.
    def _removed_ok(c: Dict[str, Any]) -> bool:
        removed = c.get("removed")
        return (
            isinstance(removed, dict)
            and isinstance(removed.get("bad_metadata_keys"), list)
            and isinstance(removed.get("figure_noise_stripped"), bool)
        )

    failures += not _check("removed block well-formed on every chunk", all(_removed_ok(c) for c in chunks))

    print()
    if failures:
        print(f"RESULT: {failures} check(s) FAILED")
        return 1
    print("RESULT: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
