"use client";

/*
 * The first screen: what the page does, the question box with the privacy line between
 * the box and its button (read, and reached by keyboard, before a question can be sent),
 * the questions to try, and the way to how it works and how it was evaluated.
 *
 * Beside them (under them on a narrow screen) a plate of stamps cropped from the literature, read
 * at run time from the figures host (lib/figures.ts). Without that list nothing is drawn and no
 * room is kept: the first screen is as it was.
 */
import { useEffect, useState } from "react";
import type { Example, StoredExample } from "@/lib/ask";
import { MAX_QUESTION_CHARS } from "@/lib/ask";
import type { Conversation } from "@/lib/conversation";
import type { PlateItem } from "@/lib/figures";
import { figureFailed, figureSrc, plateList, plateShown, useFigureFailures } from "@/lib/figures";
import type { Labels } from "@/lib/i18n";
import { HOW_URL, PrivacyLine } from "./parts";

type Props = {
  t: Labels;
  draft: string;
  setDraft: (value: string) => void;
  submit: (text: string) => void;
  busy: boolean;
  closed: boolean;
  examples: Example[];
  stored: StoredExample[];
  pick: (example: Example) => void;
  onBoxFocus: () => void; // the human check starts here
  mine: Conversation[]; // the kept conversations, newest first: listed here where there is no rail
  onOpen: (id: string) => void;
  onAll: () => void;
};

const MINE_SHOWN = 3;

export default function FirstScreen({ t, draft, setDraft, submit, busy, closed, examples, stored, pick, onBoxFocus, mine, onOpen, onAll }: Props) {
  const left = MAX_QUESTION_CHARS - draft.length;
  const [plate, setPlate] = useState<PlateItem[]>([]);
  useEffect(() => {
    let live = true;
    plateList().then((items) => live && setPlate(items));
    return () => {
      live = false;
    };
  }, []);
  return (
    <>
      <div className="first__part first__head">
        <h1>{t.title}</h1>
        <p className="first__what">{t.what}</p>
        <form
          className="ask-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit(draft);
          }}
        >
          <label className="label" htmlFor="q">{t.question}</label>
          <textarea
            id="q"
            rows={2}
            maxLength={MAX_QUESTION_CHARS}
            placeholder={t.placeholder}
            value={draft}
            disabled={closed}
            onChange={(e) => setDraft(e.target.value)}
            onFocus={onBoxFocus}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(draft);
              }
            }}
          />
          <PrivacyLine t={t} />
          <div className="ask-form__row">
            <button type="submit" className="ask-btn ask-btn--primary" disabled={busy || closed || !draft.trim()}>
              {busy ? t.asking : t.ask}
            </button>
            {left <= 60 && <span className="ask-form__left" data-testid="chars-left">{t.left(left)}</span>}
          </div>
        </form>
      </div>
      {/* the human check's element stands between these two parts (Chat.tsx) */}
      <div className="first__part first__more">
        {mine.length > 0 && (
          // below the rail's width the kept conversations stand under the box
          <section className="mine" aria-labelledby="mine-h" data-testid="mine">
            <h2 id="mine-h" className="label">{t.convs}</h2>
            <p className="examples__note">{t.kept}</p>
            <ul>
              {mine.slice(0, MINE_SHOWN).map((c) => (
                <li key={c.id}>
                  <button type="button" onClick={() => onOpen(c.id)}>{c.turns[0]?.question}</button>
                </li>
              ))}
            </ul>
            <p className="mine__all"><button type="button" className="linkbtn" onClick={onAll} data-testid="all-conversations">{t.allConvs}</button></p>
          </section>
        )}
        {examples.length > 0 && (
          <section className="examples" aria-labelledby="examples-h">
            <h2 id="examples-h" className="label">{t.examples}</h2>
            {stored.length > 0 && <p className="examples__note">{t.storedAll}</p>}
            <ul>
              {examples.map((example) => (
                <li key={example.question}>
                  <button type="button" className="example" lang={example.lang} onClick={() => pick(example)} disabled={busy}>
                    {example.question}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <p className="first__how"><a href={HOW_URL}>{t.evalLink}</a></p>
      </div>
      {plate.length > 0 && <Plate items={plate} caption={t.plateCaption} />}
    </>
  );
}

/**
 * The plate: a ruled grid, each crop at its own proportions in a square cell, never larger than its
 * pixels. Decoration beside the title: the pictures have empty alt text and the caption says what
 * they are. The cells are square, so their room is held before any file arrives.
 */
function Plate({ items: all, caption }: { items: PlateItem[]; caption: string }) {
  useFigureFailures(); // a picture whose file fails leaves the plate, and the plate goes when none is left
  const items = plateShown(all);
  if (items.length === 0) return null;
  return (
    <figure className="first__part plate" data-testid="plate">
      <ul className="plate__grid" aria-hidden="true">
        {items.map((item, i) => {
          const src = figureSrc(item.digest);
          return src ? (
            <li key={`${i}-${item.digest}`}>
              <img src={src} width={item.width} height={item.height} style={{ maxWidth: item.width, maxHeight: item.height }} loading="lazy" decoding="async" alt="" onError={() => figureFailed(item.digest)} />
            </li>
          ) : null;
        })}
      </ul>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
