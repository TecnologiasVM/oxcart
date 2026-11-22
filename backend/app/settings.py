"""Application settings.

This module holds the FastAPI runtime configuration (port, CORS origins, and the
question path's limits and keys).

The shared modules (``config``, ``retrieve``, ``examples_runner``, the catalogue
lookup) are the ``oxcart`` package at the repository root. It is installed into the
environment (``python -m pip install -e .`` from the root), so the backend imports
it like any other package: ``from oxcart import config``.

The backend honours these contracts and they are enforced elsewhere:

* One module calls a language model: ``app.answer_model`` (the written answer of
  ``POST /api/chat``). One module calls an embedding service: ``app.ask_service``
  (the question's vector). No other code calls a model, and the explorer's routes
  call none.
* Weaviate is read-only.
* Neo4j queries issued by the backend are read-only.
* Embedding/vector properties are never exposed (stripped in ``app.deps``).
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# This file lives at: backend/app/settings.py
#   parents[0] -> .../backend/app
#   parents[1] -> .../backend
APP_DIR: Path = Path(__file__).resolve().parent
BACKEND_DIR: Path = APP_DIR.parent


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
# Which part of a passage longer than the limit is shown: "start" (its first characters) or "nearest"
# (the stretch that shares the most words with the question). The model is given what is shown.
ASK_EXCERPT: str = "nearest" if os.getenv("ASK_EXCERPT", "").strip().lower() == "nearest" else "start"
# The catalogue lookup also asks the second, short vector index of the issues (their title, years and
# section). Off until the graph holds it: scripts/issue_short_vectors.py writes it and can take it away.
ASK_SHORT_VECTOR: bool = _flag("ASK_SHORT_VECTOR")
ASK_TIMEOUT_SECONDS: int = _int("ASK_TIMEOUT_SECONDS", 25)
EMBED_TIMEOUT_SECONDS: int = _int("EMBED_TIMEOUT_SECONDS", 5)

# Limits per visitor and for the whole service (kept in this process's memory).
ASK_LIMIT_PER_MINUTE: int = _int("ASK_LIMIT_PER_MINUTE", 10)
ASK_LIMIT_PER_DAY: int = _int("ASK_LIMIT_PER_DAY", 100)
ASK_LIMIT_GLOBAL_PER_DAY: int = _int("ASK_LIMIT_GLOBAL_PER_DAY", 2000)
# How many proxies of the host stand in front of this process. The visitor's address is
# read that many entries from the right of X-Forwarded-For; 0 = use the socket's peer.
TRUSTED_PROXY_HOPS: int = _int("TRUSTED_PROXY_HOPS", 1)
# The header in which the host's edge reports the visitor's address (CF-Connecting-IP where
# Cloudflare stands in front). When this names a header and a request carries it, the visitor
# is that value; empty, or a request without the header: the X-Forwarded-For rule above.
# Name only a header the edge overwrites on every request, and check it on the host: a
# made-up value sent by a client must not change the count.
VISITOR_ADDRESS_HEADER: str = os.getenv("VISITOR_ADDRESS_HEADER", "").strip().lower()

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

# The graph connection. A hosted graph can refuse a new connection and accept the next one
# half a second later, so nothing depends on the first try: the process opens the connection
# as it starts, retrying inside a budget, and a question that finds none retries inside its own.
GRAPH_WARM_ON_START: bool = os.getenv("GRAPH_WARM_ON_START", "1").strip().lower() not in ("0", "false", "no", "off")
GRAPH_STARTUP_BUDGET_SECONDS: int = _int("GRAPH_STARTUP_BUDGET_SECONDS", 30)
GRAPH_QUESTION_BUDGET_SECONDS: int = _int("GRAPH_QUESTION_BUDGET_SECONDS", 8)
GRAPH_RETRY_EVERY_SECONDS: float = float(os.getenv("GRAPH_RETRY_EVERY_SECONDS", "0.5") or 0.5)

# The literature client and the embedding's connection are opened as the process starts too, in the
# background, so the first question does not wait for them. Opening the embedding's connection makes
# one tiny embedding per start.
ASK_WARM_ON_START: bool = os.getenv("ASK_WARM_ON_START", "1").strip().lower() not in ("0", "false", "no", "off")


# ---------------------------------------------------------------------------
# The written answer (POST /api/chat)
# ---------------------------------------------------------------------------
# A short answer written from the evidence, by one language model called from this process.
# Without ANTHROPIC_API_KEY the route still answers: with the evidence, and no written answer.
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANSWER_MODEL: str = "claude-haiku-5-5"
# Effort "low", the lowest, with thinking on. The evaluation compared thinking on and off
# (EVALUATION.md): off, the model copied the cited text into its answers and half of the
# literature answers were cut at the output limit. ANSWER_THINKING=disabled turns it off.
# With thinking on, the thinking shares the output budget, so it gets room of its own.
ANSWER_EFFORT: str = os.getenv("ANSWER_EFFORT", "low").strip().lower() or "low"
ANSWER_THINKING: str = "disabled" if os.getenv("ANSWER_THINKING", "").strip().lower() == "disabled" else "adaptive"
ANSWER_MAX_TOKENS: int = _int("ANSWER_MAX_TOKENS", 500)
ANSWER_THINKING_ROOM_TOKENS: int = _int("ANSWER_THINKING_ROOM_TOKENS", 1500)
REWRITE_MAX_TOKENS: int = _int("REWRITE_MAX_TOKENS", 120)
ANSWER_TIMEOUT_SECONDS: int = _int("ANSWER_TIMEOUT_SECONDS", 12)
REWRITE_TIMEOUT_SECONDS: int = _int("REWRITE_TIMEOUT_SECONDS", 5)
# Model calls a day for the whole service (kept in this process's memory). Every call counts,
# the rewrite of a follow-up too. Past it the route answers with the evidence only.
ANSWER_LIMIT_PER_DAY: int = _int("ANSWER_LIMIT_PER_DAY", 200)
# A follow-up comes with the earlier turns of its conversation, kept by the browser.
CHAT_MAX_BODY_BYTES: int = _int("CHAT_MAX_BODY_BYTES", 8192)
CHAT_THREAD_TURNS: int = 3
CHAT_THREAD_ANSWER_CHARS: int = 1200
