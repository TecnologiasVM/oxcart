// Build the site for a static host: `npm run build:hosted` -> ./out
//
//   NEXT_PUBLIC_API_BASE            the backend's address (required, https): the page calls it directly, and the
//                                   build sends it the eval's key to store the examples
//   NEXT_PUBLIC_TURNSTILE_SITE_KEY  the human check's public site key (required: the hosted backend refuses every
//                                   question without the check)
//   EXAMPLES_EVAL_KEY               optional: lets the build store the example questions' evidence (store-examples.mjs)
//   NEXT_PUBLIC_FIGURES_BASE        optional: the figures host (https); without it the page draws no picture
//   NEXT_PUBLIC_WEB                 optional (1, true, yes, on): the page asks for the web part and its privacy
//                                   paragraph names the search service; without it neither
//
// The hosted site ships the question page and "How it works" (which calls nothing). The explorer under /research is local
// research tooling: its routes need a backend mode the hosted backend does not mount, so
// they are removed from the output.
//
// OXCART_HOSTED_MADE_UP_SETTINGS=1 is for the checks that build the hosted site with made-up settings (CI, a
// development machine): it lets an http address and no site key through, and the build says so. A build made
// with it is not one to deploy.
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
const madeUp = process.env.OXCART_HOSTED_MADE_UP_SETTINGS === "1";
const https = (() => {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_BASE).protocol === "https:";
  } catch {
    return false;
  }
})();
if (!madeUp && !https) {
  console.error("NEXT_PUBLIC_API_BASE must be an https address: the page is served over https, and the build sends the backend the eval's key.");
  process.exit(2);
}
if (!madeUp && !process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY) {
  console.error("NEXT_PUBLIC_TURNSTILE_SITE_KEY is not set: the hosted backend refuses every question that has not passed the human check.");
  process.exit(2);
}
if (madeUp) console.log("OXCART_HOSTED_MADE_UP_SETTINGS=1: the backend's address and the human check are not checked. Not a build to deploy.");
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
