"use client";

/*
 * Small pieces of the question page, shared by the first screen, the thread and Evidence.
 */
import { useEffect, useState } from "react";
import type { WrittenAnswer } from "@/lib/ask";
import type { Turn } from "@/lib/conversation";
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
      <p className="priv__full" data-testid="privacy-full">{t.privFull}</p>
    </details>
  );
}
