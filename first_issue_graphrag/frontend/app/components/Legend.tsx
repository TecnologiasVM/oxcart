/*
 * Static legend describing node glyphs. Pure presentational (server component).
 * Glyphs are tiny outline-only shapes (cream interior) echoing the canvas styling.
 */
import { PALETTE } from "@/lib/cytoscape-style";

interface LegendItem {
  label: string;
  shape: "circle" | "square" | "round" | "rect" | "dot" | "diamond";
  border: string;
  filled?: boolean;
}

const ITEMS: LegendItem[] = [
  { label: "Issue", shape: "circle", border: PALETTE.ink },
  { label: "Stamp", shape: "round", border: PALETTE.ink },
  { label: "Scott", shape: "circle", border: PALETTE.cobalt },
  { label: "Variety", shape: "dot", border: PALETTE.ink },
  { label: "Illustration", shape: "diamond", border: PALETTE.ink },
  { label: "Proof", shape: "round", border: PALETTE.ink },
  { label: "Plate", shape: "round", border: PALETTE.ink },
  { label: "Document", shape: "rect", border: PALETTE.ink },
  { label: "Chunk", shape: "dot", border: PALETTE.ink, filled: true },
];

export function Legend() {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "var(--space-4)",
        alignItems: "center",
      }}
    >
      {ITEMS.map((item) => (
        <span
          key={item.label}
          style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}
        >
          <Glyph item={item} />
          <span className="mono-label">{item.label}</span>
        </span>
      ))}
    </div>
  );
}

function Glyph({ item }: { item: LegendItem }) {
  const base: React.CSSProperties = {
    display: "inline-block",
    width: item.shape === "dot" ? 9 : 14,
    height: item.shape === "dot" ? 9 : item.shape === "rect" ? 10 : 14,
    backgroundColor: item.filled ? PALETTE.ink : PALETTE.paper,
    border: `1.5px solid ${item.border}`,
    boxSizing: "border-box",
  };

  switch (item.shape) {
    case "circle":
    case "dot":
      return <span style={{ ...base, borderRadius: "50%" }} />;
    case "round":
      return <span style={{ ...base, borderRadius: 2 }} />;
    case "diamond":
      return <span style={{ ...base, transform: "rotate(45deg)" }} />;
    case "rect":
    case "square":
    default:
      return <span style={base} />;
  }
}

export default Legend;
