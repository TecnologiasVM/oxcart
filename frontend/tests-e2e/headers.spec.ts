import { test, expect } from "@playwright/test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CSP_HEADER, MAX_LINE, buildHashes, headersText, inlineScriptHashes, originOf, policy, writeHeaders } from "../scripts/headers.mjs";

/*
 * scripts/headers.mjs, alone: the hosted build's out/_headers, from a made-up out/ folder in a temp directory.
 * No browser page. It is a spec because CI runs the frontend's checks as Playwright specs only. Every address is
 * made up (.invalid).
 */
const API = "https://backend.invalid";
const FIGS = "https://figures.invalid/crops";

// the sha256 of "alert(1)" and of "self.x=2", computed by hand (openssl dgst -sha256 -binary | base64)
const ALERT = "'sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI='";
const SELF_X = "'sha256-Lucm8PUUjG09QwIwt0stS08jQ2KRsBYtU5CWh/X2XFY='";

function madeUpOut() {
  const dir = mkdtempSync(join(tmpdir(), "oxcart-headers-"));
  writeFileSync(join(dir, "index.html"),
    '<!DOCTYPE html><html><head><script src="/_next/static/chunks/a.js" async=""></script></head>'
    + '<body><script>alert(1)</script><script type="application/json">{"made":"up"}</script></body></html>');
  mkdirSync(join(dir, "how-it-works"));
  // a second page: one script of its own, and the same one again (one hash for both)
  writeFileSync(join(dir, "how-it-works.html"), "<html><body><script>self.x=2</script><script>alert(1)</script></body></html>");
  writeFileSync(join(dir, "how-it-works", "index.txt"), "<script>not a page</script>");
  return dir;
}

test("each inline script gives the sha256 of its text; an external script and a JSON block give none", () => {
  expect(inlineScriptHashes("<script>alert(1)</script>")).toEqual([ALERT]);
  expect(inlineScriptHashes('<script src="/x.js"></script>')).toEqual([]);
  expect(inlineScriptHashes('<script type="application/json">{"a":1}</script>')).toEqual([]);
  // a schema.org data block (JSON-LD) is not run either: no hash
  expect(inlineScriptHashes('<script type="application/ld+json">{"@type":"Thing"}</script>')).toEqual([]);
  expect(inlineScriptHashes('<script type="module">alert(1)</script>')).toEqual([ALERT]);
});

test("a build's hashes: every page's inline scripts, each once, from the .html files only", () => {
  const dir = madeUpOut();
  try {
    expect(buildHashes(dir)).toEqual([ALERT, SELF_X].sort());
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the policy names the backend's and the figures host's origins, and no figures host when the setting is unset", () => {
  const hashes = [ALERT];
  const withFigures = policy({ hashes, apiBase: `${API}/`, figuresBase: FIGS });
  expect(withFigures).toBe(
    "default-src 'none'; "
    + `script-src 'self' ${ALERT} https://challenges.cloudflare.com; `
    + "frame-src https://challenges.cloudflare.com; "
    + "connect-src 'self' https://backend.invalid https://figures.invalid; "
    + "img-src 'self' data: https://figures.invalid; "
    + "style-src 'self' 'unsafe-inline'; font-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'");
  const without = policy({ hashes, apiBase: API, figuresBase: undefined });
  expect(without).toContain("connect-src 'self' https://backend.invalid;");
  expect(without).toContain("img-src 'self' data:;");
  expect(without).not.toContain("figures.invalid");
  expect(policy({ hashes, apiBase: API, figuresBase: "" })).toBe(without);
  // not an https address: no origin (the page draws no picture then either)
  expect(policy({ hashes, apiBase: API, figuresBase: "http://figures.invalid" })).toBe(without);
  expect(originOf("http://127.0.0.1:8090/x")).toBe("http://127.0.0.1:8090");
  expect(() => policy({ hashes, apiBase: "", figuresBase: FIGS })).toThrow(/NEXT_PUBLIC_API_BASE/);
  expect(policy({ hashes, apiBase: API, figuresBase: FIGS, manifest: true })).toMatch(/; manifest-src 'self'$/);
});

test("the file: one rule for every path, the policy enforced, the other headers", () => {
  const dir = madeUpOut();
  try {
    const made = writeHeaders(dir, { NEXT_PUBLIC_API_BASE: API, NEXT_PUBLIC_FIGURES_BASE: FIGS });
    const text = readFileSync(join(dir, "_headers"), "utf-8");
    expect(text).toBe(made.text);
    expect(CSP_HEADER).toBe("Content-Security-Policy");
    expect(made.header).toBe("Content-Security-Policy");
    expect(made.hashes).toBe(2);
    const lines = text.trimEnd().split("\n");
    expect(lines[0]).toBe("/*");
    expect(lines[1]).toMatch(/^ {2}Content-Security-Policy: default-src 'none'; script-src 'self' /);
    expect(lines.slice(2)).toEqual([
      "  X-Content-Type-Options: nosniff",
      "  Referrer-Policy: strict-origin-when-cross-origin",
      "  X-Frame-Options: DENY",
      "  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()",
      "  Strict-Transport-Security: max-age=86400",
    ]);
    expect(text).not.toContain("Report-Only");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a policy line longer than Cloudflare's 2,000 characters fails, and nothing is written", () => {
  const many = Array.from({ length: 40 }, (_, i) => inlineScriptHashes(`<script>self.n=${i}</script>`)[0]);
  const csp = policy({ hashes: many, apiBase: API, figuresBase: FIGS });
  expect(`  ${CSP_HEADER}: ${csp}`.length).toBeGreaterThan(MAX_LINE);
  expect(() => headersText(csp)).toThrow(/at most 2000/);
  const dir = mkdtempSync(join(tmpdir(), "oxcart-headers-long-"));
  try {
    writeFileSync(join(dir, "index.html"), many.map((_, i) => `<script>self.n=${i}</script>`).join(""));
    expect(() => writeHeaders(dir, { NEXT_PUBLIC_API_BASE: API })).toThrow(/2000/);
    expect(existsSync(join(dir, "_headers"))).toBe(false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("Strict-Transport-Security is there for one day, without includeSubDomains or preload", () => {
  const text = headersText(policy({ hashes: [ALERT], apiBase: API, figuresBase: FIGS }));
  const hsts = text.split("\n").filter((l) => l.startsWith("  Strict-Transport-Security:"));
  expect(hsts).toEqual(["  Strict-Transport-Security: max-age=86400"]);
  expect(text).not.toMatch(/includeSubDomains/i);
  expect(text).not.toMatch(/preload/i);
});
