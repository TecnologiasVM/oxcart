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
  const { pending: _p, writing: _w, check: _c, error: _e, ...kept } = turn;
  return kept;
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

/** Everything kept, carrying over the first version once. */
export function loadStore(): { conversations: Conversation[]; current: string; keeping: Keeping } {
  const fresh = newId("c");
  const ls = storage();
  if (!ls) return { conversations: [], current: fresh, keeping: "blocked" };
  try {
    const raw = ls.getItem(STORE_KEY);
    if (raw) {
      const store = JSON.parse(raw) as Partial<Store>;
      const conversations = (Array.isArray(store.conversations) ? store.conversations : [])
        .filter((c) => c && typeof c.id === "string")
        .map((c) => ({ id: c.id, started: String(c.started ?? ""), turns: readTurns(c.turns) }))
        .filter((c) => c.turns.length > 0);
      const current = typeof store.current === "string" ? store.current : fresh;
      return { conversations, current, keeping: "kept" };
    }
    const old = ls.getItem(OLD_KEY);
    if (old) {
      // the first version kept the newest turn first
      const turns = readTurns(JSON.parse(old)).reverse();
      const conversations = turns.length ? [{ id: fresh, started: turns[0].at, turns }] : [];
      if (saveStore(conversations, fresh) === "kept") ls.removeItem(OLD_KEY);
      return { conversations, current: fresh, keeping: "kept" };
    }
  } catch {
    /* unreadable: start again, and leave what is there untouched */
  }
  return { conversations: [], current: fresh, keeping: "kept" };
}

/** Write every conversation. Says whether the browser kept it. */
export function saveStore(conversations: Conversation[], current: string): Keeping {
  const ls = storage();
  if (!ls) return "blocked";
  const kept = conversations
    .map((c) => ({ ...c, turns: c.turns.map(keepable).filter((t): t is Turn => t !== null).slice(-MAX_TURNS) }))
    .filter((c) => c.turns.length > 0)
    .map((c) => ({ ...c, started: c.turns[0].at }));
  try {
    ls.setItem(STORE_KEY, JSON.stringify({ version: STORE_VERSION, current, conversations: kept } satisfies Store));
    return "kept";
  } catch (e) {
    const full = e instanceof DOMException && (e.name === "QuotaExceededError" || e.name === "NS_ERROR_DOM_QUOTA_REACHED" || e.code === 22);
    return full ? "full" : "blocked";
  }
}
