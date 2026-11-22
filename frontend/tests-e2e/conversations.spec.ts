import { test, expect, Page } from "@playwright/test";
import {
  ANSWER, THREAD, WRITTEN, ask, box, deleteConversation, lines, mock, newest, noOverflow, panel, seedMany, startNew,
  type SeedConversation,
} from "./helpers";

/*
 * The conversations kept in this browser: the rail, the list under the box and as a sheet,
 * "New conversation", deleting one and all, the rail hidden, storage blocked or full.
 * The service is mocked in the browser; every fixture is made up.
 */

const NOW = () => new Date().toISOString();
const three = (): SeedConversation[] => [
  { id: "c-one", at: NOW(), turns: [{ question: "When was the test issue placed on sale?", written: WRITTEN }] },
  { id: "c-two", at: NOW(), turns: [{ question: "Who printed the second test issue?", written: WRITTEN }, { question: "And when?", written: WRITTEN }] },
  { id: "c-three", at: NOW(), turns: [{ question: "Which test documents mention a perforation?", written: { state: "not_covered" } }] },
];
const rail = (page: Page) => page.getByTestId("rail");
const items = (page: Page) => page.getByTestId("conversation");

async function at(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
}

// ===================================================================== page 02: a returning visitor

test("a returning visitor: the first screen with the kept conversations, a rail from 1100 px", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, three(), "c-new");                              // the open one is new: the first screen
  await mock(page);
  await page.goto("/");
  await expect(rail(page)).toBeVisible();
  await expect(rail(page).getByRole("heading", { name: "Your conversations" })).toBeVisible();
  await expect(items(page)).toHaveCount(3);
  await expect(rail(page).locator("[aria-current]")).toHaveCount(0);  // none of them is open
  await expect(page.getByTestId("new-conversation")).toBeVisible();
  await expect(rail(page)).toContainText("Kept in this browser only.");
  await expect(page.getByTestId("mine")).toBeHidden();                // the rail holds the list here
  await expect(box(page)).toBeVisible();
  // the rail stands beside the first screen, not over it
  const r = (await rail(page).boundingBox())!;
  expect(r.x + r.width).toBeLessThanOrEqual((await box(page).boundingBox())!.x);
  await noOverflow(page, "02, 1440");
});

test("a returning visitor below 1100 px: the list under the box, and all of them one step away", async ({ page }) => {
  await at(page, 820);
  await seedMany(page, [...three(), { id: "c-four", turns: [{ question: "A fourth test question?", written: WRITTEN }] }], "c-new");
  await mock(page);
  await page.goto("/");
  await expect(rail(page)).toBeHidden();
  const mine = page.getByTestId("mine");
  await expect(mine).toBeVisible();
  await expect(mine.getByRole("button")).toHaveCount(4);               // three questions and "All conversations"
  const boxBottom = (await box(page).boundingBox())!;
  expect((await mine.boundingBox())!.y).toBeGreaterThan(boxBottom.y + boxBottom.height);   // under the box
  await page.getByTestId("all-conversations").click();
  await expect(rail(page)).toHaveAttribute("role", "dialog");
  await expect(items(page)).toHaveCount(4);
  await items(page).filter({ hasText: "Which test documents mention a perforation?" }).click();
  await expect(rail(page)).toBeHidden();
  await expect(newest(page)).toContainText("Which test documents mention a perforation?");
  await noOverflow(page, "02, 820");
});

test("a conversation is named by its first question, as text", async ({ page }) => {
  await at(page, 1440);
  const question = "<b>Bold?</b> & <img src=x onerror=alert(1)> and so on";
  await seedMany(page, [{ id: "c-x", turns: [{ question, written: WRITTEN }, { question: "A later question?", written: WRITTEN }] }], "c-x");
  await mock(page);
  await page.goto("/");
  const item = items(page).first();
  await expect(item).toContainText(question);
  await expect(item.locator("b, img")).toHaveCount(0);
  await expect(item).toHaveAttribute("aria-current", "true");          // the open one is marked
  await expect(item).toContainText("open now");                       // and says so to a screen reader
});

// ===================================================================== page 09: the sheet below 1100 px

test("below 1100 px the conversations open as a sheet from the bar; keyboard stays inside, Esc closes", async ({ page }) => {
  await at(page, 820);
  await seedMany(page, three(), "c-two");
  await mock(page);
  await page.goto("/");
  await expect(page.getByTestId("turn")).toHaveCount(2);
  const button = page.getByTestId("conversations-button");
  await expect(button).toBeVisible();
  await expect(page.getByTestId("new-short")).toBeVisible();
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await button.focus();
  await page.keyboard.press("Enter");
  const sheet = rail(page);
  await expect(sheet).toHaveAttribute("role", "dialog");
  await expect(sheet).toHaveAttribute("aria-modal", "true");
  await expect(page.getByTestId("rail-close")).toBeFocused();
  const box1 = (await sheet.boundingBox())!;
  expect([Math.round(box1.width), Math.round(box1.height)]).toEqual([820, 900]);   // the whole screen
  await expect(sheet.locator("[aria-current]")).toContainText("Who printed the second test issue?");
  await expect(sheet.getByRole("link", { name: "How it works" })).toBeVisible();
  for (let i = 0; i < 14; i++) {
    await page.keyboard.press(i % 5 === 4 ? "Shift+Tab" : "Tab");
    expect(await page.evaluate(() => document.getElementById("conversations")?.contains(document.activeElement))).toBe(true);
  }
  await noOverflow(page, "09, 820");
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(button).toBeFocused();
  // choosing one opens it, and focus comes back to the bar
  await button.click();
  await items(page).filter({ hasText: "When was the test issue placed on sale?" }).click();
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page)).toContainText("When was the test issue placed on sale?");
  await expect(button).toBeFocused();
});

// ===================================================================== "New conversation", switching

test("New conversation opens the first screen; the others stay, and each keeps its own turns", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, [three()[0]], "c-one");
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await page.getByTestId("new-conversation").click();
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await expect(box(page)).toBeFocused();                               // ready for the new question
  await expect(items(page)).toHaveCount(1);
  await expect(rail(page).locator("[aria-current]")).toHaveCount(0);
  await ask(page, "A question that starts a second conversation?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).first()).toContainText("A question that starts a second conversation?");   // newest first
  await expect(items(page).first()).toHaveAttribute("aria-current", "true");
  await items(page).nth(1).click();
  await expect(page.getByTestId("turn")).toHaveCount(1);
  await expect(newest(page)).toContainText("When was the test issue placed on sale?");
  // both are kept, with the open one named
  await page.reload();
  await expect(items(page)).toHaveCount(2);
  await expect(rail(page).locator("[aria-current]")).toContainText("When was the test issue placed on sale?");
});

test("opening another conversation closes Evidence, and an answer still on its way lands in its own conversation", async ({ page }) => {
  await at(page, 1600);                                                // the rail and Evidence side by side
  await seedMany(page, three(), "c-one");
  await mock(page);
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/chat", async (route) => {
    await held;
    await route.fulfill({ contentType: "application/x-ndjson", body: lines(WRITTEN, { ...ANSWER, question: "A held question?" }) });
  });
  await page.goto("/");
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
  await expect(panel(page)).toHaveCount(0);
  await ask(page, "A held question?");
  await expect(newest(page).getByTestId("searching-bar")).toBeVisible();
  await items(page).filter({ hasText: "When was the test issue placed on sale?" }).click();
  release();
  await expect(page.getByTestId("turn")).toHaveCount(1);              // not here
  await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
  await expect(page.getByTestId("turn")).toHaveCount(3);
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
});

// ===================================================================== pages 36 and 37: deleting

test("deleting a conversation is asked in place; focus lands on 'Keep it', Esc keeps it", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, three(), "c-one");
  await mock(page);
  await page.goto("/");
  const ask1 = page.getByTestId("delete-one");
  await expect(ask1).toHaveText("Delete this conversation");
  await ask1.click();
  const confirm = page.getByTestId("confirm-one");
  await expect(confirm).toContainText("Delete this conversation? It is kept only in this browser and cannot be recovered.");
  await expect(confirm.getByRole("button", { name: "Keep it" })).toBeFocused();
  await expect(confirm.getByRole("button", { name: "Delete" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);              // in place, no dialog
  await page.keyboard.press("Escape");
  await expect(confirm).toHaveCount(0);
  await expect(ask1).toBeFocused();
  await ask1.click();
  await page.getByTestId("confirm-one").getByRole("button", { name: "Keep it" }).click();
  await expect(ask1).toBeFocused();
  await expect(items(page)).toHaveCount(3);
  // deleted: gone from the rail and from the browser; the others stay
  await deleteConversation(page);
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await expect(items(page)).toHaveCount(2);
  await expect(rail(page)).not.toContainText("When was the test issue placed on sale?");
  await expect(box(page)).toBeFocused();
  const kept = JSON.parse((await page.evaluate(() => window.localStorage.getItem("oxcart-conversations")))!);
  expect(kept.conversations.map((c: { id: string }) => c.id).sort()).toEqual(["c-three", "c-two"]);
});

test("deleting all is asked in place in the rail's foot; focus lands on 'Keep them', and all are gone after it", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, three(), "c-one");
  await mock(page);
  await page.goto("/");
  const all = page.getByTestId("delete-all");
  await all.click();
  const confirm = page.getByTestId("confirm-all");
  await expect(confirm).toContainText("Delete all 3 conversations? They are kept only in this browser and cannot be recovered.");
  await expect(confirm.getByRole("button", { name: "Keep them" })).toBeFocused();
  await noOverflow(page, "37, 1440");
  await page.keyboard.press("Escape");
  await expect(all).toBeFocused();
  await all.click();
  await page.getByTestId("confirm-all").getByRole("button", { name: "Delete all" }).click();
  await expect(rail(page)).toHaveCount(0);                             // nothing kept: no rail, as on a first visit
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await expect(box(page)).toBeFocused();
  const kept = JSON.parse((await page.evaluate(() => window.localStorage.getItem("oxcart-conversations")))!);
  expect(kept.conversations).toEqual([]);
  await page.reload();
  await expect(rail(page)).toHaveCount(0);
});

// ===================================================================== pages 38 and 39: storage

test("storage blocked: one line in the rail, and under the bar where there is no rail; the list holds only this conversation", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    Storage.prototype.getItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };
  });
  await mock(page, { written: WRITTEN });
  await at(page, 1440);
  await page.goto("/");
  await ask(page, "A question in a browser that keeps nothing?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  const note = rail(page).getByTestId("keep-note");
  await expect(note).toHaveText(/This browser is not keeping conversations\. This one will be gone when you close the page\./);
  await expect(items(page)).toHaveCount(1);
  await expect(page.getByTestId("delete-all")).toHaveCount(0);       // nothing kept, nothing to delete there
  await page.getByTestId("new-conversation").click();
  await ask(page, "A second question in the same browser?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  await expect(items(page)).toHaveCount(1);                            // only this one
  await expect(items(page)).toContainText("A second question in the same browser?");
  await at(page, 360);
  await expect(page.locator(".strip").getByTestId("keep-note")).toBeVisible();
  await noOverflow(page, "38, 360");
});

test("storage full: one line says so, the kept conversations stay listed, and deleting makes room again", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, three(), "c-new");
  await page.addInitScript(() => {
    const set = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key: string, value: string) {
      // a browser out of room: the kept conversations can be read but not grow, until some are deleted
      if (key === "oxcart-conversations" && value.length > Number(window.sessionStorage.getItem("room") ?? 1e9)) {
        throw new DOMException("full", "QuotaExceededError");
      }
      return set.call(this, key, value);
    };
  });
  await mock(page, { written: WRITTEN });
  await page.goto("/");
  await page.evaluate(() => window.sessionStorage.setItem("room", String(window.localStorage.getItem("oxcart-conversations")!.length)));
  await ask(page, "A question with no room left to keep it?");
  await expect(newest(page).getByTestId("written-answer")).toBeVisible();
  const note = rail(page).getByTestId("keep-note");
  await expect(note).toContainText("There is no room left in this browser to keep new conversations. This one will be gone when you close the page. Delete some to keep the next.");
  await expect(items(page)).toHaveCount(4);
  await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
  await deleteConversation(page);                                      // room again
  await expect(note).toHaveCount(0);
});

// ===================================================================== two tabs on one store

test("two tabs on one store do not overwrite each other, and a deletion is never written back", async ({ context }) => {
  const [a, b] = [await context.newPage(), await context.newPage()];   // two pages of one context share local storage
  for (const p of [a, b]) {
    await at(p, 1440);
    await mock(p, { written: WRITTEN });
  }
  const stored = () => a.evaluate(() => {
    const store = JSON.parse(window.localStorage.getItem("oxcart-conversations") ?? "{\"conversations\":[]}");
    return (store.conversations as { turns: { question: string }[] }[]).map((c) => c.turns.map((t) => t.question));
  });
  await a.goto("/");
  await b.goto("/");
  await ask(a, "Tab A's made-up question?");
  await expect(newest(a).getByTestId("written-answer")).toBeVisible();
  await ask(b, "Tab B's made-up question?");
  await expect(newest(b).getByTestId("written-answer")).toBeVisible();
  // both are kept, and each rail lists both: at once (the other tab's write is followed) and after a reload
  expect((await stored()).map((c) => c[0]).sort()).toEqual(["Tab A's made-up question?", "Tab B's made-up question?"]);
  await expect(items(a)).toHaveCount(2);
  await expect(items(b)).toHaveCount(2);
  await a.reload();
  await b.reload();
  await expect(items(a)).toHaveCount(2);
  await expect(items(b)).toHaveCount(2);
  // A deletes its conversation after B has saved again: B's stays whole
  await items(a).filter({ hasText: "Tab A's made-up question?" }).click();
  await items(b).filter({ hasText: "Tab B's made-up question?" }).click();
  await ask(b, "Tab B's second made-up question?");
  await expect(b.getByTestId("turn")).toHaveCount(2);
  await expect(newest(b).getByTestId("written-answer")).toBeVisible();
  await deleteConversation(a);
  expect(await stored()).toEqual([["Tab B's made-up question?", "Tab B's second made-up question?"]]);
  await expect(items(b)).toHaveCount(1);                               // gone from the other tab's rail too
  // B saving after A's deletion does not bring it back
  await ask(b, "Tab B's third made-up question?");
  await expect(b.getByTestId("turn")).toHaveCount(3);
  await expect(newest(b).getByTestId("written-answer")).toBeVisible();
  expect(await stored()).toEqual([["Tab B's made-up question?", "Tab B's second made-up question?", "Tab B's third made-up question?"]]);
  // a tab showing a conversation deleted in another tab closes it, and keeps what was being typed
  await items(a).filter({ hasText: "Tab B's made-up question?" }).click();
  await expect(a.getByTestId("turn")).toHaveCount(3);                  // A sees B's turns, written by B
  await box(a).fill("A question being typed in tab A");
  await deleteConversation(b);
  await expect(a.getByTestId("turn")).toHaveCount(0);
  await expect(box(a)).toHaveValue("A question being typed in tab A");
  expect(await stored()).toEqual([]);
  // and two tabs asking in one conversation keep each other's turns
  await box(a).fill("");
  await ask(a, "A shared conversation's first question?");
  await expect(newest(a).getByTestId("written-answer")).toBeVisible();
  await items(b).filter({ hasText: "A shared conversation's first question?" }).click();
  await ask(b, "Asked in the shared conversation from tab B?");
  await expect(newest(b).getByTestId("written-answer")).toBeVisible();
  await ask(a, "Asked in the shared conversation from tab A?");
  await expect(newest(a).getByTestId("written-answer")).toBeVisible();
  expect(await stored()).toEqual([[
    "A shared conversation's first question?", "Asked in the shared conversation from tab B?", "Asked in the shared conversation from tab A?",
  ]]);
});

// ===================================================================== page 40: a long list

test("a long list: 'Today' and 'Earlier', and it scrolls between New conversation and the foot", async ({ page }) => {
  await at(page, 1440);
  const many: SeedConversation[] = Array.from({ length: 24 }, (_, i) => ({
    id: `c-${i}`,
    at: i < 5 ? NOW() : `2026-10-${String(10 + i).padStart(2, "0")}T10:00:00.000Z`,
    turns: [{ question: `Made-up question number ${i + 1}, long enough to take two lines in the rail?`, written: WRITTEN }],
  }));
  await seedMany(page, many, "c-0");
  await mock(page);
  await page.goto("/");
  const groups = rail(page).locator(".rail__group h3");
  await expect(groups).toHaveText(["Today", "Earlier"]);
  await expect(rail(page).locator(".rail__group").first().getByTestId("conversation")).toHaveCount(5);
  const list = page.getByTestId("conversation-list");
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await expect(page.getByTestId("new-conversation")).toBeInViewport();
  await expect(page.getByTestId("delete-all")).toBeInViewport();
  await list.evaluate((el) => el.scrollTo(0, el.scrollHeight));
  await expect(page.getByTestId("new-conversation")).toBeInViewport();   // they stay put
  await expect(page.getByTestId("delete-all")).toBeInViewport();
  await noOverflow(page, "40, 1440");
});

test("the rail stands under the site header, at the top of a long thread and at its foot", async ({ page }) => {
  await at(page, 1440);
  const long = Array.from({ length: 8 }, (_, i) => ({ question: `Made-up question ${i + 1}?`, written: WRITTEN }));
  await seedMany(page, [{ id: "c-long", turns: long }, ...three()], "c-long");
  await mock(page);
  await page.goto("/");
  await expect(page.getByTestId("turn")).toHaveCount(8);
  const gap = () => page.evaluate(() =>
    Math.round(document.getElementById("conversations")!.getBoundingClientRect().top - document.querySelector("header.masthead")!.getBoundingClientRect().bottom));
  const gaps: number[] = [];
  for (const y of [0, 1_000_000]) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(100);
    gaps.push(await gap());
  }
  expect(gaps).toEqual([0, 0]);                                        // never pushed under the header by the footer
});

// ===================================================================== pages 53 to 55: the rail hidden

test("the rail can be hidden: 'Conversations' stands where 'Hide' was, and the choice is remembered", async ({ page }) => {
  await at(page, 1440);
  await seedMany(page, three(), "c-two");
  await mock(page);
  await page.goto("/");
  const hide = page.getByTestId("rail-hide");
  await expect(hide).toHaveAccessibleName("Hide (Your conversations)");
  await expect(hide).toHaveAttribute("aria-expanded", "true");
  const hideBox = (await hide.boundingBox())!;
  await hide.focus();
  await page.keyboard.press("Enter");
  await expect(rail(page)).toBeHidden();
  const back = page.getByTestId("conversations-button");
  await expect(back).toBeVisible();
  await expect(back).toBeFocused();                                    // no travel to undo it
  await expect(page.getByTestId("new-short")).toBeVisible();
  const backBox = (await back.boundingBox())!;
  expect(Math.abs(backBox.x - hideBox.x)).toBeLessThan(40);           // the same corner
  expect(Math.abs(backBox.y - hideBox.y)).toBeLessThan(40);
  expect(await page.evaluate(() => window.localStorage.getItem("oxcart-rail"))).toBe("hidden");
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(2);
  await expect(rail(page)).toBeHidden();
  await expect(back).toBeVisible();
  await noOverflow(page, "54, 1440");
  // hidden, with Evidence open (page 55)
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  await expect(back).toBeVisible();
  await noOverflow(page, "55, 1440");
  await page.getByTestId("evidence-close").click();
  await back.click();
  await expect(rail(page)).toBeVisible();
  await page.reload();
  await expect(rail(page)).toBeVisible();
  expect(await page.evaluate(() => window.localStorage.getItem("oxcart-rail"))).toBe("open");
});

test("with Evidence open the rail steps aside between 1280 and 1599 px; from 1600 px all three stand together", async ({ page }) => {
  await seedMany(page, three(), "c-two");
  await mock(page);
  await at(page, 1440);
  await page.goto("/");
  await expect(rail(page)).toBeVisible();
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  await expect(rail(page)).toBeHidden();
  await expect(page.getByTestId("conversations-button")).toBeVisible();
  expect(await page.evaluate(() => window.localStorage.getItem("oxcart-rail"))).toBeNull();   // nothing was chosen
  await noOverflow(page, "ev, 1440");
  await page.getByTestId("conversations-button").click();              // the way back to the rail closes Evidence
  await expect(panel(page)).toHaveCount(0);
  await expect(rail(page)).toBeVisible();
  await at(page, 1600);
  await newest(page).getByTestId("evidence-button").click();
  await expect(panel(page)).toBeVisible();
  await expect(rail(page)).toBeVisible();
  await expect(page.getByTestId("conversations-button")).toBeHidden();
  const r = (await rail(page).boundingBox())!;
  const q = (await newest(page).locator(".turn__text").boundingBox())!;
  const ev = (await panel(page).boundingBox())!;
  expect(r.x + r.width).toBeLessThanOrEqual(q.x);
  expect(q.x + q.width).toBeLessThanOrEqual(ev.x);
  await noOverflow(page, "ev, 1600");
});

// ===================================================================== widths and pictures

test("no horizontal overflow with conversations kept, at 360, 820, 1100, 1280, 1440 and 1600 px", async ({ page }) => {
  test.setTimeout(120_000);
  await seedMany(page, three(), "c-new");
  await mock(page);
  for (const width of [360, 820, 1100, 1280, 1440, 1600]) {
    await at(page, width);
    await page.goto("/");
    await expect(box(page)).toBeVisible();
    await noOverflow(page, `first screen, ${width}`);
    if (width < 1100) await page.getByTestId("all-conversations").click();   // the sheet
    await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await noOverflow(page, `thread, ${width}`);
    await page.getByTestId("delete-one").click();
    await noOverflow(page, `deleting one, ${width}`);
    await page.keyboard.press("Escape");
    await newest(page).getByTestId("evidence-button").click();
    await noOverflow(page, `evidence, ${width}`);
    await page.keyboard.press("Escape");
    if (width < 1100) {
      await page.getByTestId("conversations-button").click();
      await noOverflow(page, `sheet, ${width}`);
      await page.keyboard.press("Escape");
    } else {
      await page.getByTestId("rail-hide").click();
      await noOverflow(page, `rail hidden, ${width}`);
      await page.getByTestId("conversations-button").click();
    }
    await startNew(page);
  }
});

test("screenshots of the kept conversations at 360, 820, 1440 and 1600 px (kept under test-results, not committed)", async ({ page }) => {
  test.setTimeout(180_000);
  const shot = (name: string, width: number) => page.screenshot({ path: `test-results/screens/conv-${name}-${width}.png` });
  await seedMany(page, [
    ...three(),
    ...Array.from({ length: 12 }, (_, i) => ({ id: `c-old-${i}`, at: "2026-11-01T10:00:00.000Z", turns: [{ question: `An earlier made-up question, number ${i + 1}?`, written: WRITTEN }] })),
  ], "c-new");
  await mock(page);
  for (const width of [360, 820, 1440, 1600]) {
    await at(page, width);
    await page.goto("/");
    await expect(items(page).first()).toBeAttached();                  // the kept conversations are read
    if (await page.getByTestId("turn").count()) await startNew(page);  // the last width's conversation
    await expect(box(page)).toBeVisible();
    await shot("01-first-returning", width);
    if (width < 1100) {
      await page.getByTestId("all-conversations").click();
      await shot("02-sheet", width);
      await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
    } else {
      await items(page).filter({ hasText: "Who printed the second test issue?" }).click();
    }
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await shot("03-thread", width);
    await page.getByTestId("delete-one").click();
    await expect(page.getByTestId("confirm-one").getByRole("button", { name: "Keep it" })).toBeFocused();
    await page.waitForTimeout(150);                                     // the page's own scroll, not the test's
    await shot("04-delete-one", width);
    await page.keyboard.press("Escape");
    if (width >= 1100) {
      await page.getByTestId("delete-all").click();
      await shot("05-delete-all", width);
      await page.keyboard.press("Escape");
      await newest(page).getByTestId("evidence-button").click();
      await shot("06-evidence", width);
      await page.keyboard.press("Escape");
      await page.getByTestId("rail-hide").click();
      await shot("07-rail-hidden", width);
      await newest(page).getByTestId("evidence-button").click();
      await shot("08-rail-hidden-evidence", width);
      await page.keyboard.press("Escape");
      await page.getByTestId("conversations-button").click();
    }
  }
});

// ===================================================================== nothing asked under the pinned box
// (tabbing through a thread is tested in chat.spec.ts)

/** The box pinned at the foot of the window: the form on a phone, the whole dock from 720 px. */
async function pinned(page: Page) {
  return page.evaluate(() => {
    const dock = document.querySelector<HTMLElement>(".dock")!;
    const el = getComputedStyle(dock).display === "contents" ? document.querySelector<HTMLElement>("form.composer")! : dock;
    const r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom };
  });
}
for (const width of [360, 820]) {
  test(`deleting asks in place wholly in view above the pinned box, at ${width} px`, async ({ page }) => {
    await at(page, width);
    await seedMany(page, [{ id: "c-long", turns: THREAD }, ...three()], "c-long");
    await mock(page);
    await page.goto("/");
    await expect(page.getByTestId("turn")).toHaveCount(4);
    await page.getByTestId("delete-one").click();
    const confirm = page.getByTestId("confirm-one");
    await expect(confirm.getByRole("button", { name: "Keep it" })).toBeFocused();
    await page.waitForTimeout(150);
    const box = await pinned(page);
    for (const name of ["Delete", "Keep it"]) {
      const b = (await confirm.getByRole("button", { name, exact: true }).boundingBox())!;
      expect(b.y, `${name}: inside the window`).toBeGreaterThanOrEqual(0);
      expect(b.y + b.height, `${name}: clear of the pinned box`).toBeLessThanOrEqual(box.top);
    }
  });
}
