"""META router -- health and overview surfaces.

Endpoints (mounted under ``/api`` by :mod:`app.main`):

* ``GET /api/health``      Dependency liveness (Neo4j, Weaviate) + graph_populated.
* ``GET /api/overview``    Landing-page summary of the First Issue knowledge graph.

The Weaviate readiness probe opens a client (read-only) and immediately closes
it; the prototype retrieve layer owns the per-call client otherwise. No LLM
calls anywhere.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from neo4j import Driver

from app import graph_service, settings
from app.deps import get_driver, get_weaviate
from app.schemas import HealthResponse, OverviewResponse

from oxcart import config

router = APIRouter(tags=["meta"])


def _weaviate_ready() -> bool:
    """Return True if Weaviate is reachable. Opens and closes its own client."""
    client = None
    try:
        client = get_weaviate()
        return bool(client.is_ready())
    except Exception:
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


@router.get("/health", response_model=HealthResponse)
async def health(driver: Driver = Depends(get_driver)) -> HealthResponse:
    """Liveness/readiness for Neo4j and Weaviate, plus graph-populated flag.

    The blocking probes (sync Neo4j driver, Weaviate client open/close) run in a
    worker thread via ``run_in_threadpool`` so they never block the event loop.
    """
    neo4j_ok = await run_in_threadpool(graph_service.neo4j_ok, driver)
    weaviate_ok = await run_in_threadpool(_weaviate_ready)
    graph_pop = (
        await run_in_threadpool(graph_service.graph_populated, driver) if neo4j_ok else False
    )
    return HealthResponse(
        neo4j=neo4j_ok,
        weaviate=weaviate_ok,
        graph_populated=graph_pop,
        detail={"issue_id": config.ISSUE_ID, "service": settings.SERVICE_NAME},
    )


@router.get("/overview", response_model=OverviewResponse)
async def overview(driver: Driver = Depends(get_driver)) -> OverviewResponse:
    """Return the landing-page overview for the whole First Issue graph.

    Offloaded to a worker thread (sync Neo4j driver) via ``run_in_threadpool``.
    """
    payload = await run_in_threadpool(graph_service.overview, driver)
    return OverviewResponse(**payload)
