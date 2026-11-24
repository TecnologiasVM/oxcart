import { test, expect, Page } from "@playwright/test";
import { WRITTEN, ask, mock, newest } from "./helpers";

/*
 * The page's own language, <html lang>: what a screen reader reads the page in. It follows the language button both
 * ways, on both pages, and the choice kept in this browser when a page opens. Every question is made up.
 */
const html = (page: Page) => page.locator("html");
/** The language stays what it was set to: checked again after a moment, as later renders could change it. */
async function holds(page: Page, lang: "en" | "es") {
  await expect(html(page)).toHaveAttribute("lang", lang);
  await page.waitForTimeout(400);
  await expect(html(page)).toHaveAttribute("lang", lang);
}

for (const path of ["/", "/how-it-works"]) {
  test(`${path}: the language button sets the page's language to Spanish and back to English`, async ({ page }) => {
    await mock(page, { written: WRITTEN });
    await page.goto(path);
    await holds(page, "en");
    await page.getByTestId("lang-toggle").click();
    await holds(page, "es");
    if (path === "/") {
      // a question asked in Spanish leaves the page in Spanish
      await ask(page, "¿Una pregunta inventada?");
      await expect(newest(page)).toContainText(WRITTEN.sentences[0].text);
      await holds(page, "es");
    } else {
      await page.getByTestId("versions").locator("summary").click();
      await holds(page, "es");
    }
    await page.getByTestId("lang-toggle").click();
    await holds(page, "en");
  });

  test(`${path}: a page opened with Spanish kept in this browser is in Spanish, and stays so after a reload`, async ({ page }) => {
    await mock(page);
    await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
    await page.goto(path);
    await holds(page, "es");
    await page.reload();
    await holds(page, "es");
  });
}

test("the language chosen on one page is the language of the other", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByTestId("lang-toggle").click();
  await holds(page, "es");
  await page.locator("header.masthead").getByRole("link", { name: "Cómo funciona" }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
  await holds(page, "es");
  await page.getByTestId("lang-toggle").click();
  await holds(page, "en");
  await page.goto("/");
  await holds(page, "en");
});
