import { test, expect } from "@playwright/test";
import { WRITTEN, ask, box, mock, newest } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 6. a late failure and a newer draft
test("finding 6: a late failure does not overwrite what the visitor has typed since", async ({ page }) => {
  await mock(page);
  let release: () => void = () => {};
  await page.route("**/api/chat", async (route) => {
    await new Promise<void>((r) => (release = r));
    return route.fulfill({ status: 500, json: { error: "internal", message: "made up" } });
  });
  await page.goto("/");
  await ask(page, "A made-up first question?");
  await expect(newest(page).getByTestId("searching-bar")).toBeVisible();
  await box(page).fill("A made-up second question?");
  release();
  await expect(newest(page).getByTestId("turn-error")).toBeVisible();
  await expect(box(page)).toHaveValue("A made-up second question?");
});

// ------------------------------------------------------------------ 15. focus after the first question
test("finding 15: after the first question, focus is in the conversation's question box", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await box(page).fill("A made-up question?");
  await box(page).press("Enter");
  await expect(newest(page)).toContainText(WRITTEN.sentences[0].text);
  await expect(page.locator("form.composer #q")).toBeFocused();
});
