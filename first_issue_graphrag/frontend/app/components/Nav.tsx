"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/*
 * Top navigation. Mono links FIRST in source/visual order per design spec:
 *   FIRST ISSUE / EXPLORE / QUERY.
 * The active link is marked with the single amber border (never amber type).
 */
const LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/", label: "First Issue" },
  { href: "/explore", label: "Explore" },
  { href: "/query", label: "Query" },
];

export function Nav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <nav className="nav" aria-label="Primary">
      <Link href="/" className="nav__brand">
        First Issue
      </Link>
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

export default Nav;
