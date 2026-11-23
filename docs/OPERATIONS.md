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
200 model calls a day (about 4 USD a month at the measured average). The page has one question box, so every
question after a conversation's first takes two of those calls: the day's allowance is between 100 and 200
written answers. All of these counts live in the server's memory and start again whenever the service restarts,
which on a host that puts an idle service to sleep happens many times a day. They slow down a running service;
they are not a budget. The one limit that cannot be passed is the monthly spend limit of the model key's
workspace at the provider. It is set there, not in this repository (9 USD for November 2026); when it is reached
the page shows the evidence without a written answer.

## The web part, when it is on

It is on at the hosted demo. It adds a third outside service: the question as it was searched goes to Tavily,
with fixed words after it; the earlier turns do not, though a follow-up's rewritten question can hold a subject
named in an earlier turn. The question, the pages the search returned and, for a part answer, the answer already
given go to Anthropic for one more model call, which counts toward the day's 200; a web request also counts as
one of the visitor's questions. Settings: `ASK_WEB` and `TAVILY_API_KEY` on the backend, `NEXT_PUBLIC_WEB` in
the page's build, `WEB_QUERY_SUFFIX` for the fixed words. Pages of video and social sites, of marketplaces and
their price guides, and of the search service itself are never used.

## How many searches

The search plan is a free one of 1,000 credits a month with no card, so a month that uses them up shows no web
part and costs nothing. Before that, a search is allowed while the credits used this month are under
`30 + 920 x the share of the month gone by`: a quiet day leaves its share for a busier one. The count comes from
the search service's usage route, read at most once in five minutes. **That route runs behind** (measured: 26
searches were not in it eleven minutes after the first, and were fifty minutes after the last), so the backend
adds the searches it made itself in the last two hours. After a restart it knows only what the route says, and
can allow a few more than the rule until the route catches up. If the route cannot be read: 30 searches a day,
counted in memory.

## What is in place for running it as a service

- The explorer's query path calls no language model. The written answer of the question page does: one call to
  write it, measured at 0.0007 USD a question on average and 0.0014 USD at most, and for every question after a
  conversation's first one small call before the search, about 0.0001 USD, which says whether the question
  needs the earlier turns and rewrites it only then
  ([EVALUATION.md](../EVALUATION.md#written-answers)). Without a key the page works and shows the evidence only.
- Both stores are used read-only.
- One Neo4j connection pool is shared by all requests. Against a hosted Neo4j this took the demo questions from
  5 to 66 seconds (with failed requests) to a median of 2.9 seconds, same passages.
- Responses are bounded: at most 40 graph passages per question, long passages clipped for display, the full text
  available as a separate export.
- Only the frontend port needs to be reachable; it proxies `/api` to the backend. Everything binds to `127.0.0.1`
  by default. Embedding vectors are stripped from every response.
- Dependencies are pinned.
- A workflow runs what needs no database on every pull request: the Python tests, the frontend's build and the
  build of the hosted site, the browser tests, and the backend's image built and started with no settings.

The hosted demo serves the question path only: a human check before the first question, limits per visitor and
for the whole service, and a subset of the index that fits a free hosting tier, chosen and measured in
[EVALUATION.md](../EVALUATION.md). Not done yet: caching.
