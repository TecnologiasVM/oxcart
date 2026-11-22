import { defineConfig, devices } from "@playwright/test";

/*
 * Playwright config for the First Issue KG frontend.
 * Starts `next dev` on :3000 and runs smoke tests against it.
 * The backend (:8090) is NOT started here — backend-dependent assertions are
 * written to tolerate a down backend (the UI must degrade gracefully).
 */
// OXCART_TEST_PORT: another port for the site under test, when 3000 is taken on the machine.
const port = Number(process.env.OXCART_TEST_PORT || 3000);
const site = `http://localhost:${port}`;

export default defineConfig({
  testDir: "./tests-e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: site,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // In CI the tests run against the site that was just built: the dev server fetches the
    // fonts from Google as it starts, and a slow answer there made it miss its start timeout.
    command: `npx next ${process.env.CI ? "start" : "dev"} -H 127.0.0.1 -p ${port}`,
    url: site,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
