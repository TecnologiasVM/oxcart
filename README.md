# Oxcart — a knowledge graph and retrieval system for Costa Rican philately

<div align="center">
  <img src="./assets/oxcart_logo.svg" width="260" alt="Oxcart logo">
</div>

<div align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-lightgray" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Graph-Neo4j-008CC1" alt="Neo4j">
  <img src="https://img.shields.io/badge/Search-Weaviate-00cc66" alt="Weaviate">
  <img src="https://img.shields.io/badge/API-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/UI-Next.js-000000" alt="Next.js">
</div>

Oxcart answers questions about Costa Rican stamps with **evidence**: catalogue facts from a knowledge graph, and the
passages of the philatelic literature that support them, each with its document and page.

**Status.** What runs today is a **retrieval-only research demo** for one issue, the 1863 First Issue. It returns
the evidence and does not write an answer. It runs locally; there is no hosted demo yet. The [roadmap](#roadmap)
lists what is planned and not built.

<p align="center">
  <img src="assets/screenshots/explore.png" alt="The Explore view: the First Issue at the centre, with its stamps, Scott equivalents, varieties and the documents that cite them" width="85%">
</p>

## What works today

- **A domain graph in Neo4j** built from the Mena 2018 catalogue: issues, stamps, varieties, proofs, plates, and
  equivalences to Scott numbers.
- **A literature index in Weaviate**: 192,680 text chunks from 1,424 documents (journals, monographs, bulletins,
  catalogues). The documents were published from 1952 to 2025 and cover stamps from 1863 to 2025. See
  [docs/PHILATELIC_LITERATURE.md](docs/PHILATELIC_LITERATURE.md).
- **A First Issue evidence graph**: 653 passages from 296 documents linked to the 1863 First Issue and to its
  individual stamps by a rule-based linker, with no language model.
- **An explorer app** (`first_issue_graphrag/`): a FastAPI backend and a Next.js frontend with four views:
  Overview, Explore (the graph), Query (ask and read the evidence), and the Mena Catalogue by year.
- **A question page and the path behind it** (the site root, `POST /api/ask`): ask about any Costa Rican issue
  in Spanish or English and read the evidence, the catalogue issue and the passages of the literature. The
  conversation stays in the browser; there are no accounts. The hosted demo is not live yet.
- **A test set and a retrieval evaluation** (`eval/`, [EVALUATION.md](EVALUATION.md)): 151 questions in Spanish
  and English, and a measured choice of a 41,126-passage subset of the literature index that answers more of them
  than the full index does. The gold for the literature questions is judged by a model, not yet by a person.
- **A catalogue lookup for any issue** (`first_issue_graphrag/catalogue_lookup.py`): finds the issue a question
  is about, in Spanish or English, with no language model. It is a module with tests; the app does not call it yet.

The corpus, the databases and the page images are **not in this repository**; see [Data](#data).

## Stack

| Layer | What the code uses | Where |
|---|---|---|
| Graph | Neo4j, queried with Cypher | `neo4j_utils/`, `first_issue_graphrag/` |
| Search | Weaviate 1.32.4. Keyword search (BM25) by default; `near_text` and `hybrid` search over OpenAI `text-embedding-3-large` vectors (3,072 dimensions) when an OpenAI key is set | `docker-compose.yml`, `pipeline/philatelic_weaviate.py`, `first_issue_graphrag/README.md` |
| API | FastAPI, Pydantic v2 | `first_issue_graphrag/backend/requirements.txt` |
| UI | Next.js, React, TypeScript, Cytoscape | `first_issue_graphrag/frontend/package.json` |
| Tests | Playwright for the UI; Python test scripts for the linker, the backend and the pipeline | `first_issue_graphrag/frontend/tests/`, `first_issue_graphrag/tests/`, `tests/` |
| Parsing | Dolphin | `third_party/dolphin/` |
| Earlier prototype and catalogue parsing | LangChain, Gradio | `pipeline/mena_stamp_agent.py`, `notebooks/`, `neo4j_utils/neo4j_gradio_VIS.py` |

## How it works

### 1. The pipeline

```
Scanned literature (PDF)                       Mena 2018 catalogue
        │                                              │
        ▼                                              ▼
 Parse layout and text (Dolphin)              Parse into structured issues
        │                                     (pipeline/mena_*.py)
        ▼                                              │
 Chunk + enrich with philatelic metadata               ▼
 (pipeline/philatelic_*.py)                   Neo4j domain graph (neo4j_utils/)
        │                                     Issue → Stamp → Variety, Proof, Plate
        ▼                                              │
 Weaviate collection "Oxcart"                          │  + Scott equivalences
 192,680 chunks · 1,424 documents                      │
        │                                              │
        └────────► First Issue linker ◄────────────────┘
                   (first_issue_graphrag/lexicon.py, coverage_scan.py)
                   scores every chunk; links passages to the issue and its stamps
                                 │
                                 ▼
                   Query: graph first, Weaviate as a short backup list
                   (first_issue_graphrag/retrieve.py → FastAPI → Next.js)
```

### 2. What makes the retrieval more than a vector search

- **Graph first.** A question is answered from the graph: the catalogue record, the related varieties, proofs and
  plates, then the linked passages ranked by how strongly they refer to the issue. Weaviate adds only a short list
  of passages the graph did not already return (5 by default).
- **A rule-based linker, no language model.** `lexicon.py` scores each chunk with weighted signals (the year, the
  denominations and colours, the printer, plate and variety vocabulary, in English and Spanish). A chunk needs at
  least two independent strong signals to be linked.
- **Guards against look-alikes**, recorded on each link so they can be audited: `FOREIGN` (another country's first
  issue), `COMPETING` (later Costa Rican issues that reuse the same words), `FISCAL` (revenue stamps).
- **A quality tier.** The default evidence set is links with score 6 or more and no competing signal: 232 passages.
- **Two catalogue systems joined.** A Mena number resolves to its Scott equivalent and back.
- **Figures by page.** Images cropped from the cited pages are attached by document and page, not by similarity.
- **Nothing is generated.** The query path makes no language-model call.

### 3. What improved the quality of the evidence

Measured in [first_issue_graphrag/EVALUATION.md](first_issue_graphrag/EVALUATION.md):

| Change | Effect |
|---|---|
| Scan the whole corpus, not one journal | Documents with First Issue evidence: 155 → **296** |
| Collapse nested duplicate chunks (same passage stored at growing lengths) | One validation sample: 139 linked chunks → **15 distinct passages**, no distinct content lost |
| Add Spanish vocabulary to the linker (the corpus is about 70% Spanish) | About 298 chunks across 126 documents newly linked |
| Add the `FOREIGN`, `COMPETING` and `FISCAL` guards | About **90% precision** on a hand-audited 36-document sample |

Source documents returned for the four demo questions, before and after: 75 → 131, 33 → 68, 31 → 46, 30 → 49.

The known remaining error source is oversized chunks that merge unrelated paragraphs. `EVALUATION.md` describes it
and the fix.

### 4. Which evaluations ran

| Check | Result |
|---|---|
| Coverage scan (`evaluate.py`) | 296 documents, 653 passages, 826 stamp mentions, 232 in the clean tier |
| Hand audit of linked passages (36-document sample) | about 90% precision; details in `EVALUATION.md` |
| Linker regression checks (`tests/test_lexicon.py`) | pass |
| Backend tests (`backend/test_mena_backend.py`) | 22 passed |
| Browser tests (Playwright) | 57 passed, 3 skipped (full suite); 4 passed (smoke) |
| Reference run on a clean Linux machine | source-document counts for the four demo questions match `first_issue_graphrag/EVALUATION.md` (46, 131, 68, 49); the same passages come back in the same order before and after the changes that made the app portable |
| Retrieval on literature questions ([EVALUATION.md](EVALUATION.md)) | a page that answers the question is among the first five passages for 36 of the 41 questions in the set, and 36 of all 49 drafted (the 8 left out counted as misses); the app as it was: 12 of 41 and 12 of 49 |
| Catalogue lookup, held-out questions | the right issue is first for 30 of 32 and in the first three for 32 of 32; the fact asked comes from the same graph that generated the question |
| Eval and lookup unit tests (`eval/tests`, `first_issue_graphrag/tests/test_catalogue_lookup.py`) | 36 passed |

How to read the retrieval numbers: the literature gold was judged by a model (`gpt-6.1-sol`); no person has checked
the grades. A second model read a blind sample of 45 pages and gave the same grade on 39 and the same "answers the
question or not" on 41; both readers are OpenAI models with one rubric. A question entered the set only when
search had already found a page that answers it, which is why every figure has two denominators.
[EVALUATION.md](EVALUATION.md) has the method and the limits.

Not done yet: a person's check of the model-judged gold, and any evaluation of written answers (there is no
answer step yet).

### 5. What is in place for running it as a service

- The query path calls no language model, so a question has no per-request model cost.
- Both stores are used read-only.
- One Neo4j connection pool is shared by all requests. Against a hosted Neo4j this took the demo questions from
  5 to 66 seconds (with failed requests) to a median of 2.9 seconds, same passages.
- Responses are bounded: at most 40 graph passages per question, long passages clipped for display, the full text
  available as a separate export.
- Only the frontend port needs to be reachable; it proxies `/api` to the backend. Everything binds to `127.0.0.1`
  by default. Embedding vectors are stripped from every response.
- Dependencies are pinned.
- A workflow runs the tests that need no database on every pull request: the Python unit tests, the frontend
  build and the browser smoke test.

Not done yet: hosting, caching and rate limits. A subset of the index that fits a free hosting tier was chosen
and measured ([EVALUATION.md](EVALUATION.md)); the hosted demo itself is not built.

## Run it locally

You need Python 3.10+, Node.js 20+, a Neo4j database holding the graph, and a Weaviate instance holding the `Oxcart`
collection (`docker-compose.yml` starts Weaviate 1.32.4). The data itself is not distributed; see [Data](#data).

```bash
git clone https://github.com/TecnologiasVM/oxcart.git
cd oxcart

# 1. configuration: copy the template and fill in the Neo4j and Weaviate settings
cp .env.example .env

# 2. backend dependencies, in a virtual environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -r first_issue_graphrag/backend/requirements.txt

# 3. frontend dependencies
cd first_issue_graphrag/frontend && npm ci && cd ../..

# 4. start both servers, check them, stop them
python first_issue_graphrag/servers.py start
python first_issue_graphrag/servers.py status
python first_issue_graphrag/servers.py stop
```

Open <http://localhost:3000/research>. `GET /api/health` reports whether Neo4j and Weaviate are reachable.

Tests:

```bash
python first_issue_graphrag/tests/test_lexicon.py                  # no services needed
python first_issue_graphrag/tests/test_figure_refs.py              # no services needed
cd first_issue_graphrag/backend && python test_mena_backend.py     # needs Neo4j (and Weaviate for evidence)
cd ../frontend && npx playwright install chromium
npx playwright test                                                # smoke tests, no backend needed
npx playwright test --config=playwright.shadow.config.ts           # full suite, needs both servers running
```

`servers.py` was tested on Linux. It is written to work on Windows and macOS and has not been run there yet.

## Repository map

| Path | What it holds |
|---|---|
| `first_issue_graphrag/` | The app: graph build and linker, retrieval, catalogue lookup, FastAPI backend, Next.js frontend. Start with its [README](first_issue_graphrag/README.md); the audit of the First Issue evidence graph is its [EVALUATION.md](first_issue_graphrag/EVALUATION.md). |
| `eval/` | The retrieval evaluation: measures, search arms, the catalogue question generator, pooling, page judging, scoring. Results and method in [EVALUATION.md](EVALUATION.md). |
| `scripts/` | `with-key.sh`: runs one command with keys taken from the machine's secret store, without writing them to a file. |
| `neo4j_utils/` | Loading the Mena catalogue into Neo4j, indexes, search, and a Cypher cookbook. |
| `pipeline/` | Parsing, chunking, enrichment and indexing of the literature; catalogue parsing. |
| `notebooks/` | Research notebooks, without outputs, including the earlier Gradio question-answering prototype. |
| `third_party/dolphin/` | The Dolphin document parser (ByteDance, MIT). |
| `docs/` | The literature catalogue and working notes. |
| `tests/` | Tests for the pipeline modules. |

## The graph

The Neo4j graph models the catalogue: `Issue`, `Stamp`, `Variety`, `Proof`, `Plate`, `PlatePosition`, and the
administrative context (`LegalAct`, `Person`, `Printer`, `ProductionOrder`). Typical paths:

```
(:Issue)-[:HAS_STAMP]->(:Stamp)-[:HAS_VARIETY]->(:Variety)-[:AT_POSITION]->(:PlatePosition)
(:Stamp)-[:EQUIVALENT_TO]->(:ScottStamp)
(:Chunk)-[:MENTIONS {score, signals}]->(:Issue)        (:Chunk)-[:MENTIONS_STAMP]->(:Stamp)
```

<div align="center">
  <img src="./neo4j_utils/img/Stamp View Sample.png" width="45%" alt="Stamp view">
  <img src="./neo4j_utils/img/Issue View Sample.png" width="45%" alt="Issue view">
  <br>
  <i>Left: a stamp with its varieties and plates. Right: an issue with its related entities.</i>
</div>

Queries and the full schema: [neo4j_utils/neo4j_technical_guide_cypher_cookbook.md](neo4j_utils/neo4j_technical_guide_cypher_cookbook.md)
and [first_issue_graphrag/cypher_queries.md](first_issue_graphrag/cypher_queries.md).

## Data

This repository holds code and documentation. It does not hold the scanned literature, its extracted text, the page
images, the Weaviate collection or the Neo4j database. Without them the app starts and reports the stores as
unreachable.

Two facts about the literature index that anything built on it must respect:

- Every stored vector is the `text-embedding-3-large` embedding of the word `Oxcart`, a space, and the passage
  text: the collection name was prepended when the collection was first vectorized. Questions are embedded as they
  are, without that prefix, and the evaluation was measured that way.
- Many passages are stored several times as growing prefixes of one another. Collapsing them (keep the longest
  copy per document) takes the index from 192,680 to 94,116 passages and improves keyword search; see
  [EVALUATION.md](EVALUATION.md).

## Roadmap

Planned, **not built**:

1. **A hosted demo**, retrieval only, on free hosting tiers.
2. **An answer step.** A short written answer that cites the passages it used, declines questions outside its
   sources, and falls back to evidence-only when it cannot answer. Evaluated on the test set before release.
3. **The answer step as a multi-step flow** (route, retrieve, grade the evidence, retrieve again once, answer),
   scored against the simpler version on the same evaluation.
4. **Scope beyond the First Issue in the app**: any Costa Rican stamp question. The catalogue lookup and the
   evaluated literature search exist as modules; the app still answers from the First Issue only.

## License

MIT, see [LICENSE](LICENSE).

It includes code from [Dolphin](https://github.com/bytedance/Dolphin) (MIT, Copyright 2025 ByteDance Ltd. and/or its
affiliates). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the files and the original license.

## Acknowledgments

- [Dolphin](https://github.com/bytedance/Dolphin) for PDF structure extraction
- [Neo4j](https://neo4j.com/) and [Weaviate](https://weaviate.io/)
- The authors and editors of the philatelic literature this work indexes

## Earlier prototype

Before the explorer, the project had a Gradio question-answering prototype over the same index. Its notebook is
kept in `notebooks/gradio_app.ipynb`; this is what it looked like:

<p align="center">
  <img src="assets/preview_full.png" alt="The earlier Gradio prototype: a question, a graph view and a list of source passages" width="60%" />
</p>

<div align="center">
  <i>Built for stamp history, scholarship, and collectors.</i>
</div>
