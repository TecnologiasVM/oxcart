"use client";

/*
 * The first screen: what the page does, the question box with the privacy line between
 * the box and its button (read, and reached by keyboard, before a question can be sent),
 * the questions to try, and the way to how it works and how it was evaluated.
 */
import type { Example, StoredExample } from "@/lib/ask";
import { MAX_QUESTION_CHARS } from "@/lib/ask";
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
};

export default function FirstScreen({ t, draft, setDraft, submit, busy, closed, examples, stored, pick, onBoxFocus }: Props) {
  const left = MAX_QUESTION_CHARS - draft.length;
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
    </>
  );
}
