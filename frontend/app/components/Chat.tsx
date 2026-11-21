"use client";

/*
 * The chat page: one question box, and under it the conversation so far.
 *
 * - No account. The conversation is a list of turns (question, written answer,
 *   evidence) kept in this browser's local storage, so a returning visitor sees it
 *   again. "Clear" empties it.
 * - A question gets its evidence first and, a moment later, a short answer written
 *   from that evidence, each sentence with the cards and passages it cites. When no
 *   answer can be written the page says so in one line and shows the evidence.
 * - Under the newest answer a second box asks more about it. That follow-up is sent
 *   with the last turns it follows (at most three): this browser is the only memory
 *   the conversation has, the server keeps none.
 * - Stored examples ship with the page (a static file): a visitor sees real
 *   evidence while the service wakes up, and when it is asleep or gone. They are
 *   marked as stored.
 * - Before the first question a human check (Cloudflare Turnstile) runs once; the
 *   backend answers it with a short-lived token that is sent with each question.
 * - Every answer says which mode produced it (search by meaning, or keyword mode).
 * - The service sleeps when nobody uses it. While it wakes, the page says so in short
 *   lines that follow one another (waking, connecting, searching) with a count of
 *   seconds, so a long first wait does not look like a fault.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ask, AskError, chat, liveExamples, MAX_QUESTION_CHARS, openSession, serviceState, storedExamples,
  THREAD_ANSWER_CHARS, THREAD_TURNS, TURNSTILE_SITE_KEY,
} from "@/lib/ask";
import type { AskAnswer, Example, ServiceState, StoredExample, ThreadTurn, WrittenAnswer } from "@/lib/ask";
import { LABELS } from "@/lib/i18n";
import type { Labels, Lang } from "@/lib/i18n";

const HISTORY_KEY = "oxcart-chat-v1";
const LANG_KEY = "oxcart-lang";
const SESSION_KEY = "oxcart-session";
const MAX_TURNS = 30;
const POLL_EVERY_MS = 2000;
const WAIT_LINES_AFTER_SECONDS = 3; // a question that is answered sooner shows "Searching…" and nothing else

type Turn = {
  id: string;
  question: string;
  at: string;
  answer?: AskAnswer;
  written?: WrittenAnswer; // the answer written from the evidence, or why there is none
  writing?: boolean; // the evidence is here and the answer is being written
  thread?: ThreadTurn[]; // the turns this question follows, as they were sent with it
  after?: string; // the question it follows, to say so on the page
  rewritten?: boolean; // the follow-up was made into a question that stands alone before the search
  stored?: boolean;
  storedDate?: string | null;
  error?: { code: string; message: string };
  pending?: boolean;
};

type Service = "checking" | "waking" | "connecting" | "ready" | "unreachable";

const fromState = (state: ServiceState): Service => (state === "ready" ? "ready" : state === "connecting" ? "connecting" : "waking");
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
    // a turn that was being written when the page closed has its evidence and no answer
    return Array.isArray(turns) ? turns.filter((t) => t && t.question && (t.answer || t.error)).map((t) => ({ ...t, writing: false })) : [];
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
  const [more, setMore] = useState("");
  const [busy, setBusy] = useState(false);
  const [service, setService] = useState<Service>("checking");
  const [stored, setStored] = useState<StoredExample[]>([]);
  const [storedDate, setStoredDate] = useState<string | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [session, setSession] = useState<string | null>(null);
  const [checkNote, setCheckNote] = useState<string | null>(null);
  // the list of questions to try: open while there is no conversation, folded once there is one,
  // so a new question's evidence is not below a list; the visitor's own click wins until the next question
  const [examplesChoice, setExamplesChoice] = useState<boolean | null>(null);
  const newestTurn = useRef<HTMLElement | null>(null);
  const seenTurn = useRef<string | null | undefined>(null);
  const widgetRef = useRef<HTMLDivElement | null>(null);
  const widgetId = useRef<string | null>(null);
  const waiting = useRef<((session: string | null) => void) | null>(null);
  const t: Labels = LABELS[lang];
  const needsCheck = Boolean(TURNSTILE_SITE_KEY);
  const examplesOpen = examplesChoice ?? turns.length === 0;

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

  // --- a new question is brought into view (the conversation found when the page opens is not)
  const newestId = turns[0]?.id;
  useEffect(() => {
    if (!loaded) return;
    if (seenTurn.current !== null && newestId && newestId !== seenTurn.current) {
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      newestTurn.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "nearest" });
    }
    seenTurn.current = newestId;
  }, [newestId, loaded]);

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

  // --- while a question waits, keep looking at where the service is: a page left open
  //     finds it asleep again, and the waiting lines must say what is true now
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
    async (text: string, follows?: Turn) => {
      const q = text.replace(/\s+/g, " ").trim().slice(0, MAX_QUESTION_CHARS);
      if (!q || busy) return;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      // a follow-up carries the turns it follows: what was searched for each, and what was answered
      const thread: ThreadTurn[] = follows
        ? [...(follows.thread ?? []), { question: follows.answer?.question || follows.question, answer: textOf(follows.written).slice(0, THREAD_ANSWER_CHARS) }].slice(-THREAD_TURNS)
        : [];
      setBusy(true);
      setQuestion("");
      setMore("");
      setExamplesChoice(null);
      setTurns((prev) => [
        { id, question: q, at: new Date().toISOString(), pending: true, ...(follows ? { thread, after: follows.question } : {}) },
        ...prev,
      ]);
      const finish = (patch: Partial<Turn>) =>
        setTurns((prev) => prev.map((turn) => (turn.id === id ? { ...turn, pending: false, ...patch } : turn)));
      // the evidence comes first and is shown at once; the written answer follows
      const answered = async (s: string | null) => {
        try {
          const written = await chat(q, thread, s, (answer, rewritten) => {
            setService("ready");
            finish({ answer, rewritten, writing: true });
          });
          finish({ written, writing: false });
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "no_chat_route") throw e;
          finish({ answer: await ask(q, s) }); // a backend without the answer step: the evidence, as before
        }
      };
      try {
        let s = await sessionForAsk();
        if (needsCheck && !s) throw new AskError("session_required", "", 401);
        try {
          await answered(s);
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "session_required" || !needsCheck) throw e;
          window.sessionStorage.removeItem(SESSION_KEY); // the token expired: one more check, one more try
          s = await sessionForAsk();
          if (!s) throw e;
          await answered(s);
        }
        setService("ready");
      } catch (e) {
        const err = e instanceof AskError ? e : new AskError("unreachable", "", 0);
        // a refusal came from a service that is up; no answer at all, from one that is not
        // (a human check that did not finish says nothing about the service)
        if (err.code !== "session_required") setService(err.status > 0 ? "ready" : "unreachable");
        finish({ error: { code: err.code, message: err.message }, writing: false });
      } finally {
        setBusy(false);
      }
    },
    [busy, needsCheck, sessionForAsk],
  );

  const showStored = (example: StoredExample) => {
    setExamplesChoice(null);
    setTurns((prev) => [
      { id: `stored-${Date.now()}`, question: example.question, at: new Date().toISOString(), answer: example.answer, stored: true, storedDate },
      ...prev,
    ]);
  };

  const pick = (example: Example) => {
    const saved = stored.find((s) => s.question === example.question);
    if (saved) showStored(saved);
    else submit(example.question);
  };

  const clear = () => {
    setTurns([]);
    setExamplesChoice(null);
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

      {(service === "waking" || service === "connecting") && !busy && (
        <div className="chat__notice" role="status" data-testid="service-starting">
          <Waiting service={service} t={t} from={0} />
          {stored.length > 0 && <p className="chat__wait-hint">{t.waitExamples}</p>}
        </div>
      )}
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
          <button
            type="button"
            className="chat__examples-toggle mono muted"
            aria-expanded={examplesOpen}
            aria-controls="chat-example-list"
            onClick={() => setExamplesChoice(!examplesOpen)}
            data-testid="examples-toggle"
          >
            <span aria-hidden="true">{examplesOpen ? "▾" : "▸"}</span> {t.examples}
            {!examplesOpen && <span> ({examples.length})</span>}
          </button>
          {examplesOpen && (
            <div id="chat-example-list" className="chat__example-list">
              {examples.map((example) => (
                <button key={example.question} type="button" className="chat__example" onClick={() => pick(example)} disabled={busy}>
                  {example.question}
                  {stored.some((s) => s.question === example.question) && <span className="chip chat__stored-chip">{t.stored}</span>}
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      <section className="chat__turns" aria-live="polite">
        {turns.map((turn, i) => (
          <article key={turn.id} className="chat__turn" data-testid="turn" ref={i === 0 ? newestTurn : undefined}>
            <header className="chat__turn-head">
              <span className="mono muted">{t.you}</span>
              {turn.stored && <span className="chip chip--amber" data-testid="stored-tag">{t.stored}</span>}
            </header>
            {turn.after && <p className="body-sm muted chat__follows" data-testid="follows">{t.follows} “{turn.after}”</p>}
            <p className="chat__question">{turn.question}</p>
            {turn.rewritten && turn.answer && (
              <p className="body-sm muted chat__follows" data-testid="searched-as">{t.searchedAs} “{turn.answer.question}”</p>
            )}
            {turn.pending && <div className="chat__progress" aria-hidden="true" data-testid="searching-bar" />}
            {turn.pending && <Waiting service={service} t={t} from={WAIT_LINES_AFTER_SECONDS} searching />}
            {turn.error && (
              <p className="chat__notice chat__notice--warn" role="alert" data-testid="turn-error">
                {t.errors[turn.error.code] ?? turn.error.message ?? t.errors.unreachable}
              </p>
            )}
            {turn.answer && <Written turn={turn} t={t} />}
            {turn.answer && <Evidence turn={turn} answer={turn.answer} t={t} storedNote={turn.stored ? t.storedNote(turn.storedDate ?? null) : null} />}
            {i === 0 && turn.answer && !turn.writing && (
              <form
                className="chat__more"
                data-testid="follow-up"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit(more, turn);
                }}
              >
                <label className="mono" htmlFor="chat-more">{t.more}</label>
                <div className="chat__more-row">
                  <input
                    id="chat-more"
                    className="input"
                    type="text"
                    maxLength={MAX_QUESTION_CHARS}
                    placeholder={t.morePlaceholder}
                    value={more}
                    onChange={(e) => setMore(e.target.value)}
                  />
                  <button type="submit" className="btn btn--ghost" disabled={busy || !more.trim()}>{t.ask}</button>
                </div>
              </form>
            )}
          </article>
        ))}
      </section>

      <p className="body-sm muted chat__privacy">{t.privacy}</p>
    </main>
  );
}

/*
 * What the visitor reads while waiting: short lines that follow one another, the last
 * one with a running count of seconds.
 *
 *   Waking the service… 7 s            (no answer from the service yet)
 *   ✓ The service is awake.
 *   Connecting to the catalogue and the literature… 19 s
 *   ✓ Catalogue and literature connected.
 *   Searching… 22 s                    (only when a question is waiting)
 *
 * The lines follow what the health route says, not a timer. `from` is how many seconds
 * pass before the lines appear: a question that is answered at once shows "Searching…".
 */
function Waiting({ service, t, from, searching = false }: { service: Service; t: Labels; from: number; searching?: boolean }) {
  const stage = service === "ready" ? 2 : service === "connecting" ? 1 : 0;
  const [seconds, setSeconds] = useState(0);
  const [first, setFirst] = useState(stage); // the earliest stage seen in this wait
  if (stage < first) setFirst(stage);
  useEffect(() => {
    const started = Date.now();
    const id = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  if (seconds < from) return <p className="body-sm muted" role="status">{t.asking}</p>;

  const done = [t.waitAwake, t.waitConnected].slice(Math.min(first, stage), stage);
  const now = stage === 0 ? t.waitWaking : stage === 1 ? t.waitConnecting : searching ? t.asking : null;
  return (
    <div className="chat__wait" data-testid="waiting">
      {done.map((line) => (
        <p key={line} className="muted">✓ {line}</p>
      ))}
      {now && (
        <p role="status">
          {now} <span className="mono muted" aria-hidden="true" data-testid="waiting-seconds">{t.seconds(seconds)}</span>
        </p>
      )}
      {stage < 2 && <p className="chat__wait-hint">{t.waitHint}</p>}
    </div>
  );
}

/** The text of a written answer, as it is sent back with a follow-up. */
function textOf(written?: WrittenAnswer): string {
  return (written?.sentences ?? []).map((sentence) => sentence.text).join(" ");
}

/** Where a cited card or passage is on the page. */
const anchor = (turnId: string, kind: string, index: number) => `t${turnId}-${kind}-${index}`;

/*
 * The answer written from the evidence: its sentences, each followed by the numbers of
 * the sources it cites, then those sources with the text they were cited for. A number
 * leads to the card or passage below. When nothing was written, one line says why.
 */
function Written({ turn, t }: { turn: Turn; t: Labels }) {
  if (turn.writing) {
    return (
      <div className="chat__answer" data-testid="writing">
        <div className="chat__progress" aria-hidden="true" />
        <p className="body-sm muted" role="status">{t.writing}</p>
      </div>
    );
  }
  const written = turn.written;
  if (!written) return null;
  if (written.state === "not_covered") return <p className="chat__notice" data-testid="not-covered">{t.notCovered}</p>;
  if (written.state !== "ok" || !written.sentences?.length) {
    return <p className="body-sm muted chat__no-answer" data-testid="no-written-answer">{written.state === "daily_cap" ? t.answerCap : t.noAnswer}</p>;
  }
  const sources = written.sources ?? [];
  const href = (n: number) => {
    const source = sources.find((s) => s.n === n);
    return source ? `#${anchor(turn.id, source.kind, source.index)}` : undefined;
  };
  return (
    <div className="chat__answer" data-testid="written-answer">
      <h2 className="chat__block-title mono">{t.answer}</h2>
      <p className="chat__answer-text">
        {written.sentences.map((sentence, i) => (
          <span key={i} data-testid="answer-sentence">
            {sentence.text}
            {sentence.cites.map((n) => (
              <a key={n} className="chat__cite mono" href={href(n)} aria-label={`${t.source} ${n}`}>[{n}]</a>
            ))}{" "}
          </span>
        ))}
      </p>
      <ol className="chat__sources" aria-label={t.sources}>
        {sources.map((source) => (
          <li key={source.n} data-testid="answer-source">
            <a className="mono" href={`#${anchor(turn.id, source.kind, source.index)}`}>[{source.n}] {source.title}</a>
            {source.quotes.map((quote, i) => (
              <q key={i} className="chat__quote">{quote}</q>
            ))}
          </li>
        ))}
      </ol>
      <p className="body-sm muted">{t.answerNote}</p>
    </div>
  );
}

function Evidence({ turn, answer, t, storedNote }: { turn: Turn; answer: AskAnswer; t: Labels; storedNote: string | null }) {
  const keyword = answer.mode.embedding !== "ok";
  const sources = turn.written?.state === "ok" ? turn.written.sources ?? [] : [];
  const cited = (kind: string, index: number) => sources.find((s) => s.kind === kind && s.index === index)?.n;
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
          <details key={issue.issue_id} id={anchor(turn.id, "issue", index)} className="evi-card evi-card--cobalt chat__issue" open={index === 0 || cited("issue", index) !== undefined}>
            <summary>
              {cited("issue", index) !== undefined && <span className="chip chat__cited mono">[{cited("issue", index)}]</span>}{" "}
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
          <div key={i} id={anchor(turn.id, "passage", i)} className="evi-card" data-testid="passage">
            <div className="evi-card__meta">
              {cited("passage", i) !== undefined && <span className="chip chat__cited mono">[{cited("passage", i)}]</span>}
              <strong className="body-sm">{p.doc_id}</strong>
              <span className="mono muted">{t.page} {p.page ?? "?"}</span>
              {p.clipped && <span className="chip">{t.clipped}</span>}
            </div>
            {p.text ? <p className="evi-card__text">{p.text}</p> : <p className="body-sm muted" data-testid="passage-no-text">{t.noText}</p>}
          </div>
        ))
      )}
    </div>
  );
}
