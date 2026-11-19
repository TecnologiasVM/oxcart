// Store the example questions' evidence beside the page: public/stored-examples.json
//
// The page shows these while the service wakes up, and when it is asleep or gone, marked as
// stored examples. The file is made at build time from the backend's own answers and is NOT
// kept in the repository: it holds excerpts of the literature.
//
//   NEXT_PUBLIC_API_BASE   the backend's address
//   EXAMPLES_EVAL_KEY      the eval's secret header value (the build is not a browser, so it cannot
//                          pass the human check). Never printed.
//
// Without both, an existing file is kept; if there is none, an empty one is written so the
// page simply has no stored examples.
import { existsSync, mkdirSync, writeFileSync } from "node:fs";

const OUT = "public/stored-examples.json";
const base = (process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");
const key = process.env.EXAMPLES_EVAL_KEY || "";
mkdirSync("public", { recursive: true });

const empty = () => {
  if (!existsSync(OUT)) writeFileSync(OUT, JSON.stringify({ generated: null, examples: [] }) + "\n");
};

if (!base || !key) {
  const had = existsSync(OUT);
  empty();
  console.log(`stored examples: not refreshed (${had ? "kept the file that is there" : "none: an empty file was written"})`);
  process.exit(0);
}

try {
  const list = await (await fetch(`${base}/api/ask/examples`, { signal: AbortSignal.timeout(120_000) })).json();
  const examples = [];
  for (const example of list.examples ?? []) {
    const res = await fetch(`${base}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Oxcart-Eval": key },
      body: JSON.stringify({ question: example.question }),
      signal: AbortSignal.timeout(120_000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    examples.push({ lang: example.lang, question: example.question, answer: await res.json() });
  }
  writeFileSync(OUT, JSON.stringify({ generated: new Date().toISOString().slice(0, 10), examples }) + "\n");
  console.log(`stored examples: ${examples.length} written`);
} catch (error) {
  empty();
  console.log(`stored examples: not refreshed (${error?.name ?? "error"}); the build goes on without new ones`);
}
