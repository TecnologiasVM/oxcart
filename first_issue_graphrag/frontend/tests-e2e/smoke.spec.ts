import { test, expect } from "@playwright/test";

/*
 * Smoke tests for the scaffold. These assert the shell renders and the three
 * routes are reachable. They deliberately do NOT require a live backend — the
 * UI must render its chrome and degrade gracefully when :8090 is down.
 */

test("home renders the lede and nav", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  // Mono nav links present.
  await expect(page.getByRole("link", { name: "Explore" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Query" })).toBeVisible();
});

test("explore route renders graph chrome", async ({ page }) => {
  await page.goto("/explore");
  await expect(page.locator("h1")).toContainText(/graph/i);
  // The graph control buttons render even before data loads.
  await expect(page.getByRole("button", { name: "Force" })).toBeVisible();
});

test("query route renders the question form", async ({ page }) => {
  await page.goto("/query");
  await expect(page.getByLabel("Question")).toBeVisible();
  await expect(page.getByRole("button", { name: /Retrieve/i })).toBeVisible();
});
