import { test, expect, Page } from "@playwright/test";
import { formatDate } from "../lib/evidence-text";
import { webOn } from "../lib/web";
import {
  ANSWER,
  ISSUE,
  LONG,
  STORED,
  type SeedTurn,
  THREAD,
  WRITTEN,
  ask,
  box,
  checkInReach,
  checkMode,
  checks,
  deleteConversation,
  lines,
  mock,
  newest,
  noOverflow,
  panel,
  seed,
  settleCheck,
  startNew,
} from "./helpers";

/*
 * The question page, with the backend's answers mocked in the browser. No live backend,
 * no network, no window: Chromium runs headless. Every fixture is made up.
 *
 * The site under test is built with Cloudflare's documented test site key that always passes
 * (NEXT_PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA), so the human check is on. Every test
 * routes Cloudflare's script to a stub (TURNSTILE_STUB: no network) and mocks /api/session. The
 * stub passes on its own unless a test sets another mode with `checkMode`.
 * A build with no site key (no human check) is not covered by these tests.
 */

// the build the tests run against asks for the web part unless it was built with NEXT_PUBLIC_WEB empty
const WEB_BUILD = webOn(process.env.NEXT_PUBLIC_WEB ?? "1");

// ===================================================================== the first screen

test("the site opens directly on the question box", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByLabel(/Your question|Su pregunta/)).toBeVisible();
  await expect(page.locator("header.masthead")).toContainText("Oxcart");
  await expect(page.getByTestId("demo-tag")).toBeVisible();
  await expect(page.getByRole("button", { name: "A live example question?" })).toBeVisible();
  // "How it works" is one link away; no figure is written on the page
  await expect(page.locator("main").getByRole("link", { name: "How it works and how it was evaluated" })).toHaveAttribute("href", "/how-it-works");
  await expect(page.locator("main")).not.toContainText(/For engineers| of 41| of 32| of 357/);
});

test("the privacy line stands by the box, and Details unfolds the full paragraph", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const line = page.getByTestId("privacy");
  await expect(line).toContainText(/Your question goes to outside services\. The server does not store it\./);
  await expect(line.locator("summary")).not.toContainText(/OpenAI|Anthropic|Cloudflare/);   // no company name in the closed line
  // between the box and the Ask button, so it is read before a question can be sent
  const boxBottom = (await box(page).boundingBox())!.y;
  const lineTop = (await line.boundingBox())!.y;
  const buttonTop = (await page.getByRole("button", { name: /^(Ask|Preguntar)$/ }).boundingBox())!.y;
  expect(boxBottom).toBeLessThan(lineTop);
  expect(lineTop).toBeLessThan(buttonTop);
  await expect(page.getByTestId("privacy-full")).toBeHidden();
  await line.getByText(/Details|Detalles/).click();
  const full = page.getByTestId("privacy-full");
  await expect(full).toBeVisible();
  for (const name of ["OpenAI", "Anthropic", "Cloudflare"]) await expect(full).toContainText(name);
  // this build draws pictures (the tests' figures host), so the paragraph says where they come from
  await expect(full).toContainText("Pictures are loaded by your browser from a separate host at Cloudflare, which sees your browser's address as any web server does.");
  // the web search service is named only in a build that asks for the web part (tests-e2e/web.spec.ts)
  if (WEB_BUILD) await expect(full).toContainText("When our sources cover only part of a question, or none of it, the question is also sent to Tavily (to search the web).");
  else await expect(full).not.toContainText("Tavily");
  // what the server holds of a question: the vectors of the last 256, in memory, with no text (backend: Embedder)
  await expect(full).toContainText("last 256 questions");
  await expect(full).toContainText("writes nothing to disk");
  // the footer is one line, with no company name; "How it works" is the site's own page, the source the repository
  const footer = page.locator("footer.site-foot");
  await expect(footer).not.toContainText(/OpenAI|Anthropic|Cloudflare/);
  await expect(footer.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/how-it-works");
  await expect(footer.getByRole("link", { name: "Source · MIT" })).toHaveAttribute("href", "https://github.com/TecnologiasVM/oxcart");
  await expect(page.locator("header.masthead").getByRole("link", { name: /How it works|Cómo funciona/ })).toHaveAttribute("href", "/how-it-works");
  // in a conversation it stands under the box
  await ask(page, "A question?");
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
  const composerBottom = (await box(page).boundingBox())!;
  const threadLine = (await page.getByTestId("privacy").boundingBox())!;
  expect(threadLine.y).toBeGreaterThan(composerBottom.y + composerBottom.height - 1);
});

test("a question holds at most 300 characters, and the box counts down the last 60", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(box(page)).toHaveAttribute("maxlength", "300");
  await expect(page.getByTestId("chars-left")).toHaveCount(0);
  await box(page).fill("x".repeat(250));
  await expect(page.getByTestId("chars-left")).toHaveText(/50 characters left|Quedan 50 caracteres/);
  await box(page).fill("y".repeat(400));
  await expect(box(page)).toHaveValue("y".repeat(300));
  await expect(page.getByTestId("chars-left")).toHaveText(/0 characters left|Quedan 0 caracteres/);
});

test("the questions to try give way to the thread, and come back when it is deleted", async ({ page }) => {
  const many = Array.from({ length: 8 }, (_, i) => ({ lang: "en", question: `Example question number ${i + 1}?` }));
  await mock(page, { examples: many });
  await page.goto("/");
  const examples = page.getByRole("button", { name: /Example question number/ });
  await expect(examples).toHaveCount(8);
  await ask(page, "A typed question?");
  const turn = newest(page);
  await expect(turn.getByTestId("evidence-button")).toBeVisible();
  await expect(examples).toHaveCount(0);
  await expect(turn.locator(".turn__text")).toBeInViewport();          // not below a list
  await page.reload();                                                // a conversation found on opening: no list
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(examples).toHaveCount(0);
  await deleteConversation(page);
  await expect(examples).toHaveCount(8);
  await examples.first().click();                                     // a live example is asked at once
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page)).toContainText("Example question number 1?");
});

test("the page speaks Spanish and English", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const toggle = page.getByTestId("lang-toggle");
  const before = await page.locator("h1").first().innerText();
  await toggle.click();
  await expect(page.locator("h1").first()).not.toHaveText(before);
  await expect(page.getByTestId("privacy")).toContainText("Su pregunta va a servicios externos.");
  await page.reload();
  await expect(page.locator("h1").first()).not.toHaveText(before);   // the choice is remembered
});

test("muted ink holds 4.5:1 or more on each of the three papers", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const css = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const v = (name: string) => root.getPropertyValue(name).trim();
    return {
      muted: v("--color-ink-muted"),
      papers: [v("--color-paper"), v("--color-paper-2"), v("--color-paper-3")],
      rendered: getComputedStyle(document.querySelector(".ask .label")!).color,
    };
  });
  expect(css.muted.toLowerCase()).toBe("#55524b");
  expect(css.rendered).toBe("rgb(85, 82, 75)");                       // what the page actually paints
  const channel = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map(channel);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  for (const paper of css.papers) {
    const [hi, lo] = [luminance(paper), luminance(css.muted)].sort((a, b) => b - a);
    const ratio = (hi + 0.05) / (lo + 0.05);
    expect(ratio, `muted on ${paper}`).toBeGreaterThanOrEqual(4.5);
  }
});

// ===================================================================== the service

test("with nothing heard from the service for 90 seconds the page says it is not answering, whatever a try takes", async ({ page }) => {
  await page.clock.install();
  await mock(page, { health: 0 });
  await page.goto("/");
  let seconds = 0;
  const pass = async (until: number) => {
    while (seconds < until) {
      await page.clock.runFor(2000);
      seconds += 2;
      await page.waitForTimeout(20);        // the call that failed is seen before the clock moves again
    }
  };
  await pass(80);
  await expect(page.getByTestId("service-starting")).toContainText(/Waking the service…|Despertando el servicio…/);
  await expect(page.getByTestId("service-unreachable")).toHaveCount(0);
  await pass(96);
  await expect(page.getByTestId("service-unreachable")).toContainText(/not answering right now|no responde en este momento/);
  await expect(page.getByTestId("service-starting")).toHaveCount(0);
});

test("the waking notice ends 180 seconds after the page started looking, even while the service answers that it is connecting", async ({ page }) => {
  await page.clock.install();
  await mock(page);
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok", graph: "connecting", literature: "connected", embedding: "connected" } }));
  await page.goto("/");
  let seconds = 0;
  const pass = async (until: number) => {
    while (seconds < until) {
      await page.clock.runFor(2000);
      seconds += 2;
      await page.waitForTimeout(20);
    }
  };
  await pass(170);                                          // well past the 90 seconds: it answers, so it is not "not answering"
  await expect(page.getByTestId("service-starting")).toBeVisible();
  await expect(page.getByTestId("service-unreachable")).toHaveCount(0);
  await pass(190);
  await expect(page.getByTestId("service-unreachable")).toContainText(/not answering right now|no responde en este momento/);
  await expect(page.getByTestId("service-starting")).toHaveCount(0);
});

test("stored examples show real evidence while the service is not answering, marked as stored", async ({ page }) => {
  await mock(page, { health: 0, stored: STORED });
  await page.goto("/");
  await expect(page.getByTestId("service-starting")).toContainText(/Waking the service…|Despertando el servicio…/, { timeout: 15_000 });
  await expect(page.getByTestId("service-starting")).toContainText(/stored examples work meanwhile|funcionan los ejemplos guardados/);
  await page.getByRole("button", { name: /A stored example question\?/ }).click();
  const turn = newest(page);
  await expect(turn.getByTestId("stored-tag")).toBeVisible();
  await expect(turn.getByTestId("stored-note")).toContainText("2026-11-19");
  await turn.getByTestId("evidence-button").click();
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("passage")).toHaveCount(2);
  await expect(panel(page).getByTestId("ev-stored-note")).toContainText("2026-11-19");
  await page.getByTestId("tab-made").click();
  await expect(panel(page).getByTestId("mode-line")).toHaveAttribute("data-mode", "vector");
});

test("the page keeps saying 'starting' while the backend is up but one of its connections is still opening", async ({ page }) => {
  const state = { graph: "connecting", literature: "connecting", embedding: "connecting" };
  await mock(page);
  await page.route("**/api/health", (route) => route.fulfill({ json: { status: "ok", ...state } }));
  await page.goto("/");
  const notice = page.getByTestId("service-starting");
  await expect(notice).toContainText(/Connecting to the catalogue and the literature|Conectando con el catálogo y la literatura/, { timeout: 15_000 });
  await expect(notice.getByTestId("waiting-seconds")).toHaveText(/^\d+ s$/);
  await expect(notice).not.toContainText(/stored examples|ejemplos guardados/);   // this page was built without any
  state.graph = "connected";
  state.embedding = "not configured";
  await page.waitForTimeout(2500);
  await expect(notice).toBeVisible();                                // the literature client is still opening
  state.literature = "connected";
  await expect(notice).toHaveCount(0, { timeout: 20_000 });
});

// ===================================================================== a turn arriving

test("searching: the first seconds show the bar and one line, in view at the foot of the thread, on a small screen too", async ({ page }) => {
  let answer: () => void = () => {};
  const held = new Promise<void>((resolve) => (answer = resolve));
  await page.setViewportSize({ width: 390, height: 700 });
  await mock(page, { examples: Array.from({ length: 8 }, (_, i) => ({ lang: "en", question: `Example question number ${i + 1}?` })) });
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.fulfill({ contentType: "application/x-ndjson", body: lines({ state: "no_key" }) });
  });
  await page.goto("/");
  await ask(page, "A typed question?");
  const turn = newest(page);
  await expect(turn.getByTestId("searching-bar")).toBeInViewport();
  await expect(turn).toContainText(/Searching…|Buscando…/);
  await expect(turn.getByTestId("waiting")).toHaveCount(0);           // no waiting lines in the first seconds
  await expect(page.getByRole("button", { name: /^(Searching…|Buscando…)$/ })).toBeDisabled();
  answer();
  await expect(turn.getByTestId("evidence-button")).toBeVisible();
  await expect(turn.getByTestId("searching-bar")).toHaveCount(0);
});

test("a question asked while the service wakes shows short lines that follow one another, with a count of seconds", async ({ page }) => {
  let phase: "asleep" | "connecting" | "ready" = "asleep";
  let answer: () => void = () => {};
  const asked = new Promise<void>((resolve) => (answer = resolve));
  await mock(page);
  await page.route("**/api/health", (route) =>
    phase === "asleep"
      ? route.abort()
      : route.fulfill({ json: { status: "ok", graph: "connected", literature: phase === "ready" ? "connected" : "connecting", embedding: "connected" } }));
  await page.route("**/api/chat", async (route) => {
    await asked;                                                      // the question waits, as it does while the service wakes
    await route.fulfill({ contentType: "application/x-ndjson", body: lines({ state: "no_key" }) });
  });
  await page.goto("/");
  await ask(page, "When was it placed on sale?");
  const turn = newest(page);
  await expect(turn).toContainText(/Searching…|Buscando…/);            // the first seconds: nothing but "Searching"
  await expect(page.getByTestId("service-starting")).toHaveCount(0);   // said once, in the turn, not also by the box
  const waiting = turn.getByTestId("waiting");
  await expect(waiting).toContainText(/Waking the service…|Despertando el servicio…/, { timeout: 10_000 });
  await expect(waiting).toContainText(/takes about half a minute|tarda cerca de medio minuto/);
  const first = Number((await waiting.getByTestId("waiting-seconds").innerText()).replace(/\D/g, ""));
  expect(first).toBeGreaterThanOrEqual(3);
  await expect.poll(async () => Number((await waiting.getByTestId("waiting-seconds").innerText()).replace(/\D/g, "")), { timeout: 10_000 })
    .toBeGreaterThan(first);                                          // the count runs
  phase = "connecting";
  await expect(waiting).toContainText(/The service is awake\.|El servicio está despierto\./, { timeout: 15_000 });
  await expect(waiting).toContainText(/Connecting to the catalogue and the literature…|Conectando con el catálogo y la literatura…/);
  await expect(waiting).not.toContainText(/Waking the service…|Despertando el servicio…/);
  phase = "ready";
  await expect(waiting).toContainText(/Catalogue and literature connected\.|Catálogo y literatura conectados\./, { timeout: 15_000 });
  await expect(waiting).toContainText(/Searching…|Buscando…/);
  await expect(waiting).not.toContainText(/half a minute|medio minuto/);
  answer();
  await expect(turn.getByTestId("evidence-button")).toBeVisible();
  await expect(turn.getByTestId("waiting")).toHaveCount(0);
  await turn.getByTestId("evidence-button").click();
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("passage")).toHaveCount(2);
});

test("a question answered at once shows no waiting lines", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await ask(page, "A question?");
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
  await expect(page.getByTestId("waiting")).toHaveCount(0);
});

test("the human check, case 1: it starts when the box takes focus and passes before the question is sent; nothing about it is drawn", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.addInitScript(() => {
    // remember whether anything of the check was ever drawn
    new MutationObserver(() => {
      if (document.querySelector(".check__say, .check--waiting")) Object.assign(window, { __sawCheck: true });
    }).observe(document, { childList: true, subtree: true, attributes: true });
  });
  const sessions: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/chat")) sessions.push(request.headers()["x-oxcart-session"] ?? "");
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "A live example question?" })).toBeVisible();
  expect(await checks(page)).toEqual([]);                              // not at page load
  const traded = page.waitForRequest("**/api/session");
  await box(page).focus();
  await traded;                                                        // the token is traded at once
  expect(await checks(page)).toEqual([{ id: "w1", runs: 1, appearance: "interaction-only", inHost: true }]);
  await checkInReach(page);
  expect((await page.getByTestId("check-host").boundingBox())!.height).toBe(0);   // invisible, it takes no room
  await ask(page, "A question asked after the check passed?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  expect(await page.evaluate(() => Boolean((window as unknown as { __sawCheck?: boolean }).__sawCheck))).toBe(false);
  expect(sessions).toEqual(["test-session"]);
  // once per session: the next question asks no check either, and the widget is never drawn again
  await ask(page, "And the next one?");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
  expect(await checks(page)).toEqual([{ id: "w1", runs: 1, appearance: "interaction-only", inHost: true }]);
});

test("the human check's element is as tall as the box it holds, on the first screen and under a question", async ({ page }) => {
  await checkMode(page, "click");
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await box(page).focus();
  await expect(page.getByTestId("check-host").getByRole("button", { name: "Verify you are human" })).toBeVisible();
  const first = (await page.getByTestId("check-host").boundingBox())!;
  expect(Math.round(first.height)).toBe(65);            // the box is 65 px: no line's room above or under it
  await ask(page, "A question sent before the click?");
  await expect(page.getByTestId("check")).toContainText(/Waiting for the human check to finish|Esperando a que termine la comprobación/);
  const waiting = (await page.getByTestId("check-host").boundingBox())!;
  expect([Math.round(waiting.width), Math.round(waiting.height)]).toEqual([300, 65]);   // the room kept is the room taken
});

test("the human check, case 2: still running when the question is sent, it goes on; its words and room stand under the question", async ({ page }) => {
  await checkMode(page, "hold");
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await box(page).focus();
  await expect.poll(async () => (await checks(page)).length).toBe(1);
  const host = await page.getByTestId("check-host").elementHandle();
  await ask(page, "A question sent before the check passed?");
  const turn = newest(page);
  const check = page.getByTestId("check");
  await expect(check).toContainText(/A quick check that you are a person|Una comprobación rápida/);
  await expect(check).toContainText(/Waiting for the human check to finish|Esperando a que termine la comprobación/);
  const room = (await page.getByTestId("check-host").boundingBox())!;
  expect([Math.round(room.width), Math.round(room.height)]).toEqual([300, 65]);   // kept, so nothing moves when it comes or goes
  // under the question that waits, above the box
  expect(room.y).toBeGreaterThan((await turn.locator(".turn__text").boundingBox())!.y);
  expect(room.y + room.height).toBeLessThan((await box(page).boundingBox())!.y);
  await checkInReach(page);
  // the same element and the same widget, still running: it was not drawn again nor restarted
  expect(await page.getByTestId("check-host").evaluate((el, first) => el === first, host)).toBe(true);
  expect(await checks(page)).toEqual([{ id: "w1", runs: 1, appearance: "interaction-only", inHost: true }]);
  await settleCheck(page);
  await expect(turn.getByTestId("written-answer")).toBeVisible();
  await expect(check).not.toContainText(/A quick check/);
  expect((await page.getByTestId("check-host").boundingBox())!.height).toBe(0);
});

test("the human check, case 3: when it needs a click, the visitor sees it by the box, and under the question once it is sent", async ({ page }) => {
  await checkMode(page, "click");
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await box(page).focus();
  const click = page.getByRole("button", { name: "Verify you are human" });
  await expect(click).toBeVisible();                                   // on the first screen, under the box
  await expect(page.getByTestId("check")).toContainText(/A quick check that you are a person/);
  const first = (await page.getByTestId("check-host").boundingBox())!;
  expect(first.y).toBeGreaterThan((await box(page).boundingBox())!.y);
  await checkInReach(page);
  const host = await page.getByTestId("check-host").elementHandle();
  await ask(page, "A question whose check needs a click?");
  await expect(page.getByTestId("check")).toContainText(/Waiting for the human check to finish/);
  await expect(click).toBeVisible();
  await checkInReach(page);
  // the first screen gave way to the thread around it: the same element, the same widget
  expect(await page.getByTestId("check-host").evaluate((el, h) => el === h, host)).toBe(true);
  expect((await checks(page)).length).toBe(1);
  await click.click();
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(click).toBeHidden();
});

test("the human check's element is in the page and in reach, at every width", async ({ page }) => {
  await checkMode(page, "hold");
  await mock(page);
  for (const width of [360, 820, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await box(page).focus();
    await expect.poll(async () => (await checks(page)).length).toBe(1);
    await checkInReach(page);                                          // first screen
    await ask(page, "A question that waits for the check?");
    await expect(page.getByTestId("check")).toHaveClass(/check--waiting/);
    await checkInReach(page);                                          // a thread, waiting
    await settleCheck(page);
    await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
    await checkInReach(page);                                          // a thread, passed
    await deleteConversation(page);
    await page.evaluate(() => window.sessionStorage.clear());
  }
});

test("a human check that does not pass is said in the turn, and the question stays in the box", async ({ page }) => {
  await mock(page);
  await page.route("**/api/session", (route) => route.fulfill({ status: 403, json: { error: "human_check_failed", message: "The human check did not pass." } }));
  await page.goto("/");
  await ask(page, "A question that fails the check?");
  const turn = newest(page);
  await expect(turn.getByTestId("turn-error")).toContainText(/The human check did not pass|La comprobación no pasó/);
  await expect(box(page)).toHaveValue("A question that fails the check?");
  await expect(turn.getByTestId("evidence-button")).toHaveCount(0);
  // the one widget stays, and is run again when the question is sent again
  const before = (await checks(page))[0].runs;
  await box(page).press("Enter");
  await expect(newest(page).getByTestId("turn-error")).toBeVisible();
  await expect.poll(async () => (await checks(page))[0].runs).toBe(before + 1);
  expect((await checks(page)).length).toBe(1);
});

test("writing: 'What was found' opens the evidence before the answer, and becomes 'Evidence' when it arrives", async ({ page }) => {
  await mock(page);
  // the first line arrives, the second waits: a server that answers in two parts
  await page.addInitScript(() => {
    const original = window.fetch;
    window.fetch = async (input, init) => {
      if (!String(input).endsWith("/api/chat")) return original(input, init);
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode((window as unknown as { __first: string }).__first));
          (window as unknown as { __finish: () => void }).__finish = () => {
            controller.enqueue(encoder.encode((window as unknown as { __second: string }).__second));
            controller.close();
          };
        },
      });
      return new Response(stream, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
    };
  });
  await page.goto("/");
  const [first, second] = lines(WRITTEN).trim().split("\n");
  await page.evaluate(([a, b]) => Object.assign(window, { __first: a + "\n", __second: b + "\n" }), [first, second]);
  await ask(page, "When was it placed on sale?");
  const turn = newest(page);
  await expect(turn.getByTestId("writing")).toContainText(/Writing an answer|Redactando una respuesta/);
  const button = turn.getByTestId("evidence-button");
  await expect(button).toHaveText(/What was found|Lo que se encontró/);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(page.getByLabel(/Ask more about this|Pregunte más sobre esto/)).toHaveCount(0);   // no follow-up before the answer
  await button.click();
  await expect(page.getByRole("tab")).toHaveCount(3);                  // no sources yet
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("passage")).toHaveCount(2);    // the evidence is here
  await page.evaluate(() => (window as unknown as { __finish: () => void }).__finish());
  await expect(turn.getByTestId("written-answer")).toBeVisible();
  await expect(turn.getByTestId("writing")).toHaveCount(0);
  await expect(button).toHaveText(/^(Evidence|Evidencia)/);
  await expect(page.getByRole("tab")).toHaveCount(4);                  // the panel gains the answer's sources
});

test("the answer arrives whole: every sentence at once, nothing held back", async ({ page }) => {
  await mock(page, { written: LONG });
  await page.goto("/");
  await ask(page, "A question with a long answer?");
  const answer = newest(page).getByTestId("written-answer");
  await expect(answer).toBeVisible();
  await expect(answer.getByTestId("answer-sentence")).toHaveCount(4);
  for (const sentence of await answer.getByTestId("answer-sentence").all()) await expect(sentence).toBeVisible();
  await expect(answer.locator('[aria-hidden="true"]')).toHaveCount(0);
  await expect(answer.getByText("Answer · written by AI")).toBeVisible();
  // the reader follows the new turn: its answer starts in view, and the box stays at the foot
  await expect(answer.getByTestId("answer-sentence").first()).toBeInViewport();
  await expect(box(page)).toBeInViewport();
});

test("a question gets a written answer with its sources under it, each sentence with the sources it cites", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await ask(page, "When was it placed on sale?");
  const turn = newest(page);
  const answer = turn.getByTestId("written-answer");
  await expect(answer.getByTestId("answer-sentence")).toHaveCount(2);
  await expect(answer).toContainText("The test issue was placed on sale on 20 September 1889.");
  // the newest answer lists its sources, then its Evidence button
  await expect(answer.getByTestId("answer-source")).toHaveCount(2);
  await expect(answer.getByTestId("answer-source").first()).toContainText("Catalogue card: A test issue");
  const listBottom = (await answer.getByTestId("answer-source").last().boundingBox())!.y;
  expect(listBottom).toBeLessThan((await turn.getByTestId("evidence-button").boundingBox())!.y);
  // the AI note stands once, at the foot of the thread
  await expect(page.getByTestId("ai-note")).toHaveCount(1);
  await expect(page.getByTestId("ai-note")).toContainText(/Everything here is written by an AI model \(Claude\) from the sources shown with it|Todo lo que aparece aquí lo redacta un modelo de IA/);
  // a mark opens Evidence on Sources, at that source, with the text it was cited for
  await answer.getByTestId("answer-sentence").nth(1).getByRole("button", { name: /2/ }).click();
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  const source = panel(page).getByTestId("ev-source").nth(1);
  await expect(source).toBeFocused();
  await expect(source).toContainText("A TEST DOCUMENT, page 12");
  await expect(source).toContainText("A passage that answers the question.");
  // and it is kept with the conversation
  await page.reload();
  await expect(newest(page).getByTestId("written-answer")).toContainText("A test document says the same.");
});

// ===================================================================== the thread

test("the thread and the compact rule: older answers keep their text, marks and one button; the newest lists its sources", async ({ page }) => {
  await seed(page, THREAD);
  await mock(page);
  await page.goto("/");
  const turns = page.getByTestId("turn");
  await expect(turns).toHaveCount(4);
  // oldest first
  await expect(turns.first()).toContainText("When was the test issue placed on sale?");
  await expect(turns.last()).toContainText("Which documents mention it?");
  // every turn has its one way to its evidence
  for (const turn of await turns.all()) await expect(turn.getByTestId("evidence-button")).toHaveCount(1);
  // older answers: text and marks, no list of sources, the count of sources beside the button
  await expect(turns.nth(0).getByTestId("answer-source")).toHaveCount(0);
  await expect(turns.nth(0).getByTestId("source-mark")).toHaveCount(2);
  await expect(turns.nth(0).locator(".evrow__counts")).toHaveText(/^2 sources$/);
  await expect(turns.nth(1).locator(".evrow__counts")).toHaveText(/^1 source$/);
  await expect(turns.nth(1).getByTestId("searched-as")).toBeVisible();
  // an older turn with no written answer: its notice and "What was found"
  await expect(turns.nth(2).getByTestId("not-covered")).toBeVisible();
  await expect(turns.nth(2).getByTestId("evidence-button")).toHaveText(/What was found/);
  await expect(turns.nth(2).locator(".foundnames")).toHaveCount(0);
  // the newest: the full list of its sources above its button
  await expect(turns.nth(3).getByTestId("answer-source")).toHaveCount(2);
  await expect(turns.nth(3).locator(".evrow__counts")).toHaveText("2 sources · 2 catalogue cards · 2 passages");
  // above every answer the byline; the AI note once, after the last turn
  await expect(page.getByText("Answer · written by AI")).toHaveCount(3);
  await expect(page.getByTestId("ai-note")).toHaveCount(1);
  const noteTop = (await page.getByTestId("ai-note").boundingBox())!.y;
  expect(noteTop).toBeGreaterThan((await turns.last().boundingBox())!.y);
  // a follow-up typed now follows the newest answer
  await expect(page.getByLabel(/Ask more about this/)).toBeVisible();
});

test("an older answer's Evidence names its own question, and each answer keeps its own button", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await seed(page, THREAD);
  await mock(page);
  await page.goto("/");
  const first = page.getByTestId("turn").first();
  await first.getByTestId("evidence-button").click();
  await expect(page.getByTestId("evidence-question")).toHaveText("When was the test issue placed on sale?");
  await expect(first.getByTestId("evidence-button")).toHaveAttribute("aria-expanded", "true");
  await expect(newest(page).getByTestId("evidence-button")).toHaveAttribute("aria-expanded", "false");
  await newest(page).getByTestId("evidence-button").click();          // another answer's button moves the panel to it
  await expect(page.getByTestId("evidence-question")).toHaveText("Which documents mention it?");
  await expect(first.getByTestId("evidence-button")).toHaveAttribute("aria-expanded", "false");
  await newest(page).getByTestId("evidence-button").click();          // its own button closes it
  await expect(panel(page)).toHaveCount(0);
});

test("the conversation stays in this browser and can be deleted", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await ask(page, "First question?");
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();   // kept once it has its evidence
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page)).toContainText("First question?");
  const cookies = await page.context().cookies();
  expect(cookies).toHaveLength(0);                                   // local storage, not cookies
  const kept = JSON.parse((await page.evaluate(() => window.localStorage.getItem("oxcart-conversations")))!);
  expect(kept.version).toBe(2);
  expect(kept.conversations).toHaveLength(1);
  expect(kept.conversations[0].id).toBe(kept.current);
  expect(kept.conversations[0].turns[0].question).toBe("First question?");
  await deleteConversation(page);
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(0);
});

test("a conversation kept by the first version is carried over once, oldest turn first", async ({ page }) => {
  const old = [
    { id: "b", question: "The second question?", at: "2026-11-20T10:01:00.000Z", answer: ANSWER, written: WRITTEN },
    { id: "a", question: "The first question?", at: "2026-11-20T10:00:00.000Z", answer: ANSWER },
    { id: "c", question: "A question cut off before its evidence?", at: "2026-11-20T10:02:00.000Z", pending: true },
  ];
  await page.addInitScript((value) => {
    if (!window.sessionStorage.getItem("seeded")) {
      window.localStorage.setItem("oxcart-chat-v1", value);
      window.sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(old));
  await mock(page);
  await page.goto("/");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(page.getByTestId("turn").first()).toContainText("The first question?");
  await expect(newest(page).getByTestId("written-answer")).toContainText("The test issue was placed on sale");
  const keys = await page.evaluate(() => ({ old: window.localStorage.getItem("oxcart-chat-v1"), now: window.localStorage.getItem("oxcart-conversations") }));
  expect(keys.old).toBeNull();
  expect(JSON.parse(keys.now!).conversations[0].turns.map((t: { question: string }) => t.question)).toEqual(["The first question?", "The second question?"]);
});

test("storage blocked or full does not break the page", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("full", "QuotaExceededError");
    };
    Storage.prototype.getItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
  });
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await ask(page, "A question in a browser that keeps nothing?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await page.getByTestId("lang-toggle").click();
  await expect(page.getByTestId("privacy")).toContainText("Su pregunta");
});

test("a follow-up is sent with the turns it follows, and the page says what was searched", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await ask(page, "When was it placed on sale?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();

  const bodies: { question: string; thread: { question: string; answer: string }[] }[] = [];
  await page.unroute("**/api/chat");
  await page.route("**/api/chat", (route) => {
    bodies.push(route.request().postDataJSON());
    const evidence = { ...ANSWER, question: "Who printed the test issue?" };
    return route.fulfill({ contentType: "application/x-ndjson", body: lines({ state: "ok", sentences: [{ text: "A printer printed it.", cites: [1] }],
      sources: [{ n: 1, kind: "issue", index: 0, title: "Catalogue card: A test issue", quotes: ["printers: A printer"] }] }, evidence, true) });
  });
  const more = page.getByLabel(/Ask more about this|Pregunte más sobre esto/);
  await more.fill("And who printed it?");
  await more.press("Enter");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  const turn = newest(page);
  await expect(turn.getByTestId("searched-as")).toContainText("Who printed the test issue?");
  await expect(turn.getByTestId("written-answer")).toContainText("A printer printed it.");
  expect(bodies[0]).toEqual({
    question: "And who printed it?",
    thread: [{ question: "When was it placed on sale?", answer: "The test issue was placed on sale on 20 September 1889. A test document says the same." }],
  });
  // a second follow-up carries both turns
  await ask(page, "And the next one?");
  await expect(page.getByTestId("turn")).toHaveCount(3);
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  expect(bodies[1].thread.map((t) => t.question)).toEqual(["When was it placed on sale?", "Who printed the test issue?"]);
  // a new conversation starts again, with no thread
  await startNew(page);
  await ask(page, "Another subject?");
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
  expect(bodies[2].thread).toEqual([]);
});

test("a turn arriving with Evidence open: the panel stays on the answer it was opened for", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await seed(page, [THREAD[0]]);
  await mock(page);
  let answer: () => void = () => {};
  const held = new Promise<void>((resolve) => (answer = resolve));
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.fulfill({ contentType: "application/x-ndjson", body: lines(WRITTEN, { ...ANSWER, question: "And who printed the test issue?" }, true) });
  });
  await page.goto("/");
  const first = page.getByTestId("turn").first();
  await first.getByTestId("evidence-button").click();
  await expect(panel(page)).toHaveAttribute("role", "complementary");  // docked: the conversation stays usable
  await ask(page, "And who printed it?");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(newest(page).getByTestId("searching-bar")).toBeVisible();
  await expect(page.getByTestId("evidence-question")).toHaveText("When was the test issue placed on sale?");
  answer();
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(page.getByTestId("evidence-question")).toHaveText("When was the test issue placed on sale?");
  await expect(first.getByTestId("evidence-button")).toHaveAttribute("aria-expanded", "true");
  await expect(newest(page).getByTestId("evidence-button")).toHaveAttribute("aria-expanded", "false");
  await expect(newest(page).getByTestId("evidence-button")).toBeInViewport();   // the reader stays at the foot
  await noOverflow(page, "arriving, 1440");
});

// ===================================================================== no answer, refusals, failures

test("when no answer is written the turn says why in one line, and what was found is one step away", async ({ page }) => {
  await mock(page, { written: { state: "not_covered" } });
  await page.goto("/");
  await ask(page, "What is the capital of a made-up country?");
  const turn = newest(page);
  await expect(turn.getByTestId("not-covered")).toContainText(WEB_BUILD ? /do not answer this question/ : /does not answer this question|no responde esta pregunta/);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(turn.getByTestId("evidence-button")).toHaveText(/What was found/);
  await expect(turn.locator(".foundnames li")).toHaveCount(4);
  await expect(page.getByLabel("Your question")).toBeVisible();        // nothing to follow: the box asks a new question
  await turn.getByTestId("evidence-button").click();
  await expect(page.getByRole("tab")).toHaveCount(3);                  // not covered: three tabs
  await expect(page.getByTestId("tab-sources")).toHaveCount(0);
  await expect(panel(page).locator("#evp-label")).toHaveText("The evidence that was found");
  await page.getByTestId("tab-made").click();
  await expect(panel(page)).toContainText("The model judged that the evidence does not cover the question");
  await page.getByTestId("evidence-close").click();

  for (const [state, words] of [["daily_cap", /all its answers for today|todas sus respuestas de hoy/], ["timeout", /No answer could be written|no se pudo redactar/]] as const) {
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines({ state }) }));
    await ask(page, `A question that ends as ${state}?`);
    const next = newest(page);
    await expect(next).toContainText(`A question that ends as ${state}?`);
    await expect(next.getByTestId("no-written-answer")).toContainText(words);
    await expect(next.getByTestId("evidence-button")).toHaveText(/What was found/);
    await expect(next.getByTestId("turn-error")).toHaveCount(0);
  }
});

test("the minute's limit: one line, and the question stays in the box", async ({ page }) => {
  await mock(page, { askStatus: 429, ask: { error: "visitor_minute_limit", message: "Too many questions in a minute." } });
  await page.goto("/");
  await ask(page, "A question?");
  await expect(page.getByTestId("turn-error")).toContainText(/Too many questions|Demasiadas preguntas/);
  await expect(box(page)).toHaveValue("A question?");
  await expect(box(page)).toBeEnabled();
  await page.reload();                                                // a refusal is not kept
  await expect(page.getByTestId("turn")).toHaveCount(0);
});

test("the day's limit: one line, the question stays in the box, and the box is closed", async ({ page }) => {
  await seed(page, [THREAD[0]]);
  await mock(page, { chatStatus: 429, ask: { error: "visitor_daily_limit", message: "Daily limit." } });
  await page.goto("/");
  await ask(page, "And one more?");
  await expect(newest(page).getByTestId("turn-error")).toContainText(/today's limit of questions|límite de preguntas de hoy/);
  await expect(box(page)).toHaveValue("And one more?");
  await expect(box(page)).toBeDisabled();
  await expect(page.getByRole("button", { name: /^(Ask|Preguntar)$/ })).toBeDisabled();
});

test("a failed call: one line, and the question stays in the box", async ({ page }) => {
  await mock(page);
  await page.route("**/api/chat", (route) => route.abort());
  await page.goto("/");
  await ask(page, "A question to a service that is gone?");
  await expect(newest(page).getByTestId("turn-error")).toContainText(/could not be reached|No se pudo contactar/);
  await expect(box(page)).toHaveValue("A question to a service that is gone?");
  await expect(newest(page).getByTestId("evidence-button")).toHaveCount(0);
  // sent again, the failed turn gives way to the new one
  await page.unroute("**/api/chat");
  await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(WRITTEN) }));
  await box(page).press("Enter");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(page.getByTestId("turn")).toHaveCount(1);
});

test("a stored example opens as a conversation, and 'Ask it now' asks it live", async ({ page }) => {
  await mock(page, { stored: STORED, written: WRITTEN });
  await page.goto("/");
  await page.getByRole("button", { name: /A stored example question\?/ }).click();
  const stored = newest(page);
  await expect(stored.getByTestId("stored-tag")).toBeVisible();
  await expect(stored.getByTestId("stored-note")).toContainText("2026-11-19");
  await expect(stored.getByTestId("evidence-button")).toHaveText(/What was found/);
  const asked: string[] = [];
  page.on("request", (r) => r.url().endsWith("/api/chat") && asked.push(r.postDataJSON().question));
  await stored.getByTestId("ask-now").click();
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(newest(page).getByTestId("stored-tag")).toHaveCount(0);
  expect(asked).toEqual(["A stored example question?"]);
});

test("part of the evidence missing is said in the turn, and inside Evidence", async ({ page }) => {
  await mock(page, {
    ask: { ...ANSWER, mode: { embedding: "failed", catalogue: "unavailable", literature: "keyword" }, issues: [] },
    written: { state: "not_covered" },
  });
  await page.goto("/");
  await ask(page, "A question?");
  const turn = newest(page);
  await expect(turn.getByTestId("turn-catalogue-down")).toContainText(/catalogue could not be reached|No se pudo consultar el catálogo/);
  await expect(turn.getByTestId("turn-keyword")).toContainText(/Keyword mode|Modo de palabras clave/);
  await turn.getByTestId("evidence-button").click();
  await expect(panel(page)).toContainText(/catalogue could not be reached/);   // the graph tab has nothing to draw, and says why
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("catalogue-down")).toBeVisible();
  await expect(panel(page).getByTestId("passage")).toHaveCount(2);
  await page.getByTestId("tab-made").click();
  await expect(panel(page).getByTestId("mode-line")).toHaveAttribute("data-mode", "keyword");
});

test("a backend without the answer step still gives the evidence", async ({ page }) => {
  await mock(page, { chatStatus: 404 });
  await page.goto("/");
  await ask(page, "When was it placed on sale?");
  const turn = newest(page);
  await expect(turn.getByTestId("evidence-button")).toBeVisible();
  await expect(turn.getByTestId("turn-error")).toHaveCount(0);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(turn.getByTestId("no-written-answer")).toHaveCount(0);
  await turn.getByTestId("evidence-button").click();
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("passage")).toHaveCount(2);
});

// ===================================================================== Evidence, tab by tab

async function openNewest(page: Page, width = 1440) {
  await page.setViewportSize({ width, height: 900 });
  await seed(page, [THREAD[0]]);
  await mock(page);
  await page.goto("/");
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
}

test("Evidence, Graph: the answer, its sources, the cited card's printer, act and stamps, and apart what was not cited", async ({ page }) => {
  await openNewest(page);
  await expect(page.getByRole("tab")).toHaveCount(4);
  for (const [key, name] of [["graph", "Graph"], ["sources", "Sources"], ["found", "Cards and passages"], ["made", "How it was made"]]) {
    await expect(page.getByTestId(`tab-${key}`)).toHaveAccessibleName(name);   // in the drawn order
  }
  expect(await page.getByRole("tab").evaluateAll((all) => all.map((el) => el.getAttribute("data-testid")))).toEqual(["tab-graph", "tab-sources", "tab-found", "tab-made"]);
  await expect(page.getByTestId("tab-graph")).toHaveAttribute("aria-selected", "true");
  const drawing = panel(page).getByTestId("graph-drawing");
  await expect(drawing).toBeVisible();
  // the box takes its proportions from the data
  const ratio = await drawing.evaluate((el) => getComputedStyle(el).aspectRatio);
  expect(ratio).toMatch(/^640 \/ \d+$/);
  const nodes = panel(page).getByTestId("graph-node");
  const names = await nodes.evaluateAll((all) => all.map((n) => n.getAttribute("aria-label")));
  expect(names).toContain("Answer");
  expect(names).toContain("Source 1: A test issue (CR-TEST-ISSUE)");
  expect(names).toContain("Source 2: A TEST DOCUMENT, page 12");
  expect(names).toContain("A test issue, printed by: A printer");
  expect(names).toContain("A test issue, authorized by: Test decree 1, 2 January 1889");   // dates in words, no repeated word
  expect(names).toContain("Another test issue, authorized by: Act 7 (law), May 1890");
  expect(names).toContain("A test issue, stamp T1");
  expect(names).toContain("Found, not cited by the answer: Another test issue (CR-OTHER-TEST-ISSUE)");
  await expect(panel(page).locator(".g-node--found")).not.toHaveCount(0);
  // only a node that does something takes focus: the cited sources and the card found and not cited
  const acting = panel(page).locator("[data-testid=graph-node][tabindex='0']");
  expect(await acting.evaluateAll((all) => all.map((n) => n.getAttribute("aria-label")))).toEqual([
    "Source 1: A test issue (CR-TEST-ISSUE)",
    "Source 2: A TEST DOCUMENT, page 12",
    "Found, not cited by the answer: Another test issue (CR-OTHER-TEST-ISSUE)",
  ]);
  for (const node of await acting.all()) await expect(node).toHaveAttribute("role", "button");
  await expect(panel(page).locator(".g-node--stamp[tabindex], .g-node--leaf[tabindex], .g-node--answer[tabindex]")).toHaveCount(0);
  await expect(panel(page).locator(".g-node--stamp").first()).toHaveAttribute("role", "img");
  // Enter on a cited source opens Sources at it
  await acting.nth(1).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  await expect(panel(page).getByTestId("ev-source").nth(1)).toBeFocused();
  // a click on the card found and not cited opens it under Cards and passages
  await page.getByTestId("tab-graph").click();
  await panel(page).locator("[data-testid=graph-node][tabindex='0']").nth(2).click();
  await expect(page.getByTestId("tab-found")).toHaveAttribute("aria-selected", "true");
  const other = panel(page).getByTestId("card").nth(1);
  await expect(other).toHaveAttribute("open", "");
  await expect(other.locator("summary")).toBeFocused();
  await page.getByTestId("tab-graph").click();
  // the same as a list
  await panel(page).getByTestId("view-list").click();
  await expect(drawing).toBeHidden();
  await expect(panel(page).getByTestId("graph-list")).toContainText("A printer");
  await noOverflow(page, "graph, 1440");
});

test("Evidence, Graph on a phone: the list alone", async ({ page }) => {
  await openNewest(page, 360);
  await expect(panel(page).getByTestId("graph-list")).toBeVisible();
  await expect(panel(page).getByTestId("graph-drawing")).toBeHidden();
  await expect(panel(page).getByTestId("view-graph")).toBeHidden();
  // on a phone the sheet covers the screen
  const sheet = (await panel(page).boundingBox())!;
  expect(Math.round(sheet.width)).toBe(360);
  await noOverflow(page, "graph, 360");
});

test("Evidence, Sources: each source with the exact text it was cited for", async ({ page }) => {
  await openNewest(page);
  await page.getByTestId("tab-sources").click();
  const sources = panel(page).getByTestId("ev-source");
  await expect(sources).toHaveCount(2);
  await expect(sources.first()).toContainText("Catalogue card: A test issue");
  await expect(sources.first()).toContainText(/Cited for/i);
  await expect(sources.first().locator("blockquote")).toHaveText("placed on sale: 1889-09-20");
});

test("Evidence, Cards and passages: what the answer cites starts open, the rest folds", async ({ page }) => {
  await openNewest(page);
  await page.getByTestId("tab-found").click();
  const cards = panel(page).getByTestId("card");
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toHaveAttribute("open", "");
  // date names in the page's words; a name the list does not hold, as the data has it
  await expect(cards.first()).toContainText("Placed on sale: 20 September 1889");
  await expect(cards.first()).toContainText("Probable first circulation: 21 September 1889");
  await expect(cards.first()).toContainText("issued: September 1889");
  await expect(cards.first()).toContainText("withdrawn: about 1890");     // not a date: as it is
  await expect(cards.first()).toContainText("Test decree 1, 2 January 1889");
  await expect(cards.first().locator("table.stamps tbody tr")).toHaveCount(2);
  await expect(cards.nth(1)).not.toHaveAttribute("open", "");
  const passages = panel(page).getByTestId("passage");
  await expect(passages).toHaveCount(2);
  await expect(passages.first()).toHaveAttribute("open", "");
  await expect(passages.first()).toContainText("A TEST DOCUMENT");
  await expect(passages.first().locator(".mark")).toHaveText("2");
  await expect(passages.nth(1).locator(".mark")).toHaveCount(0);
});

test("Evidence, How it was made: the steps, the model call, the check of the citations and the raw scores", async ({ page }) => {
  await openNewest(page);
  await page.getByTestId("tab-made").click();
  const made = panel(page).getByTestId("ev-made");
  await expect(made.getByTestId("mode-line")).toHaveAttribute("data-mode", "vector");
  await expect(made).toContainText("4321");                          // the write call's input tokens
  await expect(made).toContainText("1.25");
  await expect(made).toContainText(/sentences written\s*3/);
  await expect(made).toContainText(/removed for having no citation that holds\s*1/);
  await expect(made).toContainText("900 ms");
  await expect(made).toContainText("2.1235");                         // an issue score, to four decimals
  await expect(made).toContainText(/not a percent/);
});

test("Evidence by keyboard: the tab list moves with the arrows, Home and End", async ({ page }) => {
  await openNewest(page);
  const graph = page.getByTestId("tab-graph");
  await expect(graph).toBeFocused();                                  // opening moves focus to the tab shown
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("tab-sources")).toBeFocused();
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  await expect(panel(page).getByTestId("ev-sources")).toBeVisible();
  await page.keyboard.press("End");
  await expect(page.getByTestId("tab-made")).toBeFocused();
  await expect(page.getByTestId("tab-made")).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(graph).toBeFocused();
  await page.keyboard.press("ArrowLeft");                             // it wraps
  await expect(page.getByTestId("tab-made")).toBeFocused();
  await expect(page.getByTestId("tab-graph")).toHaveAttribute("tabindex", "-1");
  await expect(page.getByTestId("tab-made")).toHaveAttribute("aria-controls", "ev-panel-made");
});

test("Evidence as a sheet: focus stays inside, Esc closes it, and focus returns to the button", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 900 });
  await seed(page, [THREAD[0]]);
  await mock(page);
  await page.goto("/");
  const button = newest(page).getByTestId("evidence-button");
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(button).toHaveAttribute("aria-controls", "evidence-panel");
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(panel(page)).toHaveAttribute("role", "dialog");
  await expect(panel(page)).toHaveAttribute("aria-modal", "true");
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByTestId("tab-graph")).toBeFocused();
  // backwards past the first control, forwards past the last, and on through the panel
  const keys = ["Shift+Tab", "Shift+Tab", "Tab", ...Array(25).fill("Tab"), ...Array(5).fill("Shift+Tab")];
  for (const key of keys) {
    await page.keyboard.press(key);
    expect(await page.evaluate(() => document.getElementById("evidence-panel")?.contains(document.activeElement)), key).toBe(true);
  }
  await page.getByTestId("evidence-close").focus();
  await page.keyboard.press("Shift+Tab");                             // from the first control, round to the last
  expect(await page.evaluate(() => document.activeElement?.getAttribute("data-testid"))).not.toBe("evidence-close");
  expect(await page.evaluate(() => document.getElementById("evidence-panel")?.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(panel(page)).toHaveCount(0);
  await expect(button).toBeFocused();
  await expect(button).toHaveAttribute("aria-expanded", "false");
});

test("a source mark opens Evidence on Sources at that source, and focus returns to the mark", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 900 });
  await seed(page, [{ question: "Which documents mention it?", written: LONG }]);
  await mock(page);
  await page.goto("/");
  const mark = newest(page).getByTestId("answer-sentence").nth(1).getByRole("button", { name: "Source 1" });
  await mark.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  const target = panel(page).getByTestId("ev-source").first();
  await expect(target).toBeFocused();
  await expect(target).toBeInViewport();
  await page.keyboard.press("Escape");
  await expect(mark).toBeFocused();
});

// ===================================================================== the page's shape

test("a source mark never starts a line: it shares a line box with the last word of its sentence", async ({ page }) => {
  await seed(page, [{ question: "Which documents mention it?", written: LONG }, { question: "And again?", written: LONG }]);
  await mock(page);
  for (const width of [360, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("source-mark").first()).toBeVisible();
    const report = await page.evaluate(() => {
      const bad: string[] = [];
      let checked = 0;
      document.querySelectorAll(".a__text .keep").forEach((keep) => {
        const word = keep.firstChild as Text;
        const range = document.createRange();
        range.setStart(word, word.length - 1);
        range.setEnd(word, word.length);
        const last = range.getBoundingClientRect();
        keep.querySelectorAll(".mark").forEach((mark) => {
          checked += 1;
          const box = mark.getBoundingClientRect();
          if (!(box.top < last.bottom && box.bottom > last.top)) bad.push(`${word.data} / ${mark.textContent}`);
        });
      });
      return { bad, checked };
    });
    expect(report.checked, `${width}: marks checked`).toBeGreaterThanOrEqual(14);
    expect(report.bad, `${width}`).toEqual([]);
    await noOverflow(page, `marks, ${width}`);
  }
});

test("no horizontal overflow: first screen, thread and each Evidence tab, at 360, 820, 1280 and 1440 px", async ({ page }) => {
  test.setTimeout(90_000);
  await mock(page, { stored: STORED });
  for (const width of [360, 820, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByRole("button", { name: /A stored example question\?/ })).toBeVisible();
    await noOverflow(page, `first screen, ${width}`);
  }
  await seed(page, THREAD);
  for (const width of [360, 820, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("turn")).toHaveCount(4);
    await noOverflow(page, `thread, ${width}`);
    await newest(page).getByTestId("evidence-button").click();
    for (const tab of ["graph", "sources", "found", "made"]) {
      await page.getByTestId(`tab-${tab}`).click();
      await expect(panel(page).getByTestId(`ev-${tab}`)).toBeVisible();
      // unfold everything, so the longest content is measured
      await panel(page).locator("details:not([open]) > summary").evaluateAll((all) => all.forEach((s) => (s as HTMLElement).click()));
      await noOverflow(page, `${tab}, ${width}`);
    }
    await page.getByTestId("evidence-close").click();
  }
});

test("screenshots of the main states at 360, 820 and 1440 px (kept under test-results, not committed)", async ({ page }) => {
  test.setTimeout(180_000);
  const shot = (name: string, width: number) => page.screenshot({ path: `test-results/screens/${name}-${width}.png` });
  for (const width of [360, 820, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.unrouteAll();
    await mock(page, { stored: STORED, written: WRITTEN });
    await page.goto("/");
    await page.evaluate(() => window.localStorage.removeItem("oxcart-conversations"));   // the last width's conversations
    await page.reload();
    await expect(page.getByRole("button", { name: /A stored example question\?/ })).toBeVisible();
    await shot("01-first", width);
    await page.getByTestId("privacy").getByText("Details").click();
    await shot("02-first-privacy-open", width);
    await ask(page, "When was the test issue placed on sale?");
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    await shot("03-answer", width);
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines(LONG, ANSWER, true) }));
    await ask(page, "And which documents mention it?");
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(newest(page).getByTestId("written-answer")).toBeVisible();
    await shot("04-thread", width);
    await newest(page).getByTestId("evidence-button").click();
    for (const tab of ["graph", "sources", "found", "made"]) {
      await page.getByTestId(`tab-${tab}`).click();
      await shot(`05-evidence-${tab}`, width);
    }
    await page.getByTestId("evidence-close").click();
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines({ state: "not_covered" }) }));
    await ask(page, "What is the best glue for a test album?");
    await expect(newest(page).getByTestId("not-covered")).toBeVisible();
    await shot("06-not-covered", width);
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => route.fulfill({ status: 429, json: { error: "visitor_minute_limit" } }));
    await ask(page, "One more question?");
    await expect(newest(page).getByTestId("turn-error")).toBeVisible();
    await shot("07-limit-minute", width);
    await startNew(page);
    await page.getByRole("button", { name: /A stored example question\?/ }).click();
    await expect(newest(page).getByTestId("stored-note")).toBeVisible();
    await shot("08-stored-example", width);
  }
});

/** The question page loads no graph library: the answer's graph is plain SVG. */
test("the question page does not load Cytoscape", async ({ page }) => {
  const scripts: string[] = [];
  page.on("response", async (response) => {
    if (response.url().endsWith(".js")) scripts.push(await response.text().catch(() => ""));
  });
  await mock(page);
  await page.goto("/");
  await expect(box(page)).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(scripts.length).toBeGreaterThan(0);
  expect(scripts.some((s) => s.includes("cytoscape"))).toBe(false);
});


test("docked Evidence keeps its head's room under the site header, with a short thread and with a long one scrolled", async ({ page }) => {
  const gap = (p: Page) => p.evaluate(() => {
    const header = document.querySelector("header.masthead")!.getBoundingClientRect();
    const head = document.getElementById("evp-label")!.getBoundingClientRect();
    return Math.round(head.top - header.bottom);
  });
  const open = async (p: Page, turns: SeedTurn[]) => {
    await p.setViewportSize({ width: 1440, height: 900 });
    await seed(p, turns);
    await mock(p);
    await p.goto("/");
    await expect(p.getByTestId("turn")).toHaveCount(turns.length);
    await newest(p).getByTestId("evidence-button").click();
    await expect(panel(p)).toBeVisible();
  };
  await open(page, [THREAD[0]]);
  const short = await gap(page);
  const long = await page.context().newPage();                        // another tab: its own seed
  await open(long, [...THREAD, ...THREAD, ...THREAD]);
  const gaps: number[] = [];
  for (const y of [0, 600, 1_000_000]) {                               // the top, the middle, the very foot
    await long.evaluate((top) => window.scrollTo(0, top), y);
    await long.waitForTimeout(100);
    gaps.push(await gap(long));
  }
  expect(short).toBeGreaterThanOrEqual(12);                           // the bar's own top padding, under the header
  expect(gaps).toEqual([short, short, short]);
});

test("dates the page builds from card data are written in words, in the visitor's language", () => {
  expect(formatDate("1889-09-14", "en")).toBe("14 September 1889");
  expect(formatDate("1889-09-14", "es")).toBe("14 de septiembre de 1889");
  expect(formatDate("1889-09", "en")).toBe("September 1889");
  expect(formatDate("1889-09", "es")).toBe("septiembre de 1889");
  expect(formatDate("1889-01-02", "en")).toBe("2 January 1889");
  for (const value of ["1889", "about 1890", "1889-13-01", "1889-02-40", "14/09/1889", ""]) {
    expect(formatDate(value, "en")).toBe(value);                        // not a date: as it is
  }
});

test("in Spanish, the sources are named in Spanish from their evidence, and Evidence speaks Spanish", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => window.localStorage.setItem("oxcart-lang", "es"));
  const english = {
    ...WRITTEN,
    sentences: [...WRITTEN.sentences, { text: "Una frase de prueba.", cites: [3] }],
    sources: [...WRITTEN.sources, { n: 3, kind: "passage", index: 9, title: "AN ENGLISH TITLE, page 1", quotes: [] }],
  };
  await mock(page, { written: english });
  await page.goto("/");
  await ask(page, "¿Cuándo se puso a la venta?");
  const sources = newest(page).getByTestId("answer-source");
  // the third points at evidence that is not there: the backend's own title stands
  await expect(sources).toHaveText(["1Ficha del catálogo: A test issue", "2A TEST DOCUMENT, página 12", "3AN ENGLISH TITLE, page 1"]);
  await newest(page).getByTestId("evidence-button").click();
  await page.getByTestId("tab-sources").click();
  await expect(panel(page).getByTestId("ev-source").nth(1)).toContainText("A TEST DOCUMENT, página 12");
  await expect(panel(page).getByTestId("ev-source").first()).toContainText("Texto citado");
  await page.getByTestId("tab-found").click();
  await expect(panel(page).getByTestId("card").first()).toContainText("Puesta a la venta: 20 de septiembre de 1889");
  await expect(panel(page).getByTestId("card").first()).toContainText("Primera circulación probable: 21 de septiembre de 1889");
  await expect(panel(page).getByTestId("card").first()).toContainText("issued: septiembre de 1889");
  await expect(panel(page).getByTestId("card").first()).toContainText("Test decree 1, 2 de enero de 1889");
  await page.getByTestId("tab-made").click();
  await expect(panel(page)).toContainText("Cómo se encontró cada emisión");
  await expect(panel(page)).toContainText("Son puntuaciones brutas de coincidencia. No son un porcentaje ni una medida de confianza.");
});

// ===================================================================== nothing focused under the pinned box

/** Where the focused element stands against the window and the box pinned at the foot (the form on a phone, the dock from 720 px). */
async function focusedClear(page: Page) {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    const dock = document.querySelector<HTMLElement>(".dock")!;
    const box = (getComputedStyle(dock).display === "contents" ? document.querySelector<HTMLElement>("form.composer")! : dock).getBoundingClientRect();
    if (!el || !el.closest(".conv") || el.closest(".dock, form.composer")) return { inThread: false, ok: true, what: el?.tagName ?? "" };
    const r = el.getBoundingClientRect();
    const inWindow = r.top >= 0 && r.bottom <= window.innerHeight;
    const clearOfBox = r.bottom <= box.top || r.top >= box.bottom;
    return { inThread: true, ok: inWindow && clearOfBox, what: `${el.tagName}.${el.className} ${el.textContent?.slice(0, 30)} ${Math.round(r.top)}-${Math.round(r.bottom)} box ${Math.round(box.top)}` };
  });
}

for (const width of [360, 820]) {
  test(`focus never lands under the pinned box, tabbing through a thread both ways, at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await seed(page, THREAD);
    await mock(page);
    await page.goto("/");
    await expect(page.getByTestId("turn")).toHaveCount(4);
    // forwards from the top of the thread to the box, then back up
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.locator(".turn__text").first().evaluate((el) => {
      el.setAttribute("tabindex", "-1");
      (el as HTMLElement).focus();
    });
    const seen: string[] = [];
    for (const key of [...Array(40).fill("Tab"), ...Array(40).fill("Shift+Tab")]) {
      await page.keyboard.press(key);
      await page.waitForTimeout(30);
      const where = await focusedClear(page);
      if (where.inThread) seen.push(where.what);
      expect(where.ok, `${key}: ${where.what}`).toBe(true);
    }
    expect(seen.some((s) => s.startsWith("BUTTON.evbtn"))).toBe(true);
    expect(seen.some((s) => s.startsWith("BUTTON.mark"))).toBe(true);
    expect(seen.some((s) => s.includes("Delete this conversation"))).toBe(true);
  });
}
