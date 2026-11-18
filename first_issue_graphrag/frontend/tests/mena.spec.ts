import { test, expect } from "@playwright/test";

/**
 * Mena Catalogue page (/mena) — Surface Mail navigator.
 *
 * Real UI (app/mena/*):
 *   - 3-pane layout: YEAR pane (.mena-row buttons) -> ISSUE pane -> DETAIL.
 *   - Selecting a year lists its issues; selecting an issue loads facts + Scott
 *     match FAST. The graph and Weaviate evidence are LAZY (button-triggered):
 *     "View graph" mounts a .graph-frame; "Query evidence" renders .evi-card(s).
 *   - Fast-load contract: NO .graph-frame is mounted until "View graph" is clicked.
 *
 * Backend: GET /api/mena/surface-mail (year buckets), /issue/{id}, /issue/{id}/graph,
 * /issue/{id}/evidence. The First Issue (1863) is the safe demo target.
 */
test.describe("Mena Catalogue (/mena)", () => {
  test("renders the navigator and the catalogue title", async ({ page }) => {
    await page.goto("/research/mena");
    await expect(page.locator("h1")).toContainText(/catalogue/i);
    // Year pane populates once GET /api/mena/surface-mail resolves.
    await expect(page.locator(".mena-row").first()).toBeVisible({ timeout: 30_000 });
  });

  test("select a year then an issue shows facts + Scott + a stamp glyph", async ({ page }) => {
    await page.goto("/research/mena");

    // Pick the 1863 year row (First Issue lives here and has rich data).
    const yearRow = page.locator(".mena-row", { hasText: "1863" }).first();
    await yearRow.waitFor({ state: "visible", timeout: 30_000 });
    await yearRow.click();

    // Issue pane lists First Issue; select it.
    const issueRow = page.locator(".mena-row", { hasText: /first issue/i }).first();
    await issueRow.waitFor({ state: "visible", timeout: 15_000 });
    await issueRow.click();

    // Fast facts load: the detail title + the Scott match section appear.
    await expect(page.locator(".mena-detail h3")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Scott match")).toBeVisible({ timeout: 15_000 });
    // At least one encoded stamp glyph for an issue that has stamps.
    await expect(page.locator(".mena-detail .stamp").first()).toBeVisible({ timeout: 15_000 });

    // FAST-LOAD CONTRACT: no graph frame is mounted until "View graph" is clicked.
    await expect(page.locator(".graph-frame")).toHaveCount(0);

    // Lazy graph: click "View graph" -> a .graph-frame with an attached canvas.
    await page.getByRole("button", { name: /View graph/i }).click();
    await expect(page.locator(".graph-frame").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".graph-canvas canvas").first()).toBeAttached({ timeout: 30_000 });

    // Lazy evidence: click "Query evidence" -> evi-cards or an empty state.
    await page.getByRole("button", { name: /Query evidence/i }).click();
    const evi = page.locator(".evi-card");
    const empty = page.getByText(/No passages found/i);
    await expect(evi.first().or(empty)).toBeVisible({ timeout: 30_000 });
  });

  test("never exposes embedding/vector data", async ({ page }) => {
    await page.goto("/research/mena");
    const yearRow = page.locator(".mena-row", { hasText: "1863" }).first();
    await yearRow.waitFor({ state: "visible", timeout: 30_000 });
    await yearRow.click();
    const issueRow = page.locator(".mena-row", { hasText: /first issue/i }).first();
    await issueRow.waitFor({ state: "visible", timeout: 15_000 });
    await issueRow.click();
    await expect(page.locator(".mena-detail h3")).toBeVisible({ timeout: 15_000 });

    const bodyText = ((await page.locator("body").innerText()) ?? "").toLowerCase();
    expect(bodyText).not.toContain("embedding");
    expect(bodyText).not.toContain("vector");
    expect(bodyText).not.toContain("search_corpus");
  });
});
