import { test, expect } from "@playwright/test";

/*
 * Navigation smoke + the query export feature.
 * Nav: every primary route is reachable from the top nav and renders its hero.
 * Export: running a query exposes a .txt download whose contents are an
 * LLM-ready, citation-first prompt (no JSON, includes the question + evidence).
 */

test.describe("navigation", () => {
  test("primary nav reaches all three routes", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toBeVisible();

    await page.getByRole("link", { name: /explore/i }).first().click();
    await expect(page).toHaveURL(/\/explore$/);
    await expect(page.locator("h1, h2").first()).toBeVisible();

    await page.getByRole("link", { name: /query/i }).first().click();
    await expect(page).toHaveURL(/\/query$/);
    await expect(page.locator("h1, h2").first()).toBeVisible();

    await page.getByRole("link", { name: /first issue/i }).first().click();
    await expect(page).toHaveURL(/\/$/);
  });

  test("home clarifies the Scott catalogue count", async ({ page }) => {
    await page.goto("/");
    // The Scott-count clarification (1b is a variety) must be present.
    await expect(page.getByText(/Scott catalogues 5 stamps|Scott 1, 1a, 2, 3, 4/i)).toBeVisible({
      timeout: 15000,
    });
  });
});

test.describe("query export", () => {
  test("exports an LLM-ready .txt prompt after a query", async ({ page }) => {
    await page.goto("/query");
    await page.locator("button", { hasText: /varieties/i }).first().click();
    await expect(page.getByText("Sources", { exact: true })).toBeVisible({ timeout: 20000 });

    const exportBtn = page.getByRole("button", { name: /export/i });
    await expect(exportBtn).toBeVisible();

    const [download] = await Promise.all([page.waitForEvent("download"), exportBtn.click()]);
    expect(download.suggestedFilename()).toMatch(/\.txt$/);

    const stream = await download.createReadStream();
    let content = "";
    if (stream) {
      for await (const chunk of stream) content += chunk.toString();
    }
    // The exported prompt must be LLM-ready and human-readable.
    expect(content).toContain("QUESTION");
    expect(content.toLowerCase()).toContain("varieties");
    expect(content).toMatch(/DOMAIN FACTS|EVIDENCE PASSAGES/);
    expect(content).not.toContain('{"'); // no raw JSON
    expect(content.toLowerCase()).not.toContain("embedding");
  });
});
