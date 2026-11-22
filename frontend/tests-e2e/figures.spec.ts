import { test, expect, Page } from "@playwright/test";
import {
  ANSWER, FIGURES_HOST, ISSUE, WRITTEN, ask, box, lines, mock, newest, noOverflow, panel, seed, seedMany, serveFigures,
} from "./helpers";

/*
 * Pictures: the figures of the cited pages (mock pages 70, 72, 73 and 77) and the first screen's
 * plate (pages 01 and 02). Every id, size, document and picture is made up: the pictures are
 * plain PNGs made in the test, served from the routed figures host.
 *
 * The site under test must be built with NEXT_PUBLIC_FIGURES_BASE=https://figures.invalid (the CI
 * workflow and playwright.config.ts set it); without it the page draws no picture at all.
 */

const id = (n: number) => n.toString(16).padStart(20, "0");
const [BIG, WIDE, SMALL, UNCITED] = [id(0xa1), id(0xa2), id(0xb3), id(0xc4)];
const SIZES: Record<string, [number, number]> = { [BIG]: [520, 305], [WIDE]: [483, 306], [SMALL]: [150, 120], [UNCITED]: [300, 400] };
const fig = (fid: string, cls: "A" | "B") => ({ id: fid, width: SIZES[fid][0], height: SIZES[fid][1], class: cls });

/** Four passages: two cited pages carry figures, one cited page carries none, one uncited page carries one. */
const EVIDENCE = {
  ...ANSWER,
  passages: [
    { ...ANSWER.passages[0], figures: [fig(BIG, "B"), fig(WIDE, "B")] },
    { ...ANSWER.passages[1], figures: [fig(SMALL, "A")] },
    { doc_id: "A THIRD DOCUMENT", page: 7, chunk_type: "text", text: "A third made-up passage.", clipped: false, score: 0.7 },
    { doc_id: "AN UNCITED DOCUMENT", page: 1, chunk_type: "text", text: "A fourth made-up passage.", clipped: false, score: 0.6, figures: [fig(UNCITED, "A")] },
  ],
};
const CITES = {
  ...WRITTEN,
  sentences: [
    { text: "The test issue was placed on sale on 20 September 1889.", cites: [1, 2] },
    { text: "Two made-up documents say more about it.", cites: [3, 4] },
  ],
  sources: [
    WRITTEN.sources[0],
    { n: 2, kind: "passage", index: 0, title: "A TEST DOCUMENT, page 12", quotes: ["A passage that answers the question."] },
    { n: 3, kind: "passage", index: 1, title: "ANOTHER DOCUMENT, page 3", quotes: ["A second passage."] },
    { n: 4, kind: "passage", index: 2, title: "A THIRD DOCUMENT, page 7", quotes: ["A third made-up passage."] },
  ],
};
const PLATE = Array.from({ length: 20 }, (_, i) => ({ digest: id(0x1000 + i), width: 200 + 13 * i, height: 320 - 7 * i }));
const PLATE_SIZES = Object.fromEntries(PLATE.map((p) => [p.digest, [p.width, p.height] as [number, number]]));

async function figuresPage(page: Page, width: number, written: object = CITES, evidence: object = EVIDENCE) {
  await page.setViewportSize({ width, height: 900 });
  await mock(page);
  await serveFigures(page, SIZES);
  await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(written, evidence) }));
  await page.goto("/");
}
const figures = (page: Page) => newest(page).getByTestId("figures");

/** Every drawn picture: its box, its file's pixels, its address. */
const pictures = (page: Page, scope: string) =>
  page.locator(`${scope} img`).evaluateAll((all) =>
    (all as HTMLImageElement[]).map((img) => {
      const r = img.getBoundingClientRect();
      return { w: r.width, h: r.height, nw: img.naturalWidth, nh: img.naturalHeight, src: img.src, alt: img.alt, lazy: img.loading, done: img.complete };
    }));

// ===================================================================== page 70: under the newest answer

test("figures under the newest answer: one group per cited page, none taller than 200 px, never larger than its file", async ({ page }) => {
  await figuresPage(page, 1440);
  await ask(page, "When was the test issue placed on sale?");
  await expect(figures(page)).toBeVisible();
  // last in the turn, under the Evidence button
  const button = (await newest(page).getByTestId("evidence-button").boundingBox())!;
  expect((await figures(page).boundingBox())!.y).toBeGreaterThan(button.y + button.height);
  await expect(figures(page)).toContainText("Figures on the cited pages");
  await expect(figures(page)).toContainText("2 of the 3 cited pages carry figures.");
  const groups = figures(page).getByTestId("figure-group");
  await expect(groups).toHaveCount(2);
  await expect(groups.nth(0)).toContainText("A TEST DOCUMENT");
  await expect(groups.nth(0)).toContainText("page 12");
  await expect(groups.nth(0)).toContainText("See the passage");
  await expect(groups.nth(1)).toContainText("ANOTHER DOCUMENT");
  await expect(figures(page)).not.toContainText("AN UNCITED DOCUMENT");         // an uncited page is not drawn here
  await expect(figures(page).getByTestId("figure")).toHaveCount(3);
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=figures] img")].every((i) => i.complete && i.naturalWidth > 0));
  const shown = await pictures(page, "[data-testid=figures]");
  for (const p of shown) {
    expect(p.h).toBeLessThanOrEqual(200);
    expect(p.w).toBeLessThanOrEqual(p.nw);
    expect(p.h).toBeLessThanOrEqual(p.nh);
    expect(p.src.startsWith(`${FIGURES_HOST}/`)).toBe(true);
    expect(p.src).toMatch(/\/[0-9a-f]{20}\.png$/);
    expect(p.lazy).toBe("lazy");
  }
  // 520 by 305 and 483 by 306 are held to 200 px (the width rounded down); 150 by 120 stays at its own size
  expect(shown.map((p) => Math.round(p.w))).toEqual([340, 315, 150]);
  expect(shown[0].h).toBeGreaterThan(199);
  expect(shown[1].h).toBeGreaterThan(199);
  expect(shown[2].h).toBe(120);
  // alt text built by the page from the class and the place
  expect(shown.map((p) => p.alt)).toEqual([
    "Figure 1 of 2 on this page: a cover or a postal marking",
    "Figure 2 of 2 on this page: a cover or a postal marking",
    "Figure 1 of 1 on this page: a stamp",
  ]);
  await noOverflow(page, "figures, 1440");
});

test("a picture's box is held on its tint before its file arrives, and nothing moves when it does", async ({ page }) => {
  await figuresPage(page, 1440);
  let release: () => void = () => {};
  const held = new Promise<void>((r) => (release = r));
  await page.route(`${FIGURES_HOST}/*.png`, async (route) => {
    await held;
    await route.fallback();
  });
  await ask(page, "When was the test issue placed on sale?");
  await expect(figures(page)).toBeVisible();
  const before = await pictures(page, "[data-testid=figures]");
  expect(before.every((p) => !p.done || p.nw === 0)).toBe(true);                 // no file has arrived
  expect(before.map((p) => Math.round(p.w))).toEqual([340, 315, 150]);
  expect(before.every((p) => p.h > 119 && p.h <= 200)).toBe(true);
  const sizes = before.map((p) => [p.w, p.h]);
  const tint = await figures(page).locator("img").first().evaluate((img) => getComputedStyle(img).backgroundColor);
  expect(tint).not.toBe("rgba(0, 0, 0, 0)");
  const last = async () => (await figures(page).getByTestId("figure-group").last().boundingBox())!;
  const groupBefore = await last();
  release();
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=figures] img")].every((i) => i.complete && i.naturalWidth > 0));
  const groupAfter = await last();
  expect(groupAfter.y).toBe(groupBefore.y);
  expect(groupAfter.height).toBe(groupBefore.height);
  expect((await pictures(page, "[data-testid=figures]")).map((p) => [p.w, p.h])).toEqual(sizes);
});

// ===================================================================== page 73: no figure

test("no figures: a turn whose cited pages carry none draws nothing and keeps no room", async ({ page }) => {
  // the cited pages carry no figure; an uncited one does, and stays in Evidence only
  const evidence = { ...ANSWER, passages: [ANSWER.passages[0], ANSWER.passages[1], EVIDENCE.passages[3]] };
  await figuresPage(page, 1440, WRITTEN, evidence);
  await ask(page, "When was the test issue placed on sale?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(page.getByTestId("figures")).toHaveCount(0);
  await expect(page.locator(".turn img")).toHaveCount(0);
  // the answer ends with its foot: no frame, no room
  const lastPart = await newest(page).getByTestId("written-answer").evaluate((el) => el.lastElementChild?.className);
  expect(lastPart).toBe("a__foot");
  // a figure that is not well formed is never drawn, and nothing it holds becomes an address
  const odd = { ...ANSWER, passages: [{ ...ANSWER.passages[0], figures: [
    { id: "../../evil", width: 10, height: 10, class: "A" }, { id: "javascript:alert(1)", width: 10, height: 10, class: "B" },
    { id: id(0xd5), width: 0, height: 10, class: "A" }, { id: id(0xd6), width: 10, height: 10, class: "C" },
  ] }, ANSWER.passages[1]] };
  await page.unroute("**/api/chat");
  await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(WRITTEN, odd) }));
  await ask(page, "And which documents mention it?");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(page.getByTestId("figures")).toHaveCount(0);
  await expect(page.locator(".conv img")).toHaveCount(0);
});

// ===================================================================== page 72: inside Evidence

test("the group opens Evidence on Cards and passages, at that page's figures", async ({ page }) => {
  await figuresPage(page, 1440);
  await ask(page, "When was the test issue placed on sale?");
  const group = figures(page).getByTestId("figure-group").nth(1);
  await group.click();
  await expect(panel(page)).toBeVisible();
  await expect(page.getByTestId("tab-found")).toHaveAttribute("aria-selected", "true");
  const block = panel(page).getByTestId("passage-figures").nth(1);
  await expect(block).toBeFocused();
  await expect(block).toContainText("Figures on ANOTHER DOCUMENT, page 3");
  // in the panel's view, under its bar
  const b = (await block.boundingBox())!;
  const tabs = (await page.locator(".evp .tabs").boundingBox())!;
  expect(b.y).toBeGreaterThanOrEqual(tabs.y + tabs.height - 1);
  expect(b.y).toBeLessThan(900);
  // closed, focus goes back to the group
  await page.keyboard.press("Escape");
  await expect(panel(page)).toHaveCount(0);
  await expect(group).toBeFocused();
});

test("the group is reached by keyboard, shows its focus, and opens Evidence with Enter", async ({ page }) => {
  await figuresPage(page, 820);
  await ask(page, "When was the test issue placed on sale?");
  await expect(figures(page)).toBeVisible();
  await newest(page).getByTestId("evidence-button").focus();
  let reached = false;
  for (let i = 0; i < 12 && !reached; i++) {
    await page.keyboard.press("Tab");
    reached = await figures(page).getByTestId("figure-group").first().evaluate((el) => el === document.activeElement);
  }
  expect(reached).toBe(true);
  const group = figures(page).getByTestId("figure-group").first();
  const ring = await group.evaluate((el) => {
    const s = getComputedStyle(el);
    return { style: s.outlineStyle, width: parseFloat(s.outlineWidth) };
  });
  expect(ring.style).not.toBe("none");
  expect(ring.width).toBeGreaterThanOrEqual(2);
  // clear of the box pinned at the foot
  const clear = await group.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const dock = document.querySelector<HTMLElement>(".dock")!;
    const pinned = (getComputedStyle(dock).display === "contents" ? document.querySelector<HTMLElement>("form.composer")! : dock).getBoundingClientRect();
    return r.top >= 0 && (r.bottom <= pinned.top || r.top >= pinned.bottom);
  });
  expect(clear).toBe(true);
  await page.keyboard.press("Enter");
  await expect(panel(page)).toBeVisible();
  await expect(panel(page).getByTestId("passage-figures").first()).toBeFocused();
});

test("inside Evidence a page's figures stand under its passage at their own size, with a count in its head line", async ({ page }) => {
  await figuresPage(page, 1440);
  await ask(page, "When was the test issue placed on sale?");
  await figures(page).getByTestId("figure-group").first().click();
  const passages = panel(page).getByTestId("passage");
  await expect(passages).toHaveCount(4);
  await expect(passages.nth(0).getByTestId("passage-figures-count")).toHaveText("2 figures");
  await expect(passages.nth(1).getByTestId("passage-figures-count")).toHaveText("1 figure");
  await expect(passages.nth(2).getByTestId("passage-figures-count")).toHaveCount(0);
  await expect(passages.nth(3).getByTestId("passage-figures-count")).toHaveText("1 figure");   // an uncited page's figure stands with its passage
  await expect(passages.nth(0).getByTestId("passage-figures")).toContainText("Figures on A TEST DOCUMENT, page 12");
  // under the passage's text
  const text = (await passages.nth(0).locator(".ev-passage__text").boundingBox())!;
  expect((await passages.nth(0).getByTestId("passage-figures").boundingBox())!.y).toBeGreaterThan(text.y + text.height - 1);
  await passages.nth(3).locator("summary").click();
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("#evidence-panel img")].every((i) => i.complete && i.naturalWidth > 0));
  const shown = await pictures(page, "#evidence-panel");
  expect(shown.map((p) => [Math.round(p.w), Math.round(p.h)])).toEqual([[520, 305], [483, 306], [150, 120], [300, 400]]);
  await noOverflow(page, "evidence figures, 1440");
  // on a phone they narrow to the sheet, never beyond their own size
  await page.setViewportSize({ width: 360, height: 800 });
  for (const p of await pictures(page, "#evidence-panel")) {
    expect(p.w).toBeLessThanOrEqual(p.nw);
    expect(p.w).toBeLessThanOrEqual(360);
  }
  await noOverflow(page, "evidence figures, 360");
});

// ===================================================================== page 77: an older answer

test("an older answer counts its figures beside its Evidence button; its pictures are one step away", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await seed(page, [
    { question: "When was the test issue placed on sale?", written: CITES, evidence: EVIDENCE },
    { question: "And who printed it?", written: WRITTEN },
  ]);
  await mock(page);
  await serveFigures(page, SIZES);
  await page.goto("/");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  const older = page.getByTestId("turn").first();
  await expect(older.locator(".evrow__counts")).toHaveText("4 sources · 3 figures");
  await expect(older.getByTestId("figures")).toHaveCount(0);
  await expect(older.locator("img")).toHaveCount(0);
  await older.getByTestId("evidence-button").click();
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("passage-figures")).toHaveCount(3);
  // in Spanish
  await page.getByTestId("lang-toggle").click();
  await expect(older.locator(".evrow__counts")).toHaveText("4 fuentes · 3 figuras");
});

// ===================================================================== kept in the browser

test("a kept turn keeps its figures' ids and sizes; a follow-up sends nothing about figures", async ({ page }) => {
  await figuresPage(page, 1440);
  await ask(page, "When was the test issue placed on sale?");
  await expect(figures(page).getByTestId("figure")).toHaveCount(3);
  const kept = await page.evaluate(() => JSON.parse(window.localStorage.getItem("oxcart-conversations") || "{}"));
  const passages = kept.conversations[0].turns[0].answer.passages;
  expect(passages[0].figures).toEqual([{ id: BIG, width: 520, height: 305, class: "B" }, { id: WIDE, width: 483, height: 306, class: "B" }]);
  expect(JSON.stringify(kept)).not.toContain(FIGURES_HOST);                       // ids, never an address
  const bodies: string[] = [];
  page.on("request", (r) => r.url().endsWith("/api/chat") && bodies.push(r.postData() ?? ""));
  await ask(page, "And who printed it?");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  expect(bodies).toHaveLength(1);
  expect(bodies[0]).not.toMatch(/figure|[0-9a-f]{20}|\.png/i);
  expect(Object.keys(JSON.parse(bodies[0]))).toEqual(["question", "thread"]);
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(page.getByTestId("turn").first().locator(".evrow__counts")).toHaveText("4 sources · 3 figures");
});

// ===================================================================== pages 01 and 02: the plate

async function firstScreen(page: Page, width: number, list: unknown = PLATE, opts: { status?: number; delay?: number; raw?: string } = {}) {
  await page.setViewportSize({ width, height: 900 });
  await mock(page);
  await serveFigures(page, PLATE_SIZES);
  await page.route(`${FIGURES_HOST}/first-screen.json`, async (route) => {
    if (opts.delay) await new Promise((r) => setTimeout(r, opts.delay));
    try {
      if (opts.raw !== undefined) await route.fulfill({ contentType: "application/json", body: opts.raw });
      else await route.fulfill({ status: opts.status ?? 200, json: list });
    } catch {
      /* the page gave up waiting: the request is gone */
    }
  });
}
const plate = (page: Page) => page.getByTestId("plate");
const shownCells = (page: Page) => plate(page).locator("li").evaluateAll((all) => all.filter((li) => getComputedStyle(li).display !== "none").length);

test("the first screen's plate, from the list on the figures host", async ({ page }) => {
  await firstScreen(page, 1440);
  await page.goto("/");
  await expect(plate(page)).toBeVisible();
  await expect(plate(page).locator("img")).toHaveCount(20);
  expect(await shownCells(page)).toBe(20);
  await expect(plate(page)).toContainText("Crops from the scanned philatelic literature the demo searches.");
  // decoration: no alt text, the list out of the reading order, the caption says what they are
  expect(await plate(page).locator("img").evaluateAll((all) => all.map((i) => i.getAttribute("alt")))).toEqual(Array(20).fill(""));
  await expect(plate(page).locator("ul")).toHaveAttribute("aria-hidden", "true");
  // beside the box from 1040 px, and the box keeps its place above the questions
  const q = (await box(page).boundingBox())!;
  const p = (await plate(page).boundingBox())!;
  expect(p.x).toBeGreaterThan(q.x + q.width);
  expect(p.y).toBeLessThan(q.y);
  // each crop in a square cell, never larger than its file
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=plate] img")].every((i) => i.complete && i.naturalWidth > 0));
  const cells = await plate(page).locator("li").evaluateAll((all) => all.map((li) => {
    const r = li.getBoundingClientRect();
    const img = li.querySelector("img")!;
    return { square: Math.abs(r.width - r.height) < 1.5, src: img.src, nw: img.naturalWidth };
  }));
  expect(cells.every((c) => c.square)).toBe(true);
  expect(cells.map((c) => c.src)).toEqual(PLATE.map((x) => `${FIGURES_HOST}/${x.digest}.png`));
  for (const width of [360, 820, 1100, 1280, 1440, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page, `plate, ${width}`);
  }
  // on a phone: under the questions to try, twelve cells
  await page.setViewportSize({ width: 360, height: 800 });
  expect(await shownCells(page)).toBe(12);
  const examples = (await page.locator(".examples").boundingBox())!;
  expect((await plate(page).boundingBox())!.y).toBeGreaterThan(examples.y + examples.height - 1);
});

test("the plate beside the box with the rail of kept conversations (page 02)", async ({ page }) => {
  await seedMany(page, [{ id: "c-one", at: new Date().toISOString(), turns: [{ question: "When was the test issue placed on sale?", written: WRITTEN }] }], "c-new");
  await firstScreen(page, 1440);
  await page.goto("/");
  await expect(page.getByTestId("rail")).toBeVisible();
  await expect(plate(page)).toBeVisible();
  const rail = (await page.getByTestId("rail").boundingBox())!;
  const q = (await box(page).boundingBox())!;
  const p = (await plate(page).boundingBox())!;
  expect(rail.x + rail.width).toBeLessThanOrEqual(q.x);
  expect(p.x).toBeGreaterThan(q.x + q.width);
  for (const width of [1100, 1280, 1440, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page, `plate and rail, ${width}`);
  }
});

test("the first screen with no list is today's: nothing drawn, nothing kept", async ({ page }) => {
  // today's first screen, measured with the list missing
  await firstScreen(page, 1440, null, { status: 404 });
  await page.goto("/");
  await expect(box(page)).toBeVisible();
  await page.waitForTimeout(300);
  await expect(plate(page)).toHaveCount(0);
  const today = (await page.locator(".first__head").boundingBox())!;
  // missing, malformed, partly malformed and slow lists: the same first screen
  const cases: [string, unknown, { status?: number; delay?: number; raw?: string }][] = [
    ["malformed", null, { raw: "{not json" }],
    ["not a list", { digest: PLATE[0].digest }, {}],
    ["one entry is not an id", [...PLATE.slice(0, 3), { digest: "../x", width: 10, height: 10 }], {}],
    ["empty", [], {}],
    ["slow", PLATE, { delay: 3500 }],
  ];
  for (const [what, list, opts] of cases) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await firstScreen(page, 1440, list, opts);
    await page.reload();
    await expect(box(page)).toBeVisible();
    await page.waitForTimeout(what === "slow" ? 4000 : 300);
    await expect(plate(page), what).toHaveCount(0);
    expect((await page.locator(".first__head").boundingBox())!, what).toEqual(today);
  }
});

// ===================================================================== every width, and screenshots

test("no horizontal overflow with figures, in the thread and in Evidence, at 360, 820, 1100, 1280, 1440 and 1600 px", async ({ page }) => {
  await figuresPage(page, 1440);
  await ask(page, "When was the test issue placed on sale?");
  await expect(figures(page)).toBeVisible();
  for (const width of [360, 820, 1100, 1280, 1440, 1600]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow(page, `figures, ${width}`);
    for (const p of await pictures(page, "[data-testid=figures]")) expect(p.h, `${width}`).toBeLessThanOrEqual(200);
    await figures(page).getByTestId("figure-group").first().click();
    await expect(panel(page)).toBeVisible();
    await noOverflow(page, `figures in Evidence, ${width}`);
    await page.getByTestId("evidence-close").click();
  }
});

test("screenshots of the figure states at 360 and 1440 px (kept under test-results, not committed)", async ({ page }) => {
  test.setTimeout(120_000);
  const shot = (name: string, width: number) => page.screenshot({ path: `test-results/screens/figures-${name}-${width}.png`, fullPage: true });
  for (const width of [360, 1440]) {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await firstScreen(page, width);
    await page.goto("/");
    await page.evaluate(() => window.localStorage.removeItem("oxcart-conversations"));
    await page.reload();
    await expect(plate(page)).toBeVisible();
    await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=plate] img")].filter((i) => i.offsetParent).every((i) => i.complete));
    await shot("01-first-plate", width);
    await serveFigures(page, SIZES);
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(CITES, EVIDENCE) }));
    await ask(page, "When was the test issue placed on sale?");
    await expect(figures(page)).toBeVisible();
    await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>("[data-testid=figures] img")].every((i) => i.complete));
    await shot("70-figures", width);
    await figures(page).getByTestId("figure-group").first().click();
    await expect(panel(page)).toBeVisible();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `test-results/screens/figures-72-evidence-${width}.png` });
    await page.getByTestId("evidence-close").click();
    await expect(panel(page)).toHaveCount(0);
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines({ ...WRITTEN, sources: [WRITTEN.sources[0]], sentences: [{ ...WRITTEN.sentences[0], cites: [1] }] }, { ...ANSWER, issues: [ISSUE] }) }));
    await ask(page, "And who printed it?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    await shot("73-77-none-and-older", width);
  }
});
