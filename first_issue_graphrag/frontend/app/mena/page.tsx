import { MenaCatalogueView } from "./MenaCatalogueView";

/*
 * Mena Catalogue route (Server Component shell). A new way to navigate the Mena
 * 2018 catalogue via the graph + Weaviate, scoped to the Surface-Mail section
 * for this MVP. The interactive 3-pane navigator lives in the client view.
 */
export default function MenaPage() {
  return (
    <main className="container" style={{ paddingBottom: "var(--space-12)" }}>
      <header className="page-head">
        <div className="eyebrow">
          <span className="eyebrow__tick" />
          <span className="mono">Mena 2018 · Surface Mail</span>
        </div>
        <h1>
          Navigate the <em className="cobalt">catalogue.</em>
        </h1>
        <p className="page-head__lede">
          The Surface-Mail section of the Mena catalogue, by year then issue. Each issue loads its
          catalogue facts and Scott equivalents instantly; the graph and the literature evidence are
          one click away. This is the foundation for navigating the full catalogue through the graph.
        </p>
      </header>

      <MenaCatalogueView />
    </main>
  );
}
