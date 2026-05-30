"use client";

import { useEffect, useState } from "react";
import { getExamples, postQuery } from "@/lib/api";
import type { ExampleQuery, QueryRequest, QueryResponse } from "@/lib/types";
import { issueDatesText, issueDateEvents } from "@/lib/format";
import { downloadQueryExport } from "@/lib/export";
import { GraphView } from "../components/GraphView";
import { NodeDetailPanel } from "../components/NodeDetailPanel";

/*
 * Query surface: a question box, example chips (GET /api/examples), and a results
 * region — counts, a domain card with a chronology timeline, the retrieval
 * subgraph, ranked sources, and evidence in two columns (lexical | Weaviate).
 * BM25 is the default retrieval path (no API key); there is no answer generation.
 *
 * Frozen test selectors preserved: #q input, a /Retrieve/i button, example chips
 * as button.btn, exact "Sources", "Lexical (graph)", "Retrieval subgraph",
 * lexical hits as article.surface, .graph-frame/.graph-canvas.
 */
export function QueryView() {
  const [question, setQuestion] = useState("");
  const [stamp, setStamp] = useState<string>("");
  const [examples, setExamples] = useState<ExampleQuery[]>([]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultQuestion, setResultQuestion] = useState("");

  useEffect(() => {
    let cancelled = false;
    getExamples()
      .then((ex) => {
        if (!cancelled) setExamples(ex);
      })
      .catch(() => {
        /* examples are optional chrome; ignore failures */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(q: string, s?: string | null) {
    const body: QueryRequest = {
      question: q,
      stamp: s ?? (stamp || null),
      exclude_competing: true,
    };
    setLoading(true);
    setError(null);
    setSelectedNodeId(null);
    try {
      const res = await postQuery(body);
      setResult(res);
      setResultQuestion(q);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    void run(question.trim());
  }

  return (
    <div>
      <form className="q-form" onSubmit={onSubmit}>
        <label className="mono mono-muted" htmlFor="q">
          Question
        </label>
        <div className="q-row">
          <input
            id="q"
            className="input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How many covers exist of the 1 peso of the first issue?"
          />
          <button type="submit" className="btn btn--solid" disabled={loading || !question.trim()}>
            {loading ? "Retrieving…" : "Retrieve"} <span className="btn__arrow">→</span>
          </button>
        </div>

        {/* Example chips (button.btn preserved for the e2e selector) */}
        {examples.length > 0 && (
          <div className="q-examples">
            {examples.map((ex, i) => (
              <button
                key={i}
                type="button"
                className={`btn q-chip${question === ex.question ? " q-chip--active" : ""}`}
                onClick={() => {
                  setQuestion(ex.question);
                  setStamp(ex.stamp ?? "");
                  void run(ex.question, ex.stamp);
                }}
              >
                {ex.question}
              </button>
            ))}
          </div>
        )}
      </form>

      {error && (
        <p className="mono-label" role="alert" style={{ marginTop: "var(--space-4)" }}>
          Error: {error}
        </p>
      )}

      {result && (
        <div style={{ marginTop: "var(--space-6)" }}>
          <div className="q-results-head">
            <Counts result={result} />
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => downloadQueryExport(resultQuestion || question, result)}
              title="Download a ready-to-paste prompt with all evidence for ChatGPT or Claude"
            >
              ↓ Export for ChatGPT / Claude (.txt)
            </button>
          </div>

          <hr className="rule-faint" />

          {/* Domain summary + chronology */}
          <DomainCard result={result} />

          {/* Subgraph + detail */}
          {result.subgraph && (result.subgraph.nodes?.length ?? 0) > 0 && (
            <section className="section">
              <div className="section__head">
                <div>
                  <span className="mono mono-muted">Retrieval subgraph</span>
                  <h2 className="serif-h2" style={{ marginTop: "var(--space-2)" }}>
                    What the question touched.
                  </h2>
                </div>
              </div>
              <div className="explore-grid" style={{ marginTop: "var(--space-4)" }}>
                <div style={{ height: 460 }}>
                  <GraphView graph={result.subgraph} onSelectNode={setSelectedNodeId} height="100%" />
                </div>
                <NodeDetailPanel nodeId={selectedNodeId} />
              </div>
            </section>
          )}

          {/* Sources */}
          <Sources result={result} />

          {/* Lexical + Weaviate evidence */}
          <Evidence result={result} />
        </div>
      )}
    </div>
  );
}

function Counts({ result }: { result: QueryResponse }) {
  const c = result.counts;
  return (
    <div
      className="stats"
      style={{ border: "none", display: "inline-grid", gridTemplateColumns: "repeat(3, auto)" }}
    >
      <div className="stat" style={{ paddingLeft: 0 }}>
        <div className="stat__num serif-display">{c?.lexical ?? 0}</div>
        <span className="mono mono-muted">lexical hits</span>
      </div>
      <div className="stat">
        <div className="stat__num serif-display stat__num--mark">{c?.weaviate ?? 0}</div>
        <span className="mono cobalt">weaviate hits</span>
      </div>
      <div className="stat">
        <div className="stat__num serif-display">{c?.source_docs ?? 0}</div>
        <span className="mono mono-muted">source docs</span>
      </div>
    </div>
  );
}

function DomainCard({ result }: { result: QueryResponse }) {
  const d = result.domain;
  if (!d) return null;
  const events = issueDateEvents(d.issue_dates);
  return (
    <section className="domain">
      <div className="domain__body">
        <span className="mono mono-muted">{d.issue_id ?? "CR-1863-FIRST-ISSUE"} · domain record</span>
        <h3>{d.title ?? "First Issue"}</h3>
        {d.plain_raw_text_excerpt && <p className="domain__excerpt">{d.plain_raw_text_excerpt}</p>}
        <div className="domain__kv">
          {d.country && <KV k="Country" v={d.country} />}
          {d.perforation && <KV k="Perforation" v={d.perforation} />}
          {Array.isArray(d.stamps) && <KV k="Stamps" v={String(d.stamps.length)} />}
          {d.issue_dates && <KV k="Dates" v={issueDatesText(d.issue_dates)} />}
        </div>
      </div>
      {events.length >= 2 && <Timeline events={events} />}
    </section>
  );
}

function Timeline({ events }: { events: ReturnType<typeof issueDateEvents> }) {
  const n = events.length;
  return (
    <div className="timeline">
      <span className="mono mono-muted">Chronology · cobalt marks first circulation</span>
      <div className="timeline__track">
        <div className="timeline__line" />
        {events.map((e, i) => {
          const left = n === 1 ? 50 : 6 + (i / (n - 1)) * 88;
          return (
            <div
              key={i}
              className={`timeline__ev${e.focal ? " timeline__ev--focal" : ""}`}
              style={{ left: `${left}%` }}
            >
              <span className="yr">{e.yr}</span>
              <span className="lb">{e.label}</span>
              <span className="pt" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <span className="mono mono-muted">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

function Sources({ result }: { result: QueryResponse }) {
  if (!result.sources || result.sources.length === 0) return null;
  return (
    <section className="section" style={{ paddingTop: 0 }}>
      {/* "Sources" kept as a standalone element — frozen e2e selector getByText("Sources", exact). */}
      <div className="section__head" style={{ alignItems: "baseline" }}>
        <span className="mono mono-muted">Sources</span>
        <span className="mono mono-muted">ranked by best link score</span>
      </div>
      <ul className="sources">
        {result.sources.map((s) => (
          <li key={s.doc_id}>
            <span className="doc">{s.doc_id}</span>
            <span className="mono mono-muted">
              {s.chunks} chunks · best {Number(s.best_score).toFixed(2)} · pp {(s.pages ?? []).join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Evidence({ result }: { result: QueryResponse }) {
  return (
    <section className="section" style={{ paddingTop: 0 }}>
      <div className="evidence">
        <div>
          <div className="evi-col__head">
            <span className="mono">Lexical (graph)</span>
            <span className="mono mono-muted">link-scored</span>
          </div>
          {result.lexical?.length ? (
            result.lexical.map((h) => (
              <article key={h.chunk_id} className="surface evi-card evi-card--cobalt">
                <div className="evi-card__meta">
                  <span className="mono mono-muted">
                    {h.doc_id} · p{h.page ?? "—"}
                  </span>
                  {h.link_score != null && (
                    <span className="evi-card__score">link {h.link_score.toFixed(1)}</span>
                  )}
                </div>
                <p className="evi-card__text">{h.text}</p>
                {h.signals && h.signals.length > 0 && (
                  <div className="evi-card__signals">
                    {h.signals.map((sig, i) => (
                      <span key={i} className="chip">
                        {sig}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))
          ) : (
            <p className="mono-label mono-muted" style={{ marginTop: "var(--space-3)" }}>
              none
            </p>
          )}
        </div>

        <div>
          <div className="evi-col__head">
            <span className="mono">Weaviate · BM25 / hybrid</span>
            <span className="mono mono-muted">no key</span>
          </div>
          {result.weaviate?.length ? (
            result.weaviate.map((h, i) => (
              <article key={h.chunk_id ?? `weaviate-${i}`} className="surface evi-card">
                <div className="evi-card__meta">
                  <span className="mono mono-muted">
                    {h.doc_id} · p{h.page ?? "—"}
                  </span>
                  {h.score != null && <span className="evi-card__score">{h.score.toFixed(3)}</span>}
                </div>
                <p className="evi-card__text">{h.snippet}</p>
              </article>
            ))
          ) : (
            <p className="mono-label mono-muted" style={{ marginTop: "var(--space-3)" }}>
              none
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export default QueryView;
