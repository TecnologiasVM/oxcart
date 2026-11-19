# First Issue KG Explorer — Backend

FastAPI service that exposes the **First Issue GraphRAG** prototype
(the `oxcart/` package) as a read-only HTTP API for the Next.js frontend.

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
backend/
├── app/
│   ├── __init__.py
│   ├── settings.py      # ports, CORS, the question path's limits and keys
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
`WEAVIATE_URL`, etc.

### Mena Catalogue tunables (optional; safe defaults)

Read once at import in `app/mena_service.py` via `os.getenv` (never hardcoded).
Add to the repo `.env` to override:

| Var | Default | Effect |
|---|---|---|
| `MENA_SECTION` | `Surface Mail` | The `Issue.section` the `/api/mena/*` endpoints scope to. |
| `MENA_EVIDENCE_K` | `6` | Default BM25 passages for `/issue/{id}/evidence` (router caps `0..25`). |
| `MENA_EVIDENCE_MIN_SCORE` | `0.0` | Drop BM25 hits below this score (`0` = keep all). |

`config` constants surfaced through the prototype:

| Constant | Value |
|---|---|
| `config.ISSUE_ID` | `CR-1863-FIRST-ISSUE` |
| `config.PROTOTYPE_TAG` | `first_issue_graphrag` |
| `config.OXCART_COLLECTION` | `Oxcart` |
| `config.NEO4J_DATABASE` | (from `.env`) |

## Running

With the project's virtual environment active, from `backend`:

```bash
# uvicorn (recommended); listens on this machine only
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090

# or run the module entrypoint (no reload; host/port from API_HOST / API_PORT)
python -m app.main
```

To start the backend and the frontend together, on any OS:

```bash
python scripts/servers.py start    # from the repo root; also: status, stop
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
| `GET`  | `/api/mena/surface-mail` | `SurfaceMailResponse` — Surface-Mail issues grouped by year (fast). |
| `GET`  | `/api/mena/issue/{issue_id}` | `MenaIssueDetail` — fast per-issue facts + Scott match. |
| `GET`  | `/api/mena/issue/{issue_id}/graph` | `GraphResponse` — lazy per-issue mini-graph. |
| `GET`  | `/api/mena/issue/{issue_id}/evidence` | `MenaEvidenceResponse` — lazy Weaviate BM25 passages (`?k=`). |

## The question path and the hosted mode

`POST /api/ask` takes one question and returns the evidence for it, for any issue. No written answer.

1. The backend makes the question's embedding (`text-embedding-3-large`, the question as asked). The embedding
   key is used for that call only; it is never given to the vector store.
2. `catalogue_lookup.lookup` finds the issue in the graph: with the embedding through the vector index over
   issues, without it through the full-text index.
3. The literature store is searched: `near_vector` with the embedding, `bm25` without it.

The answer carries `issues`, `passages` (five, text clipped to 700 characters), `timings`, and a `mode` block that
says what produced each part: `embedding` (`ok`, `failed`, `not configured`), `catalogue` (`vector index`,
`full-text index`, `unavailable`), `literature` (`vector`, `keyword`, `unavailable`). A store that cannot be
reached costs its own block only; the question fails (503) when neither answers.

With `OXCART_PUBLIC=1` the app runs in **hosted mode**:

| | |
|---|---|
| Routes mounted | `GET /api/health`, `GET /api/ask/examples`, `POST /api/session`, `POST /api/ask`. Nothing else: no explorer routes, no export, no figures |
| Docs | `/docs`, `/redoc` and `/openapi.json` are off |
| Human check | The page solves a Cloudflare Turnstile challenge and posts its token to `/api/session`; the backend verifies it with Cloudflare and returns a signed token valid for an hour, sent as `X-Oxcart-Session` with each question. If the check cannot be verified, questions are refused with a message |
| Limits | 10 questions a minute and 100 a day per visitor, 2,000 a day for the service, in memory; a question is at most 300 characters and a request 2 kB |
| CORS | The origins in `CORS_ORIGINS`, GET and POST, no credentials |
| Errors | `{"error": code, "message": text}`; no exception text, nothing of the request repeated |
| Logs | One line per question with the mode, the timings and error classes. No question text, no address |

Settings, all from the environment (`app/settings.py`): `OXCART_PUBLIC`, `CORS_ORIGINS`, `WEAVIATE_URL` and
`WEAVIATE_API_KEY` (a Weaviate Cloud cluster; without `WEAVIATE_URL` the local instance is used),
`OPENAI_API_KEY`, `TURNSTILE_SECRET`, `SESSION_SIGNING_KEY`, `EVAL_ACCESS_KEY` (the eval's own way in, a secret
header; empty means that door does not exist), `TRUSTED_PROXY_HOPS`, and the `ASK_*` bounds.

Without `OXCART_PUBLIC` nothing changes for local use: the explorer's routes are mounted as before, and
`/api/ask` works without a session.

Tests, with fakes in place of the stores: `python -m pytest backend/tests`.
To score the test set through a running backend: `python -m eval.ask_arm --label <name>` (see `EVALUATION.md`).

## Deploying the hosted mode

Two parts, both on free plans that cannot bill: the backend as a container, the page as static files.

**Backend.** `backend/Dockerfile`, built from the repository root. The image runs the hosted mode
(`OXCART_PUBLIC=1` is set in it), listens on `PORT` (8000 without it), runs as a non-root user and writes no
access log. It holds no key and no data. The host provides these settings, as secrets where it has them:

| Setting | What it is |
|---|---|
| `CORS_ORIGINS` | The page's origin, for example `https://example.org` |
| `WEAVIATE_URL`, `WEAVIATE_API_KEY` | The literature cluster and a **read-only** key |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | The catalogue graph |
| `OPENAI_API_KEY` | A key limited to embeddings, with a spend limit. Without it the backend answers in keyword mode |
| `TURNSTILE_SECRET` | The human check's secret key |
| `SESSION_SIGNING_KEY` | A long random string; signs the session tokens |
| `EVAL_ACCESS_KEY` | Optional: a long random string that lets the eval and the page's build in without the human check |
| `TRUSTED_PROXY_HOPS` | How many of the host's proxies stand in front of the app (default 1). Check it on the host: the visitor limit must follow the caller, and a made-up `X-Forwarded-For` must not change it |

Health check path: `/api/health`. One instance: the limits are counted in the process's memory.
A service that sleeps when idle wakes on the first request; the page calls `/api/health` as it opens and tells
the visitor the service is starting.

**The graph connection.** A hosted graph can refuse a new connection and accept the next one half a second
later. So the process opens its connection as it starts, in the background, retrying every half second for up
to 30 seconds (`GRAPH_STARTUP_BUDGET_SECONDS`), and keeps one driver for its whole life. `/api/health` does not
wait for it: it answers at once with `graph` set to `connecting`, `connected` or `unavailable`, and the page
keeps saying "starting" while it is `connecting`. A question that finds no connection retries for up to 8
seconds (`GRAPH_QUESTION_BUDGET_SECONDS`) before its catalogue block says "unavailable"; the passages do not wait
for it. A query error is not retried.

**Page.** In `frontend/`: `npm ci && npm run build:hosted` writes the static site to `out/` (the question page
only). At build time:

| Setting | What it is |
|---|---|
| `NEXT_PUBLIC_API_BASE` | The backend's address (required) |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | The human check's public site key |
| `EXAMPLES_EVAL_KEY` | Optional, the backend's `EVAL_ACCESS_KEY`: the build then asks the example questions and stores their evidence in `public/stored-examples.json`, which the page shows while the service is asleep. That file holds excerpts of the literature and is not kept in the repository |

**Literature cluster.** `scripts/load_cluster.py` rebuilds the collection on a Weaviate Cloud cluster from an
export (passages and their stored vectors). The export is not in this repository.

## Dependencies

See `requirements.txt` (pinned: FastAPI 0.116.2, Pydantic 2.12.5, uvicorn 0.35.0,
`neo4j` 6.4.1, `weaviate-client` 4.24.1). Install it into a Python 3.10+ virtual
environment:

```bash
python -m pip install -r backend/requirements.txt
python -m pip install -e .          # the shared modules (oxcart/), from the repo root
```

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
