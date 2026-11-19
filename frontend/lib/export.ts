/*
 * Trigger a full-text, LLM-ready .txt download for a query.
 *
 * The file is built SERVER-SIDE (POST /api/query/export) and streamed as
 * text/plain, then saved by the browser. This is deliberate:
 *   - the DISPLAY response (POST /api/query) clips each card's text to keep its
 *     JSON small, so the full evidence text is NOT in what the page holds;
 *   - the full text lives only here, and because this is a file download (not a
 *     browser JSON.parse) it is immune to the "Unterminated string in JSON"
 *     truncation that large bodies hit on the display path.
 * No LLM is called — the system is retrieval-only; the file packages the evidence.
 */
import { API_BASE, ApiError } from "./api";

export interface ExportParams {
  /** Mena scope code "1".."4" or null (must match the query that produced the view). */
  stamp?: string | null;
  min_link?: number;
  max_lexical?: number;
  k_weaviate?: number;
  exclude_competing?: boolean;
}

function slug(q: string): string {
  return (
    (q || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 50) || "query"
  );
}

/**
 * Fetch the server-built export for `question` (+ the same params used for the
 * query) and save it as `first-issue-<slug>.txt`. Throws {@link ApiError} on a
 * non-2xx response so the caller can surface it.
 */
export async function downloadQueryExport(
  question: string,
  params: ExportParams = {},
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/query/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, ...params }),
  });
  if (!res.ok) {
    throw new ApiError(`Export failed (${res.status})`, res.status);
  }
  const text = await res.text();
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `first-issue-${slug(question)}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
