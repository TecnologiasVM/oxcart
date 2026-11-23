import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

/*
 * For the specs of the generated figures: scripts/how-figures.mjs run in a sandbox, a temp copy of exactly the
 * files it reads, so a test can change one of them without touching the repository.
 */
export const FRONTEND = join(__dirname, "..");
const REPO = join(FRONTEND, "..");

/** A temp copy of what scripts/how-figures.mjs reads, and a way to run it there. */
export function sandbox() {
  const dir = mkdtempSync(join(tmpdir(), "oxcart-figures-"));
  const copy = (rel: string) => cpSync(join(REPO, rel), join(dir, rel), { recursive: true });
  for (const rel of ["eval/outcomes", "eval/data/questions_out_of_scope.jsonl", "backend/app/settings.py", "backend/app/ask_service.py",
    "backend/requirements.txt", "backend/Dockerfile", ".github/workflows/tests.yml", "frontend/package-lock.json",
    "frontend/playwright.config.ts", "frontend/tests-e2e", "frontend/scripts/how-figures.mjs",
    "eval/tests", "oxcart/tests", "pipeline/first_issue_graph/tests", "backend/tests"]) copy(rel);
  mkdirSync(join(dir, "frontend", "lib"), { recursive: true });
  const path = (rel: string) => join(dir, rel);
  return {
    json: (rel: string) => JSON.parse(readFileSync(path(rel), "utf-8")),
    write: (rel: string, value: unknown) => writeFileSync(path(rel), JSON.stringify(value, null, 1) + "\n"),
    run: () => {
      const r = spawnSync(process.execPath, [path("frontend/scripts/how-figures.mjs")], { encoding: "utf-8" });
      return { status: r.status, out: r.stdout + r.stderr, figures: r.status === 0 ? JSON.parse(readFileSync(path("frontend/lib/how-figures.json"), "utf-8")) : null };
    },
    runFile: (rel: string) => readFileSync(path(rel), "utf-8"),
    done: () => rmSync(dir, { recursive: true, force: true }),
  };
}
/** The results run the generator names (RUN in how-figures.mjs). */
export const runName = () => /const RUN = "([^"]+)";/.exec(readFileSync(join(FRONTEND, "scripts", "how-figures.mjs"), "utf-8"))![1];

