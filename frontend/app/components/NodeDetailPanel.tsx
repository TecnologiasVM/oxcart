"use client";

import { useEffect, useState } from "react";
import { getNodeDetail } from "@/lib/api";
import type { NodeDetail } from "@/lib/types";
import { issueDatesText } from "@/lib/format";
import { StampGlyph, type StampVariant } from "./StampGlyph";

/*
 * Side panel that loads NodeDetail for the selected graph node and renders it in
 * a HUMAN-READABLE layout — never raw JSON, never one-item-per-line dumps:
 *   - scalar properties        -> compact definition list
 *   - long text (chunk/issue)  -> readable wrapped paragraph
 *   - page lists               -> chips
 *   - varieties / equivalents  -> readable "lead — detail" lines
 *   - evidence chunks          -> small preview cards
 *
 * DEFENSIVE INVARIANT: never render any property whose key matches /embed|vector/i,
 * even if the backend regresses.
 */
const FORBIDDEN_KEY = /embed|vector/i;

// Long free-text fields rendered as a paragraph, not squeezed into the KV grid.
const TEXT_KEYS = new Set(["plain_raw_text", "text", "preview"]);
// Internal/bookkeeping keys not worth showing.
const HIDE_KEYS = new Set(["prototype", "reading_order", "issue_id"]);

const TEXT_TITLE: Record<string, string> = {
  plain_raw_text: "Catalog note",
  text: "Passage",
  preview: "Passage",
};

const GROUP_TITLE: Record<string, string> = {
  scott_roster: "Scott roster",
  equivalent_scott: "Scott equivalents",
  equivalent_mena: "Mena equivalents",
  variety_of: "Variety of",
  top_chunks: "Top passages",
  mentions_stamp: "Mentions stamps",
  chunk_count: "Chunks in document",
  evidence_chunks: "Evidence chunks",
  link_score: "Link score",
};

export interface NodeDetailPanelProps {
  nodeId: string | null;
}

export function NodeDetailPanel({ nodeId }: NodeDetailPanelProps) {
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    if (!nodeId) {
      setDetail(null);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    getNodeDetail(nodeId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  if (!nodeId) {
    return (
      <aside className="surface" aria-live="polite">
        <p className="mono-label">No selection</p>
        <p>Tap a node in the graph to inspect its catalog record and relationships.</p>
      </aside>
    );
  }

  return (
    <aside className="surface detail-panel" aria-live="polite">
      {loading && <p className="mono-label">Loading…</p>}
      {error && (
        <p className="mono-label" role="alert">
          Error: {error}
        </p>
      )}
      {detail && (
        <>
          <div className="detail__type">
            <span className="dot" />
            <span className="mono mono-muted">{detail.type}</span>
          </div>
          <h3 className="detail__title serif-display" style={{ marginTop: "var(--space-2)" }}>
            {detail.title || detail.type}
          </h3>

          <DetailGlyph detail={detail} />

          <hr className="rule-faint" />

          <PropertyList props={detail.properties} />
          <RelatedGroups related={detail.related} />
        </>
      )}
    </aside>
  );
}

// --------------------------------------------------------------------------- //
// Type glyph (encoded stamp) for Stamp / Issue / ScottStamp
// --------------------------------------------------------------------------- //
function DetailGlyph({ detail }: { detail: NodeDetail }) {
  const props = detail.properties ?? {};
  let denom = "";
  let variant: StampVariant = "ink";
  if (detail.type === "Stamp") {
    denom = String(props.catalog_no ?? "");
    variant = "amber";
  } else if (detail.type === "Issue") {
    denom = "1863";
    variant = "cobalt";
  } else if (detail.type === "ScottStamp") {
    denom = String(props.scott_number ?? "");
    variant = "cobalt";
  } else {
    return null;
  }
  return (
    <div className="detail__glyph">
      <StampGlyph denom={denom} variant={variant} w={84} h={104} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Properties
// --------------------------------------------------------------------------- //
function PropertyList({ props }: { props?: Record<string, unknown> }) {
  const entries = Object.entries(props ?? {}).filter(
    ([k]) => !FORBIDDEN_KEY.test(k) && !HIDE_KEYS.has(k),
  );
  const scalars = entries.filter(([k, v]) => !TEXT_KEYS.has(k) && isScalar(v) && !isEmpty(v));
  const texts = entries.filter(([k, v]) => TEXT_KEYS.has(k) && !isEmpty(v));

  return (
    <>
      {scalars.length > 0 && (
        <dl className="dl">
          {scalars.map(([k, v]) => (
            <FieldRow key={k} k={k} v={v} />
          ))}
        </dl>
      )}
      {texts.map(([k, v]) => (
        <div className="detail-group" key={k}>
          <span className="mono-label">{TEXT_TITLE[k] ?? humanize(k)}</span>
          <p className="chunk-text">{String(v)}</p>
        </div>
      ))}
    </>
  );
}

function FieldRow({ k, v }: { k: string; v: unknown }) {
  const display = k === "issue_dates" ? issueDatesText(v) : scalarText(v);
  return (
    <>
      <dt className="mono-label" style={{ alignSelf: "start" }}>
        {humanize(k)}
      </dt>
      <dd style={{ margin: 0, wordBreak: "break-word" }}>{display}</dd>
    </>
  );
}

// --------------------------------------------------------------------------- //
// Related groups (type-aware, never JSON)
// --------------------------------------------------------------------------- //
function RelatedGroups({ related }: { related?: Record<string, unknown> }) {
  const groups = Object.entries(related ?? {}).filter(
    ([k, v]) => !FORBIDDEN_KEY.test(k) && !isEmpty(v),
  );
  if (groups.length === 0) return null;

  return (
    <>
      <hr className="rule-faint" />
      {groups.map(([key, value]) => (
        <Group key={key} name={key} value={value} />
      ))}
    </>
  );
}

function Group({ name, value }: { name: string; value: unknown }) {
  const title = GROUP_TITLE[name] ?? humanize(name);

  // Page lists -> chips (was one number per line).
  if (name === "pages" && Array.isArray(value)) {
    return (
      <div className="detail-group">
        <span className="mono-label">{title}</span>
        <div className="chip-row">
          {value.map((p, i) => (
            <span key={i} className="chip">
              p.{String(p)}
            </span>
          ))}
        </div>
      </div>
    );
  }

  // Evidence passages -> small preview cards (was raw JSON).
  if (name === "top_chunks" && Array.isArray(value)) {
    return (
      <div className="detail-group">
        <span className="mono-label">{title}</span>
        {value.map((c, i) => (
          <EvidenceCard key={i} item={c} />
        ))}
      </div>
    );
  }

  // Plain scalar (chunk_count, evidence_chunks, series, link_score, page, …).
  if (isScalar(value)) {
    return (
      <p className="kv-row">
        <span className="mono-label">{title}</span>
        {scalarText(value)}
      </p>
    );
  }

  // Single related object (e.g. a chunk's MENTIONS edge).
  if (!Array.isArray(value)) {
    return (
      <div className="detail-group">
        <span className="mono-label">{title}</span>
        <ul className="plain-list">
          <li>
            <EntityLine d={describeItem(value)} />
          </li>
        </ul>
      </div>
    );
  }

  // List of related entities -> readable lines (was JSON dumps).
  const items = value.map((it) => describeItem(it)).filter(Boolean) as ItemDesc[];
  if (items.length === 0) return null;
  return (
    <div className="detail-group">
      <span className="mono-label">{title}</span>
      <ul className="plain-list">
        {items.map((d, i) => (
          <li key={i}>
            <EntityLine d={d} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceCard({ item }: { item: unknown }) {
  if (!item || typeof item !== "object") return null;
  const o = item as Record<string, unknown>;
  const meta = [
    o.page != null ? `p.${String(o.page)}` : "",
    o.link_score != null ? `link ${String(o.link_score)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const preview = o.preview != null ? String(o.preview) : "";
  return (
    <div className="evi-card">
      {meta && <p className="mono-label mono-muted">{meta}</p>}
      {preview && <p className="evi-text">{preview}…</p>}
    </div>
  );
}

interface ItemDesc {
  lead?: string;
  sub?: string;
  chips?: string[];
}

function EntityLine({ d }: { d: ItemDesc | null }) {
  if (!d || (!d.lead && !d.sub && !(d.chips && d.chips.length))) return null;
  return (
    <>
      {d.lead && <span className="lead">{d.lead}</span>}
      {d.sub && (
        <span>
          {d.lead ? " — " : ""}
          {d.sub}
        </span>
      )}
      {d.chips && d.chips.length > 0 && (
        <span className="chip-row">
          {d.chips.map((c, i) => (
            <span key={i} className="chip">
              {c}
            </span>
          ))}
        </span>
      )}
    </>
  );
}

/**
 * Turn an arbitrary related entity into a readable {lead, sub, chips} — NEVER
 * JSON. Handles ScottStamp / Stamp / Variety / Illustration / chunk-mention
 * shapes and degrades gracefully for anything else.
 */
function describeItem(item: unknown): ItemDesc | null {
  if (item === null || item === undefined) return null;
  if (typeof item !== "object") return { lead: String(item) };
  const o = item as Record<string, unknown>;

  let lead = "";
  if (o.scott_number != null) lead = `Scott ${String(o.scott_number)}`;
  else if (o.catalog_no != null) lead = `Mena ${String(o.catalog_no)}`;
  else if (o.suffix != null) lead = String(o.suffix);
  else if (o.design_name) lead = String(o.design_name);
  else if (o.label ?? o.title ?? o.name) lead = String(o.label ?? o.title ?? o.name);

  const sub: string[] = [];
  if (o.description) sub.push(String(o.description));
  if (o.denomination) sub.push(String(o.denomination));
  if (o.denomination_value != null) {
    sub.push(`${String(o.denomination_value)} ${String(o.denomination_unit ?? "")}`.trim());
  }
  if (o.color) sub.push(String(o.color));
  if (o.design_description && !o.description) sub.push(String(o.design_description));
  if (o.plate != null) sub.push(`plate ${String(o.plate)}`);
  if (o.position != null) sub.push(`pos ${String(o.position)}`);
  if (o.type) sub.push(`(${String(o.type)})`);
  if (o.score != null) sub.push(`score ${String(o.score)}`);
  if (o.confidence != null) sub.push(`confidence ${String(o.confidence)}`);

  const chips = Array.isArray(o.signals) ? o.signals.map(String).filter(Boolean) : undefined;

  return { lead: lead || undefined, sub: sub.join(", ") || undefined, chips };
}

// --------------------------------------------------------------------------- //
// Primitives
// --------------------------------------------------------------------------- //
function isScalar(v: unknown): boolean {
  return v === null || v === undefined || typeof v !== "object";
}

function isEmpty(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    v === "" ||
    (Array.isArray(v) && v.length === 0) ||
    (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0)
  );
}

function scalarText(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (Array.isArray(v)) return v.map((x) => String(x)).join(", ") || "—";
  if (typeof v === "object") {
    // Never dump JSON: summarize an object's scalar fields readably.
    const parts = Object.entries(v as Record<string, unknown>)
      .filter(([k, val]) => !FORBIDDEN_KEY.test(k) && val !== null && val !== undefined && typeof val !== "object")
      .map(([k, val]) => `${humanize(k)} ${String(val)}`);
    return parts.join(" · ") || "—";
  }
  return String(v);
}

function humanize(key: string): string {
  return key.replace(/_/g, " ");
}

export default NodeDetailPanel;
