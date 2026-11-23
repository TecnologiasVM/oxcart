/*
 * The web part of a turn (backend: app/web_step.py), asked for only by a page built with
 * NEXT_PUBLIC_WEB on (1, true, yes or on). Off, a ticket in a chat reply is ignored, no request is
 * made, and the page and its privacy paragraph are what they were before the web part existed: so a
 * search can only happen from a page whose privacy paragraph names the search service.
 *
 * The request is made once, by the page that asked the question, after the answer is on screen. A turn
 * read back from storage never asks again: its ticket is not kept, and a search under way is not kept.
 *
 * Everything in a web part is text: the sentences, the titles, the hosts. A result's address becomes
 * a link only when the page has checked it again here (https, no user name, a host that parses).
 */
import { API_BASE } from "./api";
import type { AnswerSentence, WrittenAnswer } from "./ask";

/** Whether a build setting's value turns the web part on. */
export const webOn = (raw: string | undefined) => ["1", "true", "yes", "on"].includes((raw ?? "").trim().toLowerCase());
export const WEB = webOn(process.env.NEXT_PUBLIC_WEB);

/** What a chat reply's answer carries when the web may be searched for it. */
export type WebTicket = { ticket: string; expires_in: number };
/** One cited result: its title and host as text, its address. */
export type WebResult = { n: number; title: string; host: string; url: string };
/**
 * The web part: "searching" only while the page waits (never kept); "ok" with sentences and the cited
 * results; "nothing" (the web had nothing to add); "unavailable" (no search, it failed, or the searches are
 * used up) and "out_of_scope" (the web call judged the question outside the scope), for which nothing is drawn.
 */
export type WebPart =
  | { state: "searching" }
  | { state: "ok"; sentences: AnswerSentence[]; results: WebResult[] }
  | { state: "nothing" | "unavailable" | "out_of_scope" };

/** The ticket to ask with, when this build asks for the web and the answer carries one. */
export function ticketOf(written: (WrittenAnswer & { web?: unknown }) | undefined, enabled: boolean = WEB): string | null {
  const web = written?.web as Partial<WebTicket> | undefined;
  return enabled && web && typeof web.ticket === "string" && web.ticket ? web.ticket : null;
}

/** The written answer as it is kept: without the ticket, which is good for two minutes and once. */
export function withoutTicket<T extends object>(written: T): T {
  const { web: _w, ...rest } = written as T & { web?: unknown };
  return rest as T;
}

/** The address as a link, when it is https with no user name or password and a host that parses; else null. */
export function linkOf(url: unknown): string | null {
  // no space, control character or backslash, and a host right after the scheme ("https:///x" is not one)
  if (typeof url !== "string" || url.length > 300 || /[\s\u0000-\u001f\u007f\\]/.test(url) || !/^https:\/\/[^/]/i.test(url)) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.username || parsed.password || !parsed.hostname) return null;
    return parsed.href;
  } catch {
    return null;
  }
}

/** "PDF" is read from the address's ending, before any query or fragment. */
export const isPdf = (url: string) => /\.pdf$/i.test(url.split(/[?#]/)[0]);

/** A web part as received or read back, kept only in its known shape; anything else is "unavailable". */
export function keepWeb(value: unknown): WebPart {
  const part = value as { state?: unknown; sentences?: unknown; results?: unknown } | null;
  if (!part || typeof part !== "object") return { state: "unavailable" };
  if (part.state === "nothing" || part.state === "out_of_scope" || part.state === "unavailable") return { state: part.state };
  if (part.state !== "ok" || !Array.isArray(part.sentences) || !Array.isArray(part.results)) return { state: "unavailable" };
  const results = (part.results as Partial<WebResult>[])
    .filter((r) => r && Number.isInteger(r.n) && typeof r.title === "string" && typeof r.host === "string" && typeof r.url === "string")
    .map((r) => ({ n: r.n!, title: r.title!, host: r.host!, url: r.url! }));
  const known = new Set(results.map((r) => r.n));
  const sentences = (part.sentences as Partial<AnswerSentence>[])
    .filter((s) => s && typeof s.text === "string" && Array.isArray(s.cites))
    .map((s) => ({ text: s.text!, cites: s.cites!.filter((n) => known.has(n)) }))
    .filter((s) => s.cites.length > 0);
  return sentences.length ? { state: "ok", sentences, results } : { state: "nothing" };
}

/** One web part, for the question as it was searched, the answer's text and the ticket. Never throws. */
export async function askWeb(question: string, answer: string, ticket: string, session: string | null): Promise<WebPart> {
  try {
    const res = await fetch(`${API_BASE}/api/chat/web`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(session ? { "X-Oxcart-Session": session } : {}) },
      body: JSON.stringify({ question, answer, ticket }),
    });
    if (!res.ok) return { state: "unavailable" };
    return keepWeb(await res.json());
  } catch {
    return { state: "unavailable" };
  }
}
