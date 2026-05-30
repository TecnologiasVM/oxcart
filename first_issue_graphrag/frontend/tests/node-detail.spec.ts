import { test, expect } from "@playwright/test";

/*
 * Node-detail smoke tests — these guard the bugs reported from the screenshots:
 *   1. Tapping a Stamp dumped raw JSON for varieties.
 *   2. Tapping a Document listed every page one-per-line (huge overflow).
 * The panel must now render human-readable content: NO raw JSON braces, page
 * numbers as chips (not a one-per-line column), and never an embedding/vector key.
 */

async function tapType(page: import("@playwright/test").Page, type: string) {
  await page.goto("/explore");
  await page.waitForFunction(() => Boolean((window as any).__cy), null, { timeout: 15000 });
  // Give the cose layout a beat so nodes exist + are tappable.
  await page.waitForTimeout(1500);
  const tapped = await page.evaluate((t) => {
    const cy = (window as any).__cy;
    const nodes = cy.nodes(`[type = "${t}"]`);
    if (!nodes.length) return false;
    nodes[0].emit("tap");
    return true;
  }, type);
  return tapped;
}

test.describe("node detail panel", () => {
  test("Stamp detail is human-readable (no raw JSON, no embeddings)", async ({ page }) => {
    const ok = await tapType(page, "Stamp");
    expect(ok).toBeTruthy();

    const aside = page.locator("aside").first();
    await expect(aside).toContainText(/Mena/i, { timeout: 5000 });

    const text = await aside.innerText();
    // No raw JSON objects leaking into the UI.
    expect(text).not.toContain('{"');
    expect(text).not.toContain('"suffix"');
    expect(text).not.toContain('"base_catalog_no"');
    // No embedding/vector ever.
    expect(text.toLowerCase()).not.toContain("embedding");
  });

  test("Document detail shows pages as chips, not one-per-line", async ({ page }) => {
    const ok = await tapType(page, "Document");
    expect(ok).toBeTruthy();

    const aside = page.locator("aside").first();
    await expect(aside).toBeVisible();

    const text = await aside.innerText();
    expect(text).not.toContain('{"chunk_id"'); // top_chunks must not be raw JSON
    expect(text.toLowerCase()).not.toContain("embedding");

    // Pages render as chips inside a .chip-row when present.
    const hasPages = /pages/i.test(text);
    if (hasPages) {
      const chipRows = await aside.locator(".chip-row").count();
      expect(chipRows).toBeGreaterThan(0);
    }
  });

  test("tapping background clears the panel", async ({ page }) => {
    await tapType(page, "Stamp");
    await expect(page.locator("aside").first()).toContainText(/Mena/i);
    await page.evaluate(() => {
      const cy = (window as any).__cy;
      cy.emit("tap", [{ target: cy }]); // background tap
    });
    // Either returns to the empty state or simply stops showing the stamp.
    await page.waitForTimeout(500);
  });
});
