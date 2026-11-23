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

**Try it: [oxcart.chat](https://oxcart.chat).** Ask about any Costa Rican issue, in Spanish or English. You get the
evidence and, a moment later, a short answer written from it, each sentence with the card or passage it cites. The
demo runs on free hosting tiers and sleeps when nobody uses it; waking it takes about half a minute, and the
stored examples on the page work meanwhile.

**Status.** What runs today is retrieval and, on top of it, **a short written answer with citations**. A language
model writes the answer from the evidence that is shown and from nothing else; a sentence that cites nothing is
not shown, and when the evidence does not cover the question the page says so and shows the evidence. How often
the answers are supported and correct was measured on the test set ([EVALUATION.md](EVALUATION.md#written-answers));
the grades are a model's, not a person's. The hosted demo is the question page and a page on
[how it works](https://oxcart.chat/how-it-works); the explorer app for the 1863
First Issue runs locally and writes no answer. The [roadmap](#roadmap) lists what is planned and not built.

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
- **An explorer app** (`backend/`, `frontend/`): a FastAPI backend and a Next.js frontend with four views:
  Overview, Explore (the graph), Query (ask and read the evidence), and the Mena Catalogue by year.
- **A question page and the path behind it** (the site root, `POST /api/ask`): ask about any Costa Rican issue
  in Spanish or English and read the evidence, the catalogue issue and the passages of the literature. The
  conversation stays in the browser; there are no accounts. This is the page the hosted demo serves.
- **A written answer with citations, as a graph** (`POST /api/chat`, `backend/app/answer_graph.py`, LangGraph).
  Four steps: `contextualize` rewrites a follow-up as a question that stands alone, `retrieve` is the question
  path as it was, `write` asks the model for a short answer with citations, `check` keeps the sentences whose
  citation holds and drops the rest.
  - *Why a graph:* each step is given only the part of the state it declares. The earlier turns of a conversation
    come from the browser, so they are a visitor's text, and `contextualize` is the only step that receives them;
    the step that writes the answer gets the question that stands alone and the evidence. Each step's result is
    sent as it ends, so the evidence arrives as fast as before and the answer follows.
  - *Why no checkpointer:* a conversation lives in the visitor's browser, which sends its last three turns with a
    follow-up. The server keeps nothing between two requests, so no visitor's text stays in its memory and
    nothing is lost when the service sleeps.
  - *What it does not do:* no step grades the evidence, none retrieves a second time, and there is no scope
    router; a rule in the model's instructions stands in for the last. Those are the next step, see the
    [roadmap](#roadmap).
- **A web part, on at the hosted demo and off by default in the code** (`POST /api/chat/web`, `backend/app/web_step.py`). When the catalogue
  and the literature do not cover an in-scope question, or answer part of it, the page can add a short part
  written from one web search, in a marked block of its own under the answer, with the pages it cites.
  - *How it is asked:* the write call says which of three things happened (outside the scope, not covered,
    part only). The answer from our sources comes first; the page then asks for the web part in a request of
    its own, with a ticket the backend signed, so the answer waits no longer than before.
  - *What it never does:* a question outside the scope gets no answer and no search. The search query is the
    question as it was searched (for a follow-up, as the rewrite step wrote it) and fixed words: nothing of an
    answer a model wrote is in it, and nothing a model writes becomes a link.
  - *Two settings turn it on:* `ASK_WEB` on the backend (with a search key) and `NEXT_PUBLIC_WEB` in the page's
    build. A page built without the second ignores the ticket and makes no request, so a search can only start
    from a page whose privacy details name the search service.
  - *Measured before it is served,* on the development questions ([EVALUATION.md](EVALUATION.md#a-web-part-three-markers-and-a-trial-with-real-searches)):
    a web sentence can be checked against the page it cites, not for being right.
- **A test set and a retrieval evaluation** (`eval/`, [EVALUATION.md](EVALUATION.md)): 151 questions in Spanish
  and English, and a measured choice of a 41,126-passage subset of the literature index that answers more of them
  than the full index does. The gold for the literature questions is judged by a model, not yet by a person.
- **A catalogue lookup for any issue** (`oxcart/catalogue_lookup.py`): finds the issue a question
  is about, in Spanish or English, with no language model. The question path calls it for every question.

The corpus, the databases and the page images are **not in this repository**; see [Data](#data).

## Stack

| Layer | What the code uses | Where |
|---|---|---|
| Graph | Neo4j, queried with Cypher | `neo4j_utils/`, `pipeline/first_issue_graph/`, `oxcart/` |
| Search | Weaviate 1.32.4. Keyword search (BM25) by default; `near_text` and `hybrid` search over OpenAI `text-embedding-3-large` vectors (3,072 dimensions) when an OpenAI key is set | `docker-compose.yml`, `pipeline/philatelic_weaviate.py`, `pipeline/first_issue_graph/README.md` |
| API | FastAPI, Pydantic v2 | `backend/requirements.txt` |
| Written answer | Claude Haiku 5.5 through Anthropic's API, with its citations feature; the steps as a LangGraph graph | `backend/app/answer_model.py`, `backend/app/answer_graph.py` |
| Web part (off by default; on at the hosted demo) | Tavily's search API: one basic search of five results; the part written by the same model, with citations | `backend/app/web_step.py` |
| UI | Next.js, React, TypeScript, Cytoscape | `frontend/package.json` |
| Tests | Playwright for the UI; Python test scripts for the linker, the backend and the pipeline | `frontend/tests/`, `oxcart/tests/`, `pipeline/first_issue_graph/tests/`, `tests/` |
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
                   (pipeline/first_issue_graph/lexicon.py, coverage_scan.py)
                   scores every chunk; links passages to the issue and its stamps
                                 │
                                 ▼
                   Query: graph first, Weaviate as a short backup list
                   (oxcart/retrieve.py → FastAPI → Next.js)
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

Measured in [pipeline/first_issue_graph/EVALUATION.md](pipeline/first_issue_graph/EVALUATION.md):

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
| Reference run on a clean Linux machine | source-document counts for the four demo questions match `pipeline/first_issue_graph/EVALUATION.md` (46, 131, 68, 49); the same passages come back in the same order before and after the changes that made the app portable |
| Retrieval on literature questions ([EVALUATION.md](EVALUATION.md)) | a page that answers the question is among the first five passages for 36 of the 41 questions in the set, and 36 of all 49 drafted (the 8 left out counted as misses); the app as it was: 12 of 41 and 12 of 49 |
| Catalogue lookup, held-out questions | the right issue is first for 30 of 32 and in the first three for 32 of 32; the fact asked comes from the same graph that generated the question |
| Written answers ([EVALUATION.md](EVALUATION.md#written-answers)), graded by a model | catalogue questions: 73 of 80 got a written answer, 62 supported by what they cite, 69 correct; literature questions: 41 of 41 written, 27 supported, 10 agree in full with the reference answer and 29 in part (10 of all 49 drafted); 29 of 30 out-of-scope questions got no written answer |
| Eval and lookup unit tests (`eval/tests`, `oxcart/tests/test_catalogue_lookup.py`) | 36 passed |

How to read the retrieval numbers: the literature gold was judged by a model (`gpt-6.1-sol`); no person has checked
the grades. A second model read a blind sample of 45 pages and gave the same grade on 39 and the same "answers the
question or not" on 41; both readers are OpenAI models with one rubric. A question entered the set only when
search had already found a page that answers it, which is why every figure has two denominators.
[EVALUATION.md](EVALUATION.md) has the method and the limits.

The web part was measured apart, with its settings on, and is not in the rows above: three runs of the markers
that ask for it, and a trial of 26 real searches in which 28 of 35 shown web sentences were supported by the
page they cite ([EVALUATION.md](EVALUATION.md#a-web-part-three-markers-and-a-trial-with-real-searches)).

Not done yet: a person's check of the model-judged gold and of the grades of the written answers.

### 5. What is in place for running it as a service

- The explorer's query path calls no language model. The written answer of the question page does: one call to
  write it, measured at 0.0007 USD a question on average and 0.0013 USD at most, and for every question after a
  conversation's first one small call before the search, about 0.0001 USD, which says whether the question
  needs the earlier turns and rewrites it only then
  ([EVALUATION.md](EVALUATION.md#written-answers)). Without a key the page works and shows the evidence only.
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

The hosted demo serves the question path only: a human check before the first question, limits per visitor and
for the whole service, and a subset of the index that fits a free hosting tier, chosen and measured in
[EVALUATION.md](EVALUATION.md). Not done yet: caching.

**The hosts are free tiers, and two of them stop when unused.** The backend's host puts it to sleep; it wakes in
about half a minute and the page says so. The literature's cluster (Weaviate Cloud, free plan) does not expire,
but its provider suspends a free cluster after 7 days without use, keeping the data, and deletes it after 30
(its documentation, read on 2026-11-22). A scheduled job outside this repository makes one read-only search of
it several times a day, and a heartbeat write to the graph database for the same reason. While either store
cannot be reached the page shows what the other returned and says which one is missing.

**What the limits are, and what they are not.** A visitor may ask 10 questions a minute and 100 a day; the
service takes 2,000 questions a day and makes at most 200 model calls a day (about 4 USD a month at the measured
average). The page has one question box, so every question after a conversation's first takes two of those
calls: the day's allowance is between 100 and 200 written answers. All of these counts live in the server's memory and start again whenever the service restarts, which on
a host that puts an idle service to sleep happens many times a day. They slow down a running service; they are
not a budget. The one limit that cannot be passed is the monthly spend limit of the model key's workspace at the
provider. It is set there, not in this repository (9 USD for November 2026); when it is reached the page shows
the evidence without a written answer.

**The web part, when it is on** (it is on at the hosted demo). It adds a third outside service: the question as it was searched goes to
Tavily, with fixed words after it; the earlier turns do not, though a follow-up's rewritten question can hold a
subject named in an earlier turn. The question, the pages the search returned and, for a part answer, the
answer already given go to Anthropic for one more model call, which counts toward the day's 200; a web request
also counts as one of the visitor's questions. Settings: `ASK_WEB` and `TAVILY_API_KEY` on the backend,
`NEXT_PUBLIC_WEB` in the page's build, `WEB_QUERY_SUFFIX` for the fixed words. Pages of video and social sites,
of marketplaces and their price guides, and of the search service itself are never used.

**How many searches.** The search plan is a free one of 1,000 credits a month with no card, so a month that
uses them up shows no web part and costs nothing. Before that, a search is allowed while the credits used this
month are under `30 + 920 x the share of the month gone by`: a quiet day leaves its share for a busier one.
The count comes from the search service's usage route, read at most once in five minutes. **That route runs
behind** (measured: 26 searches were not in it eleven minutes after the first, and were fifty minutes after the
last), so the backend adds the
searches it made itself in the last two hours. After a restart it knows only what the route says, and can allow a
few more than the rule until the route catches up. If the route cannot be read: 30 searches a day, counted in
memory.

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
python -m pip install -r backend/requirements.txt
python -m pip install -e .           # the shared modules, as the oxcart package

# 3. frontend dependencies
cd frontend && npm ci && cd ..

# 4. start both servers, check them, stop them
python scripts/servers.py start
python scripts/servers.py status
python scripts/servers.py stop
```

Open <http://localhost:3000/research>. `GET /api/health` reports whether Neo4j and Weaviate are reachable.

Tests:

```bash
python pipeline/first_issue_graph/tests/test_lexicon.py            # no services needed
python oxcart/tests/test_figure_refs.py                            # no services needed
cd backend && python test_mena_backend.py                          # needs Neo4j (and Weaviate for evidence)
cd ../frontend && npx playwright install chromium
npx playwright test                                                # smoke tests, no backend needed
npx playwright test --config=playwright.shadow.config.ts           # full suite, needs both servers running
```

`servers.py` was tested on Linux. It is written to work on Windows and macOS and has not been run there yet.

## Repository map

| Path | What it holds |
|---|---|
| `backend/` | The API (FastAPI): the question path and the explorer's routes, its tests and its Dockerfile. See its [README](backend/README.md). |
| `frontend/` | The page (Next.js): the question page and the explorer under `/research`. See its [README](frontend/README.md). |
| `oxcart/` | The modules the backend and the eval share, as a Python package: settings, the catalogue lookup, retrieval. Installed with `python -m pip install -e .`. |
| `eval/` | The evaluations: retrieval (measures, search arms, the catalogue question generator, pooling, page judging, scoring) and the written answers (`chat_arm.py`, `answer_judge.py`). Results and method in [EVALUATION.md](EVALUATION.md). |
| `scripts/` | `with-key.sh`: runs one command with keys taken from the machine's secret store, without writing them to a file. `load_cluster.py`: rebuilds the literature collection on a Weaviate Cloud cluster from an export. `servers.py`: starts, checks and stops the backend and the frontend on this machine. |
| `neo4j_utils/` | Loading the Mena catalogue into Neo4j, indexes, search, and a Cypher cookbook. |
| `pipeline/` | Parsing, chunking, enrichment and indexing of the literature; catalogue parsing. `pipeline/first_issue_graph/` holds the First Issue graph build and linker; start with its [README](pipeline/first_issue_graph/README.md); the audit of the First Issue evidence graph is its [EVALUATION.md](pipeline/first_issue_graph/EVALUATION.md). |
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
and [pipeline/first_issue_graph/cypher_queries.md](pipeline/first_issue_graph/cypher_queries.md).

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

1. **Grade the evidence and retrieve again once.** The answer graph has four steps today. The next ones: a step
   that judges whether the evidence answers the question before anything is written, one more search when it
   does not, and a scope router in place of the rule in the model's instructions; each scored against today's
   graph on the same evaluation.
2. **Better evidence for the literature questions.** The answer is written from five passages of at most 700
   characters, and for most literature questions that covers part of the answer only
   ([EVALUATION.md](EVALUATION.md#written-answers)).
3. **Scope beyond the First Issue in the explorer**: the question page already takes any Costa Rican stamp
   question; the explorer's graph views still cover the First Issue only.

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
