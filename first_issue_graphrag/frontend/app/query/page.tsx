import { QueryView } from "./QueryView";

/*
 * Query route (Server Component shell). The interactive form + results live in
 * the client QueryView. There is NO generated answer — only retrieval evidence.
 */
export default function QueryPage() {
  return (
    <main className="container" style={{ paddingTop: "var(--space-10)", paddingBottom: "var(--space-12)" }}>
      <p className="mono-label">Query · Grounded retrieval</p>
      <h1 style={{ maxWidth: "18ch", marginTop: "var(--space-3)" }}>Ask, and read the evidence.</h1>
      <p style={{ marginTop: "var(--space-3)" }}>
        Questions resolve to a domain record, a retrieval subgraph, and the literature chunks that
        ground them. No answer is generated — the sources are the answer.
      </p>

      <hr className="rule-faint" />

      <QueryView />
    </main>
  );
}
