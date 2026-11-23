"use client";

/*
 * Evidence for one answer: four tabs (Graph, Sources, Cards and passages, How it was
 * made), three when no source was cited. From 1280 px it is docked beside the
 * conversation, so an answer and the text it cites can be read side by side; below that it
 * is a sheet over the conversation that keeps focus inside and closes with Esc.
 *
 * The panel names the question it belongs to, and stays on that answer while a new turn
 * arrives. What the model wrote (source titles, quotes) and what the stores returned
 * (passages, card facts) are text nodes only.
 */
import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { answerGraph } from "@/lib/answer-graph";
import type { AnswerGraph, GNode, TreeIssue } from "@/lib/answer-graph";
import type { AskAnswer, IssueCard, ModelCall } from "@/lib/ask";
import type { Turn } from "@/lib/conversation";
import { actLine, dateLabel, formatDate, sourceTitle } from "@/lib/evidence-text";
import { figureSrc, figuresOf, ratio } from "@/lib/figures";
import type { Labels, Lang } from "@/lib/i18n";
import { answered, figuresId, PANEL_ID, sourceId, Warn } from "./parts";

export type TabKey = "graph" | "sources" | "found" | "made";
/** Where Evidence opens: at a source (Sources), at a passage's figures (Cards and passages), or at its tab. */
export type PanelFocus = { source?: number; figures?: number; nonce: number };

type Props = {
  turn: Turn;
  t: Labels;
  lang: Lang;
  tab: TabKey;
  onTab: (tab: TabKey) => void;
  onClose: () => void;
  sheet: boolean;
  focus: PanelFocus;
  storedNote: string | null;
};

const cardId = (turnId: string, index: number) => `ev-card-${turnId}-${index}`;
const FOCUSABLE = 'button:not([disabled]), [href], summary, input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** The tabs a turn has: Sources only when the answer cites something. */
export function tabsOf(turn: Turn): TabKey[] {
  return !turn.writing && answered(turn.written) ? ["graph", "sources", "found", "made"] : ["graph", "found", "made"];
}

export default function EvidencePanel({ turn, t, lang, tab, onTab, onClose, sheet, focus, storedNote }: Props) {
  const panel = useRef<HTMLElement | null>(null);
  const tabs = tabsOf(turn);
  const current = tabs.includes(tab) ? tab : "graph";
  const ok = tabs.includes("sources");
  const names: Record<TabKey, [string, string]> = { graph: t.tabGraph, sources: t.tabSources, found: t.tabFound, made: ok ? t.tabMade : t.tabSearched };

  // opened: focus the source or the figures it was opened at, or the tab it shows
  const at = focus.source !== undefined || focus.figures !== undefined;
  useEffect(() => {
    const target = focus.source !== undefined
      ? document.getElementById(sourceId(turn.id, focus.source))
      : focus.figures !== undefined
        ? document.getElementById(figuresId(turn.id, focus.figures))
        : panel.current?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
    const fold = target?.closest("details");
    if (fold) fold.open = true;
    target?.focus({ preventScroll: !at });
    if (at) target?.scrollIntoView({ block: "start" });
    // only a new request to open moves focus; a tab change by keyboard moves it itself
  }, [focus.nonce, turn.id]);

  // a node of the graph leads to its source or its card, inside the panel
  const [jump, setJump] = useState<{ id: string; seq: number } | null>(null);
  const jumped = useRef(false);
  const go = (target: NonNullable<GNode["target"]>) => {
    jumped.current = true;
    onTab(target.tab);
    const id = target.tab === "sources" ? sourceId(turn.id, target.n) : cardId(turn.id, target.index);
    setJump((j) => ({ id, seq: (j?.seq ?? 0) + 1 }));
  };
  useEffect(() => {
    if (!jump) return;
    const el = document.getElementById(jump.id);
    if (el instanceof HTMLDetailsElement) el.open = true;
    const target = el?.querySelector<HTMLElement>(":scope > summary") ?? el;
    target?.focus();
    el?.scrollIntoView({ block: "start" });
  }, [jump]);

  // another answer or another tab starts at its top
  useEffect(() => {
    if (jumped.current) {
      jumped.current = false; // a jump scrolls to its own target
      return;
    }
    if (!at && panel.current) panel.current.scrollTop = 0;
  }, [turn.id, current]);

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !sheet || !panel.current) return;
    // in the sheet, focus stays inside
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && (document.activeElement === first || !panel.current.contains(document.activeElement))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const at = tabs.indexOf(current);
    const next = e.key === "ArrowRight" ? (at + 1) % tabs.length
      : e.key === "ArrowLeft" ? (at - 1 + tabs.length) % tabs.length
      : e.key === "Home" ? 0
      : e.key === "End" ? tabs.length - 1
      : -1;
    if (next < 0) return;
    e.preventDefault();
    onTab(tabs[next]);
    document.getElementById(`ev-tab-${tabs[next]}`)?.focus();
  };

  return (
    <aside
      id={PANEL_ID}
      ref={panel}
      className={`evp${sheet ? " evp--sheet" : ""}`}
      role={sheet ? "dialog" : "complementary"}
      aria-modal={sheet || undefined}
      aria-labelledby="evp-label evp-q"
      onKeyDown={onKeyDown}
      data-testid="evidence-panel"
      data-turn={turn.id}
    >
      <div className="evp__bar">
        <div className="evp__title">
          <p className="label" id="evp-label">{ok ? t.evFor : t.doorFound}</p>
          <p className="evp__q" id="evp-q" data-testid="evidence-question">{turn.question}</p>
        </div>
        <button type="button" className="evp__close" onClick={onClose} data-testid="evidence-close">
          <span aria-hidden="true">×</span> {t.close}
        </button>
      </div>
      <div className="tabs" role="tablist" aria-labelledby="evp-label" onKeyDown={onTabKey}>
        {tabs.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`ev-tab-${key}`}
            aria-selected={key === current}
            aria-controls={`ev-panel-${key}`}
            tabIndex={key === current ? 0 : -1}
            onClick={() => onTab(key)}
            data-testid={`tab-${key}`}
          >
            <span className="tab__long">{names[key][0]}</span>
            <span className="tab__short">{names[key][1]}</span>
          </button>
        ))}
      </div>
      <div className="evp__body">
        <section className="ev" role="tabpanel" id={`ev-panel-${current}`} aria-labelledby={`ev-tab-${current}`} tabIndex={0} data-testid={`ev-${current}`}>
          {current === "graph" && <GraphTab turn={turn} t={t} lang={lang} ok={ok} go={go} />}
          {current === "sources" && <SourcesTab turn={turn} t={t} />}
          {current === "found" && <FoundTab turn={turn} t={t} lang={lang} storedNote={storedNote} />}
          {current === "made" && <MadeTab turn={turn} t={t} ok={ok} />}
        </section>
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------- Graph

function GraphTab({ turn, t, lang, ok, go }: { turn: Turn; t: Labels; lang: Lang; ok: boolean; go: (target: NonNullable<GNode["target"]>) => void }) {
  const evidence = turn.answer!;
  const [view, setView] = useState<"graph" | "list">("graph");
  const title = ok ? t.evGraph : t.evGraphFound;
  const graph = answerGraph(evidence, ok ? turn.written : undefined, { ...t, lang });
  const empty = !ok && evidence.issues.length === 0;
  return (
    <>
      <h3>{title}</h3>
      {empty ? (
        evidence.mode.catalogue === "unavailable" ? <Warn inline alert={false} text={t.catalogueDown} /> : <p className="ev__lead">{t.gEmpty}</p>
      ) : (
        <>
          {!ok && turn.written && !turn.writing && <p className="ev__lead">{t.gNone}</p>}
          <div className="ev-view" role="group" aria-label={t.view}>
            <button type="button" aria-pressed={view === "graph"} onClick={() => setView("graph")} data-testid="view-graph">{t.asGraph}</button>
            <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")} data-testid="view-list">{t.asList}</button>
          </div>
          <div className={`ev-graphbox ev-graphbox--${view}`}>
            <GraphDrawing graph={graph} title={title} go={go} />
            <GraphList graph={graph} t={t} />
          </div>
        </>
      )}
    </>
  );
}

/** The drawing: its box takes the data's proportions before anything is drawn, so nothing shifts. */
function GraphDrawing({ graph, title, go }: { graph: AnswerGraph; title: string; go: (target: NonNullable<GNode["target"]>) => void }) {
  return (
    <div className="ev-graph" style={{ aspectRatio: `${graph.width} / ${graph.height}` }} data-testid="graph-drawing">
      <svg className="ev-graph__svg" viewBox={`0 0 ${graph.width} ${graph.height}`} role="group" aria-label={title}>
        {graph.edges.map((e) => (
          <path key={e.key} className={`g-edge${e.cites ? " g-edge--cites" : ""}${e.found ? " g-edge--found" : ""}`} d={e.d} aria-hidden="true" />
        ))}
        {graph.rule && <line className="g-rule" x1={graph.rule.x1} x2={graph.rule.x2} y1={graph.rule.y} y2={graph.rule.y} aria-hidden="true" />}
        {graph.labels.map((l) => (
          <text key={l.key} className={l.head ? "g-head" : "g-rel"} x={l.x} y={l.y} aria-hidden="true">{l.text}</text>
        ))}
        {graph.nodes.map((n) => {
          const tx = n.x + 12 + (n.mark ? 30 : 0);
          const target = n.target;
          // only a node that does something takes focus; the others are read, and the List says the same
          const act = target
            ? {
                tabIndex: 0,
                role: "button",
                onClick: () => go(target),
                onKeyDown: (e: KeyboardEvent<SVGGElement>) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    go(target);
                  }
                },
              }
            : { role: "img" };
          return (
            <g key={n.key} className={`g-node g-node--${n.kind}${n.found ? " g-node--found" : ""}${target ? " g-node--go" : ""}`} aria-label={n.name} data-testid="graph-node" {...act}>
              <rect x={n.x} y={n.y} width={n.w} height={n.h} rx={n.kind === "stamp" ? 2 : 3} />
              {n.mark !== undefined && (
                <>
                  <rect className="g-mark" x={n.x + 8} y={n.y + 8} width={24} height={24} rx={2} />
                  <text className="g-marktext" x={n.x + 20} y={n.y + 25} textAnchor="middle">{n.mark}</text>
                </>
              )}
              {n.kind === "stamp" ? (
                <text className="g-mono" x={n.x + n.w / 2} y={n.y + 19} textAnchor="middle">{n.lines[0]}</text>
              ) : (
                n.lines.map((line, i) => <text key={i} x={tx} y={n.y + 25 + 20 * i}>{line}</text>)
              )}
              {n.mono && <text className="g-mono" x={n.x + 12} y={n.y + 23 + 20 * n.lines.length}>{n.mono}</text>}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function TreeIssueItem({ issue, t, rel }: { issue: TreeIssue; t: Labels; rel?: string }) {
  return (
    <li>
      {rel && <span className="tree__rel">{rel}</span>}
      <span className="tree__node">
        {issue.mark !== undefined && <b className="mark mark--solid">{issue.mark}</b>} {issue.title} <code>{issue.id}</code>
      </span>
      {(issue.printers.length > 0 || issue.acts.length > 0 || issue.stamps.length > 0) && (
        <ul>
          {issue.printers.map((p, i) => <li key={`p${i}`}><span className="tree__rel">{t.gPrinter}</span> {p}</li>)}
          {issue.acts.map((a, i) => <li key={`a${i}`}><span className="tree__rel">{t.gAct}</span> {a}</li>)}
          {issue.stamps.length > 0 && (
            <li><span className="tree__rel">{t.gStamps}</span> {issue.stamps.map((s, i) => <code key={i}>{s}</code>)}</li>
          )}
        </ul>
      )}
    </li>
  );
}

/** The same graph as a nested list: on a phone it is the only form. */
function GraphList({ graph, t }: { graph: AnswerGraph; t: Labels }) {
  const { tree } = graph;
  return (
    <ul className="tree" data-testid="graph-list">
      {tree.answer && (
        <li>
          <span className="tree__node tree__node--answer">{t.gAnswer}</span>
          <ul>
            {tree.cited.map((c, i) =>
              c.kind === "issue" ? (
                <TreeIssueItem key={i} issue={c.issue} t={t} rel={t.gCites} />
              ) : (
                <li key={i}><span className="tree__rel">{t.gCites}</span><span className="tree__node"><b className="mark mark--solid">{c.mark}</b> {c.title}</span></li>
              ),
            )}
          </ul>
        </li>
      )}
      {tree.found.length > 0 && (
        <li className="tree__found">
          <span className="tree__head">{tree.foundLabel}</span>
          <ul>{tree.found.map((issue, i) => <TreeIssueItem key={i} issue={issue} t={t} />)}</ul>
        </li>
      )}
    </ul>
  );
}

// ---------------------------------------------------------------- Sources

function SourcesTab({ turn, t }: { turn: Turn; t: Labels }) {
  return (
    <>
      <h3>{t.evSources}</h3>
      <ol className="src">
        {(turn.written?.sources ?? []).map((source) => (
          <li key={source.n} id={sourceId(turn.id, source.n)} tabIndex={-1} data-testid="ev-source">
            <div className="src__head"><b className="mark mark--solid">{source.n}</b><span className="src__title">{sourceTitle(source, turn.answer, t)}</span></div>
            {source.quotes.length > 0 && <p className="src__for">{t.citedFor}</p>}
            {source.quotes.map((quote, i) => <blockquote key={i}>{quote}</blockquote>)}
          </li>
        ))}
      </ol>
    </>
  );
}

// ---------------------------------------------------------------- Cards and passages

const present = (v: unknown) => v !== null && v !== undefined && v !== "";

function CardFacts({ card, t, lang }: { card: IssueCard; t: Labels; lang: Lang }) {
  const dates = Object.entries(card.dates ?? {}).filter(([, v]) => present(v));
  const printers = (card.printers ?? []).filter(Boolean);
  const acts = card.acts ?? [];
  const stamps = (card.stamps ?? []).slice(0, 24);
  return (
    <>
      {(dates.length > 0 || printers.length > 0 || card.perforation || acts.length > 0) && (
        <dl className="facts">
          {dates.length > 0 && (
            <>
              <dt>{t.dates}</dt>
              <dd className="stack">{dates.map(([k, v]) => <span key={k}>{dateLabel(k, t.dateNames)}: {formatDate(String(v), lang)}</span>)}</dd>
            </>
          )}
          {printers.length > 0 && <><dt>{t.printers}</dt><dd>{printers.join("; ")}</dd></>}
          {card.perforation && <><dt>{t.perforation}</dt><dd>{card.perforation}</dd></>}
          {acts.length > 0 && <><dt>{t.acts}</dt><dd className="stack">{acts.map((a, i) => <span key={i}>{actLine(a, lang)}</span>)}</dd></>}
        </dl>
      )}
      {stamps.length > 0 && (
        <div className="table-scroll">
          <table className="stamps">
            <caption>{(card.stamps ?? []).length} {t.stamps}</caption>
            <thead>
              <tr><th scope="col">{t.no}</th><th scope="col">{t.value}</th><th scope="col">{t.colour}</th><th scope="col" className="r">{t.quantity}</th></tr>
            </thead>
            <tbody>
              {stamps.map((s, i) => (
                <tr key={i}>
                  <th scope="row">{present(s.catalog_no) ? s.catalog_no : "–"}</th>
                  <td>{present(s.value) ? [s.value, s.unit].filter(present).join(" ") : "–"}</td>
                  <td>{present(s.color) ? s.color : "–"}</td>
                  <td className="r">{present(s.quantity) ? s.quantity : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function FoundTab({ turn, t, lang, storedNote }: { turn: Turn; t: Labels; lang: Lang; storedNote: string | null }) {
  const evidence = turn.answer!;
  const sources = !turn.writing && answered(turn.written) ? turn.written?.sources ?? [] : [];
  const cited = (kind: string, index: number) => sources.find((s) => s.kind === kind && s.index === index)?.n;
  return (
    <>
      <h3>{t.evFound}</h3>
      {storedNote && <p className="ev__lead" data-testid="ev-stored-note">{storedNote}</p>}
      {evidence.mode.embedding !== "ok" && <Warn inline alert={false} text={t.modeKeyword} />}
      <h4 className="ev__sub">{t.catalogue}</h4>
      {evidence.mode.catalogue === "unavailable" ? (
        <Warn inline alert={false} text={t.catalogueDown} testId="catalogue-down" />
      ) : evidence.issues.length === 0 ? (
        <p className="ev__none">{t.noIssues}</p>
      ) : (
        evidence.issues.map((issue, i) => {
          const n = cited("issue", i);
          const card = issue.card;
          const head = (
            <>
              {n !== undefined && <b className="mark mark--solid">{n}</b>}
              <span className="ev-card__title">{issue.title || issue.issue_id}</span>
              <span className="ev-card__meta"><code>{issue.issue_id}</code> · {t.matchedBy} {issue.matched_by.join(", ")}</span>
            </>
          );
          const hasFacts = card && (Object.values(card.dates ?? {}).some(present) || (card.printers ?? []).length || card.perforation || (card.acts ?? []).length || (card.stamps ?? []).length);
          return hasFacts ? (
            <details key={issue.issue_id} id={cardId(turn.id, i)} className="ev-card" open={n !== undefined} data-testid="card">
              <summary>{head}</summary>
              <div className="ev-card__body"><CardFacts card={card!} t={t} lang={lang} /></div>
            </details>
          ) : (
            <div key={issue.issue_id} id={cardId(turn.id, i)} tabIndex={-1} className="ev-card ev-card--flat" data-testid="card"><div className="ev-card__head">{head}</div></div>
          );
        })
      )}
      <h4 className="ev__sub">{t.literature}</h4>
      {evidence.mode.literature === "unavailable" ? (
        <Warn inline alert={false} text={t.literatureDown} testId="literature-down" />
      ) : evidence.passages.length === 0 ? (
        <p className="ev__none">{t.noPassages}</p>
      ) : (
        evidence.passages.map((p, i) => {
          const n = cited("passage", i);
          const figs = figuresOf(p);
          return (
            <details key={i} className="ev-card ev-passage" open={n !== undefined} data-testid="passage">
              <summary>
                {n !== undefined && <b className="mark mark--solid">{n}</b>}
                <span className="ev-passage__doc">{p.doc_id ?? "?"}</span>
                <span className="ev-passage__page">{t.page} {p.page ?? "?"}</span>
                {figs.length > 0 && <span className="ask-chip ask-chip--fig" data-testid="passage-figures-count">{t.nFigures(figs.length)}</span>}
                {p.clipped && <span className="ask-chip">{t.clipped}</span>}
              </summary>
              <div className="ev-card__body">
                {p.text ? <p className="ev-passage__text">{p.text}</p> : <p className="ev__none" data-testid="passage-no-text">{t.noText}</p>}
              </div>
              {figs.length > 0 && (
                // under the text, at their own size: never enlarged, narrowed only to the panel's width
                <div className="pfigs" id={figuresId(turn.id, i)} tabIndex={-1} role="group" aria-labelledby={`${figuresId(turn.id, i)}-h`} data-testid="passage-figures">
                  <p className="label" id={`${figuresId(turn.id, i)}-h`}>{t.pfigs((p.doc_id ?? "?").trim(), p.page ?? "?")}</p>
                  <ul>
                    {figs.map((f, k) => {
                      const src = figureSrc(f.id);
                      return src ? (
                        <li key={f.id}>
                          <img src={src} width={f.width} height={f.height} style={ratio(f)} loading="lazy" decoding="async" alt={t.figAlt(k + 1, figs.length, t.figKind[f.class])} data-testid="figure" />
                        </li>
                      ) : null;
                    })}
                  </ul>
                </div>
              )}
            </details>
          );
        })
      )}
    </>
  );
}

// ---------------------------------------------------------------- How it was made

const issueScore = (v: number) => (Number.isInteger(v) ? v.toFixed(1) : String(Math.round(v * 10_000) / 10_000));

function CallLine({ call, t }: { call?: ModelCall; t: Labels }) {
  if (!call) return null;
  return (
    <dl className="ev-kv">
      <div><dt>{t.call}</dt><dd>{call.purpose}</dd></div>
      <div><dt>{t.state}</dt><dd>{call.state}</dd></div>
      <div><dt>s</dt><dd>{call.seconds}</dd></div>
      <div><dt>{t.tokensIn}</dt><dd>{call.input_tokens}</dd></div>
      <div><dt>{t.tokensOut}</dt><dd>{call.output_tokens}</dd></div>
    </dl>
  );
}

function Timings({ evidence, t }: { evidence: AskAnswer; t: Labels }) {
  const rows = ([["embedding_ms", t.embedding], ["catalogue_ms", t.catalogueT], ["literature_ms", t.literatureT], ["total_ms", t.total]] as const)
    .filter(([key]) => typeof evidence.timings?.[key] === "number");
  if (!rows.length) return null;
  return <dl className="ev-kv">{rows.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{evidence.timings[key]} ms</dd></div>)}</dl>;
}

function MadeTab({ turn, t, ok }: { turn: Turn; t: Labels; ok: boolean }) {
  const evidence = turn.answer!;
  const written = turn.written;
  const call = (purpose: string) => (turn.calls ?? []).find((c) => c.purpose === purpose);
  const keyword = evidence.mode.embedding !== "ok";
  const counts = written?.counts;
  return (
    <>
      <h3>{ok ? t.evMade : t.evMadeNone}</h3>
      <ol className="steps">
        {turn.rewritten && (
          <li>
            <h4>{t.stepRewritten}</h4>
            <p>{t.searchedAs} “{evidence.question}”</p>
            <CallLine call={call("rewrite")} t={t} />
          </li>
        )}
        <li>
          <h4>{t.stepSearched}</h4>
          <p data-testid="mode-line" data-mode={keyword ? "keyword" : "vector"}>{keyword ? t.modeKeyword : t.modeVector}</p>
          <dl className="ev-kv">
            {Object.entries(evidence.mode).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{String(v)}</dd></div>)}
          </dl>
          <Timings evidence={evidence} t={t} />
        </li>
        {ok && (
          <li>
            <h4>{t.stepWritten}</h4>
            <CallLine call={call("write")} t={t} />
          </li>
        )}
        {ok && counts && (
          <li>
            <h4>{t.stepChecked}</h4>
            <dl className="ev-kv">
              <div><dt>{t.cWritten}</dt><dd>{counts.sentences}</dd></div>
              <div><dt>{t.cRemoved}</dt><dd>{counts.sentences_without_citation}</dd></div>
              <div><dt>{t.cShown}</dt><dd>{written?.sentences?.length ?? 0}</dd></div>
              <div><dt>{t.cCitations}</dt><dd>{counts.citations}</dd></div>
              <div><dt>{t.cNotHold}</dt><dd>{counts.citations_that_do_not_hold}</dd></div>
            </dl>
          </li>
        )}
        {!ok && written && !turn.writing && (
          <li>
            <h4>{t.stepWritten}</h4>
            <p>{written.state === "not_covered" ? t.notWritten : t.writtenNone}</p>
            <dl className="ev-kv"><div><dt>{t.state}</dt><dd>{written.state}</dd></div></dl>
            <CallLine call={call("write")} t={t} />
          </li>
        )}
      </ol>
      {evidence.issues.length > 0 && (
        <div className="table-scroll">
          <table className="scores">
            <caption>{t.issueMatch}</caption>
            <thead><tr><th scope="col">{t.catalogue}</th><th scope="col">{t.matchedBy}</th><th scope="col" className="r">{t.score}</th></tr></thead>
            <tbody>
              {evidence.issues.map((issue) => (
                <tr key={issue.issue_id}><th scope="row">{issue.title || issue.issue_id}</th><td>{issue.matched_by.join(", ")}</td><td className="r">{issueScore(issue.score)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {evidence.passages.length > 0 && (
        <div className="table-scroll">
          <table className="scores">
            <caption>{t.passageScore}</caption>
            <thead><tr><th scope="col">{t.literature}</th><th scope="col" className="r">{t.score}</th></tr></thead>
            <tbody>
              {evidence.passages.map((p, i) => (
                <tr key={i}><th scope="row">{p.doc_id ?? "?"}, {t.page} {p.page ?? "?"}</th><td className="r">{p.score ?? "–"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="scorenote">{t.scoreNote}</p>
    </>
  );
}
