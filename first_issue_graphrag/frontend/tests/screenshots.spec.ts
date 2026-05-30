import { test } from "@playwright/test";
import path from "path";

/**
 * Full-page screenshots of /, /explore, /query at the 1440 and 375 viewports.
 * Output: tests/__screenshots__/<route>-<width>.png. The 768 project runs the
 * functional specs but skips these shots (only the two requested widths).
 */
const SHOT_DIR = path.join(__dirname, "__screenshots__");

const ROUTES: { name: string; path: string; waitFor?: string }[] = [
  { name: "home", path: "/", waitFor: "h1" },
  { name: "explore", path: "/explore", waitFor: ".graph-frame" },
  { name: "query", path: "/query", waitFor: "button.btn" },
];

test.describe("Full-page screenshots", () => {
  for (const route of ROUTES) {
    test(`capture ${route.name}`, async ({ page }, testInfo) => {
      const width = testInfo.project.use.viewport?.width ?? 0;
      test.skip(width !== 1440 && width !== 375, "screenshots only at 1440 and 375");

      await page.goto(route.path);
      if (route.waitFor) {
        await page
          .locator(route.waitFor)
          .first()
          .waitFor({ state: "visible", timeout: 30_000 })
          .catch(() => {
            /* still capture even if a backend-dependent element is slow */
          });
      }

      // On /query, run the first example so the evidence panels show in the shot.
      if (route.name === "query") {
        const chip = page
          .locator("button.btn", { hasText: /first issue|peso|varieties|reales|plate/i })
          .first();
        if (await chip.isVisible().catch(() => false)) {
          await chip.click().catch(() => {});
          await page
            .getByText("Sources", { exact: true })
            .waitFor({ state: "visible", timeout: 30_000 })
            .catch(() => {});
        }
      }

      // For graph routes, wait until cytoscape has actually rendered nodes so the
      // captured PNG shows the populated graph (not an empty canvas mid-layout).
      if (route.name === "explore" || route.name === "query") {
        await page
          .waitForFunction(
            () => {
              const cy = (window as unknown as { __cy?: { nodes: () => { length: number } } }).__cy;
              return !!cy && cy.nodes().length > 0;
            },
            { timeout: 30_000 },
          )
          .catch(() => {
            /* still capture even if the graph is slow */
          });
      }

      await page.waitForTimeout(1200); // let cose layout settle + first paint
      await page.screenshot({
        path: path.join(SHOT_DIR, `${route.name}-${width}.png`),
        fullPage: true,
      });
    });
  }
});
