# First Issue GraphRAG (prototype)

A clean, self-contained prototype that builds an **end-to-end GraphRAG** over the
Costa Rica **1863 First Issue** (`ISSUE_ID = "CR-1863-FIRST-ISSUE"`), and answers
queries by combining a **domain graph** (Mena + Scott), a **lexical chunk graph**
(LLM-free chunk → issue/stamp links), and the existing **Weaviate** literature
corpus.

The prototype lives entirely under `first_issue_graphrag/`. It reads from the
existing Oxcart artifacts (`results/final_jsons`, `results/markdown`) and the
already-populated Neo4j Mena graph + Weaviate `Oxcart` collection, and writes
**only** new, namespaced Neo4j data that can be removed cleanly.

---

## Goal

Demonstrate a retrieval pipeline that is grounded in three complementary layers
and fuses them at query time:

1. **Domain graph (Mena + Scott).** The existing Mena `Issue`/`Stamp`/`Variety`
   graph (already in Neo4j) is extended with a `ScottStamp` layer plus
   user-provided Mena↔Scott equivalences, so a catalog number resolves across
   both systems.
2. **Lexical chunk graph (LLM-free).** Curated journal chunks are sanitized of
   hallucinated metadata, ingested as `Chunk` nodes, and linked to the Issue and
   to specific stamps using the deterministic regex/weighted-signal scorer in
   `lexicon.py` — **no LLM, no embeddings** in our code.
3. **Weaviate corpus (read-only).** The existing `Oxcart` collection
   (192,680 objects) provides free-text evidence via **BM25** (no API key) and,
   when a key is present, Weaviate's own `near_text`/`hybrid` vectorizer.

`retrieve.py` runs all three and returns a fused, citation-friendly result set.

---

## Owner constraints (non-negotiable)

These are hard contracts. The code is built around them; do not relax them.

- **No direct LLM API calls anywhere in our code.** No `openai`/`anthropic`
  client, no `embeddings.create`. The *only* accepted exception is **Weaviate
  using OpenAI under the hood** for its own vectorizer (`near_text`/`hybrid`).
  The default lexical path is **BM25**, which needs no API key.
- **Weaviate is READ-ONLY.** We never create, delete, or update Weaviate
  collections or objects. The collection is `"Oxcart"`. Each object exposes
  `doc_id`, `chunk_id`, `text` (enriched/contaminated), `text_original`
  (CLEAN), `page_number`, and many flattened metadata fields.
- **Neo4j writes are ADDITIVE and NAMESPACED.** Every node and relationship we
  create carries `prototype = config.PROTOTYPE_TAG` (`"first_issue_graphrag"`).
  This lets `teardown.py` delete only our data and never touch the existing
  Mena domain graph.

---

## Architecture

```
                          first_issue_graphrag/  (prototype scope)
 results/final_jsons/                                                       Neo4j  (additive, prototype-tagged)
 ┌───────────────────┐                                                      ┌──────────────────────────────────┐
 │ <DOC>_final.json  │   sanitize_chunks.py     results/oxcarts-patch/      │                                  │
 │  (contaminated:    │  ───────────────────►   ┌────────────────────┐      │  (Document)-[:HAS_CHUNK]->(Chunk) │
 │   phantom condition│   - strip \nCondición/  │ <DOC>_patched.json │ ──┐  │  (Chunk)-[:NEXT]->(Chunk)         │
 │   /color/design,   │     Fechas/Colores/     │  clean text +      │   │  │                                  │
 │   quality_score,   │     Diseños suffixes     │  clean_meta +      │   ├─►│  build_lexical_graph.py          │
 │   topics, prices)  │   - drop caption-only   │  reading_order     │   │  │                                  │
 └───────────────────┘     chunks; clean meta   └────────────────────┘   │  └──────────────────────────────────┘
        (FIRST_ISSUE_DOCS subset, validated against results/markdown/<DOC>.md)
                                                                          │
 data/scott_first_issue.json                                             │     link_lexical_to_domain.py
 data/scott_equivalences.json   build_domain_scott.py                    │   (lexicon.score_chunk per Chunk)
 ┌──────────────────────────┐  ─────────────────────►  (Issue)-[:HAS_SCOTT_STAMP]->(ScottStamp)
 │ Scott stamp details +    │   - MERGE ScottStamp     (ScottStamp)-[:DEPICTS]->(Illustration)
 │ Mena↔Scott equivalences  │   - MERGE Illustration   (ScottStamp)-[:VARIETY_OF]->(ScottStamp)
 └──────────────────────────┘   - EQUIVALENT_TO from   (Stamp)-[:EQUIVALENT_TO]->(ScottStamp)
                                   existing Stamp                │
                                                                 ▼   MENTIONS edges (lexicon-scored)
                                            (Chunk)-[:MENTIONS {confidence,signals,score}]->(Issue)
                                            (Chunk)-[:MENTIONS_STAMP {confidence,signals}]->(Stamp)

 Query time:  retrieve.py
 ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
 │  q ──► Neo4j DOMAIN   : Issue + Stamp/ScottStamp/Variety/Illustration + equivalences            │
 │    └─► Neo4j LEXICAL  : Chunk fulltext (chunk_text_fts) + MENTIONS/MENTIONS_STAMP expansion      │
 │    └─► Weaviate       : BM25 (default) or near_text/hybrid (server-side OpenAI) over "Oxcart"    │
 │                         READ-ONLY — returns text_original (CLEAN) for citations                  │
 │  ──► fused, deduped, citation-friendly result set                                               │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
```

`run_end_to_end.py` orchestrates the build steps in order:
**sanitize → build_domain_scott → build_lexical_graph → link_lexical_to_domain →
validation report**.

---

## File map

| File | Role |
|------|------|
| `config.py` | **(already written — do not modify)** Paths, `PROTOTYPE_TAG`, `ISSUE_ID`, Neo4j/Weaviate connection factories, lexical-linking tunables, `env_summary()`. |
| `lexicon.py` | **(already written — do not modify)** LLM-free scorer: `score_chunk()`, `match_stamps()`, year/denomination/color/catalog extractors. The core of the lexical link layer. |
| `sanitize_chunks.py` | Reads `results/final_jsons/<DOC>_final.json` for the curated `FIRST_ISSUE_DOCS` subset, strips hallucinated metadata/text, drops caption-only chunks, validates against `results/markdown/<DOC>.md`, and writes `results/oxcarts-patch/<DOC>_patched.json`. |
| `build_domain_scott.py` | Loads `data/scott_first_issue.json` + `data/scott_equivalences.json`; MERGEs `ScottStamp` / `Illustration` nodes; creates `HAS_SCOTT_STAMP`, `DEPICTS`, `VARIETY_OF`, and `EQUIVALENT_TO` (to existing Mena `Stamp`). |
| `build_lexical_graph.py` | Reads the patched chunk JSONs; MERGEs `Document` + `Chunk` nodes; creates `HAS_CHUNK` and `NEXT` (reading order). |
| `link_lexical_to_domain.py` | Runs `lexicon.score_chunk()` over each `Chunk`; creates `MENTIONS` (→ `Issue`) and `MENTIONS_STAMP` (→ `Stamp`) edges with confidence/signals/score. |
| `retrieve.py` | Retrieval API: `answer()` (compact card) **and** `context_bundle()` (the graph-first, quality-gated, per-source-budget bundle — recommended). See **`retrieve.md`**. |
| `examples_runner.py` | CLI for `context_bundle()` — prints the graph-first context (domain → related → ranked source docs → all good lexical passages → thin Weaviate backup) and **auto-saves a transcript** to `results/`. `--q`/`--stamp`/`--max-lexical`/`--min-link`/`--k-weaviate`/`--width`/`--demo`. |
| `retrieve.md` | **How to use retrieval + feed an LLM.** Output shapes, worked examples, the generate-step prompt pattern, depth levers, and the graph-first `context_bundle` mode (§9). |
| `results/` | Per-run context transcripts (`examples_runner.py`) + `--dry-run` reports (gitignored). |
| `sample40.txt` | A 36-doc Spanish-heavy validation sample (CRF 01–12 + Filatelia/Timbre/Juventud/Philatelist/AFCR + non-first-issue negative controls) for `--docs-file` dry-runs. |
| `run_end_to_end.py` | Orchestrates sanitize → domain → lexical → link → validation report. |
| `teardown.py` | Deletes **only** prototype-tagged Neo4j data (`prototype = PROTOTYPE_TAG`). `--yes` to skip the confirmation prompt. |
| `coverage_scan.py` | **Whole-corpus scan (Approach A).** Sanitizes in-memory + scores *every* chunk of all docs, but materializes **only** first-issue hits (**prefix-deduped, keep-longest**) plus `MENTIONS`/`MENTIONS_STAMP`. `--all` scans the full corpus **except** the 526 Boletín Correos bulletins + the Mena/Scott catalogs = **894 docs**; also `--sample N`, `--docs ...`, `--docs-file PATH`, `--include-boletines`, and **`--dry-run`** (score-only; writes a `results/` report, **no** Neo4j/Weaviate writes — validate a lexicon change before committing it). Resets prototype `Chunk`/`Document` first (keeps the Scott layer + Mena domain). |
| `evaluate.py` | **Read-only ground-truth + coverage report.** Coverage stats, `link_score` distribution, per-stamp mentions, domain join, and a precision sample (strongest + weakest linked chunks with their text) so you can judge precision yourself. |
| `cypher_queries.md` | Copy-paste **Neo4j Browser** queries: domain layer, clean evidence set (`score≥6, ¬COMPETING`), per-stamp evidence, coverage, and a subgraph visualization. |
| `EVALUATION.md` | Coverage numbers, ground-truth precision verdict, and the **chunking root-cause** analysis for the remaining false positives. |
| `data/` | `scott_first_issue.json` (Scott stamp details + illustrations) and `scott_equivalences.json` (Mena↔Scott). |
| `tests/` | `test_lexicon.py` (already passing — do not modify) and any added regression tests. Test files add the parent dir to `sys.path`. |
| `requirements.txt` | Documentation/portability list; deps are already in `.venv-clean`. |

---

## Run commands

> **Interpreter:** always the repo venv `".venv-clean\Scripts\python.exe"`, never
> bare `python`. Run every script **from the repo root** so the script's own
> directory is `sys.path[0]` and `from config import ...` / `import lexicon`
> resolve without any path hacks.

```powershell
# 0. Config / environment sanity check (prints a non-secret snapshot)
".venv-clean\Scripts\python.exe" first_issue_graphrag\config.py

# 0b. Lexicon smoke test (LLM-free scorer — already passing)
".venv-clean\Scripts\python.exe" first_issue_graphrag\tests\test_lexicon.py

# 1. Sanitize the curated chunk subset -> results/oxcarts-patch/<DOC>_patched.json
".venv-clean\Scripts\python.exe" first_issue_graphrag\sanitize_chunks.py

# 2. Build the whole graph end-to-end (sanitize -> domain -> lexical -> link -> report)
".venv-clean\Scripts\python.exe" first_issue_graphrag\run_end_to_end.py

# 3. Ask a question (combines Neo4j domain + Neo4j lexical + Weaviate read-only)
".venv-clean\Scripts\python.exe" first_issue_graphrag\retrieve.py --q "Who printed the 1863 half real and what color is it?"

# 3b. RECOMMENDED for LLM hand-off: graph-first context bundle (auto-saves to results/)
#     defaults give ALL good lexical passages with FULL text (no truncation)
".venv-clean\Scripts\python.exe" first_issue_graphrag\examples_runner.py --q "the first issue plate crack and its positions" --stamp 1

# 4. Roll back: remove ONLY our prototype-tagged Neo4j data
".venv-clean\Scripts\python.exe" first_issue_graphrag\teardown.py --yes
```

Individual build steps can also be run on their own (each is idempotent via
MERGE and takes argparse defaults):

```powershell
".venv-clean\Scripts\python.exe" first_issue_graphrag\build_domain_scott.py
".venv-clean\Scripts\python.exe" first_issue_graphrag\build_lexical_graph.py
".venv-clean\Scripts\python.exe" first_issue_graphrag\link_lexical_to_domain.py
```

### Whole-corpus coverage + evaluation (Approach A)

`run_end_to_end.py` builds the **10-doc demo** (it ingests *all* chunks of those
docs). To cover the **whole corpus** instead — scanning every chunk of all
**894 docs** (the 1,424-PDF corpus **minus** the 526 Boletín Correos bulletins
and the Mena/Scott catalogs, which already live in the domain graph) and
materializing **only** the first-issue hits (prefix-deduped) — use
`coverage_scan.py`.

**Validate before you write.** `--dry-run` scores everything and dumps a
linked + near-miss report to `results/` **without touching Neo4j or Weaviate** —
the safe way to test a lexicon/threshold change. Then do the real run:

```powershell
# 0. (optional) dry-run a representative sample first — NO database writes
".venv-clean\Scripts\python.exe" first_issue_graphrag\coverage_scan.py --dry-run --docs-file first_issue_graphrag\sample40.txt

# 1. Build domain layer once (idempotent), then scan the full corpus into Neo4j
".venv-clean\Scripts\python.exe" first_issue_graphrag\build_domain_scott.py
".venv-clean\Scripts\python.exe" first_issue_graphrag\coverage_scan.py --all --no-weaviate   # 894 docs; or --sample 80

# 2. Read coverage stats + a ground-truth precision sample (strongest & weakest links)
".venv-clean\Scripts\python.exe" first_issue_graphrag\evaluate.py --top 15 --weak 15
```

Current full build: **296 docs / 653 distinct first-issue chunks** (170 docs /
431 chunks are newly-added non-OXCART sources). Inspect it in **Neo4j Browser**
with `cypher_queries.md` — start with the *clean evidence set* (`score ≥ 6 AND
NOT 'COMPETING' IN signals`) and see §14–§17 for the multi-corpus expansion.
`EVALUATION.md` records the measured coverage, precision/recall, and the
de-duplication finding.

> **`coverage_scan.py` (Approach A) vs `build_lexical_graph.py` + `link_lexical_to_domain.py`:**
> the two-step path ingests *all* chunks of the chosen docs (fine for the 10-doc
> demo; ~193k nodes for the whole corpus). `coverage_scan.py` is the
> prototype-correct path for wide coverage — it scans everything but writes only
> the hits, collapses nested/near-duplicate passages (prefix-dedupe, keep-longest),
> and drops heading/byline fragments.

### Curated document subset

`sanitize_chunks.py` defines `FIRST_ISSUE_DOCS` (the default for sanitize and all
downstream steps) — journal issues with strong first-issue content:

```
OXCART03  OXCART50  OXCART08  OXCART09  OXCART02
OXCART04  OXCART05  OXCART06  OXCART75  OXCART51
```

---

## Neo4j new-schema reference

All nodes and relationships below carry `prototype = "first_issue_graphrag"`.
Existing Mena nodes (`Issue`, `Stamp`, `Variety`, ...) are **read only** — we
attach to them but never alter their existing properties.

### Nodes (MERGE key in bold)

| Label | MERGE key | Properties |
|-------|-----------|------------|
| `ScottStamp` | **`scott_number`** | `denomination?`, `color?`, `mint_value?`, `used_value?`, `perforation?`, `illustration?`, `variety_of?`, `description?`, `prototype` |
| `Illustration` | **`illustration_number`** | `design_name`, `design_description`, `denomination?`, `prototype` |
| `Document` | **`doc_id`** | `prototype` |
| `Chunk` | **`chunk_id`** | `doc_id`, `text` (clean), `page`, `reading_order`, `link_score?`, `prototype` |

### Relationships

| Pattern | Notes |
|---------|-------|
| `(Issue {issue_id: ISSUE_ID})-[:HAS_SCOTT_STAMP]->(ScottStamp)` | Always created for each Scott stamp. |
| `(ScottStamp)-[:DEPICTS]->(Illustration)` | When the stamp references an illustration. |
| `(ScottStamp)-[:VARIETY_OF]->(ScottStamp)` | e.g. `"1a"`/`"1b"` → `"1"`. |
| `(Stamp {issue_id: ISSUE_ID, catalog_no: <mena>})-[:EQUIVALENT_TO {confidence, source:"user_provided"}]->(ScottStamp {scott_number: <scott>})` | Created only if the Mena `Stamp` exists. For a Mena number with a letter suffix (e.g. `"1A"`), also try a `Variety` match; if neither exists, skip the `Stamp` edge but still keep `HAS_SCOTT_STAMP`. |
| `(Document)-[:HAS_CHUNK]->(Chunk)` | Document ownership. |
| `(Chunk)-[:NEXT]->(Chunk)` | Reading order within a document. |
| `(Chunk)-[:MENTIONS {confidence, signals, score}]->(Issue {issue_id: ISSUE_ID})` | Lexicon-scored issue link. |
| `(Chunk)-[:MENTIONS_STAMP {confidence, signals}]->(Stamp {issue_id: ISSUE_ID, catalog_no: <mena>})` | Lexicon-resolved specific stamp. |

### Constraints + index (created idempotently)

```cypher
CREATE CONSTRAINT scott_stamp_number IF NOT EXISTS
  FOR (s:ScottStamp)   REQUIRE s.scott_number IS UNIQUE;
CREATE CONSTRAINT illustration_number IF NOT EXISTS
  FOR (i:Illustration) REQUIRE i.illustration_number IS UNIQUE;
CREATE CONSTRAINT document_doc_id IF NOT EXISTS
  FOR (d:Document)     REQUIRE d.doc_id IS UNIQUE;
CREATE CONSTRAINT chunk_chunk_id IF NOT EXISTS
  FOR (c:Chunk)        REQUIRE c.chunk_id IS UNIQUE;

CREATE FULLTEXT INDEX chunk_text_fts IF NOT EXISTS
  FOR (c:Chunk) ON EACH [c.text];
```

> **Write safety:** all mutations use parameterized Cypher (`$param`, never
> f-string interpolation) and run through `session.execute_write(...)` so they
> retry on transient errors. Fulltext queries Lucene-escape the user string
> (`+ - && || ! ( ) { } [ ] ^ " ~ * ? : \ /`) before `CALL
> db.index.fulltext.queryNodes('chunk_text_fts', $q)` — catalog numbers with
> colons (e.g. `A:123`) would otherwise fail to parse.

---

## Validation report

`run_end_to_end.py` (and `sanitize_chunks.py` per-doc) print a concise report so
you can confirm the build without opening a graph browser. It shows:

- **Sanitization:** per document `total / kept / dropped_caption /
  figure_noise_stripped`, plus a markdown source-of-truth check flagging any
  cleaned chunk whose text does not substring-match `results/markdown/<DOC>.md`
  (potential residual hallucination).
- **Domain build:** counts of `ScottStamp` and `Illustration` MERGEd;
  `EQUIVALENT_TO` edges created vs. Mena `Stamp`s that were missing (so an
  equivalence had to fall back to `Variety` or skip the `Stamp` edge).
- **Lexical build:** `Document`/`Chunk` node counts and `NEXT` chain length per
  document.
- **Linking:** how many chunks linked to the Issue (`MENTIONS`), how many
  resolved to a specific stamp (`MENTIONS_STAMP`), and the score distribution
  against `FIRST_ISSUE_MIN_LINK_SCORE` / `FIRST_ISSUE_PHRASE_MIN_SCORE`.
- **Connectivity:** confirmation that every created node/edge carries
  `prototype = PROTOTYPE_TAG` (the teardown precondition).

---

## Rollback

The prototype is fully reversible because every node and relationship it writes
is tagged `prototype = "first_issue_graphrag"`.

```powershell
".venv-clean\Scripts\python.exe" first_issue_graphrag\teardown.py --yes
```

`teardown.py` deletes only prototype-tagged nodes and relationships
(`DETACH DELETE` on `MATCH (n {prototype: $tag})`, plus relationship cleanup),
leaving the existing Mena domain graph untouched. Weaviate is never modified, so
there is nothing to roll back there. The sanitized files under
`results/oxcarts-patch/` are plain artifacts and can be deleted manually if you
want a completely clean slate; re-running `sanitize_chunks.py` regenerates them.

Without `--yes`, `teardown.py` prints the count of prototype-tagged nodes it
would remove and asks for confirmation before deleting.

---

## Tuning knobs (read from `.env`, defaults in `config.py`)

| Variable | Default | Effect |
|----------|---------|--------|
| `FIRST_ISSUE_MIN_LINK_SCORE` | `4` | Min weighted signal score for a chunk to link to the Issue. |
| `FIRST_ISSUE_MIN_STRONG_CLASSES` | `2` | Min number of **distinct** strong signal classes required (precision gate — rejects single-cue links). |
| `FIRST_ISSUE_COMPETING_MIN_CLASSES` | `3` | Higher bar when competing/commemorative context is detected. |
| `FIRST_ISSUE_STAMP_MIN_CONF` | `0.5` | Min confidence to attach a specific stamp (denomination ± color). |

> The linker also requires at least one **core** cue (`YEAR_ANCHOR`=1863, a reales/peso
> `DENOM`, or the `ABNCo`/`Banco Americano` `PRINTER`) — this is structural, not a tunable.
> It is **bilingual** (English + Spanish: `primera emisión`/`primera serie`, `medio/dos/cuatro
> reales`, `un peso`, `Decreto N° 2`, …) and applies three structural suppressors:
> **FOREIGN** (another country's classic issue, unless Costa Rica is named), **COMPETING**
> (commemorative / 1881-83 surcharge / Guanacaste / later issue), and **FISCAL** (revenue
> stamps, unless the 1863 anchor is present). See `EVALUATION.md`.
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | `bolt://127.0.0.1:7687` / `neo4j` / — / `neo4j` | Neo4j connection. |
| `WEAVIATE_HOST` / `WEAVIATE_HTTP_PORT` / `WEAVIATE_GRPC_PORT` | `localhost` / `8085` / `50056` | Weaviate connection (read-only). |
| `OPENAI_API_KEY` | — | Optional. Only enables Weaviate's server-side `near_text`/`hybrid`; BM25 works without it. Never used for direct LLM calls. |
