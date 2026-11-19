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

import os
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
# Localhost by default: the browser reaches the API through the Next.js /api
# proxy, so the backend port does not need to be exposed. Override with API_HOST.
API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
API_PORT: int = int(os.getenv("API_PORT", "8090"))

# Exact origins for CORS. ``allow_credentials=True`` is incompatible with the
# ``["*"]`` wildcard, so the frontend dev origin(s) are listed explicitly.
CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Service metadata surfaced at the root endpoint.
SERVICE_NAME: str = "First Issue KG Explorer API"


# ---------------------------------------------------------------------------
# The question path (POST /api/ask) and the hosted mode
# ---------------------------------------------------------------------------
def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


# Hosted mode: only the question path is mounted, the API docs are off, and a
# human check is required before questions are accepted.
PUBLIC: bool = _flag("OXCART_PUBLIC")

# CORS_ORIGINS in the environment replaces the localhost defaults (comma separated).
if os.getenv("CORS_ORIGINS"):
    CORS_ORIGINS = [o.strip() for o in os.environ["CORS_ORIGINS"].split(",") if o.strip()]

# Bounds fixed by the server. Nothing a client sends changes them.
ASK_MAX_QUESTION_CHARS: int = _int("ASK_MAX_QUESTION_CHARS", 300)
ASK_MAX_BODY_BYTES: int = _int("ASK_MAX_BODY_BYTES", 2048)
ASK_PASSAGES: int = _int("ASK_PASSAGES", 5)
ASK_ISSUES: int = _int("ASK_ISSUES", 3)
ASK_TEXT_LIMIT: int = _int("ASK_TEXT_LIMIT", 700)
ASK_TIMEOUT_SECONDS: int = _int("ASK_TIMEOUT_SECONDS", 25)
EMBED_TIMEOUT_SECONDS: int = _int("EMBED_TIMEOUT_SECONDS", 5)

# Limits per visitor and for the whole service (kept in this process's memory).
ASK_LIMIT_PER_MINUTE: int = _int("ASK_LIMIT_PER_MINUTE", 10)
ASK_LIMIT_PER_DAY: int = _int("ASK_LIMIT_PER_DAY", 100)
ASK_LIMIT_GLOBAL_PER_DAY: int = _int("ASK_LIMIT_GLOBAL_PER_DAY", 2000)
# How many proxies of the host stand in front of this process. The visitor's address is
# read that many entries from the right of X-Forwarded-For; 0 = use the socket's peer.
TRUSTED_PROXY_HOPS: int = _int("TRUSTED_PROXY_HOPS", 1)

# The literature store for the question path: a Weaviate Cloud cluster when WEAVIATE_URL
# is set, the local instance of config.py otherwise. OXCART_VECTOR_NAME names the vector
# to search when the collection has several.
WEAVIATE_URL: str = os.getenv("WEAVIATE_URL", "")
VECTOR_NAME: str = os.getenv("OXCART_VECTOR_NAME", "")
EMBEDDING_MODEL: str = "text-embedding-3-large"

# Human check (Cloudflare Turnstile) and the session token that follows it.
TURNSTILE_SECRET: str = os.getenv("TURNSTILE_SECRET", "")
TURNSTILE_VERIFY_URL: str = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
SESSION_SIGNING_KEY: str = os.getenv("SESSION_SIGNING_KEY", "")
SESSION_TTL_SECONDS: int = _int("SESSION_TTL_SECONDS", 3600)
# The eval's own way in: a secret header. Empty = that door does not exist.
EVAL_ACCESS_KEY: str = os.getenv("EVAL_ACCESS_KEY", "")
