import { test, expect } from "@playwright/test";
import { WRITTEN, ask, mock, newest, heldStream } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 7. two tabs, one answer still being written
test("finding 7: a tab that read a turn before its answer came does not erase the answer", async ({ context }) => {
  const a = await context.newPage();
  await heldStream(a, WRITTEN);
  await mock(a);
  await a.goto("/");
  await ask(a, "A made-up question?");
  await expect(newest(a).getByTestId("writing")).toBeVisible();
  // the second tab opens on the stored turn, which has its evidence and no answer yet
  const b = await context.newPage();
  await mock(b);
  await b.goto("/");
  await expect(newest(b).getByTestId("evidence-button")).toBeVisible();
  await a.evaluate(() => (window as unknown as { __release: () => void }).__release());
  await expect(newest(a)).toContainText(WRITTEN.sentences[0].text);
  await expect(newest(b)).toContainText(WRITTEN.sentences[0].text);
});
