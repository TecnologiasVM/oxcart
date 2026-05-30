"use client";

import { useEffect, useState } from "react";
import { getOverview } from "@/lib/api";
import type { OverviewResponse } from "@/lib/types";
import { issueYear, displayDenom } from "@/lib/format";

/*
 * Client panel rendering GET /api/overview: issue header, totals as a mono
 * stat row, the stamp roster as outline cards, and a flat bar for the
 * score distribution (ink bars on cream, one amber bar marks the mode).
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

  return (
    <section>
      <p className="mono-label">{data.issue.country ?? "Costa Rica"} · {issueYear(data.issue.issue_dates)}</p>
      <h2 style={{ marginTop: "var(--space-2)" }}>{data.issue.title ?? "First Issue"}</h2>

      {/* Totals */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-8)",
          marginTop: "var(--space-6)",
        }}
      >
        {Object.entries(data.totals ?? {}).map(([key, value]) => (
          <div key={key}>
            <div className="serif-display" style={{ fontSize: "2.2rem" }}>
              {value}
            </div>
            <div className="mono-label">{key.replace(/_/g, " ")}</div>
          </div>
        ))}
      </div>

      {typeof data.issue.scott_note === "string" && (
        <p
          style={{
            marginTop: "var(--space-3)",
            fontSize: 13,
            color: "var(--color-ink-muted)",
            maxWidth: "78ch",
          }}
        >
          {data.issue.scott_note}
        </p>
      )}

      <hr className="rule-faint" />

      {/* Stamp roster */}
      <p className="mono-label">Mena roster</p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
          gap: "var(--space-4)",
          marginTop: "var(--space-3)",
        }}
      >
        {(data.stamps ?? []).map((s) => (
          <div className="surface" key={s.catalog_no}>
            <p className="mono-label">No. {s.catalog_no}</p>
            <h3 className="serif-display" style={{ fontSize: "1.3rem", marginTop: "var(--space-2)" }}>
              {displayDenom(s.catalog_no, s.denomination_value, s.denomination_unit) || "—"}
            </h3>
            <dl style={{ margin: "var(--space-3) 0 0", display: "grid", gap: "var(--space-1)" }}>
              {s.color && <Row k="Color" v={s.color} />}
              {s.perforation && <Row k="Perf" v={s.perforation} />}
              {s.quantity_reported != null && <Row k="Qty" v={String(s.quantity_reported)} />}
              {s.equivalent_scott && s.equivalent_scott.length > 0 && (
                <Row k="Scott" v={s.equivalent_scott.join(", ")} />
              )}
            </dl>
          </div>
        ))}
      </div>

      {/* Score distribution */}
      {data.score_distribution && data.score_distribution.length > 0 && (
        <>
          <hr className="rule-faint" />
          <p className="mono-label">Link-score distribution</p>
          <ScoreBars buckets={data.score_distribution} />
        </>
      )}
    </section>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-3)" }}>
      <span className="mono-label" style={{ minWidth: 56 }}>
        {k}
      </span>
      <span style={{ fontSize: 14 }}>{v}</span>
    </div>
  );
}

function ScoreBars({ buckets }: { buckets: NonNullable<OverviewResponse["score_distribution"]> }) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const modeIdx = buckets.reduce<number>(
    (best, b, i, arr) => (b.count > arr[best].count ? i : best),
    0,
  );

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--space-2)", height: 120, marginTop: "var(--space-3)" }}>
      {buckets.map((b, i) => {
        const isMode = i === modeIdx;
        const h = Math.round((b.count / max) * 100);
        return (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--space-1)" }}>
            <div
              title={`${b.label ?? b.bucket ?? i}: ${b.count}`}
              style={{
                width: 28,
                height: `${h}%`,
                minHeight: 2,
                // Ink bars on cream; the modal bucket is marked amber (the single focal accent).
                backgroundColor: isMode ? "var(--color-amber)" : "var(--color-ink)",
              }}
            />
            <span className="mono-label">{b.label ?? b.bucket ?? i}</span>
          </div>
        );
      })}
    </div>
  );
}

export default OverviewPanel;
