"use client";

import { useEffect, useState } from "react";
import { getExamples, postQuery } from "@/lib/api";
import type { ExampleQuery, QueryRequest, QueryResponse } from "@/lib/types";
import { issueDatesText } from "@/lib/format";
import { downloadQueryExport } from "@/lib/export";
import { GraphView } from "../components/GraphView";
import { NodeDetailPanel } from "../components/NodeDetailPanel";

/*
 * Query surface: a question box, example chips (GET /api/examples), and a results
 * region splitting into Domain, Subgraph, Sources, Lexical, and Weaviate panels.
 * BM25 is the default retrieval path (no API key); there is no answer generation.
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
      <form onSubmit={onSubmit}>
        <label className="mono-label" htmlFor="q">
          Question
        </label>
        <div style={{ display: "flex", gap: "var(--space-3)", marginTop: "var(--space-2)" }}>
          <input
            id="q"
            className="input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="How many covers exist of the 1 peso of the first issue?"
          />
          <button type="submit" className="btn" disabled={loading || !question.trim()}>
            {loading ? "Retrieving…" : "Retrieve"}
          </button>
        </div>
      </form>

      {/* Example chips */}
      {examples.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginTop: "var(--space-4)" }}>
          {examples.map((ex, i) => (
            <button
              key={i}
              type="button"
              className="btn"
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

      {error && (
        <p className="mono-label" role="alert" style={{ marginTop: "var(--space-4)" }}>
          Error: {error}
        </p>
      )}

      {result && (
        <div style={{ marginTop: "var(--space-8)" }}>
          <div
            style={{
              display: "flex",
              alignItems: "flex-end",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "var(--space-4)",
            }}
          >
            <Counts result={result} />
            <button
              type="button"
              className="btn"
              onClick={() => downloadQueryExport(resultQuestion || question, result)}
              title="Download a ready-to-paste prompt with all evidence for ChatGPT or Claude"
            >
              ↓ Export for ChatGPT / Claude (.txt)
            </button>
          </div>

          <hr className="rule-faint" />

          {/* Domain summary */}
          <DomainCard result={result} />

          {/* Subgraph + detail */}
          {result.subgraph && (result.subgraph.nodes?.length ?? 0) > 0 && (
            <>
              <hr className="rule-faint" />
              <p className="mono-label">Retrieval subgraph</p>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(0, 1fr) 300px",
                  gap: "var(--space-6)",
                  marginTop: "var(--space-3)",
                }}
              >
                <div style={{ height: 480 }}>
                  <GraphView graph={result.subgraph} onSelectNode={setSelectedNodeId} height="100%" />
                </div>
                <NodeDetailPanel nodeId={selectedNodeId} />
              </div>
            </>
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
    <div style={{ display: "flex", gap: "var(--space-8)", marginTop: "var(--space-4)" }}>
      <Stat n={c?.lexical ?? 0} label="lexical hits" />
      <Stat n={c?.weaviate ?? 0} label="weaviate hits" />
      <Stat n={c?.source_docs ?? 0} label="source docs" />
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div>
      <div className="serif-display" style={{ fontSize: "2rem" }}>
        {n}
      </div>
      <div className="mono-label">{label}</div>
    </div>
  );
}

function DomainCard({ result }: { result: QueryResponse }) {
  const d = result.domain;
  if (!d) return null;
  return (
    <section className="surface" style={{ marginTop: "var(--space-2)" }}>
      <p className="mono-label">{d.issue_id}</p>
      <h3 className="serif-display" style={{ marginTop: "var(--space-2)" }}>
        {d.title ?? "First Issue"}
      </h3>
      {d.plain_raw_text_excerpt && (
        <p style={{ marginTop: "var(--space-3)" }}>{d.plain_raw_text_excerpt}</p>
      )}
      <div style={{ display: "flex", gap: "var(--space-8)", marginTop: "var(--space-3)", flexWrap: "wrap" }}>
        {d.country && <KV k="Country" v={d.country} />}
        {d.issue_dates && <KV k="Dates" v={issueDatesText(d.issue_dates)} />}
        {d.perforation && <KV k="Perf" v={d.perforation} />}
        {Array.isArray(d.stamps) && <KV k="Stamps" v={String(d.stamps.length)} />}
      </div>
    </section>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="mono-label">{k}</div>
      <div style={{ fontSize: 14 }}>{v}</div>
    </div>
  );
}

function Sources({ result }: { result: QueryResponse }) {
  if (!result.sources || result.sources.length === 0) return null;
  return (
    <>
      <hr className="rule-faint" />
      <p className="mono-label">Sources</p>
      <ul style={{ listStyle: "none", padding: 0, margin: "var(--space-3) 0 0" }}>
        {result.sources.map((s) => (
          <li
            key={s.doc_id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "var(--space-4)",
              padding: "var(--space-2) 0",
              borderBottom: "1px solid var(--color-hairline)",
            }}
          >
            <span style={{ fontSize: 14 }}>{s.doc_id}</span>
            <span className="mono-label">
              {s.chunks} chunks · best {Number(s.best_score).toFixed(2)} · pp {(s.pages ?? []).join(",")}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Evidence({ result }: { result: QueryResponse }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
        gap: "var(--space-6)",
        marginTop: "var(--space-8)",
      }}
    >
      <div>
        <p className="mono-label">Lexical (graph)</p>
        {result.lexical?.length ? (
          result.lexical.map((h) => (
            <article key={h.chunk_id} className="surface" style={{ marginTop: "var(--space-3)" }}>
              <p className="mono-label">
                {h.doc_id} · p{h.page ?? "—"} · link {Number(h.link_score).toFixed(1)}
              </p>
              <p style={{ marginTop: "var(--space-2)", fontSize: 14 }}>{h.text}</p>
              {h.signals && h.signals.length > 0 && (
                <p className="mono-label" style={{ marginTop: "var(--space-2)" }}>
                  {h.signals.join(" · ")}
                </p>
              )}
            </article>
          ))
        ) : (
          <p className="mono-label" style={{ marginTop: "var(--space-2)" }}>
            none
          </p>
        )}
      </div>

      <div>
        <p className="mono-label">Weaviate (BM25 / hybrid)</p>
        {result.weaviate?.length ? (
          result.weaviate.map((h) => (
            <article key={h.chunk_id} className="surface" style={{ marginTop: "var(--space-3)" }}>
              <p className="mono-label">
                {h.doc_id} · p{h.page ?? "—"} · {Number(h.score).toFixed(3)}
              </p>
              <p style={{ marginTop: "var(--space-2)", fontSize: 14 }}>{h.snippet}</p>
            </article>
          ))
        ) : (
          <p className="mono-label" style={{ marginTop: "var(--space-2)" }}>
            none
          </p>
        )}
      </div>
    </div>
  );
}

export default QueryView;
