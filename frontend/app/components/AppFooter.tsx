/*
 * AppFooter.tsx — neutral site footer (Server Component, pure markup).
 *
 * States what the demo is and is not. Rendered once in app/layout.tsx; pages do
 * not add their own footer.
 */
const REPO_URL = "https://github.com/TecnologiasVM/oxcart";

export function AppFooter() {
  return (
    <footer className="site-foot">
      <div className="container">
        <div className="site-foot__bar">
          <span className="mono muted">
            Oxcart · open-source research demo · short answers written from the evidence it shows
          </span>
          <a className="mono muted" href={REPO_URL} target="_blank" rel="noreferrer">
            Source · MIT
          </a>
        </div>
      </div>
    </footer>
  );
}

export default AppFooter;
