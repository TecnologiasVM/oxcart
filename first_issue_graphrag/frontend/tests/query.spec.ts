import { test, expect } from "@playwright/test";

/**
 * Query page (/query):
 *   - click the first example chip (auto-runs the query),
 *   - expect the Sources section + >= 1 lexical evidence item,
 *   - expect the retrieval subgraph canvas (backend returns result.subgraph).
 *
 * Real UI (app/query/QueryView.tsx):
 *   - example chips: <button class="btn"> with the question text (auto-run on click)
 *   - results region: "Sources" mono-label + a <ul> of source <li>,
 *     a "Lexical (graph)" column with <article class="surface"> per hit,
 *     and a GraphView subgraph (.graph-canvas canvas) when result.subgraph has nodes.
 *   No data-testids here, so selectors are role/text/class based.
 *
 * Example questions come from examples_runner.DEMO; the first ("1 peso covers",
 * scope 4) has graph-linked lexical evidence and a non-empty subgraph.
 */
const EXAMPLE_CHIP = "button.btn";
const CHIP_TEXT = /first issue|peso|varieties|reales|plate/i;

test.describe("Query page (/query)", () => {
  test("click first example, see Sources + >=1 lexical item + subgraph", async ({
    page,
  }) => {
    await page.goto("/research/query");

    // Example chips render once GET /api/examples resolves.
    const exampleChip = page.locator(EXAMPLE_CHIP, { hasText: CHIP_TEXT }).first();
    await exampleChip.waitFor({ state: "visible", timeout: 30_000 });
    await exampleChip.click();

    // Sources section appears once the backend responds.
    await expect(page.locator("summary", { hasText: /^\s*Sources/ })).toBeVisible({
      timeout: 30_000,
    });

    // The sources list is a collapsed accordion: open it, then expect a document row.
    await page.locator("summary", { hasText: /^\s*Sources/ }).click();
    const sourceItems = page.locator("ul li", { hasText: /chunks|best|pp/i });
    await expect(sourceItems.first()).toBeVisible({ timeout: 15_000 });

    // At least one lexical evidence article ("Lexical (graph)" column).
    await expect(page.getByText("Lexical (graph)")).toBeVisible();
    const lexicalArticles = page.locator("article.surface");
    await expect(lexicalArticles.first()).toBeVisible({ timeout: 15_000 });
    expect(await lexicalArticles.count()).toBeGreaterThanOrEqual(1);

    // The retrieval subgraph renders (QueryView mounts a GraphView when
    // result.subgraph has nodes). Cytoscape's <canvas> reports as hidden to
    // Playwright, so assert the "Retrieval subgraph" section heading + the
    // GraphView frame + an attached <canvas>, rather than canvas "visibility".
    // exact:true — the intro paragraph also contains the words "retrieval subgraph".
    await expect(page.getByText("Retrieval subgraph", { exact: true })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.locator(".graph-frame").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".graph-canvas canvas").first()).toBeAttached({
      timeout: 30_000,
    });
  });

  test("manual question submission returns results", async ({ page }) => {
    await page.goto("/research/query");

    await page.locator("#q").fill("What are the main varieties of the first issue?");
    await page.getByRole("button", { name: /Retrieve/i }).click();

    await expect(page.locator("summary", { hasText: /^\s*Sources/ })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("query results never expose embedding/vector data", async ({ page }) => {
    await page.goto("/research/query");
    const exampleChip = page.locator(EXAMPLE_CHIP, { hasText: CHIP_TEXT }).first();
    await exampleChip.waitFor({ state: "visible", timeout: 30_000 });
    await exampleChip.click();
    await expect(page.locator("summary", { hasText: /^\s*Sources/ })).toBeVisible({
      timeout: 30_000,
    });

    const bodyText = ((await page.locator("body").innerText()) ?? "").toLowerCase();
    expect(bodyText).not.toContain("embedding");
    expect(bodyText).not.toContain("vector");
  });
});
