import Link from "next/link";
import { HealthBanner } from "./components/HealthBanner";
import { OverviewPanel } from "./components/OverviewPanel";

/*
 * Landing / First Issue overview (Server Component shell).
 * Editorial layout: large serif lede on cream, mono micro-labels, a single
 * cobalt rule as structural accent. Data loads in the client OverviewPanel.
 */
export default function Page() {
  return (
    <main className="container" style={{ paddingTop: "var(--space-12)", paddingBottom: "var(--space-16)" }}>
      <p className="mono-label">Costa Rica · 1863 · CR-1863-FIRST-ISSUE</p>

      <h1 style={{ maxWidth: "18ch", marginTop: "var(--space-4)" }}>
        The first issue, as a knowledge graph.
      </h1>

      <p style={{ marginTop: "var(--space-4)" }}>
        A reductionist explorer over the Mena 2018 catalog, its Scott equivalents, and the
        philatelic literature that documents the 1863 first issue of Costa Rica. Retrieval is
        grounded and citation-first — there is no generated answer, only the evidence.
      </p>

      <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "var(--space-6)" }}>
        <Link href="/explore" className="btn">
          Explore the graph
        </Link>
        <Link href="/query" className="btn">
          Run a query
        </Link>
      </div>

      <hr className="rule" />

      <HealthBanner />

      <hr className="rule-faint" />

      <OverviewPanel />
    </main>
  );
}
