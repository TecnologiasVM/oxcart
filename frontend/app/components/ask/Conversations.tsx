"use client";

/*
 * The conversations kept in this browser: a rail beside the thread from 1100 px, the same
 * list as a sheet below that (opened from the bar above a thread).
 *
 * Each conversation is named by its first question, in the visitor's own words and as text:
 * no model call, and nothing a model wrote. The open one is marked by a bar, a tint and a
 * heavier weight, never by colour alone. "New conversation" stays at the top and the foot at
 * the bottom; the list scrolls between them, in two groups when it holds both, "Today" and
 * "Earlier".
 */
import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { Conversation, Keeping } from "@/lib/conversation";
import { lastAt } from "@/lib/conversation";
import type { Labels } from "@/lib/i18n";
import { Confirm, HOW_URL, keepFocusIn, KeepNote, REPO_URL } from "./parts";

export const RAIL_ID = "conversations";

type Props = {
  t: Labels;
  list: Conversation[];
  current: string;
  keeping: Keeping;
  sheet: boolean; // open as a sheet over the page (below 1100 px)
  behind: boolean; // Evidence is open over the page: the rail is out of reach behind it
  confirmAll: boolean;
  deleteAllRef: RefObject<HTMLButtonElement | null>;
  onOpen: (id: string) => void;
  onNew: () => void;
  onHide: () => void;
  onClose: () => void;
  onAskDeleteAll: () => void;
  onDeleteAll: () => void;
  onKeepAll: () => void;
};

const sameDay = (iso: string, now: Date) => {
  const d = new Date(iso);
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
};

export default function Conversations(props: Props) {
  const { t, list, current, keeping, sheet, confirmAll, deleteAllRef } = props;
  const box = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  // opened as a sheet: focus goes into it
  useEffect(() => {
    if (sheet) closeRef.current?.focus();
  }, [sheet]);

  const now = new Date();
  const today = list.filter((c) => sameDay(lastAt(c), now));
  const earlier = list.filter((c) => !sameDay(lastAt(c), now));
  const groups: [string | null, Conversation[]][] = today.length && earlier.length
    ? [[t.today, today], [t.earlier, earlier]]
    : [[null, list]];

  const item = (c: Conversation) => (
    <li key={c.id}>
      <button
        type="button"
        className="rail__item"
        aria-current={c.id === current ? "true" : undefined}
        onClick={() => props.onOpen(c.id)}
        data-testid="conversation"
      >
        {c.id === current && <span className="vh">{t.current}: </span>}
        <span className="rail__t">{c.turns[0]?.question}</span>
      </button>
    </li>
  );

  return (
    <div
      ref={box}
      id={RAIL_ID}
      className="rail"
      role={sheet ? "dialog" : undefined}
      aria-modal={sheet || undefined}
      aria-labelledby="rail-h"
      inert={props.behind}
      data-testid="rail"
      onKeyDown={(e) => {
        if (!sheet) return;
        if (e.key === "Escape") {
          e.preventDefault();
          props.onClose();
          return;
        }
        keepFocusIn(e, box.current);
      }}
    >
      <nav className="rail__in" aria-labelledby="rail-h">
        <div className="rail__head">
          <button type="button" className="rail__hide" aria-expanded="true" aria-controls={RAIL_ID} onClick={props.onHide} data-testid="rail-hide">
            <span className="rail__hide-sign" aria-hidden="true">«</span>{t.hideRail}<span className="vh"> ({t.convs})</span>
          </button>
          <h2 id="rail-h" className="label">{t.convs}</h2>
          <button type="button" ref={closeRef} className="rail__close linkbtn" onClick={props.onClose} data-testid="rail-close">{t.close}</button>
        </div>
        <button type="button" className="newbtn" onClick={props.onNew} data-testid="new-conversation">
          {/* one run of text, so a long name wraps under itself and the sign stays with its first word */}
          <span><span aria-hidden="true">+</span>{"\u00a0"}{t.newConv}</span>
        </button>
        {keeping !== "kept" && <KeepNote text={keeping === "full" ? t.noRoom : t.notKept} />}
        <ol className="rail__list" data-testid="conversation-list">
          {groups.map(([name, items]) =>
            name ? (
              <li key={name} className="rail__group">
                <h3 className="label">{name}</h3>
                <ol>{items.map(item)}</ol>
              </li>
            ) : (
              items.map(item)
            ),
          )}
        </ol>
        {keeping !== "blocked" && (
          <div className="rail__foot">
            {confirmAll ? (
              <Confirm text={t.delAllAsk(list.length)} yes={t.delAllYes} no={t.delAllNo} onYes={props.onDeleteAll} onNo={props.onKeepAll} testId="confirm-all" />
            ) : (
              <>
                <p>{t.kept}</p>
                <button type="button" ref={deleteAllRef} className="linkbtn" onClick={props.onAskDeleteAll} data-testid="delete-all">{t.delAll}</button>
              </>
            )}
          </div>
        )}
        <p className="rail__links"><a href={HOW_URL}>{t.how}</a><a href={REPO_URL}>{t.code}</a></p>
      </nav>
    </div>
  );
}
