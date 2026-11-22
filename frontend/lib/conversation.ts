/*
 * The conversation as this browser keeps it. Nothing of it is sent to be stored anywhere:
 * local storage is its only home, and the page works the same when storage is blocked or
 * full (the conversation is then simply not kept).
 *
 * Shape on disk (key `oxcart-conversations`):
 *
 *   { version: 2, current: "<id>", conversations: [{ id, started, turns: [...] }] }
 *
 * The page keeps one conversation today. The list is there so a later version can keep
 * several without losing what a visitor already has. The first version (key
 * `oxcart-chat-v1`: a bare list of turns, newest first) is read once and carried over.
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
  check?: "waiting" | "failed"; // the human check stands in this turn
  error?: TurnError;
};

export type Conversation = { id: string; started: string; turns: Turn[] };
export type Store = { version: number; current: string; conversations: Conversation[] };

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

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // blocked
  }
}

/** The current conversation's turns, oldest first, carrying over the first version once. */
export function loadTurns(): { id: string; turns: Turn[] } {
  const ls = storage();
  const fresh = { id: newId("c"), turns: [] as Turn[] };
  if (!ls) return fresh;
  try {
    const raw = ls.getItem(STORE_KEY);
    if (raw) {
      const store = JSON.parse(raw) as Partial<Store>;
      const list = Array.isArray(store.conversations) ? store.conversations : [];
      const current = list.find((c) => c && c.id === store.current) ?? list[0];
      return current ? { id: String(current.id), turns: readTurns(current.turns) } : fresh;
    }
    const old = ls.getItem(OLD_KEY);
    if (old) {
      // the first version kept the newest turn first
      const turns = readTurns(JSON.parse(old)).reverse();
      const carried = { id: fresh.id, turns };
      if (saveTurns(carried.id, turns)) ls.removeItem(OLD_KEY);
      return carried;
    }
  } catch {
    /* unreadable: start again, and leave what is there untouched */
  }
  return fresh;
}

/** Write the conversation. False when the browser would not keep it (blocked or full). */
export function saveTurns(id: string, turns: Turn[]): boolean {
  const ls = storage();
  if (!ls) return false;
  try {
    const kept = turns.map(keepable).filter((t): t is Turn => t !== null).slice(-MAX_TURNS);
    let store: Store = { version: STORE_VERSION, current: id, conversations: [] };
    const raw = ls.getItem(STORE_KEY);
    if (raw) {
      const read = JSON.parse(raw) as Partial<Store>;
      // keep any other conversation a later version wrote; this page edits only its own
      const others = (Array.isArray(read.conversations) ? read.conversations : []).filter((c) => c && c.id !== id);
      store = { ...store, conversations: others };
    }
    const started = kept[0]?.at ?? new Date().toISOString();
    store.conversations = kept.length ? [...store.conversations, { id, started, turns: kept }] : store.conversations;
    ls.setItem(STORE_KEY, JSON.stringify(store));
    return true;
  } catch {
    return false;
  }
}
