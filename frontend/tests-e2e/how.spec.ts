import { test, expect, Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { FIGURES } from "../lib/how-figures";
import { HOW, modelName } from "../lib/how-i18n";
import { webOn } from "../lib/web";
import { mock, noOverflow } from "./helpers";

/*
 * "How it works" (app/how-it-works). No backend: every request to /api is refused and counted, and the
 * page must make none. Its figures are the build's (lib/how-figures.json); the tests read the same file,
 * so they hold whichever run it was generated from. No window: Chromium runs headless.
 *
 * Which build: as web.spec.ts. Built with NEXT_PUBLIC_WEB on (CI, playwright.config.ts) the web step is on
 * the page; built and run with NEXT_PUBLIC_WEB empty, it is not, and Tavily is never named.
 */
const WEB_BUILD = webOn(process.env.NEXT_PUBLIC_WEB ?? "1");
const URL = "/how-it-works";
const EVAL = "https://github.com/TecnologiasVM/oxcart/blob/main/EVALUATION.md";
const REPO = "https://github.com/TecnologiasVM/oxcart";
const H1 = { en: "How it works, and how it was measured", es: "Cómo funciona y cómo se midió" };

/** Every request the page makes to the backend, refused. */
async function noBackend(page: Page) {
  const asked: string[] = [];
  await page.route("**/api/**", (route) => {
    asked.push(route.request().url());
    return route.abort();
  });
  return asked;
}

async function open(page: Page, lang: "en" | "es" = "en") {
  const asked = await noBackend(page);
  if (lang === "es") await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
  await page.goto(URL);
  await expect(page.locator("h1")).toHaveText(H1[lang]);
  return asked;
}

test("the page reads in English and in Spanish by its own language button, and calls nothing", async ({ page }) => {
  const asked = await open(page);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByTestId("how")).toContainText("Why a graph and vectors together");
  await page.getByTestId("lang-toggle").click();
  await expect(page.locator("h1")).toHaveText(H1.es);
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByTestId("how")).toContainText("Por qué un grafo y vectores a la vez");
  // the header names the page it is on, and the language is kept as the question page keeps it
  await expect(page.locator("header.masthead").getByRole("link", { name: "Cómo funciona" })).toHaveAttribute("aria-current", "page");
  expect(await page.evaluate(() => window.localStorage.getItem("oxcart-lang"))).toBe("es");
  await page.reload();
  await expect(page.locator("h1")).toHaveText(H1.es);
  // the question page opens in the language chosen here
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mock(page);
  await page.goto("/");
  await expect(page.getByLabel("Su pregunta")).toBeVisible();
  expect(asked).toEqual([]);
});

test("one h1, and no heading level is skipped, in both languages", async ({ page }) => {
  for (const lang of ["en", "es"] as const) {
    await open(page, lang);
    const levels = await page.locator("main").evaluate((main) =>
      [...main.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((h) => Number(h.tagName[1])));
    expect(levels.filter((l) => l === 1), lang).toHaveLength(1);
    expect(levels[0], lang).toBe(1);
    for (let i = 1; i < levels.length; i++) expect(levels[i] - levels[i - 1], `${lang}: heading ${i}`).toBeLessThanOrEqual(1);
  }
});

test("no horizontal overflow at 360, 820, 1100, 1280, 1440 and 1600 px, in both languages", async ({ page }) => {
  for (const lang of ["en", "es"] as const) {
    await open(page, lang);
    for (const width of [360, 820, 1100, 1280, 1440, 1600]) {
      await page.setViewportSize({ width, height: 900 });
      await page.getByTestId("versions").evaluate((d: HTMLDetailsElement) => { d.open = true; });
      await noOverflow(page, `${lang} at ${width} px`);
      // the diagram is drawn at its own width, 320 px
      expect(Math.round((await page.getByTestId("pipeline").boundingBox())!.width), `${lang} at ${width} px`).toBe(320);
    }
  }
});

test("every text of the diagram stands inside its box, in both languages", async ({ page }) => {
  for (const lang of ["en", "es"] as const) {
    await open(page, lang);
    await page.evaluate(() => document.fonts.ready);
    const outside = await page.getByTestId("pipeline").evaluate((svg) => {
      const out: string[] = [];
      for (const g of svg.querySelectorAll("g[data-node]")) {
        const box = g.querySelector("rect")!.getBoundingClientRect();
        for (const text of g.querySelectorAll("text")) {
          const r = text.getBoundingClientRect();
          if (r.left < box.left + 2 || r.right > box.right - 2 || r.top < box.top || r.bottom > box.bottom) out.push(`${g.getAttribute("data-node")}: ${text.textContent}`);
        }
      }
      return out;
    });
    expect(outside, lang).toEqual([]);
  }
});

test("the diagram says what the list says, and has a text alternative", async ({ page }) => {
  await open(page);
  const svg = page.getByTestId("pipeline");
  await expect(svg).toHaveAttribute("role", "img");
  await expect(svg.locator("title")).toHaveText("Diagram: the path of a question, from the question to the answer shown.");
  const steps = page.getByTestId("steps").locator("li");
  const numbered = svg.locator(".p-numtext");
  await expect(steps).toHaveCount(WEB_BUILD ? 5 : 4);
  await expect(numbered).toHaveCount(WEB_BUILD ? 5 : 4);
  for (let i = 0; i < (WEB_BUILD ? 5 : 4); i++) {
    const name = await svg.locator(`g[data-node="s${i + 1}"] .p-name`).textContent();
    await expect(steps.nth(i).locator("h3"), `step ${i + 1}`).toContainText(name!);
  }
  // step 1 runs for every question: query rewriting, in the box and in the list, and its box is not dashed
  await expect(svg.locator('g[data-node="s1"]')).not.toHaveClass(/p-node--some/);
  await expect(svg.locator('g[data-node="s1"] .p-name')).toHaveText("Query rewriting");
  await expect(steps.first()).toContainText("For every question, one call to");
  await expect(steps.first()).toContainText("the question is given in the other of the two languages, Spanish and English");
  await expect(steps.first()).toContainText("If the call fails or is late, the question is searched as it was typed.");
  await expect(page.locator(".pipe__fig figcaption")).not.toContainText("step 1");
  await expect(page.getByTestId("how")).not.toContainText("after the first");
  await expect(page.getByTestId("how")).not.toContainText("one vector");
  // step 2 in the usual terms: multi-query retrieval and reciprocal rank fusion, and the lead says them too
  await expect(steps.nth(1)).toContainText("Both texts are embedded in one request");
  await expect(steps.nth(1)).toContainText("searched once with each text (multi-query retrieval)");
  await expect(steps.nth(1)).toContainText("reciprocal rank fusion (RRF)");
  await expect(steps.nth(1)).toContainText("A passage is shown in its own language; nothing is translated.");
  await expect(page.locator(".how__lead")).toContainText("query rewriting");
  await expect(page.locator(".how__lead")).toContainText("multi-query retrieval");
  await expect(page.locator(".how__lead")).toContainText("reciprocal rank fusion (RRF)");
  // the figure of the two runs: questions with passages in both languages, before and after, from the generated file
  const both = FIGURES.languages;
  await expect(steps.nth(1)).toContainText(`Searched with the question alone, ${both.before!.both} of ${both.after!.of} catalogue and literature questions of the test set got passages in both languages among those shown; searched with both texts, ${both.after!.both}.`);
  // step 2 names the indexes as the stores report them: HNSW for the catalogue, HFresh with RQ for the literature
  const st = FIGURES.stores;
  await expect(steps.nth(1)).toContainText(`two ${st.graph.index.type} vector indexes by ${st.graph.index.similarity}`);
  await expect(steps.nth(1)).toContainText("full-text index");
  await expect(steps.nth(1)).toContainText(`from an ${st.literature.index.type} vector index with ${st.literature.index.compression} compression`);
  // the catalogue's box and the lead carry the graph's counts
  await expect(svg.locator('g[data-node="cat"]')).toContainText(`${st.graph.issues} issues`);
  await expect(page.locator(".how__lead")).toContainText(`Neo4j (${st.graph.issues} issues, ${new Intl.NumberFormat("en").format(st.graph.stamps)} stamps)`);
});

test("the fold \"Versions and tests\" is closed, and opens and closes by keyboard with a visible ring", async ({ page }) => {
  await open(page);
  const fold = page.getByTestId("versions");
  await expect(fold).not.toHaveAttribute("open");
  await expect(fold.locator("dl")).toBeHidden();
  // reached by Tab from the link before it
  await page.getByRole("link", { name: "Ask about Costa Rican stamps" }).focus();
  await page.keyboard.press("Tab");
  const summary = fold.locator("summary");
  await expect(summary).toBeFocused();
  expect(await summary.evaluate((el) => getComputedStyle(el).outlineStyle)).toBe("solid");
  await page.keyboard.press("Enter");
  await expect(fold).toHaveAttribute("open");
  await expect(fold.locator("dl")).toBeVisible();
  const v = FIGURES.versions;
  await expect(fold).toContainText(`LangGraph ${v.langgraph}`);
  await expect(fold).toContainText(`Neo4j ${FIGURES.stores.graph.neo4j}, on Aura Free`);
  await expect(fold).toContainText(`Weaviate ${FIGURES.stores.literature.weaviate}, on Weaviate Cloud`);
  await expect(fold).toContainText(`Next.js ${v.next}, React ${v.react}, TypeScript ${v.typescript}`);
  await expect(fold).toContainText(`pytest ${v.pytest} and Playwright ${v.playwright}, run by GitHub Actions on every pull request`);
  await page.keyboard.press("Space");
  await expect(fold).not.toHaveAttribute("open");
});

test("the Spanish page writes its numbers as es-CR does; the English page as English", async ({ page }) => {
  const es = new Intl.NumberFormat("es-CR");
  const usd = (x: number) => new Intl.NumberFormat("es-CR", { minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(x);
  const passages = es.format(FIGURES.stores.literature.objects);
  expect(passages).toMatch(/^\d{2} \d{3}$/); // 41 126, a space that does not break
  await open(page, "es");
  const how = page.getByTestId("how");
  await expect(page.locator(".how__lead")).toContainText(`${passages} pasajes`);
  await expect(page.getByTestId("pipeline")).toContainText(`${passages} pasajes`);
  if (FIGURES.run.cost) {
    expect(usd(FIGURES.run.cost.mean)).toMatch(/^0,\d{4}$/);
    await expect(page.getByTestId("costs")).toContainText(usd(FIGURES.run.cost.mean));
  }
  await expect(how).toContainText(`${es.format(FIGURES.issue_found.first)} de ${es.format(FIGURES.issue_found.of)}`);
  // a score of the trace, two decimals with a comma; the data's titles as stored
  const score = new Intl.NumberFormat("es-CR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(FIGURES.trace.issues[0].score);
  await expect(page.getByTestId("trace").locator("td.r").first()).toHaveText(score);
  await expect(page.getByTestId("trace").locator("tbody th").first()).toContainText(FIGURES.trace.issues[0].title);
  await expect(page.getByTestId("trace").locator("tbody th span").first()).toHaveAttribute("lang", "en");
  await page.getByTestId("lang-toggle").click();
  await expect(page.locator(".how__lead")).toContainText(`${new Intl.NumberFormat("en").format(FIGURES.stores.literature.objects)} passages`);
});

test("the figures are the generated file's: the results, the sealed set first among the limits, the judges", async ({ page }) => {
  await open(page);
  const run = FIGURES.run;
  const results = page.getByTestId("results");
  await expect(results.locator('[data-result="catalogue"] .ledger__n')).toHaveText(`${run.catalogue.correct} of ${run.catalogue.of}`);
  await expect(results.locator('[data-result="literature"] .ledger__n')).toHaveText(`${run.literature.in_full} of ${run.literature.of}`);
  if (run.literature.asks != null) await expect(results.locator('[data-result="literature"]')).toContainText(`${run.literature.asks} of ${run.literature.of} give what the question asks`);
  else await expect(results).not.toContainText("give what the question asks");
  await expect(results.locator('[data-result="page"]')).toHaveCount(run.page_found ? 1 : 0);
  await expect(page.getByTestId("costs").locator("li")).toHaveCount((run.cost ? 1 : 0) + (run.waits ? 2 : 0));
  const [a, b] = FIGURES.sealed.runs;
  const limits = page.getByTestId("limits");
  await expect(limits).toContainText(new RegExp(`^Limits: on ${FIGURES.sealed.questions} questions never used while the system was changed`));
  await expect(limits).toContainText(`${a.literature.asks} and ${b.literature.asks} of ${a.literature.of} gave what was asked`);
  await expect(limits).toContainText(`${a.catalogue.correct} and ${b.catalogue.correct} of ${a.catalogue.of} catalogue answers were correct`);
  await expect(limits).toContainText("The grades are a model's and no person has checked them");
  await expect(page.getByTestId("how")).not.toContainText("has not been run");
  await expect(page.getByTestId("how")).not.toContainText(/placeholder|Mock note/i);
  const j = FIGURES.judges.answers;
  await expect(page.getByTestId("how")).toContainText(`a second judge, ${modelName(j.second)}, on ${j.answers} literature answers: the same mark on ${j.same_mark}`);
  await expect(page.getByTestId("how")).not.toContainText("one judge and one pass");
  // nothing on the page calls the grades a person's
  const text = (await page.getByTestId("how").innerText()).replace(/a human check \(Cloudflare Turnstile\)/g, "");
  expect(text).not.toMatch(/human|validat/i);
  // the traced question: whatever rows and sentences the file holds, with their source marks
  const trace = page.getByTestId("trace");
  await expect(trace.locator("tbody tr")).toHaveCount(FIGURES.trace.issues.length);
  await expect(trace.locator(".trace__q--a .mark")).toHaveCount(FIGURES.trace.answer.reduce((n, s) => n + s.sources.length, 0));
  await expect(trace.locator("tbody .mark")).toHaveCount(FIGURES.trace.issues.filter((i) => i.source != null).length);
});

test("page found, the two waits and \"gives what the question asks\" read right in both languages, when the run holds them", async ({ page }) => {
  const run = FIGURES.run;
  for (const lang of ["en", "es"] as const) {
    const loc = lang === "es" ? "es-CR" : "en";
    const of = lang === "es" ? "de" : "of";
    const s2 = (x: number) => new Intl.NumberFormat(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(x);
    await open(page, lang);
    const results = page.getByTestId("results");
    if (run.page_found) {
      const p = run.page_found;
      await expect(results.locator('[data-result="page"] .ledger__n')).toHaveText(`${p.found} ${of} ${p.of}`);
      await expect(results.locator('[data-result="page"]')).toContainText(
        lang === "es" ? `entre los ${p.k} pasajes. Contando los ${p.drafts - p.of} borradores que quedaron fuera: ${p.found} de ${p.drafts}.`
          : `among the ${p.k} passages. Counting the ${p.drafts - p.of} drafts left out: ${p.found} of ${p.drafts}.`);
    }
    if (run.literature.asks != null) {
      await expect(results.locator('[data-result="literature"]')).toContainText(
        lang === "es" ? `${run.literature.asks} de ${run.literature.of} dan lo que pide la pregunta` : `${run.literature.asks} of ${run.literature.of} give what the question asks`);
    }
    if (run.waits) {
      const costs = page.getByTestId("costs").locator("li");
      await expect(costs.nth(1)).toContainText(s2(run.waits.evidence));
      await expect(costs.nth(2)).toContainText(s2(run.waits.answer));
      await expect(costs.nth(2)).toContainText(lang === "es" ? `${s2(run.waits.answer_p95)} s en el percentil 95` : `${s2(run.waits.answer_p95)} s at the 95th percentile`);
    }
  }
});

test("on a phone the traced issues are a block each, every value with its column's name", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await open(page);
  const row = page.getByTestId("trace").locator("tbody tr").first();
  expect(await row.evaluate((el) => getComputedStyle(el).display)).toBe("block");
  expect(await row.locator("td").first().evaluate((el) => getComputedStyle(el, "::before").content)).toContain("Score");
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(await row.evaluate((el) => getComputedStyle(el).display)).toBe("table-row");
});

test("the web step and Tavily are on the page only in a build that asks for the web part", async ({ page }) => {
  await open(page);
  const how = page.getByTestId("how");
  const svg = page.getByTestId("pipeline");
  if (WEB_BUILD) {
    await expect(svg.locator('g[data-node="s5"]')).toHaveCount(1);
    await expect(svg.locator('g[data-node="s5"]')).toHaveClass(/p-node--some/);
    await expect(page.getByTestId("steps").locator("li").nth(4)).toContainText("searched on the web (Tavily)");
    await expect(page.getByTestId("how-privacy")).toContainText("When our sources cover only part of a question, or none of it, the question is also sent to Tavily (to search the web).");
    await expect(page.getByTestId("limits")).toContainText("A web part changes from one asking to the next and has no gold");
    // the questions outside the scope given a ticket for a web search in this run, from the generated file
    const t = FIGURES.run.web_tickets_outside_scope;
    await expect(page.getByTestId("limits")).toContainText(t.ticketed === 0
      ? `In this run, none of the ${t.of} questions outside the scope was given a ticket for a web search.`
      : `In this run, ${t.ticketed} of the ${t.of} questions outside the scope got a part answer, and with it a ticket for a web search.`);
    await expect(how).toContainText(`a pacing target of ${FIGURES.limits.web_searches_a_month} searches a month`);
    await expect(page.locator("h2#h-pipe")).toHaveText("A question, in five steps");
    await page.getByTestId("lang-toggle").click();
    await expect(page.getByTestId("limits")).toContainText(t.ticketed === 0
      ? `En esta corrida, ninguna de las ${t.of} preguntas fuera de alcance recibió un pase para una búsqueda en la web.`
      : `En esta corrida, ${t.ticketed} de las ${t.of} preguntas fuera de alcance ${t.ticketed === 1 ? "recibió" : "recibieron"} una respuesta parcial, y con ella un pase para una búsqueda en la web.`);
  } else {
    await expect(svg.locator('g[data-node="s5"]')).toHaveCount(0);
    await expect(how).not.toContainText("Tavily");
    await expect(how).not.toContainText("web part");
    await expect(page.locator("h2#h-pipe")).toHaveText("A question, in four steps");
    await expect(page.getByTestId("limits")).not.toContainText("In this run");
    await page.getByTestId("lang-toggle").click();
    await expect(page.getByTestId("limits")).not.toContainText("En esta corrida");
  }
});

test("the spend limit is named without its amount or its month, in both languages", async ({ page }) => {
  for (const lang of ["en", "es"] as const) {
    await open(page, lang);
    const line = page.locator("ul.safe li").filter({ hasText: HOW[lang].spend.lead });
    await expect(line, lang).toHaveCount(FIGURES.spend_limit ? 1 : 0);
    if (!FIGURES.spend_limit) continue;
    await expect(line, lang).toContainText(HOW[lang].spend.text);
    const text = await line.innerText();
    expect(text, lang).not.toMatch(/\d/);
    expect(text, lang).not.toMatch(/USD/i);
    expect(text, lang).not.toMatch(/November|noviembre/i);
  }
  // the generated file holds no amount and no month either
  expect(Object.keys(FIGURES.spend_limit ?? {})).not.toContain("usd");
  expect(Object.keys(FIGURES.spend_limit ?? {})).not.toContain("month");
});

test("the three links: the evaluation, the source, and back to the question page; and the ways in", async ({ page }) => {
  await open(page);
  const links = page.getByTestId("how-links");
  await expect(links.getByRole("link", { name: "The full evaluation, with every table and limit" })).toHaveAttribute("href", EVAL);
  await expect(links.getByRole("link", { name: "Source code" })).toHaveAttribute("href", REPO);
  await expect(links.getByRole("link", { name: "Ask about Costa Rican stamps" })).toHaveAttribute("href", "/");
  await expect(page.locator("footer.site-foot").getByRole("link", { name: "How it works" })).toHaveAttribute("href", URL);
  await expect(page.locator("header.masthead").getByRole("link", { name: "How it works" })).toHaveAttribute("href", URL);
  // from the question page, the header's link leads here
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await mock(page);
  await page.goto("/");
  await page.locator("header.masthead").getByRole("link", { name: /How it works|Cómo funciona/ }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
  await expect(page.locator("h1")).toHaveText(H1.en);
});

test("the figures file is what its sources give (scripts/how-figures.mjs --check)", () => {
  // regenerated from eval/outcomes, backend/app/settings.py, the versions and the test files; fails when it differs
  const out = execFileSync(process.execPath, [join(__dirname, "..", "scripts", "how-figures.mjs"), "--check"], { encoding: "utf-8" });
  expect(out).toContain("is up to date");
});
