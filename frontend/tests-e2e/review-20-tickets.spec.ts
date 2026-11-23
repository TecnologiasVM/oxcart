import { test, expect } from "@playwright/test";
import { runName, sandbox } from "./figures-sandbox";

/*
 * A finding of an independent review of the page, on the build scripts or the generated figures, as the failure
 * it describes. No browser page. Every value changed in a test is made up.
 */
// ------------------------------------------------------------------ 20. a ticket is a published fact
test("finding 20: the tickets are counted from the run's web_ticket, and a run without it is refused", () => {
  const box = sandbox();
  try {
    const name = runName();
    const run = box.json(`eval/outcomes/${name}`);
    // a run that says nothing of tickets: refused
    for (const r of run.rows) delete r.web_ticket;
    box.write(`eval/outcomes/${name}`, run);
    const refused = box.run();
    expect(refused.status).not.toBe(0);
    expect(refused.out).toMatch(/web_ticket/);
    // every question outside the scope had a ticket, whatever its state: all of them are counted
    const types = new Map(box.runFile("eval/data/questions_out_of_scope.jsonl").trim().split("\n").map((l) => {
      const { id, type } = JSON.parse(l);
      return [id, type];
    }));
    for (const r of run.rows) r.web_ticket = types.get(r.id) === "out_of_scope";
    box.write(`eval/outcomes/${name}`, run);
    const all = box.run().figures.run.web_tickets_outside_scope;
    expect(all.ticketed).toBe(all.of);
  } finally {
    box.done();
  }
});
