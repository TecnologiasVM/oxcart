/*
 * The site described for machines (schema.org, JSON-LD): a web application, free, in English and Spanish, and the
 * repository of its source code. One block, the same on both pages.
 *
 * It is a data block (<script type="application/ld+json">): the browser does not run it, so the site's policy
 * (scripts/headers.mjs) needs no hash for it and gives it none. Its text is this file's constant, made with
 * JSON.stringify and with "<" written as \u003c, so nothing in it can close the element; nothing a visitor typed or a
 * model wrote is in it.
 */
import { SITE, SITE_DESCRIPTION } from "./link-picture";

export const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "Oxcart",
  description: SITE_DESCRIPTION,
  url: `${SITE}/`,
  inLanguage: ["en", "es"],
  isAccessibleForFree: true,
  applicationCategory: "ReferenceApplication",
  isBasedOn: {
    "@type": "SoftwareSourceCode",
    name: "Oxcart",
    codeRepository: "https://github.com/TecnologiasVM/oxcart",
    programmingLanguage: ["Python", "TypeScript"],
  },
};

export default function StructuredData() {
  return (
    <script
      type="application/ld+json"
      // a constant of this file, as JSON, with "<" escaped: see the comment above
      dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA).replace(/</g, "\\u003c") }}
    />
  );
}
