Costa Rica Philately → Neo4j (V1) — Technical Guide & Cypher Cookbook

A practical, end-to-end reference for the codebase that ingests the Mena Costa Rica postal catalog into Neo4j, builds search indexes & embeddings, exposes hybrid retrieval utilities, and ships a modern Gradio + vis.js graph viewer for interactive exploration.

⸻

1) Project Overview

What this repo does
	•	Ingests a structured JSON export of the Mena catalog (issues, stamps, varieties, proofs, plates, production orders, remainders, essays/specimens, legal acts, people, printers, orgs, biblio refs) into a normalized Neo4j graph.
	•	Creates indexes (Neo4j full-text + vector) and generates OpenAI embeddings for hybrid search.
	•	Provides a search module with three modes: full-text, vector, and hybrid (alpha-weighted).
	•	Renders the graph with a Gradio UI that runs Cypher and visualizes paths via vis.js with a philately-friendly color palette and UX (tooltips, physics toggle, fullscreen, legend feel).

Primary modules (files)
	•	neo4j_ingest_mena_v1.py – ingestion pipeline & constraints
	•	neo4j_index_and_embed.py – indexes, corpus builder, embedding generation/upsert
	•	neo4j_search.py – full-text / vector / hybrid search + graph expansion helpers
	•	neo4j_gradio_VIS.py – Gradio + vis.js viewer that executes arbitrary Cypher and draws the result

⸻

2) Data Model (V1) — Entities, Keys, and Rationale

Goals of the model (V1)
	1.	Represent Issues and their technical/administrative context; 2) Stamps (base/catalog numbers) + Varieties (suffix-level distinctions); 3) Proofs (die/plate/color) linked to issues; 4) Production Orders & Remainders; 5) Plates and optional Plate Positions for repeatable flaws; 6) Idempotent ingestion via unique constraints and MERGE.  ￼

Key design choices
	•	:LegalAct replaces the earlier :Document; the Issue→Act relation is (:Issue)-[:AUTHORIZED_BY]->(:LegalAct) keyed by (type, id, date) and stores ids (council/session references).  ￼
	•	Officials are only recorded as :Person when the token looks like a real name; otherwise the token is appended to LegalAct.ids to avoid polluting people with “session #229”.  ￼  ￼
	•	Essays provenance is typed: :Person, :Organization, or :BiblioRef. Prefix “ex-” maps to EX_PROVENANCE; otherwise PROVENANCE. Bibliographic strings become :BiblioRef via CITED_IN.  ￼  ￼
	•	Varieties live under :Stamp (V1), mirroring JSON (base + suffix). This is convenient for “list all suffixes of #N” and for tying constant plate flaws to PlatePosition.  ￼  ￼
	•	issue_dates are preserved as a JSON string property on :Issue. PlatePosition nodes are created only when both position and plate are present. Ingestion is idempotent via constraints.  ￼  ￼

Unique keys / constraints (recommended)
	•	(:Issue) ON issue_id
	•	(:Stamp) ON (issue_id, catalog_no)
	•	(:Variety) ON (issue_id, base_catalog_no, suffix)
	•	(:Proof) ON code (die/plate/color sublabels)
	•	(:Plate) ON (issue_id, denomination, no)
	•	(:ProductionOrder) ON (issue_id, date)
	•	(:Quantity) ON po_key
	•	(:LegalAct) ON (type, id, date)
	•	(:Person), (:Printer), (:Organization), (:BiblioRef) on their names/keys.  ￼  ￼

⸻

3) Ingestion Pipeline (neo4j_ingest_mena_v1.py)

Inputs & config
	•	Set DATA_JSON to your consolidated Mena JSON (e.g., mena_all_with_raw.json).
	•	Neo4j connection via NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.

Constraints first
run_constraints() installs all uniqueness constraints (see section 2), then ingestion runs per issue to keep idempotency.

Issue core
ingest_issue() creates/updates :Issue with essential fields and stores issue_dates as JSON string; connects PRINTED_BY to :Printer when present; creates :LegalAct nodes and AUTHORIZED_BY edges; signers become :Person via a name-shaped heuristic, otherwise appended to LegalAct.ids. (This matches the README design.)  ￼

Stamps & Varieties
ingest_stamps() creates :Stamp (value/unit, color, perf, watermark, etc.) and links to Issue.
ingest_varieties() creates :Variety under each base stamp; if a variety has a position and the plate is known, it creates/links a :PlatePosition ((issue_id, plate no, pos) via elementId(pl) to scope positions to a specific plate instance).

Plates & Positions
ingest_issue() also creates :Plate nodes per denomination + number (and notes) and links via HAS_PLATE. :PlatePosition is optional and only created when the data supports it.  ￼

Proofs
ingest_proofs() handles DieProof, PlateProof, ColorProof under a unified :Proof supertype keyed by code, ensuring uniqueness across groups/variants.

Production Orders & Remainders
ingest_production_orders() models (Issue)-[:HAS_PRODUCTION_ORDER]->(ProductionOrder)-[:INCLUDES]->(Quantity) (prints) and (Issue)-[:HAS_REMAINDERS]->(RemaindersEvent)-[:INCLUDES]->(Quantity) (remainders), with optional purchaser via SOLD_TO. (See cookbook queries below.)  ￼

Essays & Specimens
ingest_specimens_essays() creates :Essay/:Specimen and attaches typed provenance (PROVENANCE / EX_PROVENANCE) to :Person/:Organization, and citations to :BiblioRef.  ￼

One-time cleanup tip. If older data incorrectly created sessions as :Person (e.g., “session #229”), move those tokens to LegalAct.ids, delete the wrong edges/nodes with the provided normalization script.  ￼

⸻

4) Indexing & Embeddings (neo4j_index_and_embed.py)

What it builds
	•	Unique constraint on :Issue(issue_id).
	•	Full-text index issue_text_idx over i.title, i.plain_raw_text, i.pictures_raw_text.
	•	Vector index issue_vec_idx on i.embedding with cosine similarity (dimension = embedding size).
	•	Search corpus materialized in i.search_corpus (title + raw texts).

Embeddings
	•	Generates text-embedding-3-large vectors via OpenAI and upserts into each :Issue.embedding.
	•	Supports batching with progress logging and optional sleeps.

CLI examples

# Create indexes and build corpus (one-time), then generate embeddings
python neo4j_index_and_embed.py

# Only embeddings (skip index creation)
python neo4j_index_and_embed.py --skip-indexes

Required env

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
OPENAI_API_KEY=sk-xxxxx


⸻

5) Search Utilities (neo4j_search.py)

Modes
	•	fulltext(q, k) → hits issue_text_idx full-text index.
	•	vector(text, k) → embeds the query text, queries issue_vec_idx.
	•	hybrid(q, text, alpha, k) → score-normalized blend: alpha·vector + (1-alpha)·full-text.

Driver function

run_search(
  mode,                # "fulltext" | "vector" | "hybrid"
  q="first issue",     # for fulltext/hybrid
  text="...query...",  # for vector/hybrid (embedded)
  alpha=0.35,          # hybrid coefficient
  k=10,                # top-K
  min_score=0.4        # optional post-filter
)

Environment flags (optional)
	•	SEARCH_MODE (hybrid|fulltext|vector)
	•	SEARCH_ALPHA, SEARCH_TOPK, SEARCH_MIN_SCORE
	•	SEARCH_INCLUDE_GRAPH (true/false) — if you choose to fetch a neighborhood after getting results.

Expanding to a navigable graph
	•	build_issue_graph_cypher(issues) → returns Cypher that collects a rich neighborhood for the given list of issue_ids using non-deprecated syntax (helpful for Neo4j Browser and the Gradio viewer).
	•	expand(issue_ids, limit_paths=2000) → returns paths (for graph view) and a summary table (issue → stamps/varieties).

Hybrid query (concept)

The hybrid Cypher normalizes both score lists (vector/full-text) to [0..1], blends using alpha, orders by combined score, then resolves to :Issue. (Useful when users mix exact IDs/titles with narrative text.)

⸻

6) Graph Viewer (neo4j_gradio_VIS.py)

What it is

A Gradio Blocks app that accepts a free-form Cypher input, executes it, and renders the returned paths and nodes as an interactive vis.js network:
	•	Color palette by label (Issue / Stamp / Variety / Plate / Proof / LegalAct / Person / Printer / Organization / etc.).
	•	Tooltips show label, caption, and serialized properties (selected keys are highlighted).
	•	Physics auto-stops after stabilization; toggle on/off with a button or Space.
	•	Fullscreen & reset view controls; short vs full labels.

Default Cypher

The default query is a safe starter: find an Issue by text (title or issue_id), then expand one hop to its Stamps and optionally to Varietys—returning paths for graph rendering. (You can paste any Cypher that RETURNs nodes, relationships, and/or paths.)

Tip: In Neo4j Browser or the viewer, queries that RETURN p or RETURN p1, p2... render as Graph. You can switch to a table when you need row detail. See the cookbook in the next section for ready-to-run examples.  ￼

Running the app

# env (example)
export NEO4J_URI="neo4j://127.0.0.1:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your-password"
export NEO4J_DATABASE="neo4j"   # optional
export GRADIO_SHARE="1"         # set 0/false to disable share link
# optional basic auth for the UI:
export APP_USER="viewer" ; export APP_PASS="viewer-pass"

python neo4j_gradio_VIS.py


⸻

7) Cypher Cookbook (ready to paste)

These match the V1 model and are safe to run in the viewer or Neo4j Browser.

A) Issue “global” view — Issue and first/second-level neighbors (legal acts, plates, stamps, proofs, quantities, essays/specimens, etc.).  ￼

WITH 'CR-1863-FIRST-ISSUE' AS issue_id
MATCH p = (iss:Issue {issue_id:issue_id})
          -[:PRINTED_BY|AUTHORIZED_BY|HAS_PLATE|HAS_STAMP|HAS_PROOF
            |HAS_PRODUCTION_ORDER|HAS_REMAINDERS|HAS_ESSAY|HAS_SPECIMEN*1..2]-(n)
WITH collect(p) AS paths1, collect(DISTINCT n) AS lvl1
UNWIND lvl1 AS x
OPTIONAL MATCH p2 = (x)-[:SIGNED_BY|INCLUDES|SOLD_TO|USES_PLATE|HAS_VARIETY|AT_POSITION]->(y)
RETURN p, p2
LIMIT 2000;

B) All stamps of an Issue, with varieties (ordered)  ￼

WITH 'CR-1863-FIRST-ISSUE' AS issue_id
MATCH (iss:Issue {issue_id:issue_id})-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
RETURN s.catalog_no AS no, s.color AS color, s.perforation AS perf,
       collect(v.suffix) AS varieties
ORDER BY no;

C) Varieties anchored to Plate Positions (for constant plate flaws)  ￼

MATCH (s:Stamp)-[:HAS_VARIETY]->(v:Variety)-[:AT_POSITION]->(pp:PlatePosition)
RETURN s.issue_id, s.catalog_no, v.suffix, v.description, v.plate AS plate_no, pp.pos
ORDER BY s.issue_id, s.catalog_no, pp.pos;

D) Overprint/Surcharge derivations (OVERPRINTED_ON)  ￼

MATCH (d:Stamp)-[r:OVERPRINTED_ON]->(b:Stamp)
RETURN d.issue_id AS derived_issue, d.catalog_no AS derived_no,
       r.type AS op_type, r.surcharged_value AS sc_val, r.surcharged_unit AS sc_unit,
       r.on_value AS on_val, r.on_unit AS on_unit,
       b.issue_id AS base_issue, b.catalog_no AS base_no
ORDER BY derived_issue, derived_no;

E) Production orders & quantities (by date)  ￼

MATCH (iss:Issue)-[:HAS_PRODUCTION_ORDER]->(po:ProductionOrder)-[:INCLUDES]->(q:Quantity)
RETURN iss.issue_id, po.date, q.plate_desc, q.quantity
ORDER BY iss.issue_id, po.date, q.plate_desc;

F) Remainders (with buyer when present)  ￼

MATCH (iss:Issue)-[:HAS_REMAINDERS]->(ev:RemaindersEvent)-[:INCLUDES]->(q:Quantity)
OPTIONAL MATCH (ev)-[:SOLD_TO]->(p:Person)
RETURN iss.issue_id, ev.date, q.plate_desc, q.quantity, p.name AS buyer
ORDER BY iss.issue_id, ev.date, q.plate_desc;

G) “Tech sheet” for a Stamp (core properties + linked plates & suffixes)  ￼

WITH 'CR-1863-FIRST-ISSUE' AS issue_id, '1' AS catalog_no
MATCH (s:Stamp {issue_id:issue_id, catalog_no:catalog_no})
OPTIONAL MATCH (s)-[:USES_PLATE]->(pl:Plate)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
RETURN s.catalog_no AS no, s.denomination_value AS val, s.denomination_unit AS unit,
       s.color AS color, s.perforation AS perf, s.quantity_reported AS qty_reported,
       collect(DISTINCT pl.no) AS plates, collect(DISTINCT v.suffix) AS variety_suffixes;

H) Quick sanity counts (by label)  ￼

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


⸻

8) Setup & Execution (end-to-end)
	1.	Prepare Neo4j (local or remote). Ensure you can connect with your credentials.
	2.	Load .env (optional): NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OPENAI_API_KEY.
	3.	Ingest the JSON:

export DATA_JSON="/absolute/path/mena_all_with_raw.json"
python neo4j_ingest_mena_v1.py

	4.	Create indexes & generate embeddings:

python neo4j_index_and_embed.py

	5.	Try searches (optional local test):

from neo4j_search import run_search
run_search("hybrid", q="first issue", text="Costa Rica first issue 1863", alpha=0.35, k=10)

	6.	Run the viewer:

python neo4j_gradio_VIS.py


⸻

9) Philately-Aware Tips
	•	Use Varieties under :Stamp to group all suffixes for a base number—great for collectors’ view and for anchoring to PlatePosition when the flaw is constant.  ￼
	•	Keep Proofs distinct (Die/Plate/Color) but keyed via a unifying code, so your counts and linkages remain clean across subtypes.
	•	Model Overprints/Surcharges through OVERPRINTED_ON with a few well-chosen properties (type, on/off values/units) and grow later into events if needed.  ￼

⸻

10) Gotchas & Migration Notes
	•	If you migrated from an earlier schema that used :Document / HAS_DOCUMENT, prefer :LegalAct / AUTHORIZED_BY and do not create fake :Person nodes for sessions/councils. Use the cleanup query if needed.  ￼  ￼
	•	In Neo4j Browser/Viewer, only paths render as graphs. Ensure your query RETURNs paths (or nodes + relationships) rather than scalar columns.  ￼

⸻

11) Environment Variables (summary)

Common across modules
	•	NEO4J_URI (neo4j://host:7687 or bolt://host:7687)
	•	NEO4J_USER, NEO4J_PASSWORD
	•	NEO4J_DATABASE (optional, viewer)
	•	OPENAI_API_KEY (index/embedding, search vector)
	•	DATA_JSON (ingestion script input)

Viewer (optional)
	•	GRADIO_SHARE (1/0), APP_USER, APP_PASS, PORT

Search (optional)
	•	SEARCH_MODE, SEARCH_ALPHA, SEARCH_TOPK, SEARCH_MIN_SCORE, SEARCH_INCLUDE_GRAPH

⸻

12) Troubleshooting
	•	neo4j Python driver not found – Install the official driver: pip install neo4j python-dotenv gradio openai tqdm.
	•	AuthError in the viewer – Verify NEO4J_URI/USER/PASSWORD and database name.
	•	Embeddings step fails – Check OPENAI_API_KEY and outbound network access.
	•	No graph appears – Ensure your query RETURNs paths (e.g., RETURN p) and that limits are high enough to see context.

⸻

13) Appendix — Quick Labels & Colors (viewer)

Issue, Stamp, Variety, Plate, PlatePosition, Proof (Die/Plate/Color sublabels), ProductionOrder, Quantity, LegalAct, Person, Printer, Organization, BiblioRef, Essay, Specimen. The viewer maps each label to a distinct palette so issues, stamps, legal acts, etc., are immediately recognizable while browsing.

⸻

A final word

This V1 graph mirrors your JSON, is idempotent, and supports hybrid retrieval and interactive exploration. Upgrading later to treat every suffixed variety as a first-class collectible unit is straightforward, thanks to the current constraints and relationships.  ￼

⸻

Selected references come from the bundled schema README to keep this guide aligned with your actual graph model and Cypher best practices.