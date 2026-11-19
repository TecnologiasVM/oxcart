"use client";

/*
 * The chat page: one question box, and under it the conversation so far.
 *
 * - No account. The conversation is a list of turns (question, evidence) kept in
 *   this browser's local storage, so a returning visitor sees it again. "Clear"
 *   empties it. One conversation; no threads yet.
 * - Stored examples ship with the page (a static file): a visitor sees real
 *   evidence while the service wakes up, and when it is asleep or gone. They are
 *   marked as stored.
 * - Before the first question a human check (Cloudflare Turnstile) runs once; the
 *   backend answers it with a short-lived token that is sent with each question.
 * - Every answer says which mode produced it (search by meaning, or keyword mode).
 *
 * Retrieval only: the page shows evidence, it does not write an answer.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ask, AskError, health, liveExamples, MAX_QUESTION_CHARS, openSession, storedExamples, TURNSTILE_SITE_KEY } from "@/lib/ask";
import type { AskAnswer, Example, StoredExample } from "@/lib/ask";
import { LABELS } from "@/lib/i18n";
import type { Labels, Lang } from "@/lib/i18n";

const HISTORY_KEY = "oxcart-chat-v1";
const LANG_KEY = "oxcart-lang";
const SESSION_KEY = "oxcart-session";
const MAX_TURNS = 30;

type Turn = {
  id: string;
  question: string;
  at: string;
  answer?: AskAnswer;
  stored?: boolean;
  storedDate?: string | null;
  error?: { code: string; message: string };
  pending?: boolean;
};

type Service = "checking" | "starting" | "ready" | "unreachable";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, options: Record<string, unknown>) => string;
      reset: (id?: string) => void;
    };
  }
}

function loadTurns(): Turn[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    const turns = raw ? (JSON.parse(raw) as Turn[]) : [];
    return Array.isArray(turns) ? turns.filter((t) => t && t.question && (t.answer || t.error)) : [];
  } catch {
    return [];
  }
}

function saveTurns(turns: Turn[]) {
  try {
    const keep = turns.filter((t) => !t.pending && t.answer).slice(0, MAX_TURNS);
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(keep));
  } catch {
    /* storage full or blocked: the conversation simply is not kept */
  }
}

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

export default function Chat() {
  const [lang, setLang] = useState<Lang>("en");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [service, setService] = useState<Service>("checking");
  const [stored, setStored] = useState<StoredExample[]>([]);
  const [storedDate, setStoredDate] = useState<string | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [checkNote, setCheckNote] = useState<string | null>(null);
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);
  const waiting = useRef<((session: string | null) => void) | null>(null);
  const t: Labels = LABELS[lang];
  const needsCheck = Boolean(TURNSTILE_SITE_KEY);

  // --- what this browser remembers
  useEffect(() => {
    const savedLang = window.localStorage.getItem(LANG_KEY);
    setLang(savedLang === "es" || savedLang === "en" ? savedLang : navigator.language.toLowerCase().startsWith("es") ? "es" : "en");
    setTurns(loadTurns());
    setSession(savedSession());
    setLoaded(true);
  }, []);
  useEffect(() => {
    if (loaded) saveTurns(turns);
  }, [turns, loaded]);
  useEffect(() => {
    if (loaded) {
      window.localStorage.setItem(LANG_KEY, lang);
      document.documentElement.lang = lang;
    }
  }, [lang, loaded]);

  // --- the examples that ship with the page, and the live list when there are none
  useEffect(() => {
    storedExamples().then((data) => {
      setStored(data.examples);
      setStoredDate(data.generated);
      if (data.examples.length === 0) liveExamples().then(setExamples);
      else setExamples(data.examples.map(({ lang: l, question: q }) => ({ lang: l, question: q })));
    });
  }, []);

  // --- wake the service as soon as the page opens, and say so while it starts
  useEffect(() => {
    let stop = false;
    (async () => {
      const first = await health(4000);
      if (stop) return;
      if (first) return setService("ready");
      setService("starting");
      for (let i = 0; i < 45 && !stop; i++) {
        if (await health(8000)) return setService("ready");
        await new Promise((r) => setTimeout(r, 4000));
      }
      if (!stop) setService("unreachable");
    })();
    return () => {
      stop = true;
    };
  }, []);

  // --- the human check: once per session
  const onToken = useCallback(async (token: string) => {
    try {
      const { session: s, expires_in } = await openSession(token);
      window.sessionStorage.setItem(SESSION_KEY, JSON.stringify({ session: s, expires: Date.now() + expires_in * 1000 }));
      setSession(s);
      setCheckNote(null);
      waiting.current?.(s);
    } catch (e) {
      const code = e instanceof AskError ? e.code : "human_check_unavailable";
      setCheckNote(code);
      waiting.current?.(null);
    } finally {
      waiting.current = null;
    }
  }, []);

  useEffect(() => {
    if (!needsCheck || session || !loaded) return;
    let cancelled = false;
    const render = () => {
      if (cancelled || !widgetRef.current || !window.turnstile || widgetId.current) return;
      widgetId.current = window.turnstile.render(widgetRef.current, {
        sitekey: TURNSTILE_SITE_KEY,
        callback: onToken,
        "error-callback": () => setCheckNote("human_check_unavailable"),
      });
    };
    if (window.turnstile) render();
    else {
      const script = document.createElement("script");
      script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      script.async = true;
      script.onload = render;
      script.onerror = () => setCheckNote("human_check_unavailable");
      document.head.appendChild(script);
    }
    return () => {
      cancelled = true;
    };
  }, [needsCheck, session, loaded, onToken]);

  const sessionForAsk = useCallback(async (): Promise<string | null> => {
    if (!needsCheck) return null;
    const current = savedSession();
    if (current) return current;
    setSession(null);
    if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
    return new Promise((resolve) => {
      waiting.current = resolve;
      setTimeout(() => {
        if (waiting.current === resolve) {
          waiting.current = null;
          resolve(null);
        }
      }, 60_000);
    });
  }, [needsCheck]);

  // --- asking
  const submit = useCallback(
    async (text: string) => {
      const q = text.replace(/\s+/g, " ").trim().slice(0, MAX_QUESTION_CHARS);
      if (!q || busy) return;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setBusy(true);
      setQuestion("");
      setTurns((prev) => [{ id, question: q, at: new Date().toISOString(), pending: true }, ...prev]);
      const finish = (patch: Partial<Turn>) =>
        setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, pending: false, ...patch } : turn)));
      try {
        let s = await sessionForAsk();
        if (needsCheck && !s) throw new AskError("session_required", "", 401);
        let answer: AskAnswer;
        try {
          answer = await ask(q, s);
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "session_required" || !needsCheck) throw e;
          window.sessionStorage.removeItem(SESSION_KEY); // the token expired: one more check, one more try
          s = await sessionForAsk();
          if (!s) throw e;
          answer = await ask(q, s);
        }
        setService("ready");
        finish({ answer });
      } catch (e) {
        const err = e instanceof AskError ? e : new AskError("unreachable", "", 0);
        finish({ error: { code: err.code, message: err.message } });
      } finally {
        setBusy(false);
      }
    },
    [busy, needsCheck, sessionForAsk],
  );

  const showStored = (example: StoredExample) =>
    setTurns((prev) => [
      { id: `stored-${Date.now()}`, question: example.question, at: new Date().toISOString(), answer: example.answer, stored: true, storedDate },
      ...prev,
    ]);

  const pick = (example: Example) => {
    const saved = stored.find((s) => s.question === example.question);
    if (saved) showStored(saved);
    else submit(example.question);
  };

  const clear = () => {
    setTurns([]);
    try {
      window.localStorage.removeItem(HISTORY_KEY);
    } catch {
      /* nothing to remove */
    }
  };

  const left = MAX_QUESTION_CHARS - question.length;

  return (
    <main className="container chat">
      <div className="chat__top">
        <h1 className="chat__title">{t.title}</h1>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setLang(lang === "es" ? "en" : "es")} data-testid="lang-toggle">
          {t.language}
        </button>
      </div>
      <p className="chat__lede">{t.lede}</p>

      {service === "starting" && <p className="chat__notice" role="status" data-testid="service-starting">{t.starting}</p>}
      {service === "unreachable" && <p className="chat__notice chat__notice--warn" role="status" data-testid="service-unreachable">{t.unreachable}</p>}

      <form
        className="chat__form"
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <label className="mono" htmlFor="chat-question">{t.question}</label>
        <textarea
          id="chat-question"
          className="input chat__input"
          rows={2}
          maxLength={MAX_QUESTION_CHARS}
          placeholder={t.placeholder}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(question);
            }
          }}
        />
        <div className="chat__actions">
          <button type="submit" className="btn btn--solid" disabled={busy || !question.trim()}>
            {busy ? t.asking : t.ask}
          </button>
          {left <= 60 && <span className="mono muted">{t.left(left)}</span>}
          {turns.length > 0 && (
            <button type="button" className="btn btn--ghost btn--sm chat__clear" onClick={clear} data-testid="clear">
              {t.clear}
            </button>
          )}
        </div>
        {needsCheck && !session && (
          <div className="chat__check">
            <span className="body-sm">{busy ? t.humanWaiting : t.humanCheck}</span>
            <div ref={widgetRef} data-testid="human-check" />
          </div>
        )}
        {checkNote && <p className="chat__notice chat__notice--warn" role="alert">{t.errors[checkNote] ?? t.errors.human_check_unavailable}</p>}
      </form>

      {examples.length > 0 && (
        <section className="chat__examples" aria-label={t.examples}>
          <span className="mono muted">{t.examples}</span>
          <div className="chat__example-list">
            {examples.map((example) => (
              <button key={example.question} type="button" className="chat__example" onClick={() => pick(example)} disabled={busy}>
                {example.question}
                {stored.some((s) => s.question === example.question) && <span className="chip chat__stored-chip">{t.stored}</span>}
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="chat__turns" aria-live="polite">
        {turns.map((turn) => (
          <article key={turn.id} className="chat__turn" data-testid="turn">
            <header className="chat__turn-head">
              <span className="mono muted">{t.you}</span>
              {turn.stored && <span className="chip chip--amber" data-testid="stored-tag">{t.stored}</span>}
            </header>
            <p className="chat__question">{turn.question}</p>
            {turn.pending && <p className="body-sm muted" role="status">{t.asking}</p>}
            {turn.error && (
              <p className="chat__notice chat__notice--warn" role="alert" data-testid="turn-error">
                {t.errors[turn.error.code] ?? turn.error.message ?? t.errors.unreachable}
              </p>
            )}
            {turn.answer && <Evidence answer={turn.answer} t={t} storedNote={turn.stored ? t.storedNote(turn.storedDate ?? null) : null} />}
          </article>
        ))}
      </section>

      <p className="body-sm muted chat__privacy">{t.privacy}</p>
    </main>
  );
}

function Evidence({ answer, t, storedNote }: { answer: AskAnswer; t: Labels; storedNote: string | null }) {
  const keyword = answer.mode.embedding !== "ok";
  return (
    <div className="chat__evidence">
      {storedNote && <p className="chat__notice" data-testid="stored-note">{storedNote}</p>}
      <p className={`chat__mode${keyword ? " chat__mode--keyword" : ""}`} data-testid="mode-line" data-mode={keyword ? "keyword" : "vector"}>
        {keyword ? t.modeKeyword : t.modeVector}
      </p>

      <h2 className="chat__block-title mono">{t.catalogue}</h2>
      {answer.mode.catalogue === "unavailable" ? (
        <p className="chat__notice chat__notice--warn" data-testid="catalogue-down">{t.catalogueDown}</p>
      ) : answer.issues.length === 0 ? (
        <p className="body-sm muted">{t.noIssues}</p>
      ) : (
        answer.issues.map((issue, index) => (
          <details key={issue.issue_id} className="evi-card evi-card--cobalt chat__issue" open={index === 0}>
            <summary>
              <strong>{issue.title || issue.issue_id}</strong>{" "}
              <span className="mono muted">{issue.issue_id} · {t.matchedBy} {issue.matched_by.join(", ")}</span>
            </summary>
            {issue.card && (
              <dl className="chat__facts">
                {Object.entries(issue.card.dates ?? {}).filter(([, v]) => v).map(([k, v]) => (
                  <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v}</dd></div>
                ))}
                {(issue.card.printers ?? []).length > 0 && <div><dt>{t.printers}</dt><dd>{(issue.card.printers ?? []).join("; ")}</dd></div>}
                {issue.card.perforation && <div><dt>{t.perforation}</dt><dd>{issue.card.perforation}</dd></div>}
                {(issue.card.acts ?? []).map((act, i) => (
                  <div key={i}><dt>{t.acts}</dt><dd>{[act.type, act.id, act.date].filter(Boolean).join(" · ")}</dd></div>
                ))}
                {(issue.card.stamps ?? []).length > 0 && (
                  <div>
                    <dt>{(issue.card.stamps ?? []).length} {t.stamps}</dt>
                    <dd>
                      {(issue.card.stamps ?? []).slice(0, 24).map((s) =>
                        [s.catalog_no, [s.value, s.unit].filter((x) => x !== null && x !== undefined && x !== "").join(" "), s.color, s.quantity]
                          .filter((x) => x !== null && x !== undefined && x !== "").join(", ")).join(" | ")}
                    </dd>
                  </div>
                )}
              </dl>
            )}
          </details>
        ))
      )}

      <h2 className="chat__block-title mono">{t.literature}</h2>
      {answer.mode.literature === "unavailable" ? (
        <p className="chat__notice chat__notice--warn" data-testid="literature-down">{t.literatureDown}</p>
      ) : answer.passages.length === 0 ? (
        <p className="body-sm muted">{t.noPassages}</p>
      ) : (
        answer.passages.map((p, i) => (
          <div key={i} className="evi-card" data-testid="passage">
            <div className="evi-card__meta">
              <strong className="body-sm">{p.doc_id}</strong>
              <span className="mono muted">{t.page} {p.page ?? "?"}</span>
              {p.clipped && <span className="chip">{t.clipped}</span>}
            </div>
            <p className="evi-card__text">{p.text}</p>
          </div>
        ))
      )}
    </div>
  );
}
