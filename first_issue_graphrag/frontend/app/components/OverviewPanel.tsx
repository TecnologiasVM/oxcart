"use client";

import { useEffect, useState } from "react";
import { getOverview } from "@/lib/api";
import type { OverviewResponse, OverviewStamp } from "@/lib/types";
import { displayDenom } from "@/lib/format";
import { StampGlyph, type StampVariant } from "./StampGlyph";

/*
 * Landing overview (lean editorial — NO charts, owner decision).
 * Renders GET /api/overview as: a mono stat row (.stats), the Scott-count note,
 * and the Mena roster as outline cards with the encoded stamp glyph. The roster
 * marks the type stamp (No.1) cobalt and the rarest printing amber (the single
 * focal accent), echoing the redesign mockup without a dashboard.
 */
export function OverviewPanel() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getOverview()
      .then((d) => {
        if (!cancelled) setData(d);
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
  }, []);

  if (loading) return <p className="mono-label">Loading overview…</p>;
  if (error)
    return (
      <p className="mono-label" role="alert">
        Error: {error}
      </p>
    );
  if (!data) return null;

  const totals = data.totals ?? {};
  const stamps = data.stamps ?? [];
  const rarestNo = rarestStampNo(stamps);

  return (
    <section>
      {/* Mono stat row (the only numeric summary — no charts) */}
      <div className="stats">
        {Object.entries(totals).map(([key, value]) => {
          const mark = key === "scott_stamps";
          return (
            <div className="stat" key={key}>
              <div className={`stat__num serif-display${mark ? " stat__num--mark" : ""}`}>{value}</div>
              <span className={`mono${mark ? " cobalt" : " mono-muted"}`}>{key.replace(/_/g, " ")}</span>
            </div>
          );
        })}
      </div>

      {typeof data.issue.scott_note === "string" && (
        <p
          style={{
            marginTop: "var(--space-4)",
            fontSize: 13,
            color: "var(--color-ink-muted)",
            maxWidth: "78ch",
          }}
        >
          {data.issue.scott_note}
        </p>
      )}

      {/* Mena roster as encoded-stamp cards */}
      <div className="section__head" style={{ marginTop: "var(--space-10)" }}>
        <div>
          <span className="mono mono-muted">Mena roster · 2018 catalogue</span>
          <h2 className="serif-h2" style={{ marginTop: "var(--space-2)" }}>
            The roster.
          </h2>
        </div>
      </div>

      <div className="roster">
        {stamps.map((s) => {
          const isRare = s.catalog_no === rarestNo;
          const variant: StampVariant = isRare ? "amber" : s.catalog_no === "1" ? "cobalt" : "ink";
          return (
            <div className={`card${isRare ? " card--rare" : ""}`} key={s.catalog_no}>
              <div className="card__glyph">
                <StampGlyph denom={s.catalog_no} variant={variant} w={70} h={88} />
              </div>
              <div className="card__no">
                <span className="mono mono-muted">No. {s.catalog_no}</span>
                {isRare && <span className="tag-rare">Rarest</span>}
              </div>
              <div className="card__denom">
                {displayDenom(s.catalog_no, s.denomination_value, s.denomination_unit) || "—"}
              </div>
              <dl className="card__dl">
                {s.color && (
                  <>
                    <dt>Color</dt>
                    <dd>{s.color}</dd>
                  </>
                )}
                {s.perforation && (
                  <>
                    <dt>Perf</dt>
                    <dd>{s.perforation}</dd>
                  </>
                )}
                {s.quantity_reported != null && (
                  <>
                    <dt>Qty</dt>
                    <dd>{formatQty(s.quantity_reported)}</dd>
                  </>
                )}
                {scottText(s) && (
                  <>
                    <dt>Scott</dt>
                    <dd>{scottText(s)}</dd>
                  </>
                )}
              </dl>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Scott numbers from the backend `scott` field (list of {scott_number}). */
function scottText(s: OverviewStamp): string {
  return (s.scott ?? [])
    .map((x) => x?.scott_number)
    .filter(Boolean)
    .join(", ");
}

/** Catalog_no of the lowest reported printing (the rarest), or null. */
function rarestStampNo(stamps: OverviewStamp[]): string | null {
  let best: { no: string; qty: number } | null = null;
  for (const s of stamps) {
    const qty = Number(s.quantity_reported);
    if (!Number.isFinite(qty)) continue;
    if (best === null || qty < best.qty) best = { no: s.catalog_no, qty };
  }
  return best?.no ?? null;
}

function formatQty(value: number | string): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("en-US") : String(value);
}

export default OverviewPanel;
