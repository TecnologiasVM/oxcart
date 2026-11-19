import { defineConfig, devices } from "@playwright/test";

/**
 * "Shadow" (headless) Playwright config for the First Issue KG frontend.
 *
 * Separate from playwright.config.ts (the pre-existing dev-server smoke config)
 * so the two suites don't collide. This one:
 *   - drives the production build (`npm run build && npm run start`) on :3000,
 *   - runs headless Chromium at three viewports (375 / 768 / 1440),
 *   - captures a screenshot on every test; trace on first retry,
 *   - writes artifacts to test-results/ and named full-page shots to tests/__screenshots__/.
 *
 * Servers (backend :8090 + frontend :3000) are started OUT OF BAND by the runner,
 * so there is deliberately no `webServer` block here — uvicorn keeps ownership of
 * the prototype's synchronous Neo4j/Weaviate handles.
 *
 * Run:
 *   npx playwright test --config=playwright.shadow.config.ts
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["html", { open: "never", outputFolder: "playwright-report-shadow" }], ["list"]],
  outputDir: "test-results",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.FRONTEND_BASE_URL ?? "http://localhost:3000",
    headless: true,
    screenshot: "on",
    trace: "on-first-retry",
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium-375",
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 812 } },
    },
    {
      name: "chromium-768",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "chromium-1440",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
