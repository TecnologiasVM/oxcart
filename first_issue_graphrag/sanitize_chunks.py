"""
Sanitize OXCART ``*_final.json`` chunks into clean patched chunk JSON.

The chunks in ``results/final_jsons/*_final.json`` were contaminated during an
LLM "semantic enrichment" pass. Two distinct kinds of contamination exist:

1. HALLUCINATED STRUCTURED METADATA -- ``metadata.entities`` (condition/prices),
   ``metadata.topics`` (primary/secondary/confidence), and ``metadata.quality_score``
   are synthetic stamp-condition data that never appears in the clean source text.
2. TEXT CONTAMINATION -- chunk ``text`` ends with injected condition/design
   sentences such as ``\\nCondición: centrado fine.`` / ``\\nColores: coffee.`` /
   ``\\nDiseños: café/coffee.`` / ``\\nFechas: 1851.`` (NOTE: in the on-disk JSON
   the line break is a *literal* two-character ``\\n`` sequence, not a real
   newline -- this module strips both forms).
3. FIGURE CAPTION INJECTION -- some chunks are nothing but
   ``![Figure](figures/...png)`` or a short ``Figure 23`` / ``Table 11`` caption.

This module reads each final JSON, strips the contamination deterministically,
re-derives clean philatelic metadata via the LLM-free ``lexicon`` extractors, and
writes the PATCHED CHUNK JSON shape to ``results/oxcarts-patch/<doc>_patched.json``.

NO LLM calls are made here (owner constraint): all enrichment is regex/lexicon.

Run from the repo root with the project venv::

    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\sanitize_chunks.py
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\sanitize_chunks.py --docs OXCART03 OXCART50
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\sanitize_chunks.py --all

Importable API::

    from sanitize_chunks import sanitize_doc, write_patched, iter_patched_chunks
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import config
import lexicon

# --------------------------------------------------------------------------- #
# Curated First-Issue document subset (default for sanitize + downstream).
# These are journal issues with strong first-issue content; final_jsons exist
# for all of them.
# --------------------------------------------------------------------------- #
FIRST_ISSUE_DOCS: List[str] = [
    "OXCART03",
    "OXCART50",
    "OXCART08",
    "OXCART09",
    "OXCART02",
    "OXCART04",
    "OXCART05",
    "OXCART06",
    "OXCART75",
    "OXCART51",
]

# --------------------------------------------------------------------------- #
# Contamination patterns (compiled once)
# --------------------------------------------------------------------------- #
# The injected metadata suffixes attach themselves to chunk text after a line
# break. The on-disk JSON stores line breaks as the literal two characters
# ``\`` + ``n`` (not a real newline), so the separator alternation matches BOTH
# a literal ``\n`` token and a genuine newline. The label list mirrors the
# enrichment vocabulary: Condición / Fechas / Colores / Diseño(s).
_INJECTED_META_RE = re.compile(
    r"(?:\\n|\n)[ \t]*"
    r"(?:Condici[oó]n|Fechas|Colores|Dise[ñn]os|Dise[ñn]o)"
    r"[ \t]*:[^\n]*?(?=(?:\\n|\n)|$)",
    re.IGNORECASE,
)

# Inline markdown figure embeds: ``![Figure](figures/OXCART50_page_001_figure_000.png)``.
_FIGURE_EMBED_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

# Caption-only label heuristic (used together with a short-length test): text
# whose body is just a "Figure 23" / "Table 11 of Rates" style label.
_CAPTION_LABEL_RE = re.compile(
    r"^(?:figure|fig\.?|table|plate|photo|illustration|l[aá]mina|lamina|cuadro)\b",
    re.IGNORECASE,
)

# Metadata keys that are hallucinated artifacts and must be dropped for ALL chunks.
BAD_METADATA_KEYS: List[str] = ["entities", "topics", "quality_score"]

# A figure/caption chunk whose stripped body is shorter than this AND looks like
# a bare figure/table label is treated as pure caption noise and dropped.
_CAPTION_MAX_LEN = 120


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _normalize_for_emptiness(text: str) -> str:
    """Collapse literal ``\\n`` tokens to spaces and trim, for an emptiness test."""
    return (text or "").replace("\\n", " ").strip()


def strip_injected_metadata(text: str) -> str:
    """Remove all injected ``Condición/Fechas/Colores/Diseño(s):`` suffix lines."""
    return _INJECTED_META_RE.sub("", text or "")


def strip_figure_embeds(text: str) -> str:
    """Remove inline ``![Figure](...)`` markdown embeds, keeping any body text."""
    return _FIGURE_EMBED_RE.sub("", text or "")


def has_injected_metadata(text: str) -> bool:
    """True if the text carries any injected condition/design suffix line."""
    return bool(_INJECTED_META_RE.search(text or ""))


def has_figure_embed(text: str) -> bool:
    """True if the text contains an inline ``![Figure](...)`` embed."""
    return bool(_FIGURE_EMBED_RE.search(text or ""))


def clean_text(text: str) -> str:
    """
    Produce the clean chunk text: strip injected metadata suffixes, drop inline
    figure embeds, then tidy whitespace introduced by the removals.
    """
    out = strip_injected_metadata(text or "")
    out = strip_figure_embeds(out)
    # Collapse leftover blank "literal-\n" runs at the head/tail without touching
    # interior content (which legitimately uses literal ``\n`` separators).
    out = re.sub(r"^(?:\s|\\n)+", "", out)
    out = re.sub(r"(?:\s|\\n)+$", "", out)
    # Collapse doubled spaces that a removed embed may have left behind.
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


def is_pure_caption(chunk_type: str, cleaned_text: str) -> bool:
    """
    Decide whether a chunk is PURE caption/figure noise and should be dropped.

    A chunk is pure noise when, after cleaning:
      * it is empty (e.g. was only an ``![Figure](...)`` embed), OR
      * its declared ``chunk_type`` is ``figure``/``caption`` AND the remaining
        body is short and reads as a bare figure/table label (``Figure 23``).

    Substantive bodies mislabeled as ``caption`` (e.g. a full DECREE or a
    PERFORATIONS section) are intentionally KEPT.
    """
    body = _normalize_for_emptiness(cleaned_text)
    if not body:
        return True
    if chunk_type in ("figure", "caption"):
        if len(body) < _CAPTION_MAX_LEN and _CAPTION_LABEL_RE.match(body):
            return True
    return False


def derive_clean_meta(text: str) -> Dict[str, List]:
    """
    Re-derive clean philatelic metadata from the (already cleaned) chunk text
    using the LLM-free ``lexicon`` extractors. Deterministic, no LLM.
    """
    return {
        "years": lexicon.extract_years(text),
        "denominations": lexicon.extract_denominations(text),
        "colors": lexicon.extract_colors(text),
        "catalog_refs": lexicon.extract_catalog_refs(text),
    }


# --------------------------------------------------------------------------- #
# File IO helpers
# --------------------------------------------------------------------------- #
def final_json_path(doc_id: str) -> Path:
    """Path to the source ``<doc>_final.json`` for a doc id."""
    return config.FINAL_JSONS_DIR / f"{doc_id}_final.json"


def patched_json_path(doc_id: str) -> Path:
    """Path to the patched ``<doc>_patched.json`` output for a doc id."""
    return config.PATCH_DIR / f"{doc_id}_patched.json"


def load_final_json(doc_id: str) -> dict:
    """Load and parse the raw ``<doc>_final.json``. Raises if the file is absent."""
    path = final_json_path(doc_id)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _grounding_page(chunk: dict) -> Optional[int]:
    """Derive ``page`` from ``grounding[0].page`` (or None)."""
    grounding = chunk.get("grounding")
    if isinstance(grounding, list) and grounding:
        first = grounding[0]
        if isinstance(first, dict):
            page = first.get("page")
            if isinstance(page, int):
                return page
            if isinstance(page, (str, float)):
                try:
                    return int(page)
                except (TypeError, ValueError):
                    return None
    return None


def _reading_order(chunk: dict) -> Optional[List[int]]:
    """Derive ``reading_order`` from ``metadata.reading_order_range`` (or None)."""
    meta = chunk.get("metadata") or {}
    rng = meta.get("reading_order_range")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        try:
            return [int(rng[0]), int(rng[1])]
        except (TypeError, ValueError):
            return None
    return None


def _removed_bad_keys(chunk: dict) -> List[str]:
    """Names of the hallucinated metadata keys actually present on this chunk."""
    meta = chunk.get("metadata") or {}
    return [k for k in BAD_METADATA_KEYS if k in meta]


# --------------------------------------------------------------------------- #
# Core: per-chunk + per-doc sanitization (pure; no file IO)
# --------------------------------------------------------------------------- #
def sanitize_chunk(chunk: dict) -> Optional[dict]:
    """
    Sanitize a single raw chunk into the patched chunk shape.

    Returns the patched chunk dict, or ``None`` if the chunk is pure caption /
    figure noise and should be dropped.
    """
    chunk_type = chunk.get("chunk_type") or "text"
    raw_text = chunk.get("text") or ""

    noise_stripped = has_injected_metadata(raw_text) or has_figure_embed(raw_text)
    cleaned = clean_text(raw_text)

    if is_pure_caption(chunk_type, cleaned):
        return None  # caller counts this as dropped_caption

    clean_meta = derive_clean_meta(cleaned)

    return {
        "chunk_id": chunk.get("chunk_id"),
        "chunk_type": chunk_type,
        "text": cleaned,
        "page": _grounding_page(chunk),
        "reading_order": _reading_order(chunk),
        "clean_meta": clean_meta,
        "removed": {
            "bad_metadata_keys": _removed_bad_keys(chunk),
            "figure_noise_stripped": bool(noise_stripped),
        },
    }


def sanitize_doc(doc_id: str) -> dict:
    """
    Sanitize an entire document and return the patched doc object (no file IO).

    Output conforms to the PATCHED CHUNK JSON SHAPE from the contract.
    """
    raw = load_final_json(doc_id)
    source = raw.get("source") or raw.get("doc_id") or doc_id

    raw_chunks = raw.get("chunks") or []
    total = len(raw_chunks)
    kept_chunks: List[dict] = []
    dropped_caption = 0
    figure_noise_stripped = 0

    for chunk in raw_chunks:
        patched = sanitize_chunk(chunk)
        if patched is None:
            dropped_caption += 1
            continue
        if patched["removed"]["figure_noise_stripped"]:
            figure_noise_stripped += 1
        kept_chunks.append(patched)

    return {
        "doc_id": raw.get("doc_id") or doc_id,
        "source_markdown": str(source),
        "chunk_count": len(kept_chunks),
        "summary": {
            "total": total,
            "kept": len(kept_chunks),
            "dropped_caption": dropped_caption,
            "figure_noise_stripped": figure_noise_stripped,
        },
        "chunks": kept_chunks,
    }


# --------------------------------------------------------------------------- #
# Public API: write / iterate
# --------------------------------------------------------------------------- #
def write_patched(doc_id: str) -> Path:
    """
    Sanitize ``doc_id`` and write ``<doc>_patched.json`` to ``config.PATCH_DIR``.
    Returns the path written.
    """
    patched = sanitize_doc(doc_id)
    config.PATCH_DIR.mkdir(parents=True, exist_ok=True)
    out_path = patched_json_path(doc_id)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(patched, fh, ensure_ascii=False, indent=2)
    return out_path


def iter_patched_chunks(doc_id: str) -> List[dict]:
    """
    Return the patched chunks for ``doc_id``.

    Reads the existing ``<doc>_patched.json`` if present; otherwise sanitizes on
    the fly (without writing). Useful for downstream linkers/ingesters.
    """
    path = patched_json_path(doc_id)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc.get("chunks") or []
    return sanitize_doc(doc_id).get("chunks") or []


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _discover_all_docs() -> List[str]:
    """All ``OXCART*_final.json`` doc ids under ``config.FINAL_JSONS_DIR``."""
    suffix = "_final.json"
    docs = [
        p.name[: -len(suffix)]
        for p in sorted(config.FINAL_JSONS_DIR.glob("OXCART*_final.json"))
    ]
    return docs


def _process_docs(doc_ids: List[str]) -> List[dict]:
    """
    Sanitize+write each doc, skipping (with a warning) any whose source file is
    missing or unreadable. Returns one summary row dict per successfully written
    doc.
    """
    rows: List[dict] = []
    for doc_id in doc_ids:
        src = final_json_path(doc_id)
        if not src.exists():
            print(f"[warn] skip {doc_id}: missing {src}")
            continue
        try:
            patched = sanitize_doc(doc_id)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] skip {doc_id}: could not read/parse final json ({exc})")
            continue
        out_path = patched_json_path(doc_id)
        config.PATCH_DIR.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(patched, fh, ensure_ascii=False, indent=2)
        summary = patched["summary"]
        rows.append({"doc_id": patched["doc_id"], **summary})
    return rows


def _print_summary_table(rows: List[dict]) -> None:
    """Print a per-doc summary table plus grand totals."""
    header = f"{'doc_id':<14}{'total':>8}{'kept':>8}{'dropped':>9}{'fig_noise':>11}"
    print(header)
    print("-" * len(header))
    totals = {"total": 0, "kept": 0, "dropped_caption": 0, "figure_noise_stripped": 0}
    for row in rows:
        print(
            f"{row['doc_id']:<14}{row['total']:>8}{row['kept']:>8}"
            f"{row['dropped_caption']:>9}{row['figure_noise_stripped']:>11}"
        )
        for key in totals:
            totals[key] += row.get(key, 0)
    print("-" * len(header))
    print(
        f"{'TOTAL':<14}{totals['total']:>8}{totals['kept']:>8}"
        f"{totals['dropped_caption']:>9}{totals['figure_noise_stripped']:>11}"
    )
    print(f"\nWrote {len(rows)} patched file(s) to {config.PATCH_DIR}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize OXCART final_jsons into clean patched chunk JSON.",
    )
    parser.add_argument(
        "--docs",
        nargs="*",
        default=FIRST_ISSUE_DOCS,
        help="Doc ids to process (default: the curated FIRST_ISSUE_DOCS subset).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every results/final_jsons/OXCART*_final.json (overrides --docs).",
    )
    args = parser.parse_args(argv)

    doc_ids = _discover_all_docs() if args.all else list(args.docs)
    if not doc_ids:
        print("[warn] no documents to process.")
        return 0

    rows = _process_docs(doc_ids)
    if not rows:
        print("[warn] no patched files written.")
        return 0

    _print_summary_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
