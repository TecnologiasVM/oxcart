import { test, expect } from "@playwright/test";
import { mock, runClock } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 18. the end of the waiting is announced
test("finding 18: the service-unreachable line is announced, in the same status region that said it was waking", async ({ page }) => {
  await page.clock.install();
  await mock(page, { health: 0 });
  await page.goto("/");
  await runClock(page, 10);
  // the status region that holds the waking lines (it may be the element that carries the waking lines itself)
  const region = page.locator('[role="status"]:has([data-testid="service-starting"]), [role="status"][data-testid="service-starting"]').first();
  // the region itself may take no room (on the first screen its line is pinned to the screen's foot)
  await expect(region).toHaveCount(1);
  await expect(page.getByTestId("service-starting")).toBeVisible();
  await region.evaluate((el) => el.setAttribute("data-region", "1"));
  await runClock(page, 100);
  await expect(page.getByTestId("service-unreachable")).toBeVisible();
  await expect(page.locator('[data-region="1"][role="status"]')).toContainText(/not answering right now/);
});
