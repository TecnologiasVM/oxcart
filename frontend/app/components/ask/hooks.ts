"use client";

/*
 * The question page's state that outlives a render: the conversation and its storage,
 * where the service is, the human check, and two small facts about the screen.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AskError, openSession, serviceState, turnstileSiteKey } from "@/lib/ask";
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

function savedSession(): string | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const { session, expires } = JSON.parse(raw) as { session: string; expires: number };
    return expires > Date.now() + 30_000 ? session : null;
  } catch {
    return null;
  }
}

export type CheckResult = { session: string | null; code?: string };

/**
 * The human check (Cloudflare Turnstile), once per session. Its widget is drawn into the
 * element the page attaches, which stands in the turn that waits for it. The check's
 * token is traded for a short-lived session that is sent with each question.
 */
export function useHumanCheck() {
  const [siteKey, setSiteKey] = useState("");
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);
  const waiting = useRef<((result: CheckResult) => void) | null>(null);
  useEffect(() => setSiteKey(turnstileSiteKey()), []);

  const settle = useCallback((result: CheckResult) => {
    const resolve = waiting.current;
    waiting.current = null;
    resolve?.(result);
  }, []);

  const onToken = useCallback(async (token: string) => {
    try {
      const { session, expires_in } = await openSession(token);
      try {
        window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ session, expires: Date.now() + expires_in * 1000 }));
      } catch {
        /* session storage blocked: the token still serves this question */
      }
      settle({ session });
    } catch (e) {
      settle({ session: null, code: e instanceof AskError ? e.code : "human_check_unavailable" });
    }
  }, [settle]);

  useEffect(() => {
    if (!el || !siteKey) return;
    let cancelled = false;
    const failed = () => settle({ session: null, code: "human_check_unavailable" });
    const render = () => {
      if (cancelled || !window.turnstile || widgetId.current) return;
      widgetId.current = window.turnstile.render(el, { sitekey: siteKey, callback: onToken, "error-callback": failed });
    };
    if (window.turnstile) render();
    else {
      let script = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
      if (!script) {
        script = document.createElement("script");
        script.src = SCRIPT_SRC;
        script.async = true;
        document.head.appendChild(script);
      }
      script.addEventListener("load", render);
      script.addEventListener("error", failed);
    }
    return () => {
      cancelled = true;
      if (widgetId.current && window.turnstile?.remove) window.turnstile.remove(widgetId.current);
      widgetId.current = null;
    };
  }, [el, siteKey, onToken, settle]);

  /**
   * A session for the next question. When one is needed, `show` puts the check in the
   * turn, and this waits for it (at most a minute).
   */
  const sessionFor = useCallback((show: () => void, again = false): Promise<CheckResult> => {
    if (!siteKey) return Promise.resolve({ session: null });
    if (again) {
      try {
        window.sessionStorage.removeItem(SESSION_KEY);
      } catch {
        /* nothing to remove */
      }
    }
    const current = savedSession();
    if (current) return Promise.resolve({ session: current });
    show();
    if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
    return new Promise((resolve) => {
      waiting.current = resolve;
      setTimeout(() => {
        if (waiting.current === resolve) settle({ session: null });
      }, 60_000);
    });
  }, [siteKey, settle]);

  return { needsCheck: Boolean(siteKey), attach: setEl, sessionFor };
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
