import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { ANSWER, ISSUE, OTHER_ISSUE, THREAD, WRITTEN, mock, newest, panel, seed } from "./helpers";

/*
 * Two defects seen in the README's pictures and on the served page, as the failures they were, with made-up
 * fixtures and a mocked backend. No live backend, no window.
 *  - In Spanish, the rail's "+ Conversación nueva" broke into three lines with the "+" alone on the left.
 *  - In the graph, a long title ran past the right border of its box: the lines were broken by a count of
 *    characters, not by their width.
 */

/** Every visible button under `roots` whose sign (a "+", a "«") stands on a line of its own, or that is wider than itself. */
const brokenButtons = (page: Page, roots: string) =>
  page.evaluate((roots) => {
    const bad: string[] = [];
    for (const b of document.querySelectorAll<HTMLElement>(roots)) {
      const box = b.getBoundingClientRect();
      if (!box.width || !box.height || getComputedStyle(b).visibility === "hidden") continue;
      const name = b.dataset.testid || (b.textContent || "").trim().slice(0, 30);
      const chars: [Text, number, string][] = [];
      const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT, {
        acceptNode: (n) => (n.parentElement?.closest(".vh") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
      });
      for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null)
        for (let i = 0; i < n.data.length; i++) if (n.data[i].trim()) chars.push([n, i, n.data[i]]);
      const top = ([n, i]: [Text, number, string]) => {
        const r = document.createRange();
        r.setStart(n, i);
        r.setEnd(n, i + 1);
        return r.getBoundingClientRect().top;
      };
      const first = chars[0];
      const letter = chars.find((c) => /\p{L}/u.test(c[2]));
      if (first && letter && first !== letter && Math.abs(top(first) - top(letter)) > 4) bad.push(`${name}: its sign stands on a line of its own`);
      if (b.scrollWidth > b.clientWidth + 1) bad.push(`${name}: wider than itself`);
    }
    return bad;
  }, roots);

for (const width of [1100, 1280, 1440]) {
  test(`at ${width} px, in Spanish, no button of the rail or the thread leaves its sign alone on a line`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
    await mock(page);
    await seed(page, THREAD);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    const rail = page.getByTestId("new-conversation");
    await expect(rail).toBeVisible();
    await expect(rail).toContainText("Conversación nueva");
    expect(await brokenButtons(page, ".rail button, .conv button")).toEqual([]);
    // with Evidence open the rail gives way to the thread's own bar: its buttons too
    await newest(page).getByTestId("evidence-button").click();
    await expect(panel(page)).toBeVisible();
    expect(await brokenButtons(page, ".rail button, .conv button, [data-testid=evidence-panel] button")).toEqual([]);
  });
}

test("the English rail is as it was: '+ New conversation' on one line", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "en"));
  await mock(page);
  await seed(page, THREAD);
  await page.goto("/");
  const rail = page.getByTestId("new-conversation");
  await expect(rail).toHaveText(/^\+\s*New conversation$/);
  // the lines its characters stand on, told by the top of each character's box
  const lines = await rail.evaluate((b) => {
    const tops = new Set<number>();
    const walker = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
      if (n.parentElement?.closest(".vh")) continue;
      for (let i = 0; i < n.data.length; i++) {
        if (!n.data[i].trim()) continue;
        const r = document.createRange();
        r.setStart(n, i);
        r.setEnd(n, i + 1);
        tops.add(Math.round(r.getBoundingClientRect().top / 8));
      }
    }
    return tops.size;
  });
  expect(lines).toBe(1);
});

/* Made-up cards whose names are long and set in wide letters, cited and found. */
const WIDE = {
  ...ISSUE,
  issue_id: "CR-TEST-WIDE-MAMMOTH-WAVE-MEMORIAL",
  title: "Made-up Mammoth Wave Memorial Overprint Commemoration issue",
  card: { ...ISSUE.card, printers: ["MMWW Made-up Mammoth Works of Wide Engravings"], acts: [{ type: "decree", id: "Made-up Memorandum WM #4400", date: "1889-01-02" }] },
};
const WIDE_FOUND = { ...OTHER_ISSUE, issue_id: "CR-TEST-WIDE-FOUND", title: "Surcharges Made-up Wavemouth Annexation issue" };
const EVIDENCE = { ...ANSWER, issues: [WIDE, WIDE_FOUND] };
const CITED = {
  ...WRITTEN,
  sources: [
    { ...WRITTEN.sources[0], title: `Catalogue card: ${WIDE.title}` },
    { ...WRITTEN.sources[1], title: "A MADE-UP WIDE DOCUMENT OF MANY MEMOIRS, page 12" },
  ],
};

/** Every text of every node of the graph that runs past its box, in the drawing's units. */
const overflowing = (page: Page) =>
  page.getByTestId("graph-drawing").evaluate((drawing) => {
    const bad: string[] = [];
    drawing.querySelectorAll<SVGGElement>('[data-testid="graph-node"]').forEach((node, k) => {
      const rect = node.querySelector("rect")!.getBBox();
      node.querySelectorAll<SVGTextElement>("text").forEach((text) => {
        const b = text.getBBox();
        if (b.x < rect.x - 0.5 || b.x + b.width > rect.x + rect.width - 2 || b.y + b.height > rect.y + rect.height + 0.5)
          bad.push(`node ${k} "${(text.textContent || "").slice(0, 24)}": ${Math.round(b.x + b.width - rect.x - rect.width)} past its right side`);
      });
    });
    return bad;
  });

for (const width of [760, 1100, 1280, 1440, 1920]) {
  test(`at ${width} px, no text of a graph's node is wider than its box; a long title wraps and its box grows`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mock(page);
    await seed(page, [{ question: "When was the wide test issue placed on sale?", written: CITED, evidence: EVIDENCE }]);
    await page.goto("/");
    await newest(page).getByTestId("evidence-button").click();
    await expect(panel(page).getByTestId("graph-drawing")).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect.poll(() => overflowing(page)).toEqual([]);
    // the found card's long title takes two lines, and its box is the taller for it
    const found = panel(page).locator('[data-testid="graph-node"][aria-label$="(CR-TEST-WIDE-FOUND)"]');
    await expect(found.locator("text:not(.g-mono)")).toHaveCount(2);
  });
}
