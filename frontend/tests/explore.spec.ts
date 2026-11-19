import { test, expect, type Page } from "@playwright/test";

/**
 * Explore page (/explore):
 *   - wait for the cytoscape graph to mount + populate (window.__cy has nodes),
 *   - select a node,
 *   - expect the NodeDetailPanel to leave "No selection" and show its title,
 *   - ASSERT the body text exposes no "embedding"/"vector" (embeddings_visible_in_ui).
 *
 * Real selectors (app/explore/ExploreView.tsx + app/components/NodeDetailPanel.tsx):
 *   .graph-frame / .graph-canvas   the GraphView mount (cytoscape <canvas> inside)
 *   aside                          the NodeDetailPanel ("No selection" when empty)
 *   aside h3.serif-display         the selected node's title (after GET /api/node)
 *
 * Cytoscape draws to a single <canvas> and the cose layout can place nodes far
 * outside the viewport (verified: node 0 renders at y≈-2233), so pixel-clicking a
 * rendered position is unreliable. Instead we drive selection through cytoscape's
 * own event system: GraphView exposes the live Core on window.__cy, and
 * `node.emit("tap")` fires ExploreView's delegated `cy.on("tap","node",...)`
 * handler exactly as a user tap would — confirmed to populate the detail panel
 * (NodeDetailPanel then loads GET /api/node and shows the title).
 */

const FRAME = ".graph-frame";
const CANVAS = ".graph-canvas canvas";
const PANEL_TITLE = "aside h3.serif-display";

async function waitForGraphReady(page: Page): Promise<void> {
  await page.locator(FRAME).first().waitFor({ state: "visible", timeout: 30_000 });
  await expect(page.locator(CANVAS).first()).toBeAttached({ timeout: 30_000 });
  await page.waitForFunction(
    () => {
      const cy = (window as unknown as { __cy?: { nodes: () => { length: number } } }).__cy;
      return !!cy && cy.nodes().length > 0;
    },
    { timeout: 30_000 },
  );
}

/** Fire cytoscape's "tap" on the first node, driving ExploreView's handler. */
async function selectFirstNode(page: Page): Promise<string | null> {
  return page.evaluate(() => {
    const cy = (
      window as unknown as {
        __cy?: { nodes: () => { length: number; [k: number]: { id: () => string; emit: (e: string) => void } } };
      }
    ).__cy;
    if (!cy || cy.nodes().length === 0) return null;
    const n = cy.nodes()[0];
    n.emit("tap");
    return n.id();
  });
}

test.describe("Explore page (/explore)", () => {
  test("renders cytoscape canvas, select a node, shows NodeDetailPanel title", async ({
    page,
  }) => {
    await page.goto("/research/explore");
    await waitForGraphReady(page);

    // The detail panel exists in its empty state ("No selection") before any tap.
    await expect(page.getByText("No selection")).toBeVisible();

    const selectedId = await selectFirstNode(page);
    expect(selectedId).toBeTruthy();

    // After the tap, NodeDetailPanel loads GET /api/node and shows a serif title.
    const title = page.locator(PANEL_TITLE);
    await expect(title).toBeVisible({ timeout: 20_000 });
    expect(((await title.textContent()) ?? "").trim().length).toBeGreaterThan(0);
  });

  test("page body never exposes embedding/vector data", async ({ page }) => {
    await page.goto("/research/explore");
    await waitForGraphReady(page);

    // Populate the detail panel with real node properties, then scan the body.
    await selectFirstNode(page);
    await page
      .locator(PANEL_TITLE)
      .waitFor({ state: "visible", timeout: 20_000 })
      .catch(() => {
        /* even if selection is flaky, still scan what rendered */
      });

    const bodyText = ((await page.locator("body").innerText()) ?? "").toLowerCase();
    // embeddings_visible_in_ui MUST be false.
    expect(bodyText).not.toContain("embedding");
    expect(bodyText).not.toContain("vector");
  });
});
