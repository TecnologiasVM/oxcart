# Oxcart backend

The API, in FastAPI (Python 3.10+). It serves the question path that the hosted page uses (`POST /api/ask`, the
written answer `POST /api/chat`, and the web part `POST /api/chat/web`) and, in local use, the routes of the
First Issue explorer ([docs/EXPLORER.md](../docs/EXPLORER.md)). The shared modules (settings of the stores, the
catalogue lookup, the explorer's retrieval) are the `oxcart` package at the repository root, installed with
`python -m pip install -e .`.

## Rules the code keeps

1. **One module calls a language model:** `app/answer_model.py`, for the written answer of `POST /api/chat` and
   the web part. One module calls an embedding service: `app/ask_service.py`, for the question's vector. One
   module calls the web search service: `app/web_step.py`, and only with `ASK_WEB` on. The explorer's routes call
   none and write no answer (Weaviate's own vectorizer aside: the explorer's search is BM25, which needs no key,
   with a hybrid pass added when an OpenAI key is set).
2. **Weaviate is read-only.**
3. **Neo4j is read-only.** The backend issues only read queries.
4. **No embedding or vector field is sent.** The explorer's payloads pass through `app.deps.sanitize_props` and
   the question path's through `_without_vectors` in `app/ask_service.py`; both drop any key that names an
   embedding or a vector.

## Layout

```
backend/
├── app/
│   ├── main.py            the app: middleware, error handlers, the routes of each mode
│   ├── settings.py        every setting the backend reads from the environment, and its fixed bounds
│   ├── deps.py            startup and shutdown (one Neo4j driver, the graph link, warm-up), sanitize_props
│   ├── routers/
│   │   ├── ask.py         GET /api/health (hosted mode), GET /api/ask/examples, POST /api/session, POST /api/ask
│   │   ├── chat.py        POST /api/chat, and POST /api/chat/web with ASK_WEB on
│   │   ├── meta.py        the explorer: GET /api/health (local mode), GET /api/overview
│   │   ├── query.py       the explorer: GET /api/examples, POST /api/query, POST /api/query/export
│   │   ├── graph.py       the explorer: GET /api/graph, GET /api/graph/stamp/{cno}, GET /api/node
│   │   └── mena.py        the explorer: GET /api/mena/...
│   ├── ask_service.py     the question path: embedding, catalogue lookup, literature search
│   ├── answer_graph.py    the written answer's steps, as a LangGraph graph, and the citation check
│   ├── answer_model.py    the model's calls (Claude Haiku 5.5) and their instructions
│   ├── web_step.py        the web part: its ticket, how many searches, the search, the results kept
│   ├── public_guard.py    the human check, the session token, the limits, the eval's way in
│   ├── body_limit.py      the size and the time of a POST's body, held before anything reads it
│   ├── graph_link.py      the process's link to the graph, with retries inside a budget
│   ├── figures.py         the figures a shown passage names, by digest
│   ├── passage_text.py    a passage's stored text as it is shown
│   ├── data/figures.tsv   the figures that may be named (8,082 lines: digest, width, height, class; no name)
│   ├── query_service.py, graph_service.py, mena_service.py, mena_data.py    the explorer's services
│   └── schemas.py         Pydantic v2 models of the explorer's routes
├── tests/                 pytest, with fakes in place of the stores and the model
├── test_mena_backend.py   checks of the explorer's Mena routes, against Neo4j
├── Dockerfile             the hosted mode's image
└── requirements.txt       pinned
```

## Run it

With the project's virtual environment active and the `oxcart` package installed, from `backend`:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8090   # this machine only
python -m app.main                                            # the same, host and port from API_HOST / API_PORT
```

Or both servers, backend and frontend, from the repository root: `python scripts/servers.py start` (also `status`
and `stop`). In local mode the interactive docs are at <http://localhost:8090/docs>.

## The question path: `POST /api/ask`

One question in, the evidence out, for any issue. No written answer.

1. The backend makes the question's embedding (`text-embedding-3-large`, the question as asked). The embedding
   key is used for that call only; it is never given to the vector store.
2. `catalogue_lookup.lookup` (`oxcart/catalogue_lookup.py`) finds the issue in the graph: with the embedding
   through the vector index over issues, and with `ASK_SHORT_VECTOR` on through the short vector index too;
   without the embedding through the full-text index. With the short index on and missing from the graph, the
   lookup runs without it and the log says so.
3. The literature store is searched: `near_vector` with the embedding, `bm25` without it.

Steps 2 and 3 run side by side. The answer carries `issues` (three), `passages` (five, text clipped to 700
characters), `timings`, and a `mode` block that says what produced each part: `embedding` (`ok`, `failed`,
`not configured`), `catalogue` (`vector index`, `full-text index`, `unavailable`), `literature` (`vector`,
`keyword`, `unavailable`). A store that cannot be reached costs its own block only; the question fails (503) when
neither answers. A store that has not answered within `ASK_STORE_SECONDS` (12 s) counts as unavailable for that
question, and the other's evidence is returned: a store that hangs does not hold back the other. The searches run
on two pools of four threads that live as long as the process, one per store; a late search is not waited for
and what it returns is dropped.

**Figures.** A figure on a scanned page was cropped to a file of its own, `<document>_page_N_figure_M.png`, and
the stored text of a passage names the crops of its page (a Markdown image; the reference is dropped from the
shown text). With `FIGURES_BASE` set, a shown passage carries `figures`: for each crop its stored text names, in
order, `{"id", "width", "height", "class"}`. `id` is the crop's public name, the first 20 hex characters of the
SHA-256 of its own name normalised to NFC (the figures host serves `<id>.png`); `width` and `height` are the
file's pixels; `class` is `A` (a stamp) or `B` (a cover or a postal marking). A crop is named only when its id is
in `app/data/figures.tsv` and not in `FIGURES_REMOVED`. A crop's own name is never in a response, and a passage
with no listed figure has no `figures` key. The model is not given the figures. The page builds each picture's
address from its own build setting `NEXT_PUBLIC_FIGURES_BASE` and the id (`frontend/lib/figures.ts`): the response
holds no address.

## The written answer: `POST /api/chat`

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
  follow-up (each answer clipped to 1,200 characters; a request is at most 8 kB). The server keeps no question's
  text and no conversation between two requests, so no visitor's text stays in its memory and nothing of a
  conversation is lost when the service sleeps. What it does keep in memory: the vectors of the last 256
  questions, under a digest and with no text (the embedding cache, `app/ask_service.py`); no answer is cached.
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
A shown sentence that took a citation from a quote standing after it carries `quoted`: `all` when every citation
it has came from quotes (without that rule it would not be shown), `some` when it has one of its own too; `counts`
says how many shown sentences are of each kind (`sentences_cited_by_a_quote_only`, `sentences_cited_by_a_quote_too`).
A web part's sentences carry the same field and counts.

The route stands behind the same guard as `/api/ask`: the session token, both visitor counts (a question here
counts as a question there), the service's daily limit, and the eval's way in. On top of that, the whole service
makes at most `ANSWER_LIMIT_PER_DAY` model calls a day (200; the call that reads a later question against its
conversation counts, so a question after the first takes two); the eval's way in does not skip it. Past it the
route answers with the evidence only. When nobody waits for the answer any more (the route answered 504 or 503,
or the visitor left before the answer line was sent), no call is taken from that allowance and the model is not
called; a call already under way is not stopped. Once the evidence is sent, the answer is waited for at most the
write call's timeout and 5 s; past it, it says `failed`.

**Every one of these counts lives in the process's memory and starts again when the process does**, and on a
host that puts an idle service to sleep that is often: the visitor limits, the service's daily limit and the 200
model calls are a brake on a running service, not a budget. The one limit that cannot be passed is the spend
limit of the key's workspace at the provider; set it there.

The model is `claude-haiku-5-5` at effort `low`, its lowest, with thinking on: at most 500 output tokens for an
answer plus 1,500 of room for the thinking, 120 for a rewrite, 12 and 5 seconds, no retry.
`ANSWER_THINKING=disabled` turns thinking off; the evaluation compared the two ([EVALUATION.md](../EVALUATION.md)).
The model's client is made as the process starts, in the background and without a request, so the first answer
does not wait for it. Without `ANTHROPIC_API_KEY` the route works and answers with the evidence only (`no_key`).
The log line of a question holds the answer's state, the citation counts and each call's token counts; no
question and no answer.

## The web part: `POST /api/chat/web` (`ASK_WEB`, off by default)

With `ASK_WEB` on, the write call tells apart three ways of not answering in full: `OUT_OF_SCOPE` (state
`out_of_scope`), `NOT_COVERED` (state `not_covered`), and an answer that ends with a last line `PART_ONLY` (state
`ok` with `covers: "part"`; a full answer has `covers: "all"`). The marker's line is taken out before sentences
are counted and is never sent to the page. The model is also told that a card is from the Mena catalogue.

For `not_covered`, and for `ok` with `covers: "part"`, when `TAVILY_API_KEY` is set and a search is allowed
(below), the chat reply's answer carries `web: {"ticket": .., "expires_in": 120}`. An answer in state
`out_of_scope` gets none, and no ticket is made when the catalogue or the literature did not answer: that our
sources do not cover the question is not known then. The state is the model's judgment: a question outside the
scope that the model answers in part gets a ticket, as one did in a published run (`oos-013-en` in
`eval/outcomes/answers_hosted-y.json`).
The ticket is an HMAC-SHA256, with a key made when the process starts and held in memory only (no secret to
set), over a random id, a digest of the question as it was searched (`evidence.question`), a digest of the
answer's text (its shown sentences joined with a space; empty for `not_covered`), the state and an expiry
120 s ahead. It holds no text. A restart makes the tickets of the last two minutes invalid.

`POST /api/chat/web` takes `{"question": <evidence.question>, "answer": <the answer's text, or "">, "ticket": ..}`.
The answer's text is the whole written answer, since the ticket signs it, so it has a limit of its own,
`WEB_ANSWER_CHARS` (10,000 characters: five for each token the write call may use, its 500 and the thinking's
1,500, where English and Spanish prose take about four or fewer), and the body `WEB_MAX_BODY_BYTES` (62,612
bytes: the answer and the question at six bytes a character, as JSON can write an accented letter, the ticket
and the JSON around them). The model is given that answer whole: it is the backend's own text, as the ticket
proves. It stands behind the chat route's guard (the session in hosted mode, both visitor counts, where
it counts as a question, the service's daily limit, the eval's way in), then refuses with 403 `ticket_refused` a
ticket that does not verify for that question and answer, is expired or was used (a ticket is good once; used
ids are kept in memory until they expire). Then, in this order: a search is reserved, the check that it is
allowed and its count in one step, so two requests at the limit cannot both search; one model call is taken
from the day's allowance (`ANSWER_LIMIT_PER_DAY`), so a day whose calls are spent never spends a search (the
reservation is then released); the search is made, and stays counted whatever it returns, since the service
may have charged it. When the search fails, times out or leaves no result to write from, the model is not
called and the call that was taken is given back.

- **The search** (`app/web_step.py`, Tavily): `POST https://api.tavily.com/search` with the key as a bearer
  token, `search_depth: "basic"`, `max_results: 5`, no answer, no raw content, no images, `topic: "general"`,
  6 s. The query is the question as it was searched (for a follow-up, as the rewrite step wrote it), then the
  fixed words of `WEB_QUERY_SUFFIX`; nothing of an answer a model wrote is in it. Status 432 (the plan used up),
  any other failure and a timeout give no web part.
- **What is kept of a result:** an `https` address of at most 300 characters, with no user name or password,
  no space, control character or backslash, and a host name that parses; its title cut to 200 characters (the
  host when it has none) and its text to 1,500. At most five. A host that is only numbers and dots is not a
  name and is refused. **Sites left out:** video and social sites, marketplaces and their price guides, and the
  search service's own site (`WEB_HOST_LABELS_LEFT_OUT`, `WEB_DOMAINS_LEFT_OUT` in `settings.py`): a result is
  dropped when its host has one of those names as a label or is under one of those domains, and the domains go
  with the search request as `exclude_domains`.
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
present as an integer; 4 s), at most once in five minutes, and adds the searches it made itself in the last two
hours of the current month: the usage route runs behind the searches made (`WEB_USAGE_LAG_SECONDS`). A search is
allowed while

    used < 30 + 920 x (the share of the current month gone by, in UTC)

so about 1.3 more an hour, 30 at the first instant of a month and 950 at its end. If the usage cannot be read (an
error, a timeout, another shape), 30 searches a day (UTC), counted in memory. Nothing is remembered across
restarts. One log line (`{"event": "web_rule", "rule": "usage" | "per_day"}`) when the rule in use changes, with
no number of the account. The numbers are constants in `app/settings.py` (`WEB_SEARCHES_AT_MONTH_START`,
`WEB_SEARCHES_OVER_THE_MONTH`, `WEB_SEARCHES_PER_DAY_FALLBACK`, `WEB_USAGE_EVERY_SECONDS`), as are the time-outs
and the cuts and sizes (`WEB_*`). The read is made by one request at a time and outside the lock that counts the
searches; other requests meanwhile use the last value read. It can add up to 4 s to the one chat answer that
makes it, once in five minutes.

**Logs.** The chat line gains `web_ticket` (true or false) with `ASK_WEB` on. The web route's line holds the
ticket's state, the reply's state and why (`reason`), the rule in use, the counts, the timings (`search_ms`,
`write_ms`, `total_ms`) and the call: never the question, a result, an address or a host.

**Later turns.** A follow-up sends the earlier answers from our sources, as before; the web part is never sent
(a thread turn holds `question` and `answer` only, and anything else is refused).

**Off** (the default), the write call's instructions and their reading are the ones served before, the chat
reply carries no ticket, and `/api/chat/web` is not mounted (404, as any unknown path).

## Hosted mode (`OXCART_PUBLIC=1`)

| | |
|---|---|
| Routes mounted | `GET /api/health`, `GET /api/ask/examples`, `POST /api/session`, `POST /api/ask`, `POST /api/chat`, and `POST /api/chat/web` only with `ASK_WEB` on; and `GET /`, which names the service. Nothing else: no explorer routes, no export, no figures |
| Docs | `/docs`, `/redoc` and `/openapi.json` are off |
| Human check | The page solves a Cloudflare Turnstile challenge and posts its token to `/api/session`; the backend verifies it with Cloudflare and returns a signed token valid for an hour, sent as `X-Oxcart-Session` with each question. If the check cannot be verified, questions are refused with a message |
| Limits | 10 questions a minute and 100 a day per visitor, 2,000 a day for the service, in memory; a question is at most 300 characters and a request 2 kB (a chat 8 kB, a web part about 61 kB, the human check's token up to 2,048 characters, any other POST the smallest). A body's size is held before it is read (`app/body_limit.py`): a missing or larger `Content-Length` is refused with 413 at once, and so is a body whose bytes pass the limit whatever the header said; a body must arrive within `BODY_READ_SECONDS` (10 s), or 408. A visitor is counted twice, by address (an IPv6 address by its first 64 bits) and by session token, and a question passes only when both are under the limits |
| CORS | The origins in `CORS_ORIGINS`, GET and POST, no credentials |
| Errors | `{"error": code, "message": text}`; no exception text, nothing of the request repeated |
| Logs | One line per question with the mode, the timings and error classes. No question text, no address |

`GET /api/health` in hosted mode makes no store round trip: it answers at once with `graph`, `literature` and
`embedding`, each `connecting`, `connected` or `unavailable` (`not started` when nothing was opened at startup;
`embedding` is `not configured` without a key). The page says "connecting" while any of the three is
`connecting`.

Without `OXCART_PUBLIC` nothing changes for local use: the explorer's routes are mounted, and `/api/ask` and
`/api/chat` work without a session.

## The explorer's routes

Mounted in local mode only (without `OXCART_PUBLIC`), under `/api`. They return retrieved context only and call
no model. The explorer's page is described in [docs/EXPLORER.md](../docs/EXPLORER.md) and
[frontend/README.md](../frontend/README.md).

| Method | Path | What it returns |
|---|---|---|
| `GET` | `/api/health` | Whether Neo4j and Weaviate are reachable and the graph is populated (each probed) |
| `GET` | `/api/overview` | The First Issue overview: totals, series, stamps |
| `GET` | `/api/examples` | The explorer's demo questions (`examples_runner.DEMO`) |
| `GET` | `/api/graph` | The First Issue's subgraph and its top documents (`clean`, `max_docs`, `chunks_per_doc`, `min_score`) |
| `GET` | `/api/graph/stamp/{cno}` | A subgraph around one stamp, by its Mena number |
| `GET` | `/api/node?node_id=` | One node's detail (404 when unknown) |
| `POST` | `/api/query` | The context bundle of `oxcart/retrieve.py` (`context_bundle`), with a subgraph and figures for display |
| `POST` | `/api/query/export` | The same evidence as a full-text `.txt` download |
| `GET` | `/api/mena/surface-mail` | The Surface Mail issues of the Mena catalogue, by year |
| `GET` | `/api/mena/issue/{issue_id}` | One issue's facts and its Scott match |
| `GET` | `/api/mena/issue/{issue_id}/graph` | A small graph of the issue |
| `GET` | `/api/mena/issue/{issue_id}/evidence` | BM25 passages for the issue (`?k=`, 0 to 25) |
| `GET` | `/api/figures/<file>` | The page-figure crops, when `results/markdown/figures` exists on the machine |

`MENA_SECTION`, `MENA_EVIDENCE_K` and `MENA_EVIDENCE_MIN_SCORE` (below) tune the `/api/mena/*` routes.

## Settings

All from the environment. `app/settings.py` reads the question path's and the service's; `oxcart/config.py`
reads the stores' and `OPENAI_API_KEY`; `app/mena_service.py` reads the `MENA_*` ones. Before any of them is
read, `oxcart/env.py` loads the repository's `.env` (or the file `OXCART_ENV_FILE` names) when `python-dotenv` is
installed; a variable set in the real environment wins over the file. A setting with no default below is empty
unless set.

| Setting | Default | What it does |
|---|---|---|
| **The process** | | |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8090` | Where `python -m app.main` listens |
| `OXCART_PUBLIC` | off | Hosted mode (above) |
| `CORS_ORIGINS` | `http://localhost:3000`, `http://127.0.0.1:3000` | Allowed origins, comma separated; replaces the default |
| **The stores** | | |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | `bolt://127.0.0.1:7687`, `neo4j`, empty, `neo4j` | The catalogue graph |
| `WEAVIATE_URL` | | A Weaviate Cloud cluster for the question path; without it the local instance below is used |
| `WEAVIATE_HOST`, `WEAVIATE_HTTP_PORT`, `WEAVIATE_GRPC_PORT` | `localhost`, `8085`, `50056` | The local Weaviate (the ports of `docker-compose.yml`) |
| `WEAVIATE_API_KEY` | | The Weaviate key, when the instance needs one |
| `OXCART_COLLECTION` | `Oxcart` | The literature collection |
| `OXCART_VECTOR_NAME` | | The vector to search when the collection has several |
| `OPENAI_API_KEY` | | The question's embedding. Without it the question path uses the full-text index and keyword search |
| **The question path** | | |
| `ASK_ISSUES`, `ASK_PASSAGES`, `ASK_TEXT_LIMIT` | `3`, `5`, `700` | Issues and passages returned, and the characters shown of a passage |
| `ASK_EXCERPT` | `start` | `nearest`: show the stretch of a long passage that shares most words with the question |
| `ASK_SHORT_VECTOR` | off | Also ask the short vector index of the issues (`scripts/issue_short_vectors.py` writes it) |
| `ASK_MAX_QUESTION_CHARS`, `ASK_MAX_BODY_BYTES` | `300`, `2048` | A question's length and the body of `/api/ask` |
| `ASK_TIMEOUT_SECONDS`, `ASK_STORE_SECONDS`, `EMBED_TIMEOUT_SECONDS` | `25`, `12`, `5` | The route's deadline, each store's deadline, the embedding call's timeout |
| `BODY_READ_SECONDS` | `10` | The time a POST's whole body may take to arrive; past it 408 |
| `GRAPH_WARM_ON_START`, `ASK_WARM_ON_START` | on, on | Open the graph, the literature client, the embedding's connection and the model's client as the process starts, in the background |
| `GRAPH_STARTUP_BUDGET_SECONDS`, `GRAPH_QUESTION_BUDGET_SECONDS`, `GRAPH_RETRY_EVERY_SECONDS` | `30`, `8`, `0.5` | How long the graph connection is retried at startup and for a question, and how often |
| **Visitors** | | |
| `ASK_LIMIT_PER_MINUTE`, `ASK_LIMIT_PER_DAY`, `ASK_LIMIT_GLOBAL_PER_DAY` | `10`, `100`, `2000` | Questions per visitor a minute and a day, and for the service a day |
| `TRUSTED_PROXY_HOPS` | `1` | How many of the host's proxies stand in front of the app; the visitor's address is read that many entries from the right of `X-Forwarded-For` (`0`: the socket's peer) |
| `VISITOR_ADDRESS_HEADER` | | The header in which the host's edge reports the visitor's address, for example `CF-Connecting-IP`; a request without it falls back to `TRUSTED_PROXY_HOPS` |
| `TURNSTILE_SECRET` | | The human check's secret key |
| `SESSION_SIGNING_KEY`, `SESSION_TTL_SECONDS` | , `3600` | Signs the session tokens (a long random string); their life |
| `EVAL_ACCESS_KEY` | | The eval's way in, a secret header; empty means that door does not exist |
| **The written answer** | | |
| `ANTHROPIC_API_KEY` | | The model's key. Without it `/api/chat` answers with the evidence only |
| `ANSWER_EFFORT`, `ANSWER_THINKING` | `low`, on | The model's effort; `ANSWER_THINKING=disabled` turns thinking off |
| `ANSWER_MAX_TOKENS`, `ANSWER_THINKING_ROOM_TOKENS`, `REWRITE_MAX_TOKENS` | `500`, `1500`, `120` | Output tokens of an answer, the thinking's room on top of it, and of a rewrite |
| `ANSWER_TIMEOUT_SECONDS`, `REWRITE_TIMEOUT_SECONDS` | `12`, `5` | The two calls' timeouts |
| `ANSWER_LIMIT_PER_DAY` | `200` | Model calls a day for the whole service |
| `CHAT_MAX_BODY_BYTES` | `8192` | The body of `/api/chat` |
| **Figures** | | |
| `FIGURES_BASE` | | The figures host, `https://...` (`http://127.0.0.1` or `localhost` for tests). Unset, or any other address: figures are off. It must name the same host as the page's `NEXT_PUBLIC_FIGURES_BASE` |
| `FIGURES_REMOVED` | | Comma-separated ids never named. A removal takes effect with a restart; remove the file from the host too: a conversation kept in a browser keeps the ids it was shown |
| **The web part** | | |
| `ASK_WEB` | off | The three markers of the write call and the web part (`1`, `true`, `yes`, `on`) |
| `TAVILY_API_KEY` | | The search service's key, its own and no other's. Without it no ticket is made and no search is ever made |
| `WEB_QUERY_SUFFIX` | `Costa Rica philately` | The fixed words after the question in a search; empty means none |
| **The explorer** | | |
| `MENA_SECTION`, `MENA_EVIDENCE_K`, `MENA_EVIDENCE_MIN_SCORE` | `Surface Mail`, `6`, `0.0` | The section the `/api/mena/*` routes show, their BM25 passages, and the score under which a passage is dropped |
| `FIRST_ISSUE_*` | see `oxcart/config.py` | The First Issue linker's thresholds and the explorer's bounds |

The web part's other numbers (the search's time-outs, the cuts of a result, the sites left out, the rule of how
many searches) are constants in `app/settings.py`, not settings.

## Tests

```bash
python -m pytest backend/tests          # from the repository root
cd backend && python test_mena_backend.py
```

`backend/tests` runs with fakes in place of the stores, the model and the search service: no network, no database
and no key. It covers the question path, the written answer and its graph, the web part, the body limit, the
graph link, figures, the excerpt and the shown text of a passage. The workflow runs it on every pull request with
`eval/tests`, `oxcart/tests` and `pipeline/first_issue_graph/tests`.

`test_mena_backend.py` checks the explorer's Mena routes and needs Neo4j; Weaviate is optional (without it the
evidence is an empty list). Its checks that need the catalogue match files run only when those files are on the
machine.

To ask the test set through a running backend: `python -m eval.ask_arm --label <name>` for the evidence of
`/api/ask`, and `python -m eval.chat_arm run --label <name>` for the written answers of `/api/chat`
(see [EVALUATION.md](../EVALUATION.md#run-it)).

## The Dockerfile and the hosted deployment

Two parts, both on free plans that cannot bill: the backend as a container, the page as static files. What the
hosted demo runs on, and its limits, are in [docs/OPERATIONS.md](../docs/OPERATIONS.md).

**Backend.** `backend/Dockerfile`, built from the repository root:

```bash
docker build -f backend/Dockerfile -t oxcart-backend .
docker run --rm -p 8000:8000 --env-file <your settings> oxcart-backend
```

The image is `python:3.12-slim` with the pinned packages and the `oxcart` package. It runs the hosted mode
(`OXCART_PUBLIC=1` is set in it), listens on `PORT` (8000 without it), runs as a non-root user and writes no
access log. It holds no key and no data other than the list of figures that may be named (ids and pixel sizes,
no name). The workflow builds it on every pull request, starts it with no settings and checks that it runs as a
user other than root.

The host provides, as secrets where it has them: `CORS_ORIGINS` (the page's origin); `WEAVIATE_URL` and a
**read-only** `WEAVIATE_API_KEY`; the four `NEO4J_*`; `OPENAI_API_KEY` (a key limited to embeddings, with a spend
limit); `ANTHROPIC_API_KEY` (optional, in a workspace with a spend limit); `TURNSTILE_SECRET`;
`SESSION_SIGNING_KEY`; and, as it needs them, `EVAL_ACCESS_KEY`, `FIGURES_BASE` and `FIGURES_REMOVED`, `ASK_WEB`
with `TAVILY_API_KEY` and `WEB_QUERY_SUFFIX`, `ASK_SHORT_VECTOR`, `ASK_STORE_SECONDS`, `BODY_READ_SECONDS`,
`TRUSTED_PROXY_HOPS` and `VISITOR_ADDRESS_HEADER`. Check the last two on the host: the visitor limit must follow
the caller, a made-up `X-Forwarded-For` or address header from a client must not change it, and two real
addresses must be counted apart.

Health check path: `/api/health`. One instance: the limits are counted in the process's memory.
A service that sleeps when idle wakes on the first request; the page calls `/api/health` as it opens and tells
the visitor what is happening in short lines that follow one another (waking the service, connecting to the
catalogue and the literature, searching), with a count of seconds.

**The graph connection.** A hosted graph can refuse a new connection and accept the next one half a second
later. So the process opens its connection as it starts, in the background, retrying every half second for up
to 30 seconds (`GRAPH_STARTUP_BUDGET_SECONDS`), and keeps one driver for its whole life. `/api/health` does not
wait for it, and the page keeps saying "starting" while the graph is `connecting`. A question that finds no
connection retries for up to 8 seconds (`GRAPH_QUESTION_BUDGET_SECONDS`) before its catalogue block says
"unavailable"; the passages do not wait for it. A query error is not retried.

**The literature client and the embedding's connection.** Opening the Weaviate client and the first connection
to the embedding service is what the first question after a start used to wait for. Both are opened as the
process starts, in the background too (`ASK_WARM_ON_START`, on by default); the embedding's connection is opened
with one tiny embedding per start, and later questions reuse it while it is kept open. A literature search that
fails retires the client it used, unless a newer one has replaced it; the next search opens a new one, and a
retired client is closed once no search is using it.

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

`requirements.txt`, pinned: FastAPI 0.116.2, Pydantic 2.12.5, uvicorn 0.35.0, `neo4j` 6.4.1, `weaviate-client`
4.24.1, `anthropic` 2.12.0, `langgraph` 1.2.24, and the rest it lists. Install it into a Python 3.10+ virtual
environment, from the repository root:

```bash
python -m pip install -r backend/requirements.txt
python -m pip install -e .          # the shared modules (oxcart/)
```

## Adding a route

- Inject the shared Neo4j driver with `Depends(get_driver)`: it is the one process-wide pool created in
  `app.deps.lifespan`. Never open a driver per request.
- For Weaviate, call `get_weaviate()` and **close the client yourself** (`try/finally`).
- The driver is synchronous. Inside an `async def` route, run blocking queries with
  `fastapi.concurrency.run_in_threadpool`. `retrieve.context_bundle(...)` is synchronous and manages its own
  driver and Weaviate connections: offload it the same way.
- Pass every node and edge property dict through `sanitize_props` before returning it.
