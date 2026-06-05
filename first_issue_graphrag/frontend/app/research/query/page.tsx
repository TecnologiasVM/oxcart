import { QueryView } from "./QueryView";

/*
 * Query route (Server Component shell). The interactive form + results live in
 * the client QueryView. There is NO generated answer — only retrieval evidence.
 */
export default function QueryPage() {
  return (
    <main className="container" style={{ paddingBottom: "var(--space-12)" }}>
      <header className="page-head">
        <div className="eyebrow">
          <span className="eyebrow__tick" />
          <span className="mono">Query · Grounded retrieval</span>
        </div>
        <h1>
          Ask, and read the <em className="cobalt">evidence.</em>
        </h1>
        <p className="page-head__lede">
          Questions resolve to a domain record, a retrieval subgraph, and the literature chunks that
          ground them. No answer is generated — the sources are the answer.
        </p>
      </header>

      <QueryView />
    </main>
  );
}
