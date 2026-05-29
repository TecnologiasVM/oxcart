"""
Combined GraphRAG *retrieval* for the Costa Rica 1863 First Issue prototype.

This module is **retrieval-only** — it assembles a grounded, citation-backed
"answer card" from three complementary sources and PRINTS it. There is NO LLM
generation/synthesis here; we never call an OpenAI/Anthropic client directly.
(Weaviate may use OpenAI under the hood for its own ``hybrid`` vectorizer — that
is the single accepted exception, and it only fires when an OpenAI key is
present in the environment.)

The three retrievers, deliberately kept separate so they can be compared:

  1) DOMAIN CARD (Neo4j) -- the structured facts: the Issue, its Mena Stamps,
     the EQUIVALENT_TO Scott stamps, the Illustration design, and Scott notes.
     This is the high-precision "what we know" panel.

  2) NEO4J LEXICAL EVIDENCE -- passages from the lexical graph. We query the
     ``chunk_text_fts`` fulltext index with a safe Lucene query derived from the
     question, AND pull chunks already linked to the Issue/its Stamps via the
     MENTIONS / MENTIONS_STAMP edges. Each hit carries a citation
     ``{doc_id, page, chunk_id, snippet, score}``; results are de-duped by
     ``chunk_id``.

  3) WEAVIATE EVIDENCE (READ-ONLY) -- the parallel/baseline retriever over the
     existing ``Oxcart`` collection. BM25 always (no API key needed); hybrid
     additionally when ``OPENAI_API_KEY`` is set. We prefer ``text_original``
     (the CLEAN field) for the snippet. The client is ALWAYS closed.

Public API:
    answer(question: str, k: int = 6) -> dict
        Returns {"domain": ..., "neo4j_evidence": [...], "weaviate_evidence": [...]}.

CLI:
    ".venv-clean\\Scripts\\python.exe" first_issue_graphrag\\retrieve.py \\
        --q "Tell me about the half real blue stamp of the Costa Rica first issue" --k 6
"""

from __future__ import annotations

import argparse
import re
from typing import Any, Dict, List, Optional

from config import (
    ISSUE_ID,
    NEO4J_DATABASE,
    OPENAI_API_KEY,
    OXCART_COLLECTION,
    PROTOTYPE_TAG,
    neo4j_driver,
    weaviate_client,
)

# --------------------------------------------------------------------------- #
# Lucene query construction (safe, per research notes)
# --------------------------------------------------------------------------- #
# Special characters that MUST be escaped in a Lucene query string.
_LUCENE_SPECIAL_RE = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')

# Tiny English/Spanish stop list so the fulltext query keeps only content terms.
_STOPWORDS = frozenset(
    {
        "a", "about", "an", "and", "are", "as", "at", "be", "by", "del", "de",
        "do", "for", "from", "in", "is", "it", "la", "las", "los", "el", "me",
        "of", "on", "or", "tell", "that", "the", "this", "to", "un", "una",
        "was", "what", "which", "with", "you",
    }
)

# Default Lucene query when the question yields no usable terms.
_FALLBACK_QUERY = "first issue"


def lucene_escape(token: str) -> str:
    """Backslash-escape Lucene special characters in a single token."""
    return _LUCENE_SPECIAL_RE.sub(r"\\\1", token)


def build_lucene_query(question: str) -> str:
    """
    Derive a safe Lucene query string from a natural-language question.

    Strips punctuation that would confuse the parser, drops stop words, escapes
    Lucene special characters in each surviving token, and OR-joins them. Falls
    back to ``"first issue"`` when nothing usable remains.
    """
    raw = (question or "").lower()
    # Split on any run of non-word characters (keeps ½/accents out of the way of
    # the Lucene parser; we only feed alphanumeric tokens).
    tokens = re.findall(r"[a-záéíóúñü0-9]+", raw)
    terms = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if not terms:
        return _FALLBACK_QUERY
    return " OR ".join(lucene_escape(t) for t in terms)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _snippet(text: Optional[str], limit: Optional[int] = 280) -> str:
    """Collapse whitespace and (optionally) truncate. ``limit`` None/0 -> full text."""
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", str(text)).strip()
    if not limit or limit <= 0 or len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def _as_float(value: Any) -> Optional[float]:
    """Best-effort float coercion (Neo4j/Weaviate scores arrive as various types)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# 1) DOMAIN CARD (Neo4j) — structured facts
# --------------------------------------------------------------------------- #
# All reads are parameterized and version-safe (driver 5.x execute_read).
_DOMAIN_CYPHER = """
MATCH (i:Issue {issue_id: $issue_id})
OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
WITH i, s
ORDER BY s.catalog_no
OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(scott:ScottStamp)
OPTIONAL MATCH (scott)-[:DEPICTS]->(ill:Illustration)
WITH i,
     s,
     collect(DISTINCT {
         scott_number:  scott.scott_number,
         denomination:  scott.denomination,
         color:         scott.color,
         mint_value:    scott.mint_value,
         used_value:    scott.used_value,
         perforation:   scott.perforation,
         description:   scott.description,
         variety_of:    scott.variety_of,
         confidence:    eq.confidence,
         design_name:        ill.design_name,
         design_description: ill.design_description
     }) AS scotts
WITH i,
     collect(CASE WHEN s IS NULL THEN NULL ELSE {
         catalog_no:        s.catalog_no,
         denomination_value: s.denomination_value,
         denomination_unit:  s.denomination_unit,
         color:             s.color,
         perforation:       s.perforation,
         status:            s.status,
         quantity_reported: s.quantity_reported,
         equivalent_scott:  [x IN scotts WHERE x.scott_number IS NOT NULL]
     } END) AS raw_stamps
RETURN
    i.issue_id     AS issue_id,
    i.title        AS title,
    i.plain_raw_text AS plain_raw_text,
    i.perforation  AS perforation,
    i.issue_dates  AS issue_dates,
    i.country      AS country,
    [st IN raw_stamps WHERE st IS NOT NULL] AS stamps
"""

# Scott-side notes + a flat illustration roster, fetched independently so the
# card still renders even if no Mena<->Scott equivalence edge exists yet.
_SCOTT_NOTES_CYPHER = """
MATCH (scott:ScottStamp {prototype: $tag})
OPTIONAL MATCH (scott)-[:DEPICTS]->(ill:Illustration {prototype: $tag})
WITH scott, ill
ORDER BY scott.scott_number
RETURN collect(DISTINCT {
    scott_number: scott.scott_number,
    denomination: scott.denomination,
    color:        scott.color,
    description:  scott.description,
    design_name:  ill.design_name
}) AS scott_roster
"""


def _domain_excerpt(text: Optional[str], limit: int = 600) -> str:
    """A longer excerpt of the Issue's plain_raw_text for the card body."""
    return _snippet(text, limit=limit)


def fetch_domain_card(driver: Any) -> Dict[str, Any]:
    """
    Read the structured First-Issue domain card from Neo4j (READ-ONLY).

    Returns a dict with keys: issue_id, title, plain_raw_text_excerpt,
    perforation, issue_dates, country, stamps[], scott_roster[]. Empty/partial
    when the graph has not been ingested yet (the prototype must still run).
    """
    with driver.session(database=NEO4J_DATABASE) as session:
        domain_rows = session.execute_read(
            lambda tx: list(tx.run(_DOMAIN_CYPHER, issue_id=ISSUE_ID))
        )
        roster_rows = session.execute_read(
            lambda tx: list(tx.run(_SCOTT_NOTES_CYPHER, tag=PROTOTYPE_TAG))
        )

    if not domain_rows:
        return {
            "issue_id": ISSUE_ID,
            "found": False,
            "title": None,
            "plain_raw_text_excerpt": None,
            "perforation": None,
            "issue_dates": None,
            "country": None,
            "stamps": [],
            "scott_roster": [],
        }

    row = domain_rows[0]
    scott_roster: List[Dict[str, Any]] = []
    if roster_rows:
        scott_roster = [r for r in (roster_rows[0].get("scott_roster") or []) if r.get("scott_number")]

    return {
        "issue_id": row.get("issue_id") or ISSUE_ID,
        "found": True,
        "title": row.get("title"),
        "plain_raw_text_excerpt": _domain_excerpt(row.get("plain_raw_text")),
        "perforation": row.get("perforation"),
        "issue_dates": row.get("issue_dates"),
        "country": row.get("country"),
        "stamps": row.get("stamps") or [],
        "scott_roster": scott_roster,
    }


# --------------------------------------------------------------------------- #
# 2) NEO4J LEXICAL EVIDENCE — fulltext + MENTIONS/MENTIONS_STAMP edges
# --------------------------------------------------------------------------- #
_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes('chunk_text_fts', $q) YIELD node AS c, score
WHERE c.prototype = $tag
RETURN
    c.chunk_id      AS chunk_id,
    c.doc_id        AS doc_id,
    c.page          AS page,
    c.text          AS text,
    c.link_score    AS link_score,
    score           AS score
ORDER BY score DESC
LIMIT $k
"""

# Chunks attached to the Issue (or any of its Stamps) by the lexical linker.
# These are surfaced regardless of fulltext overlap so we always have grounded
# evidence even for vague questions.
_MENTIONS_CYPHER = """
MATCH (i:Issue {issue_id: $issue_id})
MATCH (c:Chunk {prototype: $tag})
OPTIONAL MATCH (c)-[m:MENTIONS]->(i)
OPTIONAL MATCH (c)-[ms:MENTIONS_STAMP]->(:Stamp {issue_id: $issue_id})
WITH c, m, collect(DISTINCT ms.confidence) AS stamp_confs,
     max(coalesce(m.score, 0.0)) AS mention_score
WHERE m IS NOT NULL OR size(stamp_confs) > 0
RETURN
    c.chunk_id   AS chunk_id,
    c.doc_id     AS doc_id,
    c.page       AS page,
    c.text       AS text,
    c.link_score AS link_score,
    mention_score AS score
ORDER BY coalesce(c.link_score, mention_score) DESC
LIMIT $k
"""


def _citation_from_neo4j(record: Dict[str, Any], via: str) -> Dict[str, Any]:
    """Build a uniform citation dict from a Neo4j chunk record."""
    return {
        "chunk_id": record.get("chunk_id"),
        "doc_id": record.get("doc_id"),
        "page": record.get("page"),
        "snippet": _snippet(record.get("text")),
        "score": _as_float(record.get("score")),
        "link_score": _as_float(record.get("link_score")),
        "via": via,  # "fulltext" | "mentions"
    }


def fetch_neo4j_evidence(driver: Any, question: str, k: int) -> List[Dict[str, Any]]:
    """
    Lexical evidence from the Neo4j chunk graph (READ-ONLY).

    Combines two retrieval paths and de-duplicates by ``chunk_id`` (a fulltext
    hit that is also a MENTIONS chunk keeps its higher-signal fulltext entry):

      * ``chunk_text_fts`` fulltext search with a safe Lucene query, and
      * chunks linked to the Issue/its Stamps via MENTIONS / MENTIONS_STAMP.

    Each returned item is a citation: {chunk_id, doc_id, page, snippet, score,
    link_score, via}. Returns at most ``k`` items overall.
    """
    lucene_q = build_lucene_query(question)
    by_chunk: Dict[str, Dict[str, Any]] = {}

    with driver.session(database=NEO4J_DATABASE) as session:
        # Fulltext path first — these get priority on chunk_id collisions.
        try:
            ft_rows = session.execute_read(
                lambda tx: list(
                    tx.run(_FULLTEXT_CYPHER, q=lucene_q, tag=PROTOTYPE_TAG, k=k)
                )
            )
        except Exception as exc:  # index missing / Lucene parse error — degrade gracefully
            ft_rows = []
            print(f"[neo4j] fulltext path unavailable ({type(exc).__name__}): {exc}")

        for rec in ft_rows:
            cid = rec.get("chunk_id")
            if cid and cid not in by_chunk:
                by_chunk[cid] = _citation_from_neo4j(dict(rec), via="fulltext")

        # MENTIONS / MENTIONS_STAMP path — fills in graph-linked evidence.
        try:
            mention_rows = session.execute_read(
                lambda tx: list(
                    tx.run(_MENTIONS_CYPHER, issue_id=ISSUE_ID, tag=PROTOTYPE_TAG, k=k)
                )
            )
        except Exception as exc:  # graph not ingested yet — still return fulltext hits
            mention_rows = []
            print(f"[neo4j] mentions path unavailable ({type(exc).__name__}): {exc}")

        for rec in mention_rows:
            cid = rec.get("chunk_id")
            if cid and cid not in by_chunk:
                by_chunk[cid] = _citation_from_neo4j(dict(rec), via="mentions")

    # Rank: fulltext score, then link_score as a tiebreaker; cap at k.
    def _rank_key(item: Dict[str, Any]) -> tuple:
        ft = item["score"] if item["via"] == "fulltext" and item["score"] is not None else -1.0
        ls = item["link_score"] if item["link_score"] is not None else -1.0
        return (ft, ls)

    ordered = sorted(by_chunk.values(), key=_rank_key, reverse=True)
    return ordered[:k]


# --------------------------------------------------------------------------- #
# 3) WEAVIATE EVIDENCE (READ-ONLY parallel retriever)
# --------------------------------------------------------------------------- #
_WEAVIATE_PROPERTIES = [
    "chunk_id",
    "doc_id",
    "text",
    "text_original",
    "page_number",
]


def _weaviate_hit(obj: Any, mode: str) -> Dict[str, Any]:
    """Normalize a Weaviate v4 object into a uniform citation dict."""
    props = obj.properties or {}
    meta = getattr(obj, "metadata", None)
    score = getattr(meta, "score", None) if meta is not None else None
    # Prefer the CLEAN text_original; fall back to enriched text. FULL text (no
    # truncation) so the saved bundle is complete for LLM hand-off.
    snippet_source = props.get("text_original") or props.get("text")
    return {
        "chunk_id": props.get("chunk_id"),
        "doc_id": props.get("doc_id"),
        "page": props.get("page_number"),
        "snippet": _snippet(snippet_source, limit=None),
        "score": _as_float(score),
        "via": mode,  # "bm25" | "hybrid"
    }


def fetch_weaviate_evidence(question: str, k: int) -> List[Dict[str, Any]]:
    """
    Read-only retrieval from the existing ``Oxcart`` Weaviate collection.

    BM25 always runs (no API key required). When ``OPENAI_API_KEY`` is present,
    a hybrid pass is added (Weaviate's own OpenAI vectorizer — the sole accepted
    LLM-adjacent exception). NEVER creates/updates/deletes Weaviate data. The
    client is ALWAYS closed before returning. Snippet prefers ``text_original``.
    """
    import weaviate.classes as wvc

    hits: List[Dict[str, Any]] = []
    client = None
    try:
        client = weaviate_client()
        coll = client.collections.get(OXCART_COLLECTION)

        bm25_resp = coll.query.bm25(
            query=question,
            limit=k,
            return_properties=_WEAVIATE_PROPERTIES,
            return_metadata=wvc.query.MetadataQuery(score=True),
        )
        hits.extend(_weaviate_hit(o, mode="bm25") for o in (bm25_resp.objects or []))

        # Hybrid only when an OpenAI key is available for Weaviate's vectorizer.
        if OPENAI_API_KEY:
            try:
                hybrid_resp = coll.query.hybrid(
                    query=question,
                    alpha=0.35,
                    limit=k,
                    return_properties=_WEAVIATE_PROPERTIES,
                    return_metadata=wvc.query.MetadataQuery(score=True),
                )
                hits.extend(_weaviate_hit(o, mode="hybrid") for o in (hybrid_resp.objects or []))
            except Exception as exc:  # vectorizer/key issue — BM25 results still stand
                print(f"[weaviate] hybrid pass skipped ({type(exc).__name__}): {exc}")
    except Exception as exc:  # collection unavailable — return whatever we have
        print(f"[weaviate] retrieval unavailable ({type(exc).__name__}): {exc}")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # pragma: no cover - close best-effort
                pass

    # De-dup by chunk_id, keeping the highest score; preserve BM25-then-hybrid order.
    best: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for h in hits:
        cid = h.get("chunk_id") or f"_anon_{len(order)}"
        existing = best.get(cid)
        if existing is None:
            best[cid] = h
            order.append(cid)
        elif (h.get("score") or -1.0) > (existing.get("score") or -1.0):
            best[cid] = h

    deduped = [best[cid] for cid in order]
    deduped.sort(key=lambda h: (h.get("score") if h.get("score") is not None else -1.0), reverse=True)
    return deduped[:k]


# --------------------------------------------------------------------------- #
# Graph-first context bundle: DOMAIN > ALL lexical (deduped) > thin Weaviate tail
# --------------------------------------------------------------------------- #
# Separate budgets per source, with the lexical graph given predominance: pull
# *every* distinct relevant chunk from the graph (no small cap), de-duplicated by
# normalized text (so the combined-chunk duplicates collapse), then add only a
# small Weaviate tail of passages NOT already covered by the graph.

def _norm_text(text: Optional[str]) -> str:
    return " ".join((text or "").lower().split())


_LEX_FULLTEXT_SCORE_CYPHER = """
CALL db.index.fulltext.queryNodes('chunk_text_fts', $q) YIELD node AS c, score
WHERE c.prototype = $tag
RETURN c.chunk_id AS chunk_id, score AS score
ORDER BY score DESC
LIMIT 1000
"""

# Quality gate: only chunks whose MENTIONS edge is strong (score >= min_link) and
# (by default) NOT flagged COMPETING — i.e. the clean evidence set, no garbage.
_LEX_CLEAN_ISSUE_CYPHER = """
MATCH (c:Chunk {prototype:$tag})-[m:MENTIONS]->(:Issue {issue_id:$issue_id})
WHERE m.score >= $min_link AND ($keep_competing OR NOT 'COMPETING' IN m.signals)
RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.page AS page,
       c.text AS text, c.link_score AS link_score, m.signals AS signals
"""

_LEX_CLEAN_STAMP_CYPHER = """
MATCH (c:Chunk {prototype:$tag})-[ms:MENTIONS_STAMP]->(:Stamp {issue_id:$issue_id, catalog_no:$cno})
MATCH (c)-[m:MENTIONS]->(:Issue {issue_id:$issue_id})
WHERE m.score >= $min_link AND ($keep_competing OR NOT 'COMPETING' IN m.signals)
RETURN c.chunk_id AS chunk_id, c.doc_id AS doc_id, c.page AS page,
       c.text AS text, c.link_score AS link_score, m.signals AS signals,
       ms.confidence AS conf
"""


def _lex_rank(d: Dict[str, Any]) -> tuple:
    """Rank lexical hits: query relevance (fulltext) first, then link strength."""
    ft = d.get("score") if d.get("score") is not None else -1.0
    ls = d.get("link_score") if d.get("link_score") is not None else -1.0
    return (float(ft), float(ls))


def fetch_lexical_all(
    driver: Any,
    question: str,
    stamp: Optional[str] = None,
    max_lexical: int = 0,
    min_link_score: float = 6.0,
    exclude_competing: bool = True,
    include_issue_mentions: bool = True,  # accepted for API compat; clean set is always issue-linked
) -> List[Dict[str, Any]]:
    """
    Pull the GOOD first-issue chunks (not garbage) from the lexical graph.

    Quality gate: only chunks whose ``MENTIONS`` edge has ``score >= min_link_score``
    and (by default) is NOT flagged ``COMPETING`` — the clean evidence set from
    EVALUATION.md. Within that set, results are ranked by query relevance (fulltext
    score) first, then link strength, and de-duplicated by normalized text.
    ``max_lexical=0`` = no cap (bring as much good graph as the query supports).
    """
    lucene_q = build_lucene_query(question)
    keep_competing = not exclude_competing
    items_by_id: Dict[str, Dict[str, Any]] = {}

    with driver.session(database=NEO4J_DATABASE) as session:
        # 1) the clean universe of GOOD first-issue chunks (quality-gated)
        try:
            if stamp:
                clean_rows = session.execute_read(lambda tx: list(tx.run(
                    _LEX_CLEAN_STAMP_CYPHER, tag=PROTOTYPE_TAG, issue_id=ISSUE_ID,
                    cno=str(stamp), min_link=float(min_link_score), keep_competing=keep_competing)))
            else:
                clean_rows = session.execute_read(lambda tx: list(tx.run(
                    _LEX_CLEAN_ISSUE_CYPHER, tag=PROTOTYPE_TAG, issue_id=ISSUE_ID,
                    min_link=float(min_link_score), keep_competing=keep_competing)))
        except Exception as exc:
            clean_rows = []
            print(f"[neo4j] lexical (clean) path unavailable ({type(exc).__name__}): {exc}")
        for r in clean_rows:
            d = dict(r)
            d["score"] = None
            d["via"] = "mentions_stamp" if stamp else "mentions"
            items_by_id[d["chunk_id"]] = d

        # 2) query relevance (fulltext) — attach scores to the clean set for ranking
        try:
            ft_rows = session.execute_read(lambda tx: list(tx.run(
                _LEX_FULLTEXT_SCORE_CYPHER, q=lucene_q, tag=PROTOTYPE_TAG)))
        except Exception as exc:
            ft_rows = []
            print(f"[neo4j] fulltext unavailable ({type(exc).__name__}): {exc}")
        for r in ft_rows:
            cid = r["chunk_id"]
            if cid in items_by_id:
                items_by_id[cid]["score"] = r["score"]
                items_by_id[cid]["via"] = "fulltext+graph"

    # De-duplicate by a normalized-text PREFIX. Overlapping combined chunks restate
    # the same passage with different tails (so full-text keys miss them); keying on
    # the first 300 chars collapses those repeats while keeping genuinely distinct
    # passages (which diverge well before 300 chars). Keep the highest-ranked.
    best: Dict[str, Dict[str, Any]] = {}
    for d in items_by_id.values():
        key = _norm_text(d.get("text"))[:300]
        if not key:
            continue
        cur = best.get(key)
        if cur is None or _lex_rank(d) > _lex_rank(cur):
            best[key] = d

    items = sorted(best.values(), key=_lex_rank, reverse=True)
    if max_lexical and max_lexical > 0:
        items = items[:max_lexical]
    return items


# Cheap graph-derived enrichment (no Weaviate, no extra cost worth worrying about).
_DOMAIN_RELATED_CYPHER = """
MATCH (i:Issue {issue_id:$issue_id})-[:HAS_STAMP]->(s:Stamp)
WHERE $cno IS NULL OR s.catalog_no = $cno
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
WITH i, s, [x IN collect(DISTINCT v.suffix) WHERE x IS NOT NULL] AS suffixes
WITH i, collect({stamp: s.catalog_no, varieties: suffixes}) AS stamp_varieties
OPTIONAL MATCH (i)-[:HAS_PROOF]->(pr:Proof)
WITH stamp_varieties, [x IN collect(DISTINCT pr.code) WHERE x IS NOT NULL] AS proofs
OPTIONAL MATCH (i)-[:HAS_PLATE]->(pl:Plate)
RETURN stamp_varieties AS stamp_varieties, proofs[..40] AS proofs,
       [x IN collect(DISTINCT pl.no) WHERE x IS NOT NULL][..20] AS plates
"""


def fetch_domain_related(driver: Any, stamp: Optional[str] = None) -> Dict[str, Any]:
    """Cheap one-hop domain expansion: variety suffixes per stamp, proof codes, plate numbers."""
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            rows = session.execute_read(
                lambda tx: list(tx.run(_DOMAIN_RELATED_CYPHER,
                                       issue_id=ISSUE_ID, cno=(str(stamp) if stamp else None)))
            )
    except Exception as exc:
        print(f"[neo4j] related path unavailable ({type(exc).__name__}): {exc}")
        return {"stamp_varieties": [], "proofs": [], "plates": []}
    if not rows:
        return {"stamp_varieties": [], "proofs": [], "plates": []}
    r = rows[0]
    return {
        "stamp_varieties": r.get("stamp_varieties") or [],
        "proofs": r.get("proofs") or [],
        "plates": r.get("plates") or [],
    }


def _sources_from_lexical(lexical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate the lexical hits into a ranked 'documents that reference this' list (free — no DB call)."""
    by_doc: Dict[str, Dict[str, Any]] = {}
    for d in lexical:
        doc = d.get("doc_id")
        if not doc:
            continue
        e = by_doc.setdefault(doc, {"doc_id": doc, "chunks": 0, "best_score": None, "best_link": None, "pages": set()})
        e["chunks"] += 1
        s = d.get("score")
        if s is not None:
            e["best_score"] = float(s) if e["best_score"] is None else max(e["best_score"], float(s))
        ls = d.get("link_score")
        if ls is not None:
            e["best_link"] = float(ls) if e["best_link"] is None else max(e["best_link"], float(ls))
        if d.get("page") is not None:
            e["pages"].add(d["page"])
    out = []
    for e in by_doc.values():
        e["pages"] = sorted(e["pages"])
        out.append(e)
    out.sort(
        key=lambda e: (
            e["best_score"] if e["best_score"] is not None else -1.0,
            e["best_link"] if e["best_link"] is not None else -1.0,
            e["chunks"],
        ),
        reverse=True,
    )
    return out


def context_bundle(
    question: str,
    stamp: Optional[str] = None,
    max_lexical: int = 0,
    k_weaviate: int = 5,
    min_link_score: float = 6.0,
    exclude_competing: bool = True,
    include_issue_mentions: bool = True,
    related: bool = True,
) -> Dict[str, Any]:
    """
    Graph-first context bundle with PER-SOURCE budgets. The GRAPH is the knowledge
    base and gets predominance; Weaviate (slow/heavy) is a thin optional tail.

      * ``domain``   -- always first (structured facts).
      * ``related``  -- cheap graph expansion: variety suffixes / proofs / plates.
      * ``sources``  -- ranked list of documents that reference the query (free,
                        aggregated from the lexical hits): the high-quality
                        "where to read more" panel.
      * ``lexical``  -- predominant: ALL distinct relevant chunks from the graph,
                        deduped by text (``max_lexical=0`` = no cap), full text.
      * ``weaviate`` -- least important: only ``k_weaviate`` passages NOT already
                        covered by the graph (set ``k_weaviate=0`` for pure-graph).

    Returns {"domain","related","sources","lexical","weaviate","counts"}.
    """
    question = (question or "").strip()
    related_panel: Dict[str, Any] = {"stamp_varieties": [], "proofs": [], "plates": []}
    try:
        with neo4j_driver() as drv:
            domain = fetch_domain_card(drv)
            if related:
                related_panel = fetch_domain_related(drv, stamp=stamp)
            lexical = fetch_lexical_all(
                drv, question, stamp=stamp, max_lexical=max_lexical,
                min_link_score=min_link_score, exclude_competing=exclude_competing,
                include_issue_mentions=include_issue_mentions,
            )
    except Exception as exc:
        print(f"[neo4j] connection unavailable ({type(exc).__name__}): {exc}")
        domain = {"issue_id": ISSUE_ID, "found": False, "stamps": [], "scott_roster": []}
        lexical = []

    sources = _sources_from_lexical(lexical)

    # Thin Weaviate BACKUP tail — exclude anything already in the lexical set, and
    # never let it overwhelm the graph (hard cap 25; it is the slow/heavy source).
    k_weaviate = max(0, min(int(k_weaviate or 0), 25))
    lex_ids = {d.get("chunk_id") for d in lexical}
    weaviate: List[Dict[str, Any]] = []
    if k_weaviate and k_weaviate > 0:
        raw = fetch_weaviate_evidence(question, k_weaviate * 4)
        for h in raw:
            if h.get("chunk_id") in lex_ids:
                continue
            weaviate.append(h)
            if len(weaviate) >= k_weaviate:
                break

    return {
        "domain": domain,
        "related": related_panel,
        "sources": sources,
        "lexical": lexical,
        "weaviate": weaviate,
        "counts": {"lexical": len(lexical), "weaviate": len(weaviate), "source_docs": len(sources)},
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def answer(question: str, k: int = 6) -> Dict[str, Any]:
    """
    Assemble the grounded, retrieval-only answer card for ``question``.

    NO LLM synthesis happens here — this gathers and returns evidence only.

    Returns a dict with three keys:
      * ``domain``           -- structured Neo4j domain card (the Issue + Mena
                                Stamps + equivalent Scott stamps + illustration +
                                Scott notes).
      * ``neo4j_evidence``   -- top-K lexical passages from the chunk graph,
                                de-duped by chunk_id, each with a citation.
      * ``weaviate_evidence``-- top-K read-only passages from the Oxcart
                                collection (BM25, plus hybrid when a key exists).
    """
    question = (question or "").strip()

    domain: Dict[str, Any]
    neo4j_evidence: List[Dict[str, Any]]
    try:
        with neo4j_driver() as drv:
            domain = fetch_domain_card(drv)
            neo4j_evidence = fetch_neo4j_evidence(drv, question, k)
    except Exception as exc:  # Neo4j down — Weaviate baseline must still return
        print(f"[neo4j] connection unavailable ({type(exc).__name__}): {exc}")
        domain = {"issue_id": ISSUE_ID, "found": False, "error": str(exc), "stamps": [], "scott_roster": []}
        neo4j_evidence = []

    weaviate_evidence = fetch_weaviate_evidence(question, k)

    return {
        "domain": domain,
        "neo4j_evidence": neo4j_evidence,
        "weaviate_evidence": weaviate_evidence,
    }


# --------------------------------------------------------------------------- #
# Pretty-printer (CLI answer card)
# --------------------------------------------------------------------------- #
def _print_domain_card(domain: Dict[str, Any]) -> None:
    print("=" * 78)
    print("ANSWER CARD  (retrieval-only — NO LLM synthesis)")
    print("=" * 78)
    print("\n[ DOMAIN FACTS — Neo4j structured graph ]")
    if not domain.get("found"):
        print("  (no domain card found — has the graph been ingested?)")
        if domain.get("error"):
            print(f"  error: {domain['error']}")
        return

    print(f"  Issue : {domain.get('title') or domain.get('issue_id')}")
    if domain.get("country"):
        print(f"  Country     : {domain['country']}")
    if domain.get("issue_dates"):
        print(f"  Issue dates : {domain['issue_dates']}")
    if domain.get("perforation"):
        print(f"  Perforation : {domain['perforation']}")
    excerpt = domain.get("plain_raw_text_excerpt")
    if excerpt:
        print(f"  Notes       : {excerpt}")

    stamps = domain.get("stamps") or []
    if stamps:
        print("\n  Stamps (Mena -> Scott equivalents):")
        for st in stamps:
            mena = st.get("catalog_no")
            dval = st.get("denomination_value")
            dunit = st.get("denomination_unit")
            denom = " ".join(str(x) for x in (dval, dunit) if x not in (None, ""))
            color = st.get("color")
            head = f"    - Mena {mena}: {denom or '?'}"
            if color:
                head += f" ({color})"
            if st.get("perforation"):
                head += f", {st['perforation']}"
            print(head)
            for scott in st.get("equivalent_scott") or []:
                sc = scott.get("scott_number")
                bits = []
                if scott.get("denomination"):
                    bits.append(str(scott["denomination"]))
                if scott.get("color"):
                    bits.append(str(scott["color"]))
                if scott.get("description"):
                    bits.append(str(scott["description"]))
                vals = []
                if scott.get("mint_value") is not None:
                    vals.append(f"mint {scott['mint_value']}")
                if scott.get("used_value") is not None:
                    vals.append(f"used {scott['used_value']}")
                line = f"        = Scott {sc}: {', '.join(bits) if bits else ''}"
                if vals:
                    line += f"  [{'; '.join(vals)}]"
                if scott.get("perforation"):
                    line += f"  {scott['perforation']}"
                print(line)
                if scott.get("design_name"):
                    desc = scott.get("design_description") or ""
                    print(f"          design: {scott['design_name']} — {_snippet(desc, 160)}")

    roster = domain.get("scott_roster") or []
    if roster:
        print("\n  Scott roster / notes:")
        for r in roster:
            bits = [b for b in (r.get("denomination"), r.get("color"), r.get("description")) if b]
            design = f" [design: {r['design_name']}]" if r.get("design_name") else ""
            print(f"    - Scott {r.get('scott_number')}: {', '.join(str(b) for b in bits)}{design}")


def _print_evidence(title: str, evidence: List[Dict[str, Any]], note: str) -> None:
    print(f"\n[ {title} ]")
    print(f"  {note}")
    if not evidence:
        print("  (no passages)")
        return
    for idx, c in enumerate(evidence, start=1):
        doc = c.get("doc_id") or "?"
        page = c.get("page")
        page_str = f"p.{page}" if page not in (None, "") else "p.?"
        score = c.get("score")
        score_str = f"{score:.3f}" if isinstance(score, float) else "n/a"
        via = c.get("via") or ""
        print(f"  {idx}. [{doc} {page_str}] (score {score_str}, via {via}, chunk {c.get('chunk_id')})")
        print(f"     {c.get('snippet')}")


def print_answer_card(question: str, result: Dict[str, Any]) -> None:
    """Print the assembled answer card, clearly separating the two evidence sources."""
    print(f"\nQUESTION: {question}\n")
    _print_domain_card(result.get("domain") or {})
    _print_evidence(
        "NEO4J-LEXICAL EVIDENCE (chunk graph: fulltext + MENTIONS edges)",
        result.get("neo4j_evidence") or [],
        note="grounded passages with [doc_id p.N] citations",
    )
    _print_evidence(
        "WEAVIATE EVIDENCE (read-only baseline retriever — BM25/hybrid)",
        result.get("weaviate_evidence") or [],
        note="parallel comparison source; snippet prefers clean text_original",
    )
    print("\n" + "=" * 78)
    print("NOTE: retrieval-only. No LLM synthesized this answer; verify via citations.")
    print("=" * 78 + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(
        description="GraphRAG retrieval (Neo4j domain + lexical, Weaviate baseline). No LLM."
    )
    parser.add_argument(
        "--q",
        default="Tell me about the half real blue stamp of the Costa Rica first issue",
        help="Natural-language question about the First Issue.",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=6,
        help="Top-K passages per evidence source.",
    )
    args = parser.parse_args()

    result = answer(args.q, k=args.k)
    print_answer_card(args.q, result)


if __name__ == "__main__":
    main()
