# Running the hosted demo

How the demo at [oxcart.chat](https://oxcart.chat) is run: its hosts, its limits, the web part's outside service,
and what is in place for running it as a service. Every setting named here is listed in
[backend/README.md](../backend/README.md#settings).

## Free hosting tiers, and their sleep

The demo runs on free hosting tiers and sleeps when nobody uses it; waking it takes about half a minute, and the
stored examples on the page work meanwhile.

**The hosts are free tiers, and two of them stop when unused.** The backend's host puts it to sleep; it wakes in
about half a minute and the page says so. The literature's cluster (Weaviate Cloud, free plan) does not expire,
but its provider suspends a free cluster after 7 days without use, keeping the data, and deletes it after 30
(its documentation, read on 2026-11-22). A scheduled job outside this repository makes one read-only search of
it several times a day, and a heartbeat write to the graph database for the same reason. While either store
cannot be reached the page shows what the other returned and says which one is missing.

## What the limits are, and what they are not

A visitor may ask 10 questions a minute and 100 a day; the service takes 2,000 questions a day and makes at most
200 model calls a day (about 3 USD a month at the measured averages). A written answer takes two or three of
those calls: the query rewriting before the search, for every question; the call that writes the answer; and
one for a web part. So 200 calls are about 100 answered questions a day. A call can also be spent on an answer
that is not shown (a timeout, a failed call, a visitor who left), and the rewriting call is made before it is
known whether a store answers. All of these counts are counters of one process: they live in the server's memory and start again
whenever the service restarts, which on a host that puts an idle service to sleep happens many times a day.
They slow down a running service; they are not a budget. The one limit that cannot be passed is the monthly
spend limit of the model key's workspace at the provider. It is set there, not in this repository, and kept
low; when it is reached the page shows the evidence without a written answer.

## The web part, when it is on

It is on at the hosted demo. It adds a third outside service: the question as it was searched, in the visitor's
language, goes to Tavily, with fixed words after it; its translation and the earlier turns do not, though a
follow-up's rewritten question can hold a subject named in an earlier turn. The question, the pages the search returned and, for a part answer, the answer already
given go to Anthropic for one more model call, which counts toward the day's 200; a web request also counts as
one of the visitor's questions. Settings: `ASK_WEB` and `TAVILY_API_KEY` on the backend, `NEXT_PUBLIC_WEB` in
the page's build, `WEB_QUERY_SUFFIX` for the fixed words. Pages of video and social sites, of marketplaces and
their price guides, and of the search service itself are never used.

## How many searches

The search plan is a free one of 1,000 credits a month with no card: that limit, the provider's own, is the
ceiling, and a month that uses it up shows no web part and costs nothing. Below it the backend paces the
searches: one is allowed while the credits used this month are under `30 + 920 x the share of the month gone
by`, so 950 a month is a pacing target, not a ceiling the backend can hold: a quiet day leaves its share for a
busier one. The count comes from the search service's usage route, read at most once in five minutes. **That
route runs behind** (measured: 26 searches were not in it eleven minutes after the first, and were fifty minutes
after the last), so the backend adds the searches it made itself in the last two hours. After a restart it knows
only what the route says, and can allow a few more than the rule until the route catches up. If the route cannot
be read: 30 searches a day, counted in memory. The read is made while an answer that asks for the web waits for
its ticket, so it can hold that answer back by up to its timeout, 4 s, at most once in five minutes.

## What is in place for running it as a service

- The explorer's query path calls no language model. The written answer of the question page does, twice for
  every question: one small call before the search (query rewriting: it makes a follow-up stand alone and gives
  the question in the other of Spanish and English), measured at 0.00018 USD and 1.0 s (median), and one call to
  write the answer from up to seven passages, 0.0008 USD on average; together 0.001 USD a question on average
  and 0.0016 USD at most ([EVALUATION.md](../EVALUATION.md#the-literature-in-both-languages)). A web part takes
  one more. These costs are the answer
  model's only; the question's embedding and a web search are paid apart. Without a key the page works and
  shows the evidence only.
- Both stores are used read-only.
- One Neo4j connection pool is shared by all requests. Against a hosted Neo4j this took the demo questions from
  5 to 66 seconds (with failed requests) to a median of 2.9 seconds, same passages.
- Responses are bounded: at most 40 graph passages per question, long passages clipped for display, the full text
  available as a separate export.
- Run locally, only the frontend port needs to be reachable; it proxies `/api` to the backend. Everything binds
  to `127.0.0.1` by default. Hosted, there is no proxy: the page is static files, built with the backend's
  address (`NEXT_PUBLIC_API_BASE`), and calls the backend directly. The backend's container listens on the port
  its host gives it, on every interface, in hosted mode (`OXCART_PUBLIC=1`), which answers only the question
  path's routes and lets only the page's origin (`CORS_ORIGINS`) call it from a browser.
- Embedding vectors are stripped from every response.
- Dependencies are pinned.
- A workflow runs what needs no database on every pull request: the Python tests, the frontend's build and the
  build of the hosted site, the browser tests, and the backend's image built and started with no settings.

The hosted demo serves the question path only: a human check before the first question, limits per visitor and
for the whole service, and a subset of the index that fits a free hosting tier, chosen and measured in
[EVALUATION.md](../EVALUATION.md). What it caches: the vectors of the last 256 texts it searched (a question and its
translation are two), in memory, under a digest of each text and with no text, so a repeated question is not
embedded twice. No answer is cached, and
no question's text or conversation is kept between requests.
