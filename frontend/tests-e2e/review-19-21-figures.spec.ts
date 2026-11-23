import { test, expect } from "@playwright/test";
import { HOW } from "../lib/how-i18n";
import { sandbox } from "./figures-sandbox";

/*
 * A finding of an independent review of the page, on the build scripts or the generated figures, as the failure
 * it describes. No browser page. Every value changed in a test is made up.
 */
// ------------------------------------------------------------------ 19. the generated figures
test.describe("finding 19: the generated figures say only what their sources hold", () => {
  test("'in the first three' counts ranks 1 to 3 only", () => {
    const box = sandbox();
    try {
      const s2 = box.json("eval/outcomes/stage2.json");
      const before = box.run().figures.issue_found.three;
      const q = s2.catalogue.lookup_vector_index.questions;
      const held = Object.keys(s2.catalogue.split).filter((id) => s2.catalogue.split[id] === "heldout");
      const id = held.find((x) => q[x]?.rank === 1)!;
      q[id] = { rank: 99, fact_found: false };
      box.write("eval/outcomes/stage2.json", s2);
      expect(box.run().figures.issue_found.three).toBe(before - 1);
    } finally {
      box.done();
    }
  });

  test("step 2 says each store's own similarity", () => {
    const text = HOW.en.steps.s2.text({
      writer: "W", numbers: "1", issues: "3", passages: "5", graphIndex: "HNSW", litIndex: "HFresh", litCompression: "RQ",
      graphSimilarity: "dot product", litSimilarity: "cosine",
    } as Parameters<typeof HOW.en.steps.s2.text>[0]);
    expect(text).toContain("two HNSW vector indexes by dot product");
    expect(text).toContain("with RQ compression, by cosine");
  });

  test("the two sealed runs must hold the same questions, not only as many", () => {
    const box = sandbox();
    try {
      const sealed = box.json("eval/outcomes/answers_sealed-chosen.json");
      sealed.rows[0].id = "a-made-up-id";
      box.write("eval/outcomes/answers_sealed-chosen.json", sealed);
      const r = box.run();
      expect(r.status).not.toBe(0);
      expect(r.out).toMatch(/sealed/);
    } finally {
      box.done();
    }
  });
});

// ------------------------------------------------------------------ 21. what the generator's consistency checks compare
test("finding 21: a disagreement between two recorded values says they are recorded values", () => {
  const box = sandbox();
  try {
    const hiw = box.json("eval/outcomes/how_it_works.json");
    hiw.weaviate_version.value = "0.0.0-made-up";
    box.write("eval/outcomes/how_it_works.json", hiw);
    const r = box.run();
    expect(r.status).not.toBe(0);
    expect(r.out).toMatch(/recorded/);
    expect(r.out).not.toMatch(/in EVALUATION\.md$/m);
  } finally {
    box.done();
  }
});
