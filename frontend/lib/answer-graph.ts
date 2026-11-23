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
import type { AskAnswer, Issue, WrittenAnswer } from "./ask";
import { actLine, sourceTitle } from "./evidence-text";
import type { Lang } from "./i18n";

export type GraphWords = {
  lang: Lang;
  page: string;
  catalogueCard: string;
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
  // what Enter or a click on it does: a cited source opens at Sources, a card found and not
  // cited opens at Cards and passages. A node without one takes no focus.
  target?: { tab: "sources"; n: number } | { tab: "found"; index: number };
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
const WITH_ANSWER = { W: 640, XA: 2, WA: 108, XS: 128, WS: 262, XC: 422, WC: 214 };
const FOUND_ONLY = { W: 640, XA: 0, WA: 0, XS: 4, WS: 290, XC: 330, WC: 306 };
const LH = 20;
const PAD = 10;
const MONO_CHAR = 7.4; // px per character of the 12 px mono face, to size stamp chips and cut ids
const CHIP_H = 28;
const GAP = 8;

/** The width of a line of text in the drawing's units, in the face its nodes are drawn in (15 px sans). */
export type Measure = (text: string) => number;
/** With nothing to measure in: wide on purpose, so that a line breaks too early rather than runs past its box. */
export const ESTIMATE: Measure = (text) => text.length * 9.5;
const INSET = 12; // a node's text starts this far inside its box, and keeps as much free on the right
const MARK_W = 30; // the source's mark stands before the text of a cited node

/** Break text into lines no wider than `room`, at spaces; a word wider than a whole line is broken inside. */
export function wrap(text: string, room: number, measure: Measure = ESTIMATE): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const longer = line ? `${line} ${word}` : word;
    if (measure(longer) <= room) {
      line = longer;
      continue;
    }
    if (line) lines.push(line);
    line = word;
    while (line.length > 1 && measure(line) > room) {
      let k = line.length - 1;
      while (k > 1 && measure(line.slice(0, k)) > room) k--;
      lines.push(line.slice(0, k));
      line = line.slice(k);
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

const cut = (text: string, chars: number) => (text.length > chars ? `${text.slice(0, Math.max(1, chars - 1))}…` : text);

function treeIssue(issue: Issue, lang: Lang, mark?: number): TreeIssue {
  const card = issue.card ?? {};
  return {
    mark,
    title: issue.title || issue.issue_id,
    id: issue.issue_id,
    printers: (card.printers ?? []).filter(Boolean),
    acts: (card.acts ?? []).map((act) => actLine(act, lang)),
    stamps: (card.stamps ?? []).map((s) => String(s.catalog_no ?? "")).filter(Boolean).slice(0, 24),
  };
}

export function answerGraph(evidence: AskAnswer, written: WrittenAnswer | undefined, words: GraphWords, measure: Measure = ESTIMATE): AnswerGraph {
  const ok = written?.state === "ok" && (written.sources ?? []).length > 0;
  const g = ok ? WITH_ANSWER : FOUND_ONLY;
  // the room for text inside a node: its width less the inset on both sides, and the mark when it has one
  const room = (w: number, mark?: number) => w - 2 * INSET - (mark !== undefined ? MARK_W : 0);
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
  const issueBlock = (issue: Issue, index: number, key: string, top: number, found: boolean, mark?: number) => {
    const item = treeIssue(issue, words.lang, mark);
    const kids: { rel: string; lines?: string[]; chips?: string[]; names: string[] }[] = [];
    for (const p of item.printers) kids.push({ rel: words.gPrinter, lines: wrap(p, room(g.WC), measure), names: [`${item.title}, ${words.gPrinter}: ${p}`] });
    for (const a of item.acts) kids.push({ rel: words.gAct, lines: wrap(a, room(g.WC), measure), names: [`${item.title}, ${words.gAct}: ${a}`] });
    if (item.stamps.length) kids.push({ rel: words.gStamps, chips: item.stamps, names: item.stamps.map((s) => `${item.title}, ${words.gStamp} ${s}`) });

    const titleLines = wrap(item.title, room(g.WS, mark), measure);
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
    const target = mark !== undefined ? { tab: "sources" as const, n: mark } : { tab: "found" as const, index };
    node({ key, kind: "issue", found, x: g.XS, y: sy, w: g.WS, lines: titleLines, mark, mono: cut(item.id, Math.floor((g.WS - 24) / MONO_CHAR)), name, target });
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
        const block = issueBlock(issue, source.index, `src-${source.n}`, y, false, source.n);
        mids.push(block.mid);
        tree.cited.push({ kind: "issue", issue: block.item });
        y += block.h + 22;
      } else {
        const title = sourceTitle(source, evidence, words);
        const lines = wrap(title, room(g.WS, source.n), measure);
        const h = node({ key: `src-${source.n}`, kind: "doc", found: false, x: g.XS, y, w: g.WS, lines, mark: source.n, name: `${words.source} ${source.n}: ${title}`, target: { tab: "sources", n: source.n } });
        mids.push(y + h / 2);
        tree.cited.push({ kind: "doc", mark: source.n, title });
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
      const block = issueBlock(issue, i, `found-${i}`, y, true, undefined);
      tree.found.push(block.item);
      y += block.h + 22;
    }
  }
  return { width: g.W, height: Math.ceil(y), nodes, edges, labels, rule, tree };
}
