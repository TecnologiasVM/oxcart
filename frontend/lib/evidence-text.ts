/*
 * Text the page builds from the evidence's own fields (never from what the model wrote):
 * dates written in the visitor's language, an act as one line, and a source's name.
 */
import type { AnswerSource, AskAnswer, IssueCard } from "./ask";
import type { Lang } from "./i18n";

const MONTHS: Record<Lang, string[]> = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  es: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
};

/**
 * A date from card data in words: "1889-09-14" -> "14 September 1889" or "14 de septiembre
 * de 1889"; "1889-09" -> "September 1889". Anything that is not such a date is left as it is.
 */
export function formatDate(value: string, lang: Lang): string {
  const m = value.trim().match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!m) return value;
  const [, year, mm, dd] = m;
  const month = MONTHS[lang][Number(mm) - 1];
  const day = dd === undefined ? null : Number(dd);
  if (!month || (day !== null && (day < 1 || day > 31))) return value;
  const de = lang === "es" ? " de " : " ";
  return day === null ? `${month}${de}${year}` : `${day}${de}${month}${de}${year}`;
}

/** An act as one line: its id, its type only when the id does not already say it, and its date. */
export function actLine(act: NonNullable<IssueCard["acts"]>[number], lang: Lang): string {
  const id = act.id?.trim() ?? "";
  const type = act.type?.trim() ?? "";
  const named = type && !id.toLowerCase().includes(type.toLowerCase()) ? (id ? `${id} (${type})` : type) : id;
  const date = act.date ? formatDate(act.date, lang) : "";
  return [named, date].filter(Boolean).join(", ") || "–";
}

/**
 * A cited source's name, built from the evidence it points at and in the page's words; the
 * backend's own title (written in English) only when that evidence is missing.
 */
export function sourceTitle(source: AnswerSource, evidence: AskAnswer | undefined, words: { page: string; catalogueCard: string }): string {
  if (source.kind === "passage") {
    const p = evidence?.passages[source.index];
    if (p) return `${p.doc_id?.trim() || "?"}, ${words.page} ${p.page ?? "?"}`;
  } else {
    const issue = evidence?.issues[source.index];
    if (issue) return `${words.catalogueCard}: ${issue.title || issue.issue_id}`;
  }
  return source.title;
}
