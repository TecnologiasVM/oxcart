/**
 * Typed fetch client for the First Issue KG backend (read-only, LLM-free).
 *
 * Base URL points at the FastAPI backend on port 8090. The backend strips any
 * embedding/vector property; we strip again here so the UI can never render one
 * even if the contract regresses.
 */

import type {
  ExampleQuery,
  ExploreFilters,
  ExploreResponse,
  GraphOptions,
  GraphResponse,
  HealthResponse,
  MenaEvidenceResponse,
  MenaIssueDetail,
  NodeDetail,
  OverviewResponse,
  PropBag,
  QueryRequest,
  QueryResponse,
  SurfaceMailResponse,
} from "./types";

/**
 * Base URL for API calls.
 *
 * Default is "" (relative) so the browser calls the SAME origin it loaded from
 * (e.g. http://localhost:3000/api/...) and Next.js rewrites those to the
 * FastAPI backend server-side (see next.config.ts). This keeps the backend
 * internal — only port 3000 is exposed, and no CORS is needed.
 *
 * Set NEXT_PUBLIC_API_BASE to an absolute URL (e.g. http://localhost:8090) only
 * for the legacy "browser talks to FastAPI directly" mode, which then requires
 * exposing port 8090 and adding the origin to the FastAPI CORS allow-list.
 */
export const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE) || "";

/** Keys matching this are never exposed to the UI. */
const FORBIDDEN_KEY = /embed|vector/i;

/** Recursively strip any property whose key matches /embed|vector/i. */
export function stripVectors<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((v) => stripVectors(v)) as unknown as T;
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (FORBIDDEN_KEY.test(k)) continue;
      out[k] = stripVectors(v);
    }
    return out as unknown as T;
  }
  return value;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
    });
  } catch (e) {
    const target = API_BASE || "the Next.js /api proxy";
    throw new ApiError(
      `Cannot reach the First Issue KG backend via ${target}. Is FastAPI running on port 8090 (and the frontend proxying to it)?`,
      0,
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string; message?: string };
      detail = body.detail || body.message || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }
  const json = (await res.json()) as T;
  return stripVectors(json);
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** POST /api/query — wraps retrieve.context_bundle. No LLM answer is returned. */
export function postQuery(req: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>("/api/query", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/** Backwards-compatible alias for {@link postQuery}. */
export const runQuery = postQuery;

/** GET /api/health — advisory backend liveness check. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

/** GET /api/overview — landing-page summary (issue header, totals, roster, scores). */
export function getOverview(): Promise<OverviewResponse> {
  return request<OverviewResponse>("/api/overview");
}

/**
 * GET /api/graph — the full issue graph as {nodes, edges}.
 * `clean: true` requests the CLEAN tier (link score >= min, no COMPETING).
 */
export function getGraph(opts: GraphOptions = {}): Promise<GraphResponse> {
  const params = new URLSearchParams();
  if (opts.clean !== undefined) params.set("clean", String(opts.clean));
  const qs = params.toString();
  return request<GraphResponse>(`/api/graph${qs ? `?${qs}` : ""}`);
}

/** GET /api/graph/stamp/{cno} — graph focused on a single Mena stamp scope. */
export function getStampGraph(cno: string): Promise<GraphResponse> {
  return request<GraphResponse>(`/api/graph/stamp/${encodeURIComponent(cno)}`);
}

/** GET /api/explore — Cytoscape-ready graph payload, parameterized by filters. */
export function getExplore(filters: Partial<ExploreFilters>): Promise<ExploreResponse> {
  const params = new URLSearchParams();
  if (filters.clean_tier !== undefined) params.set("clean_tier", String(filters.clean_tier));
  if (filters.max_docs !== undefined) params.set("max_docs", String(filters.max_docs));
  if (filters.chunks_per_doc !== undefined) params.set("chunks_per_doc", String(filters.chunks_per_doc));
  if (filters.stamp_focus) params.set("stamp_focus", filters.stamp_focus);
  const qs = params.toString();
  return request<ExploreResponse>(`/api/explore${qs ? `?${qs}` : ""}`);
}

/** GET /api/node — generic node detail for the right-hand panel. */
export function getNodeDetail(nodeId: string): Promise<NodeDetail> {
  // Backend route (backend/app/routers/graph.py) requires the `node_id` query
  // param; sending `id` returns 422 and the panel renders the error object as
  // "[object Object]". Caught by the explore E2E + a live diagnostic.
  return request<NodeDetail>(`/api/node?node_id=${encodeURIComponent(nodeId)}`);
}

/** GET /api/examples — canonical demo questions (examples_runner.DEMO). */
export function getExamples(): Promise<ExampleQuery[]> {
  return request<ExampleQuery[]>("/api/examples");
}

// ---------------------------------------------------------------------------
// Mena Catalogue -> Surface Mail (read-only). All route through request<T> so
// stripVectors() runs defensively on every payload.
// ---------------------------------------------------------------------------

/** GET /api/mena/surface-mail — Surface-Mail issues grouped by year (fast nav index). */
export function getSurfaceMail(): Promise<SurfaceMailResponse> {
  return request<SurfaceMailResponse>("/api/mena/surface-mail");
}

/** GET /api/mena/issue/{id} — fast per-issue facts + Scott match (no graph/Weaviate). */
export function getMenaIssue(issueId: string): Promise<MenaIssueDetail> {
  return request<MenaIssueDetail>(`/api/mena/issue/${encodeURIComponent(issueId)}`);
}

/** GET /api/mena/issue/{id}/graph — lazy per-issue mini-graph (issue → stamps → varieties → Scott). */
export function getMenaIssueGraph(issueId: string): Promise<GraphResponse> {
  return request<GraphResponse>(`/api/mena/issue/${encodeURIComponent(issueId)}/graph`);
}

/** GET /api/mena/issue/{id}/evidence — lazy Weaviate BM25 passages (no key needed). */
export function getMenaIssueEvidence(issueId: string, k?: number): Promise<MenaEvidenceResponse> {
  const qs = k !== undefined ? `?k=${k}` : "";
  return request<MenaEvidenceResponse>(`/api/mena/issue/${encodeURIComponent(issueId)}/evidence${qs}`);
}

/** Convenience re-export so components can scrub a single prop bag if needed. */
export function cleanProps(props: PropBag): PropBag {
  return stripVectors(props);
}
