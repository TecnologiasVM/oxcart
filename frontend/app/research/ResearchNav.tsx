"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/*
 * Research sub-navigation. Mono links scoped to the /research surface:
 *   Overview / Explore / Query / Mena Catalogue.
 * Reuses the global .nav / .nav__links / .nav__link classes; the active link
 * carries the single amber underline (never amber type). Overview is active
 * only on the exact /research path; the others match by href prefix.
 */
const LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/research", label: "Overview" },
  { href: "/research/explore", label: "Explore" },
  { href: "/research/query", label: "Query" },
  { href: "/research/mena", label: "Mena Catalogue" },
];

export function ResearchNav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    if (href === "/research") return pathname === "/research";
    return pathname.startsWith(href);
  }

  return (
    <nav className="nav" aria-label="Research">
      <div className="nav__links">
        {LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`nav__link${isActive(link.href) ? " nav__link--active" : ""}`}
            aria-current={isActive(link.href) ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}

export default ResearchNav;
