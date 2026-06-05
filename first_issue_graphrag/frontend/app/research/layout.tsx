import type { ReactNode } from "react";
import { ResearchNav } from "./ResearchNav";

/*
 * Research section layout (Server Component). Renders the research sub-nav
 * (a client component) above the active /research page. The sub-nav is wrapped
 * in a .container so it aligns with the page content below it.
 */
interface ResearchLayoutProps {
  children: ReactNode;
}

export default function ResearchLayout({ children }: ResearchLayoutProps) {
  return (
    <>
      <div className="container">
        <ResearchNav />
      </div>
      {children}
    </>
  );
}
