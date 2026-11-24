import type { MetadataRoute } from "next";
import { SITE } from "./link-picture";

/* The two pages of the hosted site, as out/sitemap.xml (a metadata route: a static file in the export). */
export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return [{ url: `${SITE}/` }, { url: `${SITE}/how-it-works` }];
}
