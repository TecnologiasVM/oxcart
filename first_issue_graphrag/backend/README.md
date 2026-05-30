# First Issue KG Explorer — Backend

FastAPI service that exposes the **First Issue GraphRAG** prototype
(`first_issue_graphrag/`) as a read-only HTTP API for the Next.js frontend.

It wraps the prototype's Python API directly — it does **not** reimplement
retrieval. Specifically it wraps:

- `config.neo4j_driver()` / `config.weaviate_client()` — store connections.
- `retrieve.context_bundle(...)` — the retrieval/context bundle (no LLM).
- `examples_runner.DEMO` — the demo questions.

## Owner contracts (hard constraints)

These are non-negotiable and are enforced in code:

1. **No LLM calls.** No direct OpenAI/Anthropic/LLM API calls in this backend.
   The only exception is Weaviate using OpenAI *under the hood* for its own
   vectorizer; BM25 (no key) is the default. There is **no answer-generation
   phase** in this MVP — the API returns retrieved context only.
2. **Weaviate is read-only.**
3. **Neo4j is read-only.** The backend issues only read queries; it never
   writes to the graph.
4. **No embedding/vector fields are ever exposed.** Every node / detail /
   response payload is passed through `app.deps.sanitize_props`, which drops any
   property whose key matches `/embed|vector/i`. Chunk nodes carry no
   embeddings, but Mena `Issue`/`Stamp` nodes may carry one from another
   indexer — it is stripped defensively.

## Layout

```
first_issue_graphrag/backend/
├── app/
│   ├── __init__.py
│   ├── settings.py      # ports, CORS, PKG_DIR + sys.path bootstrap
│   ├── deps.py          # lifespan (Neo4j singleton), get_driver, get_weaviate, sanitize_props
│   ├── schemas.py       # Pydantic v2 request/response models
│   ├── main.py          # app factory: lifespan + CORS + routers + root
│   └── routers/
│       ├── __init__.py
│       ├── graph.py     # (written separately) /api/graph...
│       ├── meta.py      # (written separately) /api/health, /api/overview, /api/examples
│       └── query.py     # (written separately) POST /api/query
└── requirements.txt
```

> `routers/graph.py`, `routers/meta.py`, and `routers/query.py` are authored by
> other agents. `app/main.py` imports them as `from app.routers import graph,
> meta, query`. Until they exist, importing `app.main` will fail — that is
> expected for the skeleton.

## Configuration

- **Backend port:** `8090`
- **Frontend dev origin(s):** `http://localhost:3000`, `http://127.0.0.1:3000`
  (set in `app/settings.py`, used for CORS).

Store connection details come from the prototype's `config.py` (which reads the
repo `.env`): `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`,
`WEAVIATE_URL`, etc. No new env vars are introduced by the backend.

`config` constants surfaced through the prototype:

| Constant | Value |
|---|---|
| `config.ISSUE_ID` | `CR-1863-FIRST-ISSUE` |
| `config.PROTOTYPE_TAG` | `first_issue_graphrag` |
| `config.OXCART_COLLECTION` | `Oxcart` |
| `config.NEO4J_DATABASE` | (from `.env`) |

## Running

Always use the project's `.venv-clean` interpreter. From
`first_issue_graphrag/backend`:

```powershell
# uvicorn (recommended)
..\..\.venv-clean\Scripts\python.exe -m uvicorn app.main:app --port 8090

# or run the module entrypoint (no reload)
..\..\.venv-clean\Scripts\python.exe -m app.main
```

Bash equivalent:

```bash
../../.venv-clean/Scripts/python.exe -m uvicorn app.main:app --port 8090
```

Interactive docs: <http://localhost:8090/docs>

## Endpoints

Mounted under the `/api` prefix (router sub-prefixes are defined in each
router file by the agents who write them). The intended surface:

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/` | Service banner + docs pointer (`{service, docs}`). |
| `GET`  | `/api/health` | `HealthResponse` — Neo4j/Weaviate reachability + graph populated. |
| `GET`  | `/api/overview` | `OverviewResponse` — issue dashboard (totals, series, stamps). |
| `GET`  | `/api/examples` | `list[ExampleQuery]` — demo questions from `examples_runner.DEMO`. |
| `GET`  | `/api/graph...` | `GraphResponse` / `NodeDetail` — subgraph + node detail. |
| `POST` | `/api/query` | `QueryResponse` — wraps `retrieve.context_bundle` (no LLM). |

## Dependencies

See `requirements.txt`. All listed packages are already installed in
`.venv-clean` (FastAPI 0.116.x, Pydantic 2.11.x, uvicorn 0.35.x, `neo4j`,
`weaviate-client`). Do not install into system Python or the Python 3.13
`venv/`.

## Notes for router authors

- Inject the shared Neo4j driver with `Depends(get_driver)` — it is the single
  process-wide pool created in `app.deps.lifespan`. Never open a per-request
  driver.
- For Weaviate, call `get_weaviate()` and **close the client yourself**
  (`try/finally`).
- The prototype's `config.neo4j_driver()` returns a **sync** driver. Inside an
  `async def` route, run blocking queries with
  `fastapi.concurrency.run_in_threadpool`. `retrieve.context_bundle(...)` is
  synchronous and manages its own driver+Weaviate connections — offload it the
  same way.
- Pass every node/edge property dict through `sanitize_props` before returning.
