/*
 * StampGlyph — the encoded-stamp mark of the ink-cobalt-paper system.
 *
 * A reductionist postage stamp: perforation dot border + frame + central
 * vignette circle + a denomination numeral. Cream interior, ink outline; the
 * "cobalt" variant tints the frame (structural accent) and the "amber" variant
 * lights a single corner perforation (the focal accent — one per view).
 *
 * Pure typed SVG (no dangerouslySetInnerHTML). Decorative by default
 * (aria-hidden); pass `title` to expose it as an accessible image.
 */
export type StampVariant = "ink" | "cobalt" | "amber";

export interface StampGlyphProps {
  /** Short label drawn at the foot (e.g. a catalog no or year). */
  denom?: string;
  variant?: StampVariant;
  w?: number;
  h?: number;
  /** When set, the glyph is exposed as role="img" with this accessible name. */
  title?: string;
}

const PAD = 6;
const STEP = 8;
const R = 1.6;

function perfCenters(w: number, h: number): { x: number; y: number }[] {
  const innerW = w - PAD * 2;
  const innerH = h - PAD * 2;
  const cols = Math.max(1, Math.round(innerW / STEP));
  const rows = Math.max(1, Math.round(innerH / STEP));
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i <= cols; i++) {
    const x = PAD + (innerW * i) / cols;
    pts.push({ x, y: PAD });
    pts.push({ x, y: h - PAD });
  }
  for (let j = 1; j < rows; j++) {
    const y = PAD + (innerH * j) / rows;
    pts.push({ x: PAD, y });
    pts.push({ x: w - PAD, y });
  }
  return pts;
}

export function StampGlyph({ denom = "", variant = "ink", w = 70, h = 88, title }: StampGlyphProps) {
  const innerW = w - PAD * 2;
  const innerH = h - PAD * 2;
  const cx = w / 2;
  const cy = h / 2 - 4;
  const vr = Math.min(innerW, innerH) * 0.26;
  const frameStroke = variant === "cobalt" ? "var(--color-cobalt)" : "var(--color-ink)";
  const a11y = title
    ? ({ role: "img", "aria-label": title } as const)
    : ({ "aria-hidden": true } as const);

  return (
    <svg className="stamp" width={w} height={h} viewBox={`0 0 ${w} ${h}`} {...a11y}>
      {title ? <title>{title}</title> : null}
      <g className="stamp__perf">
        {perfCenters(w, h).map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={R} />
        ))}
      </g>
      {variant === "amber" ? (
        <circle className="stamp__perf stamp__perf--amber" cx={w - PAD} cy={PAD} r={R + 0.8} />
      ) : null}
      <rect
        className="stamp__frame"
        x={PAD + 3}
        y={PAD + 3}
        width={innerW - 6}
        height={innerH - 6}
        strokeWidth={1.6}
        stroke={frameStroke}
      />
      <circle className="stamp__vignette" cx={cx} cy={cy} r={vr} strokeWidth={1.3} />
      <text className="stamp__num" x={cx} y={h - PAD - 7} textAnchor="middle" fontSize={11}>
        {denom}
      </text>
    </svg>
  );
}

export default StampGlyph;
