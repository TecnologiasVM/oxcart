"use client";

/*
 * The question page.
 *
 * - No account. The conversation is a thread of turns (question, written answer,
 *   evidence), oldest first, kept in this browser's local storage (lib/conversation.ts);
 *   the server keeps none of it. "Clear conversation" empties it.
 * - A question gets its evidence first and, a moment later, a short answer written from
 *   that evidence, each sentence with the sources it cites. When no answer can be written
 *   the turn says why in one line, and the evidence is still one step away.
 * - The box at the foot of the thread asks more about the newest answer: that follow-up is
 *   sent with the turns it follows (at most three), since this browser is the only memory
 *   the conversation has.
 * - Each answer has its Evidence button; Evidence opens beside the thread on a wide screen
 *   and over it below that (components/ask/EvidencePanel.tsx).
 * - Stored examples ship with the page (a static file): a visitor sees real evidence while
 *   the service wakes up, and when it is asleep or gone. They are marked as stored.
 * - A human check (Cloudflare Turnstile) runs once per session. It starts, out of sight, when
 *   the question box first takes focus; only a question sent before it has passed shows it,
 *   standing in that question's turn.
 * - The service sleeps when nobody uses it. While it wakes the page says so in short lines
 *   that follow one another, with a count of seconds.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ask, AskError, chat, liveExamples, MAX_QUESTION_CHARS, storedExamples, THREAD_ANSWER_CHARS, THREAD_TURNS,
} from "@/lib/ask";
import type { Example, StoredExample } from "@/lib/ask";
import { newId } from "@/lib/conversation";
import type { Turn } from "@/lib/conversation";
import { LABELS } from "@/lib/i18n";
import type { Labels, Lang } from "@/lib/i18n";
import EvidencePanel from "./ask/EvidencePanel";
import type { PanelFocus, TabKey } from "./ask/EvidencePanel";
import FirstScreen from "./ask/FirstScreen";
import { useConversation, useHeaderHeight, useHumanCheck, useMedia, useService } from "./ask/hooks";
import { answered, followed, HOW_URL, PrivacyLine, REPO_URL, textOf, Waiting, Warn } from "./ask/parts";
import TurnView from "./ask/TurnView";

const LANG_KEY = "oxcart-lang";
const HUMAN_CODES = ["session_required", "human_check_failed", "human_check_unavailable"];
const DAY_CODES = ["visitor_daily_limit", "service_daily_limit"];

export default function Chat() {
  const [lang, setLang] = useState<Lang>("en");
  const { turns, loaded, add, patch, clear } = useConversation();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false); // the day's limit: the box stays closed
  const [service, setService] = useService(busy);
  const [stored, setStored] = useState<StoredExample[]>([]);
  const [storedDate, setStoredDate] = useState<string | null>(null);
  const [examples, setExamples] = useState<Example[]>([]);
  const [evidence, setEvidence] = useState<{ turnId: string; focus: PanelFocus } | null>(null);
  const [tab, setTab] = useState<TabKey>("graph");
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const opened = useRef(0);
  const pinned = useRef(true); // the reader is at the foot of the thread
  const autoScrolled = useRef(0);
  const turnsNow = useRef<Turn[]>(turns);
  const check = useHumanCheck();
  const sheet = useMedia("(max-width: 1279px)");
  const t: Labels = LABELS[lang];
  useHeaderHeight();

  useEffect(() => {
    turnsNow.current = turns;
  }, [turns]);

  // --- the language this browser chose
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(LANG_KEY);
    } catch {
      /* storage blocked */
    }
    setLang(saved === "es" || saved === "en" ? saved : navigator.language.toLowerCase().startsWith("es") ? "es" : "en");
    setSlot(document.getElementById("masthead-page"));
  }, []);
  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* storage blocked: the choice lasts as long as the page */
    }
    document.documentElement.lang = lang;
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

  // --- while a turn arrives the reader stays at the foot of the thread: what grows, grows
  //     upward. A turn taller than the screen stops at its question, so it reads from its start.
  useEffect(() => {
    const onScroll = () => {
      if (performance.now() - autoScrolled.current < 150) return; // the page's own move, not the reader's
      const below = document.documentElement.scrollHeight - window.innerHeight - window.scrollY;
      pinned.current = below < 120;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useLayoutEffect(() => {
    if (!pinned.current || !turns.length) return;
    const last = document.querySelector<HTMLElement>(".thread > article:last-child");
    const header = document.querySelector<HTMLElement>("header.masthead");
    const covered = header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0;
    const foot = document.documentElement.scrollHeight - window.innerHeight;
    const question = last ? last.getBoundingClientRect().top + window.scrollY - covered - 16 : foot;
    autoScrolled.current = performance.now();
    window.scrollTo({ top: Math.max(0, Math.min(foot, question)) });
  }, [turns]);

  // --- Evidence over the conversation (below 1280 px): the page behind it is put out of reach
  const evTurn = evidence ? turns.find((turn) => turn.id === evidence.turnId && turn.answer) : undefined;
  const modal = Boolean(evTurn) && sheet;
  useEffect(() => {
    document.documentElement.classList.toggle("evp-lock", modal);
    const outside = [...document.querySelectorAll<HTMLElement>("header.masthead, footer.site-foot")];
    outside.forEach((el) => (el.inert = modal));
    return () => {
      document.documentElement.classList.remove("evp-lock");
      outside.forEach((el) => (el.inert = false));
    };
  }, [modal]);

  const closeEvidence = useCallback(() => {
    const turnId = evidence?.turnId;
    setEvidence(null);
    // focus goes back to what opened it, or to the answer's own button
    requestAnimationFrame(() => {
      const back = opener.current && document.body.contains(opener.current)
        ? opener.current
        : document.querySelector<HTMLElement>(`[data-evidence-for="${turnId}"]`);
      back?.focus();
    });
  }, [evidence]);

  const openEvidence = useCallback((turnId: string, el: HTMLElement, source?: number) => {
    if (source === undefined && evidence?.turnId === turnId) {
      closeEvidence(); // the open answer's own button closes it
      return;
    }
    opener.current = el;
    if (source !== undefined) setTab("sources");
    opened.current += 1;
    setEvidence({ turnId, focus: { source, nonce: opened.current } });
  }, [evidence, closeEvidence]);

  // --- asking
  const submit = useCallback(
    async (text: string) => {
      const q = text.replace(/\s+/g, " ").trim().slice(0, MAX_QUESTION_CHARS);
      if (!q || busy || closed) return;
      // a follow-up carries the turns it follows: what was searched for each, and what was answered
      const follows = followed(turnsNow.current);
      const thread = follows
        ? [...(follows.thread ?? []), { question: follows.answer?.question || follows.question, answer: textOf(follows.written).slice(0, THREAD_ANSWER_CHARS) }].slice(-THREAD_TURNS)
        : [];
      const id = newId("t");
      pinned.current = true;
      setBusy(true);
      setDraft("");
      add({ id, question: q, at: new Date().toISOString(), pending: true, ...(thread.length ? { thread } : {}) });
      const finish = (change: Partial<Turn>) => patch(id, { pending: false, ...change });

      // the evidence comes first and is shown at once; the written answer follows
      const answerWith = async (session: string | null) => {
        try {
          const { answer: written, calls } = await chat(q, thread, session, (answer, rewritten) => {
            setService("ready");
            finish({ answer, rewritten, writing: true });
          });
          finish({ written, calls, writing: false });
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "no_chat_route") throw e;
          finish({ answer: await ask(q, session) }); // a backend without the answer step: the evidence, as before
        }
      };
      const sessionFor = async (again = false) => {
        const result = await check.sessionFor(() => patch(id, { check: "waiting" }), again);
        if (check.needsCheck && !result.session) throw new AskError(result.code ?? "session_required", "", 0);
        patch(id, { check: undefined });
        return result.session;
      };
      try {
        let session = await sessionFor();
        try {
          await answerWith(session);
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "session_required" || !check.needsCheck) throw e;
          session = await sessionFor(true); // the token expired: one more check, one more try
          await answerWith(session);
        }
        setService("ready");
      } catch (e) {
        const err = e instanceof AskError ? e : new AskError("unreachable", "", 0);
        const human = HUMAN_CODES.includes(err.code);
        // a refusal came from a service that is up; no answer at all, from one that is not
        // (a human check that did not finish says nothing about the service)
        if (!human) setService(err.status > 0 ? "ready" : "unreachable");
        finish({ error: { code: err.code, message: err.message }, writing: false, check: human && check.needsCheck ? "failed" : undefined });
        setDraft(q); // the question goes back to the box: nothing is typed twice
        if (DAY_CODES.includes(err.code)) setClosed(true);
      } finally {
        setBusy(false);
      }
    },
    [busy, closed, add, patch, check, setService],
  );

  const showStored = (example: StoredExample) => {
    pinned.current = true;
    add({ id: newId("t"), question: example.question, at: new Date().toISOString(), answer: example.answer, stored: true, storedDate });
  };
  const pick = (example: Example) => {
    const saved = stored.find((s) => s.question === example.question);
    if (saved) showStored(saved);
    else submit(example.question);
  };
  const clearAll = () => {
    setEvidence(null);
    clear();
    window.scrollTo({ top: 0 });
  };

  const storedNote = (turn: Turn) => (turn.stored ? t.storedNote(turn.storedDate ?? null) : null);
  const waking = (service === "waking" || service === "connecting") && !busy;
  const follows = followed(turns);
  const left = MAX_QUESTION_CHARS - draft.length;
  const docked = Boolean(evTurn) && !sheet;

  const status = waking ? (
    <div className="wake" role="status" aria-label={t.wakeTitle} data-testid="service-starting">
      <Waiting service={service} t={t} from={0} />
      {stored.length > 0 && <p className="wait__hint">{t.waitExamples}</p>}
    </div>
  ) : service === "unreachable" && !busy ? (
    <div className="wake" data-testid="service-unreachable"><Warn text={t.unreachable} alert={false} /></div>
  ) : null;

  return (
    <>
      {slot && createPortal(<HeaderNav t={t} lang={lang} setLang={setLang} />, slot)}
      <main className={`ask${turns.length ? " ask--thread" : ""}${docked ? " ask--ev" : ""}`}>
        {turns.length === 0 ? (
          <>
            <FirstScreen t={t} draft={draft} setDraft={setDraft} submit={submit} busy={busy} closed={closed} examples={examples} stored={stored} pick={pick} onBoxFocus={check.warm} />
            {status && <div className="wake-pin">{status}</div>}
          </>
        ) : (
          <div className="conv" inert={modal}>
            <div className="conv__in">
              <h1 className="vh">{t.title}</h1>
              <section className="thread" aria-live="polite" aria-relevant="additions">
                {turns.map((turn, i) => (
                  <TurnView
                    key={turn.id}
                    turn={turn}
                    t={t}
                    newest={i === turns.length - 1}
                    service={service}
                    open={evidence?.turnId === turn.id && Boolean(evTurn)}
                    storedNote={storedNote(turn)}
                    busy={busy}
                    onEvidence={openEvidence}
                    attachCheck={check.attach}
                    onAskNow={submit}
                  />
                ))}
              </section>
              {turns.some((turn) => answered(turn.written)) && <p className="thread__note" data-testid="ai-note">{t.noteOnce}</p>}
              <p className="conv__end">
                <button type="button" className="linkbtn" onClick={clearAll} data-testid="clear">{t.clear}</button>
              </p>
            </div>
            <div className="dock">
              {status}
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit(draft);
                }}
              >
                <label className="label" htmlFor="q">{follows ? t.more : t.question}</label>
                <div className="composer__row">
                  <input
                    id="q"
                    type="text"
                    maxLength={MAX_QUESTION_CHARS}
                    placeholder={follows ? t.morePlaceholder : t.placeholder}
                    value={draft}
                    disabled={closed}
                    onChange={(e) => setDraft(e.target.value)}
                    onFocus={check.warm}
                    data-testid="composer-input"
                  />
                  <button type="submit" className="ask-btn ask-btn--primary" disabled={busy || closed || !draft.trim()}>
                    {busy ? t.asking : t.ask}
                  </button>
                </div>
                {left <= 60 && <p className="composer__left" data-testid="chars-left">{t.left(left)}</p>}
              </form>
              <PrivacyLine t={t} />
            </div>
          </div>
        )}
        {check.needsCheck && <div className="check-host" ref={check.host} inert aria-hidden="true" data-testid="check-host" />}
        {evTurn && (
          <>
            {sheet && <div className="evp-backdrop" onClick={closeEvidence} aria-hidden="true" />}
            <EvidencePanel
              turn={evTurn}
              t={t}
              lang={lang}
              tab={tab}
              onTab={setTab}
              onClose={closeEvidence}
              sheet={sheet}
              focus={evidence!.focus}
              storedNote={storedNote(evTurn)}
            />
          </>
        )}
      </main>
    </>
  );
}

/** The question page's part of the header: how it works, the source, and the language. */
function HeaderNav({ t, lang, setLang }: { t: Labels; lang: Lang; setLang: (lang: Lang) => void }) {
  return (
    <nav className="page-nav" aria-label="Oxcart">
      <a className="page-nav__link" href={HOW_URL}>{t.how}</a>
      <a className="page-nav__link" href={REPO_URL}>{t.code}</a>
      <button type="button" className="lang-btn" lang={lang === "es" ? "en" : "es"} onClick={() => setLang(lang === "es" ? "en" : "es")} data-testid="lang-toggle">
        {t.language}
      </button>
    </nav>
  );
}

