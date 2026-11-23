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
 *
 * In a build that asks for the web part (lib/web.ts), it stands last in the turn, outside the
 * answer's section: under the Evidence row, and under the pictures when there are any.
 */
import type { ReactNode } from "react";
import type { AnswerSentence } from "@/lib/ask";
import type { Turn } from "@/lib/conversation";
import { sourceTitle } from "@/lib/evidence-text";
import type { FigureGroup } from "@/lib/figures";
import { citedFigures, figureFailed, figureSrc, fit, ratio, useFigureFailures } from "@/lib/figures";
import type { Labels } from "@/lib/i18n";
import type { Service } from "./hooks";
import { WAIT_LINES_AFTER_SECONDS } from "./hooks";
import { isPdf, linkOf, WEB } from "@/lib/web";
import type { WebPart, WebResult } from "@/lib/web";
import { answered, Bar, Notice, PANEL_ID, Waiting, Warn } from "./parts";

type Props = {
  turn: Turn;
  t: Labels;
  newest: boolean;
  service: Service;
  open: boolean; // this turn's Evidence is open
  storedNote: string | null;
  busy: boolean;
  onEvidence: (turnId: string, opener: HTMLElement, source?: number, figures?: number) => void;
  onAskNow: (question: string) => void;
};

export default function TurnView({ turn, t, newest, service, open, storedNote, busy, onEvidence, onAskNow }: Props) {
  const errorText = turn.error ? t.errors[turn.error.code] ?? (turn.error.message || t.errors.unreachable) : "";
  return (
    <article className={`turn${newest ? "" : " turn--old"}`} aria-labelledby={`q-${turn.id}`} data-testid="turn" data-turn={turn.id}>
      <header className="turn__q">
        <p className="label">{t.you}</p>
        <h2 className="turn__text" id={`q-${turn.id}`}>{turn.question}</h2>
        {turn.stored && <span className="ask-chip" data-testid="stored-tag">{t.stored}</span>}
        {turn.rewritten && turn.answer && <p className="turn__as" data-testid="searched-as">{t.searchedAs} “{turn.answer.question}”</p>}
      </header>
      {turn.check === "waiting" ? (
        // the check's words and its room stand right under this question (Chat.tsx, `.check`)
        null
      ) : turn.check === "failed" ? (
        <section className="a a--wait"><Warn text={errorText} testId="turn-error" /></section>
      ) : turn.pending ? (
        <section className="a a--wait">
          <Bar testId="searching-bar" />
          <Waiting service={service} t={t} from={WAIT_LINES_AFTER_SECONDS} searching />
        </section>
      ) : turn.error ? (
        <section className="a a--wait"><Warn text={errorText} testId="turn-error" /></section>
      ) : turn.answer ? (
        <>
          <Answered turn={turn} t={t} newest={newest} open={open} storedNote={storedNote} busy={busy} onEvidence={onEvidence} onAskNow={onAskNow} />
          {turn.web && !turn.writing && <Web web={turn.web} turnId={turn.id} notCovered={turn.written?.state === "not_covered"} newest={newest} t={t} />}
        </>
      ) : null}
    </article>
  );
}

function Answered({ turn, t, newest, open, storedNote, busy, onEvidence, onAskNow }: Omit<Props, "service">) {
  const evidence = turn.answer!;
  const written = turn.written;
  const ok = !turn.writing && answered(written);
  useFigureFailures(); // a picture whose file fails leaves the groups and the count
  // the figures of the cited pages: drawn under the newest answer, counted beside an older one's button
  const figs = ok ? citedFigures(written?.sources ?? [], evidence.passages) : { groups: [], pages: 0, count: 0 };
  const counts = ok && !newest
    ? [t.nSources(written?.sources?.length ?? 0), figs.count ? t.nFigures(figs.count) : ""].filter(Boolean).join(" · ")
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
                    <li key={source.n} data-testid="answer-source">{mark(source.n)}<span>{sourceTitle(source, evidence, t)}</span></li>
                  ))}
                </ol>
              </div>
              {evrow}
            </div>
            {figs.groups.length > 0 && <Figures turnId={turn.id} groups={figs.groups} pages={figs.pages} t={t} onEvidence={onEvidence} />}
          </>
        ) : (
          evrow
        )}
      </section>
    );
  }

  let notice: ReactNode = null;
  if (turn.stored && storedNote) notice = <Notice text={storedNote} testId="stored-note" />;
  // with the web part, the sentence does not say "what was found is below": the web block may stand there
  else if (written?.state === "not_covered") notice = <Notice text={WEB ? t.notCoveredWeb : t.notCovered} testId="not-covered" />;
  else if (written?.state === "out_of_scope") notice = <Notice text={t.outOfScope} testId="out-of-scope" />;
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
function Sentence({ sentence, mark, testId = "answer-sentence" }: { sentence: AnswerSentence; mark: (n: number) => ReactNode; testId?: string }) {
  const text = sentence.text.replace(/\s+$/, "");
  const split = text.match(/^([\s\S]*\s)(\S+)$/);
  const head = split ? split[1] : "";
  const tail = split ? split[2] : text;
  return (
    <span className="sentence" data-testid={testId}>
      {head}
      <span className="keep">{tail}<span className="marks">{sentence.cites.map(mark)}</span></span>{" "}
    </span>
  );
}

/** In the conversation a picture is never taller than this; inside Evidence it is at its own size. */
export const FIGURE_CAP = 200;

/**
 * The figures of the pages the newest answer cites: last in the turn, under its Evidence button,
 * so their arrival never moves the answer. One group per cited page; the whole group is one
 * button that opens Evidence on that page's figures. Each picture's box is held at its drawn size
 * (on a tint) before its file arrives; alt text is the page's own words, from the class and the place.
 */
function Figures({ turnId, groups, pages, t, onEvidence }: { turnId: string; groups: FigureGroup[]; pages: number; t: Labels; onEvidence: Props["onEvidence"] }) {
  const head = `figs-${turnId}`;
  return (
    <div className="pics" role="group" aria-labelledby={head} data-testid="figures">
      <p className="label" id={head}>{t.figsTitle}</p>
      <p className="pics__say">{t.figsSay} {t.figsOf(groups.length, pages)}</p>
      <ul className="pics__pages">
        {groups.map((g) => (
          <li key={g.index}>
            <button type="button" className="pics__link" onClick={(e) => onEvidence(turnId, e.currentTarget, undefined, g.index)} data-testid="figure-group">
              <span className="pics__cap">
                <b className="mark"><span className="vh">{t.source} </span>{g.n}</b>
                <span className="pics__what">
                  <span className="pics__doc">{g.doc}</span> <span className="pics__page">{t.page} {g.page}</span> <span className="pics__go">{t.figsGo}</span>
                </span>
              </span>
              <span className="pics__row">
                {g.figures.map((f, i) => {
                  const size = fit(f.width, f.height, FIGURE_CAP);
                  const src = figureSrc(f.id);
                  return src ? (
                    <img key={f.id} src={src} width={size.width} height={size.height} style={ratio(f)} loading="lazy" decoding="async" alt={t.figAlt(i + 1, g.figures.length, t.figKind[f.class])} onError={() => figureFailed(f.id)} data-testid="figure" />
                  ) : null;
                })}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/*
 * The web part, as drawn (a2/82 to a2/94). Searching: one line with the dashed edge. The block: its heading,
 * the line under it, the sentences with their round marks, and one row per cited page. Nothing to add: under
 * "not covered" one line, under an answer nothing. No search, a search that failed, the searches used up, or
 * a question the web call judged out of scope: nothing. In an older turn the block is one line that opens in place.
 */
function Web({ web, turnId, notCovered, newest, t }: { web: WebPart; turnId: string; notCovered: boolean; newest: boolean; t: Labels }) {
  if (web.state === "searching") {
    return (
      <div className="webline webline--wait" role="status" data-testid="web-searching">
        <Bar />
        <p>{t.webWait}</p>
      </div>
    );
  }
  if (web.state === "nothing") return notCovered ? <p className="webline" role="status" data-testid="web-nothing">{t.webNothing}</p> : null;
  if (web.state !== "ok") return null;
  const base = `web-${turnId}`;
  const goTo = (n: number) => document.getElementById(`${base}-${n}`)?.focus();
  const mark = (n: number) => (
    <button key={n} type="button" className="wmark" onClick={() => goTo(n)} data-testid="web-mark">
      <span className="vh">{t.webMark} </span>W{n}
    </button>
  );
  const head = <h3 className="web__h" id={`${base}-h`}>{t.webTitle}</h3>;
  const body = (
    <>
      <p className="web__say">{t.webUnder}</p>
      <p className="web__text">{web.sentences.map((sentence, i) => <Sentence key={i} sentence={sentence} mark={mark} testId="web-sentence" />)}</p>
      <ol className="web__list">
        {web.results.map((result) => <WebRow key={result.n} result={result} id={`${base}-${result.n}`} t={t} />)}
      </ol>
    </>
  );
  return newest ? (
    <aside className="web" aria-labelledby={`${base}-h`} data-testid="web">{head}{body}</aside>
  ) : (
    <details className="web web--old" data-testid="web">
      <summary data-testid="web-open">{head}</summary>
      {body}
    </details>
  );
}

/** One cited page: its title as text, its host as text under it, "PDF" from the address's ending. The page
 *  makes it a link only when it has checked the address again here (lib/web.ts, linkOf). */
function WebRow({ result, id, t }: { result: WebResult; id: string; t: Labels }) {
  const href = linkOf(result.url);
  const what = (
    <>
      <span className="web__t">{result.title}</span>
      <span className="web__d">
        {href ? new URL(href).hostname : result.host}
        {isPdf(result.url) && <> <span className="web__pdf">PDF</span></>}
        {href && <> <span aria-hidden="true">↗</span><span className="vh"> ({t.webNew})</span></>}
      </span>
    </>
  );
  return (
    <li id={id} tabIndex={-1} data-testid="web-result">
      <div className="web__row">
        <b className="wmark wmark--solid"><span className="vh">{t.webMark} </span>W{result.n}</b>
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer" data-testid="web-link">{what}</a>
        ) : (
          <span className="web__plain">{what}</span>
        )}
      </div>
    </li>
  );
}
