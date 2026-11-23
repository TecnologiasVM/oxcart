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

1. **One module calls a language model, and the explorer calls none.** The
   explorer's routes return retrieved context only: no answer is generated and
   no model is called (Weaviate's own vectorizer aside; BM25, which needs no
   key, is the default). The written answer of `POST /api/chat` is the one
   exception: `app/answer_model.py` calls Claude, and nothing else in the
   backend calls a language model. The question's embedding is made in
   `app/ask_service.py`.
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
reached costs its own block only; the question fails (503) when neither answers. A store that has not answered
within `ASK_STORE_SECONDS` (12 s) counts as unavailable for that question, and the other's evidence is returned:
a store that hangs no longer holds back the other. The searches run on two pools of four threads that live as
long as the process, one per store; a late search is not waited for and what it returns is dropped.

**Figures.** A figure on a scanned page was cropped to a file of its own, `<document>_page_N_figure_M.png`, and
the stored text of a passage names the crops of its page (a Markdown image; the reference is dropped from the
shown text). With `FIGURES_BASE` set, a shown passage carries `figures`: for each crop its stored text names, in
order, `{"id", "width", "height", "class"}`. `id` is the crop's public name, the first 20 hex characters of the
SHA-256 of its own name normalised to NFC (the figures host serves `<id>.png`); `width` and `height` are the
file's pixels; `class` is `A` (a stamp) or `B` (a cover or a postal marking). A crop is named only when its id is
in the list the backend ships with, `app/data/figures.tsv` (8,216 lines: id, width, height, class; no name), and
not in `FIGURES_REMOVED`. A crop's own name is never in a response, and a passage with no listed figure has no
`figures` key. The model is not given the figures. The page builds each picture's address from its own build
setting `NEXT_PUBLIC_FIGURES_BASE` and the id (`frontend/lib/figures.ts`): the response holds no address.

| Setting | Effect |
|---|---|
| `FIGURES_BASE` | The address of the figures host, `https://...` (`http://127.0.0.1` or `localhost` for tests). Unset, or any other address: figures are off, no figure is named and the response is what it was without them. It must name the same host as the page's `NEXT_PUBLIC_FIGURES_BASE` |
| `FIGURES_REMOVED` | Comma-separated ids never named, whatever the list says. A removal on request takes effect with a restart; no build. Remove the file from the host too: a conversation kept in a browser keeps the ids it was shown |

With `OXCART_PUBLIC=1` the app runs in **hosted mode**:

| | |
|---|---|
| Routes mounted | `GET /api/health`, `GET /api/ask/examples`, `POST /api/session`, `POST /api/ask`, `POST /api/chat`, and `POST /api/chat/web` only with `ASK_WEB` on. Nothing else: no explorer routes, no export, no figures |
| Docs | `/docs`, `/redoc` and `/openapi.json` are off |
| Human check | The page solves a Cloudflare Turnstile challenge and posts its token to `/api/session`; the backend verifies it with Cloudflare and returns a signed token valid for an hour, sent as `X-Oxcart-Session` with each question. If the check cannot be verified, questions are refused with a message |
| Limits | 10 questions a minute and 100 a day per visitor, 2,000 a day for the service, in memory; a question is at most 300 characters and a request 2 kB (a chat 8 kB, a web part its own limit, the human check's token up to 2,048 characters, any other POST the smallest). A body's size is held before it is read (`app/body_limit.py`): a missing or larger `Content-Length` is refused with 413 at once, and so is a body whose bytes pass the limit whatever the header said; a body must arrive within `BODY_READ_SECONDS` (10 s), or 408. A visitor is counted twice, by address (an IPv6 address by its first 64 bits) and by session token, and a question passes only when both are under the limits |
| CORS | The origins in `CORS_ORIGINS`, GET and POST, no credentials |
| Errors | `{"error": code, "message": text}`; no exception text, nothing of the request repeated |
| Logs | One line per question with the mode, the timings and error classes. No question text, no address |

Settings, all from the environment (`app/settings.py`): `OXCART_PUBLIC`, `CORS_ORIGINS`, `WEAVIATE_URL` and
`WEAVIATE_API_KEY` (a Weaviate Cloud cluster; without `WEAVIATE_URL` the local instance is used),
`OPENAI_API_KEY`, `TURNSTILE_SECRET`, `SESSION_SIGNING_KEY`, `EVAL_ACCESS_KEY` (the eval's own way in, a secret
header; empty means that door does not exist), `TRUSTED_PROXY_HOPS`, `VISITOR_ADDRESS_HEADER`, the `ASK_*` bounds
(among them `ASK_STORE_SECONDS`), `BODY_READ_SECONDS`,
for the written answer `ANTHROPIC_API_KEY` and the `ANSWER_*` settings, for figures `FIGURES_BASE` and
`FIGURES_REMOVED`, and for the web step `ASK_WEB`, `TAVILY_API_KEY` and `WEB_QUERY_SUFFIX`.

Without `OXCART_PUBLIC` nothing changes for local use: the explorer's routes are mounted as before, and
`/api/ask` and `/api/chat` work without a session.

### The written answer

`POST /api/chat` takes a question, and the earlier turns of its conversation when it is a follow-up, and returns
the same evidence followed by a short answer whose sentences cite it. The steps are a graph (LangGraph,
`app/answer_graph.py`):

| Step | What it does | Model |
|---|---|---|
| `contextualize` | Only for a follow-up: rewrites it as a question that stands alone ("and its perforation?" becomes a question that names the issue). If that fails, the question is used as written | one call |
| `retrieve` | The question path above, unchanged | none |
| `write` | A short answer from the shown evidence, with citations (`app/answer_model.py`) | one call |
| `check` | Keeps the sentences that carry a citation that holds, drops the others, and names why there is no answer when there is none | none |

- **Why a graph.** Each step is given only the part of the state it declares. The earlier turns come from the
  browser, so they are a visitor's text: `contextualize` is the only step that receives them, and `write`
  receives the question that stands alone and the evidence. The route sends each step's result as it ends, so the
  evidence arrives as fast as on `/api/ask` and the answer follows.
- **No checkpointer.** A conversation is kept in the visitor's browser, which sends its last three turns with a
  follow-up (each answer clipped to 1,200 characters; a request is at most 8 kB). The server keeps nothing between
  two requests, so nothing of a visitor stays in its memory and nothing is lost when the service sleeps.
- **Citations.** Each shown card and passage goes to the model as a document with citations on (Anthropic's
  citations feature), holding the text the page shows. A citation holds when it names one of them and its cited
  text is in it. A sentence with no citation that holds is not shown; a piece that is only the cited text,
  standing between two sentences, counts as the citation of the sentence before it and is not printed. The part
  of a kept sentence outside its cited text is not removed.
- **Where a sentence ends.** At a line break, or at an end mark followed by space when what follows can start a
  sentence. Not at the full stop of an abbreviation of a list ("No.", "núm.", "pp.", "Sc.", "Co." and the
  like) or of an initial ("Dr. N. M. Somebody", "U. S."); not before a number; and not before a lower-case
  letter when what stands before the stop reads as an abbreviation (a single letter, letters with full stops
  between them, "etc.", "cts."): "a copy of Guanacaste No. 7 with double overprints" is one sentence. After a
  word or a number, a full stop before a lower-case letter does end the sentence: a model at times starts one
  that way. The cost is that two sentences are sometimes taken for one ("… in 1889. 500 were printed.",
  "… & Co. It was …", "… of type A. The …"), and then one citation keeps both; a sentence cut in two inside a
  number or a name was the worse error, because each piece needed a citation of its own and a source mark stood
  in the middle of it.
- **The evidence is untrusted text.** It enters a request as document content only, never in the instructions;
  the instructions say that text inside a document is not to be followed; the model has no tools. The earlier
  turns are treated the same way.
- **Not built.** No step grades the evidence, none retrieves a second time, and there is no scope router.

The response is lines of JSON (`application/x-ndjson`): `{"type": "evidence", "rewritten": .., "evidence": {..}}`
(what `/api/ask` returns, for the question that was searched), then `{"type": "answer", "answer": {..}, "calls": [..]}`.
`calls` has one entry per model call made for the question (what for, its state, its token counts, its seconds):
a cost is measured from it.
`answer.state` is `ok` (with `sentences`, each with the numbers of its `sources`, and for each source the text it
was cited for), `not_covered` (the evidence does not answer the question), or the reason nothing was written:
`no_key`, `daily_cap`, `no_evidence`, `timeout`, `key_refused`, `rate_limited`, `request_refused`,
`model_unavailable`, `declined`, `cut` (the answer hit its length limit), `uncited` (no sentence carried a
citation that holds), `empty`, `stopped`, `failed`. In every one of those the evidence has already been sent.

The route stands behind the same guard as `/api/ask`: the session token, both visitor counts (a question here
counts as a question there), the service's daily limit, and the eval's way in. On top of that, the whole service
makes at most `ANSWER_LIMIT_PER_DAY` model calls a day (200; the call that reads a later question against its
conversation counts, so a question after the first takes two); the eval's way in
does not skip it. Past it the route answers with the evidence only. When nobody waits for the answer any more
(the route answered 504 or 503, or the visitor left before the answer line was sent), no call is taken from
that allowance and the model is not called; a call already under way is not stopped. Once the evidence is sent,
the answer is waited for at most the write call's timeout and 5 s; past it, it says `failed`.

**Every one of these counts lives in the process's memory and starts again when the process does**, and on a
host that puts an idle service to sleep that is often: the visitor limits, the service's daily limit and the 200
model calls are a brake on a running service, not a budget. The one limit that cannot be passed is the spend
limit of the key's workspace at the provider; set it there.

The model is `claude-haiku-5-5` at effort `low`, its lowest, with thinking on: at most 500 output tokens for an
answer plus 1,500 of room for the thinking, 120 for a rewrite, 12 and 5 seconds, no retry.
`ANSWER_THINKING=disabled` turns thinking off; the evaluation compared the two ([EVALUATION.md](../EVALUATION.md)).
The model's client is
made as the process starts, in the background and without a request, so the first answer does not wait for it. Without
`ANTHROPIC_API_KEY` the route works and answers with the evidence only (`no_key`). The log line of a question
holds the answer's state, the citation counts and each call's token counts; no question and no answer.

### The web step (`ASK_WEB`, off by default)

With `ASK_WEB` on, the write call tells apart three ways of not answering in full: `OUT_OF_SCOPE` (state
`out_of_scope`), `NOT_COVERED` (state `not_covered`), and an answer that ends with a last line `PART_ONLY` (state
`ok` with `covers: "part"`; a full answer has `covers: "all"`). The marker's line is taken out before sentences
are counted and is never sent to the page. The model is also told that a card is from the Mena catalogue.

For `not_covered`, and for `ok` with `covers: "part"`, when `TAVILY_API_KEY` is set and a search is allowed
(below), the chat reply's answer carries `web: {"ticket": .., "expires_in": 120}`. `out_of_scope` never does,
and no ticket is made when the catalogue or the literature did not answer: that our sources do not cover the
question is not known then.
The ticket is an HMAC-SHA256, with a key made when the process starts and held in memory only (no secret to
set), over a random id, a digest of the question as it was searched (`evidence.question`), a digest of the
answer's text (its shown sentences joined with a space; empty for `not_covered`), the state and an expiry
120 s ahead. It holds no text. A restart makes the tickets of the last two minutes invalid.

`POST /api/chat/web` takes `{"question": <evidence.question>, "answer": <the answer's text, or "">, "ticket": ..}`
(at most 4 kB). It stands behind the chat route's guard (the session in hosted mode, both visitor counts, where
it counts as a question, the service's daily limit, the eval's way in), then refuses with 403 `ticket_refused` a
ticket that does not verify for that question and answer, is expired or was used (a ticket is good once; used
ids are kept in memory until they expire). Then, in this order: a search is reserved, the check that it is
allowed and its count in one step, so two requests at the limit cannot both search; one model call is taken
from the day's allowance (`ANSWER_LIMIT_PER_DAY`), so a day whose calls are spent never spends a search (the
reservation is then released); the search is made, and stays counted whatever it returns, since the service
may have charged it. When the search fails, times out or leaves no result to write from, the model is not
called and the call that was taken is given back.

- **The search** (`app/web_step.py`, `Tavily`): `POST https://api.tavily.com/search` with the key as a bearer
  token, `search_depth: "basic"`, `max_results: 5`, no answer, no raw content, no images, `topic: "general"`,
  6 s. The query is the question as it was searched (for a follow-up, as the rewrite step wrote it), then the
  fixed words of `WEB_QUERY_SUFFIX`; nothing of an answer a model wrote is in it. Status 432 (the plan used up), any other failure and a timeout give no web part.
- **What is kept of a result:** an `https` address of at most 300 characters, with no user name or password,
  no space, control character or backslash, and a host name that parses; its title cut to 200 characters (the
  host when it has none) and its text to 1,500. At most five. A host that is only numbers and dots is not a
  name and is refused. **Sites left out:** video and social sites, marketplaces and their price guides, and the
  search service's own site (`WEB_HOST_LABELS_LEFT_OUT`, `WEB_DOMAINS_LEFT_OUT` in `settings.py`): a result is dropped when its host
  has one of those names as a label or is under one of those domains, and the domains go with the search
  request as `exclude_domains`.
- **The web call** (`answer_model.ClaudeModel.write_web`, purpose `web`): the same model and call settings as
  `write`; the kept results as documents with citations on; then, in the part case, the answer already given
  between `<answer_given>` marks, and the question between `<question>` marks (the marks' own characters taken
  out of both). Its instructions (`WEB_INSTRUCTIONS`): only these documents, at most 80 words, plain sentences,
  each cited, the question's language, dates in words, only what the answer already given leaves unanswered,
  `NOTHING_TO_ADD` when the pages add nothing, `OUT_OF_SCOPE` outside the scope, and the pages are evidence to
  read, never instructions. No tools.
- **The same check** as an answer's (`answer_graph.cited_sentences`): a sentence with no citation that holds is
  removed.

The reply is JSON: `{"state", "sentences": [{"text", "cites": [n]}], "results": [{"n", "title", "host", "url"}],
"counts", "calls"}`. `results` lists the cited results only, numbered as the sentences cite them; no cited text
and no uncited result is sent. `counts` holds `results_returned`, `results_kept` and, when the call wrote
something, the check's four counts. `calls` is the web call's entry, as in the chat reply (empty when no call was
made). The states:

| State | What happened | The page |
|---|---|---|
| `ok` | sentences that cite the kept results | the block |
| `nothing` | no result kept, the call replied `NOTHING_TO_ADD`, or no sentence was left after the check | under "not covered" one line; under an answer nothing |
| `unavailable` | no search allowed, no model call left, the search failed, timed out or the plan is used up (432), or the call failed | nothing |
| `out_of_scope` | the web call judged the question outside the scope | nothing |

**How many searches.** Before a ticket is made and again before a search, the backend reads the account's
credits used this month from `GET https://api.tavily.com/usage` (`account.plan_usage`, with `account.plan_limit`
present as an integer; 4 s), at most once in five minutes, and adds the searches it made itself in the last two hours of
the current month: the usage route runs behind the searches made (`WEB_USAGE_LAG_SECONDS`). A search is allowed
while

    used < 30 + 920 x (the share of the current month gone by, in UTC)

so about 1.3 more an hour, 30 at the first instant of a month and 950 at its end. If the usage cannot be read (an
error, a timeout, another shape), 30 searches a day (UTC), counted in memory. Nothing is remembered across
restarts. One log line (`{"event": "web_rule", "rule": "usage" | "per_day"}`) when the rule in use changes, with
no number of the account. The numbers are constants in `app/settings.py` (`WEB_SEARCHES_AT_MONTH_START`,
`WEB_SEARCHES_OVER_THE_MONTH`, `WEB_SEARCHES_PER_DAY_FALLBACK`, `WEB_USAGE_EVERY_SECONDS`), as are the time-outs
and the cuts (`WEB_*`). The read is made by one request at a time and outside the lock that counts the searches;
other requests meanwhile use the last value read. It can add up to 4 s to the one chat answer that makes it,
once in five minutes.

**Logs.** The chat line gains `web_ticket` (true or false) with `ASK_WEB` on. The web route's line holds the
ticket's state, the reply's state and why (`reason`), the rule in use, the counts, the timings (`search_ms`,
`write_ms`, `total_ms`) and the call: never the question, a result, an address or a host.

**Later turns.** A follow-up sends the earlier answers from our sources, as before; the web part is never sent
(a thread turn holds `question` and `answer` only, and anything else is refused).

**Off** (the default), the write call's instructions and their reading are the ones served before, the chat
reply carries no ticket, and `/api/chat/web` is not mounted (404, as any unknown path).

Tests, with fakes in place of the stores and of the model: `python -m pytest backend/tests`.
To score the test set through a running backend: `python -m eval.ask_arm --label <name>` (see `EVALUATION.md`).

## Deploying the hosted mode

Two parts, both on free plans that cannot bill: the backend as a container, the page as static files.

**Backend.** `backend/Dockerfile`, built from the repository root. The image runs the hosted mode
(`OXCART_PUBLIC=1` is set in it), listens on `PORT` (8000 without it), runs as a non-root user and writes no
access log. It holds no key and no data other than the list of figures that may be named (ids and pixel sizes,
no name). The host provides these settings, as secrets where it has them:

| Setting | What it is |
|---|---|
| `CORS_ORIGINS` | The page's origin, for example `https://example.org` |
| `WEAVIATE_URL`, `WEAVIATE_API_KEY` | The literature cluster and a **read-only** key |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | The catalogue graph |
| `OPENAI_API_KEY` | A key limited to embeddings, with a spend limit. Without it the backend answers in keyword mode |
| `ANTHROPIC_API_KEY` | Optional: a key for the written answer, in a workspace with a spend limit. Without it `/api/chat` answers with the evidence only |
| `TURNSTILE_SECRET` | The human check's secret key |
| `SESSION_SIGNING_KEY` | A long random string; signs the session tokens |
| `EVAL_ACCESS_KEY` | Optional: a long random string that lets the eval and the page's build in without the human check |
| `FIGURES_BASE`, `FIGURES_REMOVED` | Optional: the figures host and the ids never named (see "Figures" above). Without `FIGURES_BASE` no figure is named |
| `ASK_WEB` | Optional (`1`, `true`, `yes`, `on`): the three markers of the write call and the web step (see "The web step"). Unset: as before |
| `TAVILY_API_KEY` | Optional, with `ASK_WEB`: the search service's key, its own and no other's. Without it no ticket is made and no search is ever made |
| `WEB_QUERY_SUFFIX` | Optional: the fixed words after the question in a search (default `Costa Rica philately`; empty means none) |
| `ASK_STORE_SECONDS` | Optional: each store's deadline for one question, in seconds (default 12). A store that has not answered by then is unavailable for that question |
| `BODY_READ_SECONDS` | Optional: the time a POST's whole body may take to arrive, in seconds (default 10); past it the answer is 408 |
| `TRUSTED_PROXY_HOPS` | How many of the host's proxies stand in front of the app (default 1). Check it on the host: the visitor limit must follow the caller, and a made-up `X-Forwarded-For` must not change it |
| `VISITOR_ADDRESS_HEADER` | Optional: the header in which the host's edge reports the visitor's address, for example `CF-Connecting-IP` where Cloudflare stands in front. With it the visitor limit follows that header; a request without it falls back to `TRUSTED_PROXY_HOPS`. Use it where no entry of `X-Forwarded-For` is the visitor, and check it the same way: a made-up value from a client must not change the count, and two real addresses must be counted apart |

Health check path: `/api/health`. One instance: the limits are counted in the process's memory.
A service that sleeps when idle wakes on the first request; the page calls `/api/health` as it opens and tells
the visitor what is happening in short lines that follow one another (waking the service, connecting to the
catalogue and the literature, searching), with a count of seconds.

**The graph connection.** A hosted graph can refuse a new connection and accept the next one half a second
later. So the process opens its connection as it starts, in the background, retrying every half second for up
to 30 seconds (`GRAPH_STARTUP_BUDGET_SECONDS`), and keeps one driver for its whole life. `/api/health` does not
wait for it: it answers at once with `graph` set to `connecting`, `connected` or `unavailable`, and the page
keeps saying "starting" while it is `connecting`. A question that finds no connection retries for up to 8
seconds (`GRAPH_QUESTION_BUDGET_SECONDS`) before its catalogue block says "unavailable"; the passages do not wait
for it. A query error is not retried.

**The literature client and the embedding's connection.** Opening the Weaviate client and the first connection
to the embedding service is what the first question after a start used to wait for. Both are opened as the
process starts, in the background too (`ASK_WARM_ON_START`, on by default); the embedding's connection is opened
with one tiny embedding per start, and later questions reuse it while it is kept open. `/api/health` reports
them beside the graph: `literature` and `embedding` are `connecting`, `connected` or `unavailable` (`not started`
when nothing was opened at startup; `embedding` is `not configured` without a key). The page says "connecting"
while any of the three is `connecting`. A literature search that fails retires the client it used, unless a
newer one has replaced it; the next search opens a new one, and a retired client is closed once no search is
using it.

**Page.** In `frontend/`: `npm ci && npm run build:hosted` writes the static site to `out/` (the question page
only). At build time:

| Setting | What it is |
|---|---|
| `NEXT_PUBLIC_API_BASE` | The backend's address (required) |
| `NEXT_PUBLIC_TURNSTILE_SITE_KEY` | The human check's public site key |
| `NEXT_PUBLIC_WEB` | Optional (`1`, `true`, `yes`, `on`): the page asks for the web part and its privacy paragraph names Tavily. Build with it only when the backend has `ASK_WEB` on; without it a ticket is ignored |
| `EXAMPLES_EVAL_KEY` | Optional, the backend's `EVAL_ACCESS_KEY`: the build then asks the example questions and stores their evidence in `public/stored-examples.json`, which the page shows while the service is asleep. That file holds excerpts of the literature and is not kept in the repository |

**Literature cluster.** `scripts/load_cluster.py` rebuilds the collection on a Weaviate Cloud cluster from an
export (passages and their stored vectors). The export is not in this repository.

## Dependencies

See `requirements.txt` (pinned: FastAPI 0.116.2, Pydantic 2.12.5, uvicorn 0.35.0,
`neo4j` 6.4.1, `weaviate-client` 4.24.1, `anthropic` 2.12.0, `langgraph` 1.2.24). Install it into a Python 3.10+ virtual
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
