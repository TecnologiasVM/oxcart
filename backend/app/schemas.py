"""Pydantic v2 response/request schemas for the Oxcart API.

These models are deliberately permissive on the nested payloads (``data``,
``domain``, ``related``, etc. are plain ``dict``/``list``) because the shapes
they carry are produced verbatim by the prototype's ``retrieve.context_bundle``
and by the Neo4j read queries. Routers are responsible for stripping
embedding/vector fields via :func:`app.deps.sanitize_props` before populating
these models.

No model carries an embedding or vector field, and none should ever be added.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Graph primitives (for visualisation: nodes + edges + stats)
# ---------------------------------------------------------------------------
class GraphNode(BaseModel):
    """A single node in a graph/subgraph payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Stable unique node id.")
    type: str = Field(..., description="Node label/category, e.g. 'Issue', 'Stamp', 'Chunk'.")
    label: str = Field(..., description="Human-readable display label.")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized node properties (no embedding/vector keys).",
    )


class GraphEdge(BaseModel):
    """A directed edge between two :class:`GraphNode` ids."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Stable unique edge id.")
    source: str = Field(..., description="Source node id.")
    target: str = Field(..., description="Target node id.")
    type: str = Field(..., description="Relationship type, e.g. 'HAS_STAMP', 'MENTIONS'.")
    data: dict[str, Any] = Field(default_factory=dict, description="Sanitized edge properties.")


class GraphResponse(BaseModel):
    """A graph/subgraph: nodes, edges, and summary statistics."""

    model_config = ConfigDict(from_attributes=True)

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    stats: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary counts/metrics (e.g. node/edge totals by type).",
    )


# ---------------------------------------------------------------------------
# Node detail
# ---------------------------------------------------------------------------
class NodeDetail(BaseModel):
    """Detailed view of a single node, with sanitized properties."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str = Field(..., description="Node label/category.")
    title: str = Field(..., description="Display title for the node.")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized node properties (no embedding/vector keys).",
    )
    related: dict[str, Any] = Field(
        default_factory=dict,
        description="Related entities grouped by relationship/category.",
    )


# ---------------------------------------------------------------------------
# Query (wraps retrieve.context_bundle -- NO LLM, retrieval only)
# ---------------------------------------------------------------------------
class ExampleQuery(BaseModel):
    """A demo question (from ``examples_runner.DEMO``)."""

    model_config = ConfigDict(from_attributes=True)

    question: str
    stamp: str | None = Field(
        default=None,
        description="Optional Mena scope code (1=half real, 2=2 reales, 3=4 reales, 4=1 peso).",
    )


class QueryRequest(BaseModel):
    """Request body for ``POST /api/query``.

    Mirrors the ``retrieve.context_bundle`` parameters. There is no
    answer-generation step -- this is retrieval/context only.
    """

    model_config = ConfigDict(from_attributes=True)

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language question to retrieve context for.",
    )
    stamp: str | None = Field(
        default=None,
        description="Optional Mena scope code (1=half real, 2=2 reales, 3=4 reales, 4=1 peso).",
    )
    min_link: float = Field(
        default=6.0,
        description="Minimum MENTIONS link score for the CLEAN tier.",
    )
    max_lexical: int = Field(default=0, ge=0, description="Max lexical chunks to include (0 = none).")
    k_weaviate: int = Field(default=5, ge=0, le=25, description="Number of Weaviate hits to retrieve.")
    exclude_competing: bool = Field(
        default=True,
        description="Exclude chunks whose MENTIONS signals include 'COMPETING'.",
    )


class QueryFigure(BaseModel):
    """A page figure related to the query (by the source chunk's doc_id + page).

    Figures are cropped page images produced by the Dolphin parser; this links
    them to a query via the chunks that ground it. ``url`` is browser-facing
    (served by the backend's ``/api/figures`` static mount). No embedding/vector
    field appears here.
    """

    model_config = ConfigDict(from_attributes=True)

    filename: str
    doc_id: str
    page: int
    url: str = Field(..., description="Browser-facing image URL (/api/figures/<file>).")
    chunk_id: str | None = Field(default=None, description="Source chunk that surfaced this figure.")
    link_score: float | None = Field(default=None, description="Source chunk's MENTIONS link score.")
    score: float | None = Field(default=None, description="Source chunk's fulltext relevance score.")


class QueryResponse(BaseModel):
    """Response for ``POST /api/query``.

    The first six fields are the raw ``retrieve.context_bundle`` payload
    (after embedding/vector sanitization); ``subgraph`` is a derived
    visualisation graph for the retrieved context; ``figures`` are the related
    page images for the cited pages (top-N, de-duplicated).
    """

    model_config = ConfigDict(from_attributes=True)

    domain: dict[str, Any] = Field(default_factory=dict)
    related: dict[str, Any] = Field(default_factory=dict)
    sources: list[Any] = Field(default_factory=list)
    lexical: list[Any] = Field(default_factory=list)
    weaviate: list[Any] = Field(default_factory=list)
    counts: dict[str, Any] = Field(default_factory=dict)
    subgraph: GraphResponse = Field(default_factory=GraphResponse)
    figures: list[QueryFigure] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Overview / meta
# ---------------------------------------------------------------------------
class OverviewResponse(BaseModel):
    """High-level dashboard payload for the First Issue."""

    model_config = ConfigDict(from_attributes=True)

    issue: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)
    series: list[Any] = Field(default_factory=list)
    score_distribution: list[Any] = Field(default_factory=list)
    stamps: list[Any] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Liveness/readiness for backing stores and graph population."""

    model_config = ConfigDict(from_attributes=True)

    neo4j: bool = Field(..., description="True if the Neo4j driver is reachable.")
    weaviate: bool = Field(..., description="True if a Weaviate client connects.")
    graph_populated: bool = Field(
        ...,
        description="True if the prototype's First Issue graph data is present.",
    )
    detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic details (counts, errors, versions).",
    )


# ---------------------------------------------------------------------------
# Mena Catalogue -> Surface Mail (read-only navigation over the shared Mena graph)
# ---------------------------------------------------------------------------
# These power the /api/mena/* endpoints. The Mena domain graph (Issue/Stamp/...)
# is shared with the prototype; navigation is scoped to Issue.section == the
# configured section ("Surface Mail"). No embedding/vector field appears here.
class SurfaceMailIssue(BaseModel):
    """One Surface-Mail issue in the year-grouped navigator (lightweight)."""

    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    title: str | None = None
    n_stamps: int = 0
    year: str = Field(..., description="Four-digit year parsed from issue_id, or 'Undated'.")


class SurfaceMailYear(BaseModel):
    """A year bucket: its issues, ordered for the navigator."""

    model_config = ConfigDict(from_attributes=True)

    year: str
    count: int = 0
    issues: list[SurfaceMailIssue] = Field(default_factory=list)


class SurfaceMailResponse(BaseModel):
    """The full Surface-Mail navigator index (years -> issues)."""

    model_config = ConfigDict(from_attributes=True)

    section: str = "Surface Mail"
    total_issues: int = 0
    years: list[SurfaceMailYear] = Field(default_factory=list)


class MenaScottMatch(BaseModel):
    """One Mena->Scott equivalence row (from the match catalogue files).

    NOTE: ``confidence`` is a categorical STRING in the source ("high"/"medium"),
    distinct from the numeric graph-side EQUIVALENT_TO confidence.
    """

    model_config = ConfigDict(from_attributes=True)

    mena: str | None = None
    scott: str | None = None
    confidence: str | None = None
    scott_detail: dict[str, Any] | None = None


class MenaIssueDetail(BaseModel):
    """Fast per-issue facts: catalog data + Scott match (NO graph/Weaviate)."""

    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    year: str
    title: str | None = None
    issue: dict[str, Any] = Field(default_factory=dict, description="Clean issue facts; issue_dates parsed.")
    stamps: list[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    printer: str | None = None
    printers: list[str] = Field(default_factory=list)
    legal_acts: list[dict[str, Any]] = Field(default_factory=list)
    scott_match: list[MenaScottMatch] = Field(default_factory=list)
    graph_scott_roster: list[dict[str, Any]] = Field(default_factory=list)


class MenaEvidencePassage(BaseModel):
    """A Weaviate BM25 passage relevant to an issue (lazy 'Query evidence')."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str | None = None
    doc_id: str | None = None
    page: int | str | None = None
    snippet: str = ""
    score: float | None = None


class MenaEvidenceResponse(BaseModel):
    """Lazy per-issue evidence: the BM25 query used + its passages."""

    model_config = ConfigDict(from_attributes=True)

    issue_id: str
    query: str = ""
    passages: list[MenaEvidencePassage] = Field(default_factory=list)
