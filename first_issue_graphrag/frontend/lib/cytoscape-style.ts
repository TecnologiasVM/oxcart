/**
 * Cytoscape stylesheet + layout for the First Issue KG graph.
 *
 * Design system: ink-cobalt-paper v2.0 (editorial, reductionist, FLAT).
 * The graph IS the subject. Nodes are ink + cream; cobalt is reserved for the
 * one structural node type (ScottStamp); amber appears ONLY on selection/hover.
 * No gradients, no depth shadows, no 3D, no texture.
 *
 *   Issue        large circle, ink 3px border, cream fill (DOMINANT)
 *   Stamp        square, ink 2px border, cream fill
 *   ScottStamp   circle, COBALT 2px border, cream fill
 *   Variety      small ink circle
 *   Illustration ink round-rect (diamond-leaning)
 *   Proof        ink round-rect
 *   Plate        ink round-rect
 *   Document     rectangle, ink 1.5px border, cream fill
 *   Chunk        small ink-filled dot
 *   selected/hover -> AMBER border + subtle amber halo
 *   edges        thin ink ~1.5px; MENTIONS / MENTIONS_STAMP lighter + dashed
 *   captions     mono, small, ink; canvas bg = paper
 */

import type { ElementDefinition, LayoutOptions, StylesheetStyle } from "cytoscape";
import type { GraphResponse, PropBag } from "./types";

// Strict palette (single source of truth — keep in sync with globals.css tokens)
export const PALETTE = {
  paper: "#F4EFE5",
  ink: "#0A0A0A",
  cobalt: "#1E3A6B",
  amber: "#C4923A",
  // Derived, lighter ink for de-emphasized mention edges (still "ink", not a new hue)
  inkMuted: "#6B6B6B",
} as const;

export const MONO_FONT =
  '"JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace';

export const cytoscapeStylesheet: StylesheetStyle[] = [
  // ----- Base node: cream fill, ink outline, mono ink caption -----
  {
    selector: "node",
    style: {
      "background-color": PALETTE.paper,
      "border-color": PALETTE.ink,
      "border-width": 2,
      label: "data(label)",
      color: PALETTE.ink,
      "font-family": MONO_FONT,
      "font-size": 9,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 4,
      "text-wrap": "wrap",
      "text-max-width": "90px",
      "min-zoomed-font-size": 6,
      width: 28,
      height: 28,
    },
  },

  // ----- Issue: DOMINANT large circle, ink 3px border, cream fill -----
  {
    selector: 'node[type = "Issue"]',
    style: {
      shape: "ellipse",
      width: 84,
      height: 84,
      "border-width": 3,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
      "font-size": 11,
      "font-weight": 600,
      "text-max-width": "120px",
    },
  },

  // ----- Stamp: square, ink 2px border, cream fill -----
  {
    selector: 'node[type = "Stamp"]',
    style: {
      shape: "round-rectangle",
      "corner-radius": "2",
      width: 44,
      height: 44,
      "border-width": 2,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
    },
  },

  // ----- ScottStamp: circle, COBALT 2px border (the ONLY cobalt node) -----
  {
    selector: 'node[type = "ScottStamp"]',
    style: {
      shape: "ellipse",
      width: 38,
      height: 38,
      "border-width": 2,
      "border-color": PALETTE.cobalt,
      "background-color": PALETTE.paper,
    },
  },

  // ----- Variety: small ink circle -----
  {
    selector: 'node[type = "Variety"]',
    style: {
      shape: "ellipse",
      width: 20,
      height: 20,
      "border-width": 1.5,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
      "font-size": 8,
    },
  },

  // ----- Illustration: ink round-rect (diamond-leaning) -----
  {
    selector: 'node[type = "Illustration"]',
    style: {
      shape: "diamond",
      width: 30,
      height: 30,
      "border-width": 1.5,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
    },
  },

  // ----- Proof / Plate: ink round-rect -----
  {
    selector: 'node[type = "Proof"], node[type = "Plate"]',
    style: {
      shape: "round-rectangle",
      "corner-radius": "6",
      width: 32,
      height: 24,
      "border-width": 1.5,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
      "font-size": 8,
    },
  },

  // ----- Document: rectangle, ink 1.5px border, cream fill -----
  {
    selector: 'node[type = "Document"]',
    style: {
      shape: "rectangle",
      width: 54,
      height: 32,
      "border-width": 1.5,
      "border-color": PALETTE.ink,
      "background-color": PALETTE.paper,
      "font-size": 8,
    },
  },

  // ----- Chunk: small ink-FILLED dot -----
  {
    selector: 'node[type = "Chunk"]',
    style: {
      shape: "ellipse",
      width: 12,
      height: 12,
      "border-width": 0,
      "background-color": PALETTE.ink,
      "font-size": 7,
      "text-margin-y": 2,
    },
  },

  // ----- Edges: thin ink ~1.5px -----
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": PALETTE.ink,
      "curve-style": "bezier",
      "target-arrow-shape": "triangle",
      "target-arrow-color": PALETTE.ink,
      "arrow-scale": 0.7,
      "font-family": MONO_FONT,
      "font-size": 7,
      color: PALETTE.inkMuted,
    },
  },

  // ----- MENTIONS / MENTIONS_STAMP: lighter + dashed -----
  {
    selector: 'edge[type = "MENTIONS"], edge[type = "MENTIONS_STAMP"]',
    style: {
      width: 1,
      "line-color": PALETTE.inkMuted,
      "line-style": "dashed",
      "target-arrow-color": PALETTE.inkMuted,
      "target-arrow-shape": "none",
    },
  },

  // ----- Selected / hover: AMBER border + subtle amber halo -----
  {
    selector: "node.selected, node:selected",
    style: {
      "border-color": PALETTE.amber,
      "border-width": 3,
      // "halo" via overlay (flat, no drop-shadow) — Cytoscape overlay is the
      // closest flat-compatible glow.
      "overlay-color": PALETTE.amber,
      "overlay-opacity": 0.12,
      "overlay-padding": 8,
      color: PALETTE.ink,
    },
  },
  {
    selector: "node.hovered",
    style: {
      "border-color": PALETTE.amber,
      "overlay-color": PALETTE.amber,
      "overlay-opacity": 0.08,
      "overlay-padding": 6,
    },
  },

  // De-emphasize everything not connected to the selected node
  {
    selector: "node.dimmed",
    style: { opacity: 0.28 },
  },
  {
    selector: "edge.dimmed",
    style: { opacity: 0.15 },
  },
  {
    selector: "edge.incident",
    style: {
      "line-color": PALETTE.amber,
      "target-arrow-color": PALETTE.amber,
      width: 1.8,
      opacity: 1,
    },
  },
];

/** Concentric layout keeps the Issue dominant at the center. */
export const cytoscapeLayout: LayoutOptions = {
  name: "concentric",
  fit: true,
  padding: 36,
  startAngle: (3 / 2) * Math.PI,
  minNodeSpacing: 28,
  avoidOverlap: true,
  // Issue at the core; structural catalog nodes next; lexical layer outermost.
  concentric: (node: cytoscape.NodeSingular) => concentricLevel(node.data("type")),
  levelWidth: () => 1,
} as LayoutOptions;

/** Named alias used by GraphView for the "Rings" layout toggle. */
export const concentricLayout: LayoutOptions = cytoscapeLayout;

/** Force-directed layout used as the default ("Force") in GraphView. */
export const defaultLayout: LayoutOptions = {
  name: "cose",
  fit: true,
  padding: 36,
  animate: false,
  nodeRepulsion: 8000,
  idealEdgeLength: 80,
  nestingFactor: 1.1,
} as LayoutOptions;

/**
 * Map a GraphResponse ({nodes, edges}) to Cytoscape element definitions.
 * Each Neo4j node becomes { data: { id, type, label, ...props } } and each edge
 * { data: { id, source, target, type } }. Embedding/vector props are already
 * stripped upstream (api.stripVectors); this mapping does not reintroduce them.
 */
export function toCytoscapeElements(graph: GraphResponse | null): ElementDefinition[] {
  if (!graph) return [];
  const nodes: ElementDefinition[] = (graph.nodes ?? []).map((n) => {
    // Backend serializes the prop bag under `data`; older payloads used `props`.
    // Read either so extra props (e.g. Mena Scott detail) survive. Rendering only
    // needs id/type/label, which are always set explicitly below.
    const extra = (n as { props?: PropBag; data?: PropBag }).data ?? (n as { props?: PropBag }).props ?? {};
    return { data: { id: n.id, type: n.type, label: n.label, ...extra } };
  });
  const edges: ElementDefinition[] = (graph.edges ?? []).map((e) => ({
    data: { id: e.id, source: e.source, target: e.target, type: e.type },
  }));
  return [...nodes, ...edges];
}

function concentricLevel(type: string): number {
  switch (type) {
    case "Issue":
      return 6;
    case "Stamp":
      return 5;
    case "ScottStamp":
      return 5;
    case "Variety":
    case "Illustration":
    case "Proof":
    case "Plate":
      return 4;
    case "Document":
      return 2;
    case "Chunk":
      return 1;
    default:
      return 3;
  }
}

// Type-only import to satisfy the concentric callback signature without a runtime dep.
import type cytoscape from "cytoscape";
