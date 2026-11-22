"use client";

/*
 * The question page's state that outlives a render: the conversations and their storage,
 * where the service is, the human check, and two small facts about the screen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AskError, openSession, serviceState, TURNSTILE_SITE_KEY } from "@/lib/ask";
import type { ServiceState } from "@/lib/ask";
import { lastAt, loadStore, mergeTurns, newId, readStore, removeConversations, STORE_KEY, writeConversation, writeCurrent } from "@/lib/conversation";
import type { Conversation, Keeping, Turn } from "@/lib/conversation";

// ---------------------------------------------------------------- the conversations

/**
 * The conversations of this browser, and the one open now, kept in local storage as they
 * change. The open one may be new and empty: the page then shows its first screen.
 * When the browser keeps nothing, the list holds only the open conversation.
 *
 * Two tabs on one browser share the store and do not overwrite each other: a tab writes only
 * the conversation it changed (lib/conversation.ts), and follows what another tab writes (the
 * `storage` event). The open conversation is each tab's own. A conversation deleted in another
 * tab is never written back: the tab showing it closes it and opens a new one, and what the
 * visitor was typing stays in the box.
 */
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [current, setCurrent] = useState("");
  const [keeping, setKeeping] = useState<Keeping>("kept");
  const [loaded, setLoaded] = useState(false);
  const written = useRef(new Map<string, Conversation>()); // per id, the copy last written or read: what needs no write
  const known = useRef(new Set<string>()); // the ids this tab has seen in the store
  const state = useRef({ conversations, current });
  state.current = { conversations, current };

  useEffect(() => {
    const kept = loadStore();
    for (const c of kept.conversations) {
      written.current.set(c.id, c);
      known.current.add(c.id);
    }
    setConversations(kept.conversations);
    setCurrent(kept.current);
    setKeeping(kept.keeping);
    setLoaded(true);
  }, []);

  /** Another tab deleted this one: drop it here too, never write it back. */
  const dropped = useCallback((id: string) => {
    written.current.delete(id);
    known.current.delete(id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (state.current.current === id) setCurrent(newId("c"));
  }, []);

  // write what this tab changed, one conversation at a time
  useEffect(() => {
    if (!loaded) return;
    for (const c of conversations) {
      if (written.current.get(c.id) === c) continue;
      written.current.set(c.id, c);
      const result = writeConversation(c, current, known.current.has(c.id));
      if (result === "deleted") {
        dropped(c.id);
        continue;
      }
      setKeeping(result);
      if (result === "kept" && c.turns.some((t) => t.answer && !t.pending)) known.current.add(c.id);
    }
  }, [conversations, current, loaded, dropped]);
  // which conversation a new tab opens with
  const firstCurrent = useRef(true);
  useEffect(() => {
    if (!loaded) return;
    if (firstCurrent.current) {
      firstCurrent.current = false;
      return;
    }
    setKeeping(writeCurrent(current));
  }, [current, loaded]);

  // follow another tab: its new and changed conversations come in, its deletions go
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORE_KEY) return;
      const fresh = readStore();
      if (!fresh) return;
      const mine = state.current.conversations;
      const freshIds = new Set(fresh.conversations.map((c) => c.id));
      const next: Conversation[] = [];
      for (const f of fresh.conversations) {
        const local = mine.find((c) => c.id === f.id);
        const merged = local ? { ...local, turns: mergeTurns(f.turns, local.turns) } : f;
        // unchanged here: keep the same copy, so nothing is written back
        const same = local && local.turns.length === merged.turns.length && local.turns.every((t, i) => t === merged.turns[i]);
        const kept = same ? local! : merged;
        written.current.set(kept.id, kept);
        known.current.add(kept.id);
        next.push(kept);
      }
      for (const c of mine) {
        if (freshIds.has(c.id)) continue;
        if (known.current.has(c.id)) {
          known.current.delete(c.id); // deleted in another tab
          written.current.delete(c.id);
          if (state.current.current === c.id) setCurrent(newId("c"));
        } else {
          next.push(c); // not written yet (a first question on its way): still this tab's
        }
      }
      setConversations(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const turns = useMemo(() => conversations.find((c) => c.id === current)?.turns ?? [], [conversations, current]);

  /** A new turn at the foot of the open conversation. A refused turn above it has done its work. */
  const add = useCallback((turn: Turn) => {
    setConversations((prev) => {
      const open = prev.find((c) => c.id === current);
      if (!open) return [...prev, { id: current, started: turn.at, turns: [turn] }];
      return prev.map((c) => (c.id === current ? { ...c, turns: [...c.turns.filter((t) => !t.error), turn] } : c));
    });
  }, [current]);
  /** A change to a turn, wherever it is: an answer lands in its own conversation even after another was opened. */
  const patch = useCallback((turnId: string, change: Partial<Turn>) =>
    setConversations((prev) => prev.map((c) =>
      c.turns.some((t) => t.id === turnId) ? { ...c, turns: c.turns.map((t) => (t.id === turnId ? { ...t, ...change } : t)) } : c)), []);
  const open = useCallback((id: string) => setCurrent(id), []);
  const start = useCallback(() => setCurrent(newId("c")), []);
  /** Delete by id: from this tab, and from the store only these ids. */
  const forget = useCallback((ids: string[]) => {
    const next = ids.includes(state.current.current) ? newId("c") : state.current.current;
    for (const id of ids) {
      written.current.delete(id);
      known.current.delete(id);
    }
    setConversations((prev) => prev.filter((c) => !ids.includes(c.id)));
    setCurrent(next);
    setKeeping(removeConversations(ids, next));
  }, []);
  const remove = useCallback((id: string) => forget([id]), [forget]);

  // newest first; when the browser keeps nothing, only the open one
  const list = useMemo(() => conversations
    .filter((c) => c.turns.length > 0 && (keeping !== "blocked" || c.id === current))
    .sort((a, b) => lastAt(b).localeCompare(lastAt(a))), [conversations, current, keeping]);
  /** "Delete all": the conversations this tab lists, which the question counted; nothing added elsewhere unseen. */
  const removeAll = useCallback(() => forget(list.map((c) => c.id)), [forget, list]);

  return { list, current, turns, keeping, loaded, add, patch, open, start, remove, removeAll };
}

// ---------------------------------------------------------------- the service

export type Service = "checking" | "waking" | "connecting" | "ready" | "unreachable";
const POLL_EVERY_MS = 2000;
export const WAIT_LINES_AFTER_SECONDS = 3; // a question answered sooner shows "Searching…" and nothing else
const fromState = (state: ServiceState): Service => (state === "ready" ? "ready" : state === "connecting" ? "connecting" : "waking");
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Where the service is. It is woken as soon as the page opens; while a question waits the
 * page keeps looking, because a page left open finds it asleep again and the waiting lines
 * must say what is true now.
 */
export function useService(busy: boolean) {
  const [service, setService] = useState<Service>("checking");
  useEffect(() => {
    let stop = false;
    (async () => {
      let state = await serviceState(4000);
      for (let i = 0; i < 60 && !stop; i++) {
        setService(fromState(state));
        if (state === "ready") return;
        await pause(POLL_EVERY_MS);
        if (stop) return;
        state = await serviceState(8000);
      }
      if (!stop) setService("unreachable");
    })();
    return () => {
      stop = true;
    };
  }, []);
  useEffect(() => {
    if (!busy) return;
    let stop = false;
    const timer = setTimeout(async () => {
      while (!stop) {
        const state = await serviceState(8000);
        if (stop) return;
        setService(fromState(state));
        await pause(POLL_EVERY_MS);
      }
    }, WAIT_LINES_AFTER_SECONDS * 1000);
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [busy]);
  return [service, setService] as const;
}

// ---------------------------------------------------------------- the human check

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, options: Record<string, unknown>) => string;
      reset: (id?: string) => void;
      remove?: (id: string) => void;
    };
  }
}

const SESSION_KEY = "oxcart-session";
const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type Held = { session: string; expires: number };
export type CheckResult = { session: string | null; code?: string };

function storedSession(): Held | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as Held) : null;
  } catch {
    return null;
  }
}

/** Cloudflare's script, loaded once; `ready` runs when it is there. */
function withTurnstile(ready: () => void, failed: () => void) {
  if (window.turnstile) return ready();
  let script = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
  if (!script) {
    script = document.createElement("script");
    script.src = SCRIPT_SRC;
    script.async = true;
    document.head.appendChild(script);
  }
  script.addEventListener("load", ready, { once: true });
  script.addEventListener("error", failed, { once: true });
}

/**
 * The human check (Cloudflare Turnstile), once per session. Its token is traded at once for
 * a short-lived session that is sent with each question.
 *
 * One widget, drawn when the question box first takes focus into the one element the page
 * keeps for it (`host`), and never moved or drawn again: moving its frame would reload it.
 * It uses Cloudflare's appearance "interaction-only": invisible, and taking no room, unless
 * the visitor has to click. A question sent after it passed carries the session and nothing
 * about the check is drawn; one sent before waits for the same widget to finish (`waiting`),
 * and the page shows the check's words and keeps its room meanwhile.
 */
export function useHumanCheck() {
  const siteKey = TURNSTILE_SITE_KEY;
  const held = useRef<Held | null>(null);
  const resolver = useRef<((result: CheckResult) => void) | null>(null);
  const widget = useRef<{ id: string; done: boolean } | null>(null);
  const [started, setStarted] = useState(false);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const [waiting, setWaiting] = useState(false); // a sent question waits for the check
  const [asking, setAsking] = useState(false); // the widget asks the visitor for a click

  /** The session in hand, if it has more than half a minute left. */
  const current = useCallback((): string | null => {
    const soon = Date.now() + 30_000;
    if (held.current && held.current.expires > soon) return held.current.session;
    const saved = storedSession();
    if (saved && saved.expires > soon) {
      held.current = saved;
      return saved.session;
    }
    return null;
  }, []);

  const settle = useCallback((result: CheckResult) => {
    const resolve = resolver.current;
    resolver.current = null;
    setWaiting(false);
    resolve?.(result);
  }, []);

  const onToken = useCallback(async (token: string) => {
    if (widget.current) widget.current.done = true;
    try {
      const { session, expires_in } = await openSession(token);
      held.current = { session, expires: Date.now() + expires_in * 1000 };
      try {
        window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(held.current));
      } catch {
        /* session storage blocked: the page holds the session itself */
      }
      settle({ session });
    } catch (e) {
      settle({ session: null, code: e instanceof AskError ? e.code : "human_check_unavailable" });
    }
  }, [settle]);

  // drawn once, into the element the page keeps for it
  useEffect(() => {
    if (!started || !host || !siteKey || widget.current) return;
    const failed = () => {
      if (widget.current) widget.current.done = true;
      setAsking(false);
      settle({ session: null, code: "human_check_unavailable" });
      return true; // handled: the page says so in the turn, and a new question tries again
    };
    withTurnstile(() => {
      if (!window.turnstile || widget.current) return;
      const id = window.turnstile.render(host, {
        sitekey: siteKey,
        appearance: "interaction-only",
        callback: onToken,
        "error-callback": failed,
        "timeout-callback": failed,
        "before-interactive-callback": () => setAsking(true),
        "after-interactive-callback": () => setAsking(false),
      });
      widget.current = { id, done: false };
    }, failed);
  }, [started, host, siteKey, onToken, settle]);

  /** The box took focus: start the check now, unless a session is in hand. */
  const warm = useCallback(() => {
    if (siteKey && !current()) setStarted(true);
  }, [siteKey, current]);

  /**
   * A session for the next question. With none in hand, `show` marks the turn as waiting, and
   * this waits (at most a minute) for the widget: the one already running goes on; one that
   * already ended is run again.
   */
  const sessionFor = useCallback((show: () => void, again = false): Promise<CheckResult> => {
    if (!siteKey) return Promise.resolve({ session: null });
    if (again) {
      held.current = null;
      try {
        window.sessionStorage.removeItem(SESSION_KEY);
      } catch {
        /* nothing to remove */
      }
    }
    const session = current();
    if (session) return Promise.resolve({ session });
    return new Promise((resolve) => {
      resolver.current = resolve;
      setWaiting(true);
      show();
      setStarted(true); // a question sent without the box ever taking focus starts it here
      if (widget.current?.done && window.turnstile) {
        widget.current.done = false;
        window.turnstile.reset(widget.current.id);
      }
      setTimeout(() => {
        if (resolver.current === resolve) settle({ session: null });
      }, 60_000);
    });
  }, [siteKey, current, settle]);

  return { needsCheck: Boolean(siteKey), warm, host: setHost, waiting, asking, sessionFor };
}

// ---------------------------------------------------------------- the screen

/** Whether a media query matches, kept up to date. False before the page is in a browser. */
export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const list = window.matchMedia(query);
    const update = () => setMatches(list.matches);
    update();
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return matches;
}

/** The header's height, as a CSS variable, so what sticks under it knows where to stop. */
export function useHeaderHeight() {
  useEffect(() => {
    const header = document.querySelector<HTMLElement>("header.masthead");
    if (!header) return;
    const set = () => document.documentElement.style.setProperty("--masthead-h", `${header.offsetHeight}px`);
    set();
    const observer = new ResizeObserver(set);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
}

/**
 * How much of the window the pinned parts cover: the box at the foot (the form on a phone,
 * the whole dock from 720 px) and, at the top, the header where it sticks and any bar pinned
 * above the thread (`.threadbar`). Kept as CSS variables that the page's scroll padding uses,
 * so that whatever takes focus, or is brought into view, is never left under them.
 */
export function usePinnedEdges(watch: unknown) {
  useEffect(() => {
    const root = document.documentElement;
    const measure = () => {
      const dock = document.querySelector<HTMLElement>(".dock");
      const foot = dock && getComputedStyle(dock).display === "contents" ? document.querySelector<HTMLElement>("form.composer") : dock;
      const header = document.querySelector<HTMLElement>("header.masthead");
      const bar = document.querySelector<HTMLElement>(".threadbar");
      const top = (header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0)
        + (bar && getComputedStyle(bar).display !== "none" ? bar.offsetHeight : 0);
      root.style.setProperty("--pinned-foot", `${foot?.offsetHeight ?? 0}px`);
      root.style.setProperty("--pinned-top", `${top}px`);
    };
    measure();
    const observer = new ResizeObserver(measure);
    for (const el of document.querySelectorAll<HTMLElement>(".dock, form.composer, header.masthead, .threadbar")) observer.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [watch]);
}
