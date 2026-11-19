/**
 * Shared TypeScript types for the First Issue Knowledge Graph UI.
 *
 * These mirror the read-only, LLM-free payloads produced by the prototype Python
 * layer (oxcart/retrieve.py + the backend wrapper on port 8090):
 *   - POST /api/query   -> QueryResponse   (wraps retrieve.context_bundle)
 *   - GET  /api/explore -> ExploreResponse (Cytoscape-ready graph payload)
 *   - GET  /api/node    -> NodeDetail      (generic node detail for the panel)
 *   - GET  /api/examples-> ExampleQuery[]  (examples_runner.DEMO)
 *
 * INVARIANT: no field here ever carries an embedding/vector property. The backend
 * strips any key matching /embed|vector/i; the UI strips again defensively.
 */

// ---------------------------------------------------------------------------
// Graph node taxonomy (drives Cytoscape styling + the Legend)
// ---------------------------------------------------------------------------
export type NodeType =
  | "Issue"
  | "Stamp"
  | "ScottStamp"
  | "Variety"
  | "Illustration"
  | "Proof"
  | "Plate"
  | "Document"
  | "Chunk";

export const NODE_TYPES: NodeType[] = [
  "Issue",
  "Stamp",
  "ScottStamp",
  "Variety",
  "Illustration",
  "Proof",
  "Plate",
  "Document",
  "Chunk",
];

export type EdgeType =
  | "HAS_STAMP"
  | "HAS_VARIETY"
  | "HAS_SCOTT_STAMP"
  | "EQUIVALENT_TO"
  | "DEPICTS"
  | "VARIETY_OF"
  | "HAS_PROOF"
  | "HAS_PLATE"
  | "HAS_CHUNK"
  | "NEXT"
  | "MENTIONS"
  | "MENTIONS_STAMP"
  | string;

/** A generic property bag returned from Neo4j, embeddings already stripped. */
export type PropBag = Record<string, unknown>;

// ---------------------------------------------------------------------------
// Cytoscape graph payload (GET /api/explore, GET /api/graph)
// ---------------------------------------------------------------------------
export interface GraphNode {
  id: string;
  type: NodeType;
  label: string;
  props: PropBag;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
}

export interface ExploreFilters {
  clean_tier: boolean;
  max_docs: number;
  chunks_per_doc: number;
  /** Mena scope code "1" | "2" | "3" | "4", or null for all. */
  stamp_focus: string | null;
}

export interface ExploreResponse {
  issue_id: string;
  prototype: string;
  filters: ExploreFilters;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/**
 * Graph payload consumed by the Explore/Overview surfaces and GraphView.
 * The {nodes, edges} core of an ExploreResponse — the backend's GET /api/graph,
 * GET /api/graph/stamp/{cno} responses. Embeddings/vectors already stripped.
 */
export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  issue_id?: string;
  prototype?: string;
}

/** Options for GET /api/graph (CLEAN tier = score>=min, no COMPETING). */
export interface GraphOptions {
  clean?: boolean;
}

/**
 * GET /api/health — advisory backend liveness check.
 * Reports per-service reachability plus an optional free-form `detail` bag
 * (issue_id, service, counts, errors) that HealthBanner renders as mono text.
 */
export interface HealthResponse {
  neo4j: boolean;
  weaviate: boolean;
  graph_populated: boolean;
  detail?: Record<string, unknown>;
  status?: string;
}

// ---------------------------------------------------------------------------
// Overview (GET /api/overview) — landing page panel
// ---------------------------------------------------------------------------
export interface OverviewIssue {
  issue_id?: string;
  title?: string | null;
  country?: string | null;
  issue_dates?: string | null;
  perforation?: string | null;
  /** Clarifying note about the Scott catalogue count (1b is a variety, not a 6th stamp). */
  scott_note?: string | null;
}

export interface OverviewStamp {
  catalog_no: string;
  denomination_value?: string | number | null;
  denomination_unit?: string | null;
  color?: string | null;
  perforation?: string | null;
  quantity_reported?: number | string | null;
  /**
   * Backend `graph_service.overview()` emits Scott links under `scott` as a list
   * of `{scott_number, confidence}` objects (NOT `equivalent_scott: string[]`).
   * `equivalent_scott` is kept optional for back-compat but is not populated.
   */
  scott?: { scott_number: string; confidence?: number | string | null }[];
  equivalent_scott?: string[];
}

/** One bar in the link-score distribution histogram. */
export interface ScoreBucket {
  count: number;
  label?: string | null;
  bucket?: string | number | null;
}

export interface OverviewResponse {
  issue: OverviewIssue;
  totals?: Record<string, number | string>;
  stamps?: OverviewStamp[];
  score_distribution?: ScoreBucket[];
}

/** Cytoscape element shape (what GraphCanvas consumes). */
export interface CyNodeData {
  id: string;
  type: NodeType;
  label: string;
  [key: string]: unknown;
}
export interface CyEdgeData {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  [key: string]: unknown;
}
export type CyElement = { data: CyNodeData } | { data: CyEdgeData };

// ---------------------------------------------------------------------------
// Node detail (GET /api/node) — for NodeDetailPanel
// ---------------------------------------------------------------------------
export interface NeighborRef {
  rel: EdgeType;
  dir: "in" | "out";
  id: string;
  type: NodeType;
  label: string;
}

export interface NodeDetail {
  id: string;
  type: NodeType;
  label: string;
  /** Display title used by the active panel (falls back to label/id when absent). */
  title?: string;
  /** Embeddings/vectors already stripped server-side; stripped again in the UI. */
  props: PropBag;
  /** Backend alias for `props` consumed by the active NodeDetailPanel. */
  properties?: PropBag;
  neighbors: NeighborRef[];
  /** Related entities grouped by relationship/category (backend: dict[str, Any]). */
  related?: Record<string, unknown>;
  /** Chunk-only enrichment: signals + linked stamps (from MENTIONS/MENTIONS_STAMP). */
  text?: string | null;
  signals?: string[];
  linked_stamps?: string[];
}

// ---------------------------------------------------------------------------
// Query / context bundle (POST /api/query) — mirrors retrieve.context_bundle
// ---------------------------------------------------------------------------
export interface ScottEquivalent {
  scott: string;
  confidence: number | null;
}

export interface DomainStamp {
  catalog_no: string;
  denomination_value: string | null;
  denomination_unit: string | null;
  color: string | null;
  perforation: string | null;
  status: string | null;
  quantity_reported: number | string | null;
  equivalent_scott: ScottEquivalent[];
}

export interface ScottRosterEntry {
  scott_number: string;
  denomination: string | null;
  color: string | null;
  mint_value: string | null;
  used_value: string | null;
  perforation: string | null;
  description: string | null;
  variety_of: string | null;
}

export interface DomainFacts {
  issue_id: string;
  found: boolean;
  title?: string | null;
  plain_raw_text_excerpt?: string | null;
  perforation?: string | null;
  issue_dates?: string | null;
  country?: string | null;
  stamps?: DomainStamp[];
  scott_roster?: ScottRosterEntry[];
}

export interface Variety {
  suffix: string;
  base_catalog_no: string;
  [key: string]: unknown;
}

export interface StampVarieties {
  stamp: string;
  varieties: Variety[];
}

export interface RelatedFacts {
  stamp_varieties: StampVarieties[];
  proofs: PropBag[];
  plates: PropBag[];
}

export interface SourceDoc {
  doc_id: string;
  chunks: number;
  best_score: number;
  best_link: number;
  pages: number[];
}

export interface LexicalHit {
  chunk_id: string;
  doc_id: string;
  page: number | null;
  text: string;
  link_score: number | null;
  score: number | null;
  signals: string[];
  via: string;
  conf?: number | null;
}

export interface WeaviateHit {
  chunk_id: string | null;
  doc_id: string | null;
  page: number | null;
  snippet: string;
  score: number | null;
  via: string;
}

export interface BundleCounts {
  lexical: number;
  weaviate: number;
  source_docs: number;
}

/**
 * A page figure related to the query. The backend associates figures by the
 * source chunk's (doc_id, page) — the sanitized chunk text no longer carries the
 * inline `![Figure](...)` embeds. `url` is served by the backend's /api/figures
 * static mount (proxied through the Next.js /api rewrite).
 */
export interface QueryFigure {
  filename: string;
  doc_id: string;
  page: number;
  url: string;
  chunk_id?: string | null;
  /** Source chunk's MENTIONS link score (graph link strength). */
  link_score?: number | null;
  /** Source chunk's fulltext relevance score, when available. */
  score?: number | null;
}

export interface QueryResponse {
  domain: DomainFacts;
  related: RelatedFacts;
  sources: SourceDoc[];
  lexical: LexicalHit[];
  weaviate: WeaviateHit[];
  counts: BundleCounts;
  /** Optional retrieval subgraph for the query view (nodes/edges), when present. */
  subgraph?: GraphResponse | null;
  /** Related page figures for the cited pages (top-N, de-duplicated). */
  figures?: QueryFigure[];
}

// ---------------------------------------------------------------------------
// Query request (POST /api/query body) — mirrors context_bundle kwargs
// ---------------------------------------------------------------------------
export interface QueryRequest {
  question: string;
  /** Mena scope code "1".."4" or null. */
  stamp?: string | null;
  max_lexical?: number;
  k_weaviate?: number;
  min_link_score?: number;
  exclude_competing?: boolean;
}

// ---------------------------------------------------------------------------
// Example queries (GET /api/examples) — mirrors examples_runner.DEMO
// ---------------------------------------------------------------------------
export interface ExampleQuery {
  question: string;
  /** Expected Mena scope code, or null. */
  scope?: string | null;
  /** Mena stamp scope code "1".."4" the example pre-selects (backend alias of scope). */
  stamp?: string | null;
}

// ---------------------------------------------------------------------------
// Mena scope codes (1=half real, 2=2 reales, 3=4 reales, 4=1 peso)
// ---------------------------------------------------------------------------
export interface StampScope {
  code: string;
  label: string;
}

export const STAMP_SCOPES: StampScope[] = [
  { code: "1", label: "1 — half real" },
  { code: "2", label: "2 — 2 reales" },
  { code: "3", label: "3 — 4 reales" },
  { code: "4", label: "4 — 1 peso" },
];

// ---------------------------------------------------------------------------
// Mena Catalogue -> Surface Mail (GET /api/mena/*) — mirrors backend schemas.py
// Surface Mail = Issue.section == "Surface Mail" (no A-numbers); navigate by year.
// ---------------------------------------------------------------------------
export interface SurfaceMailIssueRef {
  issue_id: string;
  title: string | null;
  n_stamps: number;
  year: string; // "1863".."2018" | "Undated"
}

export interface SurfaceMailYearGroup {
  year: string;
  count: number;
  issues: SurfaceMailIssueRef[];
}

export interface SurfaceMailResponse {
  section: string; // "Surface Mail"
  total_issues: number;
  years: SurfaceMailYearGroup[];
}

export interface MenaScottMatch {
  mena: string | null;
  scott: string | null;
  /** Categorical STRING ("high"/"medium") — distinct from the numeric graph link-score confidence. */
  confidence: string | null;
  scott_detail: Record<string, unknown> | null;
}

export interface MenaIssueStamp {
  catalog_no: string;
  denomination_value?: string | number | null;
  denomination_unit?: string | null;
  color?: string | null;
  perforation?: string | null;
  watermark?: string | null;
  quantity_reported?: number | string | null;
  status?: string | null;
  notes?: string | null;
  /** Graph-side Scott equivalents (only the First Issue has these). `confidence` is numeric here. */
  graph_scott?: { scott_number: string; confidence?: string | number | null }[];
}

export interface MenaIssueDetail {
  issue_id: string;
  year: string;
  title: string | null;
  /** Clean issue facts; `issue_dates` already parsed to an object (or kept as string on bad data). */
  issue: Record<string, unknown>;
  stamps: MenaIssueStamp[];
  counts: Record<string, number>;
  printer: string | null;
  printers: string[];
  legal_acts: Record<string, unknown>[];
  scott_match: MenaScottMatch[];
  graph_scott_roster: Record<string, unknown>[];
}

export interface MenaEvidencePassage {
  chunk_id: string | null;
  doc_id: string | null;
  page: number | string | null;
  snippet: string;
  score: number | null;
}

export interface MenaEvidenceResponse {
  issue_id: string;
  query: string;
  passages: MenaEvidencePassage[];
}
