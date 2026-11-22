"use client";

/*
 * The question page's state that outlives a render: the conversation and its storage,
 * where the service is, the human check, and two small facts about the screen.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AskError, openSession, serviceState, TURNSTILE_SITE_KEY } from "@/lib/ask";
import type { ServiceState } from "@/lib/ask";
import { loadTurns, saveTurns } from "@/lib/conversation";
import type { Turn } from "@/lib/conversation";

// ---------------------------------------------------------------- the conversation

/**
 * The one conversation of this browser, oldest turn first, kept in local storage as it
 * changes. Storage blocked or full: the conversation lives as long as the page.
 */
export function useConversation() {
  const [id, setId] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const kept = loadTurns();
    setId(kept.id);
    setTurns(kept.turns);
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (loaded) saveTurns(id, turns);
  }, [id, turns, loaded]);

  /** A new turn at the foot. A refused turn above it has done its work (its question went back to the box). */
  const add = useCallback((turn: Turn) => setTurns((prev) => [...prev.filter((t) => !t.error), turn]), []);
  const patch = useCallback((turnId: string, change: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, ...change } : t))), []);
  const clear = useCallback(() => setTurns([]), []);
  return { turns, loaded, add, patch, clear };
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
