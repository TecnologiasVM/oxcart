import { test, expect } from "@playwright/test";
import { WRITTEN, mock, newest, panel, seed } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 16. the Evidence sheet's focus trap at a phone's width
test("finding 16: in the Evidence sheet on a phone, Shift+Tab from the first control wraps to a visible one", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await seed(page, [{ question: "A made-up question?", written: WRITTEN }]);
  await mock(page);
  await page.goto("/");
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  const first = await panel(page).evaluate((p) => {
    const sel = 'button:not([disabled]), [href], summary, input:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const el = [...p.querySelectorAll<HTMLElement>(sel)].find((e) => e.checkVisibility());
    el?.setAttribute("data-first", "1");
    el?.focus();
    return Boolean(el);
  });
  expect(first).toBe(true);
  await page.keyboard.press("Shift+Tab");
  const after = await page.evaluate(() => {
    const a = document.activeElement as HTMLElement | null;
    return { inside: Boolean(a && document.getElementById("evidence-panel")?.contains(a)), visible: Boolean(a?.checkVisibility()), same: a?.getAttribute("data-first") === "1" };
  });
  expect(after).toEqual({ inside: true, visible: true, same: false });
});
