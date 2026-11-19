"""Query router: read-only retrieval endpoints (NO LLM).

Endpoints (mounted under ``/api`` by :mod:`app.main`):

* ``GET  /api/examples`` -> ``list[ExampleQuery]`` -- the demo questions from
  ``examples_runner.DEMO``.
* ``POST /api/query``    -> ``QueryResponse`` -- wraps
  ``retrieve.context_bundle`` (sanitized) plus a derived visualisation
  subgraph. There is no answer-generation step.

All heavy lifting lives in :mod:`app.query_service`; this router stays thin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool

from neo4j import Driver

from app import query_service
from app.deps import get_driver
from app.schemas import ExampleQuery, QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.get("/examples", response_model=list[ExampleQuery])
async def get_examples() -> list[ExampleQuery]:
    """Return the canned demo questions (``examples_runner.DEMO``)."""
    return query_service.list_examples()


@router.post("/query", response_model=QueryResponse)
async def post_query(payload: QueryRequest, driver: Driver = Depends(get_driver)) -> QueryResponse:
    """Run the read-only context bundle for ``payload.question`` (no LLM).

    Returns the sanitized ``retrieve.context_bundle`` fields plus a small
    ``subgraph`` derived from the retrieved context for visualisation.
    """
    bundle = await query_service.run_query(
        question=payload.question,
        stamp=payload.stamp,
        min_link=payload.min_link,
        max_lexical=payload.max_lexical,
        k_weaviate=payload.k_weaviate,
        exclude_competing=payload.exclude_competing,
        driver=driver,
    )
    subgraph = query_service.build_query_subgraph(bundle, stamp=payload.stamp)
    figures = query_service.collect_query_figures(bundle)
    return QueryResponse(
        domain=bundle["domain"],
        related=bundle["related"],
        sources=bundle["sources"],
        lexical=bundle["lexical"],
        weaviate=bundle["weaviate"],
        counts=bundle["counts"],
        subgraph=subgraph,
        figures=figures,
    )


@router.post("/query/export")
async def post_query_export(payload: QueryRequest, driver: Driver = Depends(get_driver)) -> Response:
    """Full-text, LLM-ready ``.txt`` export for ``payload.question`` (file download).

    This is the ONLY endpoint that returns full chunk text. It is built
    server-side (:func:`query_service.build_export_text`) and returned as
    ``text/plain`` with an attachment disposition, so a large body never has to be
    JSON-parsed by the browser -- which is what causes "Unterminated string in
    JSON" on the display path (``POST /api/query`` clips card text to keep its JSON
    small). No LLM is called; this only packages the retrieved evidence.
    """
    text = await run_in_threadpool(
        query_service.build_export_text,
        payload.question,
        stamp=payload.stamp,
        min_link=payload.min_link,
        max_lexical=payload.max_lexical,
        k_weaviate=payload.k_weaviate,
        exclude_competing=payload.exclude_competing,
        driver=driver,
    )
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="first-issue-export.txt"'},
    )
