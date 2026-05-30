"""Pydantic v2 response/request schemas for the First Issue KG Explorer API.

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


class QueryResponse(BaseModel):
    """Response for ``POST /api/query``.

    The first six fields are the raw ``retrieve.context_bundle`` payload
    (after embedding/vector sanitization); ``subgraph`` is a derived
    visualisation graph for the retrieved context.
    """

    model_config = ConfigDict(from_attributes=True)

    domain: dict[str, Any] = Field(default_factory=dict)
    related: dict[str, Any] = Field(default_factory=dict)
    sources: list[Any] = Field(default_factory=list)
    lexical: list[Any] = Field(default_factory=list)
    weaviate: list[Any] = Field(default_factory=list)
    counts: dict[str, Any] = Field(default_factory=dict)
    subgraph: GraphResponse = Field(default_factory=GraphResponse)


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
