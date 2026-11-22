/*
 * The graph of one answer, laid out from the response alone: the answer, the sources it
 * cites, each cited card's printers, acts and stamps; apart, what was found and not
 * cited. Only edges the response holds are drawn (answer -> cited source; card -> printer,
 * act, stamps). Nothing is fetched and no library lays it out: the page draws it as SVG, so
 * every node is an element with a name, and the box's proportions are known before
 * anything is drawn.
 *
 * The same content is also returned as a tree, for the list view (and for small screens).
 */
import type { AskAnswer, IssueCard, Issue, WrittenAnswer } from "./ask";

export type GraphWords = {
  gAnswer: string;
  gPrinter: string;
  gAct: string;
  gStamps: string;
  gStamp: string;
  gFound: string;
  gFoundOnly: string;
  source: string;
};

export type GNode = {
  key: string;
  kind: "answer" | "issue" | "doc" | "leaf" | "stamp";
  found: boolean; // found, not cited: drawn dashed
  x: number;
  y: number;
  w: number;
  h: number;
  lines: string[];
  mark?: number;
  mono?: string;
  name: string; // what a screen reader says for it
};
export type GEdge = { key: string; d: string; cites: boolean; found: boolean };
export type GLabel = { key: string; x: number; y: number; text: string; head: boolean };

export type TreeIssue = { mark?: number; title: string; id: string; printers: string[]; acts: string[]; stamps: string[] };
export type TreeSource = { kind: "issue"; issue: TreeIssue } | { kind: "doc"; mark: number; title: string };
export type Tree = { answer: boolean; cited: TreeSource[]; found: TreeIssue[]; foundLabel: string };

export type AnswerGraph = {
  width: number;
  height: number;
  nodes: GNode[];
  edges: GEdge[];
  labels: GLabel[];
  rule: { x1: number; x2: number; y: number } | null;
  tree: Tree;
};

// Geometry, for a panel about 640 px wide. With no answer the cards start at the left edge.
const WITH_ANSWER = { W: 640, XA: 2, WA: 108, XS: 128, WS: 262, XC: 422, WC: 214, kid: 25, title: 27, titlePlain: 32 };
const FOUND_ONLY = { W: 640, XA: 0, WA: 0, XS: 4, WS: 290, XC: 330, WC: 306, kid: 37, title: 36, titlePlain: 36 };
const LH = 20;
const PAD = 10;
const MONO_CHAR = 7.4; // px per character of the 12 px mono face, to size stamp chips and cut ids
const CHIP_H = 28;
const GAP = 8;

/** Break text into lines of at most `width` characters, at spaces. */
export function wrap(text: string, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (line && line.length + 1 + word.length > width) {
      lines.push(line);
      line = word;
    } else {
      line = line ? `${line} ${word}` : word;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

const cut = (text: string, chars: number) => (text.length > chars ? `${text.slice(0, Math.max(1, chars - 1))}…` : text);

/** An act as one line: its id, then its type and date. */
export function actLine(act: NonNullable<IssueCard["acts"]>[number]): string {
  const rest = [act.type, act.date].filter(Boolean).join(", ");
  return [act.id, rest ? `(${rest})` : ""].filter(Boolean).join(" ") || "–";
}

function treeIssue(issue: Issue, mark?: number): TreeIssue {
  const card = issue.card ?? {};
  return {
    mark,
    title: issue.title || issue.issue_id,
    id: issue.issue_id,
    printers: (card.printers ?? []).filter(Boolean),
    acts: (card.acts ?? []).map(actLine),
    stamps: (card.stamps ?? []).map((s) => String(s.catalog_no ?? "")).filter(Boolean).slice(0, 24),
  };
}

export function answerGraph(evidence: AskAnswer, written: WrittenAnswer | undefined, words: GraphWords): AnswerGraph {
  const ok = written?.state === "ok" && (written.sources ?? []).length > 0;
  const g = ok ? WITH_ANSWER : FOUND_ONLY;
  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const labels: GLabel[] = [];
  let y = 8;

  const node = (n: Omit<GNode, "h">): number => {
    const h = PAD * 2 + LH * n.lines.length + (n.mono ? LH - 2 : 0);
    nodes.push({ ...n, h });
    return h;
  };
  const edge = (key: string, x1: number, y1: number, x2: number, y2: number, cites: boolean, found: boolean) => {
    const mx = (x1 + x2) / 2;
    edges.push({ key, d: `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`, cites, found });
  };

  /** An issue with its printers, acts and stamps. Returns its height and the middle of its node. */
  const issueBlock = (issue: Issue, key: string, top: number, found: boolean, mark?: number) => {
    const item = treeIssue(issue, mark);
    const kids: { rel: string; lines?: string[]; chips?: string[]; names: string[] }[] = [];
    for (const p of item.printers) kids.push({ rel: words.gPrinter, lines: wrap(p, g.kid), names: [`${item.title}, ${words.gPrinter}: ${p}`] });
    for (const a of item.acts) kids.push({ rel: words.gAct, lines: wrap(a, g.kid), names: [`${item.title}, ${words.gAct}: ${a}`] });
    if (item.stamps.length) kids.push({ rel: words.gStamps, chips: item.stamps, names: item.stamps.map((s) => `${item.title}, ${words.gStamp} ${s}`) });

    const titleLines = wrap(item.title, mark ? g.title : g.titlePlain);
    const titleH = PAD * 2 + LH * titleLines.length + LH - 2;
    let ky = top;
    const kidMids: number[] = [];
    kids.forEach((kid, k) => {
      labels.push({ key: `${key}-rel-${k}`, x: g.XC, y: ky + 13, text: kid.rel, head: false });
      ky += 19;
      let h: number;
      if (kid.chips) {
        const longest = Math.max(...kid.chips.map((c) => c.length));
        const cw = Math.max(61, Math.ceil(longest * MONO_CHAR + 18));
        const per = Math.max(1, Math.floor((g.WC + GAP) / (cw + GAP)));
        kid.chips.forEach((chip, i) => {
          nodes.push({
            key: `${key}-stamp-${i}`, kind: "stamp", found, lines: [cut(chip, Math.floor((cw - 10) / MONO_CHAR))],
            x: g.XC + (i % per) * (cw + GAP), y: ky + Math.floor(i / per) * (CHIP_H + GAP), w: cw, h: CHIP_H, name: kid.names[i],
          });
        });
        h = Math.ceil(kid.chips.length / per) * (CHIP_H + GAP) - GAP;
      } else {
        h = node({ key: `${key}-kid-${k}`, kind: "leaf", found, x: g.XC, y: ky, w: g.WC, lines: kid.lines ?? [], name: kid.names[0] });
      }
      kidMids.push(ky + Math.min(h, 28) / 2);
      ky += h + 12;
    });
    const blockH = kids.length ? Math.max(titleH, ky - top - 12) : titleH;
    const sy = kids.length ? top + (blockH - titleH) / 2 : top;
    const name = mark
      ? `${words.source} ${mark}: ${item.title} (${item.id})`
      : `${found && ok ? words.gFound : words.gFoundOnly}: ${item.title} (${item.id})`;
    node({ key, kind: "issue", found, x: g.XS, y: sy, w: g.WS, lines: titleLines, mark, mono: cut(item.id, Math.floor((g.WS - 24) / MONO_CHAR)), name });
    const mid = sy + titleH / 2;
    kidMids.forEach((km, k) => edge(`${key}-e-${k}`, g.XS + g.WS, mid, g.XC - 6, km, false, found));
    return { h: blockH, mid, item };
  };

  const tree: Tree = { answer: ok, cited: [], found: [], foundLabel: ok ? words.gFound : words.gFoundOnly };
  const citedIssues = new Set<number>();

  if (ok) {
    const top = y;
    const mids: number[] = [];
    for (const source of written!.sources ?? []) {
      const issue = source.kind === "issue" ? evidence.issues[source.index] : undefined;
      if (issue) {
        citedIssues.add(source.index);
        const block = issueBlock(issue, `src-${source.n}`, y, false, source.n);
        mids.push(block.mid);
        tree.cited.push({ kind: "issue", issue: block.item });
        y += block.h + 22;
      } else {
        const lines = wrap(source.title, g.title);
        const h = node({ key: `src-${source.n}`, kind: "doc", found: false, x: g.XS, y, w: g.WS, lines, mark: source.n, name: `${words.source} ${source.n}: ${source.title}` });
        mids.push(y + h / 2);
        tree.cited.push({ kind: "doc", mark: source.n, title: source.title });
        y += h + 22;
      }
    }
    const answerH = PAD * 2 + LH;
    const ay = Math.max(4, (top + y - 22) / 2 - answerH / 2);
    node({ key: "answer", kind: "answer", found: false, x: g.XA, y: ay, w: g.WA, lines: [words.gAnswer], name: words.gAnswer });
    mids.forEach((m, i) => edge(`cites-${i}`, g.XA + g.WA, ay + answerH / 2, g.XS - 6, m, true, false));
  }

  const rest = evidence.issues.map((issue, i) => ({ issue, i })).filter(({ i }) => !citedIssues.has(i));
  let rule: AnswerGraph["rule"] = null;
  if (rest.length) {
    if (ok) {
      // what was found and not cited stands apart, under a rule, with nothing joining it to the answer
      y += 6;
      rule = { x1: g.XS, x2: g.W - 6, y };
      labels.push({ key: "found-head", x: g.XS, y: y + 24, text: words.gFound, head: true });
      y += 40;
    }
    for (const { issue, i } of rest) {
      const block = issueBlock(issue, `found-${i}`, y, true, undefined);
      tree.found.push(block.item);
      y += block.h + 22;
    }
  }
  return { width: g.W, height: Math.ceil(y), nodes, edges, labels, rule, tree };
}
