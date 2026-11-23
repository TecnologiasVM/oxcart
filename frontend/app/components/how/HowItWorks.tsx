"use client";

/*
 * "How it works": what Oxcart is and with which technologies, the path of a question (one diagram), why a
 * graph and vectors together (one traced question), results, the two judges, what did not help, cost and
 * wait, what keeps it safe, and the whole account. Drawn as on a2/80 (English) and a2/81 (Spanish) of
 * the drawing.
 *
 * Nothing here calls the backend: the page works while the service sleeps. Every figure is read from
 * lib/how-figures.json (scripts/how-figures.mjs), formatted for the page's language; the words are in
 * lib/how-i18n.ts. Every text is rendered as text, never as markup.
 *
 * The web step is described only in a build that asks for the web part (NEXT_PUBLIC_WEB, lib/web.ts), the
 * same setting the question page's Details reads.
 */
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { FIGURES } from "@/lib/how-figures";
import { HOW, modelName, numbers } from "@/lib/how-i18n";
import { LABELS } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import { WEB } from "@/lib/web";
import { EVAL_URL, HeaderNav, LANG_KEY, privacyText, REPO_URL } from "../ask/parts";
import Pipeline from "./Pipeline";

const F = FIGURES;

export default function HowItWorks() {
  const [lang, setLang] = useState<Lang>("en");
  const [ready, setReady] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  // the language this browser chose, as on the question page
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(LANG_KEY);
    } catch {
      /* storage blocked */
    }
    setLang(saved === "es" || saved === "en" ? saved : navigator.language.toLowerCase().startsWith("es") ? "es" : "en");
    setSlot(document.getElementById("masthead-page"));
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(LANG_KEY, lang);
    } catch {
      /* storage blocked: the choice lasts as long as the page */
    }
    document.documentElement.lang = lang;
  }, [lang, ready]);

  const t = LABELS[lang];
  const w = HOW[lang];
  const f = numbers(lang);
  const dataLang = (l: Lang) => (l === lang ? undefined : l);
  const writer = modelName(F.limits.models.writer);
  const steps = WEB ? 5 : 4;

  // ---------------------------------------------------------------- 2. the path of a question
  const nodes = w.node({
    writer,
    embedding: F.limits.models.embedding,
    issues: f.n(F.stores.graph.issues),
    passages: f.n(F.stores.literature.objects),
    cards: f.n(F.limits.issues),
    shown: f.n(F.limits.passages),
  });
  const S = F.stores;
  const stepArgs = {
    writer,
    numbers: f.n(S.literature.dimensions),
    issues: f.n(F.limits.issues),
    passages: f.n(F.limits.passages),
    graphIndex: S.graph.index.type,
    litIndex: S.literature.index.type,
    litCompression: S.literature.index.compression,
    graphSimilarity: S.graph.index.similarity,
    litSimilarity: S.literature.index.similarity,
  };
  const stepKeys = (["s1", "s2", "s3", "s4", "s5"] as const).slice(0, steps);

  // ---------------------------------------------------------------- 4. results
  const run = F.run;
  const lit = run.literature;
  const results: { n: string; lead: string; text: string; id: string }[] = [
    { id: "issue", n: f.of(F.issue_found.first, F.issue_found.of), lead: w.issueFound.lead, text: w.issueFound.text(f.of(F.issue_found.three, F.issue_found.of)) },
  ];
  if (run.page_found) {
    const p = run.page_found;
    results.push({ id: "page", n: f.of(p.found, p.of), lead: w.pageFound.lead, text: w.pageFound.text(f.n(p.k), f.n(p.drafts - p.of), f.of(p.found, p.drafts)) });
  }
  results.push(
    { id: "catalogue", n: f.of(run.catalogue.correct, run.catalogue.of), lead: w.catAnswers.lead, text: w.catAnswers.text(f.of(run.catalogue.supported, run.catalogue.of)) },
    {
      id: "literature",
      n: f.of(lit.in_full, lit.of),
      lead: w.litAnswers.lead,
      text: w.litAnswers.text(lit.in_part, f.n(lit.in_part), lit.not, f.n(lit.not), lit.not_written, f.n(lit.not_written))
        + (lit.asks != null ? ` ${w.asks(f.of(lit.asks, lit.of))}` : ""),
    },
    { id: "sentences", n: f.of(run.sentences.removed, run.sentences.written), lead: w.removed.lead, text: w.removed.text(f.n(run.citations.not_hold), f.n(run.citations.of)) },
  );
  const [s1, s2] = F.sealed.runs;
  const sealedOf = f.n(s1.literature.of);
  const sealedText = s1.literature.in_full === 0 && s2.literature.in_full === 0
    ? w.sealedNone(f.n(F.sealed.questions), sealedOf, f.n(s1.literature.asks), f.n(s2.literature.asks), f.n(s1.catalogue.correct), f.n(s2.catalogue.correct))
    : w.sealedSome(f.n(F.sealed.questions), sealedOf, f.n(s1.literature.in_full), f.n(s2.literature.in_full), f.n(s1.literature.asks),
      f.n(s2.literature.asks), f.n(s1.catalogue.correct), f.n(s2.catalogue.correct));

  // ---------------------------------------------------------------- 6. tried
  const tr = F.tried;
  const st = tr.stronger;
  const span = (r: [number, number]) => (r[0] === r[1] ? f.n(r[0]) : w.range(f.n(r[0]), f.n(r[1])));
  const tried = [
    { n: f.of(tr.whole.answered, tr.whole.of), text: w.triedWhole(f.n(tr.whole.passages), f.n(S.literature.objects), f.n(tr.kept_answered)) },
    { n: f.of(tr.hybrid.answered, tr.hybrid.of), text: w.triedHybrid(tr.hybrid.answered === tr.hybrid.vector, f.n(tr.hybrid.vector)) },
    { n: f.of(tr.thinking_off.cut, tr.thinking_off.of), text: w.triedOff },
    {
      n: `${st.in_full[0] === st.in_full[1] ? f.n(st.in_full[0]) : `${f.n(st.in_full[0])}–${f.n(st.in_full[1])}`}${lang === "es" ? " de " : " of "}${f.n(st.of)}`,
      text: w.triedStrong(modelName(st.model), span(st.in_full), f.n(st.of), modelName(st.served_model), span(st.served_in_full), f.n(st.times), f.usd(st.usd), f.usd(st.served_usd)),
    },
  ];

  // ---------------------------------------------------------------- 7. cost and wait
  const costs: { n: string; unit: string; text: string }[] = [];
  if (run.cost) costs.push({ n: f.usd(run.cost.mean), unit: "USD", text: w.costMean(f.usd(run.cost.max)) + (F.after_first_usd != null ? w.costAfter(f.usd(F.after_first_usd)) : "") });
  if (run.waits) {
    costs.push({ n: f.seconds(run.waits.evidence), unit: "s", text: w.waitEvidence });
    costs.push({ n: f.seconds(run.waits.answer), unit: "s", text: w.waitAnswer(f.seconds(run.waits.answer_p95)) });
  }

  // ---------------------------------------------------------------- 8. safe in public
  const L = F.limits;
  const safe: { lead: string; text: string }[] = [];
  if (F.spend_limit) safe.push({ lead: w.spend.lead, text: w.spend.text(f.n(F.spend_limit.usd), f.month(F.spend_limit.month)) });
  safe.push(
    {
      lead: w.use.lead,
      text: w.use.text(f.n(L.per_minute), f.n(L.per_day), f.n(L.model_calls_a_day), f.n(Math.ceil(L.model_calls_a_day / 2)), f.n(L.question_chars))
        + (WEB ? w.useWeb(f.n(L.web_searches_a_month)) : ""),
    },
    { lead: w.readOnly.lead, text: w.readOnly.text },
    { lead: w.scope.lead, text: w.scope.text(f.of(run.out_of_scope.no_answer, run.out_of_scope.of)) },
    { lead: w.disk.lead, text: w.disk.text(f.n(L.vectors_in_memory)) },
  );

  const V = F.versions;
  const stack: [string, string][] = [
    [w.stack.steps, `LangGraph ${V.langgraph}`],
    [w.stack.graph, w.stack.graphV(S.graph.neo4j)],
    [w.stack.lit, w.stack.litV(S.literature.weaviate)],
    [w.stack.backend, w.stack.backendV(V.fastapi, V.python)],
    [w.stack.page, w.stack.pageV(V.next, V.react, V.typescript)],
    [w.stack.tests, w.stack.testsV(V.pytest, V.playwright)],
  ];

  const J = F.judges;
  const trace = F.trace;
  const mark = (n: number) => <b className="mark mark--static"><span className="vh">{w.source} </span>{n}</b>;

  return (
    <>
      {slot && createPortal(<HeaderNav t={t} lang={lang} setLang={setLang} here />, slot)}
      <main id="main" className="how" data-testid="how" data-lang={lang}>
        <div className="how__in">
          <div className="how__top">
            <div className="how__intro">
              <h1>{w.title}</h1>
              <p className="how__lead">{w.lead({ issues: f.n(S.graph.issues), stamps: f.n(S.graph.stamps), passages: f.n(S.literature.objects), embedding: F.limits.models.embedding, writer })}</p>
            </div>
            <section className="how__pipe" aria-labelledby="h-pipe">
              <h2 id="h-pipe">{w.pipeH(steps)}</h2>
              <figure className="pipe__fig">
                <Pipeline nodes={nodes} web={WEB} title={w.pipeTitle} desc={w.pipeDesc} />
                <figcaption>{w.legend(WEB)}</figcaption>
              </figure>
              <div className="pipe__text">
                <ol className="pipe__list" data-testid="steps">
                  {stepKeys.map((key, i) => (
                    <li key={key}>
                      <h3><span className="pipe__n" aria-hidden="true">{f.n(i + 1)}</span>{w.steps[key].h}</h3>
                      <p>{w.steps[key].text(stepArgs)}</p>
                    </li>
                  ))}
                </ol>
                <p className="pipe__note">{w.pipeNote}</p>
              </div>
            </section>
          </div>

          <div className="how__rest">
            <Section id="h-why" title={w.whyH}>
              <p>{w.why}</p>
              <figure className="trace" data-testid="trace">
                <figcaption className="trace__label">{w.traceLabel(f.date(trace.date))}</figcaption>
                <dl className="trace__q">
                  <dt>{w.traceAsked(trace.after[lang], trace.lang)}</dt>
                  <dd lang={dataLang(trace.lang)}>{trace.asked}</dd>
                  <dt>{w.traceSearched}</dt>
                  <dd lang={dataLang(trace.lang)}>{trace.searched}</dd>
                </dl>
                <table className="trace__t">
                  <caption>{trace.caption[lang]}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{w.traceCols.issue}</th>
                      <th scope="col" className="r">{w.traceCols.score}</th>
                      <th scope="col">{w.traceCols.printer}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.issues.map((row, i) => (
                      <tr key={i}>
                        {/* the catalogue's titles and printers are in English, shown as stored */}
                        <th scope="row"><span lang={dataLang("en")}>{row.source != null && mark(row.source)}{row.title}</span></th>
                        <td className="r" data-label={w.traceCols.score}>{f.two(row.score)}</td>
                        <td data-label={w.traceCols.printer}><span lang={dataLang("en")}>{row.printer}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <dl className="trace__q trace__q--a">
                  <dt>{w.traceAnswer}</dt>
                  <dd lang={dataLang(trace.lang)}>
                    {trace.answer.map((s, i) => {
                      const cut = s.text.lastIndexOf(" ");
                      return (
                        <span key={i} className="trace__s">
                          {i > 0 ? " " : ""}
                          {s.text.slice(0, cut + 1)}
                          <span className="keep">{s.text.slice(cut + 1)}{s.sources.map((n) => <span key={n}> {mark(n)}</span>)}</span>
                        </span>
                      );
                    })}
                  </dd>
                </dl>
              </figure>
              <p>{trace.note[lang]}</p>
              <p>{w.whyAlone(f.of(F.full_text.first, F.full_text.of), f.of(F.issue_found.first, F.issue_found.of), f.of(F.full_text.es_first, F.full_text.es_of))}</p>
            </Section>

            <Section id="h-res" title={w.resH}>
              <p>{w.resSet(f.n(run.questions.all), f.n(run.questions.catalogue), f.n(run.questions.literature), f.n(run.questions.out_of_scope))}</p>
              <ul className="ledger" data-testid="results">
                {results.map((r) => (
                  <li key={r.id} data-result={r.id}>
                    <p className="ledger__n">{r.n}</p>
                    <p><b>{r.lead}</b> {r.text}</p>
                  </li>
                ))}
              </ul>
              <p className="limits" data-testid="limits">
                <b>{w.limitsLead}</b> {sealedText}{w.limitsRest(f.n(F.points_a_question[0]), f.n(F.points_a_question[1]))}{WEB ? w.limitsWeb + w.limitsTickets(run.web_tickets_outside_scope.ticketed, f.n(run.web_tickets_outside_scope.ticketed), f.n(run.web_tickets_outside_scope.of)) : ""}
              </p>
            </Section>

            <Section id="h-jud" title={w.judH}>
              <p>
                {w.judges(J.pages.first, J.pages.second, f.n(J.pages.sample), f.n(J.pages.same_grade), f.n(J.pages.same_answers_or_not))}
                {w.judgesAnswers(modelName(J.answers.second), f.n(J.answers.answers), f.n(J.answers.same_mark), f.two(J.answers.kappa))}
              </p>
            </Section>

            <Section id="h-tried" title={w.triedH}>
              <ul className="ledger ledger--small">
                {tried.map((x, i) => (
                  <li key={i}>
                    <p className="ledger__n">{x.n}</p>
                    <p>{x.text}</p>
                  </li>
                ))}
              </ul>
            </Section>

            <Section id="h-cost" title={w.costH}>
              {costs.length > 0 && (
                <ul className="costs" data-testid="costs">
                  {costs.map((c, i) => (
                    <li key={i}>
                      <b className="costs__n">{c.n}<span className="costs__unit"> {c.unit}</span></b>
                      <span>{c.text}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="costs__note">{run.waits ? `${w.waitsWhere[run.through]} ` : ""}{w.sleeps}</p>
            </Section>

            <Section id="h-safe" title={w.safeH}>
              <ul className="safe">
                {safe.map((s, i) => (
                  <li key={i}><b>{s.lead}</b> {s.text}</li>
                ))}
              </ul>
              <h3 id="h-priv" className="how__h3">{w.privH}</h3>
              <p data-testid="how-privacy">{privacyText(t)}</p>
            </Section>

            <Section id="h-more" title={w.moreH}>
              <p className="how__links" data-testid="how-links">
                <a href={EVAL_URL}>{w.linkEval}</a>
                <a href={REPO_URL}>{t.code}</a>
                <a href="/">{t.title}</a>
              </p>
              <details className="how__fold" data-testid="versions">
                <summary>{w.stackH}</summary>
                <dl className="how__stack">
                  {stack.map(([k, v]) => (
                    <Pair key={k} k={k} v={v} />
                  ))}
                </dl>
                <p>{w.stackNote}</p>
              </details>
            </Section>
          </div>
        </div>
      </main>
    </>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="how__sec" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      <div className="how__body">{children}</div>
    </section>
  );
}

function Pair({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
