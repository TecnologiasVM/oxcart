# Evaluation

What was measured in November 2026, on which questions, and how far the numbers can be trusted. Most of this file
is about retrieval: does the right passage, or the right catalogue issue, come back. The last measured part,
[Written answers](#written-answers), is about the short answer the question page writes from that evidence.

The earlier audit of the First Issue evidence graph (coverage and precision of the rule-based linker) is a
separate document: [pipeline/first_issue_graph/EVALUATION.md](pipeline/first_issue_graph/EVALUATION.md).

## Read this first

- **The gold for the literature questions was judged by a model. No person has checked the grades.** The judge
  was `gpt-6.1-sol` at high reasoning effort, run through the Codex CLI. A second model, `gpt-6-astra`, read a
  blind sample of 45 pages: same grade on 39 of 45, same "answers the question or not" on 41 of 45. Both readers
  are OpenAI models given one rubric, so this shows the grading is stable. It does not show the grading is right.
- **The literature questions were drafted with an AI assistant**, from the catalogue's issue titles and general
  knowledge of the field, before any search was run for them. No philatelist has edited them.
- **Every literature result has two denominators.** A draft question entered the set only when the pooled search
  results already held a page that answers it, so the 8 drafts left out are the ones retrieval may have failed on.
  Each result is given over the 41 questions in the set and over all 49 drafts with those 8 counted as misses.
  The true figure lies between the two.
- The sets are small. One question is 2 to 7 points, depending on the table.

## Result

"Answered" means: a page that answers the question is among the first five passages returned.

Literature questions, on the hosted collection (41,126 passages on a Weaviate Cloud free cluster):

| | Answered, of the 41 in the set | Answered, of all 49 drafts |
|---|---|---|
| The app as it was (its own retrieval path over the full 192,680-passage collection) | 12 (29%) | 12 (24%) |
| Vector search | 36 (88%; 95% interval 78 to 98) | 36 (73%) |
| Keyword search, the fallback when no embedding is available | 34 (83%) | 34 (69%) |

Catalogue questions (which issue is the question about), held-out half, 32 questions:

| | Right issue first | Right issue in the first three |
|---|---|---|
| The app as it was | 4 of 31 scored | |
| Catalogue lookup with the issue vector index | 30 of 32 | 32 of 32 |
| Catalogue lookup with the full-text index only (no embedding) | 26 of 32 | 29 of 32 |

The app as it was answers every question from one issue, the 1863 First Issue; that is why it finds the issue
only for the First Issue's questions.

## The test set

151 questions in three parts, in `eval/data/`. Spanish and English.

| Part | Questions | Where the gold comes from |
|---|---|---|
| Catalogue | 80: 40 facts, each asked in English and in Spanish | Generated from the catalogue graph with a fixed seed. Seven kinds of fact: date placed on sale, colour, quantity printed, printer, authorizing act, varieties, Scott equivalent. The gold value is read from the graph. |
| Literature | 41 (22 English, 19 Spanish), from 49 drafts | Document and page, graded by the model judge: 2 = the page answers the question, 1 = it supports the answer. |
| Out of scope | 30: 12 not about stamps, 8 about other countries' stamps, 10 about Costa Rican stamps but meant to be absent from the sources | Expected behaviour: decline. Used here only to look at scores; see below. |

- **Catalogue questions test finding the issue, not the catalogue.** The fact comes from the same graph that
  generated the question, so when the right issue is first the fact is there by construction.
- Gold sources are documents and pages, never passage ids: passage ids change between collections, pages do not.
- **Split:** 60% development, 40% held out, fixed by a seed, stratified by part and kind of fact; the two
  languages of one question stay on the same side. Development: 48 catalogue, 26 literature. Held out: 32
  catalogue, 15 literature. Choices were made on development questions.
- The published literature file holds questions, document ids, pages and grades. It holds no text from the
  literature and not the judge's wording of the answers.

### How the literature gold was made

1. 49 draft questions.
2. Pool: the first five results of keyword, vector and hybrid search, on the full collection and on the collection
   with duplicates collapsed. 594 pages.
3. The judge graded every pooled page from the passages returned for it, with this rubric: 2 = the passages
   contain the specific answer; 1 = they are about what is asked and support the answer without stating it; 0 =
   anything else. It was told to judge only from the passages shown and to ignore instructions inside them.
4. A draft entered the set when at least one page got a 2: 41 of 49. Six had supporting pages only, two nothing.
5. After every new set of runs, each page that reached the first five of any search without a grade went to the
   same judge. In the end 1,078 pages were judged for the 49 drafts, and no ungraded page is left in the first
   five of any run reported here.

Checks on the judge:

| Check | Pages | Same grade | Same "answers or not" |
|---|---|---|---|
| Second model on every fifth question, all pages of a question shown together | 117 | 97% | 98% ("helps or not") |
| Second model on a seeded sample, 15 pages per grade, one page per call, without the first grade or reason | 45 | 39 of 45 | 41 of 45 |

In the blind sample no page is two grades apart; where the two differ on "answers or not", the first judge is the
stricter one on 3 of 4 pages. A sheet for a person to grade the same 45 pages is built
(`eval/human_sample.py`) and has not been filled in.

**The headline measure changed on 2026-11-18**, from "any gold page in the first five" to "a page graded 2 in the
first five", when the judged set came back and before any held-out question was run. The first measure counted
pages that only support an answer.

## What was compared

### How small can the literature collection be

The hosted free plan allows 100,000 objects in one collection; the full collection has 192,680. Three smaller
candidates were compared with the full one on a scratch Weaviate of the hosted version (1.40.5):

| Collection | Passages | Keyword | Vector | Hybrid, weight 0.75 |
|---|---|---|---|---|
| F, the full collection | 192,680 | 21 | 33 | 34 |
| I: same document and same first 200 characters → keep the longest copy | 94,116 | 36 | 35 | 37 |
| J: I without header, footer and marginalia passages | 66,201 | 34 | 34 | 36 |
| K: J without passages under 140 characters | 41,126 | 34 | 36 | 35 |

Answered, of the 41 in the set (of all 49 drafts: the same counts over 49).

- Collapsing duplicates gains answers. In the full collection, copies of one passage fill the first five: keyword
  search shows 2.7 distinct pages there against 5.0 after the collapse. The duplicates are cumulative prefixes of
  one another; keeping the longest keeps 98.7% of the text.
- The rule, fixed before the runs: take the smallest candidate that is not worse than the full collection (at
  most one question lost net, and the interval of the difference not wholly below zero) and that loads and
  answers on the free cluster. I, J and K pass; K is the smallest.
- The full collection turned out to be a low bar. Against I, K loses 2 questions on keyword search and gains 1 on
  vector search, which is inside the noise of 41 questions. The export keeps I with a mark for J and K, so the
  choice can be reversed without re-embedding.

### Vector size

The stored vectors are `text-embedding-3-large` at 3,072 numbers. Shorter vectors were made by keeping the first
N numbers and normalizing again (checked against the API's own shortened vectors on 20 passages: cosine 0.9999).
On K, vector search, answered of 41: 3,072 → 36; 1,536 → 35; 1,024 → 33; 512 → 32; 256 → 34. Kept: 3,072. It fits
on the free cluster and no gain was measured from shortening.

### Search arm

On the development questions, on the hosted collection, keyword, vector and hybrid (0.75) search each answered 21
of 26. Vector search was chosen because it repeats: two identical runs returned the same first five passages for
every question, while hybrid runs did not (the same first passage in 79% to 97% of questions, depending on the
weight). Keyword search is the fallback.

### Stopwords

One comparison on development questions: the English stopword preset against English plus 135 Spanish words.
The Spanish list never helped and cost keyword search three questions (23 of 26 to 20 of 26, with the gold as it
stands now; 22 to 20 when the choice was made, before later pages were judged). The preset stays.

### Catalogue lookup

`oxcart/catalogue_lookup.py` finds the issue a question is about from catalogue numbers, the year,
and either the graph's full-text index or its vector index over issues. No language model.

| | Development (48) | Held out (32) |
|---|---|---|
| With the vector index | 48 of 48 | 30 of 32 |
| Full-text index only | 41 of 48 (English 24 of 24, Spanish 17 of 24) | 26 of 32 (English 15 of 16, Spanish 11 of 16) |
| The app as it was | 2 of 48 | 4 of 31 |

The catalogue's titles are in English, so Spanish questions miss on the full-text index; the vector index closes
that gap. The lookup does not make the embedding itself: the caller passes it, and with none the lookup uses the
full-text index. The two held-out misses are one question in both languages: an issue of the same president two
years earlier ranks first and the right one third.

### Can a score cut-off tell out-of-scope questions apart

How often an in-scope question's best score beats an out-of-scope one's (0.5 = chance): for keyword search 0.91
(not about stamps), 0.83 (other countries), 0.74 (Costa Rican, not in the sources); for vector search 0.92, 0.64,
0.81. A cut-off alone is not enough to decline questions; that belongs to the answer step.

## What the held-out numbers are

| Literature, held out | Answered, of the 15 in the set | Answered, of all 18 drafts on that side |
|---|---|---|
| The app as it was | 6 | 6 (33%) |
| Vector search | 15 | 15 (83%) |
| Keyword search | 13 | 13 (72%) |

15 of 15 does not mean 100%: with 15 questions that result is compatible with a true rate near 80%. The whole-set
figure above is the better guide.

Two things to know about "held out":

- The literature held-out questions were scored on **three runs of one configuration** on the hosted collection:
  the first load, an identical repeat to see whether runs repeat, and a run after the collection was rebuilt from
  its export. No setting changed between them.
- The vector-size rule was applied on the held-out questions, as planned beforehand. Its outcome was the default
  (keep 3,072).

Catalogue held-out questions were run once per mode. The hosted graph instance refused new connections during the
runs; an unreachable graph is recorded as "not scored", never as a miss (`eval/graph_conn.py` logs every
attempt). The graph was then moved to a fresh instance with identical content, and the questions left unscored
(3 with the vector index, 7 with the full-text index) were run there once. Two of those three were misses.

## Written answers

The question page writes a short answer from the evidence it shows (`POST /api/chat`: Claude Haiku 5.5, the
catalogue cards and passages given as documents with citations on; `backend/README.md` has the steps). This part
measures those answers on the same 151 questions, asked once each through a backend in hosted mode on the
development machine, against the hosted stores.

### Read this first

- **The grades are a model's. No person has checked them.** The judge was `gpt-6.1-sol` at high reasoning effort,
  run through the Codex CLI: another vendor's model than the one that writes the answers. One judge, one pass.
- **One run per setting.** The model's answers change from run to run, and nothing here measures by how much. A
  difference of a few questions between two columns is not a finding.
- **The last column is not a held-out result.** After the first two runs the model's instructions were revised
  once (a rule on scope, and one on writing in the question's language), having read answers to these same
  questions. The third run is the setting that is served.
- **"Correct" for a literature question means agreeing with a reference answer** that the retrieval judge wrote
  from the pages it graded for that question in its first pass (12 pages a question on average, each with up to
  two full passages). The answer is written from
  five passages of at most 700 characters. "In part" is the usual grade: the answer gives a true part of the
  reference and leaves out the rest. That measures the evidence the model is given as much as the model.
- **"Correct" for a catalogue question** means stating the value the graph holds for the fact asked; the judge
  reads the answer against that value.
- The literature gold behind those references is itself model-judged (see the top of this file).
- Grades are counted over **all** questions of a part: a question with no written answer is neither supported
  nor correct. Literature results are also given over all 49 drafts, the 8 left out counted as misses.

### What is graded

- **How a question ended:** an answer was written; the model said the evidence does not cover the question
  (`not covered`); or nothing was shown, and why (cut at the output limit, no sentence with a citation that
  holds, a failed call).
- **Sentences with no citation.** The page shows a sentence only if a citation that holds is attached to it: it
  names a shown card or passage, and the cited text is in it. A sentence the model wrote with no citation is
  removed before the page shows the answer. The table gives the share of written sentences that were removed.
  The part of a kept sentence that lies outside its cited text is not removed; "supported" is what measures it.
- **Supported:** every shown sentence of the answer is stated by the sources it cites (the judge marks each
  sentence yes, partly or no; an answer is supported when all are yes).
- **Correct:** as above.
- **Out of scope:** 30 questions that are not about Costa Rican stamps, or whose answer is not in the sources. The
  wanted outcome is no written answer.
- **Follow-ups:** 10 conversations of two turns, written for this test (`eval/data/threads.jsonl`): a catalogue
  question, then a follow-up that names nothing ("And who printed it?"). No judge: is the first question's issue
  among the issues returned for the follow-up, with the conversation and with the follow-up asked alone.

### Result

Four runs. **Thinking off** and **thinking on, first instructions** differ only in the model's thinking setting
(both at effort `low`). **Thinking on, as served** has the revised instructions. **As served, through the public
host** is the same code and settings asked once more on 2026-11-21 through the public service itself (the hosted
backend and the hosted stores), from another machine: a second run of the served setting, not a new setting.

| | Thinking off | Thinking on, first instructions | Thinking on, as served | As served, through the public host |
|---|---|---|---|---|
| **Catalogue, 80 questions** | | | | |
| A written answer | 65 | 75 | 73 | 75 |
| Not covered | 3 | 5 | 6 | 4 |
| Cut at the output limit | 12 | 0 | 0 | 0 |
| No sentence with a citation that holds | 0 | 0 | 1 | 1 |
| Supported | 56 | 65 | 62 | 59 |
| Correct | 64 | 74 | 69 | 74 |
| Correct in part / not correct | 1 / 0 | 1 / 0 | 3 / 1 | 1 / 0 |
| Supported and correct | 56 | 64 | 58 | 58 |
| **Literature, 41 questions** | | | | |
| A written answer | 19 | 41 | 41 | 41 |
| Not covered | 1 | 0 | 0 | 0 |
| Cut at the output limit | 21 | 0 | 0 | 0 |
| Supported | 14 | 28 | 27 | 24 |
| Correct (agrees with the reference in full) | 5 | 8 | 10 | 9 |
| Correct in part / not correct | 13 / 1 | 32 / 1 | 29 / 2 | 32 / 0 |
| Supported and correct | 4 | 7 | 9 | 5 |
| Correct, of all 49 drafts | 5 | 8 | 10 | 9 |
| Supported and correct, of all 49 drafts | 4 | 7 | 9 | 5 |
| **Out of scope, 30 questions** | | | | |
| No written answer (the wanted outcome) | 27 | 21 | 29 | 28 |
| **Sentences** | | | | |
| Written with no citation, and removed | 79 of 266 (30%) | 113 of 439 (26%) | 100 of 419 (24%) | 98 of 433 (23%) |
| Citations that did not hold | 0 of 197 | 0 of 355 | 0 of 357 | 0 of 373 |
| Shown sentences the judge marked supported / partly / not | 179 / 15 / 0 | 314 / 28 / 2 | 292 / 28 / 1 | 281 / 35 / 0 |
| **Follow-ups, 10 conversations** | | | | |
| With the conversation: the issue first / in the first three | 8 / 10 | 9 / 10 | 9 / 10 | 8 / 10 |
| The follow-up asked alone: first / in the first three | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |

By language, as served:

| | English | Spanish |
|---|---|---|
| Catalogue: written / supported / correct | 34 / 29 / 33 of 40 | 39 / 33 / 36 of 40 |
| Literature: written / supported / correct (in part) | 22 / 15 / 3 (18) of 22 | 19 / 12 / 7 (11) of 19 |
| Answers in another language than the question | 0 | 2 (both catalogue) |

- **Thinking off is not served.** With it the model wrote a fact without a citation and then copied the cited
  text as a piece of its own; the copied text is output, so half of the literature answers and 12 catalogue
  answers hit the output limit and nothing was shown for them.
- **The scope rule did what it was written for** (out-of-scope questions with a written answer: 9, then 1), and
  the catalogue column moved by a few questions with it. With one run per setting those few cannot be told from
  run-to-run change.
- **About a quarter of what the model writes carries no citation** and is removed; most answers lose at least one
  sentence. What is shown is mostly supported by its sources (292 of 321 sentences in full), and one sentence in
  eleven says more than its sources do.
- **Literature answers are rarely complete.** 10 of 41 agree with the reference in full and 29 in part; 2 do not.
- **Retrieval did not move.** Through this route the counts are the question path's: a page that answers in the
  first five for 36 of 41 literature questions (36 of 49 drafts); the issue first with the fact in its card for 78
  of 80 catalogue questions, in the first three for 80 of 80. A first question is searched as it is typed; only a
  follow-up is rewritten.

### Cost and waits

Measured from the token counts the API returned for every call, at the list price of the day (0.10 USD per
million input tokens, 0.50 per million output tokens; thinking is billed as output).

| | Thinking off | Thinking on, first instructions | Thinking on, as served | As served, through the public host |
|---|---|---|---|---|
| Cost of a question, USD: mean / maximum | 0.00055 / 0.00089 | 0.00069 / 0.00128 | 0.00068 / 0.00129 | 0.00068 / 0.00122 |
| Cost of a follow-up (rewrite and answer), USD: mean / maximum | 0.00063 / 0.00083 | 0.00070 / 0.00093 | 0.00070 / 0.00094 | 0.00070 / 0.00097 |
| Input tokens of a question: mean / maximum | 4,304 / 7,254 | 4,305 / 7,255 | 4,442 / 7,392 | 4,442 / 7,392 |
| Output tokens of a question: mean / maximum | 249 / 500 | 520 / 1,562 | 478 / 1,478 | 476 / 1,417 |
| Wait for the evidence, s: median / 95th percentile | 1.26 / 1.58 | 1.27 / 1.51 | 1.28 / 1.53 | 0.89 / 1.15 |
| Wait for the answer, s: median / 95th percentile | 2.57 / 4.15 | 3.49 / 6.64 | 3.46 / 6.48 | 3.25 / 6.11 |
| The whole run, 151 questions and 10 conversations, USD | about 0.10 | about 0.12 | about 0.12 | about 0.11 |

The waits of the first three columns are from the development machine, with the backend on it. The last column's
are measured from a laptop through the public service, with the service awake; the hosted backend is on a smaller
machine.
At the served mean, 200 model calls a day are about 4 USD a month. That count lives in the server's memory and
starts again when the service restarts, so the limit that holds is the spend limit of the key's workspace.

Per-question outcomes of the four runs: `eval/outcomes/answers_thinking-off.json`,
`answers_thinking-on-first.json`, `answers_thinking-on.json`, `answers_hosted.json` (ids, how each ended, sentence and citation counts,
token counts, the judge's marks; no answer and no passage).

## Other limits

- The pool that produced the gold was built from keyword, vector and hybrid search, so those arms are favoured
  over any method not in the pool. The top-ups in step 5 remove the bias between the runs reported here, not
  towards a future method.
- Hybrid search on the hosted collection does not repeat from run to run.
- Latency from a home connection to the hosted cluster, warm, per search, without the embedding call: keyword
  77–80 ms median, vector 86–87 ms, hybrid 120–123 ms. The hosted backend's latency has not been measured.
- The Spanish names of issues used in the catalogue questions were written for this test set and have not been
  reviewed by a philatelist.

## Data notes

- Every stored vector is the embedding of the word `Oxcart`, a space, and the passage text (the collection name
  was prepended when the collection was first vectorized). Questions are embedded as they are, without that
  prefix. All numbers here were measured that way.
- The eval makes the question's embedding itself and sends the vector to Weaviate; the embedding key is never
  passed to the vector store. All question embeddings for this evaluation cost under 0.01 USD.
- The literature, its extracted text, the export of the collection and the scripts that build the candidate
  collections are not in this repository.

## Run it

The eval reads its stores from the app's settings and the environment (`eval/stores.py`). Keys come from the
machine's secret store through `scripts/with-key.sh`, for the one command only; nothing is written to a file.
The questions are read from `eval/data/`.

```bash
# unit tests (no store needed)
python -m pytest eval/tests oxcart/tests/test_catalogue_lookup.py

# literature questions against a collection: writes local-data/eval/results/run_<label>_<split>.json
scripts/with-key.sh OPENAI_API_KEY=<entry> WEAVIATE_URL=<entry> WEAVIATE_API_KEY=<entry> -- \
    python -m eval.run --label cloud-K --split dev

# score stored runs with the current gold, both denominators
python -m eval.table local-data/eval/results/run_cloud-K_dev.json --split dev

# catalogue questions against the graph
scripts/with-key.sh OPENAI_API_KEY=<entry> -- python -m eval.catalogue_arm --split dev --mode vector

# written answers: ask every question through a running backend, then grade and print the tables
OXCART_API=http://127.0.0.1:8090 OXCART_EVAL_KEY=<the backend's EVAL_ACCESS_KEY> python -m eval.chat_arm run --label <name>
python -m eval.answer_judge prepare --label <name> --dir local-data/eval/judge/answers-<name> --references <judgment files>
#   ... run a judge model once per file of that folder's inputs/, writing outputs/<id>.json (see eval/answer_judge.py) ...
python -m eval.answer_judge collect --dir local-data/eval/judge/answers-<name>
python -m eval.chat_arm table --label <name> --grades local-data/eval/judge/answers-<name>/grades.json
```

Per-question outcomes behind every table: `eval/outcomes/stage2.json` (ids and ranks only).
