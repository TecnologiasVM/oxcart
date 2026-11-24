import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { inlineScriptHashes } from "../scripts/headers.mjs";
import { mock } from "./helpers";

/*
 * What the site says of itself to machines: a canonical address per page, sitemap.xml, robots.txt with the owner's
 * content signals, the schema.org description (JSON-LD), and llms.txt. The backend is mocked; nothing leaves the
 * test server.
 */
const PAGES = [
  // Next writes the root as the origin with no slash: the same address as "https://oxcart.chat/" (an empty path is "/")
  { path: "/", canonical: "https://oxcart.chat" },
  { path: "/how-it-works", canonical: "https://oxcart.chat/how-it-works" },
];

for (const { path, canonical } of PAGES) {
  test(`${path}: one canonical address, absolute`, async ({ page }) => {
    await mock(page);
    await page.goto(path);
    const link = page.locator('head link[rel="canonical"]');
    await expect(link).toHaveCount(1);
    await expect(link).toHaveAttribute("href", canonical);
  });

  test(`${path}: the schema.org description is one data block that parses, and the policy gives it no hash`, async ({ page, request }) => {
    await mock(page);
    await page.goto(path);
    const blocks = page.locator('script[type="application/ld+json"]');
    await expect(blocks).toHaveCount(1);
    const text = (await blocks.textContent())!;
    const data = JSON.parse(text);
    expect(data).toMatchObject({
      "@context": "https://schema.org",
      "@type": "WebApplication",
      name: "Oxcart",
      url: "https://oxcart.chat/",
      inLanguage: ["en", "es"],
      isAccessibleForFree: true,
      applicationCategory: "ReferenceApplication",
      isBasedOn: { "@type": "SoftwareSourceCode", codeRepository: "https://github.com/TecnologiasVM/oxcart" },
    });
    expect(typeof data.description).toBe("string");
    // the page as served holds the block, and the hashes the site's policy is made from do not include it
    const html = await (await request.get(path)).text();
    expect(html).toContain('<script type="application/ld+json">');
    const own = `'sha256-${createHash("sha256").update(text, "utf8").digest("base64")}'`;
    expect(inlineScriptHashes(html)).not.toContain(own);
    expect(inlineScriptHashes(`<script type="application/ld+json">${text}</script>`)).toEqual([]);
  });
}

test("sitemap.xml names the two pages by their absolute addresses", async ({ request }) => {
  const res = await request.get("/sitemap.xml");
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toMatch(/xml/);
  const xml = await res.text();
  expect(xml).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">');
  expect([...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1])).toEqual(["https://oxcart.chat/", "https://oxcart.chat/how-it-works"]);
});

test("robots.txt allows all, gives the content signals under the wildcard group, and names the sitemap", async ({ request }) => {
  const res = await request.get("/robots.txt");
  expect(res.status()).toBe(200);
  const rules = (await res.text()).split("\n").filter((l) => l.trim() && !l.startsWith("#"));
  expect(rules).toEqual([
    "User-agent: *",
    "Content-Signal: search=yes, ai-input=yes, ai-train=no",
    "Allow: /",
    "Sitemap: https://oxcart.chat/sitemap.xml",
  ]);
});

test("llms.txt: a title, a summary, and links to how it works, the evaluation and the repository, and no other host", async ({ request }) => {
  const res = await request.get("/llms.txt");
  expect(res.status()).toBe(200);
  const text = await res.text();
  const lines = text.split("\n");
  expect(lines[0]).toBe("# Oxcart");
  expect(lines.find((l) => l.trim()) === "# Oxcart" && lines.some((l) => l.startsWith("> "))).toBe(true);
  expect(text).toMatch(/^## /m);
  const links = [...text.matchAll(/^- \[[^\]]+\]\((https:\/\/[^)]+)\)/gm)].map((m) => m[1]);
  expect(links).toEqual([
    "https://oxcart.chat/how-it-works",
    "https://github.com/TecnologiasVM/oxcart/blob/main/EVALUATION.md",
    "https://github.com/TecnologiasVM/oxcart",
  ]);
  const hosts = new Set([...text.matchAll(/https?:\/\/([^/)\s]+)/g)].map((m) => m[1]));
  expect([...hosts].sort()).toEqual(["github.com", "oxcart.chat"]);
  expect(text).not.toMatch(/figures|invalid|key/i);
});
