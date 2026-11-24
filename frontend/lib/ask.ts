/*
 * Client for the question path (POST /api/ask) and what surrounds it:
 * the light health check, the human-check session, and the stored examples
 * that ship with the page.
 *
 * Nothing here stores a question on a server. The conversation is kept by the
 * page in this browser's local storage (see lib/conversation.ts).
 */
import { API_BASE, stripVectors } from "./api";
import type { Figure } from "./figures";
import { keepFigures } from "./figures";
import type { WebTicket } from "./web";

export type Mode = {
  embedding: "ok" | "failed" | "not configured" | string;
  catalogue: "vector index" | "full-text index" | "unavailable" | string;
  literature: "vector" | "keyword" | "unavailable" | string;
};

export type Passage = {
  doc_id: string | null;
  page: number | null;
  chunk_type?: string | null;
  text: string;
  clipped: boolean;
  score: number | null;
  lang?: "es" | "en" | null; // the passage's own language, told by its words; only when both languages were searched
  found?: string[]; // which of the two searches returned it: "question", "translation" or both
  figures?: Figure[]; // the figures the passage's page carries, by id (lib/figures.ts); only when the backend names some
};

export type CardStamp = {
  catalog_no?: string | null;
  value?: string | number | null;
  unit?: string | null;
  color?: string | null;
  quantity?: string | number | null;
};

export type IssueCard = {
  issue_id?: string;
  title?: string | null;
  section?: string | null;
  perforation?: string | null;
  printers?: string[];
  acts?: { type?: string | null; id?: string | null; date?: string | null }[];
  dates?: Record<string, string | null>;
  stamps?: CardStamp[];
};

export type Issue = {
  issue_id: string;
  title: string | null;
  score: number;
  matched_by: string[];
  card: IssueCard | null;
};

/** One of the two texts the literature was searched with: the question, then the question in the other language. */
export type Search = { question: string; lang: "es" | "en"; state: "ok" | "unavailable" };

export type AskAnswer = {
  question: string;
  mode: Mode;
  issues: Issue[];
  passages: Passage[];
  searches?: Search[]; // both texts, when the literature was searched in both languages
  timings: Record<string, number>;
};

/** One sentence of a written answer, with the numbers of the sources it cites. */
export type AnswerSentence = { text: string; cites: number[] };
/** A card or passage of the evidence that the answer cites, and the text it was cited for. */
export type AnswerSource = { n: number; kind: "issue" | "passage"; index: number; title: string; quotes: string[] };
/**
 * The written answer. `state` is "ok" (with sentences and sources), "not_covered" (the
 * evidence does not answer the question), "out_of_scope" (with the backend's ASK_WEB: the
 * question is outside what Oxcart covers), or the reason nothing was written.
 */
export type WrittenAnswer = {
  state: string;
  sentences?: AnswerSentence[];
  sources?: AnswerSource[];
  counts?: AnswerCounts;
  covers?: "all" | "part"; // with the backend's ASK_WEB: whether the answer covers all of the question or part
  web?: WebTicket; // with ASK_WEB: the ticket for the web part (lib/web.ts); never kept
};
/** What the check of the citations found: sentences written and removed, citations given and not holding. */
export type AnswerCounts = {
  sentences: number;
  sentences_without_citation: number;
  citations: number;
  citations_that_do_not_hold: number;
};
/** One model call made for a question: what it was for, how it ended, its tokens and its seconds. */
export type ModelCall = { purpose: string; state: string; input_tokens: number; output_tokens: number; seconds: number };
/** What the chat route resolves to: the written answer and the model calls made for it. */
export type ChatResult = { answer: WrittenAnswer; calls: ModelCall[] };
/** An earlier turn of a conversation, sent with a follow-up. */
export type ThreadTurn = { question: string; answer: string };
export const THREAD_TURNS = 3;
export const THREAD_ANSWER_CHARS = 1200;

export type Example = { lang: "es" | "en"; question: string };
export type StoredExample = Example & { answer: AskAnswer };
export type StoredExamples = { generated: string | null; examples: StoredExample[] };

export const MAX_QUESTION_CHARS = 300;

/*
 * How long the page waits, in ms, before it stops waiting and says so. Each is above what the backend itself
 * allows (backend/app/settings.py): its search gives up at 25 s (ASK_TIMEOUT_SECONDS), a rewrite at 5 s and a
 * model call at 12 s (ANSWER_TIMEOUT_SECONDS, no retry), and a service asleep takes about half a minute to wake
 * while its host holds the request.
 *   evidence  from sending a question to its evidence: waking, a rewrite and the search, with room (90 s)
 *   answer    from the evidence to the written answer: one model call, with room (45 s)
 *   request   any other request of the question path: a session, the evidence-only route (90 s)
 * What has arrived when a wait ends is kept: evidence without its answer stays on the page.
 */
export const DEADLINES = { evidence: 90_000, answer: 45_000, request: 90_000 };
export const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || "";

/** A refusal from the backend: a code the page can translate, and a wait when there is one. */
export class AskError extends Error {
  code: string;
  status: number;
  retryAfter: number | null;
  constructor(code: string, message: string, status: number, retryAfter: number | null = null) {
    super(message);
    this.name = "AskError";
    this.code = code;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

async function post<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEADLINES.request);
  try {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      throw controller.signal.aborted ? new AskError("timeout", "The request took too long.", 0) : new AskError("unreachable", "The service could not be reached.", 0);
    }
    if (!res.ok) throw await refusal(res);
    try {
      return (await res.json()) as T;
    } catch {
      throw new AskError(controller.signal.aborted ? "timeout" : "unreachable", "The reply did not arrive whole.", 0);
    }
  } finally {
    clearTimeout(timer);
  }
}

/** What a response that is not a success says, as an error the page can translate. */
async function refusal(res: Response): Promise<AskError> {
  let code = "http_error";
  let message = res.statusText;
  try {
    const data = (await res.json()) as { error?: string; message?: string };
    code = data.error || code;
    message = data.message || message;
  } catch {
    /* not JSON: a gateway answered instead of the backend */
  }
  const retry = Number(res.headers.get("Retry-After"));
  return new AskError(code, message, res.status, Number.isFinite(retry) && retry > 0 ? retry : null);
}

/**
 * Defence in depth: drop anything that looks like an embedding from what the stores returned.
 * Only the store data is filtered. The `mode` block has a key named "embedding" that is a
 * label, not a vector, and the page needs it to say which mode answered.
 */
function clean(answer: AskAnswer): AskAnswer {
  const passages = stripVectors(answer.passages ?? []).map((p) => {
    // a passage's figures are kept only when well formed: an id and a pixel size, never an address
    const { figures, ...rest } = p;
    const kept = keepFigures(figures);
    return kept ? { ...rest, figures: kept } : rest;
  });
  const { searches, ...rest } = answer;
  const both = keepSearches(searches);
  return { ...rest, issues: stripVectors(answer.issues ?? []), passages, ...(both ? { searches: both } : {}) };
}

/** The two searched texts, kept only when they are what the backend sends: two entries, each a text and a language. */
function keepSearches(value: unknown): Search[] | null {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const out: Search[] = [];
  for (const v of value) {
    if (!v || typeof v.question !== "string" || !v.question.trim() || (v.lang !== "es" && v.lang !== "en")) return null;
    out.push({ question: v.question, lang: v.lang, state: v.state === "unavailable" ? "unavailable" : "ok" });
  }
  return out;
}

/**
 * Where the service is, from its health route:
 *
 * - "no answer": nothing came back in time. The service is asleep and waking, or gone.
 * - "connecting": the backend answers, and is still opening its link to the graph, its
 *   literature client or its connection for embeddings.
 * - "ready": none of the three is "connecting" (each is connected, or gave up: the page
 *   then says per answer what could not be reached).
 *
 * Used to tell the visitor what is happening while the service wakes.
 */
export type ServiceState = "no answer" | "connecting" | "ready";

export async function serviceState(timeoutMs = 8000): Promise<ServiceState> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
    if (!res.ok) return "no answer";
    const body = (await res.json().catch(() => ({}))) as { graph?: string; literature?: string; embedding?: string };
    return [body.graph, body.literature, body.embedding].includes("connecting") ? "connecting" : "ready";
  } catch {
    return "no answer";
  } finally {
    clearTimeout(timer);
  }
}

/** Trade a passed human check for a session token. */
export function openSession(token: string): Promise<{ session: string; expires_in: number }> {
  return post("/api/session", { token });
}

export async function ask(question: string, session: string | null): Promise<AskAnswer> {
  return clean(await post<AskAnswer>("/api/ask", { question }, session ? { "X-Oxcart-Session": session } : {}));
}

/**
 * One question through the route that also writes an answer. The response is lines of
 * JSON sent as they are ready: the evidence first (`onEvidence` is called with it, and with
 * whether a follow-up was rewritten before it was searched; the evidence itself says which two
 * texts were searched, `searches`), then the written answer and
 * the model calls made for it, which is what this resolves to.
 *
 * `thread` holds the earlier turns of the conversation when the question is a follow-up;
 * it is kept by this browser and is the only memory the conversation has.
 *
 * Throws an AskError with code "no_chat_route" when the backend has no such route, so the
 * caller can ask the evidence-only route instead.
 */
export async function chat(
  question: string,
  thread: ThreadTurn[],
  session: string | null,
  onEvidence: (answer: AskAnswer, rewritten: boolean) => void,
): Promise<ChatResult> {
  // one deadline for the evidence, then a new one for the answer; when one passes, the request is cancelled
  const controller = new AbortController();
  let timer = setTimeout(() => controller.abort(), DEADLINES.evidence);
  const ended = new Promise<null>((resolve) => controller.signal.addEventListener("abort", () => resolve(null), { once: true }));
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(session ? { "X-Oxcart-Session": session } : {}) },
      body: JSON.stringify({ question, thread }),
      signal: controller.signal,
    });
  } catch {
    clearTimeout(timer);
    throw controller.signal.aborted ? new AskError("timeout", "The search took too long.", 0) : new AskError("unreachable", "The service could not be reached.", 0);
  }
  if (res.status === 404 || res.status === 405) {
    clearTimeout(timer);
    throw new AskError("no_chat_route", "", res.status);
  }
  if (!res.ok) {
    clearTimeout(timer);
    throw await refusal(res);
  }

  let seen = false;
  let written: WrittenAnswer | null = null;
  let calls: ModelCall[] = [];
  const take = (line: string) => {
    if (!line.trim()) return;
    const data = JSON.parse(line) as { type?: string; evidence?: AskAnswer; rewritten?: boolean; answer?: WrittenAnswer; calls?: ModelCall[] };
    if (data.type === "evidence" && data.evidence) {
      seen = true;
      clearTimeout(timer);
      timer = setTimeout(() => controller.abort(), DEADLINES.answer);
      onEvidence(clean(data.evidence), Boolean(data.rewritten));
    } else if (data.type === "answer" && data.answer) {
      written = data.answer;
      calls = Array.isArray(data.calls) ? data.calls : [];
    }
  };
  try {
    const reader = res.body?.getReader();
    if (!reader) {
      const text = await Promise.race([res.text(), ended]);
      if (text !== null) text.split("\n").forEach(take);
    } else {
      const decoder = new TextDecoder();
      let rest = "";
      for (;;) {
        // a stream that stops sending ends at the deadline, whether or not the request honours the abort
        const step = await Promise.race([reader.read(), ended]);
        if (step === null) {
          reader.cancel().catch(() => {});
          break;
        }
        const { done, value } = step;
        rest += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const lines = rest.split("\n");
        rest = lines.pop() ?? "";
        lines.forEach(take);
        if (done) break;
      }
      take(rest);
    }
  } catch {
    /* the connection broke: what arrived before it stands */
  } finally {
    clearTimeout(timer);
  }
  if (!seen) throw controller.signal.aborted ? new AskError("timeout", "The search took too long.", 0) : new AskError("unreachable", "The service could not be reached.", 0);
  return { answer: written ?? { state: "failed" }, calls };
}

/**
 * The examples that ship with the page, each with the evidence it returned when
 * the page was built. Served as a static file beside the page, so a visitor sees
 * real evidence while the service wakes, and when it is asleep or gone.
 */
export async function storedExamples(): Promise<StoredExamples> {
  try {
    const res = await fetch("/stored-examples.json");
    if (!res.ok) return { generated: null, examples: [] };
    const data = (await res.json()) as StoredExamples;
    const examples = Array.isArray(data.examples) ? data.examples : [];
    return { generated: data.generated ?? null, examples: examples.map((e) => ({ ...e, answer: clean(e.answer) })) };
  } catch {
    return { generated: null, examples: [] };
  }
}

/** Example questions from the backend, for when the page was built without stored ones. */
export async function liveExamples(): Promise<Example[]> {
  try {
    const res = await fetch(`${API_BASE}/api/ask/examples`);
    if (!res.ok) return [];
    const data = (await res.json()) as { examples?: Example[] };
    return data.examples ?? [];
  } catch {
    return [];
  }
}
