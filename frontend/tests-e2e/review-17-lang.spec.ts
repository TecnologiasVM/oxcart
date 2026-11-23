import { test, expect } from "@playwright/test";
import { STORED, mock, newest } from "./helpers";

/*
 * A finding of an independent review of the question page, as the failure it describes, with the specs' made-up
 * fixtures and mocked backend. The test is named after the finding's number in the review. No live backend, no window.
 */
// ------------------------------------------------------------------ 17. language marks
test("finding 17: in the Spanish interface, the English header line, footer and an English example keep lang=en", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
  await mock(page, { stored: STORED });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.locator(".brand__sub")).toHaveAttribute("lang", "en");
  await expect(page.locator("footer.site-foot .site-foot__bar > span").first()).toHaveAttribute("lang", "en");
  await page.getByRole("button", { name: "A stored example question?" }).click();
  await expect(newest(page).locator(".turn__text")).toHaveAttribute("lang", "en");
});
