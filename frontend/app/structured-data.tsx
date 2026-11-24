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
  // the path of a question, in the usual names of its techniques (the page "How it works" says the same)
  featureList: [
    "Query rewriting: a follow-up question is made to stand alone, and every question is translated into the other of Spanish and English",
    "Multi-query retrieval: the philatelic literature is searched by vectors once per language; a catalogue graph is searched with the question's own vector",
    "Reciprocal rank fusion (RRF) of the two lists of passages",
    "A short answer written only from the evidence found, in the language of the question, each sentence with a citation that is checked",
  ],
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
