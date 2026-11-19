import { ExploreView } from "./ExploreView";

/*
 * Explore route (Server Component shell). The interactive graph lives in the
 * client ExploreView. Page chrome stays flat and editorial.
 */
export default function ExplorePage() {
  return (
    <main className="container" style={{ paddingBottom: "var(--space-12)" }}>
      <header className="page-head">
        <div className="eyebrow">
          <span className="eyebrow__tick" />
          <span className="mono">Explore · Knowledge graph</span>
        </div>
        <h1>
          Walk the <em className="cobalt">graph.</em>
        </h1>
        <p className="page-head__lede">
          The issue sits at the centre — the dominant form. Stamps, Scott equivalents, varieties, and
          the documents that cite them radiate outward. Select any node to read its record.
        </p>
      </header>

      <ExploreView />
    </main>
  );
}
