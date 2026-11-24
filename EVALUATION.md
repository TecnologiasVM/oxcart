# Evaluation

What was measured in November 2026, on which questions, and how far the numbers can be trusted. The first parts,
from [Result](#result) to [What the held-out numbers are](#what-the-held-out-numbers-are), are about retrieval:
does the right passage, or the right catalogue issue, come back. [Written answers](#written-answers) and
[What was tried to raise the literature answers](#what-was-tried-to-raise-the-literature-answers) (with the
sealed set's two runs at its end) are about the short answer the question page writes from that evidence.
[A web part](#a-web-part-three-markers-and-a-trial-with-real-searches) is about the part written from a web
search, and holds the two runs of the whole set with the web setting on.
[The literature in both languages](#the-literature-in-both-languages) is about version 1.1: the question
searched in Spanish and in English, with the same questions asked before and after; "How it works" reads its
figures from the first run after. The file
ends with other limits, the numbers that have no published record, notes on the data, and the commands that run
it.

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
  These are two ways of counting, not bounds on a true figure: how a method would do on the 8 is not known.
- The sets are small. One question is 1.25 points of the 80 catalogue questions, about 2.0 of the 49 drafts,
  about 2.4 of the 41 literature questions, about 3.1 of the 32 held-out catalogue questions, about 3.3 of the 30
  out of scope, about 3.8 of the 26 development literature questions, 5 of a sealed part's 20, about 6.7 of the
  15 held-out literature questions, and 10 of the 10 follow-ups.

## Result

"Answered" (hit@5) means: a page graded 2 ([below](#how-the-literature-gold-was-made)) is among the first five
passages returned. A question counts once, however many of its gold pages are found; this is not recall, the
share of a question's gold pages that are found.

Literature questions, on the hosted collection (41,126 passages on a Weaviate Cloud free cluster):

| | Answered, of the 41 in the set | Answered, of all 49 drafts |
|---|---|---|
| The app as it was (its own retrieval path over the full 192,680-passage collection) | 12 (29%) | 12 (24%) |
| Vector search | 36 (88%; 95% interval 78 to 98) | 36 (73%) |
| Vector search with the question and with its translation, the two lists joined by reciprocal rank fusion (served since version 1.1; [below](#the-literature-in-both-languages)) | 38 (93%) | 38 (78%) |
| Keyword search, the fallback when no embedding is available | 34 (83%) | 34 (69%) |

Catalogue questions (which issue is the question about), held-out half, 32 questions. They were kept aside while
the lookup was built, then reused, with the other 48, when the short vector of the served lookup was chosen
([below](#the-catalogue-lookup-a-second-short-vector-for-each-issue)):

| | Right issue first | Right issue in the first three |
|---|---|---|
| The app as it was | 4 of 31 scored | |
| Catalogue lookup with the issue vector index | 30 of 32 | 32 of 32 |
| Catalogue lookup as served: the issue vector index and the short vector index | 29 of 32 | 32 of 32 |
| Catalogue lookup with the full-text index only (no embedding) | 26 of 32 | 29 of 32 |

The app as it was answers every question from one issue, the 1863 First Issue; that is why it finds the issue
only for the First Issue's questions.

## The test set

151 questions in three parts, in `eval/data/`. Spanish and English.

| Part | Questions | Where the gold comes from |
|---|---|---|
| Catalogue | 80: 40 facts, each asked in English and in Spanish | Generated from the catalogue graph with a fixed seed. Seven kinds of fact: date placed on sale, colour, quantity printed, printer, authorizing act, varieties, Scott equivalent. The gold value is read from the graph. |
| Literature | 41 (22 English, 19 Spanish), from 49 drafts | Document and page, graded by the model judge: 2 = the page answers the question, or a clear, direct part of it; 1 = it supports the answer. |
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
3. The judge graded every pooled page from the passages returned for it, with this rubric
   (`eval/model_judge.py`): 2 = the passages contain the specific answer to the question (or a clear, direct
   part of it); 1 = they are about what the question asks and support or narrow the answer, but do not state
   it; 0 = anything else, a different subject or the question's words without help to answer it (an index line,
   a list of titles, a price list, a header). It was told to be strict with 2 (a passage about the same issue or
   stamp that does not answer this question is a 1 at most), to judge only from the passages shown, and to
   ignore instructions inside them. A grade 2 can therefore rest on part of an answer.
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

The right issue first:

| | Development (48) | Held out (32) |
|---|---|---|
| With the vector index | 48 of 48 | 30 of 32 |
| As served: the vector index and the short vector index | | 29 of 32 (English 15 of 16, Spanish 14 of 16) |
| Full-text index only | 41 of 48 (English 24 of 24, Spanish 17 of 24) | 26 of 32 (English 15 of 16, Spanish 11 of 16) |
| The app as it was | 2 of 48 | 4 of 31 |

The catalogue's titles are in English, so Spanish questions miss on the full-text index; the vector index closes
that gap. The lookup does not make the embedding itself: the caller passes it, and with none the lookup uses the
full-text index.

**As served, the held-out questions measured again.** The served setting is the vector index with the short
vector index ([below](#the-catalogue-lookup-a-second-short-vector-for-each-issue); `ASK_SHORT_VECTOR` on). The
row above was measured on 2026-11-23, on code `33df63b`: the question's vector on both indexes, no full-text
index, the first three issues; the lookup only, no language model. The right issue is first for 29 of 32 and in
the first three for 32 of 32, against 30 of 32 and 32 of 32 with the vector index alone. The lookup took 0.99 s
at the median and 1.56 s at the 95th percentile. Outcome: `eval/outcomes/catalogue_heldout_served.json`. These 32
are not untouched: they are among the 80 catalogue questions measured when the short vector was chosen.

With the vector index alone, the two held-out misses are one question in both languages (`cat-001-en`,
`cat-001-es`): an issue of the same president two years earlier ranks first and the right one third. As served,
three miss the first place: that question in both languages (the same earlier issue first, the right one
second) and `cat-014-es` (another 1960 issue first, the right one second).

### Can a score cut-off tell out-of-scope questions apart

How often an in-scope question's best score beats an out-of-scope one's (0.5 = chance): for keyword search 0.91
(not about stamps), 0.83 (other countries), 0.74 (Costa Rican, not in the sources); for vector search 0.92, 0.64,
0.81. A cut-off alone is not enough to decline questions; that belongs to the answer step.

## What the held-out numbers are

| Literature, held out | Answered, of the 15 in the set | Answered, of all 18 drafts on that side |
|---|---|---|
| The app as it was | 6 | 6 (33%) |
| Vector search | 15 | 15 (83%) |
| Vector search in both languages, joined (version 1.1; scored once, after its settings were chosen) | 14 | 14 (78%) |
| Keyword search | 13 | 13 (72%) |

15 of 15 does not mean 100%: with 15 questions that result is compatible with a true rate near 80%. The whole-set
figure above is the better guide.

Three things to know about "held out":

- The literature held-out questions were scored on **three runs of one configuration** on the hosted collection:
  the first load, an identical repeat to see whether runs repeat, and a run after the collection was rebuilt from
  its export. No setting changed between them.
- The vector-size rule was applied on the held-out questions, as planned beforehand. Its outcome was the default
  (keep 3,072).
- The catalogue held-out half was reused later: the short vector the served lookup has was chosen on all 80
  catalogue questions, that half included
  ([below](#the-catalogue-lookup-a-second-short-vector-for-each-issue)).

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
  run through the Codex CLI: another vendor's model than the one that writes the answers. One judge, one pass, for the grades of this part;
  one mark was later given again by a second judge ([below](#a-stronger-writer-and-a-second-judge)).
- **One run per setting, three of the served one.** The model's answers change from run to run. The last three
  columns are the served setting asked three times, and show by how much: a difference of a few questions
  between two columns is not a finding.
- **The served setting's columns are not a held-out result.** After the first two runs the model's instructions
  were revised once (a rule on scope, and one on writing in the question's language), having read answers to
  these same questions. The third run is the setting that is served; the fourth and fifth repeat it.
- **"Correct" for a literature question is the judge's mark against a reference answer** that the retrieval
  judge wrote from the pages it graded for that question in its first pass (12 pages a question on average, each
  with up to two full passages). The rubric (`eval/answer_judge.py`, `PROMPT`): "yes" when the answer agrees
  with the reference on what the question asks; "partly" when it gives part of it, or only related facts; "no"
  when it contradicts the reference or does not answer the question. The tables call "yes" "correct" or "in
  full", and "partly" "in part". The answer is written from five passages of at most 700 characters. "In part"
  is the usual grade. That measures the evidence the model is given as much as the model.
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

Five runs. **Thinking off** and **thinking on, first instructions** differ only in the model's thinking setting
(both at effort `low`). **Thinking on, as served** has the revised instructions. **As served, through the public
host** is the same code and settings asked once more on 2026-11-21 through the public service itself (the hosted
backend and the hosted stores), from another machine: a second run of the served setting, not a new setting.
**The public host again, a day later** is that run repeated on 2026-11-22, one day after it, with nothing changed
in between: a third run of the served setting. The last three columns differ by a few answers in most rows and
by seven in one (catalogue supported: 62, 59, 66); that is what one run of this setting is worth.

| | Thinking off | Thinking on, first instructions | Thinking on, as served | As served, through the public host | The public host again, a day later |
|---|---|---|---|---|---|
| **Catalogue, 80 questions** | | | | | |
| A written answer | 65 | 75 | 73 | 75 | 75 |
| Not covered | 3 | 5 | 6 | 4 | 5 |
| Cut at the output limit | 12 | 0 | 0 | 0 | 0 |
| No sentence with a citation that holds | 0 | 0 | 1 | 1 | 0 |
| Supported | 56 | 65 | 62 | 59 | 66 |
| Correct | 64 | 74 | 69 | 74 | 74 |
| Correct in part / not correct | 1 / 0 | 1 / 0 | 3 / 1 | 1 / 0 | 1 / 0 |
| Supported and correct | 56 | 64 | 58 | 58 | 65 |
| **Literature, 41 questions** | | | | | |
| A written answer | 19 | 41 | 41 | 41 | 41 |
| Not covered | 1 | 0 | 0 | 0 | 0 |
| Cut at the output limit | 21 | 0 | 0 | 0 | 0 |
| Supported | 14 | 28 | 27 | 24 | 29 |
| Correct ("yes": agrees with the reference on what the question asks) | 5 | 8 | 10 | 9 | 10 |
| Correct in part / not correct | 13 / 1 | 32 / 1 | 29 / 2 | 32 / 0 | 30 / 1 |
| Supported and correct | 4 | 7 | 9 | 5 | 9 |
| Correct, of all 49 drafts | 5 | 8 | 10 | 9 | 10 |
| Supported and correct, of all 49 drafts | 4 | 7 | 9 | 5 | 9 |
| **Out of scope, 30 questions** | | | | | |
| No written answer (the wanted outcome) | 27 | 21 | 29 | 28 | 28 |
| **Sentences, the 121 catalogue and literature questions** | | | | | |
| Written with no citation, and removed | 79 of 266 (30%) | 113 of 439 (26%) | 100 of 419 (24%) | 88 of 401 (22%) | 108 of 418 (26%) |
| Citations that did not hold | 0 of 197 | 0 of 355 | 0 of 357 | 0 of 348 | 0 of 350 |
| Shown sentences the judge marked supported / partly / not | 172 / 15 / 0 | 299 / 25 / 2 | 291 / 27 / 1 | 279 / 34 / 0 | 286 / 23 / 1 |
| **Sentences, every question: out of scope and follow-ups too** | | | | | |
| Written with no citation, and removed | 86 of 297 (29%) | 137 of 501 (27%) | 113 of 451 (25%) | 98 of 433 (23%) | 118 of 452 (26%) |
| Citations that did not hold | 0 of 225 | 0 of 398 | 0 of 377 | 0 of 373 | 0 of 376 |
| Shown sentences the judge marked supported / partly / not (follow-ups are not graded) | 179 / 15 / 0 | 314 / 28 / 2 | 292 / 28 / 1 | 281 / 35 / 0 | 290 / 24 / 1 |
| **Follow-ups, 10 conversations** | | | | | |
| With the conversation: the issue first / in the first three | 8 / 10 | 9 / 10 | 9 / 10 | 8 / 10 | 8 / 10 |
| The follow-up asked alone: first / in the first three | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |

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
  sentence. What is shown is mostly supported by its sources (as served, 292 of the 321 shown sentences of every
  graded answer), and one sentence in eleven says more than its sources do.
- **Literature answers rarely get a "yes".** As served, 10 of 41 agree with the reference on what the question
  asks, 29 in part; 2 do not.
- **Retrieval did not move.** Through this route the counts are the question path's: a page that answers in the
  first five for 36 of 41 literature questions (36 of 49 drafts); the issue first with the fact in its card for 78
  of 80 catalogue questions, in the first three for 80 of 80. A first question is searched as it is typed; only a
  follow-up is rewritten (in these runs a question was sent with earlier turns only when it was a follow-up; see
  the note on the one question box under "Cost and waits").

### Cost and waits

Measured from the token counts the API returned for every call, at the list price of the day (0.10 USD per
million input tokens, 0.50 per million output tokens; thinking is billed as output).

| | Thinking off | Thinking on, first instructions | Thinking on, as served | As served, through the public host | The public host again, a day later |
|---|---|---|---|---|---|
| Cost of a question, USD: mean / maximum | 0.00055 / 0.00089 | 0.00069 / 0.00128 | 0.00068 / 0.00129 | 0.00068 / 0.00122 | 0.00068 / 0.00130 |
| Cost of a follow-up (rewrite and answer), USD: mean / maximum | 0.00063 / 0.00083 | 0.00070 / 0.00093 | 0.00070 / 0.00094 | 0.00070 / 0.00097 | 0.00069 / 0.00090 |
| Input tokens of a question: mean / maximum | 4,304 / 7,254 | 4,305 / 7,255 | 4,442 / 7,392 | 4,442 / 7,392 | 4,442 / 7,392 |
| Output tokens of a question: mean / maximum | 249 / 500 | 520 / 1,562 | 478 / 1,478 | 476 / 1,417 | 466 / 1,625 |
| Wait for the evidence, s: median / 95th percentile | 1.26 / 1.58 | 1.27 / 1.51 | 1.28 / 1.53 | 0.89 / 1.15 | 0.87 / 1.05 |
| Wait for the answer, s: median / 95th percentile | 2.57 / 4.15 | 3.49 / 6.64 | 3.46 / 6.48 | 3.25 / 6.11 | 3.08 / 5.97 |
| The whole run, 151 questions and 10 conversations, USD | about 0.10 | about 0.12 | about 0.12 | about 0.11 | about 0.11 |

The waits of the first three columns are from the development machine, with the backend on it. Those of the last
two columns are measured from a laptop through the public service, with the service awake; the hosted backend is
on a smaller machine.
At the served mean, 200 model calls a day are about 4 USD a month. That count lives in the server's memory and
starts again when the service restarts, so the limit that holds is the spend limit of the key's workspace.

**Since the page has one question box** (not in the runs above), every question after a conversation's first is
sent with the earlier turns and takes two model calls: one that says whether it needs those turns, and rewrites
it only then, and one that writes. The first costs about 0.0001 USD (about 740 tokens in and 12 to 44 out) and
0.9 s on average before the search starts, measured on 85 questions on the development machine. So a written
answer takes one to three of the 200 calls a day (one more for a question after a conversation's first, one more
for a web part), a call can be spent with no answer shown (a timeout, a failed call), and a question after the
first costs about 0.0008 USD on average.
Asked to repeat a standalone question unchanged, the earlier instructions still added the country to 12 of 20
development questions and an earlier turn's subject to one; a page that answers was then among the five
passages for 6 of 10 literature questions against 8 when asked alone. With the reply held to a flag and a
question, and the instruction to add nothing the question does not point to: none of the 20 is rewritten, 8 of
10 either way, and the ten follow-ups keep their issue (first for 9, in the first three for 10; all ten
rewritten). One run of each; development questions.

Per-question outcomes of the five runs: `eval/outcomes/answers_thinking-off.json`,
`answers_thinking-on-first.json`, `answers_thinking-on.json`, `answers_hosted.json`, `answers_hosted-2.json` (ids, how each ended, sentence and citation counts,
token counts, the judge's marks; no answer and no passage).

## What was tried to raise the literature answers

After the answers above were served, the literature part was the weak one: about 10 of 41 answers get the
judge's "yes" against the reference. This part reports everything that was tried on it, with what did not help.

### Read this first

- **These are the development questions.** Answers to them were read while the instructions were revised, so
  nothing here is a held-out result. A sealed set of 50 questions was made before any change
  (`eval/data/sealed/`); its two runs are reported at the end of this part.
- **Marks are a model's** (`gpt-6.1-sol`, high effort). No person has checked them. A second model marked a part
  of them again; that is reported below.
- **Three runs a setting** unless a row says otherwise, because the writer's answers change from run to run. The
  first row shows by how much: five runs of one setting (a sixth run of it, the repeat through the public
  host on 2026-11-22, was not given the second mark and is not in the row). A difference inside that spread
  is not a finding.
- **Two marks of an answer, from two prompts** (`eval/answer_judge.py`). "In full" is the first pass's "yes",
  used above: the answer agrees with the reference on what the question asks ("partly": part of it, or only
  related facts). **"Gives what is asked"** is a separate pass with its own instructions (`ASKED_PROMPT`): "yes"
  when the answer states the thing the question asks for (the date, the name, the reason, the list it requests)
  and it agrees with the reference, where leaving out further detail the reference has and the question did not
  ask for does not lower the mark; "partly" when it gives some of several things asked, or the thing asked with
  one detail that disagrees; "no" otherwise. Both prompts speak of what the question asks; the second says
  outright that detail beyond it does not count, and it sees no source text. They are two judgments under two
  prompts, not a clean split between a complete answer and an answer to the question. The first pass was not
  changed; a test pins its instructions.
- **Rows marked "not a system"** give the writer passages from pages already known to answer the question. No
  search can know that. They measure what the writer does with the right evidence.
- Costs are from the token counts the API returned, at the list prices of the day, for a literature question.

### One writer, different evidence and settings

The writer is Claude Haiku 5.5 at effort `low`, as served, in every row but one. Counts of 41 questions.

| Setting | Supported | In full | Gives what is asked | USD a question |
|---|---|---|---|---|
| As served: five passages, the first 700 characters of each (five runs) | 27, 24, 27, 31, 24 | 10, 9, 8, 9, 12 | 17, 19, 14, 16, 16 | 0.00089 |
| The 700 characters of a passage nearest the question | 25, 29, 30 | 10, 12, 10 | 18, 21, 20 | 0.00087 |
| Eight passages | 26, 28, 27 | 10, 9, 10 | 19, 18, 18 | 0.00100 |
| Nearest excerpt and eight passages | 26, 27, 27 | 12, 10, 13 | 21, 19, 19 | 0.00101 |
| A step that grades 15 passages, keeps up to 8, and may search once more | 27, 26, 30 | 12, 12, 14 | 21, 18, 21 | 0.00144 |
| That step with the nearest excerpt | 20, 24, 27 | 14, 15, 12 | 21, 23, 19 | 0.00143 |
| A rebuilt collection, five passages | 25, 32, 30 | 10, 9, 9 | 14, 14, 16 | 0.00090 |
| The rebuilt collection, ten passages | 29, 24, 24 | 12, 13, 12 | 18, 17, 18 | 0.00109 |
| Nearest excerpt; the writer reads up to 2,000 characters of a passage | 25, 23, 26 | 10, 9, 11 | 20, 19, 17 | 0.00100 |
| Nearest excerpt; the writer reads up to 4,000 characters | 26, 27, 21 | 12, 10, 14 | 19, 17, 20 | 0.00108 |
| Nearest excerpt; the writer at effort `high` | 21, 26, 31 | 10, 11, 10 | 20, 18, 20 | 0.00127 |
| Not a system: five passages of pages known to answer, 700 characters | 28, 30, 31 | 13, 14, 14 | 20, 19, 22 | 0.00091 |
| Not a system: the same passages, up to 4,000 characters | 30, 26, 30 | 17, 14, 13 | 27, 21, 25 | 0.00125 |

- **No reliable improvement was shown by a setting that could be served.** With three runs a setting, some
  counts stand outside the first row's spread (the grading step with the nearest excerpt: 12 to 15 in full and
  19 to 23 that give what is asked, against 8 to 12 and 14 to 19), and no test of a difference was made. The
  grading step comes nearest (about three more answers in full) for 60% more cost and a later first line on the
  page.
- **The search is not the limit by itself.** Five passages of pages known to answer, each cut to the 700
  characters nearest the question, against the second row (the found passages, cut the same way): about three
  more answers in full (13, 14, 14 against 10, 12, 10) and about as many that give what is asked (20, 19, 22
  against 18, 21, 20). Against the first row, as served, it is about four more of each (means of 9.6 in full
  and 16.4 that give what is asked).
- **More text is not the limit by itself.** Reading 2,000 or 4,000 characters of the passages the search finds
  changes nothing.
- **Both together move it:** the right passages and up to 4,000 characters of each give what is asked in 21 to
  27 of 41. A question has about two pages that answer it among the five passages the search shows.
- **The rebuilt collection** (the full text of each passage instead of its first 12,000 characters, repeated
  lines cut, pieces of about 1,000 characters, new vectors) ranks better: a page that answers is first for 63% of
  the questions against 51%. The written answers did not follow. It is not served.
- 13 of the 41 questions never get "gives what is asked" in 14 runs of the served writer on the found passages.
  With the known passages at 700 characters 12 of them still do not; at 4,000 characters, 9.

### A stronger writer, and a second judge

Same instructions, same effort (`low`), same evidence; only the model that writes changes. None of this is
served.

The two stronger writers were given more room than the served one: 4,000 tokens for thinking on top of the
answer's limit (as served: 500 tokens for the answer and 1,500 for thinking) and 60 seconds for a reply (12 as
served). No answer of theirs was cut by the limit.

| Writer and evidence | Runs | Written | Supported | In full | Gives what is asked | USD a question |
|---|---|---|---|---|---|---|
| Haiku 5.5, nearest excerpt | 3 | 41, 41, 41 | 25, 29, 30 | 10, 12, 10 | 18, 21, 20 | 0.00087 |
| Sonnet 5.5, nearest excerpt | 3 | 40, 40, 40 | 37, 34, 32 | 16, 16, 15 | 21, 21, 22 | 0.0130 |
| Opus 5.5, nearest excerpt | 2 | 38, 35 | 26, 28 | 10, 13 | 15, 17 | 0.0291 |
| Haiku 5.5, known passages at 4,000 characters (not a system) | 3 | 41, 41, 41 | 30, 26, 30 | 17, 14, 13 | 27, 21, 25 | 0.00125 |
| Sonnet 5.5, known passages at 4,000 characters (not a system) | 2 | 41, 41 | 35, 35 | 17, 19 | 25, 29 | 0.0200 |
| Opus 5.5, known passages at 4,000 characters (not a system) | 1 | 39 | 27 | 23 | 27 | 0.0426 |

- **The writer is not what holds back "gives what is asked".** On the same evidence Sonnet gives it for 21 or 22
  questions where Haiku gives it for 18 to 21; Opus for fewer, because for 3 and 6 questions every sentence it
  wrote lacked a citation and nothing was shown. On that evidence neither answers any of the 13 questions above.
- **Sonnet's answers are more often supported and more often complete** (about 16 in full against about 11), at
  15 times the cost of a question.
- With the known passages the three writers are close on "gives what is asked" (21 to 29); one run of Opus is
  the most complete (23 in full).

**A second judge.** Claude Opus 5.5 marked "gives what the question asks" again on the 205 literature answers of
the five runs of the first row, from the same instructions and the same inputs as the usual judge.

| Usual judge, by row; second judge, by column | yes | partly | no |
|---|---|---|---|
| yes | 73 | 9 | 0 |
| partly | 10 | 71 | 3 |
| no | 0 | 6 | 33 |

The two give the same mark for 177 of 205 answers (86%), and stand on the same side of yes against not-yes for
186 (91%). No answer is "yes" for one and "no" for the other. Totals: 82 and 83 "yes". Cohen's kappa, which
takes out the agreement two judges would reach by chance: 0.78 over the three marks, 0.81 on yes against
not-yes. Two models agreeing is not a person checking; it says the mark does not rest on one vendor's reading.

### What was kept

- **The nearest excerpt**, behind a setting (`ASK_EXCERPT=nearest`): it costs nothing and nothing falls. It is
  not a measured gain: no reliable improvement was shown.
- **A catalogue card's lines as phrases, in the language of the question, with dates in words.** The model sets
  a cited line into its own sentence, so answers held "placed on sale: 1999-11-05" and, in Spanish answers, the
  line in English. Three runs of all 151 questions with the change: catalogue answers holding a date in that
  form 0 of 75, 75 and 76 (11 of 74 before); answers the judge marks as in another language 1, 0 and 1 (3
  before); catalogue supported 56, 58 and 66 of 80 and correct 72, 73 and 72 (before: 59 to 65 and 69 to 76 in
  five runs); out of scope with no answer 28, 27 and 28 of 30.
- **Not kept:** eight passages, the grading step (measured above; its code is not in this repository), the
  rebuilt collection, a longer reading limit, a higher effort, a stronger writer.

Counts of every run, with no text: `eval/outcomes/answers_literature_settings.json`.

### The catalogue lookup: a second, short vector for each issue

Built and measured on a copy of the graph, then written to the served graph and turned on, on 2026-11-22. The
table's third row is the public service after that.

An issue has one vector, made from its title and its whole catalogue text. For "what was the first stamp of
Costa Rica?" the 1863 issue is 20th: issues that commemorate it tell its story at more length and stand before
it. A second vector made from a short text (the title, the years, the section) is asked with the same question
vector, at the same weight as the first (`scripts/issue_short_vectors.py` writes it and can take it away;
`ASK_SHORT_VECTOR` turns it on).

| Lookup | Catalogue questions (80): issue first | among the three shown | Ranking cases (15): a wanted issue first | among the three shown |
|---|---|---|---|---|
| Without the short vector (served before it) | 78 | 80 | 9 | 12 |
| With the short vector (served since 22 November 2026) | 75 | 80 | 11 | 13 |
| With the short vector, through the public host | 75 | 80 | 11 | 13 |

- The ranking cases are 15 questions a collector would type (`eval/data/ranking_cases.jsonl`); their wanted
  issues were set from the catalogue's titles and no person checked them. They are development questions; the 80
  catalogue questions are the whole set, its held-out half included (that half, measured alone as served, is
  under [Catalogue lookup](#catalogue-lookup)).
- **It is a trade:** three catalogue questions lose the first place and keep a place among the three cards
  shown; two ranking cases gain the first place and the 1863 issue comes into the three.
- **A vector index is approximate, and it showed.** Asked for 40 hits, a short index made with Neo4j's default
  compression returned 37 of the exact 40 on average over the 96 questions, and another first three for 15 of
  them. Made without compression and asked for more hits than there are issues, it returned the exact 40 in
  the exact order for all 96, in about 9 ms. The script makes it that way and checks it against exact cosine
  for every issue.
- **The first vector's index is left as it is served.** It has Neo4j's default compression and is asked for 40
  hits. Measured on the copy, over the same 96 questions: 36.8 of the exact 40 on average, the same first issue
  for 93, the same first three for 85. With exact cosine in its place no count above moves (78 of 80; 9 and 12
  of the ranking cases).
- **Written answers with it, one run through the public host** (the 151 questions and the ten conversations,
  2026-11-22; this run also has the card's lines as phrases): catalogue written 75, supported 66, correct 72 of
  80; literature written 40, supported 23, in full 13, in part 26 of 41; out of scope with no answer 27 of 30;
  citations that did not hold 0 of 378; the follow-ups keep their issue first for 9 of 10. Each count is inside
  the range of the served setting's earlier runs or one answer outside it. `eval/outcomes/answers_hosted-short.json`.

### The sealed set: two runs

The 50 questions of `eval/data/sealed/` (20 catalogue, 20 literature, 10 out of scope) were made on 2026-11-21,
before any of the changes of this part, and were not asked until 2026-11-22, when everything above was decided.
They were asked twice, once each:

- **The code of 21 November 2026, as served when the set was made:** the backend at commit `d27e269`.
- **The code of 22 November 2026:** the backend at commit `5dae0c1` with the short vector on
  (`ASK_SHORT_VECTOR=on`): the card's lines as phrases, the excerpt from the start of a passage.

Both on 22 November 2026, on a development machine against the hosted stores. Neither is the code served since
the web setting was turned on (23 November 2026;
[below](#as-served-two-runs-of-the-whole-set-with-the-web-setting-on)); no run of that code on the sealed
questions is published. The marks are the same judge's, from the
same instructions as above; no person has checked them. Nobody read the answers, and nothing was changed after
these numbers were seen. Every page the two runs showed for a literature question already had a grade (100
passages a run, and the 15 shown for the three out-of-scope questions whose pages were graded when the set was
made), so no page had to be graded before scoring.

| | 21 November 2026, `d27e269` | 22 November 2026, `5dae0c1` |
|---|---|---|
| **Catalogue, 20 questions** | | |
| The issue first, with the fact in its card / among the three shown | 17 / 18 | 17 / 18 |
| A written answer | 19 | 20 |
| Supported | 17 | 18 |
| Correct | 17 | 18 |
| Supported and correct | 15 | 16 |
| Gives what is asked | 17 | 18 |
| **Literature, 20 questions** | | |
| A page that answers among the five passages | 16 | 16 |
| A written answer | 17 | 18 |
| Supported | 12 | 10 |
| In full | 0 | 0 |
| In part | 17 | 18 |
| Gives what is asked: yes / partly / no (a question with no written answer is a no) | 2 / 10 / 8 | 4 / 10 / 6 |
| **Literature, the 16 that share no answering page with a development question** | | |
| A page that answers among the five passages | 12 | 12 |
| A written answer | 13 | 14 |
| Supported | 9 | 8 |
| In full | 0 | 0 |
| In part | 13 | 14 |
| Gives what is asked: yes / partly / no (a question with no written answer is a no) | 2 / 7 / 7 | 4 / 7 / 5 |
| **Out of scope, 10 questions** | | |
| No written answer (the wanted outcome) | 9 | 9 |
| **Sentences, all 50 questions** | | |
| Written with no citation, and removed | 43 of 141 (30%) | 40 of 158 (25%) |
| Citations that did not hold | 0 of 123 | 0 of 139 |
| Shown sentences the judge marked supported / partly / not | 90 / 8 / 0 | 106 / 12 / 0 |
| Cost of a question, USD: mean / maximum | 0.00071 / 0.00141 | 0.00076 / 0.00145 |

- **The literature answers are weaker on these questions than on the development ones.** No answer gets the
  judge's "yes" against its reference, in either run (0 of 20; about 10 of 41 on the development questions),
  and 2 and 4 of 20 give what is asked (14 to 19 of 41 there). Every written answer agrees in part. A page that
  answers is among the five passages for 16 of 20 (36 of 41 there). The development numbers of this document
  were read while the instructions were revised; these were not.
- **The catalogue part holds:** 17 and 18 of 20 correct (69 to 74 of 80 on the development questions).
- **The two runs differ by one or two questions in every row.** With one run each, that is not a finding in
  either direction. The short vector moved no sealed catalogue question: the same 17 first and 18 shown.
- The references of the sealed literature questions are somewhat longer than the development ones (a median of
  288 characters against 240), from more judged pages a question (19 against 12). That may be part of why none
  gets a "yes"; it was not tested.
- 50 questions, one run each, questions written by a model and a model's marks: small counts.

Per-question outcomes: `eval/outcomes/answers_sealed-served.json`, `answers_sealed-chosen.json` (ids, how each
ended, counts, the judge's marks; no answer and no passage). The four questions left out of the 16 are named in
`eval/data/sealed/README.md`.

## A web part: three markers, and a trial with real searches

The code can add a short part written from a web search under an answer, when the catalogue and the literature
do not cover a question or cover part of it (`backend/README.md` has the steps). It sits behind two settings
that are off by default, so **nothing in the earlier parts of this document was measured with it**. This part
holds what was measured before it is turned on. Everything was asked through a backend on the development
machine against the hosted stores, on the development questions only. The sealed set was not touched.

### Read this first

- **Nobody can grade a web sentence for being right.** The test set has no gold for the web. The judge says
  whether a sentence is stated by the web page it cites, and nothing else.
- **The marks are a model's;** no person has checked them. One run of each thing, except the markers (three).
- The 30 "out of scope" questions of the set are two kinds by their own field: 20 outside the scope (not about
  stamps, or another country's) and 10 about Costa Rican stamps whose answer is not in the sources. Only the
  20 are meant to be kept from the web; the writer's marker is what keeps them, and it is the model's judgment.

### The three markers of the write call

With the setting on, the write call says which of three things happened when it does not answer in full:
`OUT_OF_SCOPE`, `NOT_COVERED` (in scope, the documents do not answer), or an answer that ends with a last line
`PART_ONLY`. Two sentences of its instructions change and nothing else. Three runs of the 151 questions and the
ten follow-ups; the first was graded.

| | Run A | Run B | Run C |
|---|---|---|---|
| **The 20 questions outside the scope** | | | |
| `OUT_OF_SCOPE` (no answer, no ticket for the web) | 19 | 20 | 20 |
| An answer was written | 1 | 0 | 0 |
| **The 10 not in the sources** | | | |
| `NOT_COVERED` (no answer; the web is asked) | 9 | 10 | 9 |
| `OUT_OF_SCOPE` | 1 | 0 | 0 |
| An answer was written, marked as part | 0 | 0 | 1 |
| **Catalogue questions with no answer** | 6, all `NOT_COVERED` | 5, all | 5, all |
| **Written answers that end with `PART_ONLY`** | | | |
| Literature | 20 of 41 | 17 of 40 | 17 of 40 |
| Catalogue | 12 of 74 | 12 of 75 | 11 of 75 |
| Follow-ups | 2 of 10 | 2 of 10 | 2 of 10 |

- **The other counts of run A are inside the range of the served setting's earlier runs,** with one row one
  answer above it: catalogue written 74, supported 61, correct 72; literature written 41, supported 27, in full
  10, in part 29, gives what is asked 20 (14 to 19 before); out of scope with no answer 29 of 30; no citation
  that did not hold.
- **How the part marker agrees with the judge, run A.** Against "gives what is asked": on the literature
  answers it fired on 7 of the 20 marked yes, 7 of the 14 marked partly and 6 of the 7 marked no; on the
  catalogue answers on 12 of the 71 marked yes and on none of the 3 others. All together: **19 of 91 marked
  yes, 13 of 24 marked partly or no.** Against "agrees with the reference", literature: 2 of 10 in full, 16 of
  29 in part, 2 of 2 not.
- **It is a weak signal on the literature answers.** It fires more often where the judge finds less, and it
  still fires on a third of the answers the judge calls complete. The judge compares with a reference the
  writer never sees.
- **How steady it is, per question written in all three runs:** catalogue (74): never 61, in two runs 5, in all
  three 8. Literature (40): never 17, in one run 6, in two 4, in all three 13.

### Why it fired on catalogue answers, and what changed

The 12 catalogue answers that fired were of three kinds of fact only (stamp quantity, varieties, Scott
equivalent), the three whose questions name the catalogue ("Mena number 188"). No card said whose catalogue it
is. With the setting on, the card's title as the model reads it now says so. The 80 catalogue questions once
more, graded:

| Catalogue, 80 questions | Before (run A) | With the catalogue named |
|---|---|---|
| A written answer | 74 | 80 |
| Not covered | 6 | 0 |
| Ends with `PART_ONLY` | 12 | 1 |
| Supported | 61 | 67 |
| Correct | 72 | 77 |
| Supported and correct | 59 | 65 |
| Gives what is asked | 71 | 77 |
| The issue first / among the three shown | 75 / 80 | 75 / 80 |

- **The counts moved above the range of every earlier run** (written 73 to 75, correct 69 to 74). By this one
  run, the catalogue questions that ended "not covered" had the same cause as the marker.
- **This is one run, and it is not what is served while the setting is off:** off, the model reads the card's
  title as before, and the catalogue rows of the earlier parts stand.

### A trial with real searches

26 searches with the search service the code uses (Tavily, a basic search of five results), on the development
questions for which a marker had asked for the web in run A. They were alternated into two halves: one with
the fixed words "Costa Rica philately" after the question in the query, one without. The halves hold different
questions, so the columns are not one question asked two ways.

| | With the fixed words | Without |
|---|---|---|
| Questions asked again / asked the web | 24 / 14 | 24 / 12 |
| A web part was shown | 10 | 6 |
| Nothing to add, or no sentence left | 3 | 4 |
| The web call said "out of scope" | 1 | 2 |
| Results returned / kept | 70 / 61 | 60 / 54 |
| Sentences written / removed for no citation | 38 / 18 | 23 / 8 |
| Citations that did not hold | 0 of 25 | 0 of 16 |
| Shown sentences the judge marked supported / partly / not | 16 / 3 / 1 | 12 / 3 / 0 |
| Different sites among the results | 29 | 42 |

- **Shown web sentences: 28 of 35 supported by the page they cite, 6 partly, 1 not.** For the answers written
  from the catalogue and the literature the same judge gave 280, 30 and 2 of 312 (run A).
- **The fixed words stay.** With them a web part was shown for 10 of 14 searches, from 29 sites; without them
  for 6 of 12, from 42 sites, among them a customs service, a government's travel advice and sites that
  prepare for a postal operator's exams.
- **By case:** under a part answer, 12 web parts, 4 with nothing to add, and 1 stopped as out of scope (the one
  question outside the scope that had got an answer). For the 9 questions about Costa Rican stamps whose answer
  is not in the sources: 4 web parts, 3 nothing, 2 out of scope. Several of those 9 ask about something that
  does not exist; a web part written for one cannot be checked here.
- **Sites left out after the trial:** video and social sites, a marketplace and the search service's own site
  were returned often and cited almost never. The code now drops them, and other marketplaces and their price
  guides, and asks the search not to return them. The counts above are from before that.
- The web call took 3,554 input and 526 output tokens on average, about 0.0006 USD, and 2.8 s on average (5.1
  at most), after the search.
- **The search service's count of credits runs behind.** After the 26 searches its usage route still gave the
  earlier count eleven minutes after the first. The rule that allows a search reads that route, so the backend
  also adds the searches it made itself in the last two hours
  ([docs/OPERATIONS.md](docs/OPERATIONS.md#how-many-searches)).

Per-question outcomes: `eval/outcomes/answers_web-mk-a.json`, `-b`, `-c` and `answers_web-mk-cat.json` (as the
other runs, with whether an answer covers all or part), and `eval/outcomes/web_trial.json` (for each question
asked: how it ended, whether the web was asked, how the web part ended, its counts and the judge's marks; no
question, no answer, no page's text, title or address).

### As served: two runs of the whole set with the web setting on

The hosted demo has the web setting on since 2026-11-23. Two runs of the 151 questions and the ten follow-ups
with it on, each asked once. No search was made in either: the runs ask for the answer from the catalogue and
the literature and never for the web part.

- **`web-final`:** a backend on the development machine against the hosted stores, before the rule on where a
  sentence ends was changed.
- **`hosted-y`:** through the public service, after that change. "How it works" on the site reads its figures
  from this run.

| | `hosted-y` | `web-final` |
|---|---|---|
| Catalogue (80): the issue first / in the first three | 75 / 80 | 75 / 80 |
| Catalogue: written / supported / correct / supported and correct | 80 / 63 / 76 / 60 | 80 / 63 / 78 / 62 |
| Catalogue: gives what the question asks | 76 | 78 |
| Literature (41): a page that answers among the five | 36 | 36 |
| Literature: written / supported | 40 / 25 | 40 / 26 |
| Literature: correct ("yes") / in part | 10 / 30 | 10 / 28 |
| Literature: supported and correct | 7 | 6 |
| Literature: gives what the question asks | 17 | 18 |
| Out of scope (30): no written answer | 27 | 28 |
| Sentences with no citation, removed (catalogue and literature) | 94 of 380 | 95 of 395 |
| The same over every row, follow-ups and out of scope too | 101 of 410 | 104 of 427 |
| Citations that did not hold (every row) | 0 of 376 | 0 of 386 |
| Shown sentences the judge marked supported / partly / not (every graded answer, out of scope too) | 259 / 33 / 1 | 273 / 32 / 0 |
| Follow-ups: the first question's issue first / in the first three | 9 / 10 | 9 / 10 |
| Cost of a first question, mean / most, USD | 0.00070 / 0.00137 | 0.00071 / 0.00141 |
| Wait for the evidence / the answer, median, s | 1.04 / 2.94 | 1.53 / 3.76 |

- **The grades are a model's and no person has checked them;** one run of each, so a difference of a few
  questions between the columns is what the same setting gives when asked twice.
- **Against the served setting before the web setting** (the columns of "Written answers" and of the short
  vector): every catalogue question now gets a written answer (73 to 75 before) and 76 and 78 are correct (69 to
  74 before), as in the catalogue run above; the literature counts are inside their earlier ranges.
- **Where a sentence ends.** `hosted-y` ran with the rule of commit `83c9ad7` (22 November 2026): a sentence did
  not end at an abbreviation's full stop ("No.", "pp."), nor before a number or any lower-case letter; before
  it, as in `web-final`, a piece cut off at "No. 5" needed a citation of its own to be shown. In `hosted-y`, 13
  of 309 shown sentences hold a place the earlier rule would have cut: 11 places at an abbreviation, 6 before a
  lower-case letter, none before a number. The rule on numbers can take two sentences for one; in this run it
  did not. The rule changed again at commit `f5b784a` (23 November 2026), after both runs, and no published run
  has it: a full stop before a lower-case letter now ends a sentence unless what stands before it reads as an
  abbreviation (a single letter, letters with full stops between them, "etc.", "cts."), and a single capital
  letter before a full stop is an initial ([backend/README.md](backend/README.md#the-written-answer-post-apichat)).
- **The markers in `hosted-y`:** of the 20 questions outside the scope, 19 ended "out of scope" and 1,
  `oos-013-en`, got an answer marked as part, and with it a ticket for a web search; in `web-final` that
  question ended "out of scope", and another, `oos-009-en`, got an answer marked as full. Of the 10 whose answer
  is not in the sources, 8 ended "not covered" and 2 (`una-001-en`, `una-008-es`) got an answer marked as part,
  with a ticket. The part marker fired on no catalogue answer and on 18 of 40 literature answers.
- The waits of `hosted-y` are through the public service with the service awake; those of `web-final` are on
  the development machine.

Per-question outcomes: `eval/outcomes/answers_hosted-y.json` and `answers_web-final.json`, each with a summary
of its run (retrieval counts and the two waits). The figures of "How it works" that are in no other outcome
file, each with where it is stated, are in `eval/outcomes/how_it_works.json`.

## The literature in both languages

Since version 1.1 the literature is searched with the question and with the question in the other of the two
languages, and the two lists are joined ([backend/README.md](backend/README.md#the-question-path-post-apiask) has
the steps: query rewriting, multi-query retrieval, reciprocal rank fusion). This part says what was found before
the change, how the number of passages and the depth of the lists were chosen, and what the same questions gave
before and after. Measured on 24 November 2026.

### Read this first

- **The grades are a model's. No person has checked them.** The pages the new search brought up that no judge
  had seen were graded by the judge of the literature gold (`gpt-6.1-sol`, high effort) with the same
  instructions, before anything was scored: 250 pages (115 graded 0, 55 graded 1, 80 graded 2). The published
  gold holds them, and with them the 425 pages graded on 21 November for the rebuilt collection, which the
  published file did not hold yet: 1,657 judged pages in all (`eval/data/questions_literature.jsonl`). Every
  page any run of this part showed for a literature question has a grade.
- **The choices were made on the development questions** (26 literature questions). The held-out questions (15)
  were scored once, after the choice. The sealed set was not run.
- **The test set shared the gap it measures.** Its gold was pooled from searches made with the question alone,
  so most of its graded pages are in the question's language. A page in the other language that answers a
  question had no grade until this part's judging.
- **A passage's language is told by a rule**, not by a model: its function words (`oxcart/language.py`). A
  passage with fewer than five such words, or with both languages in comparable parts, counts as neither (about
  one shown passage in eight).
- **The second text is a model's translation.** The rewriting call's instructions were revised once after its
  replies to all 151 questions were counted, held-out ones included: 5 replies had given an English question
  that quotes Spanish words back unchanged, and a sentence was added for that case. No answer and no search
  result was read for it.
- One run of a setting is one sample: the writer's answers change from run to run
  ([Written answers](#written-answers)).

### What was found

As served until then: one vector of the question, one search. For each test question, the first 5, 20 and 50
passages of that search, by the passage's language against the question's (mean number of passages in the other
language; questions with none):

| Questions | n | Among the first 5 | Among the first 20 | Among the first 50 |
|---|---|---|---|---|
| Literature, in English | 22 | 0.59; 15 with none | 3.18; 7 with none | 8.05; 2 with none |
| Literature, in Spanish | 19 | 0.79; 10 with none | 3.58; 3 with none | 8.63; none with none |
| Catalogue, in English | 40 | 0.20; 33 with none | 2.17; 21 with none | 5.05; 15 with none |
| Catalogue, in Spanish | 40 | 0.70; 25 with none | 2.27; 13 with none | 6.85; 4 with none |
| Catalogue and literature, in English | 62 | 0.34; 48 with none | 2.53; 28 with none | 6.11; 17 with none |
| Catalogue and literature, in Spanish | 59 | 0.73; 35 with none | 2.69; 16 with none | 7.42; 4 with none |

Of the first five passages of an English question, 73% were in English, 11% in Spanish and 17% could not be
told; of a Spanish question, 78% in Spanish, 13% in English and 9% not told. So 83 of the 121 questions of the
catalogue and the literature got no passage in the other language among the five shown, whatever the other
language's publications held.

### Five passages, and lists of five

The rewriting call was asked once for each of the 151 questions; both texts were searched to 50 passages; the
two lists were joined off line by reciprocal rank fusion (constant 60), each list cut at a depth, and the first
passages of the joined list were scored with the gold. Development literature questions, 26: questions with a
page graded 2 among the first passages, and (in brackets) questions whose first five hold both languages.

| | The first 5 | The first 6 | The first 8 |
|---|---|---|---|
| Before: the question's own list | 21 (10) | 22 | 25 |
| Joined, each list cut at 5 | 24 (26) | 25 | 25 |
| Joined, each list cut at 8 | 24 (26) | 25 | 25 |
| Joined, each list cut at 10 | 22 (24) | 25 | 25 |
| Joined, each list cut at 20 | 24 (21) | 24 | 25 |
| Joined, each list cut at 50 | 24 (21) | 24 | 26 |

- **Five passages are shown and given to the writer, as before.** At the same five the joined list answers 24 of
  the 26 questions against 21 and loses none. Six or eight passages give one more question at most, and one
  question is 3.8 points of 26; eight passages of the question's own list had been tried before and did not
  raise the answers ([What was kept](#what-was-kept)). The same number also leaves the write call's cost as it
  was and lets the answers be compared before and after. The choice was made on the search, before any answer
  of the new search was read; eight passages were tried afterwards ([below](#the-same-questions-before-and-after)).
- **Each search returns five.** Deeper lists answer as many questions (the row at 10 is two lower, at 20 and 50
  the same as at 5), and they fill the five shown with passages that both searches found, which left 5 of the
  26 questions with one language only. A search of 50 passages takes the same 0.09 s as one of 5, so the depth
  was not chosen for time.
- **The fusion looks at ranks, not at how good a passage is.** Among the five shown for the 26 questions, the 45
  passages that only the translation's search found were graded 17 answers, 12 supports, 16 neither; the 45
  passages that were among the question's own five and are not among the joined five, 14, 14 and 17. Their
  similarity to the text that found them: median 0.67 for those that came in, 0.64 for those that left; 3 of the
  45 are under 0.60. No minimum similarity was added.
- **One document in both languages.** Some publications print a text in Spanish and in English. Among the five
  shown, one document appears in both languages for none of the 41 literature questions, 2 of the 80 catalogue
  questions and 2 of the 30 out of scope. Nothing was added against it.

**Held out, once, after the choice** (15 literature questions): a page graded 2 among the five for 14, against
15 with the question's own list; one question lost (`lit-014-en`), none won. Whole set, 41 questions: 38 against
36 (three development questions won, that one lost); of all 49 drafts, 38 against 36. Questions whose five hold
both languages: 41 of 41 against 16.

Per-question ranks and counts of this off-line comparison: `eval/outcomes/both_languages.json`. Its script is
not in this repository.

### The same questions, before and after

The 151 questions and the ten follow-ups, asked once a run through `POST /api/chat` of a backend on the
development machine, in hosted mode, against the hosted stores, with the web setting and the short vector on (as
served) and the excerpt from a passage's start; judged by the same judge with the same two prompts as every run
above. Eight runs, all on 24 November 2026:

- **Before:** the code as it was (`main` at `1dc9c10`), twice; and that code with the fix of the joined sentences
  alone (below), once. One text, one literature search.
- **After, five passages:** this version, three times.
- **After, eight passages:** this version with `ASK_PASSAGES=8` (each search then returns eight), twice. Tried
  after the first numbers were seen, to tell whether the passages that left the five explain them.

| | Before | Before | Before, with the fix | After, 5 | After, 5 | After, 5 | After, 8 | After, 8 |
|---|---|---|---|---|---|---|---|---|
| Run (`eval/outcomes/answers_v11-…`) | `before` | `before-2` | `fix-1` | `after-1` | `after-2` | `after-3` | `p8-1` | `p8-2` |
| Literature (41): a page graded 2 among the first five | 36 | 36 | 36 | 38 | 38 | 38 | 38 | 38 |
| The same, development questions (26) | 21 | 21 | 21 | 24 | 24 | 24 | 24 | 24 |
| Catalogue and literature (121): shown passages in both languages | 38 | 38 | 38 | 119 | 118 | 119 | 121 | 121 |
| Catalogue (80): the issue first, with the fact in its card | 75 | 75 | 75 | 75 | 75 | 75 | 75 | 75 |
| Catalogue: written / supported / correct | 80 / 63 / 77 | 80 / 60 / 76 | 80 / 63 / 78 | 80 / 62 / 74 | 80 / 65 / 75 | 80 / 59 / 77 | 80 / 66 / 75 | 80 / 58 / 72 |
| Catalogue: gives what the question asks | 79 | 77 | 78 | 74 | 73 | 76 | 74 | 73 |
| Catalogue, development questions (48): correct | 47 | 45 | 47 | 44 | 44 | 45 | 44 | 42 |
| Literature (41): written / supported | 41 / 29 | 40 / 26 | 38 / 31 | 41 / 27 | 41 / 24 | 41 / 26 | 40 / 20 | 40 / 24 |
| Literature: correct ("yes", in full) / in part | 10 / 30 | 10 / 30 | 10 / 27 | 8 / 32 | 8 / 33 | 7 / 33 | 10 / 30 | 12 / 27 |
| Literature: gives what the question asks | 17 | 19 | 14 | 15 | 16 | 14 | 14 | 17 |
| Literature, development questions (26): in full | 6 | 6 | 6 | 5 | 5 | 4 | 4 | 7 |
| Answers in another language than the question: English / Spanish questions | 2 / 0 | 1 / 0 | 0 / 1 | 1 / 0 | 2 / 1 | 0 / 1 | 0 / 2 | 1 / 1 |
| Citations that did not hold (every row) | 0 of 390 | 0 of 377 | 0 of 354 | 0 of 383 | 0 of 377 | 0 of 393 | 0 of 396 | 0 of 394 |
| Sentences with no citation, removed (every row) | 90 of 405 | 108 of 414 | 108 of 413 | 103 of 436 | 104 of 445 | 101 of 458 | 103 of 457 | 93 of 437 |
| Answers with two sentences shown joined | 7 | 14 | 0 | 0 | 0 | 0 | 0 | 0 |
| Out of scope (30): no written answer | 28 | 28 | 30 | 28 | 29 | 28 | 28 | 30 |
| Follow-ups (10): the first question's issue first / in the first three | 9 / 10 | 9 / 10 | 9 / 10 | 9 / 10 | 9 / 10 | 9 / 10 | 9 / 10 | 9 / 10 |
| Cost of a question, USD: median / mean | 0.00064 / 0.00071 | 0.00065 / 0.00071 | 0.00063 / 0.00068 | 0.00084 / 0.00090 | 0.00085 / 0.00089 | 0.00085 / 0.00090 | 0.00095 / 0.00100 | 0.00095 / 0.00101 |
| Wait for the evidence / the answer, median, s | 2.94 / 5.24 | 2.99 / 5.31 | 2.07 / 4.83 | 4.27 / 6.79 | 4.31 / 6.88 | 2.69 / 5.29 | 2.65 / 5.59 | 2.74 / 5.55 |

- **The search finds more.** A page that answers among the five for 38 of the 41 literature questions in every
  run after, 36 in every run before (24 against 21 of the development questions); passages in both languages for
  118 to 121 of the 121 questions of the catalogue and the literature, against 38. With five passages, a
  literature question gets 2.1 to 2.2 of them in the other language (English and Spanish questions), against
  0.6 to 0.8; a catalogue question 1.7 to 2.2, against 0.2 to 0.8.
- **The written answers did not rise with it; by the judge's marks they are a little lower.** With five
  passages, the literature answers that agree in full with the reference are 8, 8 and 7 of 41, against 10 in all
  three runs before, and on the development questions 5, 5 and 4 of 26 against 6. The catalogue answers that
  state the catalogue's value are 74, 75 and 77 of 80 against 77, 76 and 78; earlier runs of the served setting
  gave 69 to 78. Two things were looked at:
  - *Which answers moved.* Among the literature questions, `lit-006-es` was in full in all three runs before and
    in none after, and `lit-002-es` in two before and none after: a page of the question's own language that
    answered them left the five, in the first case for a page in the other language that is also graded 2. Over a run, more of the shown passages
    stand on pages graded 2 (94 against 90) and more of the cited ones (64 against 59). Among the catalogue
    questions, counting the runs with eight passages too, one is correct less often after and one more often;
    every answer cites the right issue's card before and after. The catalogue's lower counts are spread over different questions from run to run.
  - *The reference shares the gap.* "In full" compares an answer with a reference the judge wrote from the pages
    of its first pass, which the question's own search had pooled. An answer written from a page in the other
    language that the judge graded as answering can differ from that reference. The references were not written
    again, so how much of the drop is the answers' and how much the measure's is not known.
- **With eight passages** the literature answers in full are 10 and 12 of 41 (two runs), as before or more, and
  their supported counts are the lowest of the table (20 and 24); the catalogue answers are no better (75 and
  72 correct); a question costs 0.0010 USD. Five stayed the default: it was chosen on the search, before any
  answer was read, and two runs do not settle the other.
- **Answers in another language than the question:** 4 in the three runs before (1.3 a run), 5 in the three
  runs after with five passages (1.7), 4 in the two with eight (2.0). On Spanish questions: 1 in three runs
  before, 2 in three after, 3 in two with eight. Small counts; not lower.
- **No citation failed to hold** in any run. The fix of the joined sentences is in every run after and in the
  third run before: no answer shows two sentences joined, where 7 and 14 did.
- **Cost and time.** A question now takes two model calls. The rewriting call: 1,525 tokens in and 62 out on
  average, 0.00018 USD, 1.03 s at the median and 1.84 s at the 95th percentile (`after-1`; 0.97 to 1.04 s in the
  five runs). A question costs 0.0009 USD on average against 0.0007, and 0.0015 at most. The evidence reaches
  the page about a second later than before: the rewriting call stands in front of the search. The waits of the
  table are from the development machine, which the runs shared with the judge or with another run in different
  ways: they are not a comparison of two versions. Through the public service this version has not been
  measured.

**What this part does not show.** One day, one judge, questions whose gold and references were made with the
old search. Whether a collector reads a better answer when the evidence comes in both languages was not asked
of a person.

## Other limits

- The pool that produced the gold was built from keyword, vector and hybrid search, so those arms are favoured
  over any method not in the pool. The top-ups in step 5 remove the bias between the runs reported here, not
  towards a future method. The search in both languages was such a method: its pages were graded before it was
  scored, and the reference answers were left as they were
  ([The same questions, before and after](#the-same-questions-before-and-after)).
- Hybrid search on the hosted collection does not repeat from run to run.
- Latency from a home connection to the hosted cluster, warm, per search, without the embedding call: keyword
  77–80 ms median, vector 86–87 ms, hybrid 120–123 ms. These are the searches alone; the waits through the
  hosted backend are in [Cost and waits](#cost-and-waits) and in the two runs with the web setting on.
- The Spanish names of issues used in the catalogue questions were written for this test set and have not been
  reviewed by a philatelist.

## Numbers with no published record

These were measured during development, and their per-question records are not in this repository. They are
reported as measured; nothing here lets a reader recount them.

- The gold: 594 pooled pages and 1,078 judged pages ([How the literature gold was made](#how-the-literature-gold-was-made)).
- The second model on every fifth question, 117 pages (the same section).
- Distinct pages in the first five, 2.7 against 5.0, and 98.7% of the text kept after the collapse
  ([How small can the literature collection be](#how-small-can-the-literature-collection-be)).
- Shortened vectors against the API's own, cosine 0.9999 on 20 passages ([Vector size](#vector-size)).
- Two identical vector runs with the same first five, and hybrid's 79% to 97% ([Search arm](#search-arm)).
- The stopword comparison ([Stopwords](#stopwords)).
- The scores that tell out-of-scope questions apart
  ([Can a score cut-off tell out-of-scope questions apart](#can-a-score-cut-off-tell-out-of-scope-questions-apart)).
- The follow-up's rewrite call on 85 questions (its tokens, cost and 0.9 s) and the comparison of its
  instructions on 20 questions ([Cost and waits](#cost-and-waits)).
- The waits of the first three columns of [Cost and waits](#cost-and-waits), and of the runs `hosted` and
  `hosted-2`; the waits of `hosted-y` and `web-final` are in their files.
- The three runs of a card's lines as phrases: their catalogue counts, and the dates and languages counted in
  them ([What was kept](#what-was-kept); their literature counts are in `answers_literature_settings.json`).
- The vector indexes against exact cosine: 37 and 36.8 of the exact 40, the same first issue and first three, the
  96 questions, about 9 ms ([The catalogue lookup: a second, short vector](#the-catalogue-lookup-a-second-short-vector-for-each-issue)).
- In the web trial, the distinct sites (29 and 42), the web call's seconds, and how far the usage route ran
  behind ([A trial with real searches](#a-trial-with-real-searches); the tokens are in `web_trial.json`).
- The 13 places of 309 sentences counted for the rule on where a sentence ends
  ([As served](#as-served-two-runs-of-the-whole-set-with-the-web-setting-on)).
- The search latencies from a home connection ([Other limits](#other-limits)).
- For the literature in both languages: the 0.09 s of a search at 5 and at 50 passages, the five replies of the
  rewriting call that came back unchanged, and which answers moved between the runs (the counts of shown and
  cited passages on pages graded 2) ([The literature in both languages](#the-literature-in-both-languages)).
- The cost of all question embeddings, under 0.01 USD ([Data notes](#data-notes)).
- In the README: the corpus counts (1,424 documents, their years; 653 passages from 296 documents for the First
  Issue), the store-dependent tests that passed on 2026-11-18, and the half minute the demo takes to wake.

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
# unit tests (no store needed): the four folders the workflow runs
python -m pytest eval/tests oxcart/tests pipeline/first_issue_graph/tests backend/tests

# literature questions against a collection: writes local-data/eval/results/run_<label>_<split>.json
scripts/with-key.sh OPENAI_API_KEY=<entry> WEAVIATE_URL=<entry> WEAVIATE_API_KEY=<entry> -- \
    python -m eval.run --label cloud-K --split dev

# score stored runs with the current gold, both denominators
python -m eval.table local-data/eval/results/run_cloud-K_dev.json --split dev

# catalogue questions against the graph
scripts/with-key.sh OPENAI_API_KEY=<entry> -- python -m eval.catalogue_arm --split dev --mode vector
#   as served, with the short vector index too (the graph must hold it)
scripts/with-key.sh OPENAI_API_KEY=<entry> -- python -m eval.catalogue_arm --split heldout --mode vector --short

# written answers: ask every question through a running backend, then grade and print the tables
OXCART_API=http://127.0.0.1:8090 OXCART_EVAL_KEY=<the backend's EVAL_ACCESS_KEY> python -m eval.chat_arm run --label <name>
python -m eval.answer_judge prepare --label <name> --dir local-data/eval/judge/answers-<name> --references <judgment files>
#   ... run a judge model once per file of that folder's inputs/, writing outputs/<id>.json (see eval/answer_judge.py) ...
python -m eval.answer_judge collect --dir local-data/eval/judge/answers-<name>
python -m eval.chat_arm table --label <name> --grades local-data/eval/judge/answers-<name>/grades.json
```

Per-question outcomes behind the retrieval tables: `eval/outcomes/stage2.json` and, for the catalogue lookup as
served, `eval/outcomes/catalogue_heldout_served.json` (ids and ranks only).
