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

Run (from ``first_issue_graphrag/backend``)::

    ../../.venv-clean/Scripts/python.exe -m uvicorn app.main:app --port 8090

or directly::

    ../../.venv-clean/Scripts/python.exe -m app.main
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importing settings first bootstraps sys.path for the prototype modules.
from app import settings
from app.deps import lifespan
from app.routers import graph, mena, meta, query

app = FastAPI(
    title=settings.SERVICE_NAME,
    lifespan=lifespan,
)

# CORS: explicit origins (wildcard is incompatible with allow_credentials=True).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers. Each router declares its own sub-prefix; mounted under /api here.
app.include_router(graph.router, prefix="/api")
app.include_router(meta.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(mena.router, prefix="/api")


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Service banner and a pointer to the interactive docs."""
    return {"service": settings.SERVICE_NAME, "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8090, reload=False)
