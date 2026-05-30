import { defineConfig, devices } from "@playwright/test";

/*
 * Playwright config for the First Issue KG frontend.
 * Starts `next dev` on :3000 and runs smoke tests against it.
 * The backend (:8090) is NOT started here — backend-dependent assertions are
 * written to tolerate a down backend (the UI must degrade gracefully).
 */
export default defineConfig({
  testDir: "./tests-e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
