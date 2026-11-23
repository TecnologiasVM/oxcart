/*
 * The path of a question, as one SVG with real text: vertical, 320 px wide, so its words are at their drawn
 * size from a 360 px screen up. Tinted boxes are what is on the page; outlined boxes are steps in the
 * backend; dashed boxes run for some questions only. The numbered list beside it says the same, and the
 * SVG's title and description say so to a screen reader.
 */
import type { ReactNode } from "react";

type Node = { name: string; sub: string[]; tech?: string };
export type PipelineNodes = Record<"q" | "s1" | "s2" | "cat" | "lit" | "ev" | "s3" | "s4" | "ans" | "s5" | "web", Node>;

const W = 320;
const GAP = 24; // the room an arrow takes between two boxes
const LINE = 20;
const STORE_W = 152;
const STORE_H = 100;

export default function Pipeline({ nodes, web, title, desc }: { nodes: PipelineNodes; web: boolean; title: string; desc: string }) {
  const out: ReactNode[] = [];
  let key = 0;
  const k = () => `p${key++}`;

  const head = (x: number, y: number) => out.push(<path key={k()} className="p-head" d={`M${x - 5} ${y - 8}h10l-5 8z`} />);
  const arrow = (y1: number, y2: number, x = W / 2) => {
    out.push(<path key={k()} className="p-edge" d={`M${x} ${y1}V${y2 - 7}`} />);
    head(x, y2);
  };

  // a box on the page: its name and a line or two under it
  const onPage = (y: number, node: Node, id: string) => {
    const h = 38 + LINE * node.sub.length;
    out.push(
      <g key={k()} className="p-node p-node--page" data-node={id}>
        <rect x="1" y={y} width={W - 2} height={h} />
        <text x="14" y={y + 24} className="p-name">{node.name}</text>
        {node.sub.map((line, i) => <text key={i} x="14" y={y + 44 + LINE * i} className="p-sub">{line}</text>)}
      </g>,
    );
    return y + h;
  };

  // a step in the backend: its number, its name, what it does, and what does it
  const step = (y: number, node: Node, n: number, id: string, some = false) => {
    const lines = node.sub.length + (node.tech ? 1 : 0);
    const h = 42 + LINE * lines;
    out.push(
      <g key={k()} className={`p-node${some ? " p-node--some" : ""}`} data-node={id}>
        <rect x="1" y={y} width={W - 2} height={h} />
        <rect className="p-num" x="12" y={y + 12} width="24" height="24" />
        <text x="24" y={y + 29} className="p-numtext" textAnchor="middle">{n}</text>
        <text x="48" y={y + 29} className="p-name">{node.name}</text>
        {node.sub.map((line, i) => <text key={i} x="48" y={y + 49 + LINE * i} className="p-sub">{line}</text>)}
        {node.tech && <text x="48" y={y + 49 + LINE * node.sub.length} className="p-mono">{node.tech}</text>}
      </g>,
    );
    return y + h;
  };

  // a store, half the width: its name and how it is searched at the top, what holds it at the foot
  const store = (x: number, y: number, node: Node, id: string) => {
    out.push(
      <g key={k()} className="p-node" data-node={id}>
        <rect x={x} y={y} width={STORE_W} height={STORE_H} />
        <text x={x + 12} y={y + 26} className="p-name">{node.name}</text>
        {node.sub.map((line, i) => <text key={i} x={x + 12} y={y + 46 + LINE * i} className="p-sub">{line}</text>)}
        {node.tech && <text x={x + 12} y={y + 86} className="p-mono">{node.tech}</text>}
      </g>,
    );
  };

  const left = 1 + STORE_W / 2;
  const right = W - 1 - STORE_W / 2;
  let y = onPage(0, nodes.q, "q");
  arrow(y, y + GAP);
  y = step(y + GAP, nodes.s1, 1, "s1", true);
  arrow(y, y + GAP);
  y = step(y + GAP, nodes.s2, 2, "s2");
  // one vector, two searches at the same time
  out.push(<path key={k()} className="p-edge" d={`M${W / 2} ${y}V${y + 11}H${left}V${y + 19}M${W / 2} ${y + 11}H${right}V${y + 19}`} />);
  head(left, y + GAP + 2);
  head(right, y + GAP + 2);
  store(1, y + GAP + 2, nodes.cat, "cat");
  store(W - 1 - STORE_W, y + GAP + 2, nodes.lit, "lit");
  y += GAP + 2 + STORE_H;
  out.push(<path key={k()} className="p-edge" d={`M${left} ${y}V${y + 11}H${right}V${y}M${W / 2} ${y + 11}V${y + 19}`} />);
  head(W / 2, y + GAP + 2);
  y = onPage(y + GAP + 2, nodes.ev, "ev");
  arrow(y, y + GAP);
  y = step(y + GAP, nodes.s3, 3, "s3");
  arrow(y, y + GAP);
  y = step(y + GAP, nodes.s4, 4, "s4");
  arrow(y, y + GAP);
  y = onPage(y + GAP, nodes.ans, "ans");
  if (web) {
    arrow(y, y + GAP);
    y = step(y + GAP, nodes.s5, 5, "s5", true);
    arrow(y, y + GAP);
    y = onPage(y + GAP, nodes.web, "web");
  }
  const H = y + 1;
  return (
    <svg className="pipe__svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-labelledby="pipe-t pipe-d" data-testid="pipeline">
      <title id="pipe-t">{title}</title>
      <desc id="pipe-d">{desc}</desc>
      {out}
    </svg>
  );
}
