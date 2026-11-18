# Pipeline

The code that turned the scanned literature and the catalogues into the data the app reads. It is kept as it was
written; it needs the source PDFs, a GPU for the parser, and API keys, none of which are in this repository.

| Step | Files |
|---|---|
| Parse PDFs (Dolphin) and normalise | `dolphin_transformer.py`, `dolphin_quality_control.py`, `run_quality_check.py`, `merge_pdfs.py` |
| Chunk and enrich with philatelic metadata | `philatelic_chunk_logic.py`, `philatelic_chunk_schema.py`, `philatelic_patterns.py`, `chunk_optimizer.py` |
| Index into Weaviate | `philatelic_weaviate.py` |
| Parse the Mena catalogue into structured issues | `mena_catalog_schema.py`, `mena_stamp_agent.py`, `mena_stamp_agent2.py`, `mena_stamp_agent_prompts.py` |
| Knowledge-graph schema | `kg_pydantic.py` |
| One-off analysis scripts | `analysis/` |
| Example outputs of past runs | `sample_outputs/` |

Run scripts from the repository root so relative data paths (`results/`, `pdfs/`) resolve:

```
python pipeline/run_quality_check.py
```

Modules import each other by name; running a script this way puts `pipeline/` on the import path. The Dolphin
parser itself is in `third_party/dolphin/`. Loading the graph into Neo4j is in `neo4j_utils/`, and the First Issue
graph build is in `first_issue_graphrag/`.
