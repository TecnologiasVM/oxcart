"""
Catalogue lookup for ANY issue: from a question to the issues it is about, and their facts.

The graph-first path in ``retrieve.py`` is tied to one issue (``config.ISSUE_ID``). This
module is the general entry: it reads the question, finds the ``Issue`` nodes it most
likely refers to, and returns each one's catalogue facts with the node they came from.

No model call is made here. Three signals are always used, all deterministic:

  1. a Mena or Scott catalogue number named in the question  -> the stamp's issue
  2. Neo4j's full-text index over issue titles and catalogue text (``issue_text_idx``)
  3. a year in the question -> issues of that year

and a fourth when the caller passes the question's embedding:

  4. the vector index over issues (``issue_vec_idx``, text-embedding-3-large, 3,072 numbers)

and a fifth when the caller asks for it and the graph holds it (``scripts/issue_short_vectors.py``):

  5. a second vector index (``issue_short_vec_idx``) over a short text of each issue: its
     title, its years and its section. The first vector is made from the title and the whole
     catalogue text, so a commemorative issue whose text tells an earlier issue's story can
     stand before that issue; the short vector is about what the issue is called.

The catalogue's titles are English. A Spanish question shares few words with them, so
signals 2 and 3 are not enough for it; the vector index is what finds the issue then.
The embedding is made by the caller, never in this module.

READ-ONLY. Every function takes an open Neo4j session; nothing here opens a driver.

    from oxcart.catalogue_lookup import lookup
    with driver.session(database=NEO4J_DATABASE, default_access_mode="READ") as session:
        for hit in lookup(session, "Who printed the 1946 San Juan de Dios Hospital issue?"):
            print(hit["issue_id"], hit["score"], hit["card"]["printers"])
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Reading the question
# --------------------------------------------------------------------------- #
_NUMBER = r"([A-Z]{0,3}\s?\d{1,4}[A-Za-z]?)"
_MENA_RES = [
    re.compile(r"\bmena\s+(?:number|no\.?|n[úu]mero|n[º°]\.?|#)?\s*" + _NUMBER + r"(?![\w])", re.IGNORECASE),
    re.compile(r"\bn[úu]mero\s+" + _NUMBER + r"\s+del?\s+(?:cat[áa]logo\s+)?mena\b", re.IGNORECASE),
]
_SCOTT_RES = [
    re.compile(r"\bscott\s+(?:number|no\.?|n[úu]mero|n[º°]\.?|#)?\s*" + _NUMBER + r"(?![\w])", re.IGNORECASE),
    re.compile(r"\bn[úu]mero\s+" + _NUMBER + r"\s+del?\s+(?:cat[áa]logo\s+)?scott\b", re.IGNORECASE),
]
_YEAR_RE = re.compile(r"(?<!\d)(18[4-9]\d|19\d\d|20[0-2]\d)(?!\d)")
_TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+")
_LUCENE_SPECIAL_RE = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')

# Words that say nothing about WHICH issue: question words, articles, and the vocabulary
# every catalogue question shares (issue, stamp, printed, colour ...), English and Spanish.
_STOPWORDS = frozenset("""
a about an and are as at be by did do does for from has have how in is it many much of on or that the this to
was were what when where which who whom whose why with you
al como con cual cuales cuando cuanto cuanta cuantos cuantas de del donde el en es esta este fue fueron ha han
la las lo los para por que quien quienes se su sus un una uno y
act acto authorized autorizo autorizó catalog catalogo catálogo catalogue color colour copies copy cuándo cuál
cuántos date día disposicion disposición ejemplares emision emisión emitio emitió fecha imprimieron imprimio
imprimió issue issued issues legal list lista listed mena number numero número placed printed printer puso
quién qué registra sale scott sello sellos stamp stamps varieties variedades venta
""".split())


@dataclass
class Parsed:
    """What a question says about which issue it means."""

    mena_numbers: List[str] = field(default_factory=list)
    scott_numbers: List[str] = field(default_factory=list)
    years: List[int] = field(default_factory=list)
    terms: List[str] = field(default_factory=list)


def _numbers(patterns, text: str) -> List[str]:
    found: List[str] = []
    for pattern in patterns:
        for m in pattern.finditer(text):
            number = re.sub(r"\s+", "", m.group(1)).upper()
            if number not in found:
                found.append(number)
    return found


def parse(question: str) -> Parsed:
    """Pull catalogue numbers, years and content words out of a question."""
    text = question or ""
    mena = _numbers(_MENA_RES, text)
    scott = _numbers(_SCOTT_RES, text)
    years = []
    for m in _YEAR_RE.finditer(text):
        year = int(m.group(1))
        if year not in years:
            years.append(year)
    taken = {n.lower() for n in mena + scott} | {str(y) for y in years}
    terms: List[str] = []
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) > 1 and token not in _STOPWORDS and token not in taken and token not in terms:
            terms.append(token)
    return Parsed(mena_numbers=mena, scott_numbers=scott, years=years, terms=terms)


def lucene_query(terms: List[str]) -> str:
    """Full-text query: the words anywhere, weighted three times when they are in the title."""
    if not terms:
        return ""
    joined = " OR ".join(_LUCENE_SPECIAL_RE.sub(r"\\\1", t) for t in terms)
    return f"title:({joined})^3 OR ({joined})"


# --------------------------------------------------------------------------- #
# Finding the issues
# --------------------------------------------------------------------------- #
_BY_MENA = """
MATCH (i:Issue)-[:HAS_STAMP]->(s:Stamp)
WHERE toUpper(s.catalog_no) IN $numbers
RETURN DISTINCT i.issue_id AS issue_id, i.title AS title, toUpper(s.catalog_no) AS number
"""
_BY_SCOTT = """
MATCH (i:Issue)-[:HAS_STAMP]->(s:Stamp)-[:EQUIVALENT_TO]->(sc:ScottStamp)
WHERE toUpper(sc.scott_number) IN $numbers
RETURN DISTINCT i.issue_id AS issue_id, i.title AS title, toUpper(sc.scott_number) AS number
"""
_BY_TEXT = """
CALL db.index.fulltext.queryNodes('issue_text_idx', $q) YIELD node AS i, score
RETURN i.issue_id AS issue_id, i.title AS title, i.issue_dates AS issue_dates, score
ORDER BY score DESC LIMIT $limit
"""
_BY_VECTOR = """
CALL db.index.vector.queryNodes('issue_vec_idx', $limit, $vector) YIELD node AS i, score
RETURN i.issue_id AS issue_id, i.title AS title, i.issue_dates AS issue_dates, score
ORDER BY score DESC
"""
# A vector index is approximate, and how near it comes depends on how many hits it is asked for.
# Measured on a copy of the graph, 96 questions, against exact cosine: asked for 40 hits, an index
# with Neo4j's default compression returned 37 of the exact 40 on average and another first three
# for 15 questions. Made without compression and asked for more hits than there are issues, it
# returned the exact 40 in the exact order for all 96, in about 9 ms. So the short index is made
# that way (scripts/issue_short_vectors.py) and asked that way: SHORT_INDEX_ASK hits, the best kept.
SHORT_INDEX_ASK = 2000
_BY_SHORT_VECTOR = """
CALL db.index.vector.queryNodes('issue_short_vec_idx', $ask, $vector) YIELD node AS i, score
RETURN i.issue_id AS issue_id, i.title AS title, i.issue_dates AS issue_dates, score
ORDER BY score DESC, issue_id LIMIT $limit
"""
_BY_YEAR = """
MATCH (i:Issue)
WHERE any(y IN $years WHERE i.issue_id CONTAINS ('-' + y + '-') OR i.issue_dates CONTAINS ('"' + y + '-'))
RETURN i.issue_id AS issue_id, i.title AS title
"""

# Weights of the signals. A catalogue number names the stamp outright; the year only
# narrows. Text and vector scores are scaled so the best hit of each is worth its weight.
NUMBER_WEIGHT = 10.0
TEXT_WEIGHT = 4.0
VECTOR_WEIGHT = 4.0
SHORT_VECTOR_WEIGHT = 4.0
YEAR_WEIGHT = 3.0


def _issue_years(issue_id: str, issue_dates: Any) -> set:
    years = {int(y) for y in _YEAR_RE.findall(issue_id or "")}
    years |= {int(y) for y in re.findall(r'"(\d{4})-', issue_dates or "")} if isinstance(issue_dates, str) else set()
    return years


def short_text(issue_id: str, title: Any, issue_dates: Any, section: Any) -> str:
    """The text an issue's short vector is made from: its title, its years and its section."""
    years = sorted(_issue_years(issue_id, issue_dates))
    return f"{title or ''}. Costa Rica, {', '.join(map(str, years))}. {section or ''}".strip()


def find_issues(session, question: str, k: int = 3, text_limit: int = 40,
                question_vector: List[float] | None = None, use_text: bool | None = None,
                use_short: bool = False) -> List[Dict[str, Any]]:
    """Rank the issues a question is most likely about. Returns up to k of
    ``{"issue_id", "title", "score", "matched_by": [...]}``, best first.

    ``question_vector``: the question's text-embedding-3-large embedding, to use the vector
    index. ``use_text``: use the full-text index; by default only when no vector is given.
    Measured on the test set's development questions (48, half Spanish): right issue first
    in 85% with the full-text index, 100% with the vector index, 98% with both, so the
    words are left out when the meaning is available.

    ``use_short``: also use the short vector index, with the same question vector. Its hits
    are named "title" in ``matched_by``. Measured on a copy of the graph: on 15 questions a
    collector would type, a wanted issue first for 11 against 9, and among the first three
    for 13 against 12; on the 80 catalogue questions, first for 75 against 78 and among the
    first three for all 80 either way."""
    if use_text is None:
        use_text = question_vector is None
    parsed = parse(question)
    found: Dict[str, Dict[str, Any]] = {}
    wanted_years = set(parsed.years)

    def add(issue_id, title, points, reason):
        if not issue_id:
            return
        entry = found.setdefault(issue_id, {"issue_id": issue_id, "title": title, "score": 0.0, "matched_by": []})
        if reason == "year" and "year" in entry["matched_by"]:
            return  # the year counts once per issue
        entry["score"] += points
        if reason not in entry["matched_by"]:
            entry["matched_by"].append(reason)

    if parsed.mena_numbers:
        for r in session.run(_BY_MENA, numbers=parsed.mena_numbers):
            add(r["issue_id"], r["title"], NUMBER_WEIGHT, f"Mena {r['number']}")
    if parsed.scott_numbers:
        for r in session.run(_BY_SCOTT, numbers=parsed.scott_numbers):
            add(r["issue_id"], r["title"], NUMBER_WEIGHT, f"Scott {r['number']}")

    query = lucene_query(parsed.terms) if use_text else ""
    if query:
        rows = list(session.run(_BY_TEXT, q=query, limit=text_limit))
        top = max((r["score"] for r in rows), default=0.0)
        for r in rows:
            add(r["issue_id"], r["title"], TEXT_WEIGHT * r["score"] / top if top else 0.0, "text")
            if wanted_years & _issue_years(r["issue_id"], r["issue_dates"]):
                add(r["issue_id"], r["title"], YEAR_WEIGHT, "year")

    indexes = [(_BY_VECTOR, VECTOR_WEIGHT, "vector")] if question_vector else []
    if question_vector and use_short:
        indexes.append((_BY_SHORT_VECTOR, SHORT_VECTOR_WEIGHT, "title"))
    for query, weight, reason in indexes:
        more = {"ask": SHORT_INDEX_ASK} if query is _BY_SHORT_VECTOR else {}
        rows = list(session.run(query, vector=question_vector, limit=text_limit, **more))
        scores = [r["score"] for r in rows]
        top, low = max(scores, default=0.0), min(scores, default=0.0)
        for r in rows:
            share = (r["score"] - low) / (top - low) if top > low else 1.0
            add(r["issue_id"], r["title"], weight * share, reason)
            if wanted_years & _issue_years(r["issue_id"], r["issue_dates"]):
                add(r["issue_id"], r["title"], YEAR_WEIGHT, "year")

    if parsed.years:
        for r in session.run(_BY_YEAR, years=[str(y) for y in parsed.years]):
            add(r["issue_id"], r["title"], YEAR_WEIGHT, "year")

    ranked = sorted(found.values(), key=lambda e: (-e["score"], e["issue_id"]))
    return ranked[:k]


# --------------------------------------------------------------------------- #
# The facts of one issue
# --------------------------------------------------------------------------- #
_CARD = """
MATCH (i:Issue {issue_id: $issue_id})
OPTIONAL MATCH (i)-[:PRINTED_BY]->(p:Printer)
WITH i, collect(DISTINCT p.name) AS printers
OPTIONAL MATCH (i)-[:AUTHORIZED_BY]->(a:LegalAct)
WITH i, printers, collect(DISTINCT {type: a.type, id: a.id, date: a.date}) AS acts
OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
WITH i, printers, acts, s,
     collect(DISTINCT {suffix: v.suffix, type: v.type, description: v.description}) AS varieties
OPTIONAL MATCH (s)-[:EQUIVALENT_TO]->(sc:ScottStamp)
WITH i, printers, acts, s, varieties, collect(DISTINCT sc.scott_number) AS scott
ORDER BY s.catalog_no
RETURN i.issue_id AS issue_id, i.title AS title, i.section AS section, i.issue_dates AS issue_dates,
       i.perforation AS perforation, printers, acts,
       collect({catalog_no: s.catalog_no, value: s.denomination_value, unit: s.denomination_unit,
                color: s.color, quantity: s.quantity_reported, perforation: s.perforation,
                status: s.status, varieties: varieties, scott: scott}) AS stamps
"""


def issue_card(session, issue_id: str) -> Dict[str, Any] | None:
    """Catalogue facts of one issue, as plain data. None when the issue does not exist."""
    record = session.run(_CARD, issue_id=issue_id).single()
    if record is None:
        return None
    card = dict(record)
    raw = card.pop("issue_dates", None)
    try:
        dates = json.loads(raw) if isinstance(raw, str) and raw else {}
    except ValueError:
        dates = {}
    card["dates"] = {key: value for key, value in dates.items() if value}
    card["acts"] = [a for a in card["acts"] if a.get("id")]
    stamps = []
    for s in card["stamps"]:
        if not s.get("catalog_no"):
            continue
        s["varieties"] = [v for v in s["varieties"] if v.get("suffix") or v.get("description")]
        stamps.append(s)
    card["stamps"] = stamps
    card["source"] = {"node": "Issue", "issue_id": card["issue_id"]}
    return card


def lookup(session, question: str, k: int = 3, question_vector: List[float] | None = None,
           use_text: bool | None = None, use_short: bool = False) -> List[Dict[str, Any]]:
    """The issues a question is about, best first, each with its facts under ``"card"``."""
    hits = find_issues(session, question, k=k, question_vector=question_vector, use_text=use_text,
                       use_short=use_short)
    for hit in hits:
        hit["card"] = issue_card(session, hit["issue_id"])
    return hits
