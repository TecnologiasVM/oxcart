import { test, expect, Page } from "@playwright/test";
import { inlineScriptHashes, policy } from "../scripts/headers.mjs";
import { ANSWER, FIGURES_HOST, WRITTEN, ask, box, lines, mock, newest, panel, serveFigures } from "./helpers";

/*
 * The hosted site's content security policy, ENFORCED, on both pages of the build under test.
 *
 * The hosted site sends the policy from out/_headers (scripts/headers.mjs), and only Cloudflare reads that file;
 * the server the specs run is not Cloudflare, and its build is not the static export. So this spec makes the
 * policy the same way, from each page's own HTML as this server sends it (the hashes of its inline scripts), with
 * the specs' settings (the backend is this server, the figures host is the specs' made-up one), and adds it to
 * the page's response as an enforced Content-Security-Policy header through the test's routing.
 *
 * It fails on any securitypolicyviolation event, or a console message about the policy, while a visitor's path
 * runs: the page loads, the box takes focus (the human check's script loads: the specs' stub, from Cloudflare's
 * address), a question is asked and answered (the specs' fake backend), with a web part, pictures on the cited
 * page and on the first screen, Evidence opens, then "How it works" opens and its fold opens. Last, it checks that
 * the policy is really enforced: a script added to the page at run time is blocked and reported.
 *
 * What it does not prove: the real Cloudflare script and frame (the stub draws no frame and loads nothing more),
 * the real figures host, a real backend at another origin, and the exact HTML of the static export (whose hashes
 * the build computes the same way from its own files).
 */
const id = (n: number) => n.toString(16).padStart(20, "0");
const FIG = id(0xa1);
const PLATE = Array.from({ length: 20 }, (_, i) => ({ digest: id(0x1000 + i), width: 200 + 13 * i, height: 320 - 7 * i }));
const SIZES: Record<string, [number, number]> = Object.fromEntries([[FIG, [400, 300]], ...PLATE.map((p) => [p.digest, [p.width, p.height]])]);
const EVIDENCE = { ...ANSWER, passages: [{ ...ANSWER.passages[0], figures: [{ id: FIG, width: 400, height: 300, class: "A" }] }, ANSWER.passages[1]] };
const PART = { ...WRITTEN, covers: "part", web: { ticket: "a-made-up-ticket", expires_in: 120 } };
const WEB_PART = {
  state: "ok",
  sentences: [{ text: "A made-up page says a made-up thing.", cites: [1] }],
  results: [{ n: 1, title: "A made-up page", host: "pages.example", url: "https://pages.example/made-up" }],
};

/** Every document of this site gets the policy, made from its own HTML; the violations are kept in the page. */
async function enforce(page: Page, base: string) {
  const made: string[] = [];
  await page.route(`${base}/**`, async (route) => {
    if (route.request().resourceType() !== "document") return route.fallback();
    const response = await route.fetch();
    const body = await response.text();
    const csp = policy({ hashes: [...new Set(inlineScriptHashes(body))], apiBase: base, figuresBase: process.env.NEXT_PUBLIC_FIGURES_BASE });
    made.push(csp);
    await route.fulfill({ response, body, headers: { ...response.headers(), "content-security-policy": csp } });
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => w.__csp.push(`${e.effectiveDirective} ${e.blockedURI}`));
  });
  return made;
}

const violations = (page: Page) => page.evaluate(() => (window as unknown as { __csp: string[] }).__csp);

/** A script added at run time: the policy must block it and report it. */
async function blocksAnAddedScript(page: Page) {
  await page.evaluate(() => {
    const s = document.createElement("script");
    s.textContent = "window.__ran = true";
    document.head.appendChild(s);
  });
  await expect.poll(() => violations(page)).toEqual([expect.stringMatching(/^script-src-elem inline$/)]);
  expect(await page.evaluate(() => (window as unknown as { __ran?: boolean }).__ran)).toBeUndefined();
}

test("both pages work under the hosted policy, enforced: nothing is blocked along a visitor's path", async ({ page, baseURL }) => {
  const base = new URL(baseURL!).origin;
  const console_: string[] = [];
  page.on("console", (m) => {
    if (/Content Security Policy/i.test(m.text())) console_.push(m.text());
  });
  const made = await enforce(page, base);
  await mock(page, { written: PART, ask: EVIDENCE });
  await serveFigures(page, SIZES);
  await page.route(`${FIGURES_HOST}/first-screen.json`, (route) => route.fulfill({ json: PLATE, headers: { "Access-Control-Allow-Origin": "*" } }));
  await page.route("**/api/chat/web", (route) => route.fulfill({ json: WEB_PART }));

  // the question page: the first screen with its pictures, the box, the human check's script
  await page.goto("/");
  expect(made[0]).toMatch(/^default-src 'none'; script-src 'self' 'sha256-/);
  await expect(page.getByTestId("plate").locator("img").first()).toBeVisible();
  await box(page).focus();
  await expect.poll(() => page.evaluate(() => Boolean((window as unknown as { turnstile?: unknown }).turnstile))).toBe(true);
  // a question, its answer with a picture of the cited page, the web part, and Evidence
  await ask(page, "A made-up question?");
  await expect(newest(page).getByTestId("figures").locator("img").first()).toBeVisible();
  await expect(newest(page)).toContainText("A made-up page says a made-up thing.");
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await blocksAnAddedScript(page);

  // "How it works", and its fold
  await page.goto("/how-it-works");
  await expect(page.locator("h1")).toBeVisible();
  await page.getByTestId("versions").locator("summary").click();
  await expect(page.getByTestId("versions")).toHaveAttribute("open");
  expect(await violations(page)).toEqual([]);
  await blocksAnAddedScript(page);

  expect(made).toHaveLength(2);
  // only the two added scripts were reported in the console
  expect(console_.filter((m) => !/inline/i.test(m))).toEqual([]);
  expect(console_).toHaveLength(2);
});
