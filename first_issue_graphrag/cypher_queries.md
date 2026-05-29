# First Issue GraphRAG — Neo4j Cypher Cookbook

Copy-paste queries for **Neo4j Browser** (`http://localhost:7474`, db `neo4j`) to
inspect the prototype graph and judge ground truth yourself.

All prototype nodes/edges carry `prototype = "first_issue_graphrag"`.
Issue id is `CR-1863-FIRST-ISSUE`. Run `coverage_scan.py --all` first to populate.

> **Corpus scope (current build):** `--all` now scans the **whole corpus — 894
> docs** — i.e. every `results/final_jsons/*_final.json` **except** the 526
> Boletín Correos bulletins and the Mena/Scott catalogs (those already live in
> the domain graph, so re-ingesting them as lexical chunks would be redundant).
> Result: **296 documents / 653 distinct first-issue chunks** (170 docs / 431
> chunks of which are newly-added non-OXCART sources). See §14–§17 for the
> multi-corpus expansion.

---

## 0. Sanity — confirm the Mena domain graph is INTACT (we never touched it)

```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})-[:HAS_STAMP]->(s:Stamp)
RETURN i.issue_id AS issue, collect(s.catalog_no) AS mena_stamps;
// expect the original ['1','1A','2','3','4'] — untouched by the prototype
```

## 1. Domain layer — the Scott facts we ADDED (Mena ↔ Scott)

```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})-[:HAS_SCOTT_STAMP]->(ss:ScottStamp)
OPTIONAL MATCH (st:Stamp {issue_id:i.issue_id})-[eq:EQUIVALENT_TO]->(ss)
OPTIONAL MATCH (ss)-[:DEPICTS]->(ill:Illustration)
OPTIONAL MATCH (ss)-[:VARIETY_OF]->(parent:ScottStamp)
RETURN st.catalog_no AS mena, ss.scott_number AS scott, ss.denomination AS denom,
       ss.color AS color, ss.mint_value AS mint, ss.used_value AS used,
       eq.confidence AS conf, parent.scott_number AS variety_of, ill.design_name AS design
ORDER BY scott;
```

## 2. Lexical layer — HIGH-CONFIDENCE chunks about the First Issue (the clean view)

`score >= 6` and not flagged as competing/commemorative context → the trustworthy
evidence set. This is what you should read to judge ground truth.

```cypher
MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WHERE m.score >= 6 AND NOT 'COMPETING' IN m.signals
RETURN c.doc_id AS doc, c.page AS page, m.score AS score,
       m.signals AS signals, left(c.text, 240) AS snippet
ORDER BY m.score DESC, doc
LIMIT 50;
```

## 3. Ground-truth read — strongest evidence with full text + which stamps

```cypher
MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
OPTIONAL MATCH (c)-[:MENTIONS_STAMP]->(s:Stamp)
WITH c, m, collect(DISTINCT s.catalog_no) AS mena_stamps
RETURN c.doc_id AS doc, c.page AS page, m.score AS score, mena_stamps,
       m.signals AS signals, c.text AS full_text
ORDER BY m.score DESC
LIMIT 25;
```

## 4. Inspect the noisy boundary tier (score = 4) — combined-chunk artifacts live here

```cypher
MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WHERE m.score = 4
RETURN c.doc_id AS doc, c.page AS page, m.signals AS signals, left(c.text,200) AS snippet
ORDER BY doc, page
LIMIT 40;
```

## 5. Flagged competing/commemorative chunks (e.g. the 1961 Lawyers Conference)

```cypher
MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WHERE 'COMPETING' IN m.signals
RETURN c.doc_id AS doc, c.page AS page, m.score AS score, left(c.text,200) AS snippet;
```

## 6. Combined domain + lexical — evidence per Scott/Mena stamp

```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})-[:HAS_SCOTT_STAMP]->(ss:ScottStamp)
OPTIONAL MATCH (st:Stamp {issue_id:i.issue_id})-[:EQUIVALENT_TO]->(ss)
OPTIONAL MATCH (c:Chunk)-[:MENTIONS_STAMP]->(st)
RETURN ss.scott_number AS scott, st.catalog_no AS mena, ss.denomination AS denom,
       ss.color AS color, count(DISTINCT c) AS evidence_chunks
ORDER BY scott;
```

## 7. Evidence for one specific stamp — e.g. Mena 1 / Scott 1 (½ real blue)

```cypher
MATCH (c:Chunk)-[ms:MENTIONS_STAMP]->(s:Stamp {issue_id:'CR-1863-FIRST-ISSUE', catalog_no:'1'})
RETURN c.doc_id AS doc, c.page AS page, ms.confidence AS conf,
       ms.signals AS signals, left(c.text,240) AS snippet
ORDER BY ms.confidence DESC
LIMIT 25;
```

## 8. Coverage — how many first-issue chunks per document

```cypher
MATCH (d:Document {prototype:'first_issue_graphrag'})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
RETURN d.doc_id AS doc, count(c) AS linked_chunks
ORDER BY linked_chunks DESC;
```

## 9. Score distribution (how strong are the links)

```cypher
MATCH (:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
RETURN CASE WHEN m.score >= 12 THEN '12+  very strong'
            WHEN m.score >= 8  THEN '8-11 strong'
            WHEN m.score >= 6  THEN '6-7  solid'
            ELSE '4-5  threshold' END AS band,
       count(*) AS chunks
ORDER BY band DESC;
```

## 10. VISUALIZE the first-issue subgraph (use Neo4j Browser graph view)

```cypher
// Issue + Mena stamps + Scott equivalents + the strongest 30 evidence chunks
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
OPTIONAL MATCH (i)-[hs:HAS_SCOTT_STAMP]->(ss:ScottStamp)
OPTIONAL MATCH (st:Stamp {issue_id:i.issue_id})-[eq:EQUIVALENT_TO]->(ss)
OPTIONAL MATCH (ss)-[dp:DEPICTS]->(ill:Illustration)
WITH i, collect(DISTINCT ss)+collect(DISTINCT st)+collect(DISTINCT ill) AS domain
CALL {
  MATCH (c:Chunk)-[m:MENTIONS]->(i2:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
  WHERE m.score >= 8 AND NOT 'COMPETING' IN m.signals
  RETURN c ORDER BY m.score DESC LIMIT 30
}
OPTIONAL MATCH (c)-[ms:MENTIONS_STAMP]->(:Stamp)
OPTIONAL MATCH (c)-[mi:MENTIONS]->(i)
RETURN *;
```

## 11. Walk a chunk's neighbours in reading order (NEXT chain)

```cypher
MATCH (c:Chunk {doc_id:'OXCART75'})-[:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
OPTIONAL MATCH (c)-[:NEXT]->(nxt:Chunk)
RETURN c.page AS page, c.link_score AS score, left(c.text,120) AS this_chunk,
       left(nxt.text,80) AS next_chunk
ORDER BY c.link_score DESC LIMIT 15;
```

## 12. GRAPH VIEW — complete domain + 10 docs × ≤5 chunks each

Best run in **Neo4j Desktop / Browser** (returns paths → renders as a graph).
Shows the **full first-issue domain** (Issue, Mena Stamps + Varieties, Scott
stamps + Illustration, *and* the rest of the Mena context: Printer, LegalActs,
Plates, Proofs, Specimens, Production Orders) plus the **10 documents with the
most clean first-issue chunks**, capped at **5 chunks per doc** (clean tier:
`score ≥ 6`, not `COMPETING`). ~140 nodes.

```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})

// ---- COMPLETE DOMAIN (Mena + Scott; p7/p8 pull the rest of the Mena context) ----
OPTIONAL MATCH p1 = (i)-[:HAS_STAMP]->(st:Stamp)
OPTIONAL MATCH p2 = (st)-[:HAS_VARIETY]->(:Variety)
OPTIONAL MATCH p3 = (i)-[:HAS_SCOTT_STAMP]->(ss:ScottStamp)
OPTIONAL MATCH p4 = (st)-[:EQUIVALENT_TO]->(ss)
OPTIONAL MATCH p5 = (ss)-[:DEPICTS]->(:Illustration)
OPTIONAL MATCH p6 = (ss)-[:VARIETY_OF]->(:ScottStamp)
OPTIONAL MATCH p7 = (i)-[]->(o)  WHERE NOT o:Chunk  AND NOT o:Stamp   AND NOT o:ScottStamp
OPTIONAL MATCH p8 = (st)-[]->(o2) WHERE NOT o2:Chunk AND NOT o2:Variety AND NOT o2:ScottStamp
WITH i, collect(p1)+collect(p2)+collect(p3)+collect(p4)+collect(p5)+collect(p6)
        +collect(p7)+collect(p8) AS domainPaths

// ---- 10 docs with the most CLEAN first-issue chunks ----
CALL (i) {
  MATCH (d:Document {prototype:'first_issue_graphrag'})-[:HAS_CHUNK]->(:Chunk)-[mm:MENTIONS]->(i)
  WHERE mm.score >= 6 AND NOT 'COMPETING' IN mm.signals
  WITH d, count(*) AS linked ORDER BY linked DESC LIMIT 10
  RETURN collect(d) AS topDocs
}
UNWIND topDocs AS d

// ---- up to 5 chunks per doc (best first) + their stamp links ----
CALL (d, i) {
  MATCH cp = (d)-[:HAS_CHUNK]->(c:Chunk)-[m:MENTIONS]->(i)
  WHERE m.score >= 6 AND NOT 'COMPETING' IN m.signals
  WITH cp, c, m ORDER BY m.score DESC LIMIT 5
  OPTIONAL MATCH sp = (c)-[:MENTIONS_STAMP]->(:Stamp)
  RETURN collect(cp) + collect(sp) AS docPaths
}
WITH domainPaths, collect(docPaths) AS perDoc
WITH domainPaths + reduce(acc=[], x IN perDoc | acc + x) AS allPaths
UNWIND allPaths AS p
WITH DISTINCT p
RETURN p;
```

> **Cleaner view:** if the Proof/Specimen cluster is too dense, delete the `p7`
> and `p8` lines (and drop them from the `collect(...)`). You then keep only the
> core domain: Issue, Stamp, Variety, ScottStamp, Illustration.
> **Browser tip:** click a node → set its caption (e.g. `Chunk.doc_id`,
> `Stamp.catalog_no`, `Document.doc_id`) for readable labels.

## 13. GRAPH VIEW — only the docs that reference the **1 peso** stamp (≤5 chunks/doc)

The 1 peso is **Mena `catalog_no = '4'` / Scott 4**. This shows the 1-peso domain
node + **every document that has at least one chunk mentioning it**, capped at 5
chunks per doc (best confidence first). (~60 docs reference it in the full scan.)

```cypher
// 1 PESO = Mena catalog_no '4' (Scott 4).  Swap '4' for '1' (½r), '2' (2r), '3' (4r).
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})-[:HAS_STAMP]->(peso:Stamp {catalog_no:'4'})

// domain context for the 1 peso
OPTIONAL MATCH d1 = (i)-[:HAS_STAMP]->(peso)
OPTIONAL MATCH d2 = (peso)-[:EQUIVALENT_TO]->(ss:ScottStamp)
OPTIONAL MATCH d3 = (ss)-[:DEPICTS]->(:Illustration)
OPTIONAL MATCH d4 = (peso)-[:HAS_VARIETY]->(:Variety)
WITH i, peso, collect(d1)+collect(d2)+collect(d3)+collect(d4) AS domainPaths

// docs that reference the 1 peso (only those with >=1 such chunk)
CALL (peso) {
  MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS_STAMP]->(peso)
  WITH DISTINCT d
  // OPTIONAL: cap the number of docs for a readable view -> add:  LIMIT 10
  RETURN collect(d) AS docs
}
UNWIND docs AS d

// up to 5 chunks per doc that mention the 1 peso (best confidence first)
CALL (d, peso, i) {
  MATCH cp = (d)-[:HAS_CHUNK]->(c:Chunk)-[ms:MENTIONS_STAMP]->(peso)
  WITH cp, c, ms ORDER BY ms.confidence DESC, c.link_score DESC LIMIT 5
  OPTIONAL MATCH mi = (c)-[:MENTIONS]->(i)
  RETURN collect(cp) + collect(mi) AS docPaths
}
WITH domainPaths, collect(docPaths) AS perDoc
WITH domainPaths + reduce(acc=[], x IN perDoc | acc + x) AS allPaths
UNWIND allPaths AS p
WITH DISTINCT p
RETURN p;
```

> **Too many docs?** ~60 docs reference the 1 peso, so the full graph is ~280
> nodes. For a readable view, uncomment the `LIMIT 10` inside the first `CALL`
> (docs are then arbitrary 10; to get the *top* 10 by 1-peso mentions, replace
> that subquery body with:
> `MATCH (d:Document)-[:HAS_CHUNK]->(:Chunk)-[:MENTIONS_STAMP]->(peso) WITH d, count(*) AS n ORDER BY n DESC LIMIT 10 RETURN collect(d) AS docs`).
> To inspect the text instead of the graph, use query #7 with `catalog_no:'4'`.

---

## 14. Multi-corpus expansion — first-issue evidence by SOURCE SERIES

After the full **894-doc** scan, **296 documents / 653 distinct chunks** carry
first-issue evidence — up from 155 docs in the OXCART-only graph, and now
**majority non-OXCART** (170 docs / 431 chunks newly added). This groups that
evidence by source series.

```cypher
MATCH (d:Document {prototype:'first_issue_graphrag'})-[:HAS_CHUNK]->(c:Chunk)-[:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WITH d, c, CASE
    WHEN d.doc_id STARTS WITH 'OXCART' THEN 'OXCART studies'
    WHEN d.doc_id STARTS WITH 'CRF' THEN 'CRF (Costa Rica Filatelica)'
    WHEN d.doc_id STARTS WITH 'Filatelia Costarricense' THEN 'Filatelia Costarricense'
    WHEN d.doc_id STARTS WITH 'AFCR' THEN 'AFCR Boletin'
    WHEN d.doc_id STARTS WITH 'Repertorio' THEN 'Repertorio Filatelico'
    WHEN d.doc_id STARTS WITH 'Timbre' THEN 'Timbre'
    WHEN d.doc_id STARTS WITH 'Juventud' THEN 'Juventud Filatelica'
    WHEN d.doc_id CONTAINS 'Philatelist' THEN 'The Costa Rica Philatelist'
    ELSE 'Other monographs' END AS series
RETURN series, count(DISTINCT d) AS docs, count(DISTINCT c) AS chunks
ORDER BY chunks DESC;
// Typical: OXCART 126/222 · Other monographs 31/144 · CRF 49/124 · Repertorio 53/109 · ...
```

## 15. The newly-added references — top NON-OXCART documents

The high-value first-issue sources the OXCART-only graph was missing: Frajola/Mayer
postal history, Nordberg collections, Alvaro Castro postal history, forgery
studies, and the CRF / Repertorio / Filatelia runs.

```cypher
MATCH (d:Document {prototype:'first_issue_graphrag'})-[:HAS_CHUNK]->(c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WHERE NOT d.doc_id STARTS WITH 'OXCART'
RETURN d.doc_id AS doc,
       sum(CASE WHEN m.score >= 6 AND NOT 'COMPETING' IN m.signals THEN 1 ELSE 0 END) AS clean_chunks,
       count(c) AS chunks, max(m.score) AS best_score
ORDER BY clean_chunks DESC, chunks DESC
LIMIT 30;
```

## 16. Spanish-language recall — first-issue evidence in Spanish

The corpus is ~70% Spanish; these chunks linked via the Spanish vocabulary the
lexicon now understands (`primera emisión`, `primera serie`, `medio real`,
`dos/cuatro reales`, `un peso`, `Decreto N° …`). ~298 chunks across 126 non-OXCART docs.

```cypher
MATCH (c:Chunk)-[m:MENTIONS]->(:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
WHERE c.text =~ '(?is).*(primera emisi[oó]n|primera serie|medio real|dos reales|cuatro reales|un peso|decreto n).*'
  AND NOT c.doc_id STARTS WITH 'OXCART'
RETURN c.doc_id AS doc, m.score AS score, m.signals AS signals, left(c.text, 220) AS snippet
ORDER BY m.score DESC
LIMIT 40;
```

## 17. GRAPH VIEW — the Issue + its top NEW (non-OXCART) source documents

Renders the first issue plus the 12 strongest newly-added documents (≤3 clean
chunks each) — a quick visual of what the corpus expansion contributed.

```cypher
MATCH (i:Issue {issue_id:'CR-1863-FIRST-ISSUE'})
CALL (i) {
  MATCH (d:Document {prototype:'first_issue_graphrag'})-[:HAS_CHUNK]->(:Chunk)-[mm:MENTIONS]->(i)
  WHERE NOT d.doc_id STARTS WITH 'OXCART' AND mm.score >= 6 AND NOT 'COMPETING' IN mm.signals
  WITH d, count(*) AS n ORDER BY n DESC LIMIT 12
  RETURN collect(d) AS topDocs
}
UNWIND topDocs AS d
CALL (d, i) {
  MATCH p = (d)-[:HAS_CHUNK]->(c:Chunk)-[m:MENTIONS]->(i)
  WHERE m.score >= 6 AND NOT 'COMPETING' IN m.signals
  WITH p, m ORDER BY m.score DESC LIMIT 3
  RETURN collect(p) AS paths
}
WITH reduce(acc=[], x IN collect(paths) | acc + x) AS allPaths
UNWIND allPaths AS p
RETURN p;
```

---

### Notes for interpreting results

- **Trust `score >= 6` and `NOT 'COMPETING'`** (queries #2/#10) as the clean evidence set.
- The **`score = 4` tier** (query #4) is the precision boundary: it mixes genuine
  first-issue catalogue/auction listings with **oversized combined-chunk artifacts**
  (a single merged chunk spanning unrelated sections where `1863` + a denomination
  co-occur by accident). Fixing those fully requires splitting the merged chunks at
  the parsing layer — it is not a lexicon problem.
- **De-duplication:** each distinct passage is materialized **once**. The parse
  layer emits the same passage at several growing lengths (nested chunks); the
  scanner collapses those by normalized text prefix and keeps the most complete
  one. (This is why the deduped graph has ~653 chunks, not the ~thousands of raw
  nested copies.)
- `signals` on each `MENTIONS` edge tells you *why* it linked
  (`YEAR_ANCHOR`=1863, `DENOM`, `PRINTER`=ABNCo/Banco Americano, `ISSUE_PHRASE`
  incl. Spanish `primera emisión`/`primera serie`, `PLATE`, `ENTITY` incl.
  `Decreto N° 2`, `DESIGN`). Suppression flags: **`COMPETING`** (commemorative /
  1881-83 surcharge / Guanacaste / later issue), **`FOREIGN`** (another country's
  classic issue — suppressed unless Costa Rica is also named), and **`FISCAL`**
  (revenue-stamp context — suppressed unless the 1863 anchor is present).
```
