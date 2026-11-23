// Build the site for a static host: `npm run build:hosted` -> ./out
//
//   NEXT_PUBLIC_API_BASE            the backend's address (required): the page calls it directly
//   NEXT_PUBLIC_TURNSTILE_SITE_KEY  the human check's public site key (without it the page asks without a check)
//   EXAMPLES_EVAL_KEY               optional: lets the build store the example questions' evidence (store-examples.mjs)
//   NEXT_PUBLIC_FIGURES_BASE        optional: the figures host (https); without it the page draws no picture
//   NEXT_PUBLIC_WEB                 optional (1, true, yes, on): the page asks for the web part and its privacy
//                                   paragraph names the search service; without it neither
//
// The hosted site ships the question page and "How it works" (which calls nothing). The explorer under /research is local
// research tooling: its routes need a backend mode the hosted backend does not mount, so
// they are removed from the output.
//
// Then out/_headers: the response headers Cloudflare Pages sends with every file, among them a content security
// policy built from this build's own pages (headers.mjs). Only this build writes it.
import { spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import { writeHeaders } from "./headers.mjs";

if (!process.env.NEXT_PUBLIC_API_BASE) {
  console.error("NEXT_PUBLIC_API_BASE is not set: a static site has no proxy, the page must know the backend's address.");
  process.exit(2);
}
const env = { ...process.env, OXCART_EXPORT: "1", NEXT_PUBLIC_HOSTED: "1" };
const run = (args) => {
  const result = spawnSync(process.execPath, args, { stdio: "inherit", env });
  if (result.status !== 0) process.exit(result.status ?? 1);
};
run(["scripts/store-examples.mjs"]);
run(["node_modules/next/dist/bin/next", "build"]);
for (const path of ["out/research", "out/research.html", "out/research.txt"]) {
  if (existsSync(path)) rmSync(path, { recursive: true });
}
try {
  const made = writeHeaders("out");
  console.log(`headers: out/_headers (${made.header}, ${made.hashes} inline script hashes, a policy of ${made.policyLength} characters)`);
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
console.log("static site in ./out (the question page and How it works)");
