# `retrieve.py` — the Retrieval half of GraphRAG (and how to feed an LLM)

## TL;DR

`retrieve.py` is the **R in RAG**. Given a natural-language question about the
1863 First Issue, it gathers a **grounded, citation-backed context bundle** from
three sources and returns it. **It does NOT write the answer** — there is no LLM
call inside it (that is the owner constraint). You take its output and hand it to
an LLM as context for the **G (generate)** step. The whole point is that the LLM
then answers *only* from this evidence and cites it, so the answer is verifiable
instead of hallucinated.

```
            ┌──────────────── retrieve.py (this module) ─────────────────┐
question ──►│  1. DOMAIN CARD     (Neo4j: exact catalog facts)           │
            │  2. NEO4J LEXICAL   (clean chunk graph: cited passages)    │──► context bundle
            │  3. WEAVIATE        (read-only baseline over full corpus)  │       (dict)
            └────────────────────────────────────────────────────────────┘
                                       │
                                       ▼   (YOU add this — outside the prototype)
                              LLM "generate" step  ──► grounded, cited answer
```

---

## 1. What each of the three retrievers gives you

| Source | What it returns | Why it matters for grounding |
|--------|-----------------|------------------------------|
| **Domain card** (Neo4j structured) | The exact facts: Issue metadata, every Mena `Stamp` (denomination, color, perf, quantity), the `EQUIVALENT_TO` Scott stamps (Scott #, mint/used value, perforation, variety_of), and the `Illustration` design + Scott notes. | **High-precision "what we know."** These are catalog facts, not prose — the LLM can state denominations/values/Scott numbers with confidence. |
| **Neo4j lexical evidence** | Up to `k` passages from the **sanitized** chunk graph, each a citation `{doc_id, page, chunk_id, snippet, score, link_score, via}`. Two paths merged + de-duped: fulltext (`chunk_text_fts`) over the question terms, and chunks already linked via `MENTIONS`/`MENTIONS_STAMP`. | **Clean, provenance-tagged prose.** Each passage says where it came from (doc + page) and why it was linked (`score`/`link_score`). This is the evidence the LLM quotes/cites. |
| **Weaviate evidence** | Up to `k` passages from the existing `Oxcart` collection (BM25 always; hybrid if an OpenAI key is set). Snippet prefers the clean `text_original`. | **Recall safety net + cross-check** over the *whole* corpus (incl. non-OXCART docs and chunks the graph didn't materialize). Lets you see if the graph missed something. |

The two evidence sources are kept **separate on purpose** so you (and the LLM)
can see graph-grounded evidence vs. a plain search baseline side by side.

---

## 2. Exact output shape (`answer(question, k=6) -> dict`)

```jsonc
{
  "domain": {
    "issue_id": "CR-1863-FIRST-ISSUE",
    "found": true,
    "title": "First Issue",
    "country": "Costa Rica",
    "issue_dates": "{\"placed_on_sale\": \"1863-12-01\", \"demonetized\": \"1883-01-31\", ...}",
    "perforation": "12",
    "plain_raw_text_excerpt": "## First Issue April 11, 1863. Decree #2 ... ABNCo ...",  // <= 600 chars
    "stamps": [
      {
        "catalog_no": "1", "denomination_value": 0.5, "denomination_unit": "real",
        "color": "blue", "perforation": "12", "status": "regular",
        "quantity_reported": 3000000,
        "equivalent_scott": [
          { "scott_number": "1", "denomination": "½r", "color": "blue",
            "mint_value": 0.5, "used_value": 1.1, "perforation": "Perf. 12",
            "confidence": "high",
            "design_name": "Coat of Arms",
            "design_description": "A dark blue historical postage stamp ..." }
        ]
      }
      // ... Mena 1A, 2, 3, 4
    ],
    "scott_roster": [
      { "scott_number": "1", "denomination": "½r", "color": "blue", "design_name": "Coat of Arms" },
      { "scott_number": "1b", "description": "Pair, imperf. horiz." }
      // ...
    ]
  },

  "neo4j_evidence": [
    {
      "chunk_id": "OXCART75:008:1-1:0", "doc_id": "OXCART75", "page": 8,
      "snippet": "Observations on the Stamps of the First Issue – Carlos Saenz Mata …",  // <= 280 chars
      "score": 12.0,          // fulltext relevance (when via="fulltext")
      "link_score": 12.0,     // lexicon link strength (how strongly it's about the FI)
      "via": "fulltext"       // or "mentions"
    }
    // ... up to k items, de-duped by chunk_id
  ],

  "weaviate_evidence": [
    {
      "chunk_id": "Saenz Covers First Issue:035:0-0:0", "doc_id": "Saenz Covers First Issue",
      "page": 35, "snippet": "HALF REAL STAMP. Bisected stamp of half real, probably from the second plate …",
      "score": 34.367, "via": "bm25"   // or "hybrid"
    }
    // ... up to k items, de-duped by chunk_id
  ]
}
```

**Graceful degradation:** if Neo4j is down, `domain.found = false` and
`neo4j_evidence = []`, but Weaviate evidence still returns. If Weaviate is down,
the domain card + Neo4j evidence still return. The bundle is never empty just
because one backend is unavailable.

---

## 3. How to run it

### CLI (prints a human-readable answer card)

```powershell
# default question
".venv-clean\Scripts\python.exe" first_issue_graphrag\retrieve.py

# your own question, more passages per source
".venv-clean\Scripts\python.exe" first_issue_graphrag\retrieve.py --q "What plate varieties exist on the half real?" --k 8

# windows console + special glyphs (½):
$env:PYTHONIOENCODING="utf-8"; ".venv-clean\Scripts\python.exe" first_issue_graphrag\retrieve.py --q "Who printed the 1863 issue and in what colors?"
```

Good example questions (all stay within the First Issue scope):
- "Tell me about the half real blue stamp of the Costa Rica first issue"
- "Who printed the first issue and what perforation is it?"
- "What is the Scott value of the 2 reales scarlet?"
- "What plate varieties or constant flaws exist on the first issue?"
- "When was the first issue demonetized and what happened to the remainders?"

### Programmatic (the normal way to use it in an app)

```python
import sys; sys.path.insert(0, "first_issue_graphrag")
from retrieve import answer

ctx = answer("Tell me about the half real blue stamp", k=8)
domain   = ctx["domain"]              # structured facts
passages = ctx["neo4j_evidence"]      # cited, clean passages
baseline = ctx["weaviate_evidence"]   # corpus baseline
```

---

## 4. The "generate" step — turning the bundle into an LLM answer

`retrieve.py` deliberately stops at evidence. Here is the pattern you add
**downstream** (this is outside the prototype's no-direct-LLM rule — it's *your*
application code). Two pieces: a context builder (pure, no LLM) and the LLM call.

### 4a. Build a prompt context string from the bundle (no LLM)

```python
def build_context(ctx: dict) -> str:
    d = ctx["domain"]
    lines = ["# FIRST ISSUE — DOMAIN FACTS (authoritative catalog data)"]
    lines.append(f"Issue: {d.get('title')} ({d.get('country')}), perforation {d.get('perforation')}")
    lines.append(f"Dates: {d.get('issue_dates')}")
    if d.get("plain_raw_text_excerpt"):
        lines.append(f"Catalog note: {d['plain_raw_text_excerpt']}")
    for s in d.get("stamps", []):
        eq = "; ".join(f"Scott {x['scott_number']} ({x.get('color')}, mint {x.get('mint_value')}, used {x.get('used_value')})"
                       for x in s.get("equivalent_scott", []))
        lines.append(f"- Mena {s['catalog_no']}: {s.get('denomination_value')} {s.get('denomination_unit')} "
                     f"{s.get('color')}  ->  {eq}")

    lines.append("\n# SUPPORTING PASSAGES (cite as [doc p.N]; use ONLY these for prose claims)")
    for p in ctx["neo4j_evidence"]:
        lines.append(f"[{p['doc_id']} p.{p.get('page')}] {p['snippet']}")
    for p in ctx["weaviate_evidence"]:
        lines.append(f"[{p['doc_id']} p.{p.get('page')}] {p['snippet']}")
    return "\n".join(lines)
```

### 4b. Call the LLM with a grounding system prompt (your app, your SDK)

```python
SYSTEM = (
    "You are a Costa Rica philately assistant. Answer ONLY from the CONTEXT. "
    "State catalog facts (denominations, colors, Scott numbers, values) from the "
    "DOMAIN FACTS. For any historical/narrative claim, cite the passage as "
    "[doc p.N]. If the context does not contain the answer, say so — do not guess."
)
context = build_context(answer(user_question, k=8))
# e.g. Anthropic SDK (downstream app code — NOT part of this prototype):
# msg = client.messages.create(model="claude-...", system=SYSTEM,
#         messages=[{"role":"user","content": f"CONTEXT:\n{context}\n\nQUESTION: {user_question}"}])
```

That contract — *facts from the domain card, prose cited to passages, refuse when
unknown* — is what makes the generated answer **trustworthy and checkable**: every
sentence is either a catalog fact or traceable to a `doc p.N` citation.

---

## 5. How much DEPTH does it return? (your core question)

Honest answer: **enough to ground a focused question, but the passages are
deliberately shallow by default.** Here is exactly what you get and how to deepen it.

### What the default (`k=6`) gives
- **1 domain card** — the full Mena↔Scott table (high value, complete) + a **600-char**
  excerpt of the issue's catalog note.
- **≤6 Neo4j passages**, each a **≤280-char snippet** (not the full chunk).
- **≤6 Weaviate passages**, each a **≤280-char snippet**.

So ≈ 12 short snippets + the fact table ≈ **3–4 KB of context**. That is good for
"what is the 2 reales worth?" but **thin** for "explain the plate varieties in
detail," because:
1. snippets are truncated to 280 chars (you lose the rest of the chunk),
2. the chunk graph still has **near-duplicate** chunks (same passage, different
   `chunk_id`) that can crowd the top-k,
3. it does **not** expand the graph (no surrounding `NEXT` chunks, no
   varieties/proofs/plates pulled into the evidence),
4. the issue note is capped at 600 chars.

### Levers to increase depth (in order of impact)

**(a) Raise `k`.** `answer(q, k=15)` — more passages per source.

**(b) Use full chunk text, not the 280-char snippet.** For the passages the LLM
will actually read, fetch the whole text by `chunk_id`:
```cypher
MATCH (c:Chunk) WHERE c.chunk_id IN $ids
RETURN c.chunk_id AS chunk_id, c.doc_id AS doc, c.page AS page, c.text AS full_text
```
(or raise the `_snippet(..., limit=280)` cap in `retrieve.py`).

**(c) Expand reading-order neighbours** so the LLM sees the passage *in context*
(the sentence before/after), which is where GraphRAG beats plain vector RAG:
```cypher
MATCH (c:Chunk {chunk_id:$id})
OPTIONAL MATCH (c)-[:NEXT*1..2]->(after:Chunk)
OPTIONAL MATCH (before:Chunk)-[:NEXT*1..2]->(c)
RETURN [x IN [before] WHERE x IS NOT NULL | x.text] + c.text +
       [y IN [after]  WHERE y IS NOT NULL | y.text] AS window
```

**(d) Pull the domain subgraph deeper.** The card stops at Stamp+Scott. For
"varieties / proofs / plates" questions, add a one-hop expansion to the context:
```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
OPTIONAL MATCH (i)-[:HAS_PROOF]->(pr:Proof)
OPTIONAL MATCH (i)-[:HAS_PLATE]->(pl:Plate)
RETURN s.catalog_no, collect(DISTINCT v.suffix) AS varieties,
       collect(DISTINCT pr.code) AS proofs, collect(DISTINCT pl.no) AS plates
```

**(e) De-duplicate near-identical passages** before sending to the LLM (hash the
normalized text; keep one). This frees top-k slots for *distinct* evidence.

**(f) Stamp-scoped retrieval.** For "tell me about the 1 peso," filter evidence to
chunks that `MENTIONS_STAMP` Mena 4 (see `cypher_queries.md` #7/#13) so every
passage is on-topic.

### A practical "deep context" profile
For a thorough, trustworthy answer: `k=12`, **full chunk text**, **±1 `NEXT`
neighbour**, **dedup by text**, and **append the domain variety/proof expansion**.
That typically yields ~15–25 distinct, full passages + the complete fact table —
a solid GraphRAG context an LLM can reason over and cite, while staying grounded.

---

## 6. Why this is "GraphRAG" and not just search

- The **domain card** is the *graph* contribution: structured, joined facts
  (Mena↔Scott↔Illustration) that a pure vector store can't give you cleanly — and
  they're authoritative, so the LLM doesn't have to infer values from prose.
- The **lexical graph** gives passages that were linked by **explainable signals**
  (`score`, `link_score`, the edge's `signals` like `YEAR_ANCHOR`/`DENOM`/`PRINTER`),
  and `NEXT`/`MENTIONS_STAMP` edges let you *walk* to related context.
- The **Weaviate baseline** is the safety net for recall.

Trust comes from the **combination**: exact facts (low hallucination risk) +
cited, signal-explained passages (auditable) + a corpus baseline (recall). The
generate step just has to obey the "facts-from-card, prose-cited, refuse-if-absent"
contract.

---

## 7. Tuning & current limitations

**Tunable now** (`.env`, read at runtime): `FIRST_ISSUE_MIN_LINK_SCORE`,
`FIRST_ISSUE_MIN_STRONG_CLASSES` (affect *what* is in the graph to retrieve);
`--k` (breadth). Snippet length and `NEXT`/full-text expansion are code-level (see §5).

**Known limitations (and the fix):**
- *Short snippets (280 chars).* → use full chunk text for the LLM (§5b).
- *Near-duplicate chunks in top-k.* → dedup by text (§5e); root cause is the
  oversized **combined chunks** described in `EVALUATION.md` (a chunking-layer fix).
- *No multi-hop expansion yet.* → add `NEXT`/variety/proof expansion (§5c/§5d).
- *Weaviate pass:* hybrid `alpha` is currently hardcoded (0.35) and BM25 matches
  all text fields incl. the contaminated `text`; for cleaner baseline recall,
  pin `query_properties=["text_original"]` and read `alpha`/`MIN_HYBRID_SCORE`
  from `.env` (deferred review nit — safe to apply when you productionize).
- *Retrieval-only by design.* The generate step is yours to add (§4); keep the
  grounding contract so answers stay verifiable.

---

## 8. Worked examples — real context bundles delivered to an LLM

These are **actual outputs** of the retriever (via `examples_runner.py --demo`,
which shows full passage text). Each shows the context an LLM would receive and a
**grounded answer** that uses *only* that context, cited `[doc p.N]`. They span the
full quality range — including the honest cases where the corpus does **not**
contain the answer (so a grounded LLM must decline rather than hallucinate).

> Run them yourself:
> `".venv-clean\Scripts\python.exe" first_issue_graphrag\examples_runner.py --demo`
> or one at a time: `... examples_runner.py --q "..." --stamp 4`

---

### Example A — "How many covers exist of the 1 peso?"  → coverage: **ABSENT**

**Context delivered:**
- *Domain facts:* Mena 4 / Scott 4 = **1 peso**, **printed quantity 35,000**,
  catalogue mint 35.0 / used 35.0, perf 12.
- *Stamp-scoped passages (MENTIONS_STAMP Mena 4):* `[OXCART72 p.11]` the Mechin &
  Cohen "basic study on the first issue" (meta/bibliographic); `[OXCART04 p.31]` a
  1961 "First Continental Lawyers Conference" decree — a **combined-chunk false
  positive, flagged `COMPETING`**.
- *Weaviate baseline:* `[Nordberg Collection Gold p.1]` (about the ½ real crack),
  census and exhibition pages — none give a 1-peso cover count.

**Grounded answer an LLM should produce (cited):**
> "The retrieved sources do **not** state how many covers of the 1 peso survive.
> What is recorded is that **35,000 of the 1 peso (Mena 4 / Scott 4) were printed**
> [Mena 2018 domain facts], at a catalogue value of mint 35.0 / used 35.0. A
> surviving-cover census is not present in the available passages — so I can't give
> a cover count from these sources."

**Why this example matters:** it demonstrates the **anti-hallucination** behavior
the grounding contract buys you — and that one stamp-scoped hit (`OXCART04`) is a
`COMPETING`-flagged combined-chunk artifact you'd filter out (see `EVALUATION.md`).

---

### Example B — "What are the main varieties of the first issue?"  → coverage: **PARTIAL**

**Context delivered:**
- *Domain facts:* the **1A light-blue second-plate** variety is in the graph —
  Scott 1a = **"½r light blue"** (Mena 1A, variety of Scott 1).
- *Neo4j fulltext:* general/meta pages (`OXCART191` deep-study intro, `OXCART199`
  surcharges) — the generic phrasing under-ranked the real variety articles.
- *Weaviate baseline:* `[CRF 88 p.23]` *"Errors and varieties of the classic
  issues"* — a dedicated varieties article.

**Grounded answer an LLM could produce (cited):**
> "From these sources: the first issue includes the **½ real light-blue second-plate
> variety** (Mena 1A / Scott 1a) [domain], and a dedicated treatment exists in
> *'Errors and varieties of the classic issues'* [CRF 88 p.23]. The retrieved
> context here is not exhaustive — a complete variety list isn't in this top-k."

**Why this example matters:** the comprehensive variety content **exists in the
graph** (see Examples C and D) but the *generic* question under-retrieves it. This
is the ranking limitation from §5 — for thematic questions, raise `k`, weight the
`MENTIONS`/`link_score` path, or ask stamp-specific questions.

---

### Example C — "What is the crack plate of the first issue?"  → coverage: **STRONG**

**Context delivered (verbatim passages):**
- `[OXCART19-20 p.5]` *"MEDIO REAL (PLATE 1) VARIETIES — The most prominent variety
  of the first issue is the 'cracked plate' on this value … the crack extended
  completely through No. 11 and halfway through No. 21, each position being
  identifiable."*
- `[OXCART119 p.26]` *"Sc 1, complete sheet Medio Real, with plate crack into 'E'
  of 'Real'."*
- `[Nordberg Collection Gold p.1]` *"The ½ real plate I stamps … Probably the plate
  cracked during printing for the 1873 delivery."*

**Grounded answer an LLM could produce (cited):**
> "The crack plate is on the **½ real (medio real), Plate I**. It is the most
> prominent variety of the first issue: the crack runs through sheet **positions 1,
> 11 (completely) and 21 (halfway)**, passing into the **'E' of 'REAL'**
> [OXCART19-20 p.5; OXCART119 p.26]. The plate is believed to have cracked during
> printing for the **1873 delivery** [Nordberg Collection Gold p.1]."

**Why this example matters:** a specific, well-phrased question yields
authoritative, fully-cited grounding — GraphRAG working as intended.

---

### Example D — "What is the 4 reales double transfer at pos 8?"  → coverage: **STRONG**

**Context delivered (verbatim passages):**
- `[OXCART75 p.16]` *"PLATE VARIETIES … In the four reales stamp … there are
  several more 'double transfers' because of the repairs that were made in the
  plate. **POSITION 8: This is the classic and well-known 'double transfer'. The
  double drawings are quite visible in 'CORREOS DE COSTA RICA' and in 'CUATRO
  REALES'. In some specimens, even the stars are double.**"*
- `[CRF 87 p.23]` *"FOUR REALE … Plate Varieties: … as for the stamps of half and
  two reales …"*

**Grounded answer an LLM could produce (cited):**
> "On the **4 reales (Scott 3 / Mena 3)**, plate **position 8** is the **classic,
> well-known double transfer**: the doubling is clearly visible in the inscriptions
> **'CORREOS DE COSTA RICA'** and **'CUATRO REALES'**, and in some specimens even
> the stars are doubled [OXCART75 p.16]. The 4 reales shows several double transfers
> due to repairs made to the plate [OXCART75 p.16]."

**Why this example matters:** a precise philatelic query is answered exactly, with a
single high-`link_score` passage carrying the whole answer — and the same passage
tops both the Neo4j and Weaviate retrievers (strong agreement = high confidence).

---

### What the four examples tell you about depth & trust

| Question | Coverage | What it teaches |
|----------|----------|-----------------|
| 1 peso covers | **Absent** | The retriever supplies context but no answer → a grounded LLM declines (no hallucination). Printed quantity ≠ surviving covers. |
| Main varieties | **Partial** | Content exists but generic phrasing under-ranks it → raise `k` / weight `link_score` / ask specifically. |
| Crack plate | **Strong** | Specific question → authoritative, fully-cited answer. |
| 4 reales pos 8 | **Strong** | Precise question → exact answer from one high-signal passage, corroborated across both retrievers. |

**Bottom line:** the retriever gives an LLM trustworthy grounding **when the
question is specific and the answer is in the corpus**, correctly **declines when
it isn't**, and is **only limited on broad thematic questions by retrieval ranking**
(fixable with the depth levers in §5) and by the combined-chunk artifacts in
`EVALUATION.md`.

---

## 9. Graph-first context bundle (the RECOMMENDED retrieval mode)

`context_bundle()` — and its CLI, **`examples_runner.py`** — is the preferred way
to assemble LLM context. It treats the **graph as the knowledge base** (cheap
Cypher, predominant) and keeps **Weaviate as a thin, capped backup** (slow/heavy).

**Precedence — what the bundle returns, in order:**
1. **`domain`** — authoritative structured facts (Issue + Mena↔Scott + illustration).
2. **`related`** — cheap one-hop graph expansion: variety suffixes per stamp, proof codes, plate numbers.
3. **`sources`** — ranked list of the documents that reference the query (the
   high-quality "where to read more" panel; free — aggregated from the lexical hits).
4. **`lexical`** — the predominant evidence: ALL **good** first-issue chunks
   (quality-gated), deduped, full text, ranked by query relevance then link strength.
5. **`weaviate`** — least important: a small backup tail (≤25), only passages the
   graph did not already cover.

**Quality gate (no garbage):** lexical includes only chunks whose `MENTIONS` edge
has `score ≥ min_link` (default **6** — the clean tier from `EVALUATION.md`) and is
**not** `COMPETING`-flagged. Near-duplicate combined-chunks are collapsed by a
300-character text prefix, so there are no repeats.

**Knobs (CLI flag / function arg):**

| flag | arg | default | effect |
|------|-----|---------|--------|
| `--max-lexical` | `max_lexical` | `0` (= ALL good) | cap on graph passages |
| `--min-link` | `min_link_score` | `6.0` | quality gate; lower = more recall + more noise |
| `--include-competing` | `exclude_competing=False` | off | keep COMPETING-flagged chunks |
| `--k-weaviate` | `k_weaviate` | `5` (hard cap 25) | backup breadth; `0` = pure graph |
| `--stamp` | `stamp` | none | scope to a Mena stamp (1=½r, 2=2r, 3=4r, 4=1p) |
| `--width` | — | `900` | characters of each passage shown |

**Auto-save:** every `examples_runner.py` run writes a timestamped transcript to
`first_issue_graphrag/results/<slug>_<timestamp>.txt` (gitignored) — open it and
paste into your LLM.

**Recommended usage:**
- Tight, on-topic context for a specific question → `--max-lexical 15`.
- Maximum breadth (everything good in the graph) → default `--max-lexical 0`.
- Pure graph, skip Weaviate entirely → `--k-weaviate 0`.

```powershell
.\.venv-clean\Scripts\python.exe first_issue_graphrag\examples_runner.py --q "the first issue plate crack and its positions" --stamp 1 --max-lexical 15 --width 1500
```

Programmatic:
```python
from retrieve import context_bundle
b = context_bundle("the first issue plate crack and its positions",
                   stamp="1", max_lexical=15, k_weaviate=5)
# keys: b["domain"], b["related"], b["sources"], b["lexical"], b["weaviate"], b["counts"]
```

> The older `answer(question, k)` (§2) still exists (compact, single shared `k`,
> 280-char snippets). `context_bundle` supersedes it for graph-first retrieval
> with per-source budgets and quality gating — use it for LLM hand-off.

---

See also: `README.md` (architecture/run), `EVALUATION.md` (coverage + precision +
the chunking root cause), `cypher_queries.md` (graph inspection & stamp-scoped queries).
```
