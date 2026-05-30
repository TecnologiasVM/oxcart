"""MENA router -- read-only Mena Catalogue (Surface Mail) navigation + per-issue views.

Endpoints (mounted under ``/api`` by :mod:`app.main`, so the full paths are
``/api/mena/...``):

* ``GET /mena/surface-mail``                 Year-grouped Surface-Mail navigator (fast).
* ``GET /mena/issue/{issue_id}``             Fast per-issue facts + Scott match.
* ``GET /mena/issue/{issue_id}/graph``       Lazy small mini-graph for the issue.
* ``GET /mena/issue/{issue_id}/evidence``    Lazy Weaviate BM25 passages (?k=).

All work is delegated to :mod:`app.mena_service` (read-only, parameterized
Cypher; Weaviate BM25 only). The shared Neo4j driver is injected from
``app.state`` via ``deps.get_driver``; the blocking sync work is offloaded with
``run_in_threadpool`` (same pattern as the graph router).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app import mena_service
from app.deps import get_driver
from app.schemas import (
    GraphResponse,
    MenaEvidenceResponse,
    MenaIssueDetail,
    SurfaceMailResponse,
)

router = APIRouter(prefix="/mena", tags=["mena"])


@router.get("/surface-mail", response_model=SurfaceMailResponse)
async def get_surface_mail(driver: Driver = Depends(get_driver)) -> SurfaceMailResponse:
    """Return the full Surface-Mail navigator (issues grouped by year)."""
    years = await run_in_threadpool(mena_service.list_surface_mail, driver)
    total = sum(y["count"] for y in years)
    return SurfaceMailResponse(section=mena_service._SECTION, total_issues=total, years=years)


@router.get("/issue/{issue_id}", response_model=MenaIssueDetail)
async def get_mena_issue(issue_id: str, driver: Driver = Depends(get_driver)) -> MenaIssueDetail:
    """Return fast per-issue facts (catalog data + Scott match). 404 if unknown."""
    detail = await run_in_threadpool(mena_service.issue_detail, driver, issue_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Surface-Mail issue not found: {issue_id}")
    return MenaIssueDetail(**detail)


@router.get("/issue/{issue_id}/graph", response_model=GraphResponse)
async def get_mena_issue_graph(issue_id: str, driver: Driver = Depends(get_driver)) -> GraphResponse:
    """Return the lazy mini-graph for an issue. 404 if the issue is unknown/empty."""
    graph = await run_in_threadpool(mena_service.issue_graph, driver, issue_id)
    if not graph.nodes:
        raise HTTPException(status_code=404, detail=f"Surface-Mail issue not found: {issue_id}")
    return graph


@router.get("/issue/{issue_id}/evidence", response_model=MenaEvidenceResponse)
async def get_mena_issue_evidence(
    issue_id: str,
    k: Optional[int] = Query(None, ge=0, le=25, description="Max BM25 passages (default from MENA_EVIDENCE_K)."),
    driver: Driver = Depends(get_driver),
) -> MenaEvidenceResponse:
    """Return lazy Weaviate BM25 passages for an issue. 404 if the issue is unknown.

    Existence is checked with a cheap parameterized query (not the full detail
    bundle), then BM25 runs (degrades to an empty list if Weaviate is down).
    """
    exists = await run_in_threadpool(mena_service.issue_exists, driver, issue_id)
    if not exists:
        raise HTTPException(status_code=404, detail=f"Surface-Mail issue not found: {issue_id}")
    result = await run_in_threadpool(mena_service.issue_evidence, driver, issue_id, k)
    return MenaEvidenceResponse(issue_id=issue_id, query=result["query"], passages=result["passages"])
