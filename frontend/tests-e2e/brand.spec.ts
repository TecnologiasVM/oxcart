import { test, expect, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { mock } from "./helpers";

/*
 * The site's icon (app/icon.svg) and the picture a link to the site shows (public/oxcart-card-c-stamp.png, named by
 * app/link-picture.ts). The backend is mocked; nothing leaves the test server.
 */
const FRONTEND = join(__dirname, "..");
const REPO = join(FRONTEND, "..");
const CARD = "https://oxcart.chat/oxcart-card-c-stamp.png";
const PAGES = [
  { path: "/", description: "Research demo: ask about any Costa Rican stamp issue and read a short answer with its sources, written from the evidence of the catalogue graph and the philatelic literature." },
  { path: "/how-it-works", description: "How Oxcart answers a question about Costa Rican stamps from a catalogue graph and the philatelic literature, and how its answers were measured." },
];

const meta = (page: Page, attr: "property" | "name", key: string) => page.locator(`head meta[${attr}="${key}"]`);

for (const { path, description } of PAGES) {
  test(`${path}: the link picture's tags, with absolute https addresses, and the icon's link`, async ({ page }) => {
    await mock(page);
    await page.goto(path);
    await expect(meta(page, "property", "og:image")).toHaveAttribute("content", CARD);
    await expect(meta(page, "property", "og:image:width")).toHaveAttribute("content", "1280");
    await expect(meta(page, "property", "og:image:height")).toHaveAttribute("content", "640");
    await expect(meta(page, "property", "og:image:type")).toHaveAttribute("content", "image/png");
    await expect(meta(page, "property", "og:image:alt")).toHaveAttribute("content", description);
    await expect(meta(page, "property", "og:url")).toHaveAttribute("content", `https://oxcart.chat${path === "/" ? "" : path}`);
    await expect(meta(page, "name", "twitter:card")).toHaveAttribute("content", "summary_large_image");
    await expect(meta(page, "name", "twitter:image")).toHaveAttribute("content", CARD);
    await expect(meta(page, "name", "twitter:image:alt")).toHaveAttribute("content", description);
    // every address in these tags is absolute and https
    for (const content of await page.locator('head meta[property^="og:"], head meta[name^="twitter:"]').evaluateAll((els) =>
      els.map((e) => e.getAttribute("content") ?? "").filter((c) => /^(\/|https?:)/.test(c)))) {
      expect(content).toMatch(/^https:\/\/oxcart\.chat(\/|$)/);
    }
    const icon = page.locator('head link[rel="icon"][type="image/svg+xml"]');
    await expect(icon).toHaveCount(1);
    await expect(icon).toHaveAttribute("href", /^\/icon\.svg(\?|$)/);
    // the same icon as a PNG, for what takes no SVG icon (app/apple-icon.png)
    const apple = page.locator('head link[rel="apple-touch-icon"]');
    await expect(apple).toHaveCount(1);
    await expect(apple).toHaveAttribute("href", /^\/apple-icon\.png(\?|$)/);
    await expect(apple).toHaveAttribute("sizes", "180x180");
    await expect(apple).toHaveAttribute("type", "image/png");
  });
}

test("the picture's address answers 200 with a PNG of 1280 by 640", async ({ request }) => {
  const res = await request.get("/oxcart-card-c-stamp.png");
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toBe("image/png");
  const body = await res.body();
  expect(body.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a"); // the PNG signature
  expect([body.readUInt32BE(16), body.readUInt32BE(20)]).toEqual([1280, 640]); // IHDR: width, height
  expect(body.equals(readFileSync(join(FRONTEND, "public", "oxcart-card-c-stamp.png")))).toBe(true);
});

test("the page's copy of the picture and the one in docs/brand are the same bytes", () => {
  const page = readFileSync(join(FRONTEND, "public", "oxcart-card-c-stamp.png"));
  const brand = readFileSync(join(REPO, "docs", "brand", "oxcart-card-c-stamp.png"));
  expect(page.equals(brand)).toBe(true);
});

test("the icon is shapes only, on the page's paper: no text, script, metadata or outside reference; served as SVG", async ({ request }) => {
  const svg = readFileSync(join(FRONTEND, "app", "icon.svg"), "utf-8");
  expect(svg).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" viewBox="-48 -48 96 96">/);
  for (const banned of [/<text/i, /<script/i, /<title/i, /<desc/i, /<metadata/i, /<style/i, /<image/i, /<use/i, /<foreignObject/i, /\bhref\s*=/i, /url\(/i, /font/i, /\bon[a-z]+\s*=/i]) {
    expect(svg, String(banned)).not.toMatch(banned);
  }
  // the one address in it is the SVG namespace
  expect(svg.match(/https?:\/\/[^"\s]+/g)).toEqual(["http://www.w3.org/2000/svg"]);
  // two rings, eight blades and the amber hub, as in the mark it is taken from
  expect(svg.match(/<circle/g)).toHaveLength(3);
  expect(svg.match(/<path/g)).toHaveLength(8);
  expect(svg).toContain('fill="#c4923a"');
  // a rounded square of the page's paper (--color-paper) behind the wheel, the whole viewBox
  expect(svg).toContain('<rect x="-48" y="-48" width="96" height="96" rx="20" fill="#f4efe5"/>');
  expect(readFileSync(join(FRONTEND, "app", "globals.css"), "utf-8")).toContain("--color-paper: #f4efe5;");
  const res = await request.get("/icon.svg");
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toMatch(/^image\/svg\+xml/);
});

test("the apple icon is a PNG of 180 by 180 with no text chunk, only what a PNG needs; served as PNG", async ({ request }) => {
  const png = readFileSync(join(FRONTEND, "app", "apple-icon.png"));
  expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([180, 180]);
  const chunks: string[] = [];
  for (let i = 8; i < png.length; i += 12 + png.readUInt32BE(i)) chunks.push(png.toString("latin1", i + 4, i + 8));
  expect(chunks[0]).toBe("IHDR");
  expect(chunks[chunks.length - 1]).toBe("IEND");
  for (const c of chunks) expect(["IHDR", "IDAT", "IEND", "sRGB", "gAMA", "pHYs"], c).toContain(c);
  expect(chunks.filter((c) => /^(tEXt|zTXt|iTXt)$/.test(c))).toEqual([]);
  const res = await request.get("/apple-icon.png");
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toBe("image/png");
  expect((await res.body()).equals(png)).toBe(true);
});
