import { test, expect } from "@playwright/test";
import { TURNSTILE_STUB, ask, box, mock, newest } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 3. the human check's script failed to load
test("finding 3: when the human check's script failed to load, the next question loads it again", async ({ page }) => {
  await mock(page);
  let fail = true;
  await page.route(/^https:\/\/challenges\.cloudflare\.com\/turnstile\//, (route) =>
    fail ? route.abort() : route.fulfill({ contentType: "text/javascript", body: TURNSTILE_STUB }));
  await page.goto("/");
  await box(page).focus();
  await page.waitForTimeout(500);
  fail = false;
  await ask(page, "A made-up question?");
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible({ timeout: 10_000 });
});

// ------------------------------------------------------------------ 4. the session exchange
test.describe("finding 4: the session exchange", () => {
  test("a refusal of the session keeps its status: a limit is not 'the service is unreachable'", async ({ page }) => {
    await mock(page);
    await page.route("**/api/session", (route) =>
      route.fulfill({ status: 429, json: { error: "visitor_minute_limit", message: "made up" }, headers: { "Retry-After": "30" } }));
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("turn-error")).toContainText("Too many questions in a minute");
    await page.waitForTimeout(300);
    await expect(page.getByTestId("service-unreachable")).toHaveCount(0);
  });

  test("a question sent while the first exchange is under way waits for it, and does not start another", async ({ page }) => {
    await mock(page);
    let sessions = 0;
    let release: () => void = () => {};
    await page.route("**/api/session", async (route) => {
      sessions += 1;
      if (sessions === 1) await new Promise<void>((r) => (release = r));
      return route.fulfill({ json: { session: `made-up-session-${sessions}`, expires_in: 600 } });
    });
    await page.goto("/");
    await box(page).focus();
    await expect.poll(() => sessions).toBe(1);
    await ask(page, "A made-up question?");
    await page.waitForTimeout(500);
    release();
    await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
    expect(sessions).toBe(1);
  });
});
