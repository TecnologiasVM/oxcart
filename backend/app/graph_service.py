"""Read-only Neo4j graph service for the First Issue KG backend.

Builds graph views (domain subgraph + lexical evidence), single-node detail
payloads, and the landing overview. Every query is read-only and fully
parameterized (no value is ever f-string-interpolated into Cypher). Every node /
detail / overview payload is passed through ``deps.sanitize_props`` so that no
embedding / vector property can leak to the client.

The driver is the shared singleton on ``app.state.neo4j`` (created in
``app.deps.lifespan``); callers pass it in. Reads run with
``session.execute_read(...)`` against ``config.NEO4J_DATABASE``.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from neo4j import Driver, ManagedTransaction

from app import settings  # noqa: F401  (kept so the import order stays as it was)
from app.deps import sanitize_props
from app.schemas import GraphEdge, GraphNode, GraphResponse, NodeDetail

from oxcart import config
from oxcart.catalogue_lookup import denomination

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
DEFAULT_ISSUE_TITLE = "First Issue 1863"
_PREVIEW_LEN = 180

# Heavy / noisy Issue properties not useful in the UI: a duplicate full-text
# field (search_corpus) and figure-caption OCR noise (pictures_raw_text:
# "logo: … : figure"), plus ingest bookkeeping. Dropped from the graph payload
# and the Issue detail; the curated plain_raw_text / title / dates / perforation
# / country are kept. (Embeddings are stripped separately by sanitize_props.)
_ISSUE_HEAVY_KEYS = frozenset(
    {"search_corpus", "pictures_raw_text", "ingested_at", "source", "section"}
)


def _issue_props(issue_node: Any) -> dict[str, Any]:
    """Issue node -> UI-safe props: drop heavy/noisy keys, then strip embeddings."""
    trimmed = {k: v for k, v in dict(issue_node).items() if k not in _ISSUE_HEAVY_KEYS}
    return sanitize_props(trimmed)


# Display-only corrections for known Mena source-data errors. The read-only Mena
# graph is NEVER mutated; we correct the value only when projecting for the UI.
# The corrections, and why each one is made, are kept in one place for the
# explorer and the question path: oxcart.catalogue_lookup.DENOMINATION_CORRECTIONS
# (Mena 1A of the first issue is the half real; the source records 1.5).
def _display_denom(props: dict[str, Any]) -> tuple[Any, Any]:
    """Return (value, unit) for display, applying known Mena display corrections.

    The explorer shows the first issue (``config.ISSUE_ID``): a row without an
    ``issue_id`` of its own is read as one of its stamps."""
    return denomination(props.get("issue_id") or config.ISSUE_ID, props.get("catalog_no"),
                        props.get("denomination_value"), props.get("denomination_unit"))


# --------------------------------------------------------------------------- #
# Mint-id helpers (stable, prefix-tagged node ids for the UI)
# --------------------------------------------------------------------------- #
def issue_id(value: str) -> str:
    return f"issue:{value}"


def stamp_id(catalog_no: str) -> str:
    return f"stamp:{catalog_no}"


def scott_id(scott_number: Any) -> str:
    return f"scott:{scott_number}"


def variety_id(base_catalog_no: Any, suffix: Any) -> str:
    return f"variety:{base_catalog_no}|{suffix}"


def illustration_id(illustration_number: Any) -> str:
    return f"ill:{illustration_number}"


def document_id(doc_id: str) -> str:
    return f"doc:{doc_id}"


def chunk_id(chunk_id_value: str) -> str:
    return f"chunk:{chunk_id_value}"


def _parse_node_id(node_id: str) -> tuple[str, str]:
    """Split a mint id into ``(prefix, raw)``. Raises ValueError if malformed."""
    if ":" not in node_id:
        raise ValueError(f"Malformed node id (missing prefix): {node_id!r}")
    prefix, raw = node_id.split(":", 1)
    return prefix, raw


# --------------------------------------------------------------------------- #
# Transaction runner
# --------------------------------------------------------------------------- #
def _read(driver: Driver, work: Callable[..., Any], **params: Any) -> Any:
    """Run *work* in a managed read transaction against the configured database."""
    with driver.session(database=config.NEO4J_DATABASE) as session:
        return session.execute_read(work, **params)


# --------------------------------------------------------------------------- #
# Caption / preview shaping
# --------------------------------------------------------------------------- #
def _issue_label(props: dict[str, Any]) -> str:
    return props.get("title") or DEFAULT_ISSUE_TITLE


def _stamp_label(props: dict[str, Any]) -> str:
    catalog_no = props.get("catalog_no", "")
    denom, unit = _display_denom(props)
    unit = unit or ""
    denom_part = f" {denom} {unit}".rstrip() if denom is not None else ""
    return f"Mena {catalog_no}{denom_part}".strip()


def _scott_label(props: dict[str, Any]) -> str:
    return f"Scott {props.get('scott_number', '')}".strip()


def _variety_label(props: dict[str, Any]) -> str:
    return str(props.get("suffix") or "variety")


def _illustration_label(props: dict[str, Any]) -> str:
    return str(props.get("design_name") or props.get("illustration_number") or "illustration")


def _document_label(props: dict[str, Any]) -> str:
    return str(props.get("doc_id") or "document")


def _chunk_label(props: dict[str, Any]) -> str:
    return f"{props.get('doc_id', '')} p.{props.get('page', '')}".strip()


def _chunk_data(props: dict[str, Any]) -> dict[str, Any]:
    """Sanitize chunk props and add a short text preview (never the embedding)."""
    data = sanitize_props(props)
    text = props.get("text") or ""
    data["preview"] = text[:_PREVIEW_LEN]
    # Avoid shipping the full chunk body inside a graph node payload.
    data.pop("text", None)
    return data


# --------------------------------------------------------------------------- #
# Node/edge accumulator
# --------------------------------------------------------------------------- #
class _GraphBuilder:
    """Collects unique nodes and edges and emits a GraphResponse."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}

    def add_node(self, node_id: str, label: str, node_type: str, data: dict[str, Any]) -> None:
        if node_id not in self._nodes:
            self._nodes[node_id] = GraphNode(id=node_id, label=label, type=node_type, data=data)

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        data: Optional[dict[str, Any]] = None,
    ) -> None:
        edge_id = f"{source}->{target}:{edge_type}"
        if edge_id not in self._edges:
            self._edges[edge_id] = GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                type=edge_type,
                data=sanitize_props(data or {}),
            )

    def stats(self) -> dict[str, Any]:
        counts: dict[str, Any] = {}
        for node in self._nodes.values():
            counts[node.type] = counts.get(node.type, 0) + 1
        counts["nodes"] = len(self._nodes)
        counts["edges"] = len(self._edges)
        return counts

    def build(self) -> GraphResponse:
        return GraphResponse(
            nodes=list(self._nodes.values()),
            edges=list(self._edges.values()),
            stats=self.stats(),
        )


# --------------------------------------------------------------------------- #
# Cypher work functions (read-only, parameterized)
# --------------------------------------------------------------------------- #
def _tx_domain_subgraph(tx: ManagedTransaction, issue_id_value: str) -> list[Any]:
    """Cypher #12 core -- Issue + Stamps + Varieties + Scott + equivalence + illustrations."""
    result = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id})
        OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
        OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
        OPTIONAL MATCH (i)-[:HAS_SCOTT_STAMP]->(sc:ScottStamp)
        OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(sc2:ScottStamp)
        OPTIONAL MATCH (sc)-[:DEPICTS]->(ill:Illustration)
        OPTIONAL MATCH (sc)-[:VARIETY_OF]->(scbase:ScottStamp)
        RETURN i AS issue, s AS stamp, v AS variety, sc AS scott,
               sc2 AS equiv_scott, eq AS equiv_rel, ill AS illustration,
               scbase AS scott_base
        """,
        issue_id=issue_id_value,
    )
    return list(result)


def _tx_top_documents(
    tx: ManagedTransaction,
    issue_id_value: str,
    proto: str,
    clean: bool,
    min_score: float,
    max_docs: int,
) -> list[dict[str, Any]]:
    """Documents ranked by qualifying MENTIONS count (clean-aware)."""
    result = tx.run(
        """
        MATCH (d:Document {prototype: $proto})-[:HAS_CHUNK]->(c:Chunk)
              -[m:MENTIONS]->(i:Issue {issue_id: $issue_id})
        WHERE m.score >= $min_score
          AND ($clean = false OR NOT "COMPETING" IN coalesce(m.signals, []))
        WITH d, count(DISTINCT c) AS qualifying_chunks
        RETURN d.doc_id AS doc_id, qualifying_chunks
        ORDER BY qualifying_chunks DESC, doc_id ASC
        LIMIT $max_docs
        """,
        proto=proto,
        issue_id=issue_id_value,
        min_score=min_score,
        clean=clean,
        max_docs=max_docs,
    )
    return [dict(r) for r in result]


def _tx_chunks_for_documents(
    tx: ManagedTransaction,
    doc_ids: list[str],
    issue_id_value: str,
    proto: str,
    clean: bool,
    min_score: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Top chunks for a LIST of documents in ONE round-trip (score-filtered, clean-aware).

    Replaces the per-document fetch loop (N+1). For each document the qualifying
    chunks are ranked by MENTIONS score and capped at ``$limit`` via a per-document
    ``CALL (d) { ... }`` scoped subquery (the Neo4j 5.23+/2025.x variable-scope
    form). Rows are returned flat and pivoted by ``doc_id`` in Python.
    """
    result = tx.run(
        """
        UNWIND $doc_ids AS did
        MATCH (d:Document {prototype: $proto, doc_id: did})
        CALL (d) {
            MATCH (d)-[:HAS_CHUNK]->(c:Chunk)-[m:MENTIONS]->(i:Issue {issue_id: $issue_id})
            WHERE m.score >= $min_score
              AND ($clean = false OR NOT "COMPETING" IN coalesce(m.signals, []))
            WITH c, m
            ORDER BY m.score DESC
            LIMIT $limit
            OPTIONAL MATCH (c)-[ms:MENTIONS_STAMP]->(s:Stamp)
            RETURN c AS chunk,
                   m.score AS mention_score,
                   m.signals AS mention_signals,
                   m.confidence AS mention_confidence,
                   collect(DISTINCT {catalog_no: s.catalog_no,
                                     confidence: ms.confidence,
                                     signals: ms.signals}) AS stamp_links
        }
        RETURN d.doc_id AS doc_id, chunk, mention_score, mention_signals,
               mention_confidence, stamp_links
        """,
        proto=proto,
        doc_ids=doc_ids,
        issue_id=issue_id_value,
        min_score=min_score,
        clean=clean,
        limit=limit,
    )
    return [dict(r) for r in result]


def _tx_stamp_subgraph(
    tx: ManagedTransaction,
    catalog_no_value: str,
    issue_id_value: str,
    proto: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Cypher #13 -- one Mena stamp + domain context + MENTIONS_STAMP evidence."""
    result = tx.run(
        """
        MATCH (s:Stamp {catalog_no: $catalog_no})
        OPTIONAL MATCH (i:Issue {issue_id: $issue_id})-[:HAS_STAMP]->(s)
        OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
        OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(sc:ScottStamp)
        OPTIONAL MATCH (c:Chunk {prototype: $proto})-[m:MENTIONS_STAMP]->(s)
        WITH s, i, v, sc, eq, c, m
        ORDER BY coalesce(c.link_score, 0.0) DESC
        WITH s, i,
             collect(DISTINCT v) AS varieties,
             collect(DISTINCT {scott: sc, confidence: eq.confidence}) AS scott_links,
             [x IN collect(DISTINCT {chunk: c, confidence: m.confidence, signals: m.signals})
                WHERE x.chunk IS NOT NULL][..$limit] AS evidence
        RETURN s AS stamp, i AS issue, varieties, scott_links, evidence
        """,
        catalog_no=catalog_no_value,
        issue_id=issue_id_value,
        proto=proto,
        limit=limit,
    )
    return [dict(r) for r in result]


# --------------------------------------------------------------------------- #
# Public: build_graph
# --------------------------------------------------------------------------- #
def build_graph(
    driver: Driver,
    clean: bool = True,
    max_docs: int = 10,
    chunks_per_doc: int = 5,
    min_score: float = 6.0,
) -> GraphResponse:
    """Build the full domain subgraph plus the top *max_docs* lexical documents.

    Domain core: Issue, its Stamps (HAS_STAMP), Varieties (HAS_VARIETY),
    ScottStamps (HAS_SCOTT_STAMP), EQUIVALENT_TO links, Illustrations (DEPICTS),
    and VARIETY_OF links. Lexical layer: the top documents by qualifying MENTIONS
    count, each with up to *chunks_per_doc* qualifying chunks, plus HAS_CHUNK,
    MENTIONS, and MENTIONS_STAMP edges.
    """
    builder = _GraphBuilder()
    iid = config.ISSUE_ID

    domain_rows = _read(driver, _tx_domain_subgraph, issue_id_value=iid)
    _add_domain_subgraph(builder, domain_rows, iid)

    top_docs = _read(
        driver,
        _tx_top_documents,
        issue_id_value=iid,
        proto=config.PROTOTYPE_TAG,
        clean=clean,
        min_score=min_score,
        max_docs=max_docs,
    )

    # Add the Document nodes, then fetch ALL of their chunks in ONE round-trip
    # (previously an N+1 loop of one _read per document, up to max_docs reads).
    doc_ids: list[str] = []
    for doc_row in top_docs:
        doc_id_value = doc_row.get("doc_id")
        if not doc_id_value:
            continue
        doc_ids.append(doc_id_value)
        builder.add_node(
            document_id(doc_id_value),
            _document_label({"doc_id": doc_id_value}),
            "Document",
            sanitize_props({"doc_id": doc_id_value, "qualifying_chunks": doc_row.get("qualifying_chunks")}),
        )

    if doc_ids:
        chunk_rows = _read(
            driver,
            _tx_chunks_for_documents,
            doc_ids=doc_ids,
            issue_id_value=iid,
            proto=config.PROTOTYPE_TAG,
            clean=clean,
            min_score=min_score,
            limit=chunks_per_doc,
        )
        # Pivot the flat rows by doc_id, then add each document's chunk subgraph.
        rows_by_doc: dict[str, list[dict[str, Any]]] = {}
        for crow in chunk_rows:
            rows_by_doc.setdefault(str(crow.get("doc_id")), []).append(crow)
        for doc_id_value in doc_ids:
            _add_chunk_rows(builder, document_id(doc_id_value), rows_by_doc.get(doc_id_value, []), iid)

    return builder.build()


def _add_domain_subgraph(builder: _GraphBuilder, rows: list[Any], iid: str) -> None:
    """Add Issue + Stamp/Variety/Scott/Illustration nodes and their edges."""
    issue_nid = issue_id(iid)
    issue_added = False

    for row in rows:
        issue_node = row.get("issue")
        if issue_node is not None and not issue_added:
            iprops = dict(issue_node)
            builder.add_node(issue_nid, _issue_label(iprops), "Issue", _issue_props(issue_node))
            issue_added = True

        stamp_node = row.get("stamp")
        stamp_nid: Optional[str] = None
        if stamp_node is not None:
            sprops = dict(stamp_node)
            catalog_no = sprops.get("catalog_no")
            if catalog_no is not None:
                stamp_nid = stamp_id(catalog_no)
                builder.add_node(stamp_nid, _stamp_label(sprops), "Stamp", sanitize_props(sprops))
                builder.add_edge(issue_nid, stamp_nid, "HAS_STAMP")

        variety_node = row.get("variety")
        if variety_node is not None and stamp_nid is not None:
            vprops = dict(variety_node)
            v_nid = variety_id(vprops.get("base_catalog_no"), vprops.get("suffix"))
            builder.add_node(v_nid, _variety_label(vprops), "Variety", sanitize_props(vprops))
            builder.add_edge(stamp_nid, v_nid, "HAS_VARIETY")

        scott_node = row.get("scott")
        scott_nid: Optional[str] = None
        if scott_node is not None:
            scprops = dict(scott_node)
            scnum = scprops.get("scott_number")
            if scnum is not None:
                scott_nid = scott_id(scnum)
                builder.add_node(scott_nid, _scott_label(scprops), "ScottStamp", sanitize_props(scprops))
                builder.add_edge(issue_nid, scott_nid, "HAS_SCOTT_STAMP")

        equiv_scott_node = row.get("equiv_scott")
        if equiv_scott_node is not None and stamp_nid is not None:
            eqprops = dict(equiv_scott_node)
            eq_scnum = eqprops.get("scott_number")
            if eq_scnum is not None:
                eq_nid = scott_id(eq_scnum)
                builder.add_node(eq_nid, _scott_label(eqprops), "ScottStamp", sanitize_props(eqprops))
                rel = row.get("equiv_rel")
                rel_props = dict(rel) if rel is not None else {}
                builder.add_edge(stamp_nid, eq_nid, "EQUIVALENT_TO", rel_props)

        illustration_node = row.get("illustration")
        if illustration_node is not None and scott_nid is not None:
            illprops = dict(illustration_node)
            ill_num = illprops.get("illustration_number")
            ill_nid = illustration_id(ill_num)
            builder.add_node(ill_nid, _illustration_label(illprops), "Illustration", sanitize_props(illprops))
            builder.add_edge(scott_nid, ill_nid, "DEPICTS")

        scott_base_node = row.get("scott_base")
        if scott_base_node is not None and scott_nid is not None:
            baseprops = dict(scott_base_node)
            base_scnum = baseprops.get("scott_number")
            if base_scnum is not None:
                base_nid = scott_id(base_scnum)
                builder.add_node(base_nid, _scott_label(baseprops), "ScottStamp", sanitize_props(baseprops))
                builder.add_edge(scott_nid, base_nid, "VARIETY_OF")


def _add_chunk_rows(builder: _GraphBuilder, doc_nid: str, chunk_rows: list[dict[str, Any]], iid: str) -> None:
    """Add Chunk nodes + HAS_CHUNK / MENTIONS / MENTIONS_STAMP edges for one document."""
    issue_nid = issue_id(iid)
    for crow in chunk_rows:
        chunk_node = crow.get("chunk")
        if chunk_node is None:
            continue
        cprops = dict(chunk_node)
        cid = cprops.get("chunk_id")
        if cid is None:
            continue
        chunk_nid = chunk_id(cid)
        builder.add_node(chunk_nid, _chunk_label(cprops), "Chunk", _chunk_data(cprops))
        builder.add_edge(doc_nid, chunk_nid, "HAS_CHUNK")
        builder.add_edge(
            chunk_nid,
            issue_nid,
            "MENTIONS",
            {
                "score": crow.get("mention_score"),
                "signals": crow.get("mention_signals"),
                "confidence": crow.get("mention_confidence"),
            },
        )
        for link in crow.get("stamp_links") or []:
            catalog_no = link.get("catalog_no")
            if not catalog_no:
                continue
            builder.add_edge(
                chunk_nid,
                stamp_id(catalog_no),
                "MENTIONS_STAMP",
                {"confidence": link.get("confidence"), "signals": link.get("signals")},
            )


# --------------------------------------------------------------------------- #
# Public: build_stamp_graph
# --------------------------------------------------------------------------- #
def build_stamp_graph(
    driver: Driver,
    catalog_no: str,
    max_docs: int = 12,
    chunks_per_doc: int = 5,
    min_score: float = 6.0,
) -> GraphResponse:
    """Build a stamp-centric subgraph: one Mena stamp + domain context + evidence.

    Wraps cypher #13 (stamp + Issue + Varieties + equivalent ScottStamp + the
    chunks that MENTIONS_STAMP it). *max_docs* caps the number of distinct
    evidence documents; *chunks_per_doc* caps chunks per document. *min_score* is
    accepted for signature symmetry with :func:`build_graph` (the stamp evidence
    set is already gated by the MENTIONS_STAMP edge).
    """
    builder = _GraphBuilder()
    iid = config.ISSUE_ID

    rows = _read(
        driver,
        _tx_stamp_subgraph,
        catalog_no_value=catalog_no,
        issue_id_value=iid,
        proto=config.PROTOTYPE_TAG,
        limit=max_docs * chunks_per_doc,
    )
    if not rows:
        return builder.build()

    row = rows[0]
    stamp_node = row.get("stamp")
    if stamp_node is None:
        return builder.build()

    sprops = dict(stamp_node)
    stamp_nid = stamp_id(sprops.get("catalog_no", catalog_no))
    builder.add_node(stamp_nid, _stamp_label(sprops), "Stamp", sanitize_props(sprops))

    issue_node = row.get("issue")
    if issue_node is not None:
        iprops = dict(issue_node)
        issue_nid = issue_id(iprops.get("issue_id", iid))
        builder.add_node(issue_nid, _issue_label(iprops), "Issue", _issue_props(issue_node))
        builder.add_edge(issue_nid, stamp_nid, "HAS_STAMP")

    for variety_node in row.get("varieties") or []:
        if variety_node is None:
            continue
        vprops = dict(variety_node)
        v_nid = variety_id(vprops.get("base_catalog_no"), vprops.get("suffix"))
        builder.add_node(v_nid, _variety_label(vprops), "Variety", sanitize_props(vprops))
        builder.add_edge(stamp_nid, v_nid, "HAS_VARIETY")

    for link in row.get("scott_links") or []:
        scott_node = link.get("scott")
        if scott_node is None:
            continue
        scprops = dict(scott_node)
        scnum = scprops.get("scott_number")
        if scnum is None:
            continue
        scott_nid = scott_id(scnum)
        builder.add_node(scott_nid, _scott_label(scprops), "ScottStamp", sanitize_props(scprops))
        builder.add_edge(stamp_nid, scott_nid, "EQUIVALENT_TO", {"confidence": link.get("confidence")})

    # Evidence chunks (and their documents), capped per document.
    per_doc_count: dict[str, int] = {}
    for ev in row.get("evidence") or []:
        chunk_node = ev.get("chunk")
        if chunk_node is None:
            continue
        cprops = dict(chunk_node)
        cid = cprops.get("chunk_id")
        doc_id_value = cprops.get("doc_id")
        if cid is None or not doc_id_value:
            continue
        if per_doc_count.get(doc_id_value, 0) >= chunks_per_doc:
            continue
        per_doc_count[doc_id_value] = per_doc_count.get(doc_id_value, 0) + 1

        doc_nid = document_id(doc_id_value)
        builder.add_node(
            doc_nid,
            _document_label({"doc_id": doc_id_value}),
            "Document",
            sanitize_props({"doc_id": doc_id_value}),
        )

        chunk_nid = chunk_id(cid)
        builder.add_node(chunk_nid, _chunk_label(cprops), "Chunk", _chunk_data(cprops))
        builder.add_edge(doc_nid, chunk_nid, "HAS_CHUNK")
        builder.add_edge(
            chunk_nid,
            stamp_nid,
            "MENTIONS_STAMP",
            {"confidence": ev.get("confidence"), "signals": ev.get("signals")},
        )

    return builder.build()


# --------------------------------------------------------------------------- #
# Node detail work functions
# --------------------------------------------------------------------------- #
def _tx_issue_detail(tx: ManagedTransaction, issue_id_value: str) -> Optional[dict[str, Any]]:
    record = tx.run(
        """
        MATCH (i:Issue {issue_id: $issue_id})
        OPTIONAL MATCH (i)-[:HAS_SCOTT_STAMP]->(sc:ScottStamp)
        RETURN i AS issue, collect(DISTINCT sc) AS roster
        """,
        issue_id=issue_id_value,
    ).single()
    return dict(record) if record else None


def _tx_stamp_detail(tx: ManagedTransaction, catalog_no_value: str, proto: str) -> Optional[dict[str, Any]]:
    record = tx.run(
        """
        MATCH (s:Stamp {catalog_no: $catalog_no})
        OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
        OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(sc:ScottStamp)
        OPTIONAL MATCH (c:Chunk {prototype: $proto})-[:MENTIONS_STAMP]->(s)
        RETURN s AS stamp,
               collect(DISTINCT v) AS varieties,
               collect(DISTINCT {scott: sc, confidence: eq.confidence}) AS scott_links,
               count(DISTINCT c) AS evidence_chunks
        """,
        catalog_no=catalog_no_value,
        proto=proto,
    ).single()
    return dict(record) if record else None


def _tx_scott_detail(tx: ManagedTransaction, scott_number_value: str) -> Optional[dict[str, Any]]:
    record = tx.run(
        """
        MATCH (sc:ScottStamp {scott_number: $scott_number})
        OPTIONAL MATCH (sc)-[:DEPICTS]->(ill:Illustration)
        OPTIONAL MATCH (s:Stamp)-[eq:EQUIVALENT_TO]->(sc)
        OPTIONAL MATCH (sc)-[:VARIETY_OF]->(scbase:ScottStamp)
        RETURN sc AS scott,
               collect(DISTINCT ill) AS illustrations,
               collect(DISTINCT {stamp: s, confidence: eq.confidence}) AS equivalent_mena,
               collect(DISTINCT scbase) AS variety_of
        """,
        scott_number=scott_number_value,
    ).single()
    return dict(record) if record else None


def _tx_document_detail(tx: ManagedTransaction, doc_id_value: str, proto: str) -> Optional[dict[str, Any]]:
    record = tx.run(
        """
        MATCH (d:Document {prototype: $proto, doc_id: $doc_id})
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        WITH d, c
        ORDER BY coalesce(c.link_score, 0.0) DESC
        WITH d,
             count(DISTINCT c) AS chunk_count,
             collect(DISTINCT c.page) AS pages,
             collect(c)[..5] AS top_chunks
        RETURN d AS document, chunk_count, pages, top_chunks
        """,
        proto=proto,
        doc_id=doc_id_value,
    ).single()
    return dict(record) if record else None


def _tx_chunk_detail(tx: ManagedTransaction, chunk_id_value: str, proto: str) -> Optional[dict[str, Any]]:
    record = tx.run(
        """
        MATCH (c:Chunk {prototype: $proto, chunk_id: $chunk_id})
        OPTIONAL MATCH (c)-[m:MENTIONS]->(i:Issue)
        OPTIONAL MATCH (c)-[ms:MENTIONS_STAMP]->(s:Stamp)
        RETURN c AS chunk,
               m.score AS mention_score,
               m.signals AS mention_signals,
               m.confidence AS mention_confidence,
               collect(DISTINCT {catalog_no: s.catalog_no,
                                 confidence: ms.confidence,
                                 signals: ms.signals}) AS stamp_links
        """,
        proto=proto,
        chunk_id=chunk_id_value,
    ).single()
    return dict(record) if record else None


# --------------------------------------------------------------------------- #
# Public: get_node_detail
# --------------------------------------------------------------------------- #
def get_node_detail(driver: Driver, node_id: str) -> Optional[NodeDetail]:
    """Return full detail for *node_id* (mint-prefixed) or None if not found."""
    prefix, raw = _parse_node_id(node_id)

    if prefix == "issue":
        return _detail_issue(driver, node_id, raw)
    if prefix == "stamp":
        return _detail_stamp(driver, node_id, raw)
    if prefix == "scott":
        return _detail_scott(driver, node_id, raw)
    if prefix == "doc":
        return _detail_document(driver, node_id, raw)
    if prefix == "chunk":
        return _detail_chunk(driver, node_id, raw)
    # Variety / Illustration detail is carried inline in their parent graphs.
    raise ValueError(f"Unsupported node id prefix: {prefix!r}")


def _detail_issue(driver: Driver, node_id: str, raw: str) -> Optional[NodeDetail]:
    record = _read(driver, _tx_issue_detail, issue_id_value=raw)
    if not record or record.get("issue") is None:
        return None
    iprops = _issue_props(record["issue"])
    roster = [sanitize_props(dict(sc)) for sc in (record.get("roster") or []) if sc is not None]
    return NodeDetail(
        id=node_id,
        type="Issue",
        title=_issue_label(iprops),
        properties=iprops,
        related={"scott_roster": roster},
    )


def _detail_stamp(driver: Driver, node_id: str, raw: str) -> Optional[NodeDetail]:
    record = _read(driver, _tx_stamp_detail, catalog_no_value=raw, proto=config.PROTOTYPE_TAG)
    if not record or record.get("stamp") is None:
        return None
    sprops = sanitize_props(dict(record["stamp"]))
    _dv, _du = _display_denom(sprops)
    sprops["denomination_value"] = _dv
    sprops["denomination_unit"] = _du
    varieties = [sanitize_props(dict(v)) for v in (record.get("varieties") or []) if v is not None]
    equivalent_scott = [
        sanitize_props(dict(link["scott"])) | {"confidence": link.get("confidence")}
        for link in (record.get("scott_links") or [])
        if link.get("scott") is not None
    ]
    return NodeDetail(
        id=node_id,
        type="Stamp",
        title=_stamp_label(sprops),
        properties=sprops,
        related={
            "varieties": varieties,
            "equivalent_scott": equivalent_scott,
            "evidence_chunks": record.get("evidence_chunks", 0),
        },
    )


def _detail_scott(driver: Driver, node_id: str, raw: str) -> Optional[NodeDetail]:
    record = _read(driver, _tx_scott_detail, scott_number_value=raw)
    if not record or record.get("scott") is None:
        return None
    scprops = sanitize_props(dict(record["scott"]))
    illustrations = [sanitize_props(dict(ill)) for ill in (record.get("illustrations") or []) if ill is not None]
    equivalent_mena = [
        sanitize_props(dict(link["stamp"])) | {"confidence": link.get("confidence")}
        for link in (record.get("equivalent_mena") or [])
        if link.get("stamp") is not None
    ]
    variety_of = [sanitize_props(dict(b)) for b in (record.get("variety_of") or []) if b is not None]
    return NodeDetail(
        id=node_id,
        type="ScottStamp",
        title=_scott_label(scprops),
        properties=scprops,
        related={
            "illustration": illustrations,
            "equivalent_mena": equivalent_mena,
            "variety_of": variety_of,
        },
    )


def _detail_document(driver: Driver, node_id: str, raw: str) -> Optional[NodeDetail]:
    record = _read(driver, _tx_document_detail, doc_id_value=raw, proto=config.PROTOTYPE_TAG)
    if not record or record.get("document") is None:
        return None
    dprops = sanitize_props(dict(record["document"]))
    pages = sorted({p for p in (record.get("pages") or []) if p is not None})
    top_previews = []
    for c in record.get("top_chunks") or []:
        if c is None:
            continue
        cprops = dict(c)
        top_previews.append(
            {
                "chunk_id": cprops.get("chunk_id"),
                "page": cprops.get("page"),
                "link_score": cprops.get("link_score"),
                "preview": (cprops.get("text") or "")[:_PREVIEW_LEN],
            }
        )
    return NodeDetail(
        id=node_id,
        type="Document",
        title=_document_label(dprops),
        properties=dprops,
        related={
            "chunk_count": record.get("chunk_count", 0),
            "pages": pages,
            "series": dprops.get("series"),
            "top_chunks": top_previews,
        },
    )


def _detail_chunk(driver: Driver, node_id: str, raw: str) -> Optional[NodeDetail]:
    record = _read(driver, _tx_chunk_detail, chunk_id_value=raw, proto=config.PROTOTYPE_TAG)
    if not record or record.get("chunk") is None:
        return None
    cprops = sanitize_props(dict(record["chunk"]))  # full text retained (drill-down view)
    stamp_links = [
        {
            "catalog_no": link.get("catalog_no"),
            "confidence": link.get("confidence"),
            "signals": link.get("signals"),
        }
        for link in (record.get("stamp_links") or [])
        if link.get("catalog_no")
    ]
    return NodeDetail(
        id=node_id,
        type="Chunk",
        title=_chunk_label(cprops),
        properties=cprops,
        related={
            "page": cprops.get("page"),
            "link_score": cprops.get("link_score"),
            "mention": {
                "score": record.get("mention_score"),
                "signals": record.get("mention_signals"),
                "confidence": record.get("mention_confidence"),
            },
            "mentions_stamp": stamp_links,
        },
    )


# --------------------------------------------------------------------------- #
# Overview work functions
# --------------------------------------------------------------------------- #
def _tx_overview_bundle(tx: ManagedTransaction, issue_id_value: str, proto: str) -> dict[str, Any]:
    """Run the four overview aggregates in ONE round-trip (was 4 separate sessions).

    Each independent aggregate -- totals (Cypher-style facts), series breakdown
    (#14), MENTIONS score histogram (#9), and the Mena/Scott stamp table (#6) --
    is computed in its own ``CALL () { }`` scoped subquery (Neo4j 5.23+/2025.x
    variable-scope form) and collected; the four results come back as a single
    record. This replaces four serial ``_read`` calls (each acquiring its own
    session) with one round-trip.
    """
    record = tx.run(
        """
        CALL () {
            MATCH (i:Issue {issue_id: $issue_id})
            OPTIONAL MATCH (i)-[:HAS_STAMP]->(s:Stamp)
            OPTIONAL MATCH (i)-[:HAS_SCOTT_STAMP]->(sc:ScottStamp)
            WITH i,
                 count(DISTINCT s) AS mena_stamps,
                 count(DISTINCT sc) AS scott_stamps
            OPTIONAL MATCH (d:Document {prototype: $proto})
            WITH i, mena_stamps, scott_stamps, count(DISTINCT d) AS documents
            OPTIONAL MATCH (lc:Chunk {prototype: $proto})-[m:MENTIONS]->(i)
            WITH i, mena_stamps, scott_stamps, documents,
                 count(DISTINCT lc) AS linked_chunks,
                 count(DISTINCT CASE WHEN m.score >= 6 AND NOT "COMPETING" IN coalesce(m.signals, [])
                                     THEN lc END) AS clean_chunks
            OPTIONAL MATCH (:Chunk {prototype: $proto})-[ms:MENTIONS_STAMP]->(:Stamp)
            RETURN i AS issue, mena_stamps, scott_stamps, documents,
                   linked_chunks, clean_chunks, count(ms) AS mentions_stamp
        }
        CALL () {
            MATCH (d:Document {prototype: $proto})
            WITH d, CASE
                WHEN d.doc_id STARTS WITH 'OXCART' THEN 'OXCART studies'
                WHEN d.doc_id STARTS WITH 'CRF' THEN 'CRF (Costa Rica Filatelica)'
                WHEN d.doc_id STARTS WITH 'Filatelia Costarricense' THEN 'Filatelia Costarricense'
                WHEN d.doc_id STARTS WITH 'AFCR' THEN 'AFCR Boletin'
                WHEN d.doc_id STARTS WITH 'Repertorio' THEN 'Repertorio Filatelico'
                WHEN d.doc_id STARTS WITH 'Timbre' THEN 'Timbre'
                WHEN d.doc_id STARTS WITH 'Juventud' THEN 'Juventud Filatelica'
                WHEN d.doc_id CONTAINS 'Philatelist' THEN 'The Costa Rica Philatelist'
                ELSE 'Other monographs' END AS series
            WITH series, count(DISTINCT d) AS n
            ORDER BY n DESC
            RETURN collect({series: series, n: n}) AS series_rows
        }
        CALL () {
            MATCH (:Chunk {prototype: $proto})-[m:MENTIONS]->(:Issue {issue_id: $issue_id})
            WITH CASE
                     WHEN m.score >= 12 THEN '12+  very strong'
                     WHEN m.score >= 8  THEN '8-11 strong'
                     WHEN m.score >= 6  THEN '6-7  solid'
                     ELSE '4-5  threshold'
                   END AS band,
                   count(*) AS n
            ORDER BY band DESC
            RETURN collect({band: band, n: n}) AS score_rows
        }
        CALL () {
            MATCH (i:Issue {issue_id: $issue_id})-[:HAS_STAMP]->(s:Stamp)
            OPTIONAL MATCH (s)-[eq:EQUIVALENT_TO]->(sc:ScottStamp)
            WITH s, collect({scott_number: sc.scott_number, confidence: eq.confidence}) AS scott
            ORDER BY s.catalog_no
            RETURN collect({
                catalog_no: s.catalog_no,
                denomination_value: s.denomination_value,
                denomination_unit: s.denomination_unit,
                color: s.color,
                perforation: s.perforation,
                status: s.status,
                quantity_reported: s.quantity_reported,
                scott: scott
            }) AS stamp_rows
        }
        CALL () {
            MATCH (:Issue {issue_id: $issue_id})-[:HAS_SCOTT_STAMP]->(sc:ScottStamp)
            WHERE sc.description IS NULL OR NOT toLower(sc.description) CONTAINS 'pair'
            RETURN count(DISTINCT sc) AS scott_catalogued
        }
        RETURN issue, mena_stamps, scott_stamps, documents, linked_chunks,
               clean_chunks, mentions_stamp, series_rows, score_rows, stamp_rows,
               scott_catalogued
        """,
        issue_id=issue_id_value,
        proto=proto,
    ).single()
    return dict(record) if record else {}


# --------------------------------------------------------------------------- #
# Public: overview
# --------------------------------------------------------------------------- #
def overview(driver: Driver) -> dict[str, Any]:
    """Return the landing-page overview payload for OverviewResponse.

    All four aggregates (totals, series, score distribution, stamp table) are
    fetched in ONE Neo4j round-trip via :func:`_tx_overview_bundle` (previously
    four serial ``_read`` calls in separate sessions).
    """
    iid = config.ISSUE_ID
    proto = config.PROTOTYPE_TAG

    agg = _read(driver, _tx_overview_bundle, issue_id_value=iid, proto=proto)
    issue_node = agg.get("issue")
    issue_props = sanitize_props(dict(issue_node)) if issue_node is not None else {}
    # Display the *catalogued* Scott count (5): the graph also holds Scott 1b, an
    # imperforate-pair variety, which is not a distinct catalogued stamp.
    catalogued = int(agg.get("scott_catalogued") or 0) or int(agg.get("scott_stamps") or 0)

    issue_facts = {
        "issue_id": iid,
        "title": issue_props.get("title") or DEFAULT_ISSUE_TITLE,
        "country": issue_props.get("country"),
        "issue_dates": issue_props.get("issue_dates"),
        "perforation": issue_props.get("perforation"),
        "scott_note": (
            f"Scott catalogues {catalogued} stamps for the First Issue "
            "(Scott 1, 1a, 2, 3, 4). Scott 1b — an imperforate pair — is a variety: "
            "it appears in the graph but is not counted here."
        ),
    }

    totals = {
        "documents": int(agg.get("documents") or 0),
        "linked_chunks": int(agg.get("linked_chunks") or 0),
        "clean_chunks": int(agg.get("clean_chunks") or 0),
        "mentions_stamp": int(agg.get("mentions_stamp") or 0),
        "scott_stamps": catalogued,
        "mena_stamps": int(agg.get("mena_stamps") or 0),
    }

    # series / score_distribution / stamps now arrive in the same single record.
    series = [dict(r) for r in (agg.get("series_rows") or [])]
    score_distribution = [dict(r) for r in (agg.get("score_rows") or [])]

    stamps: list[dict[str, Any]] = []
    for r in agg.get("stamp_rows") or []:
        row = dict(r)
        _dv, _du = _display_denom(row)
        row["denomination_value"] = _dv
        row["denomination_unit"] = _du
        row["scott"] = [link for link in (row.get("scott") or []) if link.get("scott_number") is not None]
        stamps.append(row)

    return {
        "issue": issue_facts,
        "totals": totals,
        "series": series,
        "score_distribution": score_distribution,
        "stamps": stamps,
    }


# --------------------------------------------------------------------------- #
# Health helpers
# --------------------------------------------------------------------------- #
def _tx_ping(tx: ManagedTransaction) -> int:
    record = tx.run("RETURN 1 AS ok").single()
    return int(record["ok"]) if record else 0


def neo4j_ok(driver: Driver) -> bool:
    """Return True if a trivial read query succeeds."""
    try:
        return _read(driver, _tx_ping) == 1
    except Exception:
        return False


def _tx_graph_populated(tx: ManagedTransaction, issue_id_value: str) -> bool:
    record = tx.run(
        """
        MATCH (:Issue {issue_id: $issue_id})-[:HAS_STAMP]->(:Stamp)
        RETURN count(*) > 0 AS populated
        """,
        issue_id=issue_id_value,
    ).single()
    return bool(record["populated"]) if record else False


def graph_populated(driver: Driver) -> bool:
    """Return True if the Issue has at least one HAS_STAMP edge."""
    try:
        return _read(driver, _tx_graph_populated, issue_id_value=config.ISSUE_ID)
    except Exception:
        return False
