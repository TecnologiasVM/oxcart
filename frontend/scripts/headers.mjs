// The response headers of the hosted site: out/_headers, which Cloudflare Pages reads at the root of the build
// output. Written by build-hosted.mjs after the build; `npm run build` writes none.
//
// One rule, for every path:
//   - a content security policy, built from what the two pages load and nothing wider. It is sent as
//     Content-Security-Policy-Report-Only for this first step (CSP_HEADER, below): a browser reports what it
//     would block, in its console, and blocks nothing. A later change sets CSP_HEADER to
//     "Content-Security-Policy", once the report-only header has been seen to report nothing.
//   - four headers enforced from the start, which break nothing on a static site.
//
// The policy:
//   script-src   'self', the sha256 hash of every inline script of every page of this build (Next's static export
//                writes a few a page, and they change with each build, so they are computed, never typed), and
//                Cloudflare's human check (its script; https://developers.cloudflare.com/turnstile/reference/content-security-policy/)
//   frame-src    the human check's frame
//   connect-src  'self' (stored-examples.json, the pages' .txt payloads), the backend, and the figures host
//                when the build names one (the first screen fetches first-screen.json from it)
//   img-src      'self' data:, and the figures host when named (the pictures)
//   style-src    'self' 'unsafe-inline': React writes style attributes (sizes, a margin) into the export's HTML
//                and at run time, and a style attribute cannot be allowed by a hash without 'unsafe-hashes'
//   font-src     'self' (the fonts are files of the build)
//   and base-uri, form-action, frame-ancestors, object-src; manifest-src only when the build has a manifest.
//
// Cloudflare reads a _headers line of at most 2,000 characters: a longer policy fails the build.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

/** The policy's header. Report-only for now; a later change makes it "Content-Security-Policy". */
export const CSP_HEADER = "Content-Security-Policy-Report-Only";
export const MAX_LINE = 2000;
export const TURNSTILE = "https://challenges.cloudflare.com";
export const ENFORCED = [
  ["X-Content-Type-Options", "nosniff"],
  ["Referrer-Policy", "strict-origin-when-cross-origin"],
  ["X-Frame-Options", "DENY"],
  ["Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"],
];

// a script element's type the browser runs (no type, or a JavaScript one); others (JSON data) run nothing
const RUNS = /^(?:|text\/javascript|application\/javascript|module)$/i;

/** The sha256 sources of the inline scripts of one HTML text, as the browser hashes them: the element's text. */
export function inlineScriptHashes(html) {
  const out = [];
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
    const attrs = m[1];
    if (/\ssrc\s*=/i.test(` ${attrs}`)) continue;
    const type = /\btype\s*=\s*["']?([^"'\s>]*)/i.exec(attrs);
    if (!RUNS.test(type ? type[1] : "")) continue;
    out.push(`'sha256-${createHash("sha256").update(m[2], "utf8").digest("base64")}'`);
  }
  return out;
}

function htmlFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...htmlFiles(path));
    else if (name.endsWith(".html")) out.push(path);
  }
  return out.sort();
}

/** Every inline script hash of every page under a build's output folder, each once, sorted. */
export function buildHashes(outDir) {
  return [...new Set(htmlFiles(outDir).flatMap((f) => inlineScriptHashes(readFileSync(f, "utf-8"))))].sort();
}

/** An address's origin, or "" when it is not a usable https address (http only on this machine, for tests). */
export function originOf(raw) {
  const text = (raw ?? "").trim();
  if (!text) return "";
  try {
    const url = new URL(text);
    const local = url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost");
    return url.protocol === "https:" || local ? url.origin : "";
  } catch {
    return "";
  }
}

/** The policy for a build: its inline script hashes, the backend's origin, and the figures host's when named. */
export function policy({ hashes, apiBase, figuresBase, manifest = false }) {
  const api = originOf(apiBase);
  if (!api) throw new Error("headers: NEXT_PUBLIC_API_BASE is not an https address, so the policy cannot name the backend");
  const figures = originOf(figuresBase);
  const join_ = (...parts) => parts.filter(Boolean).join(" ");
  return [
    "default-src 'none'",
    join_("script-src 'self'", ...hashes, TURNSTILE),
    `frame-src ${TURNSTILE}`,
    join_("connect-src 'self'", api, figures !== api ? figures : ""),
    join_("img-src 'self' data:", figures),
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    manifest ? "manifest-src 'self'" : "",
  ].filter(Boolean).join("; ");
}

/** The _headers file's text: one rule for every path. Fails when a line would pass Cloudflare's 2,000 characters. */
export function headersText(csp, name = CSP_HEADER) {
  const lines = [`  ${name}: ${csp}`, ...ENFORCED.map(([k, v]) => `  ${k}: ${v}`)];
  const long = lines.find((l) => l.length > MAX_LINE);
  if (long) {
    throw new Error(`headers: the ${name} line is ${long.length} characters; Cloudflare Pages reads at most ${MAX_LINE}. `
      + "Fewer inline scripts, or another way to allow them (a nonce needs a server), is needed before this can ship.");
  }
  return ["/*", ...lines].join("\n") + "\n";
}

/** Whether the build has a web app manifest (a file, or a page that links one). */
function hasManifest(outDir) {
  if (["manifest.json", "manifest.webmanifest", "site.webmanifest"].some((n) => existsSync(join(outDir, n)))) return true;
  return htmlFiles(outDir).some((f) => /<link\b[^>]*rel=["']?manifest/i.test(readFileSync(f, "utf-8")));
}

/** Write out/_headers for the build in outDir, from the build's own settings. Returns what it wrote. */
export function writeHeaders(outDir, env = process.env) {
  const hashes = buildHashes(outDir);
  const csp = policy({ hashes, apiBase: env.NEXT_PUBLIC_API_BASE, figuresBase: env.NEXT_PUBLIC_FIGURES_BASE, manifest: hasManifest(outDir) });
  const text = headersText(csp);
  writeFileSync(join(outDir, "_headers"), text);
  return { hashes: hashes.length, policyLength: csp.length, header: CSP_HEADER, text };
}
