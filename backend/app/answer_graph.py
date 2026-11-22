"""The written answer, as a graph (LangGraph).

    START ──(a thread came with the question)──> contextualize ──┐
      └────────────(a first question)────────────────────────────┴─> retrieve ──> write ──> check ──> END
                                                                         └──(no store answered)──> END

    contextualize   a follow-up ("and its perforation?") -> a question that stands alone;    one model call
                    a question that already does is searched in the visitor's own words.
    retrieve        the question path as it was: embedding, catalogue lookup, literature.     no model
    write           a short answer from the shown evidence, with citations.                   one model call
    check           keeps what is cited, drops what is not, names why there is no answer.     no model

**Why a graph.** Each step is a node that is given only the part of the state it declares.
The earlier turns of a conversation come from the browser, so they are a visitor's text:
``contextualize`` is the only node that receives them. ``write`` receives the question
that stands alone and the evidence, and nothing a visitor typed in earlier turns. The
route sends each node's result as it ends, so the evidence reaches the page when
``retrieve`` ends, as fast as before, and the answer follows.

**No checkpointer.** A conversation lives in the visitor's browser, which sends its last
turns with a follow-up. The graph starts from that every time and the server keeps
nothing between two requests: no visitor's text stays in this process's memory, and
nothing is lost when the service sleeps.

**What is not here.** No step grades the evidence and none retrieves a second time; there
is no scope router. The model has no tools.

**The rule for text without a citation.** The answer is cut into sentences. A sentence is
shown only if a citation that holds is attached to it. A citation holds when it names a
shown card or passage and the text it cites is in that card or passage. It is attached to
the sentence its piece of the answer lies in. One case apart: a piece that is nothing but
the cited text itself, standing between two sentences, is a quote and not a sentence; it
is attached to the sentence before it and is not printed in the answer (the page shows
the cited text with the source). A sentence with no citation is not shown, and an answer
with no sentence left is not shown at all. The part of a kept sentence that lies outside
its cited text is NOT removed; whether such a sentence says more than its sources is what
the evaluation's "supported" grade measures.
"""

from __future__ import annotations

import operator
import re
import unicodedata
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from typing_extensions import TypedDict

from app import settings
from app.answer_model import NOT_COVERED, OUT_OF_SCOPE, PART_ONLY, UNCHANGED, Reply
from app.graph_link import Unavailable

STAMPS_ON_A_CARD = 24          # as many as the page prints
VARIETIES_OF_A_STAMP = 12
QUOTES_PER_SOURCE = 5


# --------------------------------------------------------------------------- state
class ChatState(TypedDict, total=False):
    question: str               # as the visitor wrote it
    thread: list                # the earlier turns, from the browser: [{"question": .., "answer": ..}]
    search_question: str        # the question that stands alone: what is searched and what is answered
    rewritten: bool
    evidence: dict              # what POST /api/ask returns for search_question
    error: str                  # set when no store answered
    draft: dict                 # the model's reply, before the check
    answer: dict                # what the page gets
    calls: Annotated[list, operator.add]     # one entry per model call: what for, its state, tokens, seconds


class FollowUp(TypedDict):
    """All that ``contextualize`` is given."""
    question: str
    thread: list


class Asked(TypedDict, total=False):
    """All that ``retrieve`` is given."""
    question: str
    search_question: str


class Found(TypedDict):
    """All that ``write`` is given: no earlier turn, and not the follow-up as it was typed."""
    search_question: str
    evidence: dict


class Written(TypedDict):
    """All that ``check`` is given."""
    evidence: dict
    draft: dict


@dataclass
class Deps:
    """What a run needs from the process. Tests pass fakes."""
    retrieve: Callable[[str], dict]     # ask_service.answer for this process's stores
    model: Any                          # answer_model.ClaudeModel, or a fake with the same three members
    take: Callable[[], bool]            # one model call from the day's allowance; False when it is spent


def _call(purpose: str, reply: Reply) -> dict:
    return {"purpose": purpose, "state": reply.state, "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens, "seconds": reply.seconds}


# --------------------------------------------------------------------------- the evidence as sources
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
_WORD = re.compile(r"[^\W\d_]+")
# Words that tell a question in Spanish from one in English. A question that opens with "¿" or "¡", or has
# more words of the first kind, is Spanish; anything else is English, the language the catalogue is written in.
_SPANISH = frozenset("""el la los las de del un una unos unas y que cual cuales cuando cuanto cuantos cuantas donde
quien quienes como por para con sin sobre entre fue fueron es son se su sus al sello sellos estampilla estampillas
emision emisiones emitio emitieron imprimio correo aereo sobrecarga sobrecargado sobrecargados resello ano primera
primer primeros salio salieron tiene hay catalogo valor valores""".split())
_ENGLISH = frozenset("""the of and what when which who whom whose how was were is are did does do in on for with
stamp stamps issue issued issues printed printer overprint overprints first many much have has its""".split())

# The words of a card's lines, by language. Titles, names and values stay as the catalogue writes them.
_CARD_WORDS = {
    "en": {"issue": "Issue", "on": "on", "in": "in", "of": "of", "printed": "printed by", "perforation": "perforation",
           "authorized": "authorized by", "stamp": "stamp", "value": "value", "colour": "colour", "quantity": "quantity",
           "scott": "Scott catalogue number", "variety": "variety",
           "dates": {"placed_on_sale": "placed on sale", "probable_first_circulation": "probable first circulation",
                     "announced": "announced", "demonetized": "demonetized", "second_plate_sale": "second plate sale"},
           "months": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                      "November", "December")},
    "es": {"issue": "Emisión", "on": "el", "in": "en", "of": "del", "printed": "impresa por", "perforation": "perforación",
           "authorized": "autorizada por", "stamp": "sello", "value": "valor", "colour": "color", "quantity": "cantidad",
           "scott": "número del catálogo Scott", "variety": "variedad",
           "dates": {"placed_on_sale": "puesta a la venta", "probable_first_circulation": "primera circulación probable",
                     "announced": "anunciada", "demonetized": "desmonetizada", "second_plate_sale": "venta de la segunda plancha"},
           "months": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                      "noviembre", "diciembre")},
}


def question_language(question: str) -> str:
    """"es" or "en", from the question's own words. No model."""
    text = (question or "").lower()
    if "¿" in text or "¡" in text:
        return "es"
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    words = _WORD.findall(plain)
    spanish, english = sum(w in _SPANISH for w in words), sum(w in _ENGLISH for w in words)
    if spanish == english:              # a name can carry an accent in an English question: it decides only a tie
        return "es" if any(c in text for c in "ñáéíóú") else "en"
    return "es" if spanish > english else "en"


def date_in_words(value: Any, lang: str = "en") -> tuple[str, str]:
    """("on", "1 May 1940") for 1940-05-01, ("in", "May 1940") for 1940-05; in Spanish ("el", "1 de mayo de 1940")
    and ("en", "mayo de 1940"). Anything else as it is, after ":"."""
    words = _CARD_WORDS[lang]
    text = str(value).strip()
    match = _ISO_DATE.fullmatch(text)
    if not match or not 1 <= int(match.group(2)) <= 12:
        return ":", text
    month, year = words["months"][int(match.group(2)) - 1], match.group(1)
    month_year = f"{month} de {year}" if lang == "es" else f"{month} {year}"
    if match.group(3) and 1 <= int(match.group(3)) <= 31:
        day = int(match.group(3))
        return words["on"], f"{day} de {month_year}" if lang == "es" else f"{day} {month_year}"
    return words["in"], month_year


def card_lines(issue: dict, lang: str = "en") -> list:
    """A catalogue card as fact lines, one fact per line, in the language of the question.

    The model cites a line and at times sets it inside its own sentence. So a line is a phrase
    that can stand there ("placed on sale on 1 May 1940", "puesta a la venta el 1 de mayo de 1940"),
    not a label, a colon and a value; a date is in words, not in the form 1940-05-01; and the words
    are in the language the answer will be in."""
    words = _CARD_WORDS[lang]
    card = issue.get("card") or {}
    lines = [f"{words['issue']}: {issue.get('title') or issue.get('issue_id')} ({issue.get('issue_id')})"]
    for key, value in (card.get("dates") or {}).items():
        if value:
            word, date = date_in_words(value, lang)
            name = words["dates"].get(str(key), str(key).replace("_", " "))
            lines.append(f"{name}: {date}" if word == ":" else f"{name} {word} {date}")
    if card.get("printers"):
        lines.append(f"{words['printed']} " + "; ".join(str(p) for p in card["printers"]))
    if card.get("perforation"):
        lines.append(f"{words['perforation']} {card['perforation']}")
    for act in card.get("acts") or []:
        parts = [str(act[k]) for k in ("type", "id") if act.get(k)]
        if act.get("date"):
            word, date = date_in_words(act["date"], lang)
            parts.append(date if word == ":" else f"{words['of']} {date}")
        if parts:
            lines.append(f"{words['authorized']} " + ", ".join(parts))
    for stamp in (card.get("stamps") or [])[:STAMPS_ON_A_CARD]:
        value = " ".join(str(stamp[k]) for k in ("value", "unit") if stamp.get(k) not in (None, ""))
        facts = [(words["value"], value), (words["colour"], stamp.get("color")), (words["quantity"], stamp.get("quantity"))]
        told = "; ".join(f"{name} {fact}" for name, fact in facts if fact not in (None, ""))
        number = f"{words['stamp']} {stamp.get('catalog_no')}"
        lines.append(f"{number}: {told}" if told else number)
        scott = [str(n) for n in stamp.get("scott") or [] if n]
        if scott:
            lines.append(f"{number}, {words['scott']}: {', '.join(scott)}")
        for variety in (stamp.get("varieties") or [])[:VARIETIES_OF_A_STAMP]:
            told = ": ".join(str(variety[k]) for k in ("suffix", "description") if variety.get(k))
            if told:
                lines.append(f"{number}, {words['variety']} {told}")
    return lines


def sources_of(evidence: dict) -> list:
    """The shown cards and passages, in the order the model is given them. A passage with
    no text (a figure only) is not a source. A card's lines are in the language of the question the
    evidence was found for, the same in ``write`` and in ``check``."""
    sources = []
    lang = question_language(evidence.get("question") or "")
    for index, issue in enumerate(evidence.get("issues") or []):
        sources.append({"kind": "issue", "index": index, "lines": card_lines(issue, lang),
                        "title": f"Catalogue card: {issue.get('title') or issue.get('issue_id')}"})
    for index, passage in enumerate(evidence.get("passages") or []):
        if (passage.get("text") or "").strip():
            sources.append({"kind": "passage", "index": index, "text": passage["text"],
                            "title": f"{passage.get('doc_id')}, page {passage.get('page')}"})
    return sources


def _squeezed(text: str) -> str:
    return "".join((text or "").split())


def _holds(citation: dict, sources: list) -> bool:
    """Does the citation name a shown source, and is its text in that source?"""
    n = citation.get("document")
    if not isinstance(n, int) or not 0 <= n < len(sources):
        return False
    source = sources[n]
    shown = "\n".join(source["lines"]) if source["kind"] == "issue" else source["text"]
    cited = _squeezed(citation.get("cited_text", ""))
    return bool(cited) and cited in _squeezed(shown)


_ENDS_A_SENTENCE = re.compile(r"[.!?…][\"'”’»)\]]*$")
_HAS_A_WORD = re.compile(r"\w")
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'”’»)\]]*\s+|\s*\n+\s*")


def sentence_spans(text: str) -> list:
    """(start, end) of each sentence of ``text``, without the space around it."""
    spans, start = [], 0
    for match in _SENTENCE_END.finditer(text):
        spans.append((start, match.start() + len(match.group(0).rstrip())))
        start = match.end()
    spans.append((start, len(text)))
    out = []
    for a, b in spans:
        piece = text[a:b]
        a, b = a + len(piece) - len(piece.lstrip()), b - (len(piece) - len(piece.rstrip()))
        if b > a:
            out.append((a, b))
    return out


# --------------------------------------------------------------------------- nodes
def contextualize(state: FollowUp, runtime: Runtime[Deps]) -> dict:
    deps = runtime.context
    question = state["question"]
    if not deps.model.configured or not deps.take():
        return {"search_question": question, "rewritten": False}
    reply = deps.model.rewrite(question, state["thread"])
    rewritten = " ".join(reply.text.split())
    # The model's word for "it stands alone": the visitor's own words are searched. The word counts
    # wherever it stands in the reply: seen once with a sentence of reasons before it, and a reply
    # that holds it is never a question to search.
    stands_alone = UNCHANGED in rewritten or rewritten.strip(" .\"'`").upper() == UNCHANGED
    if reply.state != "ok" or stands_alone or not 0 < len(rewritten) <= settings.ASK_MAX_QUESTION_CHARS:
        return {"search_question": question, "rewritten": False, "calls": [_call("rewrite", reply)]}
    return {"search_question": rewritten, "rewritten": rewritten != question, "calls": [_call("rewrite", reply)]}


def retrieve(state: Asked, runtime: Runtime[Deps]) -> dict:
    question = state.get("search_question") or state["question"]
    try:
        return {"search_question": question, "evidence": runtime.context.retrieve(question)}
    except Unavailable:
        return {"search_question": question, "error": "stores_unavailable"}


def write(state: Found, runtime: Runtime[Deps]) -> dict:
    deps = runtime.context
    sources = sources_of(state["evidence"])
    if not sources:
        return {"draft": {"state": "no_evidence"}}
    if not deps.model.configured:
        return {"draft": {"state": "no_key"}}
    if not deps.take():
        return {"draft": {"state": "daily_cap"}}
    reply = deps.model.write(state["search_question"], sources)
    return {"draft": {"state": reply.state, "blocks": reply.blocks}, "calls": [_call("write", reply)]}


def check(state: Written) -> dict:
    draft = state["draft"]
    if draft["state"] != "ok":
        return {"answer": {"state": draft["state"]}}
    sources = sources_of(state["evidence"])
    blocks = draft.get("blocks") or []
    whole = "".join(block["text"] for block in blocks)
    if not whole.strip():
        return {"answer": {"state": "empty"}}
    covers = None                # with ASK_WEB: "all" or "part" of the question, by the model's own last line
    if settings.ASK_WEB:
        if whole.strip().startswith(OUT_OF_SCOPE):
            return {"answer": {"state": "out_of_scope"}}
        covers = "part" if PART_ONLY in whole else "all"
        # the marker's line is taken out before sentences are counted: it is not a sentence of the answer
        blocks = [{**block, "text": block["text"].replace(PART_ONLY, "")} for block in blocks]
        blocks = [block for block in blocks if block["text"].strip() or block.get("citations")]
        if not "".join(block["text"] for block in blocks).strip():
            return {"answer": {"state": "not_covered"}}
    if whole.strip().startswith(NOT_COVERED):
        return {"answer": {"state": "not_covered"}}

    # The text that is printed, and where each citation that holds is attached to it.
    text, pieces, quotes, given, held = "", [], [], 0, 0        # pieces: (start, end, citations); quotes: (at, citations)
    for block in blocks:
        holding = [c for c in block.get("citations") or [] if _holds(c, sources)]
        given += len(block.get("citations") or [])
        held += len(holding)
        before = text.rstrip()
        between_sentences = not before or bool(_ENDS_A_SENTENCE.search(before))
        if holding and between_sentences and any(_squeezed(block["text"]) == _squeezed(c["cited_text"]) for c in holding):
            quotes.append((len(before), holding))               # a quote: attached to the sentence before it
            continue
        start = len(text)
        text += block["text"]
        if holding:
            pieces.append((start, len(text), holding))

    numbers: dict = {}          # (kind, index) -> the number the page prints
    used: list = []
    sentences = []
    spans = [(a, b) for a, b in sentence_spans(text) if _HAS_A_WORD.search(text[a:b])]
    for position, (a, b) in enumerate(spans):
        after = spans[position + 1][0] if position + 1 < len(spans) else len(text) + 1
        attached = [c for start, end, holding in pieces if text[max(a, start):min(b, end)].strip() for c in holding]
        attached += [c for at, holding in quotes if (a < at < after) or (at == 0 and position == 0) for c in holding]
        cites = []
        for citation in attached:
            source = sources[citation["document"]]
            key = (source["kind"], source["index"])
            if key not in numbers:
                numbers[key] = len(used) + 1
                used.append({"n": numbers[key], "kind": source["kind"], "index": source["index"],
                             "title": source["title"], "quotes": []})
            entry = used[numbers[key] - 1]
            quote = " ".join(citation["cited_text"].split())
            if quote not in entry["quotes"] and len(entry["quotes"]) < QUOTES_PER_SOURCE:
                entry["quotes"].append(quote)
            if numbers[key] not in cites:
                cites.append(numbers[key])
        if cites and NOT_COVERED not in text[a:b] and OUT_OF_SCOPE not in text[a:b]:
            sentences.append({"text": text[a:b], "cites": cites})

    counts = {"sentences": len(spans), "sentences_without_citation": len(spans) - len(sentences),
              "citations": given, "citations_that_do_not_hold": given - held}
    if not sentences:
        return {"answer": {"state": "uncited", "counts": counts}}
    cited_numbers = {n for sentence in sentences for n in sentence["cites"]}
    return {"answer": {"state": "ok", "sentences": sentences,
                       "sources": [source for source in used if source["n"] in cited_numbers], "counts": counts,
                       **({"covers": covers} if covers else {})}}


# --------------------------------------------------------------------------- the graph
def _first(state: ChatState) -> Literal["contextualize", "retrieve"]:
    return "contextualize" if state.get("thread") else "retrieve"


def _after_retrieve(state: ChatState) -> Literal["write", "__end__"]:
    return END if state.get("error") else "write"


def build():
    graph = StateGraph(ChatState, context_schema=Deps)
    graph.add_node("contextualize", contextualize)
    graph.add_node("retrieve", retrieve)
    graph.add_node("write", write)
    graph.add_node("check", check)
    graph.add_conditional_edges(START, _first)
    graph.add_edge("contextualize", "retrieve")
    graph.add_conditional_edges("retrieve", _after_retrieve)
    graph.add_edge("write", "check")
    graph.add_edge("check", END)
    return graph.compile()          # no checkpointer: see the module's note


GRAPH = build()
