import { test, expect } from "@playwright/test";

/*
 * Smoke tests for the shell. The site root is the question page (see chat.spec.ts);
 * the explorer of the First Issue graph lives under /research/*. These assert the
 * chrome renders and the core routes are reachable. They do NOT require a live
 * backend — the UI must render its chrome and degrade gracefully when :8090 is down.
 */

test("the research overview renders with the neutral header", async ({ page }) => {
  await page.goto("/research", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/research$/);
  await expect(page.locator("h1").first()).toBeVisible();
  await expect(page.getByTestId("research-link")).toBeVisible();
  await expect(page.locator("header.masthead")).toContainText("Oxcart");
  await expect(page.getByTestId("demo-tag")).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Research" });
  for (const label of ["Overview", "Explore", "Query", "Mena Catalogue"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
});

test("the removed society pages are gone", async ({ page }) => {
  for (const path of ["/auctions", "/membership", "/contact"]) {
    const response = await page.goto(path, { waitUntil: "domcontentloaded" });
    expect(response?.status(), path).toBe(404);
  }
});

test("research/explore route renders graph chrome", async ({ page }) => {
  await page.goto("/research/explore");
  await expect(page.locator("h1").first()).toContainText(/graph/i);
  // The graph control buttons render even before data loads.
  await expect(page.getByRole("button", { name: "Force" })).toBeVisible();
});

test("research/query route renders the question form", async ({ page }) => {
  await page.goto("/research/query");
  await expect(page.getByLabel("Question")).toBeVisible();
  await expect(page.getByRole("button", { name: /Retrieve/i })).toBeVisible();
});
