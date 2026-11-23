import { test, expect } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/*
 * A finding of an independent review of the page, on the build scripts or the generated figures, as the failure
 * it describes. No browser page. Every value changed in a test is made up.
 */
const FRONTEND = join(__dirname, "..");

// ------------------------------------------------------------------ 13. the hosted build's settings
test.describe("finding 13: the hosted build refuses an http backend and a missing human-check key", () => {
  /** build-hosted.mjs in a folder with its scripts and no packages: if it gets past its checks, it fails later, not with exit 2. */
  function hosted(env: Record<string, string>) {
    const dir = mkdtempSync(join(tmpdir(), "oxcart-hosted-"));
    try {
      mkdirSync(join(dir, "scripts"));
      for (const f of ["build-hosted.mjs", "headers.mjs", "store-examples.mjs"]) cpSync(join(FRONTEND, "scripts", f), join(dir, "scripts", f));
      const r = spawnSync(process.execPath, ["scripts/build-hosted.mjs"], { cwd: dir, encoding: "utf-8", timeout: 60_000, env: { PATH: process.env.PATH, ...env } });
      return { status: r.status, out: r.stdout + r.stderr };
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  }
  test("an http address is refused before anything is built", () => {
    const r = hosted({ NEXT_PUBLIC_API_BASE: "http://backend.invalid", NEXT_PUBLIC_TURNSTILE_SITE_KEY: "a-made-up-site-key" });
    expect(r.status).toBe(2);
    expect(r.out).toMatch(/https/);
    expect(r.out).not.toContain("stored examples");
  });
  test("no human-check site key is refused before anything is built", () => {
    const r = hosted({ NEXT_PUBLIC_API_BASE: "https://backend.invalid" });
    expect(r.status).toBe(2);
    expect(r.out).toMatch(/NEXT_PUBLIC_TURNSTILE_SITE_KEY/);
  });
  test("the override for the checks lets both through, and says so", () => {
    const r = hosted({ NEXT_PUBLIC_API_BASE: "http://backend.invalid", OXCART_HOSTED_MADE_UP_SETTINGS: "1" });
    expect(r.status).not.toBe(2);
    expect(r.out).toMatch(/OXCART_HOSTED_MADE_UP_SETTINGS/);
  });
});
