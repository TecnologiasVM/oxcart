import { test, expect } from "@playwright/test";
import { WRITTEN, ask, mock, newest, PART, WEB_OK } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 10. the web request: no frame, a fresh ticket, a renewed session
test.describe("finding 10: the web request", () => {
  test("it does not wait for a frame (a tab in the background draws none)", async ({ page }) => {
    await page.addInitScript(() => {
      window.requestAnimationFrame = () => 0;
    });
    await mock(page, { written: PART });
    await page.route("**/api/chat/web", (route) => route.fulfill({ json: WEB_OK }));
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("web")).toContainText("A made-up page says a made-up thing.");
  });

  test("a ticket past its time is not sent", async ({ page }) => {
    await mock(page, { written: { ...PART, web: { ticket: "a-made-up-ticket", expires_in: 0 } } });
    let asked = 0;
    await page.route("**/api/chat/web", (route) => {
      asked += 1;
      return route.fulfill({ status: 403, json: { error: "ticket_refused" } });
    });
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page)).toContainText(WRITTEN.sentences[0].text);
    await page.waitForTimeout(500);
    expect(asked).toBe(0);
    await expect(newest(page).getByTestId("web-searching")).toHaveCount(0);
  });

  test("a session that expired before the web request is renewed once", async ({ page }) => {
    await mock(page, { written: PART });
    let sessions = 0;
    await page.route("**/api/session", (route) => {
      sessions += 1;
      return route.fulfill({ json: { session: `made-up-session-${sessions}`, expires_in: 600 } });
    });
    let asked = 0;
    await page.route("**/api/chat/web", (route) => {
      asked += 1;
      return asked === 1 ? route.fulfill({ status: 401, json: { error: "session_required" } }) : route.fulfill({ json: WEB_OK });
    });
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("web")).toContainText("A made-up page says a made-up thing.");
    expect(asked).toBe(2);
    expect(sessions).toBe(2);
  });
});
