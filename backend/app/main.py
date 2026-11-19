"""FastAPI application for the First Issue KG Explorer backend.

This is the app factory: it wires the Neo4j-driver lifespan, CORS for the
Next.js dev frontend, and the API routers (graph, meta, query) under the
``/api`` prefix.

Owner contracts upheld across the whole service:

* No direct LLM/OpenAI/Anthropic API calls in new code. (Weaviate's own
  vectorizer is the only permitted exception; BM25 is the default and needs no
  key.) There is NO answer-generation phase in this MVP.
* Weaviate is read-only.
* Neo4j queries are read-only.
* Embedding/vector fields are never exposed -- see ``app.deps.sanitize_props``.

Run (from ``backend``, with the project virtual environment
active)::

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8090

or start backend and frontend together::

    python ../scripts/servers.py start
"""

from __future__ import annotations

import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import public_guard, settings
from app.deps import lifespan
from app.routers import ask

from oxcart import config

log = logging.getLogger("oxcart.ask")


def create_app(public: bool | None = None) -> FastAPI:
    """Build the API.

    ``public`` (default: the OXCART_PUBLIC setting) is the hosted mode: only the question
    path is mounted (health, examples, session, ask), the interactive docs and the OpenAPI
    document are off, CORS allows the listed origins for GET and POST without credentials,
    and a question needs a session token from the human check. Without it the explorer's
    routes are mounted too, as before, for local research use.
    """
    public = settings.PUBLIC if public is None else public
    if not log.handlers:          # one line per question (mode, timings, error classes); see routers/ask.py
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False
    extra = {"docs_url": None, "redoc_url": None, "openapi_url": None} if public else {}
    app = FastAPI(title=settings.SERVICE_NAME, lifespan=lifespan, **extra)
    app.state.public = public
    app.state.limiter = public_guard.Limiter(settings.ASK_LIMIT_PER_MINUTE, settings.ASK_LIMIT_PER_DAY,
                                             settings.ASK_LIMIT_GLOBAL_PER_DAY)
    app.state.session_limiter = public_guard.Limiter(10, 200, 20 * settings.ASK_LIMIT_GLOBAL_PER_DAY)

    if public:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type", public_guard.SESSION_HEADER, public_guard.EVAL_HEADER],
        )
    else:
        # CORS: explicit origins (wildcard is incompatible with allow_credentials=True).
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def api_headers(request: Request, call_next):
        request.state.request_id = secrets.token_hex(6)
        response = await call_next(request)
        if request.url.path.startswith("/api") and (public or request.url.path.startswith(("/api/ask", "/api/session"))):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex"
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(ask.ApiError)
    async def api_error(request: Request, exc: ask.ApiError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status, headers=headers)

    if public:
        @app.exception_handler(RequestValidationError)
        async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
            # FastAPI's default answer repeats what was sent; this one does not.
            return JSONResponse({"error": "invalid_request",
                                 "message": f"Send one question of at most {settings.ASK_MAX_QUESTION_CHARS} characters."},
                                status_code=422)

        @app.exception_handler(Exception)
        async def unexpected(request: Request, exc: Exception) -> JSONResponse:
            request_id = getattr(request.state, "request_id", None)
            log.error("unhandled %s (request %s)", type(exc).__name__, request_id)
            return JSONResponse({"error": "internal", "message": "Something went wrong. Please try again.",
                                 "request_id": request_id}, status_code=500)

    # The question path, in both modes.
    app.include_router(ask.router, prefix="/api")

    if public:
        app.include_router(ask.health_router, prefix="/api")
    else:
        from app.routers import graph, mena, meta, query

        # Routers. Each router declares its own sub-prefix; mounted under /api here.
        app.include_router(graph.router, prefix="/api")
        app.include_router(meta.router, prefix="/api")
        app.include_router(query.router, prefix="/api")
        app.include_router(mena.router, prefix="/api")

        # Static page-figure crops (read-only) served under /api/figures/<file> so the
        # Next.js /api proxy forwards them and the FastAPI port stays internal. The query
        # endpoint returns these URLs in ``QueryResponse.figures``. Mounted only when the
        # directory exists so the app still boots on a machine without the figures.
        if config.FIGURES_DIR.is_dir():
            app.mount(
                "/api/figures",
                StaticFiles(directory=str(config.FIGURES_DIR)),
                name="figures",
            )

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        """Service banner; in local mode also a pointer to the interactive docs."""
        return {"service": settings.SERVICE_NAME} if public else {"service": settings.SERVICE_NAME, "docs": "/docs"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=False)
