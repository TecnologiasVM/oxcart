import { test, expect, Page } from "@playwright/test";
import { ANSWER, WRITTEN, ask, box, lines, mock, newest, noOverflow, serveFigures } from "./helpers";
import { isPdf, keepWeb, linkOf, ticketOf, webOn, withoutTicket } from "../lib/web";

/*
 * The web part (lib/web.ts; drawn on a2/82 to a2/94 of the mock), with the backend mocked in the
 * browser: the chat route's answer carries a made-up ticket, and the web route answers with a
 * made-up part. No network, no window. Every text, title and address is made up.
 *
 * Which build runs these: CI and playwright.config.ts build with NEXT_PUBLIC_WEB=1, and the tests of
 * the drawn states run. Built and run with NEXT_PUBLIC_WEB set to an empty value (a second build), the
 * tests of the off build run instead and the others are skipped; the unit tests at the end run in both.
 */
const WEB_BUILD = webOn(process.env.NEXT_PUBLIC_WEB ?? "1");

const TICKET = { ticket: "a-made-up-ticket", expires_in: 120 };
const PART = { ...WRITTEN, covers: "part", web: TICKET };
const NONE = { state: "not_covered", web: TICKET };
const ANSWER_TEXT = WRITTEN.sentences.map((s) => s.text).join(" ");
const WEB_OK = {
  state: "ok",
  sentences: [
    { text: "A made-up page says a letter to a made-up place cost 25 centavos in the made-up year 1865.", cites: [1] },
    { text: "Another made-up page agrees, and names a made-up stamp that paid it.", cites: [1, 2] },
  ],
  results: [
    { n: 1, title: "The made-up postal history of a made-up place", host: "stamps.example", url: "https://stamps.example/history.pdf" },
    { n: 2, title: "Another made-up page about rates", host: "www.other.example", url: "https://www.other.example/rates?page=2" },
  ],
  counts: { results_returned: 5, results_kept: 4, sentences: 3, sentences_without_citation: 1, citations: 3, citations_that_do_not_hold: 0 },
  calls: [{ purpose: "web", state: "ok", input_tokens: 2000, output_tokens: 120, seconds: 1.4 }],
};
const WORDS = {
  en: {
    title: "From the web · not from the catalogue or the literature",
    under: "Written by AI from the pages linked below. Nobody has checked those pages.",
    wait: "Searching the web for more…",
    nothing: "A web search found nothing to add.",
    scope: "This question is outside what Oxcart covers: Costa Rican stamps, postal stationery and postal history. No answer was written.",
    notCovered: "The catalogue and the literature do not answer this question, so no answer was written from them.",
    privacy: "When our sources cover only part of a question, or none of it, the question is also sent to Tavily (to search the web).",
  },
  es: {
    title: "De la web · no del catálogo ni de la literatura",
    under: "Escrito por IA a partir de las páginas enlazadas abajo. Nadie ha revisado esas páginas.",
    wait: "Buscando más en la web…",
    nothing: "Una búsqueda en la web no encontró nada que añadir.",
    scope: "Esta pregunta está fuera de lo que cubre Oxcart: sellos, enteros postales e historia postal de Costa Rica. No se escribió respuesta.",
    notCovered: "El catálogo y la literatura no responden esta pregunta, así que no se redactó una respuesta a partir de ellos.",
    privacy: "Cuando nuestras fuentes cubren solo una parte de una pregunta, o nada, la pregunta también se envía a Tavily (para buscar en la web).",
  },
};

type Asked = { question: string; answer: string; ticket: string };

/**
 * The web route, mocked: what it answers (a part, or a status with nothing), and every request it got. With
 * `hold`, it answers only when `release` is called, so the searching line can be seen.
 */
async function mockWeb(page: Page, reply: object = WEB_OK, options: { status?: number; hold?: boolean; abort?: boolean } = {}) {
  const asked: Asked[] = [];
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/chat/web", async (route) => {
    asked.push(route.request().postDataJSON() as Asked);
    if (options.hold) await held;
    if (options.abort) return route.abort();
    return route.fulfill({ status: options.status ?? 200, json: reply });
  });
  return { asked, release: () => release() };
}

/** The chat route answers with this written answer (and the usual evidence) from now on. */
const chatWith = async (page: Page, written: object, evidence: object = ANSWER) => {
  await page.unroute("**/api/chat");
  await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(written, evidence) }));
};

const block = (page: Page) => newest(page).getByTestId("web");
const settle = (page: Page) => page.waitForTimeout(400);

/** The turn's parts in order, as its children: the block stands after the answer's section, never inside it. */
const children = (page: Page) =>
  newest(page).evaluate((turn) => [...turn.children].map((el) => `${el.tagName.toLowerCase()}.${el.className.split(" ")[0]}`));

// ===================================================================== the drawn states (a build with NEXT_PUBLIC_WEB on)

test.describe("a build that asks for the web part", () => {
  test.skip(!WEB_BUILD, "built with NEXT_PUBLIC_WEB off: the tests of the off build run instead");

  test("82: an answer in part, then the web block, last in the turn and outside the answer's section", async ({ page }) => {
    await mock(page, { written: PART });
    const web = await mockWeb(page);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale, and at what rate?");
    await expect(block(page)).toBeVisible();
    // the answer from our sources is as it is today
    await expect(newest(page).getByTestId("answer-sentence")).toHaveCount(2);
    await expect(newest(page).getByTestId("answer-source")).toHaveCount(2);
    expect(await children(page)).toEqual(["header.turn__q", "section.a", "aside.web"]);
    const button = (await newest(page).getByTestId("evidence-button").boundingBox())!;
    expect((await block(page).boundingBox())!.y).toBeGreaterThan(button.y + button.height);
    // four things and no more: the heading, the line under it, the sentences with their marks, the cited pages
    await expect(block(page).getByRole("heading", { level: 3 })).toHaveText(WORDS.en.title);
    await expect(block(page).locator(".web__say")).toHaveText(WORDS.en.under);
    await expect(block(page).getByTestId("web-sentence")).toHaveText([/25 centavos/, /names a made-up stamp/]);
    await expect(block(page).locator(".web__text").getByTestId("web-mark")).toHaveText(["web page W1", "web page W1", "web page W2"]);
    const rows = block(page).getByTestId("web-result");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).locator(".web__t")).toHaveText("The made-up postal history of a made-up place");
    await expect(rows.nth(0).locator(".web__d")).toContainText("stamps.example");
    await expect(rows.nth(0).locator(".web__pdf")).toHaveText("PDF");                 // read from the address's ending
    await expect(rows.nth(1).locator(".web__pdf")).toHaveCount(0);
    await expect(rows.nth(1).locator(".web__d")).toContainText("www.other.example");
    // the request: once, with the question as it was searched, the answer's text and the ticket
    await settle(page);
    expect(web.asked).toEqual([{ question: ANSWER.question, answer: ANSWER_TEXT, ticket: TICKET.ticket }]);
    // a mark goes to its page in the list
    await block(page).getByTestId("web-mark").last().click();
    await expect(rows.nth(1)).toBeFocused();
    // the note under the thread is about the answers from our sources, and stays once
    await expect(page.getByTestId("ai-note")).toHaveCount(1);
  });

  test("82: with pictures under the answer, the block stands under them", async ({ page }) => {
    const fid = "00000000000000000a11";
    const evidence = { ...ANSWER, passages: [{ ...ANSWER.passages[0], figures: [{ id: fid, width: 300, height: 180, class: "B" }] }, ANSWER.passages[1]] };
    await mock(page, { written: PART, ask: evidence });
    await serveFigures(page, { [fid]: [300, 180] });
    await mockWeb(page);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(block(page)).toBeVisible();
    const pics = (await newest(page).getByTestId("figures").boundingBox())!;
    expect((await block(page).boundingBox())!.y).toBeGreaterThanOrEqual(pics.y + pics.height);
    expect(await children(page)).toEqual(["header.turn__q", "section.a", "aside.web"]);
  });

  test("83: not covered, then the web block under the notice and what was found", async ({ page }) => {
    await mock(page, { written: NONE });
    const web = await mockWeb(page);
    await page.goto("/");
    await ask(page, "What did a letter to a made-up place cost in 1865?");
    await expect(block(page)).toBeVisible();
    await expect(newest(page).getByTestId("not-covered")).toHaveText(WORDS.en.notCovered);
    await expect(newest(page).getByTestId("evidence-button")).toContainText("What was found");
    expect(await children(page)).toEqual(["header.turn__q", "section.a", "aside.web"]);
    await settle(page);
    expect(web.asked).toEqual([{ question: ANSWER.question, answer: "", ticket: TICKET.ticket }]);
    await expect(page.getByTestId("ai-note")).toHaveCount(0);                         // no answer was written from our sources
  });

  for (const [name, written] of [["84: under an answer", PART], ["85: under not covered", NONE]] as const) {
    test(`${name}, the web being searched is one line with the dashed edge, in the block's place`, async ({ page }) => {
      await mock(page, { written });
      const web = await mockWeb(page, WEB_OK, { hold: true });
      await page.goto("/");
      await ask(page, "What did a letter to a made-up place cost in 1865?");
      const line = newest(page).getByTestId("web-searching");
      await expect(line).toHaveText(WORDS.en.wait);
      await expect(line).toHaveCSS("border-left-style", "dashed");
      await expect(line).toHaveAttribute("role", "status");
      await expect(newest(page).getByTestId("web")).toHaveCount(0);                  // no heading, no frame
      expect(await children(page)).toEqual(["header.turn__q", "section.a", "div.webline"]);
      // the box takes the next question while the web is searched
      await expect(box(page)).toBeEnabled();
      web.release();
      await expect(block(page)).toBeVisible();
      await expect(line).toHaveCount(0);
    });
  }

  test("86: the web has nothing to add under an answer: nothing is drawn", async ({ page }) => {
    await mock(page, { written: PART });
    await mockWeb(page, { state: "nothing", counts: {}, calls: [] });
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    await expect(newest(page).getByTestId("web-searching")).toHaveCount(0);
    await settle(page);
    await expect(newest(page).locator(".web, .webline")).toHaveCount(0);
    expect(await children(page)).toEqual(["header.turn__q", "section.a"]);
  });

  test("87: the web has nothing to add under not covered: one line", async ({ page }) => {
    await mock(page, { written: NONE });
    await mockWeb(page, { state: "nothing", counts: {}, calls: [] });
    await page.goto("/");
    await ask(page, "What did a letter to a made-up place cost in 1865?");
    const line = newest(page).getByTestId("web-nothing");
    await expect(line).toHaveText(WORDS.en.nothing);
    await expect(line).toHaveCSS("border-left-style", "dashed");
    await expect(newest(page).getByTestId("web")).toHaveCount(0);
  });

  test("88: the searches used up, or the search failed: nothing, under not covered and under an answer", async ({ page }) => {
    for (const [reply, options] of [[{ state: "unavailable" }, {}], [{ error: "ticket_refused" }, { status: 403 }], [{}, { status: 503 }], [{}, { abort: true }]] as const) {
      for (const written of [NONE, PART]) {
        await page.unrouteAll({ behavior: "ignoreErrors" });
        await mock(page, { written });
        await mockWeb(page, reply, options);
        await page.goto("/");
        await page.evaluate(() => window.localStorage.clear());
        await page.reload();
        await ask(page, "What did a letter to a made-up place cost in 1865?");
        await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
        await expect(newest(page).getByTestId("web-searching")).toHaveCount(0);
        await expect(newest(page).locator(".web, .webline")).toHaveCount(0);
        expect(await children(page)).toEqual(["header.turn__q", "section.a"]);
      }
    }
  });

  test("89: out of scope: its sentence in the notice, what was found, and never a web line", async ({ page }) => {
    await mock(page, { written: { state: "out_of_scope" } });
    const web = await mockWeb(page);
    await page.goto("/");
    await ask(page, "What is the best way to remove a made-up stamp from an envelope?");
    await expect(newest(page).getByTestId("out-of-scope")).toHaveText(WORDS.en.scope);
    await expect(newest(page).getByTestId("evidence-button")).toContainText("What was found");
    await settle(page);
    await expect(newest(page).locator(".web, .webline")).toHaveCount(0);
    expect(web.asked).toEqual([]);
  });

  test("90 to 93: in Spanish, the block, Details open, the searching line, the one line and out of scope", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
    await mock(page, { written: PART });
    let web = await mockWeb(page);
    await page.goto("/");
    await ask(page, "¿Cuándo se puso a la venta, y con qué porte?");
    await expect(block(page).getByRole("heading", { level: 3 })).toHaveText(WORDS.es.title);
    await expect(block(page).locator(".web__say")).toHaveText(WORDS.es.under);
    await expect(block(page).getByTestId("web-mark").first()).toHaveText("página web W1");
    await expect(block(page).getByTestId("web-link").first()).toContainText("se abre en otra pestaña");
    await page.getByTestId("privacy").getByText("Detalles").click();
    await expect(page.getByTestId("privacy-full")).toContainText(WORDS.es.privacy);
    await page.unroute("**/api/chat/web");
    web = await mockWeb(page, { state: "nothing" }, { hold: true });
    await chatWith(page, NONE);
    await ask(page, "¿Cuánto costaba una carta a un lugar inventado?");
    await expect(newest(page).getByTestId("web-searching")).toHaveText(WORDS.es.wait);
    await expect(newest(page).getByTestId("not-covered")).toHaveText(WORDS.es.notCovered);
    web.release();
    await expect(newest(page).getByTestId("web-nothing")).toHaveText(WORDS.es.nothing);
    await chatWith(page, { state: "out_of_scope" });
    await ask(page, "¿Cómo despego un sello inventado de un sobre?");
    await expect(newest(page).getByTestId("out-of-scope")).toHaveText(WORDS.es.scope);
    await expect(newest(page).locator(".web, .webline")).toHaveCount(0);
  });

  test("94: an older turn's block is one line that opens in place, by keyboard", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await mock(page, { written: NONE });
    await mockWeb(page);
    await page.goto("/");
    await ask(page, "What did a letter to a made-up place cost in 1865?");
    await expect(block(page)).toBeVisible();
    await chatWith(page, WRITTEN);
    await ask(page, "When was the test issue placed on sale?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    const older = page.getByTestId("turn").first().getByTestId("web");
    await expect(older).toHaveJSProperty("tagName", "DETAILS");
    await expect(older).not.toHaveAttribute("open", "");
    await expect(older.getByTestId("web-open")).toHaveText(WORDS.en.title);
    await expect(older.getByTestId("web-sentence").first()).toBeHidden();
    await older.getByTestId("web-open").focus();
    await page.keyboard.press("Enter");
    await expect(older).toHaveAttribute("open", "");
    await expect(older.getByTestId("web-sentence").first()).toBeVisible();
    await expect(older.getByTestId("web-link").first()).toBeVisible();
    await noOverflow(page, "older block open, 360");
    await expect(newest(page).getByTestId("web")).toHaveCount(0);                    // the new answer was answered in full
  });

  test("the request is made once, and never for a turn read back from storage", async ({ page }) => {
    await mock(page, { written: PART });
    const web = await mockWeb(page);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(block(page)).toBeVisible();
    await settle(page);
    expect(web.asked).toHaveLength(1);
    // kept with its turn, without the ticket
    const kept = await page.evaluate(() => JSON.parse(window.localStorage.getItem("oxcart-conversations")!).conversations[0].turns[0]);
    expect(kept.web.state).toBe("ok");
    expect(kept.web.results[0].url).toBe("https://stamps.example/history.pdf");
    expect(kept.written.web).toBeUndefined();
    await page.reload();
    await expect(block(page)).toBeVisible();
    await expect(block(page).getByTestId("web-sentence")).toHaveCount(2);
    await settle(page);
    expect(web.asked).toHaveLength(1);
  });

  test("a turn kept with a ticket or with a search under way, as an older page left it, never asks", async ({ page }) => {
    const turn = (n: number, extra: object) => ({ id: `t-${n}`, question: `A kept question ${n}?`, at: `2026-11-20T10:00:0${n}.000Z`, answer: ANSWER, ...extra });
    const store = { version: 2, current: "c-1", conversations: [{ id: "c-1", started: "2026-11-20T10:00:00.000Z", turns: [
      turn(1, { written: PART }),                                                     // a ticket in the kept answer
      turn(2, { written: NONE, web: { state: "searching" } }),                        // closed while searching
      turn(3, { written: { state: "not_covered" } }),                                 // kept before the web part existed
    ] }] };
    await page.addInitScript((value) => window.localStorage.setItem("oxcart-conversations", value), JSON.stringify(store));
    await mock(page);
    const web = await mockWeb(page);
    await page.goto("/");
    await expect(page.getByTestId("turn")).toHaveCount(3);
    await settle(page);
    expect(web.asked).toEqual([]);
    await expect(page.locator(".web, .webline")).toHaveCount(0);
    await expect(page.getByTestId("turn").nth(2).getByTestId("not-covered")).toBeVisible();
  });

  test("a follow-up sends the earlier answer from our sources, never the web part", async ({ page }) => {
    await mock(page, { written: PART });
    await mockWeb(page);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(block(page)).toBeVisible();
    const sent: { thread: { question: string; answer: string }[] }[] = [];
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => {
      sent.push(route.request().postDataJSON());
      return route.fulfill({ contentType: "application/x-ndjson", body: lines(WRITTEN) });
    });
    await ask(page, "And who printed it?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    expect(sent[0].thread).toEqual([{ question: ANSWER.question, answer: ANSWER_TEXT }]);
    const body = JSON.stringify(sent);
    for (const words of ["25 centavos", "stamps.example", "made-up page", "a-made-up-ticket"]) expect(body).not.toContain(words);
  });

  test("an address that is not https, or carries a user name, is never a link; a link opens in a new tab with noopener noreferrer", async ({ page }) => {
    const odd = {
      ...WEB_OK,
      sentences: [{ text: 'Made-up <a href="https://evil.example">markup</a> and **stars** stay text.', cites: [1, 2, 3, 4, 5] }],
      results: [
        { n: 1, title: "A plain page", host: "plain.example", url: "http://plain.example/a" },
        { n: 2, title: "A page with a name", host: "named.example", url: "https://someone@named.example/a" },
        { n: 3, title: "A page with a password", host: "secret.example", url: "https://someone:pw@secret.example/a" },
        { n: 4, title: "<b>A script</b>", host: "script.example", url: "javascript:alert(1)" },
        { n: 5, title: "A good page", host: "good.example", url: "https://good.example/a.PDF?x=1" },
      ],
    };
    await mock(page, { written: NONE });
    await mockWeb(page, odd);
    await page.goto("/");
    await ask(page, "What did a letter cost?");
    await expect(block(page)).toBeVisible();
    const links = block(page).locator("a");
    await expect(links).toHaveCount(1);
    await expect(links).toHaveAttribute("href", "https://good.example/a.PDF?x=1");
    await expect(links).toHaveAttribute("rel", "noopener noreferrer");
    await expect(links).toHaveAttribute("target", "_blank");
    await expect(links).toContainText("(opens in a new tab)");
    await expect(block(page).getByTestId("web-result").nth(4).locator(".web__pdf")).toHaveText("PDF");
    for (const n of [0, 1, 2, 3]) await expect(block(page).getByTestId("web-result").nth(n).locator(".web__plain")).toBeVisible();
    await expect(block(page).getByTestId("web-result").nth(3)).toContainText("<b>A script</b>");      // a title is text
    await expect(block(page).locator(".web__text")).toContainText('<a href="https://evil.example">markup</a> and **stars**');
    await expect(block(page).locator(".web__text b, .web__text a, .web__list b:not(.wmark)")).toHaveCount(0);
  });

  test("no horizontal overflow at 360, 820, 1100, 1280, 1440 and 1600 px, newest and older", async ({ page }) => {
    test.setTimeout(90_000);
    const long = {
      ...WEB_OK,
      results: [
        { n: 1, title: "A made-up title with a very long word: Postgeschichtsuntersuchungsergebnissammlungsband", host: "a-very-long-made-up-host-name-for-a-test.example", url: "https://a-very-long-made-up-host-name-for-a-test.example/" + "segment/".repeat(30) + "file.pdf" },
        WEB_OK.results[1],
      ],
    };
    await mock(page, { written: PART });
    await mockWeb(page, long);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(block(page)).toBeVisible();
    await chatWith(page, NONE);
    await ask(page, "And at what rate?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(block(page)).toBeVisible();
    await page.getByTestId("turn").first().getByTestId("web-open").click();
    for (const width of [360, 820, 1100, 1280, 1440, 1600]) {
      await page.setViewportSize({ width, height: 900 });
      await noOverflow(page, `web, ${width}`);
      const over = await page.locator(".web").evaluateAll((all) => all.map((el) => el.scrollWidth - el.clientWidth));
      expect(over.every((n) => n <= 0), `the block's own width at ${width}`).toBe(true);
    }
  });

  for (const width of [360, 1440]) {
    test(`by keyboard the links and the closed block's opener are reached with a visible ring, never under the pinned box, at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await mock(page, { written: NONE });
      await mockWeb(page);
      await page.goto("/");
      await ask(page, "What did a letter cost?");
      await expect(block(page)).toBeVisible();
      await chatWith(page, PART);
      await ask(page, "And when was it placed on sale?");
      await expect(page.getByTestId("turn")).toHaveCount(2);
      await expect(block(page)).toBeVisible();
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.locator(".turn__text").first().evaluate((el) => {
        el.setAttribute("tabindex", "-1");
        (el as HTMLElement).focus();
      });
      const seen = new Set<string>();
      for (const key of [...Array(45).fill("Tab"), ...Array(45).fill("Shift+Tab")]) {
        await page.keyboard.press(key);
        await page.waitForTimeout(25);
        const where = await focusedClear(page);
        expect(where.ok, `${key}: ${where.what}`).toBe(true);
        if (where.web) {
          seen.add(where.web);
          expect(where.ring, `the ring on ${where.web}`).toBe("3px solid");
        }
      }
      expect([...seen].sort()).toEqual(["link", "mark", "opener"]);
    });
  }

  for (const width of [360, 1440]) {
    test(`nothing on screen moves when the block arrives, at ${width} px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await mock(page, { written: PART });
      const web = await mockWeb(page, WEB_OK, { hold: true });
      await page.goto("/");
      await ask(page, "When was the test issue placed on sale?");
      await expect(newest(page).getByTestId("web-searching")).toBeVisible();
      await page.waitForTimeout(300);
      const where = () => page.evaluate(() => ({
        scroll: window.scrollY,
        parts: [".turn__text", ".a__text", "[data-testid=answer-source]", "[data-testid=evidence-button]", ".webline"].map((sel) =>
          Math.round(document.querySelector(`.thread > article:last-child ${sel}`)!.getBoundingClientRect().top)),
      }));
      const before = await where();
      web.release();
      await expect(block(page)).toBeVisible();
      await page.waitForTimeout(300);
      const after = await page.evaluate(() => ({
        scroll: window.scrollY,
        parts: [".turn__text", ".a__text", "[data-testid=answer-source]", "[data-testid=evidence-button]", ".web"].map((sel) =>
          Math.round(document.querySelector(`.thread > article:last-child ${sel}`)!.getBoundingClientRect().top)),
      }));
      expect(after).toEqual(before);                    // the block took the searching line's place, and nothing above it moved
    });
  }

  test("two tabs: the web part a tab received is kept when the other tab writes the same conversation", async ({ page, context }) => {
    await mock(page, { written: PART });
    await mockWeb(page);
    await page.goto("/");
    await ask(page, "When was the test issue placed on sale?");
    await expect(page.getByTestId("written-answer")).toBeVisible();
    const other = await context.newPage();
    await mock(other, { written: WRITTEN });
    await other.goto("/");
    await expect(other.getByTestId("turn")).toHaveCount(1);
    await expect(block(page)).toBeVisible();
    await expect(other.getByTestId("web")).toBeVisible();                        // it followed the first tab
    await ask(other, "And who printed it?");
    await expect(other.getByTestId("turn")).toHaveCount(2);
    await expect(other.getByTestId("turn").nth(1).getByTestId("written-answer")).toBeVisible();
    await page.waitForTimeout(300);
    const kept = await page.evaluate(() => JSON.parse(window.localStorage.getItem("oxcart-conversations")!).conversations[0].turns);
    expect(kept).toHaveLength(2);
    expect(kept[0].web.state).toBe("ok");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(page.getByTestId("turn").first().getByTestId("web")).toHaveCount(1);
  });

  test("screenshots of the web states at 360 and 1440 px (kept under test-results, not committed)", async ({ page }) => {
    test.setTimeout(180_000);
    const states: [string, object, object | null, boolean][] = [
      ["82-part", PART, WEB_OK, false], ["83-not-covered", NONE, WEB_OK, false], ["84-searching", PART, WEB_OK, true],
      ["85-searching-not-covered", NONE, WEB_OK, true], ["86-nothing", PART, { state: "nothing" }, false],
      ["87-nothing-not-covered", NONE, { state: "nothing" }, false], ["88-used-up-not-covered", NONE, { state: "unavailable" }, false],
      ["89-out-of-scope", { state: "out_of_scope" }, null, false],
    ];
    for (const width of [360, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const [name, written, reply, hold] of states) {
        await page.unrouteAll({ behavior: "ignoreErrors" });
        await mock(page, { written });
        const web = await mockWeb(page, reply ?? {}, { hold });
        await page.goto("/");
        await page.evaluate(() => window.localStorage.clear());
        await page.reload();
        await ask(page, "What did a letter to a made-up place cost in 1865?");
        await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
        if (hold) await expect(newest(page).getByTestId("web-searching")).toBeVisible();
        else await settle(page);
        await page.screenshot({ path: `test-results/screens/web-${name}-${width}.png`, fullPage: true });
        web.release();
      }
      await page.unrouteAll({ behavior: "ignoreErrors" });
      await mock(page, { written: NONE });
      await mockWeb(page);
      await page.evaluate(() => window.localStorage.clear());
      await page.reload();
      await ask(page, "What did a letter to a made-up place cost in 1865?");
      await expect(block(page)).toBeVisible();
      await chatWith(page, WRITTEN);
      await ask(page, "When was the test issue placed on sale?");
      await expect(page.getByTestId("turn")).toHaveCount(2);
      await page.screenshot({ path: `test-results/screens/web-94-older-turn-${width}.png`, fullPage: true });
    }
  });
});

/** Where the focused element stands against the window and the box pinned at the foot, and which part of the web block it is. */
async function focusedClear(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    const dock = document.querySelector<HTMLElement>(".dock")!;
    const pinned = (getComputedStyle(dock).display === "contents" ? document.querySelector<HTMLElement>("form.composer")! : dock).getBoundingClientRect();
    const web = !el?.closest(".web") ? "" : el.matches("summary") ? "opener" : el.matches("a") ? "link" : el.matches("button.wmark") ? "mark" : el.tagName;
    const style = el ? getComputedStyle(el) : null;
    const ring = style ? `${style.outlineWidth} ${style.outlineStyle}` : "";
    if (!el || !el.closest(".conv") || el.closest(".dock, form.composer")) return { ok: true, what: el?.tagName ?? "", web, ring };
    const r = el.getBoundingClientRect();
    const ok = r.top >= 0 && r.bottom <= window.innerHeight && (r.bottom <= pinned.top || r.top >= pinned.bottom);
    return { ok, what: `${el.tagName}.${el.className} ${Math.round(r.top)}-${Math.round(r.bottom)} box ${Math.round(pinned.top)}`, web, ring };
  });
}

// ===================================================================== a build with NEXT_PUBLIC_WEB off

test.describe("a build that does not ask for the web part", () => {
  test.skip(WEB_BUILD, "built with NEXT_PUBLIC_WEB on: run with NEXT_PUBLIC_WEB empty, after a build with it empty");

  test("a ticket in a reply is ignored: no request, no line, today's sentence and today's privacy paragraph", async ({ page }) => {
    await mock(page, { written: NONE });
    const web = await mockWeb(page);
    await page.goto("/");
    await page.getByTestId("privacy").getByText("Details").click();
    await expect(page.getByTestId("privacy-full")).not.toContainText("Tavily");
    await ask(page, "What did a letter to a made-up place cost in 1865?");
    await expect(newest(page).getByTestId("not-covered")).toHaveText(
      "The evidence that was found does not answer this question, so no answer was written. What was found is below.");
    await chatWith(page, PART);
    await ask(page, "When was the test issue placed on sale?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    await settle(page);
    expect(web.asked).toEqual([]);
    await expect(page.locator(".web, .webline")).toHaveCount(0);
    const kept = await page.evaluate(() => JSON.parse(window.localStorage.getItem("oxcart-conversations")!).conversations[0].turns);
    expect(kept.every((turn: { web?: unknown; written?: { web?: unknown } }) => !turn.web && !turn.written?.web)).toBe(true);
  });
});

// ===================================================================== the pieces, with no page (any build)

test("the build setting, the ticket, the link and the PDF mark are read as documented", () => {
  for (const on of ["1", "true", "yes", "on", " ON ", "True"]) expect(webOn(on)).toBe(true);
  for (const off of [undefined, "", "0", "false", "no", "off", "web"]) expect(webOn(off)).toBe(false);
  // a build with the web off ignores a ticket; with it on, only a well-formed one is used
  expect(ticketOf(PART, false)).toBeNull();
  expect(ticketOf(PART, true)).toBe(TICKET.ticket);
  for (const odd of [{ ...WRITTEN }, { ...WRITTEN, web: {} }, { ...WRITTEN, web: { ticket: 7 } }, { ...WRITTEN, web: { ticket: "" } }]) {
    expect(ticketOf(odd, true)).toBeNull();
  }
  expect(ticketOf(undefined, true)).toBeNull();
  expect(withoutTicket(PART)).toEqual({ ...WRITTEN, covers: "part" });
  // an address is a link only when https, with no user name or password, and a host
  expect(linkOf("https://stamps.example/a?b=1#c")).toBe("https://stamps.example/a?b=1#c");
  for (const bad of ["http://stamps.example/", "https://a@stamps.example/", "https://a:b@stamps.example/", "javascript:alert(1)", "https://",
                     "https:///x", "https:\\\\x.example/", "https://x.example\\@y.example/", " https://stamps.example/", "https://stamps .example/", "//stamps.example/", "https://x.example/" + "a".repeat(300), 7, null]) {
    expect(linkOf(bad), String(bad)).toBeNull();
  }
  expect([isPdf("https://x.example/a.pdf"), isPdf("https://x.example/a.PDF?x=1#p"), isPdf("https://x.example/pdf"), isPdf("https://x.example/a.pdf.html")])
    .toEqual([true, true, false, false]);
  // what is drawn is kept only in its known shape
  expect(keepWeb({ state: "nothing", extra: "x" })).toEqual({ state: "nothing" });
  expect(keepWeb({ state: "searching" })).toEqual({ state: "unavailable" });
  expect(keepWeb(null)).toEqual({ state: "unavailable" });
  expect(keepWeb({ ...WEB_OK, sentences: [{ text: "Cites a page not listed.", cites: [9] }] })).toEqual({ state: "nothing" });
  const kept = keepWeb(WEB_OK);
  expect(kept).toEqual({ state: "ok", sentences: WEB_OK.sentences, results: WEB_OK.results });
});
