"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { StampGlyph } from "./StampGlyph";

/*
 * Top navigation. Mono links per design spec:
 *   FIRST ISSUE / EXPLORE / QUERY / MENA CATALOGUE.
 * The active link is marked with the single amber border (never amber type).
 * The brand stamp glyph is decorative (aria-hidden) so the brand link's
 * accessible name stays exactly "First Issue".
 */
const LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/", label: "First Issue" },
  { href: "/explore", label: "Explore" },
  { href: "/query", label: "Query" },
  { href: "/mena", label: "Mena Catalogue" },
];

export function Nav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <nav className="nav" aria-label="Primary">
      <Link
        href="/"
        className="nav__brand"
        style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}
      >
        <StampGlyph w={18} h={22} variant="amber" />
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
