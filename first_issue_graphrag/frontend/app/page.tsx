import Link from "next/link";
import { HealthBanner } from "./components/HealthBanner";
import { OverviewPanel } from "./components/OverviewPanel";
import { StampGlyph } from "./components/StampGlyph";

/*
 * Landing / First Issue overview (Server Component shell).
 *
 * Lean editorial layout (owner decision: minimalist, NOT a chart dashboard):
 * a hero with the encoded-stamp mark, a health strip, and the OverviewPanel
 * (stat row + Mena roster — no charts). Cobalt marks one word; amber lights one
 * perforation on the mark.
 */
export default function Page() {
  return (
    <main className="container" style={{ paddingBottom: "var(--space-16)" }}>
      <header className="hero">
        <div>
          <div className="hero__eyebrow">
            <span className="hero__tick" />
            <span className="mono">Costa Rica · 1863 · CR-1863-FIRST-ISSUE</span>
          </div>
          <h1>
            The first issue, as a <em className="cobalt">knowledge graph.</em>
          </h1>
          <p className="hero__lede">
            A reductionist explorer over the Mena 2018 catalogue, its Scott equivalents, and the
            philatelic literature documenting the 1863 first issue of Costa Rica. Retrieval is
            grounded and citation-first — there is no generated answer, only the evidence.
          </p>
          <div className="hero__actions">
            <Link href="/explore" className="btn btn--solid">
              Explore the graph <span className="btn__arrow">→</span>
            </Link>
            <Link href="/query" className="btn btn--ghost">
              Run a query
            </Link>
          </div>
        </div>

        <aside className="hero__mark">
          <StampGlyph denom="1863" variant="amber" w={170} h={210} title="Encoded postage stamp" />
          <div className="cap">
            <span className="mono mono-muted">Encoding</span>
            <span className="mono" style={{ marginTop: "6px" }}>
              Rectangle · perforation · vignette
            </span>
          </div>
        </aside>
      </header>

      <hr className="rule" />

      <HealthBanner />

      <hr className="rule-faint" />

      <OverviewPanel />
    </main>
  );
}
