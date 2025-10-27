# OXCART RAG — Philatelic Research & Document Intelligence

<div align="center">
  <img src="./assets/oxcart_logo.svg" width="300" alt="OXCART RAG Logo">
  <br><br>

  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-lightgray" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python"></a>
  <a href="https://weaviate.io/"><img src="https://img.shields.io/badge/Vector%20DB-Weaviate-00cc66" alt="Weaviate"></a>
  <a href="https://openai.com/"><img src="https://img.shields.io/badge/Embeddings-OpenAI-000000" alt="OpenAI Embeddings"></a>
  <a href="https://www.landing.ai/"><img src="https://img.shields.io/badge/PDF%20Parser-Landing.ai%20ADE-3333aa" alt="Landing.ai ADE"></a>
  <a href="https://gradio.app/"><img src="https://img.shields.io/badge/UI-Gradio-ff6c3f" alt="Gradio"></a>
</div>

## 🎬 Demo

<div align="center">

[![OXCART RAG Demo](https://img.youtube.com/vi/mLhTES6oDtE/maxresdefault.jpg)](https://www.youtube.com/watch?v=mLhTES6oDtE)

**[Try the live demo →](https://huggingface.co/spaces/oxcart/philatelic-rag)** *(Public demo link coming soon)*

</div>

---

## 📋 Overview

**OXCART RAG** is a domain-specialized Retrieval-Augmented Generation system for philatelic research (Costa Rica focus). It ingests complex PDF literature (catalogs, journals, monographs, exhibits), normalizes structure, indexes **193,180 text chunks** from **1,424 documents**, and serves trustworthy answers with first-class citations.

> 📚 **[View Complete Literature Catalog →](PHILATELIC_LITERATURE.md)** — Comprehensive documentation of all 1,424 source documents, organized by category with detailed statistics.

The system combines:

- **Robust PDF parsing** (primary: Dolphin; selectively: Landing.ai ADE for difficult layouts)
- **High-recall, high-precision retrieval** over Weaviate
- **Domain filters** (e.g., Scott numbers, year ranges, issue types)
- **Multi-stage re-ranking and context compression**
- **Guardrails** for minimum similarity thresholds and grounded answers

This README supersedes the earlier project doc and keeps the same spirit while reflecting the current architecture, tooling, and retrieval strategies.

---

## 🧠 What's New

### Two Retrieval Tiers

**Basic (fast)**: Hybrid (BM25+vector) with MMR and domain filters.

**Advanced (accurate)**: Multi-query expansion (LLM-generated variants), union retrieval, summary compression, and multi-rerank (hybrid score + MMR + domain priors).

### Confidence & Safety

- **Adaptive k** with score thresholds: refuse/clarify if evidence is weak
- **Dedup & consensus** across sources; mandatory citations

### Parsing Upgrades

- **Landing.ai ADE** added for selected PDFs with complex tables/figures

### Philatelic Schema & Filters

- First-class support for **Scott numbers**, **year spans**, **issue notices**, **varieties**

---

## 🗂️ Corpus & Indexing Snapshot

- **Total chunks**: 193,180
- **Unique PDFs**: 1,424
- **Total pages**: 22,940
- **Temporal coverage**: 1863-2025 (162 years of philatelic history)

> 📖 **Detailed breakdown available**: [PHILATELIC_LITERATURE.md](PHILATELIC_LITERATURE.md) — Complete catalog with all source documents, authors, and statistics.

### Chunk Types
- **text** (148,980)
- **header** (22,790)
- **marginalia** (15,073)
- **decree** (2,797)
- **footer** (1,746)
- **caption** (666)
- **issue_notice** (620)
- **auction_result** (508)

### Collection Highlights
- Catalogs (e.g., **Scott 2024**, **Mena 2018**)
- **AFCR Boletín** (192 complete issues, 2009-2025)
- **Oxcart Collection** (257 specialized research papers)
- **Government Bulletins** (521 official postal bulletins, 1970-2023)
- **Costa Rica Philatelist** (34 historical issues, 1952-1955)
- **Costa Rican Philatelic Federation** materials (142 CRF journals)
- **Repertorio Filatélico** by Fred O'Neill (428 documents)
- Postal history monographs (247+ pages by Frajola, Castro, Mitchell)
- Forgery studies (Raul Hernandez: 177 pages)
- Specialized books and exhibits (85+ documents)

---

## 🧭 Retrieval Approaches

### Tier 1 — Basic (Fast & Strong Baseline)

- **Hybrid search** (Weaviate `hybrid()`): BM25 + vector; **alpha = 0.35**
- **MMR re-ranking** to diversify
- **Philatelic filters** (optional):
  - `year_start`–`year_end` (auto-sorted)
  - `scott_numbers` (catalog = "Scott")
- **Quality gates**:
  - Min hybrid score (e.g., >= 0.20)
  - Min cosine similarity (for pure vector mode; e.g., >= 0.78)
- **Adaptive top-k**: expand from k to k′ if threshold unmet, else fail safely with a helpful clarification prompt

### Tier 2 — Advanced (Maximum Answer Quality)

#### Multi-query expansion
Generate **3 high-quality query variants** with an LLM (+ original user query).

#### Parallel retrieval
Run hybrid for each query; union results; source-balanced sampling.

#### Multi-stage re-rank

- **Stage A**: Hybrid score desc + MMR (diversity)
- **Stage B**: Domain priors bonus (e.g., exact Scott/years hit, `issue_notice`, presence of figures/captions)
- **Stage C**: Cross-encoder optional (if enabled)

#### Summary compression
Trim long chunks into faithful summaries that preserve citations.

#### Final selection
Choose top N_ctx with coverage constraints (avoid same-page clustering; prefer multi-source corroboration).

#### Answering with guardrails
If coverage < threshold or evidence conflicts → return "insufficient evidence" with suggested refinements.

---

## 🔒 Confidence Thresholding (Recommended Defaults)

```python
# Retrieval acceptance gates (tune per collection)
MIN_HYBRID_SCORE      = 0.20     # for Weaviate hybrid metadata.score
MIN_COSINE_SIM        = 0.78     # for near_text distance→similarity
TOPK_BASE             = 12       # start k
TOPK_MAX              = 32       # expand k if under threshold
CONSENSUS_MIN_SOURCES = 2        # min distinct documents
```

### Fail-safe behavior (no low-confidence answers):

If `< CONSENSUS_MIN_SOURCES` or all scores `< thresholds` → return a clarifying prompt ("Provide Scott number / years / issue keywords") instead of speculating.

---

## 🧱 Data Model & Domain Filters

### Key metadata (per chunk) indexed in Weaviate:

- `doc_id`, `chunk_id`, `chunk_type`, `page_number`
- `text`, `text_original` (with figure dedupe)
- `catalog_systems`, `catalog_numbers`, `scott_numbers`
- `years`, `colors`, `topics_primary`, `variety_classes`
- Flags: `has_catalog`, `has_prices`, `has_varieties`, `is_guanacaste`
- `quality_score` (ingestion-time heuristic)

### Filter examples

**Year span**: `year_start=1881, year_end=1883`

**Scott**: `scott_numbers=["CR 55","CR 56"]` (catalog pinned to "Scott")

---

## 🏗️ Architecture

```
PDFs → (Dolphin | Landing.ai ADE) → JSON/Markdown → Chunker/Normalizer
    → Quality checks → Weaviate (OpenAI embeddings) → RAG Orchestrator
    → (Basic or Advanced Retrieval) → Context Compression → Answer & Citations
```

### PDF Parsers

- **Primary**: Dolphin (structure, figures, captions)
- **Selective fallback**: Landing.ai ADE (improved table/figure fidelity)

### Embeddings

- **OpenAI** (e.g., `text-embedding-3-large`), cosine distance

### Vector DB

- **Weaviate** (hybrid, BM25, near_text, metadata filters)

---

## ⚙️ Installation

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Git LFS (if you store large parser checkpoints)

### 1. Clone

```bash
git clone https://github.com/omontes/oxcart.git
cd oxcart
```

### 2. Install

```bash
pip install -r requirements.txt
```

### 3. Environment

Create `.env`:

```env
# Weaviate
WEAVIATE_URL=http://localhost:8080
WEAVIATE_API_KEY=your_weaviate_key

# OpenAI
OPENAI_API_KEY=your_openai_key
OPENAI_EMBED_MODEL=text-embedding-3-large

# Parsing
PARSER_BACKEND=dolphin          # dolphin | landing_ai_ade | auto
ADE_API_KEY=your_landing_ai_key # if using ADE for selected PDFs

# RAG
HYBRID_ALPHA=0.35
MIN_HYBRID_SCORE=0.20
MIN_COSINE_SIM=0.78
TOPK_BASE=12
TOPK_MAX=32
CONSENSUS_MIN_SOURCES=2
```

### 4. Start Weaviate

```bash
docker-compose -f weaviate_docker_compose.yml up -d
```

---

## 🚀 Usage

### A) Parse PDFs

```bash
# Primary parser
python dolphin_transformer.py \
  --input_path ./pdfs/ \
  --save_dir ./results \
  --batch_size 4

# (Optional) Re-parse selected PDFs with Landing.ai ADE
python ade_transformer.py \
  --input_path ./pdfs/hard_layouts/ \
  --save_dir ./results_ade \
  --only_overwrite_if_better
```

### B) Enrich & Validate

```bash
python philatelic_patterns.py \
  --input_dir ./results/recognition_json \
  --output_dir ./results/parsed_jsons

python run_quality_check.py \
  --input_dir ./results/parsed_jsons \
  --output_dir ./results/quality_reports
```

### C) Index in Weaviate

```bash
python philatelic_weaviate.py \
  --data_dir ./results/parsed_jsons \
  --action index
```

### D) Query — Basic Tier

```python
from rag.search import search_and_answer_basic

resp = search_and_answer_basic(
    query="When were the 1881–82 surcharges demonetized?",
    rag_system={"client": weaviate_client, "collection_name": "Oxcart"},
    year_start=1881, year_end=1883,
    scott_numbers=["CR 55","CR 56"],
    max_results=10
)
print(resp["answer"])
print(resp["metadata"])
```

### E) Query — Advanced Tier

```python
from rag.search import search_and_answer_advanced

resp = search_and_answer_advanced(
    query="Identify forged overprints for UPU 1883 surcharge and cite sources.",
    rag_system={"client": weaviate_client, "collection_name": "Oxcart"},
    multiquery_n=3,      # original + 3 LLM variants
    ctx_size=1800,       # target compressed context tokens
    topk_base=12, topk_max=32
)
```

The advanced pipeline performs multi-query retrieval, merges & re-ranks, compresses to faithful summaries with citations, applies score/consensus thresholds, and only then drafts the final answer.

---

## 📁 Project Structure

```
oxcart/
├── 📄 README.md                           # Project documentation
├── 📄 CLAUDE.md                           # Development guidelines
├── 📚 PHILATELIC_LITERATURE.md            # Complete corpus documentation (1,424 sources)
├── 🐳 weaviate_docker_compose.yml         # Vector database setup
│
├── 📊 dolphin_transformer.py              # Main PDF parsing engine (Dolphin)
├── 🔍 philatelic_patterns.py              # Philatelic metadata extraction
├── 🗄️ philatelic_weaviate.py              # Weaviate vector DB integration
├── 🏥 dolphin_quality_control.py          # Quality assessment system
├── ⚙️ run_quality_check.py                # Quality control runner
├── 📊 chat.py                             # DOLPHIN model interface
│
├── 🧩 philatelic_chunk_logic.py           # Chunk processing logic
├── 📋 philatelic_chunk_schema.py          # Schema definitions
├── 🏛️ mena_stamp_agent.py                 # MENA catalog processing
├── 🏛️ mena_catalog_schema.py              # MENA schema definitions
│
├── 📓 gradio_app.ipynb                    # Interactive web UI (Gradio)
├── 📓 philatelic_rag.ipynb                # RAG pipeline notebook
├── 📓 dolphin_parser.ipynb                # Document parsing experiments
├── 📓 philatelic_kg_builder.ipynb         # Knowledge graph construction
├── 📓 mena_to_scott_matcher_PRODUCTION.ipynb  # Catalog matching
│
├── 🧪 test_enrich_chunk.py                # Chunk enrichment tests
├── 🧪 test_scott_pattern.py               # Scott number extraction tests
├── 🧪 test_bilingual_philatelic.py        # Bilingual processing tests
├── 🧪 philatelic_metadata_tests.py        # Metadata validation tests
│
├── 📁 utils/                              # Helper modules
├── 📁 config/                             # Model configurations
├── 📁 assets/                             # Images and diagrams
├── 📁 checkpoints/                        # Model checkpoints
├── 📁 deployment/                         # Deployment configs
├── 📁 pdfs/                               # Source documents
├── 📁 results/                            # Processing outputs
└── 📁 graph_outputs/                      # Knowledge graph outputs
```

---

## ⚖️ Configuration Knobs

- **HYBRID_ALPHA** (default 0.35): blend between BM25 and vector
- **MIN_HYBRID_SCORE** / **MIN_COSINE_SIM**: acceptance thresholds
- **TOPK_BASE**, **TOPK_MAX**: adaptive recall window
- **CONSENSUS_MIN_SOURCES**: robustness to single-source bias
- **multiquery_n**: number of LLM expansions (3 recommended)
- **ctx_size**: target compressed context size (tokens)
- **use_cross_encoder**: toggle final neural re-rank pass

---

## 🧪 Quality, Safety & Monitoring

- **Grounding**: Every answer references `doc_id`/`page` with links when available
- **Thresholds**: Refuse to answer if all candidates fall below MIN_HYBRID_SCORE/MIN_COSINE_SIM
- **Consensus**: Prefer evidence drawn from ≥2 sources
- **De-duplication**: Hash (`doc_id`, `page`, canonicalized text) to avoid repeated evidence
- **MMR Diversity**: Reduce redundancy; improve coverage across issues/years
- **Eval Harness**: Offline notebooks to:
  - Sweep alpha (hybrid), k, thresholds
  - LLM-judge rubric for accuracy, grounding, coverage
  - Per-query telemetry (latency, token cost)

---

## 📊 Benchmarks (indicative)

- Retrieval **alpha=0.35** performed best in philatelic queries combining exact nomenclature (Scott numbers, year spans) with narrative text
- **Multi-query + multi-rerank** increased Top-k@5 grounded answer rate vs baseline hybrid by **~8–15%** (internal rubric)

*(Your mileage may vary; use the eval harness to calibrate on your queries.)*

---

## 🧰 Dev Notes

- **Embedding model**: `text-embedding-3-large` (cosine) recommended for long-tail philatelic terminology
- **Tokenizer drift**: keep embedder consistent across (re)indexing
- **PDF fallbacks**: enable ADE only for documents where table/figure fidelity matters; prefer single source of truth per PDF to avoid duplication

---

## 🖥️ Gradio Interface

Start the UI:

```bash
# Launch from notebook
jupyter notebook gradio_app.ipynb
```

### Features:

- Query mode toggle (Basic / Advanced)
- Filters panel (Scott / year range / issue types)
- Live evidence cards with per-chunk scores and jump-to-page links
- Confidence banner (green ≥ threshold; amber near; red below)

---

## 🚢 Deployment

```bash
docker-compose up -d
# scale workers
docker-compose up -d --scale worker=4
```

### Production checklist

- Persistent Weaviate volume & nightly backups
- HTTPS + API auth
- Centralized logging (OpenTelemetry)
- Periodic re-embedding/eval after schema or parser updates

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [**Weaviate**](https://weaviate.io/) - Vector database for hybrid search
- [**OpenAI**](https://openai.com/) - High-quality embeddings
- [**Dolphin**](https://github.com/bytedance/Dolphin) - PDF structure extraction
- [**Landing.ai ADE**](https://www.landing.ai/) - High-fidelity parsing on selected PDFs
- **Philatelic community & contributors** - For sharing knowledge and resources

---

<div align="center">
  <i>Built with ❤️ for stamp history, scholarship, and collectors.</i>
</div>
