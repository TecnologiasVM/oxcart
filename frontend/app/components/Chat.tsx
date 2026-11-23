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
 * - A human check (Cloudflare Turnstile) runs once per session. It starts when the question box
 *   first takes focus and stays invisible unless it needs a click; only a question sent before
 *   it has passed shows its words, under that question.
 * - In a build with NEXT_PUBLIC_WEB on, an answer whose sources cover part of the question, or none
 *   of it, can get a web part: asked once, by this page, after the answer is on screen, and drawn
 *   last in its turn (lib/web.ts). It is kept with the turn and never sent with a follow-up.
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
import { askWeb, ticketOf, withoutTicket } from "@/lib/web";
import type { Turn } from "@/lib/conversation";
import { LABELS } from "@/lib/i18n";
import type { Labels, Lang } from "@/lib/i18n";
import EvidencePanel from "./ask/EvidencePanel";
import type { PanelFocus, TabKey } from "./ask/EvidencePanel";
import FirstScreen from "./ask/FirstScreen";
import Conversations, { RAIL_ID } from "./ask/Conversations";
import { useConversations, useHeaderHeight, useHumanCheck, useMedia, usePinnedEdges, useService } from "./ask/hooks";
import { answered, Confirm, followed, HOW_URL, KeepNote, PrivacyLine, REPO_URL, textOf, Waiting, Warn } from "./ask/parts";
import TurnView from "./ask/TurnView";

const LANG_KEY = "oxcart-lang";
const RAIL_KEY = "oxcart-rail"; // "hidden" when the visitor hid the rail; kept with the language
const HUMAN_CODES = ["session_required", "human_check_failed", "human_check_unavailable"];
const DAY_CODES = ["visitor_daily_limit", "service_daily_limit"];

export default function Chat() {
  const [lang, setLang] = useState<Lang>("en");
  const conv = useConversations();
  const { turns, loaded, add, patch } = conv;
  const [railHidden, setRailHidden] = useState(false);
  const [convsOpen, setConvsOpen] = useState(false); // the list as a sheet, below 1100 px
  const [confirmOne, setConfirmOne] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const deleteOneRef = useRef<HTMLButtonElement | null>(null);
  const deleteAllRef = useRef<HTMLButtonElement | null>(null);
  const convsButton = useRef<HTMLButtonElement | null>(null);
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
  const railRoom = useMedia("(min-width: 1100px)");
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
    try {
      setRailHidden(window.localStorage.getItem(RAIL_KEY) === "hidden");
    } catch {
      /* storage blocked: the rail shows */
    }
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
  const arrived = useRef("");
  useLayoutEffect(() => {
    // what a turn has received so far. The web part is left out: it arrives under an answer already on
    // screen, and nothing on screen moves for it, so the page does not scroll when it comes
    const now = turns.map((x) => `${x.id}:${[x.pending, x.answer, x.writing, x.written, x.error, x.check].map((v) => (v ? 1 : 0)).join("")}`).join("|");
    const changed = now !== arrived.current;
    arrived.current = now;
    if (!changed || !pinned.current || !turns.length) return;
    const last = document.querySelector<HTMLElement>(".thread > article:last-child");
    const header = document.querySelector<HTMLElement>("header.masthead");
    const covered = header && getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0;
    const foot = document.documentElement.scrollHeight - window.innerHeight;
    const question = last ? last.getBoundingClientRect().top + window.scrollY - covered - 16 : foot;
    autoScrolled.current = performance.now();
    window.scrollTo({ top: Math.max(0, Math.min(foot, question)) });
  }, [turns]);

  // --- Evidence or the list of conversations over the page: what is behind it is put out of reach
  const evTurn = evidence ? turns.find((turn) => turn.id === evidence.turnId && turn.answer) : undefined;
  const modal = (Boolean(evTurn) && sheet) || convsOpen;
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

  const openEvidence = useCallback((turnId: string, el: HTMLElement, source?: number, figures?: number) => {
    if (source === undefined && figures === undefined && evidence?.turnId === turnId) {
      closeEvidence(); // the open answer's own button closes it
      return;
    }
    opener.current = el;
    if (source !== undefined) setTab("sources");
    else if (figures !== undefined) setTab("found"); // a page's figures stand with its passage
    opened.current += 1;
    setEvidence({ turnId, focus: { source, figures, nonce: opened.current } });
  }, [evidence, closeEvidence]);

  // --- the kept conversations
  useEffect(() => {
    if (railRoom) setConvsOpen(false); // the screen grew past the rail's width: the rail stands, no sheet
  }, [railRoom]);
  const focusLater = (el: () => HTMLElement | null | undefined) => requestAnimationFrame(() => el()?.focus());
  const leaveConversation = () => {
    // Evidence belongs to an answer of the conversation that is left: it closes
    setEvidence(null);
    setConfirmOne(false);
    setConfirmAll(false);
    pinned.current = true;
  };
  const openConversation = (id: string) => {
    leaveConversation();
    conv.open(id);
    if (convsOpen) {
      setConvsOpen(false);
      focusLater(() => convsButton.current);
    }
  };
  const newConversation = () => {
    leaveConversation();
    conv.start();
    setConvsOpen(false);
    focusLater(() => document.getElementById("q"));
  };
  const rememberRail = (hidden: boolean) => {
    setRailHidden(hidden);
    try {
      window.localStorage.setItem(RAIL_KEY, hidden ? "hidden" : "open");
    } catch {
      /* storage blocked: the choice lasts as long as the page */
    }
  };
  const hideRail = () => {
    rememberRail(true);
    focusLater(() => convsButton.current); // "Conversations" stands where "Hide" was
  };
  /** "Conversations" in the bar: the rail comes back where there is room for it, else the list opens as a sheet. */
  const showConversations = () => {
    if (window.matchMedia("(min-width: 1100px)").matches) {
      if (railHidden) rememberRail(false);
      // between 1280 and 1599 px the rail stands aside for docked Evidence: it comes back when Evidence closes
      if (window.matchMedia("(max-width: 1599px)").matches) setEvidence(null);
      focusLater(() => document.querySelector<HTMLElement>(`#${RAIL_ID} [aria-current="true"], #${RAIL_ID} .newbtn`));
    } else {
      setConvsOpen(true);
    }
  };
  const closeConversations = () => {
    setConvsOpen(false);
    setConfirmAll(false);
    focusLater(() => convsButton.current);
  };
  const deleteThis = () => {
    leaveConversation();
    conv.remove(conv.current);
    focusLater(() => document.getElementById("q"));
  };
  const deleteAll = () => {
    leaveConversation();
    conv.removeAll();
    setConvsOpen(false);
    focusLater(() => document.getElementById("q"));
  };

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
          let searched = q;
          const { answer: written, calls } = await chat(q, thread, session, (answer, rewritten) => {
            setService("ready");
            searched = answer.question || q;
            finish({ answer, rewritten, writing: true });
          });
          // the ticket is used here, once, and is not kept: a turn read back never asks for the web
          const ticket = ticketOf(written);
          finish({ written: withoutTicket(written), calls, writing: false, ...(ticket ? { web: { state: "searching" as const } } : {}) });
          setBusy(false); // with the answer on the page, so the box takes the next question at once
          if (ticket) {
            // after the answer is on screen: a frame for it to be drawn, then the request
            void new Promise<void>((resolve) => requestAnimationFrame(() => setTimeout(resolve, 0)))
              .then(() => askWeb(searched, written.state === "ok" ? textOf(written) : "", ticket, session))
              .then((web) => patch(id, { web }));
          }
        } catch (e) {
          if (!(e instanceof AskError) || e.code !== "no_chat_route") throw e;
          finish({ answer: await ask(q, session) }); // a backend without the answer step: the evidence, as before
          setBusy(false);
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

  const storedNote = (turn: Turn) => (turn.stored ? t.storedNote(turn.storedDate ?? null) : null);
  const waking = (service === "waking" || service === "connecting") && !busy;
  const follows = followed(turns);
  const left = MAX_QUESTION_CHARS - draft.length;
  const docked = Boolean(evTurn) && !sheet;
  const hasList = conv.list.length > 0;
  // what is pinned changes with the thread, the rail and Evidence: measured again each time
  usePinnedEdges(`${turns.length > 0}|${hasList}|${railHidden}|${docked}|${convsOpen}`);

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
      <main
        className={`ask${turns.length ? " ask--thread" : ""}${docked ? " ask--ev" : ""}${
          hasList ? (railHidden ? " ask--norail" : " ask--rail") : ""}${convsOpen ? " ask--convs" : ""}`}
      >
        {hasList || convsOpen ? (
          <Conversations
            t={t}
            list={conv.list}
            current={conv.current}
            keeping={conv.keeping}
            sheet={convsOpen}
            behind={Boolean(evTurn) && sheet}
            confirmAll={confirmAll}
            deleteAllRef={deleteAllRef}
            onOpen={openConversation}
            onNew={newConversation}
            onHide={hideRail}
            onClose={closeConversations}
            onAskDeleteAll={() => setConfirmAll(true)}
            onDeleteAll={deleteAll}
            onKeepAll={() => {
              setConfirmAll(false);
              focusLater(() => deleteAllRef.current);
            }}
          />
        ) : null}
        {/* the first screen and the thread share one frame, so the human check's element, its
            second child, stays the same element from the box's first focus on: its widget is
            never moved, and CSS places it under the box or under the newest turn */}
        <div className={`conv${turns.length ? "" : " conv--first"}`} inert={modal}>
          {/* where there is no rail: the bar "Conversations / New", and a storage line under it */}
          <div className="convbar">
            <div className="threadbar">
              <button type="button" ref={convsButton} className="tb" aria-expanded={convsOpen} aria-controls={RAIL_ID} onClick={showConversations} data-testid="conversations-button">
                <span className="tb__glyph" aria-hidden="true" />{t.convsBtn}
              </button>
              <button type="button" className="tb" onClick={newConversation} data-testid="new-short">
                <span aria-hidden="true">+</span> {t.newShort}<span className="vh"> ({t.newConv})</span>
              </button>
            </div>
            {conv.keeping !== "kept" && turns.length > 0 && <div className="strip"><KeepNote text={conv.keeping === "full" ? t.noRoom : t.notKept} /></div>}
          </div>
          {turns.length === 0 ? (
            <>
              <FirstScreen
                t={t} draft={draft} setDraft={setDraft} submit={submit} busy={busy} closed={closed} examples={examples} stored={stored}
                pick={pick} onBoxFocus={check.warm} mine={conv.list} onOpen={openConversation} onAll={() => setConvsOpen(true)}
              />
              {status && <div className="wake-pin">{status}</div>}
            </>
          ) : (
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
                    onAskNow={submit}
                  />
                ))}
              </section>
            </div>
          )}
          {check.needsCheck && (
            // page 22: the check's words, and its room kept while a sent question waits for it
            <div className={`check${check.waiting ? " check--waiting" : ""}`} data-testid="check">
              {(check.waiting || check.asking) && <p className="check__say">{t.humanCheck}</p>}
              <div className="check__widget" ref={check.host} data-testid="check-host" />
              {check.waiting && <p className="wait__line" role="status">{t.humanWaiting}</p>}
            </div>
          )}
          {turns.length > 0 && (
            <div className="conv__foot">
              {turns.some((turn) => answered(turn.written)) && <p className="thread__note" data-testid="ai-note">{t.noteOnce}</p>}
              <div className="conv__end">
                {confirmOne ? (
                  <Confirm
                    text={t.delAsk} yes={t.delYes} no={t.delNo} onYes={deleteThis} testId="confirm-one"
                    onNo={() => {
                      setConfirmOne(false);
                      focusLater(() => deleteOneRef.current);
                    }}
                  />
                ) : (
                  <button type="button" ref={deleteOneRef} className="linkbtn" onClick={() => setConfirmOne(true)} data-testid="delete-one">{t.delOne}</button>
                )}
              </div>
            </div>
          )}
          {turns.length > 0 && (
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
          )}
        </div>
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

