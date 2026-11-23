/*
 * The words of the page "How it works" (app/how-it-works), in English and Spanish. The question page's words
 * are in i18n.ts; this page shares its header's ("How it works", "Source code", the language button).
 *
 * No number is written here: every count, cost, wait, limit and version comes from lib/how-figures.json
 * (scripts/how-figures.mjs), already formatted for the page's language, and enters a sentence as a parameter.
 * The words are the drawing's (a2/80, a2/81), with the changes made when the page was built.
 */
import type { Lang } from "./i18n";

type S = string;

/** Numbers in the page's language: es-CR on the Spanish page (41 126, 0,0007), English otherwise. */
export function numbers(lang: Lang) {
  const locale = lang === "es" ? "es-CR" : "en";
  const fixed = (digits: number) => new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const whole = new Intl.NumberFormat(locale);
  const n = (x: number) => whole.format(x);
  return {
    n,
    of: (a: number, b: number) => (lang === "es" ? `${n(a)} de ${n(b)}` : `${n(a)} of ${n(b)}`),
    usd: (x: number) => fixed(4).format(x),
    seconds: (x: number) => fixed(2).format(x),
    two: (x: number) => fixed(2).format(x),
    /** "2026-11-23" as "23 November 2026" / "23 de noviembre de 2026" */
    date: (iso: string) =>
      new Intl.DateTimeFormat(lang === "es" ? "es-CR" : "en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${iso}T12:00:00Z`)),
    /** "2026-11" as "November 2026" / "noviembre de 2026" */
    month: (ym: string) =>
      new Intl.DateTimeFormat(lang === "es" ? "es-CR" : "en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${ym}-15T12:00:00Z`)),
  };
}
export type Numbers = ReturnType<typeof numbers>;

/** A model's id as its name: "claude-haiku-5-5" -> "Claude Haiku 5.5"; any other id is shown as it is. */
export function modelName(id: string): string {
  const m = /^claude-([a-z]+)-(\d+)-(\d+)$/.exec(id);
  return m ? `Claude ${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}` : id;
}

type Node = { name: S; sub: S[]; tech?: S };
type NodeArgs = { writer: S; embedding: S; issues: S; passages: S; cards: S; shown: S };
type Step = { h: S; text: (x: StepArgs) => S };
type StepArgs = { writer: S; numbers: S; issues: S; passages: S; graphIndex: S; litIndex: S; litCompression: S; graphSimilarity: S; litSimilarity: S };
type Lead<F> = { lead: S; text: F };

export type HowWords = {
  title: S;
  lead: (x: { issues: S; stamps: S; passages: S; embedding: S; writer: S }) => S;
  pipeH: (steps: number) => S;
  pipeTitle: S;
  pipeDesc: S;
  node: (x: NodeArgs) => Record<"q" | "s1" | "s2" | "cat" | "lit" | "ev" | "s3" | "s4" | "ans" | "s5" | "web", Node>;
  legend: (web: boolean) => S;
  steps: Record<"s1" | "s2" | "s3" | "s4" | "s5", Step>;
  pipeNote: S;
  whyH: S;
  why: S;
  traceLabel: (date: S) => S;
  traceAsked: (after: S, askedLang: Lang) => S;
  traceSearched: S;
  traceCols: { issue: S; score: S; printer: S };
  traceAnswer: S;
  source: S;
  whyAlone: (fullText: S, vector: S, spanish: S) => S;
  resH: S;
  resSet: (all: S, cat: S, lit: S, oos: S) => S;
  issueFound: Lead<(three: S) => S>;
  pageFound: Lead<(k: S, drafts: S, withDrafts: S) => S>;
  catAnswers: Lead<(supported: S) => S>;
  litAnswers: Lead<(part: number, partS: S, not: number, notS: S, notWritten: number, notWrittenS: S) => S>;
  asks: (asks: S) => S;
  removed: Lead<(notHold: S, of: S) => S>;
  limitsLead: S;
  sealedNone: (n: S, of: S, a: S, b: S, ca: S, cb: S) => S;
  sealedSome: (n: S, of: S, fa: S, fb: S, a: S, b: S, ca: S, cb: S) => S;
  limitsRest: (low: S, high: S) => S;
  limitsWeb: S;
  limitsTickets: (n: number, nS: S, of: S) => S;
  judH: S;
  judges: (first: S, second: S, sample: S, grade: S, answers: S) => S;
  judgesAnswers: (judge: S, answers: S, same: S, kappa: S) => S;
  triedH: S;
  triedWhole: (all: S, kept: S, keptAnswered: S) => S;
  triedHybrid: (same: boolean, vector: S) => S;
  triedOff: S;
  triedStrong: (model: S, inFull: S, of: S, served: S, servedInFull: S, times: S, usd: S, servedUsd: S) => S;
  range: (a: S, b: S) => S;
  costH: S;
  costMean: (max: S) => S;
  costAfter: (usd: S) => S;
  waitEvidence: S;
  waitAnswer: (p95: S) => S;
  waitsWhere: { host: S; development: S };
  sleeps: S;
  safeH: S;
  spend: Lead<(usd: S, month: S) => S>;
  use: Lead<(minute: S, day: S, calls: S, low: S, chars: S) => S>;
  useWeb: (searches: S) => S;
  readOnly: Lead<S>;
  scope: Lead<(none: S) => S>;
  disk: Lead<(kept: S) => S>;
  privH: S;
  stackH: S;
  stack: {
    steps: S; graph: S; lit: S; backend: S; page: S; tests: S;
    graphV: (v: S) => S;
    litV: (v: S) => S;
    backendV: (fastapi: S, python: S) => S;
    pageV: (next: S, react: S, ts: S) => S;
    testsV: (pytest: S, py: S, pw: S, browser: S) => S;
  };
  stackNote: S;
  moreH: S;
  linkEval: S;
};

/** A similarity's name in Spanish, when the page knows it; any other as the stores give it. */
const es = (similarity: S) => ({ cosine: "coseno" } as Record<string, string>)[similarity] ?? similarity;

export const HOW: Record<Lang, HowWords> = {
  en: {
    title: "How it works, and how it was measured",
    lead: ({ issues, stamps, passages, embedding, writer }) =>
      `Oxcart answers questions about Costa Rican stamps, in Spanish or English, from two sources: the Mena catalogue, held as a graph in Neo4j (${issues} issues, ${stamps} stamps), and ${passages} passages of scanned philatelic literature, held with their vectors in Weaviate. A question becomes one vector (OpenAI ${embedding}) and is searched in both at once. ${writer} writes a short answer with citations, and a sentence is shown only if its citation holds. The steps are a LangGraph graph in a FastAPI backend in Python; the page is Next.js and React in TypeScript.`,
    // 2. the path of a question
    pipeH: (steps: number) => `A question, in ${steps === 5 ? "five" : "four"} steps`,
    pipeTitle: "Diagram: the path of a question, from the question to the answer shown.",
    pipeDesc: "The numbered list after it says the same.",
    node: (x: NodeArgs) => ({
      q: { name: "Question", sub: ["in Spanish or English"] },
      s1: { name: "Rewritten", sub: ["every question after the first:", "read against the conversation,", "rewritten only if it points back"], tech: x.writer },
      s2: { name: "Searched", sub: ["one vector, two searches at once"], tech: `OpenAI ${x.embedding}` },
      cat: { name: "Catalogue", sub: ["as a graph", `${x.issues} issues`], tech: "Neo4j" },
      lit: { name: "Literature", sub: ["by vectors", `${x.passages} passages`], tech: "Weaviate" },
      ev: { name: "Evidence", sub: [`up to ${x.cards} cards and ${x.shown} passages, shown first`] },
      s3: { name: "Written with citations", sub: ["a short answer, only from the evidence"], tech: `${x.writer}, citations on` },
      s4: { name: "Citations checked", sub: ["a sentence with none is removed"], tech: "no model" },
      ans: { name: "Answer", sub: ["only sentences whose citation holds"] },
      s5: { name: "Searched on the web", sub: ["only when our sources cover part", "of a question, or none of it"], tech: "Tavily, then the same writer" },
      web: { name: "From the web", sub: ["not from the catalogue or the literature"] },
    }),
    legend: (web: boolean) =>
      `Tinted: what is on the page. Outlined: a step in the backend. ${
        web
          ? "Dashed: a step for some questions only: step 1 for every question after the first, which is rewritten only when it points back; step 5 when our sources cover part of a question, or none of it."
          : "Dashed: for every question after the first, which is rewritten only when it points back."
      }`,
    steps: {
      s1: { h: "Rewritten", text: ({ writer }) =>
        `Every question after the first is read against the conversation and rewritten only when it points back: ${writer} rewrites “And who printed it?” so that it stands alone. A first question is searched as it is typed.` },
      s2: { h: "Searched", text: ({ numbers, issues, passages, graphIndex, litIndex, litCompression, graphSimilarity, litSimilarity }) =>
        `One vector (${numbers} numbers) serves two searches at once. The catalogue, a graph in Neo4j, returns up to ${issues} issues with their cards, from two ${graphIndex} vector indexes by ${graphSimilarity} (one of an issue's whole text, quantized; one of its title, years and section, not quantized), or from its full-text index when no vector can be made. The literature, in Weaviate, returns the ${passages} nearest passages from an ${litIndex} vector index with ${litCompression} compression, by ${litSimilarity}. The page shows this evidence first.` },
      s3: { h: "Written with citations", text: ({ writer }) =>
        `${writer} writes a short answer only from that evidence; each piece comes back with the exact text it cites.` },
      s4: { h: "Citations checked", text: () =>
        "No model. A sentence stays only if its cited text is in a shown card or passage; one with no citation is removed." },
      s5: { h: "Searched on the web", text: ({ writer }) =>
        `Only when our sources cover part of a question, or none of it: the question is searched on the web (Tavily), and ${writer} writes a short part from the pages found, with the same check of its citations. It stands in a block of its own under the answer: from the web, not from the catalogue or the literature. A question outside the scope gets no search.` },
    },
    pipeNote: "The server keeps nothing between two requests: a conversation lives in the browser.",
    // 3. why a graph and vectors together
    whyH: "Why a graph and vectors together",
    why: "Vectors find what a question is about, in either language. The graph holds each issue's facts as stored values: dates, printers, authorizing acts, stamps.",
    traceLabel: (date: S) => `One real question, ${date}`,
    traceAsked: (after: S, askedLang: Lang) => `Asked${askedLang === "es" ? " in Spanish" : ""}, after ${after}`,
    traceSearched: "Searched as",
    traceCols: { issue: "Issue", score: "Score", printer: "Printer on its card" },
    traceAnswer: "Answer shown",
    source: "source",
    whyAlone: (fullText: S, vector: S, spanish: S) =>
      `On the graph's full-text index alone, the right issue comes first for ${fullText} held-out questions, against ${vector} with the vector. Spanish questions get ${spanish}: the catalogue's titles are in English.`,
    // 4. results
    resH: "Results",
    resSet: (all: S, cat: S, lit: S, oos: S) => `${all} questions in Spanish and English: ${cat} on the catalogue, ${lit} on the literature, ${oos} out of scope.`,
    issueFound: { lead: "Issue found.", text: (three: S) => `Held-out catalogue questions where the right issue comes first. In the first three: ${three}.` },
    pageFound: { lead: "Page found.", text: (k: S, drafts: S, withDrafts: S) =>
      `Literature questions with a page that answers among the ${k} passages. Counting the ${drafts} drafts left out: ${withDrafts}.` },
    catAnswers: { lead: "Catalogue answers", text: (supported: S) => `that state the value the catalogue holds. Every sentence stated by its sources: ${supported}.` },
    litAnswers: { lead: "Literature answers", text: (part: number, partS: S, not: number, notS: S, notWritten: number, notWrittenS: S) =>
      `that agree with the reference answer in full. ${partS} ${part === 1 ? "agrees" : "agree"} in part${
        not ? `, ${notS} ${not === 1 ? "does" : "do"} not` : ""}${notWritten ? `, and ${notWrittenS} got no written answer` : ""}.` },
    asks: (asks: S) => `${asks} give what the question asks: the thing asked, in agreement with the reference.`,
    removed: { lead: "Sentences removed:", text: (notHold: S, of: S) => `the model wrote them with no citation. Of ${of} citations, ${notHold} did not hold.` },
    limitsLead: "Limits:",
    sealedNone: (n: S, of: S, a: S, b: S, ca: S, cb: S) =>
      `on ${n} questions never used while the system was changed, no literature answer agreed with its reference in full (0 of ${of} in both runs), ${a} and ${b} of ${of} gave what was asked, and ${ca} and ${cb} of ${of} catalogue answers were correct.`,
    sealedSome: (n: S, of: S, fa: S, fb: S, a: S, b: S, ca: S, cb: S) =>
      `on ${n} questions never used while the system was changed, ${fa} and ${fb} of ${of} literature answers agreed with their reference in full, ${a} and ${b} of ${of} gave what was asked, and ${ca} and ${cb} of ${of} catalogue answers were correct.`,
    limitsRest: (low: S, high: S) =>
      ` The grades are a model's and no person has checked them; the sets are small, so one question is ${low} to ${high} points.`,
    limitsWeb: " A web part changes from one asking to the next and has no gold: no reference answer exists for a web sentence, and the judge only says whether the cited page states it.",
    limitsTickets: (n: number, nS: S, of: S) =>
      n === 0
        ? ` In this run, none of the ${of} questions outside the scope was given a ticket for a web search.`
        : ` In this run, ${nS} of the ${of} questions outside the scope got a part answer, and with it a ticket for a web search.`,
    // 5. two judges
    judH: "Two judges",
    judges: (first: S, second: S, sample: S, grade: S, answers: S) =>
      `The literature pages were graded by a model, ${first}. A second model, ${second}, read a blind sample of ${sample} pages: the same grade on ${grade}, and the same “answers the question or not” on ${answers}. Both are OpenAI models given one rubric: the grading is stable, which does not show it is right.`,
    judgesAnswers: (judge: S, answers: S, same: S, kappa: S) =>
      ` The written answers' mark “gives what the question asks” was given again by a second judge, ${judge}, on ${answers} literature answers: the same mark on ${same} (Cohen's kappa ${kappa}). Two models agreeing is not a person checking.`,
    // 6. tried, and did not help
    triedH: "Tried, and did not help",
    triedWhole: (all: S, kept: S, keptAnswered: S) =>
      `The whole collection, ${all} passages with repeated copies, by vector. The ${kept} kept answer ${keptAnswered}.`,
    triedHybrid: (same: boolean, vector: S) =>
      `Hybrid search, keywords with vectors: ${same ? "the same count as vectors alone" : `against ${vector} for vectors alone`}, and its results did not repeat from run to run.`,
    triedOff: "The model's thinking turned off: literature answers cut at the output limit, with nothing shown.",
    triedStrong: (model: S, inFull: S, of: S, served: S, servedInFull: S, times: S, usd: S, servedUsd: S) =>
      `${model} as the writer, on the same evidence: ${inFull} answers of ${of} agree with the reference in full, against ${servedInFull} for ${served}, at about ${times} times the cost of a question (${usd} USD against ${servedUsd}). Not kept.`,
    range: (a: S, b: S) => `${a} to ${b}`,
    // 7. cost and wait
    costH: "Cost and wait of a question",
    costMean: (max: S) => `a question, on average; ${max} at most.`,
    costAfter: (usd: S) => ` A question after a conversation's first: about ${usd}, with one more small call.`,
    waitEvidence: "until the evidence is on the page (median).",
    waitAnswer: (p95: S) => `until the checked answer (median; ${p95} s at the 95th percentile).`,
    waitsWhere: {
      host: "Waits measured through the public service, with the service awake.",
      development: "Waits measured on the development machine. The hosted backend is on a smaller machine.",
    },
    sleeps: "The service sleeps when unused and wakes in about half a minute.",
    // 8. safe in public
    safeH: "What keeps it safe to run in public",
    spend: { lead: "A spend limit at the provider:", text: (usd: S, month: S) =>
      `${usd} USD for ${month}, set at Anthropic. Once reached, the page shows the evidence without a written answer.` },
    use: { lead: "Limits on use:", text: (minute: S, day: S, calls: S, low: S, chars: S) =>
      `a human check (Cloudflare Turnstile) before the first question; ${minute} questions a minute and ${day} a day for a visitor; ${calls} model calls a day in all (${low} to ${calls} answers); ${chars} characters a question.` },
    useWeb: (searches: S) => ` For the web part, at most ${searches} searches a month, spread over the month.`,
    readOnly: { lead: "Read-only stores, and a model with no tools.", text:
      "The most a passage can change is the wording of one answer, and nothing the model writes is rendered as markup or as a link." },
    scope: { lead: "A scope:", text: (none: S) =>
      `Costa Rican stamps, postal stationery and postal history. Otherwise no answer is written: ${none} out-of-scope questions.` },
    disk: { lead: "Nothing of a question on disk.", text: (kept: S) =>
      `The logs hold counts and timings: no question, no answer, no passage, no address. In memory until a restart: the vectors of the last ${kept} questions, with no text.` },
    privH: "What is sent, and where",
    // the versions, folded
    stackH: "Versions and tests",
    stack: {
      steps: "The answer's steps",
      graph: "The catalogue graph",
      lit: "The literature",
      backend: "Backend",
      page: "Page",
      tests: "Tests",
      graphV: (v: S) => `Neo4j ${v}, on Aura Free`,
      litV: (v: S) => `Weaviate ${v}, on Weaviate Cloud`,
      backendV: (fastapi: S, python: S) => `FastAPI ${fastapi}, Python ${python}, Docker, on Render`,
      pageV: (next: S, react: S, ts: S) => `Next.js ${next}, React ${react}, TypeScript ${ts}, static on Cloudflare Pages`,
      testsV: (pytest: S, py: S, pw: S, browser: S) =>
        `pytest ${pytest} (${py} test functions) and Playwright ${pw} (${browser}), run by GitHub Actions on every pull request`,
    },
    stackNote: "The page, the backend, the graph and the collection are each hosted on a free tier.",
    // 9. links
    moreH: "The whole account",
    linkEval: "The full evaluation, with every table and limit",
  },
  es: {
    title: "Cómo funciona y cómo se midió",
    lead: ({ issues, stamps, passages, embedding, writer }) =>
      `Oxcart responde preguntas sobre los sellos de Costa Rica, en español o en inglés, a partir de dos fuentes: el catálogo Mena, guardado como grafo en Neo4j (${issues} emisiones, ${stamps} sellos), y ${passages} pasajes de literatura filatélica escaneada, guardados con sus vectores en Weaviate. La pregunta se convierte en un vector (${embedding} de OpenAI) y se busca en las dos a la vez. ${writer} redacta una respuesta breve con citas, y una frase solo se muestra si su cita se sostiene. Los pasos son un grafo de LangGraph en un backend de FastAPI en Python; la página es Next.js y React en TypeScript.`,
    pipeH: (steps: number) => `Una pregunta, en ${steps === 5 ? "cinco" : "cuatro"} pasos`,
    pipeTitle: "Diagrama: el camino de una pregunta, desde la pregunta hasta la respuesta mostrada.",
    pipeDesc: "La lista numerada que le sigue dice lo mismo.",
    node: (x: NodeArgs) => ({
      q: { name: "Pregunta", sub: ["en español o en inglés"] },
      s1: { name: "Reescrita", sub: ["cada pregunta tras la primera:", "se lee con la conversación y se", "reescribe solo si remite a ella"], tech: x.writer },
      s2: { name: "Buscada", sub: ["un vector, dos búsquedas a la vez"], tech: `OpenAI ${x.embedding}` },
      cat: { name: "Catálogo", sub: ["como grafo", `${x.issues} emisiones`], tech: "Neo4j" },
      lit: { name: "Literatura", sub: ["por vectores", `${x.passages} pasajes`], tech: "Weaviate" },
      ev: { name: "Evidencia", sub: [`hasta ${x.cards} fichas y ${x.shown} pasajes; va primero`] },
      s3: { name: "Redactada con citas", sub: ["respuesta breve, solo de la evidencia"], tech: `${x.writer}, citas activadas` },
      s4: { name: "Citas comprobadas", sub: ["una frase sin cita se retira"], tech: "sin modelo" },
      ans: { name: "Respuesta", sub: ["solo frases cuya cita se sostiene"] },
      s5: { name: "Buscada en la web", sub: ["solo si nuestras fuentes cubren", "una parte de la pregunta, o nada"], tech: "Tavily, luego el mismo redactor" },
      web: { name: "De la web", sub: ["no del catálogo ni de la literatura"] },
    }),
    legend: (web: boolean) =>
      `Con fondo: lo que está en la página. Con contorno: un paso en el backend. ${
        web
          ? "Con línea discontinua: un paso solo para algunas preguntas: el paso 1 para cada pregunta después de la primera, que se reescribe solo cuando remite a la conversación; el paso 5 cuando nuestras fuentes cubren solo una parte de la pregunta, o nada."
          : "Con línea discontinua: para cada pregunta después de la primera, que se reescribe solo cuando remite a la conversación."
      }`,
    steps: {
      s1: { h: "Reescrita", text: ({ writer }) =>
        `Cada pregunta después de la primera se lee con la conversación y se reescribe solo cuando remite a ella: ${writer} reescribe «¿Y quién la imprimió?» para que se entienda sola. Una primera pregunta se busca tal como se escribió.` },
      s2: { h: "Buscada", text: ({ numbers, issues, passages, graphIndex, litIndex, litCompression, graphSimilarity, litSimilarity }) =>
        `Un vector (${numbers} números) sirve para dos búsquedas a la vez. El catálogo, un grafo en Neo4j, devuelve hasta ${issues} emisiones con sus fichas, de dos índices vectoriales ${graphIndex} por ${es(graphSimilarity)} (uno del texto completo de cada emisión, cuantizado; otro de su título, sus años y su sección, sin cuantizar), o de su índice de texto completo cuando no se puede calcular el vector. La literatura, en Weaviate, devuelve los ${passages} pasajes más cercanos de un índice vectorial ${litIndex} con compresión ${litCompression}, por ${es(litSimilarity)}. La página muestra primero esta evidencia.` },
      s3: { h: "Redactada con citas", text: ({ writer }) =>
        `${writer} redacta una respuesta breve solo a partir de esa evidencia; cada parte vuelve con el texto exacto que cita.` },
      s4: { h: "Citas comprobadas", text: () =>
        "Sin modelo. Una frase se queda solo si su texto citado está en una ficha o un pasaje mostrados; la que no trae cita se retira." },
      s5: { h: "Buscada en la web", text: ({ writer }) =>
        `Solo cuando nuestras fuentes cubren una parte de una pregunta, o nada: la pregunta se busca en la web (Tavily), y ${writer} redacta una parte breve a partir de las páginas encontradas, con la misma comprobación de sus citas. Va en un bloque propio bajo la respuesta: de la web, no del catálogo ni de la literatura. Una pregunta fuera del alcance no se busca.` },
    },
    pipeNote: "El servidor no guarda nada entre dos peticiones: la conversación vive en el navegador.",
    whyH: "Por qué un grafo y vectores a la vez",
    why: "Los vectores encuentran de qué trata una pregunta, en cualquiera de los dos idiomas. El grafo guarda los datos de cada emisión como valores: fechas, impresores, actos que la autorizan, sellos.",
    traceLabel: (date: S) => `Una pregunta real, ${date}`,
    traceAsked: (after: S, askedLang: Lang) => `Preguntado${askedLang === "en" ? " en inglés" : ""}, tras ${after}`,
    traceSearched: "Se buscó como",
    traceCols: { issue: "Emisión", score: "Puntuación", printer: "Impresor en su ficha" },
    traceAnswer: "Respuesta mostrada",
    source: "fuente",
    whyAlone: (fullText: S, vector: S, spanish: S) =>
      `Solo con el índice de texto completo del grafo, la emisión correcta queda primera en ${fullText} preguntas reservadas, frente a ${vector} con el vector. Las preguntas en español aciertan ${spanish}: los títulos del catálogo están en inglés.`,
    resH: "Resultados",
    resSet: (all: S, cat: S, lit: S, oos: S) => `${all} preguntas en español y en inglés: ${cat} sobre el catálogo, ${lit} sobre la literatura, ${oos} fuera de alcance.`,
    issueFound: { lead: "Emisión encontrada.", text: (three: S) => `Preguntas reservadas del catálogo en las que la emisión correcta queda primera. Entre las tres primeras: ${three}.` },
    pageFound: { lead: "Página encontrada.", text: (k: S, drafts: S, withDrafts: S) =>
      `Preguntas de la literatura con una página que responde entre los ${k} pasajes. Contando los ${drafts} borradores que quedaron fuera: ${withDrafts}.` },
    catAnswers: { lead: "Respuestas del catálogo", text: (supported: S) => `que dan el valor que guarda el catálogo. Con todas sus frases respaldadas por sus fuentes: ${supported}.` },
    litAnswers: { lead: "Respuestas de la literatura", text: (part: number, partS: S, not: number, notS: S, notWritten: number, notWrittenS: S) =>
      `que coinciden del todo con la respuesta de referencia. ${partS} ${part === 1 ? "coincide" : "coinciden"} en parte${
        not ? ` y ${notS} no` : ""}${notWritten ? `; ${notWrittenS} ${notWritten === 1 ? "quedó" : "quedaron"} sin respuesta redactada` : ""}.` },
    asks: (asks: S) => `${asks} dan lo que pide la pregunta: lo que se pregunta, de acuerdo con la referencia.`,
    removed: { lead: "Frases retiradas:", text: (notHold: S, of: S) => `el modelo las redactó sin cita. De ${of} citas, ${notHold} no se sostuvieron.` },
    limitsLead: "Límites:",
    sealedNone: (n: S, of: S, a: S, b: S, ca: S, cb: S) =>
      `en ${n} preguntas que nunca se usaron mientras se cambiaba el sistema, ninguna respuesta de la literatura coincidió del todo con su referencia (0 de ${of} en las dos corridas), ${a} y ${b} de ${of} dieron lo que se pedía, y ${ca} y ${cb} de ${of} respuestas del catálogo fueron correctas.`,
    sealedSome: (n: S, of: S, fa: S, fb: S, a: S, b: S, ca: S, cb: S) =>
      `en ${n} preguntas que nunca se usaron mientras se cambiaba el sistema, ${fa} y ${fb} de ${of} respuestas de la literatura coincidieron del todo con su referencia, ${a} y ${b} de ${of} dieron lo que se pedía, y ${ca} y ${cb} de ${of} respuestas del catálogo fueron correctas.`,
    limitsRest: (low: S, high: S) =>
      ` Las notas las puso un modelo y ninguna persona las ha revisado; los conjuntos son pequeños, así que una pregunta vale de ${low} a ${high} puntos.`,
    limitsWeb: " Una parte de la web cambia de una vez que se pregunta a la siguiente y no tiene referencia: no existe una respuesta de referencia para una frase de la web, y el juez solo dice si la página citada la afirma.",
    limitsTickets: (n: number, nS: S, of: S) =>
      n === 0
        ? ` En esta corrida, ninguna de las ${of} preguntas fuera de alcance recibió un pase para una búsqueda en la web.`
        : ` En esta corrida, ${nS} de las ${of} preguntas fuera de alcance ${n === 1 ? "recibió" : "recibieron"} una respuesta parcial, y con ella un pase para una búsqueda en la web.`,
    judH: "Dos jueces",
    judges: (first: S, second: S, sample: S, grade: S, answers: S) =>
      `Las páginas de la literatura las calificó un modelo, ${first}. Un segundo modelo, ${second}, leyó a ciegas una muestra de ${sample} páginas: la misma nota en ${grade}, y el mismo «responde la pregunta o no» en ${answers}. Los dos son modelos de OpenAI con una misma rúbrica: la calificación es estable, lo que no muestra que sea correcta.`,
    judgesAnswers: (judge: S, answers: S, same: S, kappa: S) =>
      ` La marca «da lo que pide la pregunta» de las respuestas redactadas la puso de nuevo un segundo juez, ${judge}, en ${answers} respuestas de la literatura: la misma marca en ${same} (kappa de Cohen ${kappa}). Que dos modelos coincidan no es que una persona lo revise.`,
    triedH: "Lo que se probó y no ayudó",
    triedWhole: (all: S, kept: S, keptAnswered: S) =>
      `La colección entera, ${all} pasajes con copias repetidas, por vector. Los ${kept} que se conservan responden ${keptAnswered}.`,
    triedHybrid: (same: boolean, vector: S) =>
      `Búsqueda híbrida, palabras clave con vectores: ${same ? "la misma cuenta que los vectores solos" : `frente a ${vector} con los vectores solos`}, y sus resultados no se repetían de una corrida a otra.`,
    triedOff: "El razonamiento del modelo apagado: respuestas de la literatura cortadas en el límite de salida, sin que se mostrara nada.",
    triedStrong: (model: S, inFull: S, of: S, served: S, servedInFull: S, times: S, usd: S, servedUsd: S) =>
      `${model} como redactor, con la misma evidencia: ${inFull} respuestas de ${of} coinciden del todo con la referencia, frente a ${servedInFull} con ${served}, a unas ${times} veces el costo de una pregunta (${usd} USD frente a ${servedUsd}). No se conservó.`,
    range: (a: S, b: S) => `${a} a ${b}`,
    costH: "Costo y espera de una pregunta",
    costMean: (max: S) => `una pregunta, en promedio; ${max} como máximo.`,
    costAfter: (usd: S) => ` Una pregunta después de la primera de una conversación: cerca de ${usd}, con una llamada pequeña más.`,
    waitEvidence: "hasta que la evidencia está en la página (mediana).",
    waitAnswer: (p95: S) => `hasta la respuesta comprobada (mediana; ${p95} s en el percentil 95).`,
    waitsWhere: {
      host: "Esperas medidas a través del servicio público, con el servicio despierto.",
      development: "Esperas medidas en la máquina de desarrollo. El backend alojado está en una máquina más pequeña.",
    },
    sleeps: "El servicio se duerme cuando nadie lo usa y despierta en cerca de medio minuto.",
    safeH: "Qué lo mantiene seguro abierto al público",
    spend: { lead: "Un límite de gasto en el proveedor:", text: (usd: S, month: S) =>
      `${usd} USD en ${month}, fijado en Anthropic. Al alcanzarlo, la página muestra la evidencia sin respuesta redactada.` },
    use: { lead: "Límites de uso:", text: (minute: S, day: S, calls: S, low: S, chars: S) =>
      `una comprobación humana (Cloudflare Turnstile) antes de la primera pregunta; ${minute} preguntas por minuto y ${day} por día para un visitante; ${calls} llamadas al modelo por día en total (de ${low} a ${calls} respuestas); ${chars} caracteres por pregunta.` },
    useWeb: (searches: S) => ` Para la parte de la web, como máximo ${searches} búsquedas al mes, repartidas a lo largo del mes.`,
    readOnly: { lead: "Almacenes de solo lectura y un modelo sin herramientas.", text:
      "Lo más que puede cambiar un pasaje es la redacción de una respuesta, y nada de lo que escribe el modelo se muestra como marcado ni como enlace." },
    scope: { lead: "Un alcance:", text: (none: S) =>
      `sellos, enteros postales e historia postal de Costa Rica. Para lo demás no se redacta respuesta: ${none} preguntas fuera de alcance.` },
    disk: { lead: "Nada de una pregunta en disco.", text: (kept: S) =>
      `Los registros guardan cuentas y tiempos: ni la pregunta, ni la respuesta, ni un pasaje, ni una dirección. En memoria hasta un reinicio: los vectores de las últimas ${kept} preguntas, sin texto.` },
    privH: "Qué se envía, y adónde",
    stackH: "Versiones y pruebas",
    stack: {
      steps: "Los pasos de la respuesta",
      graph: "El grafo del catálogo",
      lit: "La literatura",
      backend: "Backend",
      page: "Página",
      tests: "Pruebas",
      graphV: (v: S) => `Neo4j ${v}, en Aura Free`,
      litV: (v: S) => `Weaviate ${v}, en Weaviate Cloud`,
      backendV: (fastapi: S, python: S) => `FastAPI ${fastapi}, Python ${python}, Docker, en Render`,
      pageV: (next: S, react: S, ts: S) => `Next.js ${next}, React ${react}, TypeScript ${ts}, estática en Cloudflare Pages`,
      testsV: (pytest: S, py: S, pw: S, browser: S) =>
        `pytest ${pytest} (${py} funciones de prueba) y Playwright ${pw} (${browser}), que GitHub Actions corre en cada pull request`,
    },
    stackNote: "La página, el backend, el grafo y la colección están alojados cada uno en un nivel gratuito.",
    moreH: "La cuenta completa",
    linkEval: "La evaluación completa, con cada tabla y cada límite",
  },
};

