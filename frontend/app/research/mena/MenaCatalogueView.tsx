"use client";

import { useEffect, useMemo, useState } from "react";
import { getSurfaceMail } from "@/lib/api";
import type { SurfaceMailResponse } from "@/lib/types";
import { MenaIssueDetail } from "./MenaIssueDetail";

/*
 * Mena Surface-Mail navigator: a three-pane explorer.
 *   YEAR pane  -> ISSUE pane -> DETAIL pane.
 * The index (years -> issues, with stamp counts) loads once and is cheap. Year
 * and issue rows are real <button>s (focusable, keyboard-operable) with
 * aria-current marking the active selection. The detail pane is aria-live so a
 * screen reader announces the loaded issue.
 */
export function MenaCatalogueView() {
  const [index, setIndex] = useState<SurfaceMailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState<string | null>(null);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSurfaceMail()
      .then((d) => {
        if (cancelled) return;
        setIndex(d);
        if (d.years.length > 0) setSelectedYear(d.years[0].year);
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

  const issues = useMemo(() => {
    if (!index || !selectedYear) return [];
    return index.years.find((y) => y.year === selectedYear)?.issues ?? [];
  }, [index, selectedYear]);

  if (loading) return <p className="mono-label">Loading the Surface-Mail index…</p>;
  if (error)
    return (
      <p className="mono-label" role="alert">
        Error: {error}
      </p>
    );
  if (!index) return null;

  return (
    <>
      <p className="mono mono-muted" style={{ marginBottom: "var(--space-2)" }}>
        {index.total_issues} catalogue entries · {index.section} · {index.years.length} years
      </p>

      <div className="mena-layout">
        {/* YEAR pane */}
        <nav className="mena-pane" aria-label="Years">
          <div className="mena-pane__head">
            <span className="mono">Year</span>
          </div>
          <div className="mena-pane__scroll">
            {index.years.map((y) => {
              const active = y.year === selectedYear;
              return (
                <button
                  key={y.year}
                  type="button"
                  className={`mena-row${active ? " mena-row--active" : ""}`}
                  aria-current={active ? "true" : undefined}
                  onClick={() => {
                    setSelectedYear(y.year);
                    setSelectedIssueId(null);
                  }}
                >
                  <span className="mena-year">{y.year}</span>
                  <span className="mena-row__meta">{y.count}</span>
                </button>
              );
            })}
          </div>
        </nav>

        {/* ISSUE pane */}
        <nav className="mena-pane" aria-label={`Issues in ${selectedYear ?? ""}`}>
          <div className="mena-pane__head">
            <span className="mono">Issue</span>
            {selectedYear && <span className="mono mono-muted">{selectedYear}</span>}
          </div>
          <div className="mena-pane__scroll">
            {issues.length === 0 ? (
              <p className="mena-empty">Select a year to list its issues.</p>
            ) : (
              issues.map((it) => {
                const active = it.issue_id === selectedIssueId;
                return (
                  <button
                    key={it.issue_id}
                    type="button"
                    className={`mena-row${active ? " mena-row--active" : ""}`}
                    aria-current={active ? "true" : undefined}
                    onClick={() => setSelectedIssueId(it.issue_id)}
                  >
                    <span>{it.title || it.issue_id}</span>
                    <span className="mena-row__meta">
                      {it.n_stamps} {it.n_stamps === 1 ? "stamp" : "stamps"}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </nav>

        {/* DETAIL pane */}
        <section className="mena-pane mena-pane--detail" aria-live="polite" aria-label="Issue detail">
          <MenaIssueDetail issueId={selectedIssueId} />
        </section>
      </div>
    </>
  );
}

export default MenaCatalogueView;
