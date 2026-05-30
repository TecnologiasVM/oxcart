"use client";

import { useEffect, useRef, useState } from "react";
import cytoscape, { Core, ElementDefinition, NodeSingular } from "cytoscape";
import {
  concentricLayout,
  cytoscapeStylesheet,
  defaultLayout,
  toCytoscapeElements,
} from "@/lib/cytoscape-style";
import type { GraphResponse } from "@/lib/types";

/*
 * Cytoscape core mounted in a client-only effect (Cytoscape reads `document`,
 * so it must never run during SSR). The container needs a measurable size.
 * cy.destroy() in cleanup keeps React 19 StrictMode double-invoke safe.
 */

type LayoutName = "cose" | "concentric";

export interface GraphViewProps {
  graph: GraphResponse | null;
  /** Called with the tapped node's id (or null when the background is tapped). */
  onSelectNode?: (nodeId: string | null) => void;
  /** Optional fixed height; defaults to filling the parent (parent must be sized). */
  height?: number | string;
}

export function GraphView({ graph, onSelectNode, height }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef<GraphViewProps["onSelectNode"]>(onSelectNode);
  const [layoutName, setLayoutName] = useState<LayoutName>("cose");

  // Keep the latest callback without re-initialising Cytoscape.
  useEffect(() => {
    onSelectRef.current = onSelectNode;
  }, [onSelectNode]);

  // Initialise the Cytoscape instance once.
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [] as ElementDefinition[],
      style: cytoscapeStylesheet,
      layout: { name: "preset" },
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      pixelRatio: "auto",
    });
    cyRef.current = cy;

    cy.on("tap", "node", (evt) => {
      const node = evt.target as NodeSingular;
      onSelectRef.current?.(node.id());
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) onSelectRef.current?.(null);
    });

    cy.on("mouseover", "node", (evt) => {
      (evt.target as NodeSingular).addClass("hovered");
      if (containerRef.current) containerRef.current.style.cursor = "pointer";
    });
    cy.on("mouseout", "node", (evt) => {
      (evt.target as NodeSingular).removeClass("hovered");
      if (containerRef.current) containerRef.current.style.cursor = "default";
    });

    // Test hook: expose the live cytoscape Core so E2E tests can target a node's
    // exact rendered pixel (cytoscape draws to a single <canvas>, which cannot be
    // DOM-targeted). No effect on the UI. Both the Explore graph and the Query
    // subgraph mount a GraphView; the last mounted wins __cy, which is fine since
    // each page only asserts against the graph currently visible on it.
    if (typeof window !== "undefined") {
      (window as unknown as Record<string, unknown>).__cy = cy;
    }

    return () => {
      cy.destroy();
      cyRef.current = null;
      if (typeof window !== "undefined") {
        const w = window as unknown as Record<string, unknown>;
        if (w.__cy === cy) delete w.__cy;
      }
    };
  }, []);

  // Sync elements whenever the graph prop changes.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const els = toCytoscapeElements(graph);
    cy.batch(() => {
      cy.elements().remove();
      cy.add(els);
    });

    if (els.length > 0) {
      const layout = layoutName === "concentric" ? concentricLayout : defaultLayout;
      const run = cy.layout(layout);
      // cose/concentric settle asynchronously; without an explicit fit the nodes
      // land outside the viewport and the canvas looks empty. Re-measure the
      // container (it may have just been sized by the grid) and frame the graph.
      run.one("layoutstop", () => {
        cy.resize();
        cy.fit(undefined, 36);
      });
      run.run();
    }
    // layoutName is intentionally part of the dependency list so a layout
    // toggle re-runs against the current elements.
  }, [graph, layoutName]);

  function relayout(name: LayoutName) {
    setLayoutName(name);
  }

  function fit() {
    cyRef.current?.fit(undefined, 36);
  }

  return (
    <div className="graph-frame" style={height ? { height } : undefined}>
      <div ref={containerRef} className="graph-canvas" />
      <div
        style={{
          position: "absolute",
          top: "var(--space-4)",
          right: "var(--space-4)",
          display: "flex",
          gap: "var(--space-2)",
          zIndex: 2,
        }}
      >
        <button
          type="button"
          className={`btn${layoutName === "cose" ? " btn--active" : ""}`}
          onClick={() => relayout("cose")}
        >
          Force
        </button>
        <button
          type="button"
          className={`btn${layoutName === "concentric" ? " btn--active" : ""}`}
          onClick={() => relayout("concentric")}
        >
          Rings
        </button>
        <button type="button" className="btn" onClick={fit}>
          Fit
        </button>
      </div>
    </div>
  );
}

export default GraphView;
