import { test, expect } from "@playwright/test";
import { ask, box, mock, newest, runClock } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 5. the day's limit
test("finding 5: the box closed by the day's limit opens again when the UTC day changes", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-11-23T23:58:30Z") });
  await mock(page, { chatStatus: 429, ask: { error: "visitor_daily_limit", message: "made up" } });
  await page.goto("/");
  await ask(page, "A made-up question?");
  await expect(newest(page).getByTestId("turn-error")).toContainText("today's limit");
  await expect(box(page)).toBeDisabled();
  await runClock(page, 120);
  await expect(box(page)).toBeEnabled();
});
