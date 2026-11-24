import type { Metadata } from "next";

/*
 * The picture a link to the site shows (Open Graph and Twitter): one file of the site, public/oxcart-card-c-stamp.png
 * (1280 by 640, the same bytes as docs/brand/oxcart-card-c-stamp.png), named by its absolute address on the site.
 * metadataBase (app/layout.tsx) makes the address absolute; each page gives its own title and description, and its
 * description is the picture's alt text.
 *
 * Set as metadata fields rather than with the opengraph-image / twitter-image files: both work in a static export,
 * but the files would be two copies of the picture with one alt text for every page.
 */
export const SITE = "https://oxcart.chat";
/** The site's title and description (the question page's, and the site's in its structured data). */
export const SITE_TITLE = "Oxcart · Costa Rica philately knowledge graph";
export const SITE_DESCRIPTION =
  "Research demo: ask about any Costa Rican stamp issue and read a short answer with its sources, written from the evidence of the catalogue graph and the philatelic literature.";
export const CARD = { url: "/oxcart-card-c-stamp.png", width: 1280, height: 640, type: "image/png" };

export function linkPicture(title: string, description: string, path: string): Pick<Metadata, "openGraph" | "twitter"> {
  return {
    openGraph: { type: "website", siteName: "Oxcart", url: path, title, description, images: [{ ...CARD, alt: description }] },
    twitter: { card: "summary_large_image", title, description, images: [{ url: CARD.url, alt: description }] },
  };
}
