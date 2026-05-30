"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";

/*
 * Compact health strip. Shows Neo4j / Weaviate / graph-populated status as mono
 * labels. Status is conveyed by an explicit "OK"/"DOWN" word AND a filled/hollow
 * ink dot — never by color alone (a11y: color is not the only signal). Cobalt and
 * amber stay reserved for structural/focal accents, not semantic state.
 */
export function HealthBanner() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p className="mono-label" role="alert">
        Error: backend unreachable — {error}
      </p>
    );
  }

  if (!health) {
    return <p className="mono-label">Checking backend…</p>;
  }

  // `detail` is a dict (issue_id, service, optional counts/errors). Surface the
  // human-meaningful bits as a compact mono string.
  const detailText = formatDetail(health.detail);

  return (
    <div style={{ display: "flex", gap: "var(--space-6)", flexWrap: "wrap" }}>
      <StatusPill label="Neo4j" ok={health.neo4j} />
      <StatusPill label="Weaviate" ok={health.weaviate} />
      <StatusPill label="Graph" ok={health.graph_populated} />
      {detailText && <span className="mono-label">{detailText}</span>}
    </div>
  );
}

function formatDetail(detail?: Record<string, unknown>): string {
  if (!detail) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(detail)) {
    if (v === null || v === undefined) continue;
    parts.push(`${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`);
  }
  return parts.join(" · ");
}

function StatusPill({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="mono-label" style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}>
      <span
        aria-hidden
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          // Filled ink dot = OK; hollow (cream) ink-outlined dot = DOWN. The
          // OK/DOWN word below carries the same signal (color is not the only cue).
          backgroundColor: ok ? "var(--color-ink)" : "var(--color-paper)",
          border: "1.5px solid var(--color-ink)",
        }}
      />
      {label}: {ok ? "OK" : "DOWN"}
    </span>
  );
}

export default HealthBanner;
