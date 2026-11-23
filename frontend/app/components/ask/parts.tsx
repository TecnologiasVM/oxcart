"use client";

/*
 * Small pieces of the question page, shared by the first screen, the thread and Evidence.
 */
import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { WrittenAnswer } from "@/lib/ask";
import type { Turn } from "@/lib/conversation";
import { FIGURES_BASE } from "@/lib/figures";
import type { Labels } from "@/lib/i18n";
import type { Service } from "./hooks";

export const PANEL_ID = "evidence-panel";
export const REPO_URL = "https://github.com/TecnologiasVM/oxcart";
export const HOW_URL = `${REPO_URL}/blob/main/EVALUATION.md`;

/** A written answer with sentences to show. */
export const answered = (written?: WrittenAnswer) => written?.state === "ok" && (written.sentences ?? []).length > 0;

/** The text of a written answer, as it is sent back with a follow-up. */
export const textOf = (written?: WrittenAnswer) => (written?.sentences ?? []).map((s) => s.text).join(" ");

/** The turn a question typed now follows: the newest settled turn, when it has a written answer. */
export function followed(turns: Turn[]): Turn | undefined {
  const settled = [...turns].reverse().find((t) => !t.error && !t.pending && !t.check);
  return settled && answered(settled.written) && !settled.writing ? settled : undefined;
}

/** Where a turn's source is, inside Evidence. */
export const sourceId = (turnId: string, n: number) => `ev-src-${turnId}-${n}`;
/** Where a passage's figures are, inside Evidence ("Cards and passages"). */
export const figuresId = (turnId: string, index: number) => `ev-figs-${turnId}-${index}`;

/** One line, with a sign, for a refusal, a failure or a part that could not be reached. Never by colour alone. */
export function Warn({ text, inline = false, testId, alert = true }: { text: string; inline?: boolean; testId?: string; alert?: boolean }) {
  return (
    <p className={`warn${inline ? " warn--in" : ""}`} role={alert ? "alert" : undefined} data-testid={testId}>
      <span className="warn__sign" aria-hidden="true">!</span>
      <span>{text}</span>
    </p>
  );
}

/** A notice in an answer's place: why no answer was written. */
export function Notice({ text, testId }: { text: string; testId?: string }) {
  return (
    <p className="notice" data-testid={testId}>
      <span className="notice__sign" aria-hidden="true" />
      <span>{text}</span>
    </p>
  );
}

/** A thin running bar: something is on its way. */
export function Bar({ testId }: { testId?: string }) {
  return <div className="wait-bar" aria-hidden="true" data-testid={testId}><span /></div>;
}

/*
 * What the visitor reads while waiting: short lines that follow one another, the last one
 * with a running count of seconds.
 *
 *   ✓ The service is awake.
 *   Connecting to the catalogue and the literature… 19 s
 *   Searching… 22 s                    (only when a question is waiting)
 *
 * The lines follow what the health route says, not a timer. `from` is how many seconds pass
 * before the lines appear: a question answered at once shows "Searching…" and nothing more.
 */
export function Waiting({ service, t, from, searching = false }: { service: Service; t: Labels; from: number; searching?: boolean }) {
  const stage = service === "ready" ? 2 : service === "connecting" ? 1 : 0;
  const [seconds, setSeconds] = useState(0);
  const [first, setFirst] = useState(stage); // the earliest stage seen in this wait
  if (stage < first) setFirst(stage);
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  if (seconds < from) return <p className="wait__line" role="status">{t.asking}</p>;

  const done = [t.waitAwake, t.waitConnected].slice(Math.min(first, stage), stage);
  const now = stage === 0 ? t.waitWaking : stage === 1 ? t.waitConnecting : searching ? t.asking : null;
  return (
    <div className="wait" data-testid="waiting">
      <ol className="wait__steps">
        {done.map((line) => (
          <li key={line} className="wait__done"><span className="wait__sign" aria-hidden="true">✓</span>{line}</li>
        ))}
        {now && (
          <li role="status">
            <span className="wait__sign wait__sign--run" aria-hidden="true" />
            <span>{now} <span className="wait__s" aria-hidden="true" data-testid="waiting-seconds">{t.seconds(seconds)}</span></span>
          </li>
        )}
      </ol>
      {stage < 2 && <p className="wait__hint">{t.waitHint}</p>}
    </div>
  );
}

/**
 * By the question box: one short line, and the full paragraph one step away. A `details`
 * element, so it works by keyboard and without script.
 */
export function PrivacyLine({ t }: { t: Labels }) {
  return (
    <details className="priv" data-testid="privacy">
      <summary>
        <span>{t.privLine}</span> <span className="priv__more">{t.privMore}</span>
      </summary>
      {/* pictures come from a host of their own: said only in a build that draws them */}
      <p className="priv__full" data-testid="privacy-full">{t.privFull}{FIGURES_BASE ? ` ${t.privPictures}` : ""}</p>
    </details>
  );
}

const FOCUSABLE = 'button:not([disabled]), [href], summary, input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** In a sheet, Tab and Shift+Tab go round inside it. */
export function keepFocusIn(e: KeyboardEvent<HTMLElement>, box: HTMLElement | null) {
  if (e.key !== "Tab" || !box) return;
  const items = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && (document.activeElement === first || !box.contains(document.activeElement))) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

/**
 * A deletion asked in place, where its button was: the words say what is lost, the two
 * buttons are named by what they do, no dialog and no timer. Focus lands on the one that
 * keeps; Esc keeps too.
 */
export function Confirm({ text, yes, no, onYes, onNo, testId }: { text: string; yes: string; no: string; onYes: () => void; onNo: () => void; testId?: string }) {
  const keep = useRef<HTMLButtonElement | null>(null);
  const group = useRef<HTMLDivElement | null>(null);
  const id = useId();
  useEffect(() => {
    // the whole question in view, clear of the pinned box (the page's scroll padding), then focus
    group.current?.scrollIntoView({ block: "nearest" });
    keep.current?.focus({ preventScroll: true });
  }, []);
  return (
    <div
      ref={group}
      className="confirm"
      role="group"
      aria-labelledby={id}
      data-testid={testId}
      onKeyDown={(e) => {
        if (e.key !== "Escape") return;
        e.preventDefault();
        e.stopPropagation(); // Esc answers the question; it does not also close a sheet around it
        onNo();
      }}
    >
      <p id={id}>{text}</p>
      <p className="confirm__btns">
        <button type="button" className="ask-btn ask-btn--primary" onClick={onYes}>{yes}</button>
        <button type="button" className="ask-btn" ref={keep} onClick={onNo}>{no}</button>
      </p>
    </div>
  );
}

/** The browser is not keeping conversations, or has no room left: one line, with a sign. */
export function KeepNote({ text }: { text: string }) {
  return (
    <p className="keepnote" role="status" data-testid="keep-note">
      <span className="warn__sign" aria-hidden="true">!</span>
      <span>{text}</span>
    </p>
  );
}
