# The sealed test set

50 questions kept apart from the development set (`eval/data/`): 20 about catalogue facts, 20 answered by the
philatelic literature, 10 out of scope. It exists because the development questions stopped being held out for
the written answers: their answers were read while the instructions were revised.

## The rule

- It was made on 2026-11-21, with the served graph at commit `d27e269`, **before any change to that graph**.
- It is run twice, at the end of the work on answer quality: once on the graph of `d27e269` and once on the graph
  that work chooses. Both results are published, whatever they say.
- Its scoring prints counts. Nobody reads the answers written for it, and nothing is changed after its numbers
  are seen.

## How it was made

- **Catalogue (20: 10 facts, each asked in English and in Spanish).** Drawn by `eval/gen_catalogue.py` with
  `OXCART_TEST_SET=sealed`: another seed, and no issue the development set uses. The gold value of each is read
  from the graph. No Scott-number fact: the development set uses the issues of every one the graph holds.
- **Literature (20: 9 questions in both languages, 2 in one).** 14 questions were written in both languages by a
  model of a third vendor (Gemini 3.8 Flash) from two public lists only: the catalogue's issue titles and the
  development set's questions, which it was told not to repeat. It saw no passage. The first ten results of
  keyword, vector and hybrid search on the hosted cluster were pooled for the 28 drafts (593 pages) and graded
  by the judge of the development set's gold (`gpt-6.1-sol`, high). A draft entered the set only if a page was
  graded as answering it: 20 of 28 did. `drafts_literature.jsonl` holds all 28; results are given over both
  counts.
- **Out of scope (10).** Written by the same third model: 4 not about stamps, 3 about another country's stamps,
  3 about Costa Rican stamps but asking for what no publication could hold. For those last 3 the judge graded
  the pooled pages too: none answers them.

## Limits

- The gold is a model's; no person has checked it. A page outside the pool was never graded and counts as a
  miss if a later search brings it up.
- The questions were written by a model and were not edited by a person. The assistant that builds the system
  did not write them and has not read them.
- 50 questions, one run each: small counts.

To use it: `OXCART_TEST_SET=sealed` before any `eval` command.
