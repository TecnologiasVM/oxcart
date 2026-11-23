import { test, expect } from "@playwright/test";
import { WRITTEN, ask, mock, newest } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 2. an old health reply
test("finding 2: a health reply older than an answer does not put the page back to waking", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  let release: () => void = () => {};
  let first = true;
  await page.route("**/api/health", async (route) => {
    if (!first) return route.fulfill({ json: { status: "ok" } });
    first = false;
    await new Promise<void>((r) => (release = r));
    return route.fulfill({ json: { status: "ok", graph: "connecting" } });
  });
  await page.goto("/");
  await ask(page, "A made-up question?");
  await expect(newest(page)).toContainText(WRITTEN.sentences[0].text);
  const answered = page.waitForResponse("**/api/health");
  release();
  await answered;
  // for two seconds after the old reply lands, the page never says it is waking again
  const seen: number[] = [];
  for (let i = 0; i < 20; i++) {
    seen.push(await page.getByTestId("service-starting").count());
    await page.waitForTimeout(100);
  }
  expect(Math.max(...seen)).toBe(0);
});
