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

async function mock(page: Page, options: { health?: number; ask?: object; askStatus?: number; stored?: object | null } = {}) {
  await page.route("**/api/health", (route) =>
    options.health === 0 ? route.abort() : route.fulfill({ status: options.health ?? 200, json: { status: "ok" } }));
  await page.route("**/api/ask/examples", (route) =>
    route.fulfill({ json: { examples: [{ lang: "en", question: "A live example question?" }], max_question_chars: 300 } }));
  await page.route("**/stored-examples.json", (route) =>
    options.stored === null ? route.fulfill({ status: 404, body: "" }) : route.fulfill({ json: options.stored ?? { generated: null, examples: [] } }));
  await page.route("**/api/ask", (route) =>
    route.fulfill({ status: options.askStatus ?? 200, json: options.ask ?? ANSWER, headers: options.askStatus === 429 ? { "Retry-After": "30" } : {} }));
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
  await page.route("**/api/ask", async (route) => {
    await asked;                                                      // the question waits, as it does while the service wakes
    await route.fulfill({ json: ANSWER });
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
