"""Application settings and prototype package bootstrap.

This module is the single place that:

1. Holds the FastAPI runtime configuration (port, CORS origins).
2. Resolves ``PKG_DIR`` -- the absolute path of the ``first_issue_graphrag``
   prototype package -- and prepends it to ``sys.path`` so that the prototype
   modules (``config``, ``retrieve``, ``examples_runner``) import as top-level
   modules exactly the way the prototype's own scripts import them.

Importing this module has the side effect of mutating ``sys.path`` once. Any
backend module that needs the prototype API should ``import app.settings``
(or import something from it) *before* doing ``import config`` / ``import
retrieve`` / ``import examples_runner``.

The backend honours three owner contracts and they are enforced elsewhere:

* No direct LLM/OpenAI/Anthropic API calls in new code (Weaviate's own
  vectorizer is the only exception). No answer-generation phase.
* Weaviate is read-only.
* Neo4j queries issued by the backend are read-only.
* Embedding/vector properties are never exposed (stripped in ``app.deps``).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# This file lives at: first_issue_graphrag/backend/app/settings.py
#   parents[0] -> .../backend/app
#   parents[1] -> .../backend
#   parents[2] -> .../first_issue_graphrag          <-- the prototype package
APP_DIR: Path = Path(__file__).resolve().parent
BACKEND_DIR: Path = APP_DIR.parent
PKG_DIR: Path = BACKEND_DIR.parent

# Make the prototype importable as top-level modules: ``import config`` etc.
_PKG_DIR_STR: str = str(PKG_DIR)
if _PKG_DIR_STR not in sys.path:
    sys.path.insert(0, _PKG_DIR_STR)


# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
API_HOST: str = "0.0.0.0"
API_PORT: int = 8090

# Exact origins for CORS. ``allow_credentials=True`` is incompatible with the
# ``["*"]`` wildcard, so the frontend dev origin(s) are listed explicitly.
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Service metadata surfaced at the root endpoint.
SERVICE_NAME: str = "First Issue KG Explorer API"
