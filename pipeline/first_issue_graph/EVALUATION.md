# First Issue GraphRAG — Evaluation & Ground-Truth Findings

Prototype goal: validate an **end-to-end GraphRAG for the Costa Rica 1863 First
Issue** — a domain graph (Mena + Scott) joined to a *lexical graph* of journal
chunks that genuinely discuss the issue — with **no direct LLM calls** and
**Weaviate read-only**.

This document records what we measured and what it means. It covers two builds:
the original **OXCART-only** scan and the current **whole-corpus** extension.

## What was built & run

- **Domain layer** added to the existing Neo4j Mena graph (idempotent, namespaced):
  6 `ScottStamp`, 1 `Illustration`, and the 5 `EQUIVALENT_TO` Mena↔Scott links
  supplied (Mena 1/1A/2/3/4 → Scott 1/1a/2/3/4). The Mena domain graph is **not
  modified** (verified: Mena stamps `['1','1A','2','3','4']` intact after every run).
- **Lexical layer** via `coverage_scan.py --all`, now over the **whole corpus**:
  every `results/final_jsons/*_final.json` **except** the 526 Boletín Correos
  bulletins (no first-issue value) and the Mena/Scott catalogs (already in the
  domain graph) = **894 docs**.

## Coverage (whole-corpus scan, current build)

| Metric | Value |
|---|---|
| Docs scanned (894 = corpus − Boletines − catalogs) | **894** |
| Chunks scanned (every chunk of every doc) | **166,338** |
| Docs containing first-issue content | **296** |
| First-issue chunks materialized (prefix-deduped) | **653** |
| Stamp-mention edges (`MENTIONS_STAMP`) | **826** |
| Clean evidence set (`score ≥ 6` AND not `COMPETING`) | **232** |

**The expansion vs the OXCART-only baseline:** 155 → **296 docs** with first-issue
content. The newly-added non-OXCART sources are now the **majority** of the
lexical graph (**170 docs / 431 chunks**), by series:

| Series | docs | chunks |
|---|---|---|
| OXCART studies | 126 | 222 |
| Other monographs (Frajola/Mayer, Nordberg, Castro, Forgeries…) | 31 | 144 |
| CRF (Costa Rica Filatélica) | 49 | 124 |
| Repertorio Filatélico | 53 | 109 |
| Filatelia Costarricense | 10 | 19 |
| The Costa Rica Philatelist | 14 | 15 |
| Timbre | 7 | 14 |
| AFCR Boletín | 6 | 6 |

Per-query effect (`examples_runner.py --demo`, lexical passages roughly doubled):

| Query | source docs (before → after) | lexical passages (before → after) |
|---|---|---|
| Main varieties of the first issue | 75 → **131** | 111 → **232** |
| Plate crack and its positions | 33 → **68** | 40 → **99** |
| 1 peso covers | 31 → **46** | 39 → **60** |
| 4 reales double transfer (pos. 8) | 30 → **49** | 34 → **62** |

## The de-duplication finding (counts were inflated ~6–9×)

The parse layer emits the **same passage at many growing lengths** (nested /
overlapping chunks): e.g. one CRF 06 passage appeared as **29 chunks** from 1,484
to 4,961 chars, all sharing the same head. The original scan deduped by *full
text*, so every nested copy survived — the OXCART-only graph's "1,350 chunks" were
really only a few hundred distinct passages.

`coverage_scan.py` now collapses these by **normalized text prefix (keep-longest)**
and drops heading/byline fragments (`< 140` chars). On the 36-doc validation
sample this took the linked set from **139 → 15 distinct passages** with **no loss
of distinct content**. Each passage is now materialized **once**.

## Spanish-language recall (the corpus is ~70% Spanish)

The lexicon was English-primary; the broader corpus is mostly Spanish journals.
We extended it (still **LLM-free**, regex only) so genuine Spanish first-issue
passages link:

- `primera emisión` / **`primera serie`** (+ OCR variants `emision`/`emission`),
  `primer sello`, `emisión inicial`
- spelled-out denominations (`medio/media real`, `dos/cuatro reales`, `un peso`)
- `Decreto N° 2` (the 1862 authorizing decree), `Banco Americano de Billetes`
- Spanish plate/variety/design vocab (`primera/segunda plancha`, `rotura de la
  plancha`, `sin perforar`, `escudo de armas`, `volcanes`, `papel indio`)

Result: **~298 Spanish-vocab chunks across 126 non-OXCART docs** now link — the
CRF *falsificaciones de la primera serie* articles, the CRF 05 *Decreto*, the Moya
*primera emisión* study, the Timbre O'Neill imperforates study, etc.

## Precision guards (LLM-free, in `lexicon.py`)

The original gates remain (≥2 distinct strong classes; generic-phrase suppression;
≥1 core cue = `1863` / a reales-peso `DENOM` / `ABNCo`). The wider, Spanish-heavy
corpus added three structural **suppressors**, recorded as edge signals:

1. **`FOREIGN`** — other Latin-American classics reuse the exact cues (`primera
   emisión` + escudo + reales). A passage naming another country (Colombia 1859,
   Mexico 1861, Chile…) and **not** Costa Rica is suppressed.
2. **`COMPETING`** (extended) — the **1881-83 surcharge issue** (`U.P.U.`,
   `sobre N reales`), Guanacaste overprints, provisionals, and the existing
   commemorative/air-mail context. Requires the `1863` anchor or a proper-noun
   issue phrase to survive.
3. **`FISCAL`** — revenue stamps can say "primera emisión [de timbres fiscales]"
   and reuse escudo/ABNCo. Fiscal context is suppressed unless the `1863` anchor
   is present.

`tests/test_lexicon.py` = **31 checks** (19 original + 12 new Spanish / foreign /
competing / fiscal regression cases), all passing.

## Ground-truth precision (read the actual linked text)

A 36-doc Spanish-heavy sample (CRF-led, with non-first-issue negative controls)
was dry-run and audited chunk-by-chunk. Findings:

- The headline number from the automated audit (~65%) was **polluted** — the
  judges scored *near-miss* chunks (correctly **not** linked) as false positives.
  On the actual **linked** set, the real error sources were just (a) fiscal
  content in the Timbre revenue journal and (b) the nested-chunk inflation.
- After the fiscal guard + prefix-dedup, the sample is **15 distinct passages at
  ~90% precision**. Representative true positives now include genuine Spanish
  content: CRF 05 *"Apuntes sobre la primera emisión… Decreto N° 2 del 18 de
  agosto de 1862"*, CRF 11 *"falsificaciones de la primera serie de Costa Rica"*,
  CRF 10 Moya *"primera emisión de Costa Rica"*, Timbre14 O'Neill *imperforados*.
- The strong tier (`score ≥ 6`) stays high-precision across the full corpus
  (Frajola/Mayer *Postal History*, Nordberg, Alvaro Castro, the OXCART studies).

## The remaining error source is CHUNKING, not the lexicon

Every surviving false positive traces to **oversized combined chunks** that merge
unrelated paragraphs (and occasionally OCR/boilerplate garbage) into one node, so
`1863` + a denomination co-occur by accident. Prefix-dedup removes the *duplicate*
copies of these, but cannot separate signals that live in different logical
sections glued into one chunk. **Recommended next step:** split the merged chunks
back to paragraph granularity at the parse/sanitize layer
(`combined_chunks` + `reading_order_range` in the source JSON make this feasible),
then re-scan. That lifts the boundary-tier (`score = 4`) precision without
touching the lexicon.

## How to trust the graph today

- Use the **clean evidence set**: `MENTIONS` where `score >= 6 AND NOT 'COMPETING'
  IN signals` (232 chunks). See `cypher_queries.md` #2/#10.
- Treat the `score = 4` tier as *candidate* evidence pending re-chunking.
- Every `MENTIONS` edge stores `signals` explaining *why* it linked — and the
  `COMPETING` / `FOREIGN` / `FISCAL` flags explaining what was guarded — fully
  auditable. See `cypher_queries.md` §14–§17 for the multi-corpus expansion views.

## Verdict

The end-to-end is **validated and extended**: domain (Mena+Scott) + lexical
(chunk→issue/stamp) + combined retrieval work, LLM-free, across the **whole
894-doc corpus** (not just OXCART). The lexical graph nearly **doubled** the
documents with first-issue evidence (155 → 296), captures Spanish content it
previously missed, and is **de-duplicated** so counts reflect distinct passages.
Precision is high in the `score ≥ 6` band; the boundary tier is bounded by chunk
quality, with a clear, actionable fix (re-chunking at the parse layer).
