"""GRAPH router -- read-only graph views and single-node drill-down.

Endpoints (mounted under ``/api`` by :mod:`app.main`):

* ``GET /api/graph``                Full domain subgraph + top lexical documents.
* ``GET /api/graph/stamp/{cno}``    Stamp-centric subgraph for one Mena catalog_no.
* ``GET /api/node?node_id=...``     Full detail for one node (404 if missing).

All work is delegated to :mod:`app.graph_service` (read-only, parameterized
Cypher). The shared Neo4j driver is injected from ``app.state`` via
``deps.get_driver``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app import graph_service
from app.deps import get_driver
from app.schemas import GraphResponse, NodeDetail

router = APIRouter(tags=["graph"])


@router.get("/graph", response_model=GraphResponse)
async def get_graph(
    clean: bool = Query(True, description="CLEAN tier only (score>=min_score AND no COMPETING signal)."),
    max_docs: int = Query(10, ge=1, le=100, description="Top N documents by qualifying MENTIONS count."),
    chunks_per_doc: int = Query(5, ge=1, le=50, description="Max chunks per document."),
    min_score: float = Query(6.0, ge=0.0, description="Minimum MENTIONS score."),
    driver: Driver = Depends(get_driver),
) -> GraphResponse:
    """Return the full domain subgraph plus the top lexical documents/chunks.

    ``graph_service.build_graph`` uses the synchronous Neo4j driver, so it is
    offloaded to a worker thread with ``run_in_threadpool`` (the same pattern as
    ``query_service.run_query``) to keep the event loop responsive under load.
    """
    return await run_in_threadpool(
        graph_service.build_graph,
        driver,
        clean=clean,
        max_docs=max_docs,
        chunks_per_doc=chunks_per_doc,
        min_score=min_score,
    )


@router.get("/graph/stamp/{cno}", response_model=GraphResponse)
async def get_stamp_graph(
    cno: str,
    max_docs: int = Query(12, ge=1, le=100, description="Max distinct evidence documents."),
    chunks_per_doc: int = Query(5, ge=1, le=50, description="Max chunks per document."),
    min_score: float = Query(6.0, ge=0.0, description="Minimum link score for evidence chunks."),
    driver: Driver = Depends(get_driver),
) -> GraphResponse:
    """Return a stamp-centric subgraph for the Mena *cno* catalog number.

    Offloaded to a worker thread (sync Neo4j driver) via ``run_in_threadpool``.
    """
    return await run_in_threadpool(
        graph_service.build_stamp_graph,
        driver,
        catalog_no=cno,
        max_docs=max_docs,
        chunks_per_doc=chunks_per_doc,
        min_score=min_score,
    )


@router.get("/node", response_model=NodeDetail)
async def get_node(
    node_id: str = Query(..., min_length=1, description="Mint-style node id, e.g. 'stamp:1A'."),
    driver: Driver = Depends(get_driver),
) -> NodeDetail:
    """Return full detail for *node_id*. 404 if the id is unknown / not found.

    Offloaded to a worker thread (sync Neo4j driver) via ``run_in_threadpool``.
    """
    try:
        detail = await run_in_threadpool(graph_service.get_node_detail, driver, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    return detail
