import { test, expect, Page } from "@playwright/test";

/*
 * The question page, with the backend's answers mocked in the browser. No live backend,
 * no network, no window: Chromium runs headless. Every fixture is made up.
 *
 * The human check needs a site key, and the test build has none: the tests that cover it
 * set `window.__OXCART_TEST_TURNSTILE_KEY__` and stub `window.turnstile` before the page
 * loads (see `stubHumanCheck`), so Cloudflare's script is never fetched.
 */

const ISSUE = {
  issue_id: "CR-TEST-ISSUE",
  title: "A test issue",
  score: 4,
  matched_by: ["vector", "year"],
  card: {
    dates: { placed_on_sale: "1889-09-20" },
    printers: ["A printer"],
    perforation: "12",
    acts: [{ type: "decree", id: "Test decree 1", date: "1889-01-02" }],
    stamps: [
      { catalog_no: "T1", value: 5, unit: "c", color: "blue", quantity: 1000 },
      { catalog_no: "T2", value: 10, unit: "c", color: "red", quantity: 500 },
    ],
  },
};
const OTHER_ISSUE = {
  issue_id: "CR-OTHER-TEST-ISSUE",
  title: "Another test issue",
  score: 2.123456,
  matched_by: ["vector"],
  card: { printers: ["Another printer"], stamps: [{ catalog_no: "T9", value: 1, unit: "c", color: "green", quantity: null }] },
};
const ANSWER = {
  question: "When was it placed on sale?",
  mode: { embedding: "ok", catalogue: "vector index", literature: "vector" },
  issues: [ISSUE, OTHER_ISSUE],
  passages: [
    { doc_id: "A TEST DOCUMENT", page: 12, chunk_type: "text", text: "A passage that answers the question.", clipped: true, score: 0.9 },
    { doc_id: "ANOTHER DOCUMENT", page: 3, chunk_type: "text", text: "A second passage.", clipped: false, score: 0.8 },
  ],
  timings: { embedding_ms: 100, catalogue_ms: 200, literature_ms: 50, total_ms: 900 },
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
  counts: { sentences: 3, sentences_without_citation: 1, citations: 2, citations_that_do_not_hold: 0 },
};
const CALLS = [{ purpose: "write", state: "ok", input_tokens: 4321, output_tokens: 123, seconds: 1.25 }];

/* Long sentences with several marks each, so lines wrap on a phone and on a wide screen. */
const LONG = {
  state: "ok",
  sentences: [
    { text: "A made-up sentence that runs on for long enough to wrap across more than one line of the answer on a narrow phone screen.", cites: [1, 2] },
    { text: "Another made-up sentence, with words of several lengths, which also carries more than one mark at its very end.", cites: [2, 1] },
    { text: "Short one.", cites: [1] },
    { text: "A third made-up sentence closes the answer with a last word that is rather long: extraordinarily.", cites: [1, 2] },
  ],
  sources: WRITTEN.sources,
  counts: { sentences: 4, sentences_without_citation: 0, citations: 7, citations_that_do_not_hold: 0 },
};

/** The chat route's answer: lines of JSON, the evidence and then the written answer. */
const lines = (written: object, evidence: object = ANSWER, rewritten = false, calls: object[] = CALLS) =>
  [{ type: "evidence", rewritten, evidence }, { type: "answer", answer: written, calls }].map((line) => JSON.stringify(line)).join("\n") + "\n";

type Mock = { health?: number; ask?: object; askStatus?: number; stored?: object | null; written?: object; chatStatus?: number; examples?: object[] };

async function mock(page: Page, options: Mock = {}) {
  await page.route("**/api/health", (route) =>
    options.health === 0 ? route.abort() : route.fulfill({ status: options.health ?? 200, json: { status: "ok" } }));
  await page.route("**/api/ask/examples", (route) =>
    route.fulfill({ json: { examples: options.examples ?? [{ lang: "en", question: "A live example question?" }], max_question_chars: 300 } }));
  await page.route("**/stored-examples.json", (route) =>
    options.stored === null ? route.fulfill({ status: 404, body: "" }) : route.fulfill({ json: options.stored ?? { generated: null, examples: [] } }));
  await page.route("**/api/ask", (route) =>
    route.fulfill({ status: options.askStatus ?? 200, json: options.ask ?? ANSWER, headers: options.askStatus === 429 ? { "Retry-After": "30" } : {} }));
  // the route that also writes an answer. By default no answer is written (no key), so the
  // tests about the evidence see the evidence alone
  await page.route("**/api/chat", (route) => {
    const status = options.chatStatus ?? options.askStatus ?? 200;
    if (status !== 200) return route.fulfill({ status, json: options.ask ?? { error: "not_found" }, headers: status === 429 ? { "Retry-After": "30" } : {} });
    return route.fulfill({ contentType: "application/x-ndjson", body: lines(options.written ?? { state: "no_key" }, options.ask ?? ANSWER) });
  });
}

/** A conversation already kept in this browser, in the stored shape. */
type SeedTurn = { question: string; written?: object; evidence?: object; rewritten?: boolean; stored?: boolean };
async function seed(page: Page, turns: SeedTurn[]) {
  const kept = turns.map((turn, i) => ({
    id: `seed-${i}`,
    question: turn.question,
    at: "2026-11-20T10:00:00.000Z",
    answer: turn.evidence ?? { ...ANSWER, question: turn.question },
    ...(turn.written ? { written: turn.written, calls: CALLS } : {}),
    ...(turn.rewritten ? { rewritten: true } : {}),
    ...(turn.stored ? { stored: true, storedDate: "2026-11-19" } : {}),
  }));
  const store = { version: 2, current: "c-seed", conversations: [{ id: "c-seed", started: kept[0].at, turns: kept }] };
  await page.addInitScript((value) => {
    if (!window.sessionStorage.getItem("seeded")) {
      window.localStorage.setItem("oxcart-conversations", value);
      window.sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(store));
}

/** Four kept turns: two answers, an answer that was not written, and the newest answer. */
const THREAD: SeedTurn[] = [
  { question: "When was the test issue placed on sale?", written: WRITTEN },
  { question: "And who printed it?", written: { ...WRITTEN, sentences: [WRITTEN.sentences[0]], sources: [WRITTEN.sources[0]] }, rewritten: true },
  { question: "What is the best glue for a test album?", written: { state: "not_covered" } },
  { question: "Which documents mention it?", written: LONG },
];

const box = (page: Page) => page.locator("#q");
async function ask(page: Page, text: string) {
  await box(page).fill(text);
  await box(page).press("Enter");
}
const newest = (page: Page) => page.getByTestId("turn").last();
const panel = (page: Page) => page.getByTestId("evidence-panel");

/** No page wider than the screen, and no Evidence panel wider than itself. */
async function noOverflow(page: Page, where: string) {
  const over = await page.evaluate(() => {
    const doc = document.documentElement;
    const ev = document.getElementById("evidence-panel");
    return { page: doc.scrollWidth - doc.clientWidth, panel: ev ? ev.scrollWidth - ev.clientWidth : 0 };
  });
  expect(over.page, `${where}: page`).toBeLessThanOrEqual(0);
  expect(over.panel, `${where}: panel`).toBeLessThanOrEqual(0);
}

async function stubHumanCheck(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as Record<string, unknown>;
    w.__OXCART_TEST_TURNSTILE_KEY__ = "test-site-key";
    w.turnstile = {
      render(el: HTMLElement, options: Record<string, unknown>) {
        w.__check = options;
        const stub = document.createElement("div");
        stub.textContent = "Stub of the check";
        stub.style.cssText = "width:300px;height:65px;border:1px dashed";
        el.appendChild(stub);
        return "widget-1";
      },
      reset() {},
      remove() {},
    };
  });
}
const passCheck = (page: Page) => page.evaluate(() => ((window as unknown as { __check: { callback: (t: string) => void } }).__check.callback("token")));

// ===================================================================== the first screen

test("the site opens directly on the question box", async ({ page }) => {
  await mock(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByLabel(/Your question|Su pregunta/)).toBeVisible();
  await expect(page.locator("header.masthead")).toContainText("Oxcart");
  await expect(page.getByTestId("demo-tag")).toBeVisible();
  await expect(page.getByRole("button", { name: "A live example question?" })).toBeVisible();
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
  await expect(full).not.toContainText("Tavily");                     // the web branch is not served
  // the footer is one line, with no company name, and both links lead to the repository
  const footer = page.locator("footer.site-foot");
  await expect(footer).not.toContainText(/OpenAI|Anthropic|Cloudflare/);
  await expect(footer.getByRole("link", { name: "How it works" })).toHaveAttribute("href", /\/oxcart\/blob\/main\/EVALUATION\.md$/);
  await expect(page.locator("header.masthead").getByRole("link", { name: /How it works|Cómo funciona/ })).toHaveAttribute("href", /EVALUATION\.md$/);
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

test("the questions to try give way to the thread, and come back when it is cleared", async ({ page }) => {
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
  await page.getByTestId("clear").click();
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

test("the human check stands in the turn, with its room kept, and the question goes on once it passes", async ({ page }) => {
  await stubHumanCheck(page);
  await mock(page, { written: WRITTEN });
  const sessions: string[] = [];
  await page.route("**/api/session", (route) => route.fulfill({ json: { session: "test-session", expires_in: 600 } }));
  page.on("request", (request) => {
    if (request.url().endsWith("/api/chat")) sessions.push(request.headers()["x-oxcart-session"] ?? "");
  });
  await page.goto("/");
  await ask(page, "A question that needs the check?");
  const turn = newest(page);
  await expect(turn).toContainText(/A quick check that you are a person|Una comprobación rápida/);
  await expect(turn).toContainText(/Waiting for the human check to finish|Esperando a que termine la comprobación/);
  const room = (await turn.getByTestId("human-check").boundingBox())!;
  expect(Math.round(room.width)).toBe(300);
  expect(Math.round(room.height)).toBe(65);
  await passCheck(page);
  await expect(turn.getByTestId("written-answer")).toBeVisible();
  await expect(turn.getByTestId("human-check")).toHaveCount(0);
  expect(sessions).toEqual(["test-session"]);
  // once per session: the next question asks no check
  await ask(page, "And the next one?");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(newest(page).getByTestId("evidence-button")).toBeVisible();
  await expect(newest(page).getByTestId("human-check")).toHaveCount(0);
});

test("a human check that does not pass is said in the turn, and the question stays in the box", async ({ page }) => {
  await stubHumanCheck(page);
  await mock(page);
  await page.route("**/api/session", (route) => route.fulfill({ status: 403, json: { error: "human_check_failed", message: "The human check did not pass." } }));
  await page.goto("/");
  await ask(page, "A question that fails the check?");
  const turn = newest(page);
  await expect(turn.getByTestId("human-check")).toBeVisible();
  await passCheck(page);
  await expect(turn.getByTestId("turn-error")).toContainText(/The human check did not pass|La comprobación no pasó/);
  await expect(turn.getByTestId("human-check")).toBeVisible();        // the widget stays, for another try
  await expect(box(page)).toHaveValue("A question that fails the check?");
  await expect(turn.getByTestId("evidence-button")).toHaveCount(0);
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
  await expect(page.getByTestId("ai-note")).toContainText(/written by an AI model|la redacta un modelo de IA/);
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

test("the conversation stays in this browser and can be cleared", async ({ page }) => {
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
  await page.getByTestId("clear").click();
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
  // a cleared conversation starts again, with no thread
  await page.getByTestId("clear").click();
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
  await expect(turn.getByTestId("not-covered")).toContainText(/does not answer this question|no responde esta pregunta/);
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
  expect(names).toContain("A test issue, authorized by: Test decree 1 (decree, 1889-01-02)");
  expect(names).toContain("A test issue, stamp T1");
  expect(names).toContain("Found, not cited by the answer: Another test issue (CR-OTHER-TEST-ISSUE)");
  await expect(panel(page).locator(".g-node--found")).not.toHaveCount(0);
  // every node is reachable by keyboard
  for (const node of await nodes.all()) await expect(node).toHaveAttribute("tabindex", "0");
  await nodes.first().focus();
  await expect(nodes.first()).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(nodes.nth(1)).toBeFocused();
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
  await expect(cards.first()).toContainText("1889-09-20");
  await expect(cards.first()).toContainText("Test decree 1");
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
    if (await page.getByTestId("clear").count()) await page.getByTestId("clear").click();   // the last width's thread
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
    await page.getByTestId("clear").click();
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

