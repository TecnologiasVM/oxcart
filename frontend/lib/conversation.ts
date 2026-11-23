/*
 * The conversations as this browser keeps them. Nothing of them is sent to be stored
 * anywhere: local storage is their only home, and the page works the same when storage is
 * blocked or full (what is not kept lives as long as the page).
 *
 * Shape on disk (key `oxcart-conversations`):
 *
 *   { version: 2, current: "<id>", conversations: [{ id, started, turns: [...] }] }
 *
 * `current` is the conversation that opens with the page; it may name one that has no turn
 * yet (a new conversation), and then the page opens on its first screen. The first version
 * (key `oxcart-chat-v1`: a bare list of turns, newest first) is read once and carried over.
 */
import type { AskAnswer, ModelCall, ThreadTurn, WrittenAnswer } from "./ask";
import type { WebPart } from "./web";

export const STORE_KEY = "oxcart-conversations";
export const OLD_KEY = "oxcart-chat-v1";
export const STORE_VERSION = 2;
export const MAX_TURNS = 30;

export type TurnError = { code: string; message: string };

/** One question and what came back for it. Turns run oldest first. */
export type Turn = {
  id: string;
  question: string; // the visitor's words
  at: string;
  answer?: AskAnswer; // the evidence
  written?: WrittenAnswer; // the answer written from the evidence, or why there is none
  calls?: ModelCall[]; // the model calls made for it
  thread?: ThreadTurn[]; // the turns this question followed, as they were sent with it
  rewritten?: boolean; // a follow-up made into a question that stands alone before the search
  web?: WebPart; // the web part (lib/web.ts), kept with its turn once it has come; a search under way is not kept
  stored?: boolean;
  storedDate?: string | null;
  // what is true only while the page is open: never written to storage
  pending?: boolean; // asked, no evidence yet
  writing?: boolean; // the evidence is here, the answer is being written
  check?: "waiting" | "failed"; // the turn waits for the human check, or it did not pass
  error?: TurnError;
};

export type Conversation = { id: string; started: string; turns: Turn[] };
export type Store = { version: number; current: string; conversations: Conversation[] };

/** Whether this browser keeps what the page writes: it does, it refuses (blocked), or it is out of room. */
export type Keeping = "kept" | "blocked" | "full";

export const newId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/** A turn as it is kept: settled, with its evidence, without what only the open page knows. */
function keepable(turn: Turn): Turn | null {
  if (!turn || typeof turn.question !== "string" || !turn.answer || turn.pending) return null;
  const { pending: _p, writing: _w, check: _c, error: _e, web, ...kept } = turn;
  // a search under way is not kept: a turn read back never asks for the web again
  return web && web.state !== "searching" ? { ...kept, web } : kept;
}

/** Turns read back from storage. A turn cut off while its answer was being written keeps its evidence. */
function readTurns(value: unknown): Turn[] {
  if (!Array.isArray(value)) return [];
  return value.map((t) => keepable(t as Turn)).filter((t): t is Turn => t !== null);
}

/** The time of a conversation's latest turn: what the list is ordered and grouped by. */
export const lastAt = (c: Conversation) => c.turns[c.turns.length - 1]?.at ?? c.started;

function storage(): Storage | null {
  try {
    const ls = window.localStorage;
    // a browser can hand out the object and still refuse to use it
    ls.getItem(STORE_KEY);
    return ls;
  } catch {
    return null;
  }
}

/** The store as it is now in this browser; null when the browser refuses to be read. */
export function readStore(): { conversations: Conversation[]; current: string | null } | null {
  const ls = storage();
  if (!ls) return null;
  try {
    const raw = ls.getItem(STORE_KEY);
    if (!raw) return { conversations: [], current: null };
    const store = JSON.parse(raw) as Partial<Store>;
    const conversations = (Array.isArray(store.conversations) ? store.conversations : [])
      .filter((c) => c && typeof c.id === "string")
      .map((c) => ({ id: c.id, started: String(c.started ?? ""), turns: readTurns(c.turns) }))
      .filter((c) => c.turns.length > 0);
    return { conversations, current: typeof store.current === "string" ? store.current : null };
  } catch {
    return { conversations: [], current: null };
  }
}

/** Everything kept, carrying over the first version once. */
export function loadStore(): { conversations: Conversation[]; current: string; keeping: Keeping } {
  const fresh = newId("c");
  const ls = storage();
  if (!ls) return { conversations: [], current: fresh, keeping: "blocked" };
  try {
    if (ls.getItem(STORE_KEY)) {
      const store = readStore()!;
      return { conversations: store.conversations, current: store.current ?? fresh, keeping: "kept" };
    }
    const old = ls.getItem(OLD_KEY);
    if (old) {
      // the first version kept the newest turn first. Written only while no store exists, so
      // a second tab opening at the same time cannot overwrite what the first carried over
      const turns = readTurns(JSON.parse(old)).reverse();
      const conversations = turns.length ? [{ id: fresh, started: turns[0].at, turns }] : [];
      if (write({ conversations, current: fresh }) === "kept") ls.removeItem(OLD_KEY);
      return { conversations, current: fresh, keeping: "kept" };
    }
  } catch {
    /* unreadable: start again, and leave what is there untouched */
  }
  return { conversations: [], current: fresh, keeping: "kept" };
}

const settledWeb = (t: Turn | undefined) => Boolean(t?.web && t.web.state !== "searching");

/**
 * Two copies of a conversation's turns as one: every turn of each, by id (the second copy wins), in time order.
 * A written answer and a web part arrive after their turn was first written, so a copy of the turn without them may
 * stand in another tab: a written answer or a web part either copy has is kept.
 */
export function mergeTurns(stored: Turn[], mine: Turn[]): Turn[] {
  const byId = new Map(stored.map((t) => [t.id, t]));
  for (const t of mine) {
    const other = byId.get(t.id);
    // a written answer either copy has is kept: a tab that read the turn before its answer came does not erase it
    let kept = !t.written && other?.written && !t.writing ? { ...t, written: other.written, ...(other.calls ? { calls: other.calls } : {}) } : t;
    if (!settledWeb(kept) && settledWeb(other)) kept = { ...kept, web: other!.web };
    byId.set(t.id, kept);
  }
  return [...byId.values()].sort((a, b) => a.at.localeCompare(b.at));
}

function write(store: { conversations: Conversation[]; current: string }): Keeping {
  const ls = storage();
  if (!ls) return "blocked";
  const conversations = store.conversations
    .map((c) => ({ ...c, turns: c.turns.map(keepable).filter((t): t is Turn => t !== null).slice(-MAX_TURNS) }))
    .filter((c) => c.turns.length > 0)
    .map((c) => ({ ...c, started: c.turns[0].at }));
  try {
    ls.setItem(STORE_KEY, JSON.stringify({ version: STORE_VERSION, current: store.current, conversations } satisfies Store));
    return "kept";
  } catch (e) {
    const full = e instanceof DOMException && (e.name === "QuotaExceededError" || e.name === "NS_ERROR_DOM_QUOTA_REACHED" || e.code === 22);
    return full ? "full" : "blocked";
  }
}

/*
 * Every write reads the store again first and changes only what this tab changed, so two tabs
 * open on one browser do not overwrite each other: a conversation another tab added or
 * changed meanwhile stays as that tab left it.
 */

/**
 * Write one conversation by its id. Its turns are merged with the stored copy, so turns another
 * tab added to the same conversation stay. `known`: this tab has seen it in the store; if it is
 * no longer there, another tab deleted it, and it is not written back ("deleted").
 */
export function writeConversation(c: Conversation, current: string, known: boolean): Keeping | "deleted" {
  const store = readStore();
  if (!store) return "blocked";
  const stored = store.conversations.find((s) => s.id === c.id);
  if (!stored && known) return "deleted";
  const merged = { ...c, turns: stored ? mergeTurns(stored.turns, c.turns) : c.turns };
  const others = store.conversations.filter((s) => s.id !== c.id);
  return write({ conversations: [...others, merged], current });
}

/** Delete these conversations by id, and nothing else. */
export function removeConversations(ids: string[], current: string): Keeping {
  const store = readStore();
  if (!store) return "blocked";
  return write({ conversations: store.conversations.filter((c) => !ids.includes(c.id)), current });
}

/** Say which conversation a new tab opens with: this tab's open one (the last tab to say so wins). */
export function writeCurrent(current: string): Keeping {
  const store = readStore();
  if (!store) return "blocked";
  if (store.current === current) return "kept";
  return write({ conversations: store.conversations, current });
}
