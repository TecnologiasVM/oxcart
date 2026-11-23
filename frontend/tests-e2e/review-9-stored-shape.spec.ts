import { test, expect } from "@playwright/test";
import { ANSWER, WRITTEN, mock } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 9. a malformed stored conversation
test("finding 9: a malformed stored turn is dropped, and the page and the other conversations load", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const at = "2026-11-20T10:00:00.000Z";
  await page.addInitScript((store) => window.localStorage.setItem("oxcart-conversations", store), JSON.stringify({
    version: 2,
    current: "c-bad",
    conversations: [
      { id: "c-bad", started: at, turns: [{ id: "t-bad", question: "A made-up broken question?", at, answer: {} }] },
      { id: "c-good", started: at, turns: [{ id: "t-good", question: "A made-up good question?", at, answer: ANSWER, written: WRITTEN }] },
    ],
  }));
  await mock(page);
  await page.goto("/");
  await expect(page.getByTestId("rail")).toContainText("A made-up good question?");
  await expect(page.getByLabel("Your question")).toBeVisible();
  expect(errors).toEqual([]);
});
