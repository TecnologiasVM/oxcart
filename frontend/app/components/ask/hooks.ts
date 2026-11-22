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
 * It starts when the question box first takes focus, in a widget kept off screen (rendered,
 * 300 by 65 px, so Cloudflare can run it), so the first question need not wait for it. A
 * question sent after it passed carries the session, and nothing about the check is drawn.
 * A question sent before that (the check still running, failed, or asking for a click that
 * could not be seen off screen) gets the check in its turn: the off-screen widget gives way
 * to a visible one drawn there, in the room the page keeps for it.
 */
export function useHumanCheck() {
  const siteKey = TURNSTILE_SITE_KEY;
  const held = useRef<Held | null>(null);
  const waiting = useRef<((result: CheckResult) => void) | null>(null);
  const [warming, setWarming] = useState(false);
  const [host, setHost] = useState<HTMLDivElement | null>(null); // the off-screen place
  const [el, setEl] = useState<HTMLDivElement | null>(null); // the place in the turn

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
    const resolve = waiting.current;
    waiting.current = null;
    resolve?.(result);
  }, []);

  const onToken = useCallback(async (token: string) => {
    try {
      const { session, expires_in } = await openSession(token);
      held.current = { session, expires: Date.now() + expires_in * 1000 };
      try {
        window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(held.current));
      } catch {
        /* session storage blocked: the page holds the session itself */
      }
      setWarming(false);
      settle({ session });
    } catch (e) {
      settle({ session: null, code: e instanceof AskError ? e.code : "human_check_unavailable" });
    }
  }, [settle]);

  // off screen, from the box's first focus until it passes or a question is sent
  useEffect(() => {
    if (!warming || !host || !siteKey) return;
    let cancelled = false;
    let id: string | null = null;
    withTurnstile(() => {
      if (cancelled || !window.turnstile) return;
      // a failure here only means the check will be drawn in the turn when a question is sent
      id = window.turnstile.render(host, { sitekey: siteKey, callback: onToken, "error-callback": () => true });
    }, () => {});
    return () => {
      cancelled = true;
      if (id && window.turnstile?.remove) window.turnstile.remove(id);
    };
  }, [warming, host, siteKey, onToken]);

  // in the turn that waits for it
  useEffect(() => {
    if (!el || !siteKey) return;
    let cancelled = false;
    let id: string | null = null;
    const failed = () => settle({ session: null, code: "human_check_unavailable" });
    withTurnstile(() => {
      if (cancelled || !window.turnstile) return;
      id = window.turnstile.render(el, { sitekey: siteKey, callback: onToken, "error-callback": failed });
    }, failed);
    return () => {
      cancelled = true;
      if (id && window.turnstile?.remove) window.turnstile.remove(id);
    };
  }, [el, siteKey, onToken, settle]);

  /** The box took focus: start the check now, unless a session is in hand. */
  const warm = useCallback(() => {
    if (siteKey && !current()) setWarming(true);
  }, [siteKey, current]);

  /**
   * A session for the next question. When none is in hand, `show` puts the check in the
   * turn, and this waits for it (at most a minute).
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
      waiting.current = resolve;
      setWarming(false); // a token already on its way still settles this wait
      show();
      setTimeout(() => {
        if (waiting.current === resolve) settle({ session: null });
      }, 60_000);
    });
  }, [siteKey, current, settle]);

  return { needsCheck: Boolean(siteKey), warm, host: setHost, attach: setEl, sessionFor };
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
