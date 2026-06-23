# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Oxcart Graph RAG** — a domain-specialized Retrieval-Augmented Generation system for Costa Rican philatelic research. It ingests philatelic literature (catalogs, journals, monographs, exhibits), normalizes structure, and serves grounded answers with citations against ~193k chunks from ~1,424 PDFs.

This repo bundles the upstream **Dolphin** multimodal document parser (Swin + MBart, analyze-then-parse) as the primary PDF backend, plus the Oxcart-specific enrichment, indexing, retrieval, and UI layers on top.

## Architecture (Big Picture)

The system has three storage layers and a single orchestration pattern: parse → enrich → dual-index → retrieve → ground → answer.

```
PDFs ──► Dolphin (or Landing.ai ADE fallback) ──► recognition_json
       │                                              │
       │                                              ▼
       │                              philatelic_patterns.py  (metadata enrichment)
       │                                              │
       │                                              ▼
       │                              dolphin_transformer.py  (OXCART chunk JSON, *.oxcart.json)
       │                                              │
       │                                              ▼
       │                              run_quality_check.py → dolphin_quality_control.py
       │                                              │
       │                                              ▼
       │                          philatelic_weaviate.py  ──►  Weaviate "Oxcart" collection
       │                                                      (text2vec-openai, hybrid+BM25)
       │
       └──► Mena 2018 catalog (JSON) ──► neo4j_utils/neo4j_ingest_mena_v1.py
                                          neo4j_utils/neo4j_index_and_embed.py
                                          ──► Neo4j (graph + vector + fulltext indexes)

Query:
  Gradio UI (gradio_app.ipynb)
    └─► philatelic_rag.ipynb pipeline:
          ├─ Weaviate hybrid search (alpha≈0.35) + MMR + domain filters
          ├─ Neo4j hybrid (fulltext / vector / graph expansion) for catalog/issue queries
          └─ multi-query expansion + multi-stage rerank + context compression (Advanced tier)
```

### Key cross-cutting concepts

- **Two storage modes are complementary, not redundant.** Weaviate holds the *literature corpus* (free-text chunks with philatelic metadata). Neo4j holds the *structured catalog* (Mena 2018) as Issue/Stamp/Variety/Proof/Plate entities. Catalog-number or issue-name queries should hit Neo4j first, then expand into Weaviate for textual evidence.
- **Chunk schema is load-bearing.** `philatelic_chunk_schema.py` defines the canonical chunk fields (`doc_id`, `chunk_id`, `chunk_type`, `scott_numbers`, `years`, `catalog_systems`, `quality_score`, etc.). `philatelic_patterns.py` populates these; `philatelic_weaviate.py` maps them to the Weaviate `Oxcart` collection. Changing one without the others will break indexing.
- **Only `text` is vectorized.** In the Weaviate schema, the named vector `default` indexes only the enriched `text` field (`text-embedding-3-large`, cosine). `text_original` is kept for filtering/dedupe but is *not* embedded — keep it that way to avoid double-vectorization cost.
- **Output format is `.oxcart.json`.** `dolphin_transformer.py` emits OXCART-format chunk JSONs (not raw Dolphin recognition JSON) — this is what `philatelic_weaviate.py` ingests.
- **Retrieval has Basic vs Advanced tiers** (see README §🔍). Both share the same Weaviate collection; the Advanced tier adds multi-query LLM expansion, cross-source reranking, and consensus gating. Confidence thresholds (`MIN_HYBRID_SCORE`, `MIN_COSINE_SIM`, `CONSENSUS_MIN_SOURCES`) live in `.env`.
- **Neo4j viewer is a Gradio sub-app.** `neo4j_utils/neo4j_gradio_VIS.py` can run standalone, but the main UI integrates it as a tab in `gradio_app.ipynb`.

### Dolphin parser (upstream, embedded)

`chat.py`, `utils/model.py`, `utils/processor.py`, `config/Dolphin.yaml`, and `demo_page*.py` / `demo_element*.py` are the upstream Dolphin model code. Two model formats are supported:

- **Original**: `./checkpoints/dolphin_model.bin` + `dolphin_tokenizer.json` (used by `demo_page.py`)
- **Hugging Face**: `./hf_model/` (used by `demo_page_hf.py`) — `git clone https://huggingface.co/ByteDance/Dolphin ./hf_model`

For Oxcart's pipeline, prefer driving Dolphin via `dolphin_transformer.py` rather than the raw `demo_page.py`, since the transformer produces the chunk JSON shape Weaviate expects.

## Python Environment Management

**CRITICAL**: Always use the `.venv-clean` environment for ALL Python package installations. This prevents damaging other Python environments on the system.

- **Install packages**: `".venv-clean\Scripts\python.exe" -m pip install <package>`
- **Run Python**: `".venv-clean\Scripts\python.exe"`
- **Check installations**: `".venv-clean\Scripts\python.exe" -c "import <module>"`

Environment details:
- Location: `.venv-clean/` (Python 3.10.11, PyTorch 2.1.0+cu118, CUDA 11.8, RTX 3060)
- All dependencies for the Dolphin parser + Oxcart pipeline are installed here.

There is a second `venv/` (Python 3.13.0, PyTorch 2.6.0+cu118) for forward-compatibility testing, **but it does not have `llmstudio` or `vllm_mbart`.** Use it only when explicitly working on Python 3.13 compatibility — see `PYTHON_ENVIRONMENTS.md`. Never install into system Python.

## Common Commands

### Start infrastructure

```powershell
# Weaviate (custom ports: HTTP 8085, gRPC 50056 — see docker-compose.yml)
docker-compose up -d
curl http://localhost:8085/v1/meta   # health check

# Neo4j (Docker)
docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<pw> neo4j:latest
```

Note: `docker-compose.yml` runs Weaviate **without a persistent volume named outside Docker** (it uses a Docker-managed volume `weaviate_oxcart_data`). Re-indexing is expected during development.

### Parse PDFs → OXCART chunk JSON

```powershell
".venv-clean\Scripts\python.exe" dolphin_transformer.py --input_path .\pdfs\ --save_dir .\results --batch_size 4
```

Outputs `*.oxcart.json` plus markdown/figures under `results/`.

### Enrich + quality-check chunks

```powershell
".venv-clean\Scripts\python.exe" philatelic_patterns.py --input_dir .\results\recognition_json --output_dir .\results\parsed_jsons
".venv-clean\Scripts\python.exe" run_quality_check.py    --input_dir .\results\parsed_jsons    --output_dir .\results\quality_reports
```

### Index into Weaviate

```powershell
".venv-clean\Scripts\python.exe" philatelic_weaviate.py --data_dir .\results\parsed_jsons --action index
```

### Ingest Mena catalog into Neo4j

```powershell
$env:DATA_JSON = "path\to\mena_all_with_raw.json"
".venv-clean\Scripts\python.exe" neo4j_utils\neo4j_ingest_mena_v1.py
".venv-clean\Scripts\python.exe" neo4j_utils\neo4j_index_and_embed.py
```

### Run the UI

Most workflows are driven from notebooks. Open in Jupyter:
- `gradio_app.ipynb` — main Gradio UI (RAG + graph viewer tab)
- `philatelic_rag.ipynb` — Basic/Advanced retrieval pipelines
- `philatelic_kg_builder.ipynb` — knowledge graph construction
- `mena_to_scott_matcher_PRODUCTION.ipynb` — cross-catalog mapping
- `dolphin_parser.ipynb`, `pdfs_processing*.ipynb` — parsing experiments

Standalone Neo4j viewer: `".venv-clean\Scripts\python.exe" neo4j_utils\neo4j_gradio_VIS.py`

### Tests (loose; no pytest harness)

Test scripts are run directly:

Test scripts live under `tests/` (each inserts the repo root on `sys.path`, so run them from the repo root):

```powershell
".venv-clean\Scripts\python.exe" tests\test_enrich_chunk.py
".venv-clean\Scripts\python.exe" tests\test_scott_pattern.py
".venv-clean\Scripts\python.exe" tests\test_bilingual_philatelic.py
".venv-clean\Scripts\python.exe" tests\philatelic_metadata_tests.py
".venv-clean\Scripts\python.exe" tests\test_chunk_optimization.py
".venv-clean\Scripts\python.exe" tests\test_live_vs_ideal.py
".venv-clean\Scripts\python.exe" tests\test_4_systems.py
```

### Raw Dolphin demos (upstream behavior, not the Oxcart pipeline)

```powershell
# Original config-based
".venv-clean\Scripts\python.exe" demo_page.py    --config .\config\Dolphin.yaml --input_path .\demo\page_imgs\page_1.jpeg --save_dir .\results
".venv-clean\Scripts\python.exe" demo_element.py --config .\config\Dolphin.yaml --input_path .\demo\element_imgs\table_1.jpeg --element_type table

# Hugging Face checkpoint
".venv-clean\Scripts\python.exe" demo_page_hf.py    --model_path .\hf_model --input_path .\demo\page_imgs\page_1.jpeg --save_dir .\results
".venv-clean\Scripts\python.exe" demo_element_hf.py --model_path .\hf_model --input_path .\demo\element_imgs\table_1.jpeg --element_type table
```

## Required Environment Variables

`.env` at repo root is read by Weaviate (`docker-compose.yml`) and by the Python pipeline. Required:

```env
OPENAI_API_KEY=sk-...                       # Weaviate text2vec-openai AND retrieval LLM
WEAVIATE_URL=http://localhost:8085          # NOTE: 8085, not the README's 8080
NEO4J_URI=neo4j://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
# Optional tuning (defaults in README §🔒):
HYBRID_ALPHA=0.35
MIN_HYBRID_SCORE=0.20
MIN_COSINE_SIM=0.78
TOPK_BASE=12
TOPK_MAX=32
CONSENSUS_MIN_SOURCES=2
```

The Weaviate client in `philatelic_weaviate.py` hardcodes the gRPC port mapping `8085→50056` to match `docker-compose.yml`. If you change the compose port, update both places.

## Code Style

- Black, line length **120** (configured in `pyproject.toml`).
- Type hints where applicable.
- MIT License headers on upstream Dolphin source files.

## Key Parameters (Dolphin)

- `max_batch_size`: parallel element decoding (default varies per demo)
- `max_length`: 4096 (config)
- `input_size`: `[896, 896]` (Swin encoder)
- `window_size`: 7 (Swin); `decoder_layer`: 10 (MBart)

## Where to look first for…

- **A retrieval bug or scoring weirdness** → `philatelic_rag.ipynb` (pipeline orchestration) and `philatelic_weaviate.py` (collection schema + hybrid call).
- **A metadata extraction bug (wrong Scott number, missing year, etc.)** → `philatelic_patterns.py` (regex/enrichment) and `philatelic_chunk_schema.py` (canonical fields). Add a regression case to `tests/test_scott_pattern.py` / `tests/philatelic_metadata_tests.py`.
- **A Dolphin parsing artifact (bad table, missing figure)** → `dolphin_transformer.py` (`_validate_html_table` and chunk-building) and `dolphin_quality_control.py`.
- **A graph/catalog question** → `neo4j_utils/neo4j_ingest_mena_v1_en.md` (V1 schema doc) and `neo4j_utils/neo4j_technical_guide_cypher_cookbook.md` (Cypher recipes).
- **UI/Gradio behavior** → `gradio_app.ipynb` (main app) and `neo4j_utils/neo4j_gradio_VIS.py` (graph viewer subcomponent).
- **What's actually in the corpus** → `PHILATELIC_LITERATURE.md` (full source catalog). Per-run indexing reports (`indexing_results*.json`, `failed_pdfs.json`) are generated under `results/` and are not committed.
