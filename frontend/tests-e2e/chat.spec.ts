import { test, expect, Page } from "@playwright/test";

/*
 * The chat page, with the backend's answers mocked in the browser. No live backend,
 * no human-check widget (no site key in the test build), no network.
 */

const ANSWER = {
  question: "When was it placed on sale?",
  mode: { embedding: "ok", catalogue: "vector index", literature: "vector" },
  issues: [
    {
      issue_id: "CR-TEST-ISSUE",
      title: "A test issue",
      score: 4,
      matched_by: ["vector", "year"],
      card: { dates: { placed_on_sale: "1889-09-20" }, printers: ["A printer"], stamps: [{ catalog_no: "1", value: 5, unit: "c", color: "blue" }] },
    },
  ],
  passages: [
    { doc_id: "A TEST DOCUMENT", page: 12, chunk_type: "text", text: "A passage that answers the question.", clipped: true, score: 0.9 },
    { doc_id: "ANOTHER DOCUMENT", page: 3, chunk_type: "text", text: "A second passage.", clipped: false, score: 0.8 },
  ],
  timings: { total_ms: 900 },
};

const STORED = {
  generated: "2026-11-19",
  examples: [{ lang: "en", question: "A stored example question?", answer: { ...ANSWER, question: "A stored example question?" } }],
};

/* A written answer for ANSWER: two sentences, the first cites the card, the second the first passage. */
const WRITTEN = {
  state: "ok",
  sentences: [
    { text: "The test issue was placed on sale on 20 September 1889.", cites: [1] },
    { text: "A test document says the same.", cites: [2] },
  ],
  sources: [
    { n: 1, kind: "issue", index: 0, title: "Catalogue card: A test issue", quotes: ["placed on sale: 1889-09-20"] },
    { n: 2, kind: "passage", index: 0, title: "A TEST DOCUMENT, page 12", quotes: ["A passage that answers the question."] },
  ],
};

/** The chat route's answer: lines of JSON, the evidence and then the written answer. */
const lines = (written: object, evidence: object = ANSWER, rewritten = false) =>
  [{ type: "evidence", rewritten, evidence }, { type: "answer", answer: written, calls: [] }].map((line) => JSON.stringify(line)).join("\n") + "\n";

type Mock = { health?: number; ask?: object; askStatus?: number; stored?: object | null; written?: object; chatStatus?: number };

async function mock(page: Page, options: Mock = {}) {
  await page.route("**/api/health", (route) =>
    options.health === 0 ? route.abort() : route.fulfill({ status: options.health ?? 200, json: { status: "ok" } }));
  await page.route("**/api/ask/examples", (route) =>
    route.fulfill({ json: { examples: [{ lang: "en", question: "A live example question?" }], max_question_chars: 300 } }));
  await page.route("**/stored-examples.json", (route) =>
    options.stored === null ? route.fulfill({ status: 404, body: "" }) : route.fulfill({ json: options.stored ?? { generated: null, examples: [] } }));
  await page.route("**/api/ask", (route) =>
    route.fulfill({ status: options.askStatus ?? 200, json: options.ask ?? ANSWER, headers: options.askStatus === 429 ? { "Retry-After": "30" } : {} }));
  // the route that also writes an answer. By default no answer is written (no key), so the
  // tests about the evidence see what they saw before there was a written answer
  await page.route("**/api/chat", (route) => {
    const status = options.chatStatus ?? options.askStatus ?? 200;
    if (status !== 200) return route.fulfill({ status, json: options.ask ?? { error: "not_found" }, headers: status === 429 ? { "Retry-After": "30" } : {} });
    return route.fulfill({ contentType: "application/x-ndjson", body: lines(options.written ?? { state: "no_key" }, options.ask ?? ANSWER) });
  });
}

test("the site opens directly on the question box", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByLabel(/Your question|Su pregunta/)).toBeVisible();
  await expect(page.locator("header.masthead")).toContainText("Oxcart");
  await expect(page.getByTestId("demo-tag")).toBeVisible();
  await expect(page.getByRole("button", { name: "A live example question?" })).toBeVisible();
});

test("a question shows the catalogue issue, the passages and the mode that answered", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("When was it placed on sale?");
  await page.getByRole("button", { name: /^(Ask|Preguntar)$/ }).click();
  const turn = page.getByTestId("turn").first();
  await expect(turn).toContainText("When was it placed on sale?");
  await expect(turn.getByTestId("mode-line")).toHaveAttribute("data-mode", "vector");
  await expect(turn.getByTestId("mode-line")).toContainText(/Searched by meaning|Búsqueda por significado/);
  await expect(turn).toContainText("A test issue");
  await expect(turn).toContainText("1889-09-20");
  await expect(turn.getByTestId("passage")).toHaveCount(2);
  await expect(turn.getByTestId("passage").first()).toContainText("A TEST DOCUMENT");
  await expect(turn.getByTestId("stored-tag")).toHaveCount(0);
});

test("the conversation stays in this browser and can be cleared", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("First question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  await expect(page.getByTestId("turn")).toHaveCount(1);
  // wait for the evidence: a turn is kept once it has its answer, not while it is pending
  await expect(page.getByTestId("turn").first().getByTestId("mode-line")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(page.getByTestId("turn").first()).toContainText("First question?");
  const cookies = await page.context().cookies();
  expect(cookies).toHaveLength(0);                                   // local storage, not cookies
  expect(await page.evaluate(() => window.localStorage.getItem("oxcart-chat-v1"))).toContain("First question?");
  await page.getByTestId("clear").click();
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(0);
});

test("stored examples show real evidence while the service is not answering, marked as stored", async ({ page }) => {
  await mock(page, { health: 0, stored: STORED });
  await page.goto("/");
  await expect(page.getByTestId("service-starting")).toContainText(/Waking the service…|Despertando el servicio…/, { timeout: 15_000 });
  await expect(page.getByTestId("service-starting")).toContainText(/stored examples below work meanwhile|funcionan los ejemplos guardados/);
  await page.getByRole("button", { name: /A stored example question\?/ }).click();
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("stored-tag")).toBeVisible();
  await expect(turn.getByTestId("stored-note")).toContainText("2026-11-19");
  await expect(turn.getByTestId("mode-line")).toHaveAttribute("data-mode", "vector");
  await expect(turn.getByTestId("passage")).toHaveCount(2);
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
  await page.getByLabel(/Your question|Su pregunta/).fill("When was it placed on sale?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn).toContainText(/Searching…|Buscando…/);            // the first seconds: nothing but "Searching"
  await expect(page.getByTestId("service-starting")).toHaveCount(0);   // said once, in the turn, not also above the box
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
  await expect(turn.getByTestId("mode-line")).toBeVisible();
  await expect(turn.getByTestId("waiting")).toHaveCount(0);
  await expect(turn.getByTestId("passage")).toHaveCount(2);
});

test("a question answered at once shows no waiting lines", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("A question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  await expect(page.getByTestId("turn").first().getByTestId("mode-line")).toBeVisible();
  await expect(page.getByTestId("waiting")).toHaveCount(0);
});

test("keyword mode and an unreachable catalogue are said on the page", async ({ page }) => {
  await mock(page, {
    ask: { ...ANSWER, mode: { embedding: "failed", catalogue: "unavailable", literature: "keyword" }, issues: [] },
  });
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("A question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("mode-line")).toHaveAttribute("data-mode", "keyword");
  await expect(turn.getByTestId("mode-line")).toContainText(/Keyword mode|Modo de palabras clave/);
  await expect(turn.getByTestId("catalogue-down")).toBeVisible();
  await expect(turn.getByTestId("passage")).toHaveCount(2);
});

test("a refusal is shown in words a visitor can read, and is not kept", async ({ page }) => {
  await mock(page, { askStatus: 429, ask: { error: "visitor_minute_limit", message: "Too many questions in a minute." } });
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("A question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  await expect(page.getByTestId("turn-error")).toContainText(/Too many questions|Demasiadas preguntas/);
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(0);
});

test("the list of questions to try folds away once there is a question, so its evidence is in view", async ({ page }) => {
  const many = Array.from({ length: 8 }, (_, i) => ({ lang: "en", question: `Example question number ${i + 1}?` }));
  await mock(page);
  await page.route("**/api/ask/examples", (route) => route.fulfill({ json: { examples: many, max_question_chars: 300 } }));
  await page.goto("/");
  const toggle = page.getByTestId("examples-toggle");
  const examples = page.getByRole("button", { name: /Example question number/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(examples).toHaveCount(8);
  await page.getByLabel(/Your question|Su pregunta/).fill("A typed question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("mode-line")).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toContainText("(8)");
  await expect(examples).toHaveCount(0);
  await expect(turn.locator(".chat__question")).toBeInViewport();     // not below a list any more
  await toggle.click();                                               // the visitor can open it again
  await expect(examples).toHaveCount(8);
  await examples.first().click();                                     // a new question folds it again
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.reload();                                                // a conversation found on opening: folded
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.getByTestId("clear").click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(examples).toHaveCount(8);
});

test("a question that is being searched shows it in view at once, on a small screen too", async ({ page }) => {
  let answer: () => void = () => {};
  const held = new Promise<void>((resolve) => (answer = resolve));
  const many = Array.from({ length: 8 }, (_, i) => ({ lang: "en", question: `Example question number ${i + 1}?` }));
  await page.setViewportSize({ width: 390, height: 700 });
  await mock(page);
  await page.route("**/api/ask/examples", (route) => route.fulfill({ json: { examples: many, max_question_chars: 300 } }));
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.fulfill({ contentType: "application/x-ndjson", body: lines({ state: "no_key" }) });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Example question number/ })).toHaveCount(8);
  await page.getByLabel(/Your question|Su pregunta/).fill("A typed question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("searching-bar")).toBeInViewport();
  await expect(turn).toContainText(/Searching…|Buscando…/);
  answer();
  await expect(turn.getByTestId("mode-line")).toBeVisible();
  await expect(turn.getByTestId("searching-bar")).toHaveCount(0);
});

test("a passage keeps its line breaks, and one that is only a figure says so", async ({ page }) => {
  const passages = [
    { doc_id: "A TEST DOCUMENT", page: 12, chunk_type: "text", text: "A first line.\nA second line.", clipped: false, score: 0.9 },
    { doc_id: "ANOTHER DOCUMENT", page: 3, chunk_type: "text", text: "", clipped: false, score: 0.8 },
  ];
  await mock(page, { ask: { ...ANSWER, passages } });
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("A typed question?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const shown = page.getByTestId("turn").first().getByTestId("passage");
  await expect(shown).toHaveCount(2);
  await expect(shown.nth(0).locator(".evi-card__text")).toHaveCSS("white-space", "pre-wrap");
  await expect(shown.nth(0).locator(".evi-card__text")).toHaveCSS("max-height", "none");   // clipped by the server, not cut by the card
  expect(await shown.nth(0).locator(".evi-card__text").innerText()).toBe("A first line.\nA second line.");
  await expect(shown.nth(1).getByTestId("passage-no-text")).toHaveText(/figure on the page|figura de la página/);
  await expect(shown.nth(1).locator(".evi-card__text")).toHaveCount(0);
});

test("the page speaks Spanish and English", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  const toggle = page.getByTestId("lang-toggle");
  const before = await page.locator("h1").first().innerText();
  await toggle.click();
  await expect(page.locator("h1").first()).not.toHaveText(before);
  await page.reload();
  await expect(page.locator("h1").first()).not.toHaveText(before);   // the choice is remembered
});

test("a question gets a written answer above the evidence, each sentence with the sources it cites", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("When was it placed on sale?");
  await page.getByRole("button", { name: /^(Ask|Preguntar)$/ }).click();
  const turn = page.getByTestId("turn").first();
  const answer = turn.getByTestId("written-answer");
  await expect(answer.getByTestId("answer-sentence")).toHaveCount(2);
  await expect(answer).toContainText("The test issue was placed on sale on 20 September 1889.");
  await expect(answer).toContainText(/Written by an AI model|Redactada por un modelo de IA/);
  // each source names the card or passage and shows the text it was cited for
  await expect(answer.getByTestId("answer-source")).toHaveCount(2);
  await expect(answer.getByTestId("answer-source").first()).toContainText("placed on sale: 1889-09-20");
  // a number leads to the cited card, which carries the same number
  const mark = answer.getByTestId("answer-sentence").nth(1).getByRole("link", { name: /2/ });
  const target = (await mark.getAttribute("href"))!.slice(1);
  await expect(page.locator(`[id="${target}"]`)).toContainText("A TEST DOCUMENT");
  await expect(page.locator(`[id="${target}"]`)).toContainText("[2]");
  await expect(turn.getByTestId("passage").nth(1)).not.toContainText("[");
  // the answer is above the evidence
  const answerTop = (await answer.boundingBox())!.y;
  const evidenceTop = (await turn.getByTestId("mode-line").boundingBox())!.y;
  expect(answerTop).toBeLessThan(evidenceTop);
  // and it is kept with the conversation
  await page.reload();
  await expect(page.getByTestId("turn").first().getByTestId("written-answer")).toContainText("A test document says the same.");
});

test("the evidence is shown while the answer is still being written", async ({ page }) => {
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
  await page.getByLabel(/Your question|Su pregunta/).fill("When was it placed on sale?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("passage")).toHaveCount(2);                       // the evidence is here
  await expect(turn.getByTestId("writing")).toContainText(/Writing an answer|Redactando una respuesta/);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(turn.getByTestId("follow-up")).toHaveCount(0);                     // no follow-up before the answer
  await page.evaluate(() => (window as unknown as { __finish: () => void }).__finish());
  await expect(turn.getByTestId("written-answer")).toBeVisible();
  await expect(turn.getByTestId("writing")).toHaveCount(0);
});

test("when no answer is written the page says why in one line and shows the evidence", async ({ page }) => {
  await mock(page, { written: { state: "not_covered" } });
  await page.goto("/");
  const box = page.getByLabel(/Your question|Su pregunta/);
  await box.fill("What is the capital of France?");
  await box.press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("not-covered")).toContainText(/does not answer this question|no responde esta pregunta/);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(turn.getByTestId("passage")).toHaveCount(2);

  for (const [state, words] of [["daily_cap", /all its answers for today|todas sus respuestas de hoy/], ["timeout", /No answer could be written|no se pudo redactar/]] as const) {
    await page.unroute("**/api/chat");
    await page.route("**/api/chat", (route) => route.fulfill({ contentType: "application/x-ndjson", body: lines({ state }) }));
    await box.fill(`A question that ends as ${state}?`);
    await box.press("Enter");
    const next = page.getByTestId("turn").first();
    await expect(next).toContainText(`A question that ends as ${state}?`);
    await expect(next.getByTestId("no-written-answer")).toContainText(words);
    await expect(next.getByTestId("passage")).toHaveCount(2);
    await expect(next.getByTestId("turn-error")).toHaveCount(0);
  }
});

test("a follow-up is sent with the turn it follows, and the page says what was searched", async ({ page }) => {
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  const box = page.getByLabel(/Your question|Su pregunta/);
  await box.fill("When was it placed on sale?");
  await box.press("Enter");
  await expect(page.getByTestId("turn").first().getByTestId("written-answer")).toBeVisible();

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
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("follows")).toContainText("When was it placed on sale?");
  await expect(turn.getByTestId("searched-as")).toContainText("Who printed the test issue?");
  await expect(turn.getByTestId("written-answer")).toContainText("A printer printed it.");
  expect(bodies[0]).toEqual({
    question: "And who printed it?",
    thread: [{ question: "When was it placed on sale?", answer: "The test issue was placed on sale on 20 September 1889. A test document says the same." }],
  });
  // only the newest turn has the box, and a second follow-up carries both turns
  await expect(page.getByTestId("follow-up")).toHaveCount(1);
  await page.getByLabel(/Ask more about this|Pregunte más sobre esto/).fill("And the next one?");
  await page.getByLabel(/Ask more about this|Pregunte más sobre esto/).press("Enter");
  await expect(page.getByTestId("turn")).toHaveCount(3);
  expect(bodies[1].thread.map((t) => t.question)).toEqual(["When was it placed on sale?", "Who printed the test issue?"]);
  // a question typed in the main box starts again, with no thread
  await box.fill("Another subject?");
  await box.press("Enter");
  await expect(page.getByTestId("turn")).toHaveCount(4);
  expect(bodies[2].thread).toEqual([]);
});

test("a backend without the answer step still gives the evidence", async ({ page }) => {
  await mock(page, { chatStatus: 404 });
  await page.goto("/");
  await page.getByLabel(/Your question|Su pregunta/).fill("When was it placed on sale?");
  await page.getByLabel(/Your question|Su pregunta/).press("Enter");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("passage")).toHaveCount(2);
  await expect(turn.getByTestId("turn-error")).toHaveCount(0);
  await expect(turn.getByTestId("written-answer")).toHaveCount(0);
  await expect(turn.getByTestId("no-written-answer")).toHaveCount(0);
});
