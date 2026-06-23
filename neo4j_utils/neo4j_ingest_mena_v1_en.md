# Costa Rica “Mena” Catalog → Neo4j (V1)

**Schema README and Philatelic/Neo4j Rationale — Updated**

> This README documents the **current V1 graph model** with the latest adjustments: `:Document` → `:LegalAct`, `HAS_DOCUMENT` → `AUTHORIZED_BY`, storing `legal_basis.ids` in `LegalAct.ids`, and safer handling of officials/provenance so non‑people like “session #229” no longer become `:Person` nodes.

---

## Goals

1. Represent **Issues** and their technical/administrative context.
2. Describe **Stamps** (catalog base numbers) and their **Varieties** (suffixes: plate flaws, perforation anomalies, etc.).
3. Preserve **Proofs** (Die/Plate/Color) and link them to their issues.
4. Record **Production Orders** (by date) and **Remainders** (including buyer).
5. Keep **Plates** and (when given) **Plate Positions** to anchor repeatable plate flaws.
6. Make ingestion **idempotent** using unique constraints and `MERGE`.

> **Why V1?** It matches your JSON and lets you explore the data right now. Later, if you need to treat each *suffixed variety as a full collectible unit*, you can upgrade to V2 with minimal churn.

---

## Design Decisions (Philatelic & Neo4j Justification)

* **`LegalAct` replaces `Document`**

  * Nodes representing decrees, resolutions, letters, etc., are now labeled **`:LegalAct`**.
  * The Issue→Act relation is **`(:Issue)-[:AUTHORIZED_BY]->(:LegalAct)`**.
  * Each `LegalAct` is keyed by `(type, id, date)` and stores **`ids`** (e.g., Council/Session references) from `issue_data.legal_basis[].ids`.

* **Officials recorded only when they look like real people**

  * We add `(:LegalAct)-[:SIGNED_BY]->(:Person)` **only** if the string looks like a personal name (2–4 capitalized words, no digits; rejects tokens like “session #229”).
  * If an “official” token is not a person, it’s appended to `LegalAct.ids` instead of creating a person.

* **Essays provenance is typed**

  * Values under `essays[].provenance[]` are classified as `:Person`, `:Organization`, or `:BiblioRef`.
  * Prefix **“ex‑”** (e.g., `ex‑Mayer`) becomes an **`EX_PROVENANCE`** relation; otherwise **`PROVENANCE`**.
  * Bibliographic strings (e.g., `Ref CRFil 47, 1962`) become **`:BiblioRef`** nodes linked via `CITED_IN`.

* **Varieties under `:Stamp` (V1)**
  Mirrors your JSON (base + suffixes). Good for “show me all suffixes of #1” and for tying constant plate flaws to plate positions.

* **`issue_dates` stored as JSON string**
  Preserves the nested map while keeping Neo4j primitives friendly.

* **Conditional `:PlatePosition`**
  Created only when both `position` and `plate` are present to avoid graph bloat while preserving plate‑position logic.

* **Idempotency via keys + `MERGE`**
  Constraints ensure you can re‑run ingestion safely.

* **`OVERPRINTED_ON` with properties**
  Lean way to express derivations and nominal changes (room to add an `:OverprintEvent` layer later if needed).

---

## Entity Keys (Constraints)

* `(:Issue)           ON issue_id`
* `(:Stamp)           ON (issue_id, catalog_no)`
* `(:Variety)         ON (issue_id, base_catalog_no, suffix)`
* `(:Proof)           ON code` (applies to Die/Plate/Color proof sublabels)
* `(:Plate)           ON (issue_id, denomination, no)`
* `(:ProductionOrder) ON (issue_id, date)`
* `(:Quantity)        ON po_key`
* `(:LegalAct)        ON (type, id, date)`
* `(:Person)          ON name`
* `(:Printer)         ON name`
* `(:Organization)    ON name`
* `(:BiblioRef)       ON key`

---

## Classic Cypher Queries (Ready for Neo4j Browser)

> **Tip:** Queries that `RETURN` **paths** (`p`, `p2`, …) render in the **Graph** view. After execution, switch to the *Graph* tab and tune the visualization limits if needed.

### 1) Global view of an **Issue** (all related elements)

**Self‑contained** (replace `issue_id`):

```cypher
WITH 'CR-1863-FIRST-ISSUE' AS issue_id

MATCH p = (iss:Issue {issue_id: issue_id})
          -[:PRINTED_BY|AUTHORIZED_BY|HAS_PLATE|HAS_STAMP|HAS_PROOF
            |HAS_PRODUCTION_ORDER|HAS_REMAINDERS|HAS_SPECIMEN|HAS_ESSAY*1..2]-(n)
WITH collect(p) AS paths1, collect(DISTINCT n) AS lvl1

UNWIND lvl1 AS x
OPTIONAL MATCH p2 = (x)-[:SIGNED_BY|INCLUDES|SOLD_TO|USES_PLATE|HAS_VARIETY|AT_POSITION]->(y)
WITH [p IN paths1 WHERE p IS NOT NULL] + [p IN collect(p2) WHERE p IS NOT NULL] AS allPaths
UNWIND allPaths AS p
RETURN p
LIMIT 2000;
```

### 2) Global view of a **Stamp** (its full neighborhood)

**Self‑contained** (replace `issue_id` and `catalog_no`):

```cypher
WITH 'CR-1863-FIRST-ISSUE' AS issue_id, '1' AS catalog_no

MATCH p1 = (st:Stamp {issue_id: issue_id, catalog_no: catalog_no})
           -[:USES_PLATE|HAS_VARIETY|OVERPRINTED_ON]-(x)
OPTIONAL MATCH p2 = (x)-[:AT_POSITION]->(:PlatePosition)
OPTIONAL MATCH p3 = (st)<-[:HAS_STAMP]-(iss:Issue)
OPTIONAL MATCH p4 = (iss)-[:PRINTED_BY|AUTHORIZED_BY|HAS_PROOF
                          |HAS_PRODUCTION_ORDER|HAS_REMAINDERS
                          |HAS_SPECIMEN|HAS_ESSAY]->(z)
OPTIONAL MATCH p5 = (z)-[:SIGNED_BY|INCLUDES|SOLD_TO]->(w)
RETURN p1, p2, p3, p4, p5
LIMIT 2000;
```

### 3) Find an **Issue** by text (title or id)

```cypher
WITH 'first issue' AS q
MATCH (iss:Issue)
WHERE toLower(iss.title) CONTAINS toLower(q)
   OR toLower(iss.issue_id) CONTAINS toLower(q)
RETURN iss
ORDER BY iss.issue_id;
```

### 4) List all **Stamps** of an Issue with their **Varieties**

```cypher
WITH 'CR-1863-FIRST-ISSUE' AS issue_id
MATCH (iss:Issue {issue_id: issue_id})-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
RETURN s.catalog_no AS no, s.color AS color, s.perforation AS perf,
       collect(v.suffix) AS varieties
ORDER BY no;
```

### 5) Varieties anchored to **Plate Positions**

```cypher
MATCH (s:Stamp)-[:HAS_VARIETY]->(v:Variety)-[:AT_POSITION]->(pp:PlatePosition)
RETURN s.issue_id, s.catalog_no, v.suffix, v.description, v.plate AS plate_no, pp.pos
ORDER BY s.issue_id, s.catalog_no, pp.pos;
```

### 6) Overprint/Surcharge **Derivations** (`OVERPRINTED_ON`)

```cypher
MATCH (d:Stamp)-[r:OVERPRINTED_ON]->(b:Stamp)
RETURN d.issue_id AS derived_issue, d.catalog_no AS derived_no,
       r.type AS op_type, r.surcharged_value AS sc_val, r.surcharged_unit AS sc_unit,
       r.on_value AS on_val, r.on_unit AS on_unit,
       b.issue_id AS base_issue, b.catalog_no AS base_no
ORDER BY derived_issue, derived_no;
```

### 7) **Production Orders** and quantities

```cypher
MATCH (iss:Issue)-[:HAS_PRODUCTION_ORDER]->(po:ProductionOrder)-[:INCLUDES]->(q:Quantity)
RETURN iss.issue_id, po.date, q.plate_desc, q.quantity
ORDER BY iss.issue_id, po.date, q.plate_desc;
```

### 8) **Remainders** and buyer (when present)

```cypher
MATCH (iss:Issue)-[:HAS_REMAINDERS]->(ev:RemaindersEvent)-[:INCLUDES]->(q:Quantity)
OPTIONAL MATCH (ev)-[:SOLD_TO]->(p:Person)
RETURN iss.issue_id, ev.date, q.plate_desc, q.quantity, p.name AS buyer
ORDER BY iss.issue_id, ev.date, q.plate_desc;
```

### 9) “Tech sheet” for a **Stamp**

```cypher
WITH 'CR-1863-FIRST-ISSUE' AS issue_id, '1' AS catalog_no
MATCH (s:Stamp {issue_id: issue_id, catalog_no: catalog_no})
OPTIONAL MATCH (s)-[:USES_PLATE]->(pl:Plate)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
RETURN s.catalog_no AS no, s.denomination_value AS val, s.denomination_unit AS unit,
       s.color AS color, s.perforation AS perf, s.quantity_reported AS qty_reported,
       collect(DISTINCT pl.no) AS plates, collect(DISTINCT v.suffix) AS variety_suffixes;
```

### 10) Quick **sanity counts**

```cypher
MATCH (n)
RETURN
  count(n) AS total,
  sum(CASE WHEN n:Issue THEN 1 ELSE 0 END) AS issues,
  sum(CASE WHEN n:Stamp THEN 1 ELSE 0 END) AS stamps,
  sum(CASE WHEN n:Variety THEN 1 ELSE 0 END) AS varieties,
  sum(CASE WHEN n:Proof THEN 1 ELSE 0 END) AS proofs,
  sum(CASE WHEN n:Plate THEN 1 ELSE 0 END) AS plates,
  sum(CASE WHEN n:PlatePosition THEN 1 ELSE 0 END) AS plate_positions,
  sum(CASE WHEN n:ProductionOrder THEN 1 ELSE 0 END) AS prod_orders,
  sum(CASE WHEN n:Quantity THEN 1 ELSE 0 END) AS quantities,
  sum(CASE WHEN n:LegalAct THEN 1 ELSE 0 END) AS legal_acts,
  sum(CASE WHEN n:Essay THEN 1 ELSE 0 END) AS essays,
  sum(CASE WHEN n:Specimen THEN 1 ELSE 0 END) AS specimens,
  sum(CASE WHEN n:Person THEN 1 ELSE 0 END) AS persons,
  sum(CASE WHEN n:Printer THEN 1 ELSE 0 END) AS printers,
  sum(CASE WHEN n:Organization THEN 1 ELSE 0 END) AS organizations,
  sum(CASE WHEN n:BiblioRef THEN 1 ELSE 0 END) AS biblio_refs;
```

---

## One‑time cleanup (only if you imported old data)

If previous runs created `:Person` nodes that are actually sessions (e.g., “session #229”), normalize them into `LegalAct.ids` and remove the wrong edges:

```cypher
MATCH (d:LegalAct)-[r:SIGNED_BY]->(p:Person)
WHERE toLower(p.name) STARTS WITH 'session'
   OR toLower(p.name) STARTS WITH 'sesion'
   OR toLower(p.name) STARTS WITH 'sesión'
WITH d, p, r
SET d.ids = CASE WHEN d.ids IS NULL THEN [p.name] ELSE d.ids + [p.name] END
DELETE r
DETACH DELETE p;
```

---

## Final Notes

* **V1 already answers** high‑value philatelic questions: which values make up an Issue, which varieties exist (and at which **plate positions**), which derived stamps come from which base via overprint, and how printings and remainders flow.
* If/when you need collection‑grade granularity **per suffix** (prices, scans, certificates, postal history), refactor to **V2** where every suffixed item is a `:Stamp` with a `:VARIANT_OF` link. That step will reuse your existing nodes and relations with minimal disruption.
