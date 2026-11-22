"use client";

/*
 * One turn of the thread: the visitor's question, then what came back for it.
 *
 * The compact rule: the newest answer has the list of its sources above its Evidence
 * button; an older answer keeps its text, its numbered marks and one Evidence button with
 * the number of its sources. A turn with no written answer keeps its notice and the button
 * "What was found". No answer is ever shown without a way to its evidence.
 *
 * Everything the model wrote (sentences, titles, quotes) is a text node. The page builds
 * only the marks and one wrapper that keeps a sentence's last word with its marks, so a
 * mark never starts a line.
 */
import type { ReactNode } from "react";
import type { AnswerSentence } from "@/lib/ask";
import type { Turn } from "@/lib/conversation";
import type { Labels } from "@/lib/i18n";
import type { Service } from "./hooks";
import { WAIT_LINES_AFTER_SECONDS } from "./hooks";
import { answered, Bar, Notice, PANEL_ID, Waiting, Warn } from "./parts";

type Props = {
  turn: Turn;
  t: Labels;
  newest: boolean;
  service: Service;
  open: boolean; // this turn's Evidence is open
  storedNote: string | null;
  busy: boolean;
  onEvidence: (turnId: string, opener: HTMLElement, source?: number) => void;
  attachCheck: (el: HTMLDivElement | null) => void;
  onAskNow: (question: string) => void;
};

export default function TurnView({ turn, t, newest, service, open, storedNote, busy, onEvidence, attachCheck, onAskNow }: Props) {
  const errorText = turn.error ? t.errors[turn.error.code] ?? (turn.error.message || t.errors.unreachable) : "";
  return (
    <article className={`turn${newest ? "" : " turn--old"}`} aria-labelledby={`q-${turn.id}`} data-testid="turn" data-turn={turn.id}>
      <header className="turn__q">
        <p className="label">{t.you}</p>
        <h2 className="turn__text" id={`q-${turn.id}`}>{turn.question}</h2>
        {turn.stored && <span className="ask-chip" data-testid="stored-tag">{t.stored}</span>}
        {turn.rewritten && turn.answer && <p className="turn__as" data-testid="searched-as">{t.searchedAs} “{turn.answer.question}”</p>}
      </header>
      {turn.check ? (
        // the human check stands in the turn, with its widget's room kept so nothing moves when it goes
        <section className="a a--wait">
          {turn.check === "failed" && <Warn text={errorText} testId="turn-error" />}
          {turn.check === "waiting" && <p className="check__say">{t.humanCheck}</p>}
          <div className="turnstile" ref={attachCheck} data-testid="human-check" />
          {turn.check === "waiting" && <p className="wait__line" role="status">{t.humanWaiting}</p>}
        </section>
      ) : turn.pending ? (
        <section className="a a--wait">
          <Bar testId="searching-bar" />
          <Waiting service={service} t={t} from={WAIT_LINES_AFTER_SECONDS} searching />
        </section>
      ) : turn.error ? (
        <section className="a a--wait"><Warn text={errorText} testId="turn-error" /></section>
      ) : turn.answer ? (
        <Answered turn={turn} t={t} newest={newest} open={open} storedNote={storedNote} busy={busy} onEvidence={onEvidence} onAskNow={onAskNow} />
      ) : null}
    </article>
  );
}

function Answered({ turn, t, newest, open, storedNote, busy, onEvidence, onAskNow }: Omit<Props, "service" | "attachCheck">) {
  const evidence = turn.answer!;
  const written = turn.written;
  const ok = !turn.writing && answered(written);
  const counts = ok && !newest
    ? t.nSources(written?.sources?.length ?? 0)
    : [ok ? t.nSources(written?.sources?.length ?? 0) : "", t.nCards(evidence.issues.length), t.nPassages(evidence.passages.length)].filter(Boolean).join(" · ");
  const evrow = (
    <p className="evrow">
      <button
        type="button"
        className="evbtn"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        data-testid="evidence-button"
        data-evidence-for={turn.id}
        onClick={(e) => onEvidence(turn.id, e.currentTarget)}
      >
        {ok ? t.evBtn : t.evBtnFound}
        {open && <span className="evbtn__state" aria-hidden="true">· {t.evOpen}</span>}
      </button>
      <span className="evrow__counts">{counts}</span>
    </p>
  );
  // a part of the evidence that is missing, or a weaker search, is said in the turn and not only inside Evidence
  const parts = newest && (
    <>
      {evidence.mode.embedding !== "ok" && <Warn inline alert={false} text={t.modeKeyword} testId="turn-keyword" />}
      {evidence.mode.catalogue === "unavailable" && <Warn inline alert={false} text={t.catalogueDown} testId="turn-catalogue-down" />}
      {evidence.mode.literature === "unavailable" && <Warn inline alert={false} text={t.literatureDown} testId="turn-literature-down" />}
    </>
  );
  const found = newest && (
    <div className="a__src">
      <p className="label">{t.foundTitles}</p>
      <ul className="foundnames">
        {evidence.issues.map((issue, i) => (
          <li key={`i${i}`}><span className="foundnames__kind">{t.catalogue}</span><span>{issue.title || issue.issue_id}</span></li>
        ))}
        {evidence.passages.map((p, i) => (
          <li key={`p${i}`}><span className="foundnames__kind">{t.literature}</span><span>{p.doc_id ?? "?"}, {t.page} {p.page ?? "?"}</span></li>
        ))}
      </ul>
    </div>
  );

  if (turn.writing) {
    return (
      <section className="a">
        <p className="label">{t.answer}</p>
        <div className="a__wait" data-testid="writing">
          <Bar />
          <p className="wait__line" role="status">{t.writing}</p>
        </div>
        {parts}
        <div className="a__foot">{evrow}</div>
      </section>
    );
  }

  if (ok) {
    const sources = written?.sources ?? [];
    const mark = (n: number) => (
      <button key={n} type="button" className="mark" aria-label={`${t.source} ${n}`} data-testid="source-mark" onClick={(e) => onEvidence(turn.id, e.currentTarget, n)}>
        {n}
      </button>
    );
    return (
      <section className={`a${newest ? "" : " a--old"}`} data-testid="written-answer">
        <p className="label">{t.answerBy}</p>
        <div className="a__body">
          <p className="a__text">
            {(written?.sentences ?? []).map((sentence, i) => <Sentence key={i} sentence={sentence} mark={mark} />)}
          </p>
        </div>
        {newest ? (
          <>
            {parts}
            <div className="a__foot">
              <div className="a__src">
                <p className="label">{t.sources}</p>
                <ol className="srcnames">
                  {sources.map((source) => (
                    <li key={source.n} data-testid="answer-source">{mark(source.n)}<span>{source.title}</span></li>
                  ))}
                </ol>
              </div>
              {evrow}
            </div>
          </>
        ) : (
          evrow
        )}
      </section>
    );
  }

  let notice: ReactNode = null;
  if (turn.stored && storedNote) notice = <Notice text={storedNote} testId="stored-note" />;
  else if (written?.state === "not_covered") notice = <Notice text={t.notCovered} testId="not-covered" />;
  else if (written) notice = <Notice text={written.state === "daily_cap" ? t.answerCap : t.noAnswer} testId="no-written-answer" />;
  return (
    <section className={`a a--none${newest ? "" : " a--old"}`}>
      {written && !turn.stored && <p className="label">{t.answer}</p>}
      {notice}
      {newest ? (
        <>
          {parts}
          <div className="a__foot">
            {found}
            {evrow}
            {turn.stored && (
              <p className="asknow">
                <button type="button" className="ask-btn" disabled={busy} onClick={() => onAskNow(turn.question)} data-testid="ask-now">{t.askNow}</button>
              </p>
            )}
          </div>
        </>
      ) : (
        evrow
      )}
    </section>
  );
}

/** A sentence, its last word kept with its marks: a mark never starts a line. */
function Sentence({ sentence, mark }: { sentence: AnswerSentence; mark: (n: number) => ReactNode }) {
  const text = sentence.text.replace(/\s+$/, "");
  const split = text.match(/^([\s\S]*\s)(\S+)$/);
  const head = split ? split[1] : "";
  const tail = split ? split[2] : text;
  return (
    <span className="sentence" data-testid="answer-sentence">
      {head}
      <span className="keep">{tail}<span className="marks">{sentence.cites.map(mark)}</span></span>{" "}
    </span>
  );
}
