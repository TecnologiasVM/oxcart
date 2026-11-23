import { test, expect } from "@playwright/test";
import { WRITTEN, ask, mock, newest, seed, startNew, failingStorage } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 8. storage that fails
test.describe("finding 8: a failed save or deletion is not taken as done", () => {
  test("a conversation whose save failed is saved once the store takes writes again", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await failingStorage(page, "full", true);
    await mock(page, { written: WRITTEN });
    await page.goto("/");
    await ask(page, "A made-up question that was not saved?");
    await expect(newest(page)).toContainText(WRITTEN.sentences[0].text);
    await expect(page.getByTestId("keep-note").first()).toBeVisible();
    await page.evaluate(() => {
      (window as unknown as { __failWrites: boolean }).__failWrites = false;
      window.sessionStorage.setItem("reloaded", "1");
    });
    await startNew(page);
    await page.reload();
    await expect(page.getByTestId("rail")).toContainText("A made-up question that was not saved?");
  });

  test("a deletion the store refused leaves the conversation where it is, and says the browser is not keeping", async ({ page }) => {
    await failingStorage(page, "refused", false);
    await seed(page, [{ question: "A made-up kept question?", written: WRITTEN }]);
    await mock(page);
    await page.goto("/");
    await expect(newest(page)).toContainText("A made-up kept question?");
    await page.evaluate(() => ((window as unknown as { __failWrites: boolean }).__failWrites = true));
    await page.getByTestId("delete-one").click();
    await page.getByTestId("confirm-one").getByRole("button", { name: /^(Delete|Borrar)$/ }).click();
    await expect(newest(page)).toContainText("A made-up kept question?");
    await expect(page.getByTestId("keep-note").first()).toBeVisible();
  });
});
