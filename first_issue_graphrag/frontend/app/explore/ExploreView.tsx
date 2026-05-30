"use client";

import { useEffect, useState } from "react";
import { getGraph, getStampGraph } from "@/lib/api";
import type { GraphResponse } from "@/lib/types";
import { GraphView } from "../components/GraphView";
import { NodeDetailPanel } from "../components/NodeDetailPanel";
import { Legend } from "../components/Legend";

/*
 * Interactive Explore surface:
 *   - loads the full issue graph (GET /api/graph)
 *   - optional per-stamp focus (GET /api/graph/stamp/{cno}) via the Mena scope row
 *   - selecting a node loads its detail in the side panel
 *
 * Mena scope codes (per prototype): 1=½ real, 2=2 reales, 3=4 reales, 4=1 peso.
 */
const STAMP_SCOPES: ReadonlyArray<{ cno: string; label: string }> = [
  { cno: "", label: "All" },
  { cno: "1", label: "½ real" },
  { cno: "2", label: "2 reales" },
  { cno: "3", label: "4 reales" },
  { cno: "4", label: "1 peso" },
];

export function ExploreView() {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [scope, setScope] = useState<string>("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // CLEAN tier by default for the full graph (score>=min_score, no COMPETING).
    const loader = scope ? getStampGraph(scope) : getGraph({ clean: true });

    loader
      .then((g) => {
        if (!cancelled) setGraph(g);
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
  }, [scope]);

  return (
    <div>
      {/* Toolbar: Mena scope (left) + retrieval tier readout (right) */}
      <div className="explore-toolbar">
        <div>
          <span className="mono mono-muted scope__caption">Mena scope</span>
          <div className="scope">
            {STAMP_SCOPES.map((s) => (
              <button
                key={s.cno || "all"}
                type="button"
                className={`btn${scope === s.cno ? " btn--active" : ""}`}
                onClick={() => {
                  setScope(s.cno);
                  setSelectedNodeId(null);
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="mono mono-muted scope__caption" style={{ textAlign: "right" }}>
            Tier
          </span>
          <div className="scope">
            <span className="chip chip--cobalt">Clean · score ≥ min</span>
            <span className="chip">No competing</span>
          </div>
        </div>
      </div>

      {error && (
        <p className="mono-label" role="alert">
          Error: {error}
        </p>
      )}

      {/* Graph + detail */}
      <div className="explore-grid">
        <div style={{ height: 600 }}>
          <GraphView graph={graph} onSelectNode={setSelectedNodeId} height="100%" />
          {loading && (
            <p className="mono-label" style={{ marginTop: "var(--space-2)" }}>
              Loading graph…
            </p>
          )}
        </div>
        <NodeDetailPanel nodeId={selectedNodeId} />
      </div>

      {/* Shape-grammar legend */}
      <Legend />
    </div>
  );
}

export default ExploreView;
