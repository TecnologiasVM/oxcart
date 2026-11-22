"""Dependencies, lifespan, and shared resources for the backend.

Responsibilities
----------------
* ``lifespan`` -- open exactly ONE Neo4j driver for the process and stash it on
  ``app.state.neo4j``; close it on shutdown. The prototype's
  ``config.neo4j_driver()`` returns a standard (sync) ``neo4j.Driver``; the
  caller owns its lifecycle, so we close it ourselves.
* ``get_driver`` -- FastAPI dependency that hands routers the shared driver.
* ``get_weaviate`` -- helper returning a fresh ``config.weaviate_client()``.
  Weaviate clients are NOT pooled here; per the prototype contract the caller
  opens and closes them. Always use it as a context manager or in a
  ``try/finally`` that calls ``.close()``.
* ``sanitize_props`` -- defensively strip any property whose key looks like an
  embedding/vector field from any dict that leaves the backend.

Contracts enforced here:
* Neo4j access is read-only at the application level (routers must only issue
  read queries -- this module does not write).
* Weaviate is read-only.
* Embedding/vector fields are never exposed (``sanitize_props``).
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request

from app import settings

from oxcart import config

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import Driver


# ---------------------------------------------------------------------------
# Embedding / vector sanitization
# ---------------------------------------------------------------------------
# Any property key matching this pattern is dropped before leaving the backend.
# Mena Issue/Stamp nodes MAY carry an embedding property written by another
# indexer; Chunk nodes do not, but we strip defensively everywhere.
_EMBED_KEY_RE = re.compile(r"(?i)(embed|vector)")


def _to_jsonable(value: Any) -> Any:
    """Coerce Neo4j-driver scalar types into JSON/Pydantic-serializable values.

    Neo4j temporal types (``neo4j.time.Date``/``DateTime``/``Time``/
    ``Duration``) and spatial ``Point`` are not natively serializable by
    Pydantic v2's response encoder, so any node property carrying one would
    raise ``PydanticSerializationError`` when returned. We stringify those
    (and recurse into list/dict containers). Plain JSON scalars pass through
    untouched. This keeps the API response contract pure-JSON without the
    callers having to know the driver's value types.
    """
    # Fast path for the common JSON scalars (avoids the isoformat/str dance).
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    # Neo4j temporal/spatial types expose isoformat(); fall back to str().
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)


def sanitize_props(d: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``d`` with embedding/vector-like keys removed.

    A key is dropped when its name contains ``embed`` or ``vector`` in any
    casing (e.g. ``embedding``, ``text_vector``, ``vectorEmbedding``). This is
    applied to every node/detail/response payload so vector data is never
    exposed over the API.

    Surviving values are additionally coerced to JSON-serializable forms via
    :func:`_to_jsonable` so Neo4j temporal/spatial property types (e.g. an
    ``Issue.some_date`` of type ``neo4j.time.Date``) do not break Pydantic
    response serialization.

    Parameters
    ----------
    d:
        A mapping of property name -> value. Non-dict inputs are returned
        unchanged (callers may pass through ``None`` safely).

    Returns
    -------
    dict
        A new dict with offending keys removed and values JSON-coerced. The
        input is not mutated.
    """
    if not isinstance(d, dict):
        return d
    return {k: _to_jsonable(v) for k, v in d.items() if not _EMBED_KEY_RE.search(str(k))}


# ---------------------------------------------------------------------------
# Lifespan: single Neo4j driver on app.state
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one Neo4j driver at startup, close it at shutdown.

    ``config.neo4j_driver()`` returns a sync ``neo4j.Driver`` (a connection
    pool that is thread-safe). We create it once per process and place it on
    ``app.state.neo4j`` for the ``get_driver`` dependency to hand out. The
    Weaviate client is intentionally NOT opened here -- it is created
    per-request by ``get_weaviate`` and closed by the caller.
    """
    driver: "Driver" = config.neo4j_driver()
    app.state.neo4j = driver
    # The question path's three steps (embedding, catalogue lookup, literature search).
    # Tests replace them on ``app.state.ask`` after startup.
    from app import ask_service
    from app.graph_link import GraphLink

    # One link to the graph for the life of the process. It starts connecting now, in the
    # background, and keeps trying inside its budget: startup and the health route do not wait.
    app.state.graph = GraphLink(lambda: app.state.neo4j, config.NEO4J_DATABASE,
                                startup_budget=settings.GRAPH_STARTUP_BUDGET_SECONDS,
                                question_budget=settings.GRAPH_QUESTION_BUDGET_SECONDS,
                                every=settings.GRAPH_RETRY_EVERY_SECONDS)
    if settings.GRAPH_WARM_ON_START:
        app.state.graph.warm_in_background()
    app.state.ask = ask_service.default_deps(app.state.graph)
    # The list of figures that may be named, read as the process starts when figures are on.
    from app import figures

    if figures.on():
        figures.shipped()
    # The literature client and the embedding's connection, opened the same way: in the
    # background, so that the first question does not wait for them.
    if settings.ASK_WARM_ON_START:
        app.state.ask.warm()
        # The written answer's client too: loading its package took the first answer's time on a small host.
        app.state.answer_model.warm_in_background()
    try:
        yield
    finally:
        app.state.ask.close()
        app.state.answer_model.close()
        # Sync driver: close() is synchronous (no await).
        app.state.neo4j.close()
        app.state.neo4j = None


# ---------------------------------------------------------------------------
# Dependencies / helpers
# ---------------------------------------------------------------------------
def get_driver(request: Request) -> "Driver":
    """FastAPI dependency returning the process-wide Neo4j driver.

    The driver is the shared singleton created in :func:`lifespan`. Routers
    must only issue read-only Cypher against the ``config.NEO4J_DATABASE``
    database.
    """
    return request.app.state.neo4j


def get_weaviate():
    """Return a fresh Weaviate client; the CALLER must close it.

    Per the prototype contract, ``config.weaviate_client()`` opens a new client
    and the caller owns its lifecycle. Use it as::

        client = get_weaviate()
        try:
            ...  # read-only queries against config.OXCART_COLLECTION
        finally:
            client.close()

    Weaviate access must remain read-only.
    """
    return config.weaviate_client()
