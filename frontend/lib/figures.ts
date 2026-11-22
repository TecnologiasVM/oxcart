/*
 * Pictures from the figures host: the figures of the cited pages, and the first screen's plate.
 *
 * The page builds every picture's address itself, from one build setting and an id:
 *
 *   NEXT_PUBLIC_FIGURES_BASE + "/" + <id> + ".png"
 *
 * The setting is used only when it is an https address (or http on this machine, for tests);
 * unset or anything else, no picture is drawn and the page is what it was without them. An id
 * is used only when it is 20 lower-case hex characters, so nothing a response or a stored turn
 * holds, and nothing a model wrote, can become an address. The backend names a figure by its id,
 * its pixel size and its class (backend/app/figures.py); a stored turn keeps those, not an address.
 *
 * The first screen's plate is a list read at run time from the same host (first-screen.json), so
 * the set can be changed there without a build and nothing of it is in the repository.
 */
import type { AnswerSource, Passage } from "./ask";

export type FigureClass = "A" | "B";
/** A figure as the backend names it: its public id (a digest), its pixel size, its class (A a stamp, B a cover or a postal marking). */
export type Figure = { id: string; width: number; height: number; class: FigureClass };
/** One picture of the first screen's plate. */
export type PlateItem = { digest: string; width: number; height: number };

const BASE_RULE = /^(?:https:\/\/[A-Za-z0-9.-]+(?::\d+)?|http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?)(?:\/[A-Za-z0-9._~/-]*)?$/;
const ID_RULE = /^[0-9a-f]{20}$/;
const MAX_SIDE = 10_000;

/** The figures host, when the build names a usable one; "" otherwise (pictures off). */
export function figuresBase(raw: string | undefined): string {
  const base = (raw ?? "").trim();
  return BASE_RULE.test(base) ? base.replace(/\/+$/, "") : "";
}

export const FIGURES_BASE = figuresBase(process.env.NEXT_PUBLIC_FIGURES_BASE);

/** The address of a picture, or null when pictures are off or the id is not one. */
export function figureSrc(id: string): string | null {
  return FIGURES_BASE && ID_RULE.test(id) ? `${FIGURES_BASE}/${id}.png` : null;
}

const side = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v) && v > 0 && v <= MAX_SIDE;

/** The figures of a passage that can be drawn: well formed, each once. Anything else is left out. */
export function figuresOf(passage: Passage | undefined): Figure[] {
  const list = (passage as { figures?: unknown } | undefined)?.figures;
  if (!FIGURES_BASE || !Array.isArray(list)) return [];
  const out: Figure[] = [];
  for (const f of list as Partial<Figure>[]) {
    if (!f || typeof f.id !== "string" || !ID_RULE.test(f.id) || !side(f.width) || !side(f.height)) continue;
    if (f.class !== "A" && f.class !== "B") continue;
    if (out.some((o) => o.id === f.id)) continue;
    out.push({ id: f.id, width: f.width, height: f.height, class: f.class });
  }
  return out;
}

/** What a response's passage keeps of its figures: the well-formed ones, whatever the build's setting. */
export function keepFigures(list: unknown): Figure[] | undefined {
  if (!Array.isArray(list)) return undefined;
  const kept = (list as Partial<Figure>[]).filter(
    (f): f is Figure => Boolean(f) && typeof f.id === "string" && ID_RULE.test(f.id) && side(f.width) && side(f.height) && (f.class === "A" || f.class === "B"),
  ).map((f) => ({ id: f.id, width: f.width, height: f.height, class: f.class }));
  return kept.length ? kept : undefined;
}

/**
 * The size a picture is drawn at: its own, or reduced to `cap` px tall. Never enlarged. The width
 * is rounded down, so at the picture's own proportions (which the page sets, see `ratio`) its
 * height never passes the cap.
 */
export function fit(width: number, height: number, cap?: number): { width: number; height: number } {
  if (cap && height > cap) return { width: Math.max(1, Math.floor((width * cap) / height)), height: cap };
  return { width, height };
}

/** The picture's own proportions, set before its file arrives: the box it holds is the box it keeps. */
export const ratio = (f: { width: number; height: number }) => ({ aspectRatio: `${f.width} / ${f.height}` });

/** One cited page that carries figures: the source mark it is cited by, the passage it is, its figures. */
export type FigureGroup = { n: number; index: number; doc: string; page: string; figures: Figure[] };

/**
 * The figures of the pages an answer cites, one group per cited page, in the order of the marks.
 * Two cited passages of the same page are one group, under the first mark. `pages` is how many
 * pages are cited at all (the line "2 of the 3 cited pages carry figures").
 */
export function citedFigures(sources: AnswerSource[], passages: Passage[]): { groups: FigureGroup[]; pages: number; count: number } {
  const pages = new Set<string>();
  const byPage = new Map<string, FigureGroup>();
  for (const source of [...sources].sort((a, b) => a.n - b.n)) {
    const p = source.kind === "passage" ? passages[source.index] : undefined;
    if (!p) continue;
    const key = `${p.doc_id ?? "?"}\u0000${p.page ?? "?"}`;
    pages.add(key);
    const figs = figuresOf(p);
    const group = byPage.get(key);
    if (group) group.figures.push(...figs.filter((f) => !group.figures.some((g) => g.id === f.id)));
    else if (figs.length) byPage.set(key, { n: source.n, index: source.index, doc: (p.doc_id ?? "?").trim(), page: String(p.page ?? "?"), figures: figs });
  }
  const groups = [...byPage.values()].sort((a, b) => a.n - b.n);
  return { groups, pages: pages.size, count: groups.reduce((sum, g) => sum + g.figures.length, 0) };
}

// ---------------------------------------------------------------- the first screen's plate

export const PLATE_MAX = 28; // the most cells the plate shows, on the widest screen
export const PLATE_WAIT_MS = 2000; // a list that has not arrived by then is not drawn: the first screen does not change late

/** The plate's list as read: every entry well formed, or nothing (a malformed file draws nothing). */
export function readPlate(value: unknown): PlateItem[] {
  if (!Array.isArray(value) || value.length === 0) return [];
  const items: PlateItem[] = [];
  for (const v of value as Partial<PlateItem>[]) {
    if (!v || typeof v.digest !== "string" || !ID_RULE.test(v.digest) || !side(v.width) || !side(v.height)) return [];
    items.push({ digest: v.digest, width: v.width, height: v.height });
  }
  return items.slice(0, PLATE_MAX);
}

let plate: Promise<PlateItem[]> | null = null;

/** The first screen's list, read once per page: [] when pictures are off, or the file is missing, malformed or slow. */
export function plateList(): Promise<PlateItem[]> {
  if (plate) return plate;
  if (!FIGURES_BASE) return (plate = Promise.resolve([]));
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PLATE_WAIT_MS);
  plate = fetch(`${FIGURES_BASE}/first-screen.json`, { signal: controller.signal, credentials: "omit" })
    .then((res) => (res.ok ? res.json() : []))
    .then(readPlate)
    .catch(() => [])
    .finally(() => clearTimeout(timer));
  return plate;
}
