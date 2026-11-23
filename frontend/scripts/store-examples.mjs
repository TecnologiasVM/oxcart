// Store the example questions' evidence beside the page: public/stored-examples.json
//
// The page shows these while the service wakes up, and when it is asleep or gone, marked as
// stored examples. The file is made at build time from the backend's own answers and is NOT
// kept in the repository: it holds excerpts of the literature.
//
//   NEXT_PUBLIC_API_BASE   the backend's address. Never printed.
//   EXAMPLES_EVAL_KEY      the eval's secret header value (the build is not a browser, so it cannot
//                          pass the human check). Never printed.
//
// Without both, an existing file is kept; if there is none, an empty one is written so the
// page simply has no stored examples.
//
// With both, the refresh:
//   1. wakes the service: GET /api/health until it answers 200, for at most 90 s (it sleeps when unused);
//   2. asks each example up to 3 times, 5 s apart; an HTTP 429 waits for its Retry-After (at most 65 s);
//   3. keeps the examples that answered. The file is written when at least one answered and they are not fewer
//      than an existing file holds; otherwise the existing file is kept, and an empty one is written only when
//      there is none and nothing answered.
// The log says what happened: "stored examples: N of M written", and a line starting "WARNING:" when N < M
// or when nothing was refreshed although it was asked for. The build is never failed for it: the service
// sleeps, and a failed build would stop the site's deploys.
//
// For the tests only (tests-e2e/store-examples.spec.ts), the waits can be shortened through the environment:
// STORE_EXAMPLES_WAKE_MS, STORE_EXAMPLES_POLL_MS, STORE_EXAMPLES_RETRY_MS, STORE_EXAMPLES_SECOND_MS (the length
// of one second of a Retry-After). They are not settings of the site.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

const OUT = "public/stored-examples.json";
const TRIES = 3;
const RETRY_AFTER_MAX = 65;
const ms = (name, fallback) => {
  const raw = process.env[name];
  const value = Number(raw);
  return raw !== undefined && raw !== "" && Number.isFinite(value) && value >= 0 ? value : fallback;
};
const WAKE_MS = ms("STORE_EXAMPLES_WAKE_MS", 90_000);
const POLL_MS = ms("STORE_EXAMPLES_POLL_MS", 3_000);
const RETRY_MS = ms("STORE_EXAMPLES_RETRY_MS", 5_000);
const SECOND_MS = ms("STORE_EXAMPLES_SECOND_MS", 1_000);
const REQUEST_MS = 120_000;

const base = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");
const key = process.env.EXAMPLES_EVAL_KEY || "";
mkdirSync("public", { recursive: true });

const sleep = (t) => new Promise((resolve) => setTimeout(resolve, t));
const say = (line) => console.log(line);
const warn = (line) => console.log(`WARNING: ${line}`);

/** How many examples the file already there holds: null when there is none, 0 when it cannot be read. */
function existing() {
  if (!existsSync(OUT)) return null;
  try {
    const data = JSON.parse(readFileSync(OUT, "utf-8"));
    return Array.isArray(data.examples) ? data.examples.length : 0;
  } catch {
    return 0;
  }
}
const writeEmptyIfNone = () => {
  if (!existsSync(OUT)) writeFileSync(OUT, JSON.stringify({ generated: null, examples: [] }) + "\n");
};

/** Nothing new is written: the file there is kept, or an empty one written when there is none. */
function keep(reason) {
  const had = existing();
  writeEmptyIfNone();
  warn(`stored examples were not refreshed (${reason}); ${had === null
    ? "there was no file: an empty one was written, so the page has no stored examples"
    : `the file that is there is kept (${had} examples)`}`);
}

if (!base || !key) {
  const had = existsSync(OUT);
  writeEmptyIfNone();
  say(`stored examples: not refreshed (${had ? "kept the file that is there" : "none: an empty file was written"})`);
  process.exit(0);
}

/** GET /api/health until 200, for at most WAKE_MS. */
async function wake() {
  const until = Date.now() + WAKE_MS;
  for (;;) {
    try {
      const res = await fetch(`${base}/api/health`, { signal: AbortSignal.timeout(Math.max(1_000, Math.min(REQUEST_MS, until - Date.now()))) });
      if (res.status === 200) return true;
    } catch {
      /* asleep, or waking */
    }
    if (Date.now() + POLL_MS > until) return false;
    await sleep(POLL_MS);
  }
}

/** One request, up to TRIES times: RETRY_MS apart, or a 429's Retry-After (at most 65 s). The reply, or why not. */
async function tries(make) {
  let last = "";
  for (let n = 1; n <= TRIES; n++) {
    let wait = RETRY_MS;
    try {
      const res = await fetch(...make());
      if (res.ok) return { data: await res.json() };
      last = `HTTP ${res.status}`;
      if (res.status === 429) {
        const after = Number(res.headers.get("Retry-After"));
        wait = Math.min(Number.isFinite(after) && after >= 0 ? after : RETRY_AFTER_MAX, RETRY_AFTER_MAX) * SECOND_MS;
      }
    } catch (error) {
      last = error?.name ?? "error";
    }
    if (n < TRIES) await sleep(wait);
  }
  return { error: last };
}

const why = (errors) => [...new Set(errors)].join(", ");

if (!(await wake())) {
  keep(`the service did not answer its health check within ${Math.round(WAKE_MS / 1000)} s`);
  process.exit(0);
}

const list = await tries(() => [`${base}/api/ask/examples`, { signal: AbortSignal.timeout(REQUEST_MS) }]);
if (!list.data) {
  keep(`the list of examples could not be read: ${list.error}`);
  process.exit(0);
}

const asked = Array.isArray(list.data.examples) ? list.data.examples : [];
const examples = [];
const failed = [];
for (const example of asked) {
  const reply = await tries(() => [`${base}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Oxcart-Eval": key },
    body: JSON.stringify({ question: example.question }),
    signal: AbortSignal.timeout(REQUEST_MS),
  }]);
  if (reply.data) examples.push({ lang: example.lang, question: example.question, answer: reply.data });
  else failed.push(reply.error);
}

const had = existing();
if (examples.length > 0 && examples.length >= (had ?? 0)) {
  writeFileSync(OUT, JSON.stringify({ generated: new Date().toISOString().slice(0, 10), examples }) + "\n");
  say(`stored examples: ${examples.length} of ${asked.length} written`);
  if (examples.length < asked.length) {
    warn(`${asked.length - examples.length} of ${asked.length} examples did not answer after ${TRIES} tries (${why(failed)}); the page shows the ${examples.length} that did`);
  }
} else {
  say(`stored examples: 0 of ${asked.length} written`);
  keep(examples.length === 0
    ? `no example answered after ${TRIES} tries${failed.length ? ` (${why(failed)})` : ""}`
    : `${examples.length} of ${asked.length} answered, fewer than the ${had} the file that is there holds`);
}
