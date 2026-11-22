import Link from "next/link";

/*
 * AppHeader.tsx — neutral site header (Server Component, pure markup).
 *
 * Presentation only: the brand line and a "demo" tag. Section navigation lives
 * in app/research/ResearchNav.tsx. Reuses the .masthead / .brand classes from
 * globals.css so a later redesign only has to touch this file and the CSS.
 *
 * `#masthead-page` is where a page puts its own part of the header: the question page
 * puts there "How it works", the source and its language button, in the visitor's language.
 */
/* The hosted site ships the question page only; the explorer is local research tooling. */
const HOSTED = process.env.NEXT_PUBLIC_HOSTED === "1";

export function AppHeader() {
  return (
    <header className="masthead">
      <div className="masthead__bar">
        <Link className="brand" href="/">
          <span className="brand__type">
            <span className="brand__name">Oxcart</span>
            <span className="brand__sub">Costa Rica philately · knowledge graph</span>
          </span>
        </Link>
        <span className="mono mono-muted" style={{ marginLeft: "auto" }} data-testid="demo-tag">
          Demo
        </span>
        <div id="masthead-page" className="masthead__page" />
        {!HOSTED && (
          <Link className="mono" href="/research" data-testid="research-link">
            Research tools
          </Link>
        )}
      </div>
    </header>
  );
}

export default AppHeader;
