import { expect, Page } from "@playwright/test";
import { deflateSync } from "node:zlib";

/*
 * What the browser tests of the question page share: made-up fixtures, the service mocked in
 * the browser, Cloudflare's script stubbed, and a few steps a visitor takes.
 */

export const ISSUE = {
  issue_id: "CR-TEST-ISSUE",
  title: "A test issue",
  score: 4,
  matched_by: ["vector", "year"],
  card: {
    // two names the catalogue uses, and two it does not (shown as the data has them)
    dates: { placed_on_sale: "1889-09-20", probable_first_circulation: "1889-09-21", issued: "1889-09", withdrawn: "about 1890" },
    printers: ["A printer"],
    perforation: "12",
    acts: [{ type: "decree", id: "Test decree 1", date: "1889-01-02" }],
    stamps: [
      { catalog_no: "T1", value: 5, unit: "c", color: "blue", quantity: 1000 },
      { catalog_no: "T2", value: 10, unit: "c", color: "red", quantity: 500 },
    ],
  },
};
export const OTHER_ISSUE = {
  issue_id: "CR-OTHER-TEST-ISSUE",
  title: "Another test issue",
  score: 2.123456,
  matched_by: ["vector"],
  card: { printers: ["Another printer"], acts: [{ type: "law", id: "Act 7", date: "1890-05" }], stamps: [{ catalog_no: "T9", value: 1, unit: "c", color: "green", quantity: null }] },
};
export const ANSWER = {
  question: "When was it placed on sale?",
  mode: { embedding: "ok", catalogue: "vector index", literature: "vector" },
  issues: [ISSUE, OTHER_ISSUE],
  passages: [
    { doc_id: "A TEST DOCUMENT", page: 12, chunk_type: "text", text: "A passage that answers the question.", clipped: true, score: 0.9 },
    { doc_id: "ANOTHER DOCUMENT", page: 3, chunk_type: "text", text: "A second passage.", clipped: false, score: 0.8 },
  ],
  timings: { embedding_ms: 100, catalogue_ms: 200, literature_ms: 50, total_ms: 900 },
};

export const STORED = {
  generated: "2026-11-19",
  examples: [{ lang: "en", question: "A stored example question?", answer: { ...ANSWER, question: "A stored example question?" } }],
};

/* A written answer for ANSWER: two sentences, the first cites the card, the second the first passage. */
export const WRITTEN = {
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
export const CALLS = [{ purpose: "write", state: "ok", input_tokens: 4321, output_tokens: 123, seconds: 1.25 }];

/* Long sentences with several marks each, so lines wrap on a phone and on a wide screen. */
export const LONG = {
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
export const lines = (written: object, evidence: object = ANSWER, rewritten = false, calls: object[] = CALLS) =>
  [{ type: "evidence", rewritten, evidence }, { type: "answer", answer: written, calls }].map((line) => JSON.stringify(line)).join("\n") + "\n";

export type Mock = { health?: number; ask?: object; askStatus?: number; stored?: object | null; written?: object; chatStatus?: number; examples?: object[] };

/*
 * Cloudflare's script, stubbed. Like the real one with appearance "interaction-only", the
 * widget it draws stays out of view (its own display: none) unless it needs a click.
 * Modes (set before the page loads with `checkMode`):
 *   pass   the check passes on its own a moment after it runs (the default)
 *   hold   the check runs until the test settles it (`settleCheck`)
 *   click  the check needs a click on its own button
 */
export const TURNSTILE_STUB = `(() => {
  let n = 0;
  window.__checks = [];
  window.turnstile = {
    render(el, o) {
      const id = "w" + (++n);
      const mode = window.__checkMode || "pass";
      const widget = document.createElement("div");
      widget.dataset.widget = id;
      // It stands on a line of text with its foot on the baseline, as the real widget's frame does (an
      // inline block that clips sits that way): so the element that holds it is taller than it by the
      // line's room under the baseline, unless the page takes that room away.
      widget.style.cssText = "width:300px;height:65px;box-sizing:border-box;border:1px dashed;overflow:hidden";
      const show = (on) => { widget.style.display = o.appearance !== "interaction-only" || on ? "inline-block" : "none"; };
      el.appendChild(widget);
      const entry = { id, el, o, runs: 0 };
      entry.run = () => {
        entry.runs += 1;
        widget.replaceChildren();
        show(false);
        if (mode === "pass") setTimeout(() => o.callback("token-" + id + "-" + entry.runs), 20);
        if (mode === "click") {
          if (o["before-interactive-callback"]) o["before-interactive-callback"]();
          show(true);
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "Verify you are human";
          button.onclick = () => {
            show(false);
            if (o["after-interactive-callback"]) o["after-interactive-callback"]();
            o.callback("token-" + id);
          };
          widget.appendChild(button);
        }
      };
      window.__checks.push(entry);
      entry.run();
      return id;
    },
    reset(id) {
      const entry = window.__checks.find((c) => c.id === id);
      if (entry) entry.run();
    },
    remove() {},
  };
})();`;

export async function checkMode(page: Page, mode: "pass" | "hold" | "click") {
  await page.addInitScript((m) => Object.assign(window, { __checkMode: m }), mode);
}
export type CheckEntry = { id: string; runs: number; el: HTMLElement; o: { callback: (t: string) => void; appearance?: string } };
export const checks = (page: Page) =>
  page.evaluate(() => ((window as unknown as { __checks?: CheckEntry[] }).__checks ?? []).map((c) => ({
    id: c.id, runs: c.runs, appearance: c.o.appearance, inHost: c.el.getAttribute("data-testid") === "check-host",
  })));
export const settleCheck = (page: Page) =>
  page.evaluate(() => {
    const all = (window as unknown as { __checks: CheckEntry[] }).__checks;
    all[all.length - 1].o.callback("token-held");
  });

/**
 * Fails if any element the check is drawn into is off screen, or is put out of view or out of
 * reach by the page: `inert` or `aria-hidden` on it or above it, `display: none` or
 * `visibility: hidden` on it or above it. (The widget inside is Cloudflare's to show or hide.)
 */
export async function checkInReach(page: Page) {
  const problems = await page.evaluate(() => {
    const out: string[] = [];
    const doc = document.documentElement;
    for (const entry of (window as unknown as { __checks?: CheckEntry[] }).__checks ?? []) {
      const el = entry.el;
      if (!el.isConnected) { out.push(`${entry.id}: not in the page`); continue; }
      const box = el.getBoundingClientRect();
      const left = box.left + window.scrollX;
      const top = box.top + window.scrollY;
      if (left < 0 || left >= doc.scrollWidth || top < 0 || top >= doc.scrollHeight) out.push(`${entry.id}: off screen at ${left},${top}`);
      for (let node: Element | null = el; node; node = node.parentElement) {
        const style = getComputedStyle(node);
        const name = `${node.tagName.toLowerCase()}.${node.className}`;
        if (node.hasAttribute("inert")) out.push(`${name}: inert`);
        if (node.getAttribute("aria-hidden") === "true") out.push(`${name}: aria-hidden`);
        if (style.display === "none") out.push(`${name}: display none`);
        if (style.visibility === "hidden") out.push(`${name}: visibility hidden`);
      }
    }
    return out;
  });
  expect(problems).toEqual([]);
}

/*
 * The figures host the browser tests are built against (NEXT_PUBLIC_FIGURES_BASE in the build: CI
 * and playwright.config.ts set it). Nothing is fetched from it: every request to it is routed, and
 * without a test's own route it answers 404, so the first screen has no plate.
 */
export const FIGURES_HOST = "https://figures.invalid";

const CRC = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf: Buffer) => {
  let c = 0xffffffff;
  for (const byte of buf) c = CRC[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
const chunk = (type: string, data: Buffer) => {
  const head = Buffer.alloc(4);
  head.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([head, body, crc]);
};
/** A made-up picture: a plain PNG of this many pixels, in one colour. */
export function png(width: number, height: number, rgb: [number, number, number] = [180, 160, 120]): Buffer {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr.set([8, 2, 0, 0, 0], 8); // 8 bits, RGB
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: width }, () => rgb).flat())]);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

/** Serve made-up pictures from the figures host: `<id>.png` at the size given for that id. */
export async function serveFigures(page: Page, sizes: Record<string, [number, number]>) {
  await page.route(`${FIGURES_HOST}/*.png`, (route) => {
    const id = new URL(route.request().url()).pathname.slice(1, -4);
    const size = sizes[id];
    return size ? route.fulfill({ contentType: "image/png", body: png(size[0], size[1]) }) : route.fulfill({ status: 404, body: "" });
  });
}

export async function mock(page: Page, options: Mock = {}) {
  await page.route(`${FIGURES_HOST}/**`, (route) => route.fulfill({ status: 404, body: "" }));
  await page.route(/^https:\/\/challenges\.cloudflare\.com\/turnstile\//, (route) =>
    route.fulfill({ contentType: "text/javascript", body: TURNSTILE_STUB }));
  await page.route("**/api/session", (route) => route.fulfill({ json: { session: "test-session", expires_in: 600 } }));
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

/** Conversations already kept in this browser, in the stored shape. */
export type SeedTurn = { question: string; written?: object; evidence?: object; rewritten?: boolean; stored?: boolean };
export type SeedConversation = { id: string; at?: string; turns: SeedTurn[] };
export const EARLIER = "2026-11-20T10:00:00.000Z";
export async function seedMany(page: Page, conversations: SeedConversation[], current: string) {
  const kept = conversations.map((c) => {
    const turns = c.turns.map((turn, i) => ({
      id: `${c.id}-t${i}`,
      question: turn.question,
      at: c.at ?? EARLIER,
      answer: turn.evidence ?? { ...ANSWER, question: turn.question },
      ...(turn.written ? { written: turn.written, calls: CALLS } : {}),
      ...(turn.rewritten ? { rewritten: true } : {}),
      ...(turn.stored ? { stored: true, storedDate: "2026-11-19" } : {}),
    }));
    return { id: c.id, started: turns[0].at, turns };
  });
  const store = { version: 2, current, conversations: kept };
  await page.addInitScript((value) => {
    if (!window.sessionStorage.getItem("seeded")) {
      window.localStorage.setItem("oxcart-conversations", value);
      window.sessionStorage.setItem("seeded", "1");
    }
  }, JSON.stringify(store));
}
/** One conversation, open. */
export const seed = (page: Page, turns: SeedTurn[]) => seedMany(page, [{ id: "c-seed", turns }], "c-seed");

/** Delete the open conversation, as a visitor does: asked in place, then confirmed. */
export async function deleteConversation(page: Page) {
  await page.getByTestId("delete-one").click();
  await page.getByTestId("confirm-one").getByRole("button", { name: /^(Delete|Borrar)$/ }).click();
}
/** "New conversation": in the rail where it stands, else "New" in the bar. */
export async function startNew(page: Page) {
  const rail = page.getByTestId("new-conversation");
  if (await rail.isVisible()) await rail.click();
  else await page.getByTestId("new-short").click();
}

/** Four kept turns: two answers, an answer that was not written, and the newest answer. */
export const THREAD: SeedTurn[] = [
  { question: "When was the test issue placed on sale?", written: WRITTEN },
  { question: "And who printed it?", written: { ...WRITTEN, sentences: [WRITTEN.sentences[0]], sources: [WRITTEN.sources[0]] }, rewritten: true },
  { question: "What is the best glue for a test album?", written: { state: "not_covered" } },
  { question: "Which documents mention it?", written: LONG },
];

export const box = (page: Page) => page.locator("#q");
export async function ask(page: Page, text: string) {
  await box(page).fill(text);
  await box(page).press("Enter");
}
export const newest = (page: Page) => page.getByTestId("turn").last();
export const panel = (page: Page) => page.getByTestId("evidence-panel");

/** No page wider than the screen, and no Evidence panel wider than itself. */
export async function noOverflow(page: Page, where: string) {
  const over = await page.evaluate(() => {
    const doc = document.documentElement;
    const ev = document.getElementById("evidence-panel");
    return { page: doc.scrollWidth - doc.clientWidth, panel: ev ? ev.scrollWidth - ev.clientWidth : 0 };
  });
  expect(over.page, `${where}: page`).toBeLessThanOrEqual(0);
  expect(over.panel, `${where}: panel`).toBeLessThanOrEqual(0);
}


// ---------------------------------------------------------------- shared by the specs of the review's findings (review-*.spec.ts)
export const TICKET = { ticket: "a-made-up-ticket", expires_in: 120 };
export const PART = { ...WRITTEN, covers: "part", web: TICKET };
export const WEB_OK = {
  state: "ok",
  sentences: [{ text: "A made-up page says a made-up thing.", cites: [1] }],
  results: [{ n: 1, title: "A made-up page", host: "pages.example", url: "https://pages.example/made-up" }],
};
export const submitButton = (page: Page) => page.locator("form.composer button[type=submit]");
/** Let the page's clock run, in steps, as the specs of the waking notice do. */
export async function runClock(page: Page, seconds: number) {
  for (let s = 0; s < seconds; s += 2) {
    await page.clock.runFor(2000);
    await page.waitForTimeout(20);
  }
}
/** The chat route answered by a stream the test drives: the evidence at once, the rest only when released. */
export async function heldStream(page: Page, answer: object | null) {
  await page.addInitScript(({ evidence, rest }) => {
    const real = window.fetch.bind(window);
    const w = window as unknown as { __release?: () => void };
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (!url.endsWith("/api/chat")) return real(input, init);
      const enc = new TextEncoder();
      const body = new ReadableStream({
        start(c) {
          c.enqueue(enc.encode(evidence));
          w.__release = () => {
            if (rest) {
              c.enqueue(enc.encode(rest));
              c.close();
            }
          };
        },
      });
      return new Response(body, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
    };
  }, {
    evidence: JSON.stringify({ type: "evidence", rewritten: false, evidence: ANSWER }) + "\n",
    rest: answer ? JSON.stringify({ type: "answer", answer, calls: CALLS }) + "\n" : null,
  });
}

/** localStorage.setItem throws while window.__failWrites is true (a full store, or a refusing one). */
export async function failingStorage(page: Page, kind: "full" | "refused", from: boolean) {
  await page.addInitScript(({ kind, from }) => {
    const w = window as unknown as { __failWrites: boolean };
    w.__failWrites = from && !window.sessionStorage.getItem("reloaded");
    const real = Storage.prototype.setItem;
    Storage.prototype.setItem = function (this: Storage, key: string, value: string) {
      if (this === window.localStorage && w.__failWrites) {
        throw kind === "full" ? new DOMException("made up", "QuotaExceededError") : new Error("made up");
      }
      return real.call(this, key, value);
    };
  }, { kind, from });
}

