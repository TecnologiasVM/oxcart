import { test, expect } from "@playwright/test";

/*
 * Smoke tests for the shell. The home route is now the SOCORICO landing; the
 * graph tools live under /research/*. These assert the chrome renders and the
 * core routes are reachable. They do NOT require a live backend — the UI must
 * render its chrome and degrade gracefully when :8090 is down.
 */

test("home renders the SOCORICO landing + primary nav", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.locator("h1").first()).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav).toBeVisible();
  // SOCORICO mono nav links present (scope to the nav — footer repeats these labels).
  await expect(nav.getByRole("link", { name: "Auctions" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Research" })).toBeVisible();
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
