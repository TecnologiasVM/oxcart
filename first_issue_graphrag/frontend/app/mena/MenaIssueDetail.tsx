"use client";

import { useEffect, useRef, useState } from "react";
import { getMenaIssue, getMenaIssueEvidence, getMenaIssueGraph } from "@/lib/api";
import type {
  GraphResponse,
  MenaEvidenceResponse,
  MenaIssueDetail as MenaIssueDetailData,
  MenaIssueStamp,
  MenaScottMatch,
} from "@/lib/types";
import { cleanCatalogText, displayDenom, issueDatesText } from "@/lib/format";
import { GraphView } from "../components/GraphView";
import { StampGlyph } from "../components/StampGlyph";

/*
 * Per-issue detail. The FAST path loads only catalogue facts + Scott match on
 * selection (getMenaIssue). The graph and the Weaviate evidence are LAZY and
 * fetched ON CLICK (not on an effect-of-flag), so selecting an issue never
 * triggers the heavy calls — each issue page stays fast. A ref guards against a
 * stale lazy result landing after the user switches issues.
 */
const COUNT_LABELS: Record<string, string> = {
  stamps: "stamps",
  proofs: "proofs",
  plates: "plates",
  essays: "essays",
  specimens: "specimens",
  production_orders: "production orders",
};

export interface MenaIssueDetailProps {
  issueId: string | null;
}

export function MenaIssueDetail({ issueId }: MenaIssueDetailProps) {
  const [facts, setFacts] = useState<MenaIssueDetailData | null>(null);
  const [factsLoading, setFactsLoading] = useState(false);
  const [factsError, setFactsError] = useState<string | null>(null);

  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);

  const [evidence, setEvidence] = useState<MenaEvidenceResponse | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  // Tracks the issue currently in view so a slow lazy fetch from a previous
  // issue cannot overwrite the new one's state.
  const currentIssue = useRef<string | null>(null);

  useEffect(() => {
    currentIssue.current = issueId;
    // Reset every lazy region on issue change (fast-load contract).
    setGraph(null);
    setGraphOpen(false);
    setGraphLoading(false);
    setEvidence(null);
    setEvidenceOpen(false);
    setEvidenceLoading(false);

    if (!issueId) {
      setFacts(null);
      setFactsError(null);
      return;
    }

    let cancelled = false;
    setFactsLoading(true);
    setFactsError(null);
    getMenaIssue(issueId)
      .then((d) => {
        if (!cancelled) setFacts(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setFactsError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setFactsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [issueId]);

  function loadGraph() {
    if (!issueId || graphOpen) return;
    const requested = issueId;
    setGraphOpen(true);
    setGraphLoading(true);
    getMenaIssueGraph(requested)
      .then((g) => {
        if (currentIssue.current === requested) setGraph(g);
      })
      .catch(() => {
        if (currentIssue.current === requested) setGraph({ nodes: [], edges: [] });
      })
      .finally(() => {
        if (currentIssue.current === requested) setGraphLoading(false);
      });
  }

  function loadEvidence() {
    if (!issueId || evidenceOpen) return;
    const requested = issueId;
    setEvidenceOpen(true);
    setEvidenceLoading(true);
    getMenaIssueEvidence(requested)
      .then((e) => {
        if (currentIssue.current === requested) setEvidence(e);
      })
      .catch(() => {
        if (currentIssue.current === requested) setEvidence({ issue_id: requested, query: "", passages: [] });
      })
      .finally(() => {
        if (currentIssue.current === requested) setEvidenceLoading(false);
      });
  }

  if (!issueId) {
    return (
      <div className="mena-detail">
        <p className="mono-label">No selection</p>
        <p className="mena-empty">Pick an issue from the list to read its catalogue record.</p>
      </div>
    );
  }

  return (
    <div className="mena-detail">
      {factsLoading && <p className="mono-label">Loading issue…</p>}
      {factsError && (
        <p className="mono-label" role="alert">
          Error: {factsError}
        </p>
      )}

      {facts && (
        <>
          <p className="mono mono-muted">
            {facts.issue_id} · {facts.year}
          </p>
          <h3>{facts.title || facts.issue_id}</h3>

          <IssueFacts facts={facts} />
          <Stamps stamps={facts.stamps} />
          <Counts counts={facts.counts} />
          <ScottMatch rows={facts.scott_match} />
          <CatalogNote text={facts.issue.plain_raw_text} />

          {/* Lazy, on-demand */}
          <div className="mena-detail__lazy">
            <button type="button" className="btn" onClick={loadGraph} disabled={graphOpen}>
              View graph <span className="btn__arrow">→</span>
            </button>
            <button type="button" className="btn" onClick={loadEvidence} disabled={evidenceOpen}>
              Query evidence <span className="btn__arrow">→</span>
            </button>
          </div>

          {graphOpen && (
            <div className="mena-detail__region">
              <span className="mono mono-muted">Graph · issue → stamps → varieties → Scott</span>
              {graphLoading ? (
                <p className="mono-label" style={{ marginTop: "var(--space-3)" }}>
                  Loading graph…
                </p>
              ) : graph && graph.nodes.length > 0 ? (
                <div style={{ height: 420, marginTop: "var(--space-3)" }}>
                  <GraphView graph={graph} height="100%" />
                </div>
              ) : (
                <p className="mena-empty">No graph nodes for this issue.</p>
              )}
            </div>
          )}

          {evidenceOpen && <Evidence loading={evidenceLoading} evidence={evidence} />}
        </>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
function IssueFacts({ facts }: { facts: MenaIssueDetailData }) {
  const issue = facts.issue ?? {};
  return (
    <dl className="dl" style={{ marginTop: "var(--space-4)" }}>
      {typeof issue.country === "string" && (
        <>
          <dt>Country</dt>
          <dd>{issue.country}</dd>
        </>
      )}
      {typeof issue.perforation === "string" && issue.perforation && (
        <>
          <dt>Perforation</dt>
          <dd>{issue.perforation}</dd>
        </>
      )}
      {facts.printer && (
        <>
          <dt>Printer</dt>
          <dd>{facts.printer}</dd>
        </>
      )}
      {issue.issue_dates != null && (
        <>
          <dt>Dates</dt>
          <dd>{issueDatesText(issue.issue_dates)}</dd>
        </>
      )}
      {facts.legal_acts.length > 0 && (
        <>
          <dt>Legal basis</dt>
          <dd>{facts.legal_acts.map(legalActLabel).filter(Boolean).join(" · ")}</dd>
        </>
      )}
    </dl>
  );
}

function legalActLabel(la: Record<string, unknown>): string {
  const type = la.type != null ? String(la.type) : "";
  const id = la.id != null ? String(la.id) : "";
  const date = la.date != null ? String(la.date) : "";
  const head = [type, id].filter(Boolean).join(" ");
  return [head, date].filter(Boolean).join(", ");
}

function Stamps({ stamps }: { stamps: MenaIssueStamp[] }) {
  if (!stamps || stamps.length === 0) return null;
  return (
    <div className="detail-group">
      <span className="mono mono-muted">Stamps · {stamps.length}</span>
      <div className="mena-stamps">
        {stamps.map((s) => (
          <div className="mena-stamp" key={s.catalog_no}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
              <StampGlyph denom={s.catalog_no} variant="ink" w={40} h={50} />
              <div>
                <span className="mono mono-muted">No. {s.catalog_no}</span>
                <div style={{ fontSize: 14 }}>
                  {displayDenom(s.catalog_no, s.denomination_value, s.denomination_unit) || "—"}
                </div>
              </div>
            </div>
            <p className="body-sm mono-muted" style={{ margin: "var(--space-2) 0 0" }}>
              {[s.color, s.perforation && `perf ${s.perforation}`].filter(Boolean).join(" · ") || ""}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Counts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts ?? {}).filter(([k, v]) => k !== "stamps" && v > 0);
  if (entries.length === 0) return null;
  return (
    <div className="mena-counts">
      {entries.map(([k, v]) => (
        <div key={k}>
          <div className="serif-display" style={{ fontSize: "1.6rem" }}>
            {v}
          </div>
          <span className="mono mono-muted">{COUNT_LABELS[k] ?? k.replace(/_/g, " ")}</span>
        </div>
      ))}
    </div>
  );
}

function ScottMatch({ rows }: { rows: MenaScottMatch[] }) {
  return (
    <div className="detail-group">
      <span className="mono mono-muted">Scott match</span>
      {rows && rows.length > 0 ? (
        <ul className="plain-list">
          {rows.map((r, i) => (
            <li key={i}>
              <span className="lead">Mena {r.mena}</span>
              <span> → </span>
              <span className="lead accent-cobalt">Scott {r.scott}</span>
              {r.confidence && (
                <span className="chip chip-competing" style={{ marginLeft: "var(--space-2)" }}>
                  {r.confidence}
                </span>
              )}
              {scottDetailText(r.scott_detail) && (
                <span className="mono-muted"> — {scottDetailText(r.scott_detail)}</span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mena-empty" style={{ padding: "var(--space-2) 0" }}>
          No Scott equivalence recorded for this issue yet.
        </p>
      )}
    </div>
  );
}

function scottDetailText(detail: Record<string, unknown> | null): string {
  if (!detail) return "";
  const parts: string[] = [];
  if (detail.denomination) parts.push(cleanCatalogText(detail.denomination));
  if (detail.color) parts.push(String(detail.color));
  if (detail.description) parts.push(cleanCatalogText(detail.description));
  if (detail.mint_value != null) parts.push(`mint ${String(detail.mint_value)}`);
  return parts.join(", ");
}

function CatalogNote({ text }: { text: unknown }) {
  if (typeof text !== "string" || !text.trim()) return null;
  return (
    <div className="detail-group">
      <span className="mono mono-muted">Catalogue note</span>
      <p className="chunk-text">{text}</p>
    </div>
  );
}

function Evidence({ loading, evidence }: { loading: boolean; evidence: MenaEvidenceResponse | null }) {
  return (
    <div className="mena-detail__region">
      <span className="mono mono-muted">Weaviate · BM25 · no key</span>
      {loading ? (
        <p className="mono-label" style={{ marginTop: "var(--space-3)" }}>
          Searching the corpus…
        </p>
      ) : evidence && evidence.passages.length > 0 ? (
        <>
          {evidence.query && (
            <p className="body-sm mono-muted" style={{ margin: "var(--space-2) 0 0" }}>
              query: {evidence.query}
            </p>
          )}
          {evidence.passages.map((p, i) => (
            <article key={p.chunk_id ?? i} className="surface evi-card">
              <div className="evi-card__meta">
                <span className="mono mono-muted">
                  {p.doc_id} · p{p.page ?? "—"}
                </span>
                {p.score != null && <span className="evi-card__score">{p.score.toFixed(2)}</span>}
              </div>
              <p className="evi-card__text">{p.snippet}</p>
            </article>
          ))}
        </>
      ) : (
        <p className="mena-empty">No passages found in the corpus for this issue.</p>
      )}
    </div>
  );
}

export default MenaIssueDetail;
