import { test, expect } from "@playwright/test";
import { ask, box, mock, newest, PART, submitButton, runClock, heldStream } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 1. every wait has an end
test.describe("finding 1: no request leaves the page waiting without end", () => {
  test("a question whose request never answers ends with a message, and the box takes the next", async ({ page }) => {
    await page.clock.install();
    await mock(page);
    await page.route("**/api/chat", () => new Promise(() => {}));
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("searching-bar")).toBeVisible();
    await runClock(page, 130);
    await expect(newest(page).getByTestId("turn-error")).toBeVisible();
    await box(page).fill("A second made-up question?");
    await expect(submitButton(page)).toBeEnabled();
  });

  test("evidence, then a stream that never ends: the evidence stays, the writing ends", async ({ page }) => {
    await page.clock.install();
    await heldStream(page, null);
    await mock(page);
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("writing")).toBeVisible();
    await runClock(page, 70);
    await expect(newest(page).getByTestId("writing")).toHaveCount(0);
    await expect(newest(page).getByTestId("no-written-answer")).toBeVisible();
    await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
    await box(page).fill("A second made-up question?");
    await expect(submitButton(page)).toBeEnabled();
  });

  test("a web request that never answers: the searching line ends", async ({ page }) => {
    await page.clock.install();
    await mock(page, { written: PART });
    await page.route("**/api/chat/web", () => new Promise(() => {}));
    await page.goto("/");
    await ask(page, "A made-up question?");
    await expect(newest(page).getByTestId("web-searching")).toBeVisible();
    await runClock(page, 70);
    await expect(newest(page).getByTestId("web-searching")).toHaveCount(0);
  });
});
