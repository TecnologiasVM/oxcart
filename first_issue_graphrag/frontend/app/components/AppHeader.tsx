import Link from "next/link";

/*
 * AppHeader.tsx — neutral site header (Server Component, pure markup).
 *
 * Presentation only: the brand line and a "demo" tag. Section navigation lives
 * in app/research/ResearchNav.tsx. Reuses the .masthead / .brand classes from
 * globals.css so a later redesign only has to touch this file and the CSS.
 */
export function AppHeader() {
  return (
    <header className="masthead">
      <div className="masthead__bar">
        <Link className="brand" href="/research">
          <span className="brand__type">
            <span className="brand__name">Oxcart</span>
            <span className="brand__sub">Costa Rica philately · knowledge graph</span>
          </span>
        </Link>
        <span className="mono mono-muted" style={{ marginLeft: "auto" }} data-testid="demo-tag">
          Demo · retrieval only
        </span>
      </div>
    </header>
  );
}

export default AppHeader;
