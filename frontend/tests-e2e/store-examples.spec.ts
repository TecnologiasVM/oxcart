import { test, expect } from "@playwright/test";
import { execFile } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { createServer, IncomingMessage, ServerResponse } from "node:http";
import { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

/*
 * scripts/store-examples.mjs, run as the build runs it (a child process, in a temp working directory) against a
 * made-up backend: a local HTTP server started here. No browser page; a spec because CI runs the frontend's checks
 * as Playwright specs. The waits are shortened through the script's test-only environment variables. Every
 * question, answer and key is made up.
 */
const SCRIPT = join(__dirname, "..", "scripts", "store-examples.mjs");
const KEY = "a-made-up-eval-key";
const EXAMPLES = [
  { lang: "en", question: "A made-up first question?" },
  { lang: "es", question: "¿Una segunda pregunta inventada?" },
  { lang: "en", question: "A made-up third question?" },
];
const FILE = (dir: string) => join(dir, "public", "stored-examples.json");

type Reply = { status: number; headers?: Record<string, string>; json?: unknown };
type Backend = {
  health?: (n: number) => number;
  ask?: (question: string, n: number) => Reply;
};

/** A made-up backend: its health, its list of examples, and an answer per question, counted. */
async function backend(behave: Backend) {
  const asked: Record<string, number> = {};
  let health = 0;
  const keys: (string | undefined)[] = [];
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    const send = (r: Reply) => {
      res.writeHead(r.status, { "Content-Type": "application/json", ...(r.headers ?? {}) });
      res.end(JSON.stringify(r.json ?? {}));
    };
    if (req.url === "/api/health") return send({ status: (behave.health ?? (() => 200))(++health) });
    if (req.url === "/api/ask/examples") return send({ status: 200, json: { examples: EXAMPLES } });
    if (req.url === "/api/ask" && req.method === "POST") {
      let body = "";
      req.on("data", (c) => (body += c));
      req.on("end", () => {
        const { question } = JSON.parse(body);
        keys.push(req.headers["x-oxcart-eval"] as string | undefined);
        asked[question] = (asked[question] ?? 0) + 1;
        send((behave.ask ?? (() => ({ status: 200 })))(question, asked[question]));
      });
      return;
    }
    send({ status: 404 });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { base, asked, keys, healthCalls: () => health, close: () => new Promise((r) => server.close(r)) };
}
const answer = (question: string) => ({ status: 200, json: { question, issues: [], passages: [], mode: { embedding: "ok" } } });

/** The script, run in a temp folder; its whole output, which must never hold the key or the backend's address. */
async function run(base: string, existing?: object) {
  const dir = mkdtempSync(join(tmpdir(), "oxcart-store-"));
  if (existing) {
    mkdirSync(join(dir, "public"));
    writeFileSync(FILE(dir), JSON.stringify(existing));
  }
  const { stdout, stderr } = await promisify(execFile)(process.execPath, [SCRIPT], {
    cwd: dir,
    env: {
      PATH: process.env.PATH,
      NEXT_PUBLIC_API_BASE: base,
      EXAMPLES_EVAL_KEY: KEY,
      STORE_EXAMPLES_WAKE_MS: "400",
      STORE_EXAMPLES_POLL_MS: "20",
      STORE_EXAMPLES_RETRY_MS: "10",
      STORE_EXAMPLES_SECOND_MS: "20",
    },
  });
  const out = stdout + stderr;
  expect(out).not.toContain(KEY);
  expect(out).not.toContain(base.replace("http://", ""));
  const file = existsSync(FILE(dir)) ? JSON.parse(readFileSync(FILE(dir), "utf-8")) : null;
  rmSync(dir, { recursive: true, force: true });
  return { out, file };
}

test("all answer: the service is woken first, every example is written, no warning", async () => {
  const b = await backend({ health: (n) => (n < 3 ? 503 : 200), ask: (q) => answer(q) });
  try {
    const { out, file } = await run(b.base);
    expect(b.healthCalls()).toBe(3);
    expect(out).toContain("stored examples: 3 of 3 written");
    expect(out).not.toContain("WARNING");
    expect(file.examples.map((e: { question: string }) => e.question)).toEqual(EXAMPLES.map((e) => e.question));
    expect(file.generated).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(b.keys.every((k) => k === KEY)).toBe(true);
  } finally {
    await b.close();
  }
});

test("one example fails three times: the others are written, and a WARNING says so", async () => {
  const bad = EXAMPLES[1].question;
  const b = await backend({ ask: (q) => (q === bad ? { status: 500 } : answer(q)) });
  try {
    const { out, file } = await run(b.base);
    expect(b.asked[bad]).toBe(3);
    expect(out).toContain("stored examples: 2 of 3 written");
    expect(out).toMatch(/^WARNING: 1 of 3 examples did not answer after 3 tries \(HTTP 500\)/m);
    expect(file.examples.map((e: { question: string }) => e.question)).toEqual([EXAMPLES[0].question, EXAMPLES[2].question]);
  } finally {
    await b.close();
  }
});

test("nothing answers and a fuller file is there: it is kept as it was, with a WARNING", async () => {
  const kept = { generated: "2026-01-01", examples: EXAMPLES.map((e) => ({ ...e, answer: { made: "up" } })) };
  const b = await backend({ ask: () => ({ status: 503 }) });
  try {
    const { out, file } = await run(b.base, kept);
    expect(out).toContain("stored examples: 0 of 3 written");
    expect(out).toMatch(/^WARNING: stored examples were not refreshed \(no example answered after 3 tries \(HTTP 503\)\); the file that is there is kept \(3 examples\)/m);
    expect(file).toEqual(kept);
  } finally {
    await b.close();
  }
});

test("fewer answer than a file there holds: the file is kept", async () => {
  const kept = { generated: "2026-01-01", examples: EXAMPLES.map((e) => ({ ...e, answer: { made: "up" } })) };
  const b = await backend({ ask: (q) => (q === EXAMPLES[0].question ? answer(q) : { status: 500 }) });
  try {
    const { out, file } = await run(b.base, kept);
    expect(out).toMatch(/^WARNING: stored examples were not refreshed \(1 of 3 answered, fewer than the 3 the file that is there holds\)/m);
    expect(file).toEqual(kept);
  } finally {
    await b.close();
  }
});

test("nothing answers and there is no file: an empty one is written, with a WARNING", async () => {
  const b = await backend({ ask: () => ({ status: 500 }) });
  try {
    const { out, file } = await run(b.base);
    expect(out).toContain("stored examples: 0 of 3 written");
    expect(out).toMatch(/^WARNING: stored examples were not refreshed .*there was no file: an empty one was written/m);
    expect(file).toEqual({ generated: null, examples: [] });
  } finally {
    await b.close();
  }
});

test("the service never wakes: nothing is asked, the WARNING says why, an empty file when there was none", async () => {
  const b = await backend({ health: () => 503 });
  try {
    const { out, file } = await run(b.base);
    expect(Object.keys(b.asked)).toEqual([]);
    expect(out).toMatch(/^WARNING: stored examples were not refreshed \(the service did not answer its health check within 0 s\)/m);
    expect(file).toEqual({ generated: null, examples: [] });
  } finally {
    await b.close();
  }
});

test("a 429 waits for its Retry-After, then the answer is kept", async () => {
  const slow = EXAMPLES[0].question;
  const b = await backend({ ask: (q, n) => (q === slow && n === 1 ? { status: 429, headers: { "Retry-After": "5" } } : answer(q)) });
  try {
    const started = Date.now();
    const { out, file } = await run(b.base);
    // Retry-After 5, at 20 ms a second in this test: at least 100 ms
    expect(Date.now() - started).toBeGreaterThanOrEqual(100);
    expect(b.asked[slow]).toBe(2);
    expect(out).toContain("stored examples: 3 of 3 written");
    expect(out).not.toContain("WARNING");
    expect(file.examples).toHaveLength(3);
  } finally {
    await b.close();
  }
});

test("not asked to refresh (no key): an existing file is kept, else an empty one, and no WARNING", async () => {
  const dir = mkdtempSync(join(tmpdir(), "oxcart-store-"));
  try {
    const { stdout } = await promisify(execFile)(process.execPath, [SCRIPT], { cwd: dir, env: { PATH: process.env.PATH } });
    expect(stdout).toContain("stored examples: not refreshed (none: an empty file was written)");
    expect(stdout).not.toContain("WARNING");
    expect(JSON.parse(readFileSync(FILE(dir), "utf-8"))).toEqual({ generated: null, examples: [] });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ------------------------------------------------------------------ finding 14 of the review: what is checked and what is kept
test("finding 14: an example of the wrong shape is skipped, and of an answer only what the page reads is written", async () => {
  const extra = (q: string) => ({
    status: 200,
    json: {
      question: q, mode: { embedding: "ok" }, issues: [{ issue_id: "I-1", title: "A made-up issue", score: 1, matched_by: [], card: null, made_up_extra: "x" }],
      passages: [{ doc_id: "A MADE-UP DOC", page: 1, text: "A made-up passage.", clipped: false, score: 1, made_up_extra: "x" }],
      timings: { total_ms: 1 }, made_up_extra: "not for the page",
    },
  });
  const b = await backend({ ask: (q) => extra(q) });
  const list = EXAMPLES.splice(0, EXAMPLES.length, ...EXAMPLES, { lang: "en", question: 42 as unknown as string });
  try {
    const { out, file } = await run(b.base);
    expect(out).toContain("stored examples: 3 of 3 written");
    expect(file.examples).toHaveLength(3);
    const text = JSON.stringify(file);
    expect(text).not.toContain("made_up_extra");
    expect(file.examples[0].answer.passages[0].text).toBe("A made-up passage.");
    expect(Object.keys(file.examples[0].answer).sort()).toEqual(["issues", "mode", "passages", "question", "timings"]);
  } finally {
    EXAMPLES.splice(0, EXAMPLES.length, ...list);
    await b.close();
  }
});

test("finding 14: a list that is not a list of examples keeps the file that is there", async () => {
  const kept = { generated: "2026-01-01", examples: [{ lang: "en", question: "A made-up kept question?", answer: { made: "up" } }] };
  const dir = mkdtempSync(join(tmpdir(), "oxcart-store-"));
  const server = createServer((req, res) => {
    res.writeHead(req.url === "/api/ask/examples" ? 500 : 200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(req.url === "/api/ask/examples" ? { error: "internal" } : {}));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    mkdirSync(join(dir, "public"));
    writeFileSync(FILE(dir), JSON.stringify(kept));
    const { stdout } = await promisify(execFile)(process.execPath, [SCRIPT], {
      cwd: dir,
      env: { PATH: process.env.PATH, NEXT_PUBLIC_API_BASE: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, EXAMPLES_EVAL_KEY: KEY, STORE_EXAMPLES_RETRY_MS: "10" },
    });
    expect(stdout).toMatch(/^WARNING: stored examples were not refreshed/m);
    expect(JSON.parse(readFileSync(FILE(dir), "utf-8"))).toEqual(kept);
  } finally {
    rmSync(dir, { recursive: true, force: true });
    await new Promise((r) => server.close(r));
  }
});
