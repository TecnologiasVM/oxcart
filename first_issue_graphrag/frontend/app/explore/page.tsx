import { ExploreView } from "./ExploreView";

/*
 * Explore route (Server Component shell). The interactive graph lives in the
 * client ExploreView. Page chrome stays flat and editorial.
 */
export default function ExplorePage() {
  return (
    <main className="container" style={{ paddingTop: "var(--space-10)", paddingBottom: "var(--space-12)" }}>
      <p className="mono-label">Explore · Knowledge graph</p>
      <h1 style={{ maxWidth: "16ch", marginTop: "var(--space-3)" }}>Walk the graph.</h1>
      <p style={{ marginTop: "var(--space-3)" }}>
        The issue sits at the centre. Stamps, Scott equivalents, varieties, and the documents that
        cite them radiate outward. Select any node to read its record.
      </p>

      <hr className="rule-faint" />

      <ExploreView />
    </main>
  );
}
