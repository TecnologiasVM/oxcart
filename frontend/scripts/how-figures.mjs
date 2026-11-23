#!/usr/bin/env node
/*
 * Every figure of the page "How it works" (app/how-it-works), in one generated file: lib/how-figures.json.
 *
 *   node scripts/how-figures.mjs           writes lib/how-figures.json
 *   node scripts/how-figures.mjs --check   exits 1 when the committed file is not what the sources give
 *
 * The page holds no number of its own. Each figure is counted here from a file of the repository:
 *   - the results run (RUN, below: the one place it is named), its rows and its summary, and of the questions
 *     outside the scope only each one's id and type (eval/data/questions_out_of_scope.jsonl);
 *   - eval/outcomes/catalogue_heldout_served.json (the catalogue lookup as served, on the held-out questions);
 *   - eval/outcomes/stage2.json (retrieval, and the catalogue lookup of stage 2), answers_thinking-off.json,
 *     answers_literature_settings.json, the two sealed runs;
 *   - eval/outcomes/how_it_works.json: the figures stated in EVALUATION.md and held in no other outcome file, as
 *     recorded values (the generator does not read EVALUATION.md itself),
 *     and (key `stores`) what the served stores say of themselves: versions, counts, index kinds;
 *   - backend/app/settings.py (limits, models), backend/app/ask_service.py (the vectors kept in memory);
 *   - the versions from package-lock.json, backend/requirements.txt, backend/Dockerfile and the CI workflow.
 * The test files are not read: a branch that adds a test does not have to make this file again.
 * A figure a source does not hold is null, and the page leaves out what it would say. No question, no
 * answer and no passage is read into the output.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// The run the page's results are read from: one published file of `python -m eval.chat_arm table --publish`.
const RUN = "answers_hosted-y.json";

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = join(FRONTEND, "..");
const OUTCOMES = join(REPO, "eval", "outcomes");
const OUT = join(FRONTEND, "lib", "how-figures.json");

const read = (...parts) => readFileSync(join(REPO, ...parts), "utf-8");
const json = (...parts) => JSON.parse(read(...parts));
const outcome = (name) => json("eval", "outcomes", name);

function fail(message) {
  throw new Error(`how-figures: ${message}`);
}
const count = (rows, test) => rows.filter(test).length;
const range = (values) => [Math.min(...values), Math.max(...values)];
const mean = (values) => values.reduce((a, b) => a + b, 0) / values.length;
const round = (value, digits) => Number(value.toFixed(digits));

// ------------------------------------------------------------------ the results run
/**
 * The questions outside the scope that were given a ticket for a web search: a row whose question is of type
 * "out_of_scope" (not "unanswerable") and whose answer carried a ticket, as the run published it (`web_ticket`,
 * written by `eval.chat_arm table --publish`). A run published without it is refused: a ticket is not inferred from
 * how an answer ended (the backend also needs a search key and searches left to give one).
 */
export function ticketedOutOfScope(rows, types) {
  const missing = rows.filter((r) => typeof r.web_ticket !== "boolean");
  if (missing.length) fail(`the results run has no web_ticket on ${missing.length} rows: publish it again with eval.chat_arm table --publish`);
  const outside = rows.filter((r) => types.get(r.id) === "out_of_scope");
  return { ticketed: count(outside, (r) => r.web_ticket === true), of: outside.length };
}
// the rule, pinned on made-up rows: only the type "out_of_scope" counts, and only a row whose answer carried a ticket
{
  const types = new Map([["a", "out_of_scope"], ["b", "out_of_scope"], ["c", "out_of_scope"], ["d", "out_of_scope"], ["e", "unanswerable"]]);
  const rows = [
    { id: "a", state: "not_covered", web_ticket: true },
    { id: "b", state: "ok", covers: "part", web_ticket: true },
    { id: "c", state: "ok", covers: "part", web_ticket: false },
    { id: "d", state: "out_of_scope", web_ticket: false },
    { id: "e", state: "not_covered", web_ticket: true },
  ];
  const got = ticketedOutOfScope(rows, types);
  if (got.ticketed !== 2 || got.of !== 4) fail(`the rule for a ticket outside the scope gives ${got.ticketed} of ${got.of}, not 2 of 4`);
  let refused = false;
  try {
    ticketedOutOfScope([{ id: "a", state: "ok", covers: "part" }], types);
  } catch {
    refused = true;
  }
  if (!refused) fail("a run without web_ticket was not refused");
}

/** Of the questions outside the scope, only each one's id and type (eval/data/questions_out_of_scope.jsonl). */
function scopeTypes() {
  const types = new Map();
  for (const line of read("eval", "data", "questions_out_of_scope.jsonl").split("\n")) {
    if (!line.trim()) continue;
    const { id, type } = JSON.parse(line);
    types.set(id, type);
  }
  return types;
}

function results(file) {
  const run = outcome(file);
  const usd = run.usd_per_mtok;
  const rows = run.rows;
  const single = rows.filter((r) => r.part !== "threads");
  const part = (name) => single.filter((r) => r.part === name);
  const written = (rs) => rs.filter((r) => r.state === "ok");
  const supported = (r) => Array.isArray(r.supported) && r.supported.length > 0 && r.supported.every((s) => s === "yes");
  const cat = part("catalogue");
  const lit = part("literature");
  const oos = part("out_of_scope");
  const litWritten = written(lit);
  // "gives what the question asks": the judge's second pass, when this run was given it
  const askedMarks = lit.filter((r) => typeof r.asked === "string");
  // every question asked in the run, the follow-ups too, as EVALUATION.md counts sentences for the runs through the host
  const counts = rows.map((r) => r.counts).filter(Boolean);
  const sum = (key) => counts.reduce((a, c) => a + c[key], 0);
  const cost = (calls) => calls.reduce((a, c) => a + c.input_tokens * usd.input + c.output_tokens * usd.output, 0) / 1e6;
  const costs = single.filter((r) => r.calls?.length).map((r) => cost(r.calls));
  const retrieval = run.summary?.retrieval ?? null;
  const waits = run.summary?.waits ?? null;
  return {
    file: `eval/outcomes/${file}`,
    label: run.label,
    // a run through the public service ("hosted…") or on the development machine: the waits' note says which
    through: /^hosted/.test(run.label) ? "host" : "development",
    questions: { all: single.length, catalogue: cat.length, literature: lit.length, out_of_scope: oos.length },
    catalogue: { correct: count(written(cat), (r) => r.correct === "yes"), supported: count(written(cat), supported), of: cat.length },
    literature: {
      in_full: count(litWritten, (r) => r.correct === "yes"),
      in_part: count(litWritten, (r) => r.correct === "partly"),
      not: count(litWritten, (r) => r.correct === "no"),
      not_written: lit.length - litWritten.length,
      asks: askedMarks.length ? count(askedMarks, (r) => r.asked === "yes") : null,
      of: lit.length,
    },
    out_of_scope: { no_answer: count(oos, (r) => r.state !== "ok"), of: oos.length },
    // with the web on: the questions outside the scope whose answer carried a ticket for a web search
    web_tickets_outside_scope: ticketedOutOfScope(oos, scopeTypes()),
    sentences: { removed: sum("sentences_without_citation"), written: sum("sentences") },
    citations: { not_hold: sum("citations_that_do_not_hold"), of: sum("citations") },
    cost: costs.length ? { mean: round(mean(costs), 5), max: round(Math.max(...costs), 5) } : null,
    page_found: retrieval
      ? { found: retrieval.literature.answered_in_first_k, k: retrieval.literature.k, of: retrieval.literature.questions, drafts: retrieval.literature.drafts }
      : null,
    waits: waits?.evidence && waits?.answer
      ? { evidence: round(waits.evidence.median, 2), answer: round(waits.answer.median, 2), answer_p95: round(waits.answer.p95, 2) }
      : null,
  };
}

// ------------------------------------------------------------------ retrieval and the catalogue lookup (stage2.json)
function stage2() {
  const s = outcome("stage2.json");
  const split = s.catalogue.split;
  const held = Object.keys(split).filter((id) => split[id] === "heldout");
  const lookup = (mode) => {
    const q = s.catalogue[mode].questions;
    const first = (ids) => count(ids, (id) => q[id]?.rank === 1);
    const spanish = held.filter((id) => id.endsWith("-es"));
    // "in the first three": a rank of 1 to 3, nothing else (a rank is null when the issue was not returned)
    const inThree = (id) => Number.isInteger(q[id]?.rank) && q[id].rank >= 1 && q[id].rank <= 3;
    return { first: first(held), three: count(held, inThree), of: held.length, es_first: first(spanish), es_of: spanish.length };
  };
  const runs = s.literature.runs;
  const arm = (run, name) => runs[run].arms[name];
  const litSplit = s.literature.split;
  const dev = Object.keys(litSplit).filter((id) => litSplit[id] === "dev");
  const devAnswered = (run, name) => count(dev, (id) => {
    const rank = arm(run, name).first_answering_rank[id];
    return rank != null && rank <= 5;
  });
  return {
    vector: lookup("lookup_vector_index"),
    full_text: lookup("lookup_full_text_only"),
    passages: runs["cloud-K"].objects,
    kept_answered: arm("cloud-K", "vector").answered_in_first_five,
    whole: { passages: runs["scratch-F"].objects, answered: arm("scratch-F", "vector").answered_in_first_five, of: arm("scratch-F", "vector").questions },
    // the hybrid arm chosen against vectors, on the development questions of the hosted collection
    hybrid: { answered: devAnswered("cloud-K", "hybrid-0.75"), vector: devAnswered("cloud-K", "vector"), of: dev.length },
  };
}

// ------------------------------------------------------------------ the catalogue lookup as served (held-out questions)
function lookupServed() {
  const s = outcome("catalogue_heldout_served.json");
  const q = Object.entries(s.questions);
  const first = (rows) => count(rows, ([, v]) => v.rank === 1);
  const spanish = q.filter(([id]) => id.endsWith("-es"));
  const inThree = ([, v]) => Number.isInteger(v.rank) && v.rank >= 1 && v.rank <= 3;
  return { first: first(q), three: count(q, inThree), of: q.length, es_first: first(spanish), es_of: spanish.length,
           median_s: s.latency_seconds.median, p95_s: s.latency_seconds.p95 };
}

// ------------------------------------------------------------------ what was tried on the written answers
function tried() {
  const off = outcome("answers_thinking-off.json").rows.filter((r) => r.part === "literature");
  const groups = outcome("answers_literature_settings.json").groups;
  const group = (setting) => groups.find((g) => g.setting === setting) ?? fail(`no setting ${setting}`);
  const served = group("nearest_excerpt"); // the served writer on the same evidence as the stronger one
  const strong = group("sonnet");
  const ratio = mean(strong.runs.map((r) => r.usd_a_question)) / mean(served.runs.map((r) => r.usd_a_question));
  return {
    thinking_off: { cut: count(off, (r) => r.state === "cut"), of: off.length },
    stronger: {
      model: strong.model,
      served_model: served.model,
      in_full: range(strong.runs.map((r) => r.in_full)),
      served_in_full: range(served.runs.map((r) => r.in_full)),
      of: strong.runs[0].questions,
      usd: round(mean(strong.runs.map((r) => r.usd_a_question)), 4),
      served_usd: round(mean(served.runs.map((r) => r.usd_a_question)), 5),
      times: Math.round(ratio),
    },
  };
}

// ------------------------------------------------------------------ the sealed set: two runs
function sealed() {
  const runs = ["answers_sealed-served.json", "answers_sealed-chosen.json"].map((file) => {
    const rows = outcome(file).rows;
    const part = (name) => rows.filter((r) => r.part === name);
    const lit = part("literature");
    const cat = part("catalogue");
    return {
      file: `eval/outcomes/${file}`,
      questions: rows.length,
      literature: { in_full: count(lit, (r) => r.state === "ok" && r.correct === "yes"), asks: count(lit, (r) => r.asked === "yes"), of: lit.length },
      catalogue: { correct: count(cat, (r) => r.state === "ok" && r.correct === "yes"), of: cat.length },
    };
  });
  // the page reads the two runs as the same questions, with one denominator: the same ids, not only as many
  const ids = ["answers_sealed-served.json", "answers_sealed-chosen.json"].map((file) => outcome(file).rows.map((r) => r.id).sort().join("\n"));
  if (ids[0] !== ids[1]) fail("the two sealed runs do not hold the same questions (their ids differ)");
  for (const key of ["literature", "catalogue"]) {
    if (runs[0][key].of !== runs[1][key].of) fail(`the two sealed runs have ${runs[0][key].of} and ${runs[1][key].of} ${key} questions`);
  }
  return { questions: runs[0].questions, runs };
}

// ------------------------------------------------------------------ settings and code
function setting(source, name) {
  const int = new RegExp(`^${name}: int = _int\\("${name}", (\\d+)\\)`, "m").exec(source);
  if (int) return Number(int[1]);
  const fixed = new RegExp(`^${name}: int = (\\d+)\\s*$`, "m").exec(source);
  if (fixed) return Number(fixed[1]);
  const str = new RegExp(`^${name}: str = "([^"]+)"`, "m").exec(source);
  if (str) return str[1];
  return fail(`${name} not found in backend/app/settings.py`);
}

function limits() {
  const s = read("backend", "app", "settings.py");
  const cache = /def __init__\(self, cache_size: int = (\d+)\)/.exec(read("backend", "app", "ask_service.py"));
  if (!cache) fail("the embedding cache's size not found in backend/app/ask_service.py");
  return {
    per_minute: setting(s, "ASK_LIMIT_PER_MINUTE"),
    per_day: setting(s, "ASK_LIMIT_PER_DAY"),
    model_calls_a_day: setting(s, "ANSWER_LIMIT_PER_DAY"),
    question_chars: setting(s, "ASK_MAX_QUESTION_CHARS"),
    issues: setting(s, "ASK_ISSUES"),
    passages: setting(s, "ASK_PASSAGES"),
    web_searches_a_month: setting(s, "WEB_SEARCHES_AT_MONTH_START") + setting(s, "WEB_SEARCHES_OVER_THE_MONTH"),
    vectors_in_memory: Number(cache[1]),
    models: { writer: setting(s, "ANSWER_MODEL"), embedding: setting(s, "EMBEDDING_MODEL") },
  };
}

// ------------------------------------------------------------------ versions
function pin(text, name) {
  const m = new RegExp(`^${name}(?:\\[[^\\]]*\\])?==([0-9][^\\s#]*)`, "m").exec(text);
  return m ? m[1] : fail(`${name} is not pinned in backend/requirements.txt`);
}

function versions() {
  const lock = JSON.parse(readFileSync(join(FRONTEND, "package-lock.json"), "utf-8")).packages;
  const npm = (name) => lock[`node_modules/${name}`]?.version ?? fail(`${name} not in package-lock.json`);
  const req = read("backend", "requirements.txt");
  const python = /^FROM python:(\d+\.\d+)/m.exec(read("backend", "Dockerfile"));
  const ci = read(".github", "workflows", "tests.yml");
  const pytest = /pytest==([0-9.]+)/.exec(ci);
  if (!python || !pytest) fail("a version was not found");
  return {
    langgraph: pin(req, "langgraph"),
    fastapi: pin(req, "fastapi"),
    python: python[1],
    next: npm("next"),
    react: npm("react"),
    typescript: npm("typescript"),
    playwright: npm("@playwright/test"),
    pytest: pytest[1],
  };
}

// ------------------------------------------------------------------ the figures stated in the documents
function documented() {
  const d = outcome("how_it_works.json");
  const trace = d.trace;
  if (!trace || !Array.isArray(trace.issues) || !Array.isArray(trace.answer)) fail("how_it_works.json holds no trace");
  const st = d.stores ?? fail("how_it_works.json holds no `stores`");
  const g = st.graph;
  const long = g.indexes.issue_vec_idx;
  const short = g.indexes.issue_short_vec_idx;
  // the sentence of step 2 says: two vector indexes of one kind, by one similarity, the long one quantized and the
  // short one not, and a full-text index; if the stores say otherwise, the sentence must change first
  if (long?.kind !== "vector" || short?.kind !== "vector" || long.type !== short.type || long.similarity !== short.similarity)
    fail("the graph's two issue vector indexes are not of one kind and one similarity");
  if (long.quantization !== true || short.quantization !== false) fail("the long issue index is not quantized, or the short one is");
  if (g.indexes.issue_text_idx?.kind !== "full-text") fail("the graph's issue_text_idx is not a full-text index");
  // one value recorded twice: the page reads `stores`. These compare two values recorded in how_it_works.json (what
  // the stores said, and what was copied from EVALUATION.md); they do not read EVALUATION.md itself
  if (st.literature.weaviate !== d.weaviate_version.value)
    fail(`two recorded values disagree in how_it_works.json: Weaviate ${st.literature.weaviate} under stores, ${d.weaviate_version.value} under weaviate_version`);
  for (const dims of [st.literature.dimensions, long.dimensions, short.dimensions]) {
    if (dims !== d.vector_numbers.value)
      fail(`two recorded values disagree in how_it_works.json: vectors of ${dims} numbers under stores, ${d.vector_numbers.value} under vector_numbers`);
  }
  return {
    stores: {
      graph: { neo4j: g.neo4j, issues: g.issues, stamps: g.stamps, index: { type: long.type, similarity: long.similarity } },
      literature: { weaviate: st.literature.weaviate, objects: st.literature.objects, dimensions: st.literature.dimensions, index: st.literature.index },
    },
    judges: {
      pages: { first: d.judges.pages.first, second: d.judges.pages.second, sample: d.judges.pages.sample, same_grade: d.judges.pages.same_grade, same_answers_or_not: d.judges.pages.same_answers_or_not },
      answers: { second: d.judges.answers.second, answers: d.judges.answers.answers, same_mark: d.judges.answers.same_mark, kappa: d.judges.answers.kappa },
    },
    points_a_question: [d.points_a_question.min, d.points_a_question.max],
    after_first_usd: d.after_first_question?.usd ?? null,
    spend_limit: d.spend_limit ? { usd: d.spend_limit.usd, month: d.spend_limit.month } : null,
    trace: {
      date: trace.date, lang: trace.lang, after: trace.after, asked: trace.asked, searched: trace.searched, caption: trace.caption,
      issues: trace.issues.map((i) => ({ title: i.title, score: i.score, printer: i.printer, source: i.source ?? null })),
      answer: trace.answer.map((s) => ({ text: s.text, sources: s.sources ?? [] })),
      note: trace.note,
    },
  };
}

export function figures() {
  const run = results(RUN);
  const s2 = stage2();
  const stored = documented();
  // a recorded value (how_it_works.json, stores) against an outcome file (stage2.json, the collection the eval ran on)
  if (stored.stores.literature.objects !== s2.passages)
    fail(`recorded values disagree: ${stored.stores.literature.objects} passages under stores in how_it_works.json, ${s2.passages} in stage2.json`);
  // the literature's judges of this run: the same model judges the pages
  return {
    _: "Generated by scripts/how-figures.mjs from the files named in it. Do not edit: run `node scripts/how-figures.mjs`.",
    run,
    // as served (the short vector on); stage 2's vector index alone and full-text index alone, for the comparison
    issue_found: lookupServed(),
    vector_only: s2.vector,
    full_text: s2.full_text,
    tried: { whole: s2.whole, kept_answered: s2.kept_answered, hybrid: s2.hybrid, ...tried() },
    sealed: sealed(),
    limits: limits(),
    versions: versions(),
    ...stored,
  };
}

const text = () => JSON.stringify(figures(), null, 1) + "\n";

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv.includes("--check")) {
    let committed = "";
    try {
      committed = readFileSync(OUT, "utf-8");
    } catch {
      /* missing: differs */
    }
    if (committed !== text()) {
      console.error(`${relative(REPO, OUT)} is not what the sources give: run \`node scripts/how-figures.mjs\` and commit it`);
      process.exit(1);
    }
    console.log(`${relative(REPO, OUT)} is up to date (run: ${RUN})`);
  } else {
    writeFileSync(OUT, text());
    console.log(`-> ${relative(REPO, OUT)} (run: ${RUN})`);
  }
}
