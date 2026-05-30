"""Read-only Mena Catalogue service (Surface Mail navigator + per-issue views).

Powers the ``/api/mena/*`` endpoints. Navigation is scoped to
``Issue.section == MENA_SECTION`` (default "Surface Mail") over the shared Mena
domain graph. Three load tiers keep each issue page fast:

* :func:`list_surface_mail` -- ONE cheap query; all Surface-Mail issues bucketed
  by year (parsed in Python from ``issue_id``; ``CR-YYYY-...`` -> ``YYYY``,
  otherwise "Undated").
* :func:`issue_detail` -- FAST per-issue facts (issue + stamps + counts +
  printer + legal acts + Scott match from :mod:`app.mena_data`). NO Weaviate,
  NO heavy lexical graph.
* :func:`issue_graph` -- LAZY small mini-graph (issue -> stamps -> varieties +
  Scott from the match file). Reuses :mod:`app.graph_service` mint-ids/labels so
  a node clicked here resolves through ``GET /api/node`` identically.
* :func:`issue_evidence` -- LAZY Weaviate **BM25** passages (no OpenAI key
  needed). Client always closed.

Contracts:
* Neo4j READ-ONLY, fully PARAMETERIZED Cypher (no value is f-string-interpolated;
  ``$section`` is the module constant). Weaviate READ-ONLY (BM25 only).
* Every dict that leaves here is passed through :func:`app.deps.sanitize_props`
  so no embedding/vector key (or raw Neo4j temporal type) can leak.
* Retrieval tunables come from ``os.getenv`` (never hardcoded literals).
* No direct LLM/OpenAI/Anthropic calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from neo4j import Driver, ManagedTransaction

# Importing settings first bootstraps sys.path so ``import config`` resolves.
from app import settings  # noqa: F401  (side effect: sys.path bootstrap)
from app import graph_service, mena_data
from app.deps import get_weaviate, sanitize_props
from app.schemas import GraphResponse

import config

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tunables (.env / os.getenv -- never hardcoded literals in the body)
# --------------------------------------------------------------------------- #
_SECTION: str = os.getenv("MENA_SECTION", "Surface Mail")
_EVIDENCE_K_DEFAULT: int = int(os.getenv("MENA_EVIDENCE_K", "6"))
_EVIDENCE_MIN_SCORE: float = float(os.getenv("MENA_EVIDENCE_MIN_SCORE", "0.0"))

_YEAR_RE = re.compile(r"^CR-(\d{4})")
_UNDATED = "Undated"
_SNIPPET_LEN = 280
# Clean Weaviate text fields (text_original preferred; both are vectorizer-safe).
_WEAVIATE_PROPS = ["chunk_id", "doc_id", "text", "text_original", "page_number"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_year(issue_id: str) -> str:
    """``CR-1863-FIRST-ISSUE`` -> ``"1863"``; unparseable ids -> ``"Undated"``."""
    match = _YEAR_RE.match(issue_id or "")
    return match.group(1) if match else _UNDATED


def _year_sort_key(year: str) -> tuple[int, int]:
    """Sort numeric years ascending (numerically); push ``"Undated"`` to the end."""
    if year == _UNDATED or not year.isdigit():
        return (1, 0)
    return (0, int(year))


def _parse_issue_dates(raw: Any) -> Any:
    """Parse the ``issue_dates`` JSON STRING to an object; pass through on failure.

    Must never raise -- a malformed value is returned unchanged so the endpoint
    cannot 500 on bad source data.
    """
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped[:1] in ("{", "["):
            try:
                return json.loads(stripped)
            except (ValueError, TypeError):
                return raw
    return raw


def _issue_facts(issue_node: Any) -> dict[str, Any]:
    """Clean issue facts: reuse graph_service._issue_props (drops heavy/noise keys
    + strips embeddings), then parse the issue_dates JSON string."""
    facts = graph_service._issue_props(issue_node)  # drops _ISSUE_HEAVY_KEYS + sanitizes
    if "issue_dates" in facts:
        facts["issue_dates"] = _parse_issue_dates(facts["issue_dates"])
    return facts


# --------------------------------------------------------------------------- #
# Cypher work functions (read-only, parameterized)
# --------------------------------------------------------------------------- #
def _tx_surface_mail(tx: ManagedTransaction, section: str) -> list[dict[str, Any]]:
    """All issues in *section* with their stamp counts. Scalars only -- the Issue
    node (and its embedding) is never returned."""
    result = tx.run(
        """
        MATCH (i:Issue {section: $section})
        OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
        RETURN i.issue_id AS issue_id, i.title AS title, count(DISTINCT s) AS n_stamps
        ORDER BY i.issue_id
        """,
        section=section,
    )
    return [dict(r) for r in result]


def _tx_issue_exists(tx: ManagedTransaction, issue_id_value: str, section: str) -> bool:
    record = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id, section: $section})
        RETURN count(i) > 0 AS ok
        """,
        issue_id=issue_id_value,
        section=section,
    ).single()
    return bool(record["ok"]) if record else False


def _tx_issue_detail(tx: ManagedTransaction, issue_id_value: str, section: str) -> Optional[dict[str, Any]]:
    """Single round-trip per-issue bundle via scoped CALL subqueries (Neo4j 2025).

    Every projected property/relationship is verified against the live graph
    (Printer.name, LegalAct.{id,type,date}, HAS_PROOF/PLATE/ESSAY/SPECIMEN/
    PRODUCTION_ORDER). All inner matches are OPTIONAL so a missing relationship
    yields null/0 rather than an error.
    """
    record = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id, section: $section})
        CALL (i) {
            OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
            OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(sc:ScottStamp)
            WITH s, collect(DISTINCT {scott_number: sc.scott_number, confidence: eq.confidence}) AS gscott
            ORDER BY s.catalog_no
            RETURN collect(CASE WHEN s IS NULL THEN NULL ELSE {
                catalog_no: s.catalog_no, denomination_value: s.denomination_value,
                denomination_unit: s.denomination_unit, color: s.color,
                perforation: s.perforation, watermark: s.watermark, status: s.status,
                quantity_reported: s.quantity_reported, notes: s.notes,
                graph_scott: [x IN gscott WHERE x.scott_number IS NOT NULL]
            } END) AS stamps_raw
        }
        CALL (i) {
            OPTIONAL MATCH (i)-[:HAS_PROOF]->(p:Proof)
            OPTIONAL MATCH (i)-[:HAS_PLATE]->(pl:Plate)
            OPTIONAL MATCH (i)-[:HAS_ESSAY]->(e:Essay)
            OPTIONAL MATCH (i)-[:HAS_SPECIMEN]->(sp:Specimen)
            OPTIONAL MATCH (i)-[:HAS_PRODUCTION_ORDER]->(po:ProductionOrder)
            RETURN count(DISTINCT p) AS n_proofs, count(DISTINCT pl) AS n_plates,
                   count(DISTINCT e) AS n_essays, count(DISTINCT sp) AS n_specimens,
                   count(DISTINCT po) AS n_production_orders
        }
        CALL (i) {
            OPTIONAL MATCH (i)-[:PRINTED_BY]->(pr:Printer)
            RETURN collect(DISTINCT pr.name)[..5] AS printers
        }
        CALL (i) {
            OPTIONAL MATCH (i)-[:AUTHORIZED_BY]->(la:LegalAct)
            RETURN collect(DISTINCT {id: la.id, type: la.type, date: la.date})[..10] AS legal_acts
        }
        CALL (i) {
            OPTIONAL MATCH (i)-[:HAS_SCOTT_STAMP]->(scs:ScottStamp)
            RETURN collect(DISTINCT scs)[..20] AS graph_scott_roster
        }
        RETURN i AS issue, stamps_raw, n_proofs, n_plates, n_essays, n_specimens,
               n_production_orders, printers, legal_acts, graph_scott_roster
        """,
        issue_id=issue_id_value,
        section=section,
    ).single()
    return dict(record) if record else None


def _tx_issue_graph(tx: ManagedTransaction, issue_id_value: str, section: str) -> list[dict[str, Any]]:
    """Issue + its stamps + varieties (for the lazy mini-graph)."""
    result = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id, section: $section})
        OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
        OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
        RETURN i AS issue, s AS stamp, v AS variety
        ORDER BY s.catalog_no
        """,
        issue_id=issue_id_value,
        section=section,
    )
    return [dict(r) for r in result]


def _tx_issue_terms(tx: ManagedTransaction, issue_id_value: str, section: str) -> Optional[dict[str, Any]]:
    """Cheap query for the BM25 query terms (title + colors + units)."""
    record = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id, section: $section})
        OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
        RETURN i.title AS title,
               collect(DISTINCT s.color) AS colors,
               collect(DISTINCT s.denomination_unit) AS units
        """,
        issue_id=issue_id_value,
        section=section,
    ).single()
    return dict(record) if record else None


# --------------------------------------------------------------------------- #
# Public: navigator
# --------------------------------------------------------------------------- #
def list_surface_mail(driver: Driver) -> list[dict[str, Any]]:
    """All Surface-Mail issues grouped by year (one fast query, no node payloads)."""
    rows = graph_service._read(driver, _tx_surface_mail, section=_SECTION)

    by_year: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        issue_id = row.get("issue_id")
        if not issue_id:
            continue
        year = parse_year(issue_id)
        by_year.setdefault(year, []).append(
            {
                "issue_id": issue_id,
                "title": row.get("title"),
                "n_stamps": int(row.get("n_stamps") or 0),
                "year": year,
            }
        )

    years: list[dict[str, Any]] = []
    for year in sorted(by_year.keys(), key=_year_sort_key):
        issues = sorted(by_year[year], key=lambda it: (str(it.get("title") or ""), it["issue_id"]))
        years.append({"year": year, "count": len(issues), "issues": issues})
    return years


def issue_exists(driver: Driver, issue_id: str) -> bool:
    """Cheap existence check (used by the router's 404 gate)."""
    return bool(graph_service._read(driver, _tx_issue_exists, issue_id_value=issue_id, section=_SECTION))


# --------------------------------------------------------------------------- #
# Public: fast per-issue facts
# --------------------------------------------------------------------------- #
def issue_detail(driver: Driver, issue_id: str) -> Optional[dict[str, Any]]:
    """FAST per-issue facts. Returns None when the issue is absent / not in section."""
    record = graph_service._read(driver, _tx_issue_detail, issue_id_value=issue_id, section=_SECTION)
    if not record or record.get("issue") is None:
        return None

    facts = _issue_facts(record["issue"])

    stamps: list[dict[str, Any]] = []
    for st in record.get("stamps_raw") or []:
        if not st:
            continue
        clean = sanitize_props(dict(st))
        clean["graph_scott"] = [g for g in (clean.get("graph_scott") or []) if g.get("scott_number") is not None]
        stamps.append(clean)

    counts = {
        "stamps": len(stamps),
        "proofs": int(record.get("n_proofs") or 0),
        "plates": int(record.get("n_plates") or 0),
        "essays": int(record.get("n_essays") or 0),
        "specimens": int(record.get("n_specimens") or 0),
        "production_orders": int(record.get("n_production_orders") or 0),
    }
    printers = [p for p in (record.get("printers") or []) if p]
    legal_acts = [sanitize_props(dict(la)) for la in (record.get("legal_acts") or []) if la and la.get("id")]
    roster = [sanitize_props(dict(sc)) for sc in (record.get("graph_scott_roster") or []) if sc is not None]

    return {
        "issue_id": issue_id,
        "year": parse_year(issue_id),
        "title": facts.get("title"),
        "issue": facts,
        "stamps": stamps,
        "counts": counts,
        "printer": printers[0] if printers else None,
        "printers": printers,
        "legal_acts": legal_acts,
        "scott_match": mena_data.scott_match_for(issue_id),
        "graph_scott_roster": roster,
    }


# --------------------------------------------------------------------------- #
# Public: lazy mini-graph
# --------------------------------------------------------------------------- #
def issue_graph(driver: Driver, issue_id: str) -> GraphResponse:
    """LAZY small graph: issue -> stamps -> varieties + Scott (from match file).

    Reuses graph_service mint-ids/labels/builder so node ids/types match
    ``/api/graph`` (a clicked node still resolves via ``GET /api/node``). Scott
    nodes come from the match file (graph EQUIVALENT_TO only exists for the
    First Issue), so this works for every Surface-Mail issue.
    """
    builder = graph_service._GraphBuilder()
    rows = graph_service._read(driver, _tx_issue_graph, issue_id_value=issue_id, section=_SECTION)
    if not rows or rows[0].get("issue") is None:
        return builder.build()

    issue_node = rows[0]["issue"]
    iprops = _issue_facts(issue_node)
    issue_nid = graph_service.issue_id(iprops.get("issue_id", issue_id))
    builder.add_node(issue_nid, graph_service._issue_label(iprops), "Issue", iprops)

    seen_stamps: set[str] = set()
    for row in rows:
        stamp_node = row.get("stamp")
        if stamp_node is not None:
            sprops = dict(stamp_node)
            catalog_no = sprops.get("catalog_no")
            if catalog_no is not None:
                cno = str(catalog_no)
                stamp_nid = graph_service.stamp_id(catalog_no)
                builder.add_node(stamp_nid, graph_service._stamp_label(sprops), "Stamp", sanitize_props(sprops))
                builder.add_edge(issue_nid, stamp_nid, "HAS_STAMP")
                seen_stamps.add(cno)

                variety_node = row.get("variety")
                if variety_node is not None:
                    vprops = dict(variety_node)
                    v_nid = graph_service.variety_id(vprops.get("base_catalog_no"), vprops.get("suffix"))
                    builder.add_node(v_nid, graph_service._variety_label(vprops), "Variety", sanitize_props(vprops))
                    builder.add_edge(stamp_nid, v_nid, "HAS_VARIETY")

    # Scott equivalents from the match file (works for non-first-issue issues).
    for match in mena_data.scott_match_for(issue_id):
        scott_no = match.get("scott")
        if not scott_no:
            continue
        scott_nid = graph_service.scott_id(scott_no)
        detail = match.get("scott_detail") or {}
        builder.add_node(
            scott_nid,
            f"Scott {scott_no}",
            "ScottStamp",
            sanitize_props({"scott_number": scott_no, **detail}),
        )
        mena_no = match.get("mena")
        if mena_no is not None and str(mena_no) in seen_stamps:
            builder.add_edge(
                graph_service.stamp_id(mena_no),
                scott_nid,
                "EQUIVALENT_TO",
                {"confidence": match.get("confidence")},
            )

    return builder.build()


# --------------------------------------------------------------------------- #
# Public: lazy Weaviate BM25 evidence
# --------------------------------------------------------------------------- #
def _build_bm25_query(title: Optional[str], year: str, colors: list[Any], units: list[Any]) -> str:
    """Compose a BM25 query from the issue's title + year + stamp colors/units."""
    tokens: list[str] = []
    seen: set[str] = set()
    parts: list[Any] = [title]
    if year and year != _UNDATED:
        parts.append(year)
    parts.extend(colors or [])
    parts.extend(units or [])
    for part in parts:
        text = str(part).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            tokens.append(text)
    return " ".join(tokens) or (str(title).strip() if title else "Costa Rica")


def issue_evidence(driver: Driver, issue_id: str, k: Optional[int] = None) -> dict[str, Any]:
    """LAZY Weaviate BM25 passages for an issue. No OpenAI key required.

    ``query`` and ``k`` are computed BEFORE the try block so a coding error is
    NOT silently swallowed into a permanent empty result; only genuine Weaviate
    failures degrade to ``[]`` (so the endpoint never 500s when Weaviate is down).
    Returns ``{"query": <str>, "passages": [...]}``.
    """
    k = max(0, int(k if k is not None else _EVIDENCE_K_DEFAULT))
    if k == 0:
        return {"query": "", "passages": []}

    terms = graph_service._read(driver, _tx_issue_terms, issue_id_value=issue_id, section=_SECTION)
    if terms is None:
        return {"query": "", "passages": []}

    query = _build_bm25_query(
        terms.get("title"),
        parse_year(issue_id),
        [c for c in (terms.get("colors") or []) if c],
        [u for u in (terms.get("units") or []) if u],
    )

    passages: list[dict[str, Any]] = []
    client = None
    try:
        # Imported inside the try so a missing/renamed weaviate package degrades
        # to an empty result (never 500), same as a Weaviate-down failure.
        import weaviate.classes as wvc

        client = get_weaviate()
        coll = client.collections.get(config.OXCART_COLLECTION)
        resp = coll.query.bm25(
            query=query,
            limit=k,
            return_properties=_WEAVIATE_PROPS,
            return_metadata=wvc.query.MetadataQuery(score=True),
        )
        for obj in resp.objects or []:
            props = obj.properties or {}
            meta = getattr(obj, "metadata", None)
            raw_score = getattr(meta, "score", None) if meta is not None else None
            score = float(raw_score) if isinstance(raw_score, (int, float)) else None
            # Unscored hits are kept (BM25 normally returns a score); the min only
            # filters scored hits below the configured threshold (default 0.0).
            if score is not None and score < _EVIDENCE_MIN_SCORE:
                continue
            snippet_src = props.get("text_original") or props.get("text") or ""
            passages.append(
                sanitize_props(
                    {
                        "chunk_id": props.get("chunk_id"),
                        "doc_id": props.get("doc_id"),
                        "page": props.get("page_number"),
                        "snippet": " ".join(str(snippet_src).split())[:_SNIPPET_LEN],
                        "score": score,
                    }
                )
            )
    except Exception as exc:  # noqa: BLE001 - Weaviate down/unavailable -> degrade, never 500
        logger.warning("evidence BM25 unavailable (%s): %s", type(exc).__name__, exc)
        passages = []
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # pragma: no cover - best-effort close
                pass

    return {"query": query, "passages": passages}
