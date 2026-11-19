/*
 * Client for the question path (POST /api/ask) and what surrounds it:
 * the light health check, the human-check session, and the stored examples
 * that ship with the page.
 *
 * Nothing here stores a question on a server. The conversation is kept by the
 * page in this browser's local storage (see Chat.tsx).
 */
import { API_BASE, stripVectors } from "./api";

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

export type AskAnswer = {
  question: string;
  mode: Mode;
  issues: Issue[];
  passages: Passage[];
  timings: Record<string, number>;
};

export type Example = { lang: "es" | "en"; question: string };
export type StoredExample = Example & { answer: AskAnswer };
export type StoredExamples = { generated: string | null; examples: StoredExample[] };

export const MAX_QUESTION_CHARS = 300;
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
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AskError("unreachable", "The service could not be reached.", 0);
  }
  if (!res.ok) {
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
    throw new AskError(code, message, res.status, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  return (await res.json()) as T;
}

/**
 * Defence in depth: drop anything that looks like an embedding from what the stores returned.
 * Only the store data is filtered. The `mode` block has a key named "embedding" that is a
 * label, not a vector, and the page needs it to say which mode answered.
 */
function clean(answer: AskAnswer): AskAnswer {
  return { ...answer, issues: stripVectors(answer.issues ?? []), passages: stripVectors(answer.passages ?? []) };
}

/** True when the backend answers. Used to show "starting" while a sleeping service wakes. */
export async function health(timeoutMs = 8000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
    return res.ok;
  } catch {
    return false;
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
