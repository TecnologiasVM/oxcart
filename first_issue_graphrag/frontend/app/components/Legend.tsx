/*
 * Shape-grammar legend (server component). A bordered grid echoing the canvas
 * styling: outline-only glyphs, cream interiors, one dominant form. Cobalt marks
 * the Scott node; the filled dot marks a Chunk.
 */
import { PALETTE } from "@/lib/cytoscape-style";

interface LegendItem {
  label: string;
  role: string;
  shape: "circle" | "square" | "round" | "rect" | "dot" | "diamond";
  border: string;
  filled?: boolean;
}

const ITEMS: LegendItem[] = [
  { label: "Issue", role: "dominant centre", shape: "circle", border: PALETTE.ink },
  { label: "Stamp", role: "Mena catalogue", shape: "round", border: PALETTE.ink },
  { label: "Scott", role: "equivalent · cobalt", shape: "circle", border: PALETTE.cobalt },
  { label: "Variety", role: "sub-type", shape: "dot", border: PALETTE.ink },
  { label: "Illustration", role: "design / vignette", shape: "diamond", border: PALETTE.ink },
  { label: "Proof", role: "production", shape: "round", border: PALETTE.ink },
  { label: "Plate", role: "production", shape: "round", border: PALETTE.ink },
  { label: "Document", role: "literature", shape: "rect", border: PALETTE.ink },
  { label: "Chunk", role: "passage · filled", shape: "dot", border: PALETTE.ink, filled: true },
];

export function Legend() {
  return (
    <div className="legend">
      <div className="legend__head">
        <span className="mono">Shape grammar</span>
        <span className="mono mono-muted">one dominant form</span>
      </div>
      <div className="legend__grid">
        {ITEMS.map((item) => (
          <div className="legend__item" key={item.label}>
            <span className="legend__glyph">
              <Glyph item={item} />
            </span>
            <span>
              <span className="mono" style={{ display: "block" }}>
                {item.label}
              </span>
              <span className="legend__role">{item.role}</span>
            </span>
          </div>
        ))}
      </div>
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
