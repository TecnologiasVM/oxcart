# First Issue GraphRAG — Evaluation & Ground-Truth Findings

Prototype goal: validate an **end-to-end GraphRAG for the Costa Rica 1863 First
Issue** — a domain graph (Mena + Scott) joined to a *lexical graph* of journal
chunks that genuinely discuss the issue — with **no direct LLM calls** and
**Weaviate read-only**.

This document records what we measured and what it means.

## What was built & run

- **Domain layer** added to the existing Neo4j Mena graph (idempotent, namespaced):
  6 `ScottStamp`, 1 `Illustration`, and the 5 `EQUIVALENT_TO` Mena↔Scott links you
  supplied (Mena 1/1A/2/3/4 → Scott 1/1a/2/3/4). The Mena domain graph was **not
  modified** (verified: 819 Issue + 2764 Stamp nodes intact).
- **Lexical layer** via `coverage_scan.py --all` over the **full OXCART collection**
  (258 `OXCART*_final.json` docs — the rest of the 1,424-PDF corpus is non-OXCART).

## Coverage (full collection scan)

| Metric | Value |
|---|---|
| OXCART docs scanned | **258** |
| Chunks scanned (every chunk of every doc) | **57,426** |
| Docs containing first-issue content | **155 (60%)** |
| First-issue chunks materialized (deduped) | **1,350** |
| Stamp-mention edges (`MENTIONS_STAMP`) | **1,646** |
| Weaviate BM25 overlap (independent cross-check) | 28 / top-100 |

Link-strength bands: `score ≥ 6` (solid→very strong) = **661**; `score = 4–5`
(threshold) = ~689; `COMPETING`-flagged = 104.
**Clean evidence set** (`score ≥ 6` AND not `COMPETING`) = **576 chunks**.

## Ground-truth precision (read the actual linked text)

**Strong tier (`score ≥ 6`) — high precision. Representative true positives:**
- `OXCART75 p.8` — *"Observations on the Stamps of the First Issue – Carlos Saenz
  Mata… the first issue of the postage stamps of Costa Rica… minor varieties in
  the plates."*
- `OXCART12 p.37` — *"Notes on First Issue Cancellations, by Dr. Carlos Saenz Mata."*
- `OXCART72 p.11` — *"the basic study on the first issue of Costa Rica by … R. J.
  Mechin and myself … Collectors Club Philatelist, 1948."*
- `OXCART50 p.19` — *"shortly after the stamps of the first issue were placed in
  use, Costa Rica adopted a decimal currency…"*
- `OXCART51 p.24` — *"1863 – ½ real (1), 8 diff. cancels, Pl. I."*

**Boundary tier (`score = 4`) — mixed.** Genuine catalogue/auction listings of
first-issue stamps land here (good), but so do **false positives caused by
oversized "combined" chunks**: a single merged ~3,000-char chunk that spans
unrelated sections where `1863` and a denomination co-occur by accident, e.g.
- `OXCART47` "BACK NUMBERS OF THE OXCART … back issues at $1.00 per number"
- `OXCART61` 1946 die-proof auction lots
- `OXCART04 p.31` 1961 "First Continental Lawyers Conference" decree (now
  auto-flagged `COMPETING`, kept but filterable).

## Precision improvements applied during evaluation (LLM-free, in `lexicon.py`)

The first pass (workflow default) over-linked. Reading the results drove three fixes:

1. **≥2 distinct strong signal classes** required → kills single-cue links
   (a lone "first issue" mention, e.g. OXCART50 "President's Page").
2. **Generic-phrase suppression** → "the first issue *will be known as* …" (a new
   1961 series) no longer counts as the 1863 proper noun; competing/commemorative
   context (`conference`, `commemorating`, `air mail`, …) is detected and flagged.
3. **At least one CORE cue** (`1863` anchor, a reales/peso `DENOM`, or `ABNCo`
   printer) required → kills "name + incidental phrase" links such as OXCART01's
   counterfeit-telegraph article and OXCART209's revenue-stamp overprint.

Net effect on the curated docs: e.g. OXCART50 60→18, OXCART04 92→41 linked chunks
(duplicates + false positives removed). All 19 lexicon regression checks pass,
including the real false positives found here, now pinned as negative tests.

## The remaining error source is CHUNKING, not the lexicon

Every surviving false positive traces to **oversized combined chunks** that merge
unrelated paragraphs. The lexicon cannot separate signals that live in different
logical sections glued into one node. **Recommended next step:** split the merged
chunks back to paragraph granularity at the sanitize/parse layer (the
`combined_chunks` count and `reading_order_range` in the source JSON make this
feasible), then re-scan. That will lift boundary-tier precision without touching
the lexicon.

## How to trust the graph today

- Use the **clean evidence set**: `MENTIONS` where `score >= 6 AND NOT 'COMPETING'
  IN signals` (576 chunks). See `cypher_queries.md` #2/#10.
- Treat the `score = 4` tier as *candidate* evidence pending re-chunking.
- Every `MENTIONS` edge stores `signals` explaining *why* it linked — fully auditable.

## Verdict

The end-to-end is **validated**: domain (Mena+Scott) + lexical (chunk→issue/stamp)
+ combined retrieval work, LLM-free, against the whole OXCART collection. The
lexical graph links to **real** first-issue content at high precision in the
`score ≥ 6` band; the boundary tier is bounded by chunk quality, with a clear,
actionable fix (re-chunking).
