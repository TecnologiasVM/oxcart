"""
Central configuration + connection factories for the First Issue GraphRAG prototype.

What this package keeps to:
  * No DIRECT LLM API calls anywhere in this package. Weaviate may use OpenAI
    under the hood for its own vectorizer — that is an accepted exception.
  * Weaviate is READ-ONLY here. Never create/delete/overwrite Weaviate data.
  * Neo4j writes are ADDITIVE + NAMESPACED. Every node/relationship this
    prototype creates carries the property ``prototype = PROTOTYPE_TAG`` so it
    can be removed cleanly by ``teardown.py`` without touching the existing
    Mena domain graph.

This module is part of the ``oxcart`` package: ``from oxcart import config`` or
``from oxcart.config import ...``. The package is installed into the environment with
``python -m pip install -e .`` from the repository root.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent

RESULTS_DIR = REPO_ROOT / "results"
MARKDOWN_DIR = RESULTS_DIR / "markdown"
# Dolphin page-figure crops, named ``<doc_id>_page_<NNN>_figure_<MMM>.png``.
FIGURES_DIR = MARKDOWN_DIR / "figures"
FINAL_JSONS_DIR = RESULTS_DIR / "final_jsons"
PATCH_DIR = RESULTS_DIR / "oxcarts-patch"

# Read by the First Issue graph build (pipeline/first_issue_graph/build_domain_scott.py).
DATA_DIR = REPO_ROOT / "pipeline" / "first_issue_graph" / "data"
SCOTT_DETAILS_PATH = DATA_DIR / "scott_first_issue.json"
SCOTT_EQUIV_PATH = DATA_DIR / "scott_equivalences.json"

# --------------------------------------------------------------------------- #
# The environment file: loaded by oxcart/env.py, before any setting below is read
# --------------------------------------------------------------------------- #
from oxcart import env as _env  # noqa: E402,F401

# --------------------------------------------------------------------------- #
# Domain constants
# --------------------------------------------------------------------------- #
PROTOTYPE_TAG = "first_issue_graphrag"  # stamped on every node/rel we create
ISSUE_ID = "CR-1863-FIRST-ISSUE"

# --------------------------------------------------------------------------- #
# Neo4j
# --------------------------------------------------------------------------- #
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


def neo4j_driver():
    """Return a Neo4j driver. Caller is responsible for ``.close()`` (use ``with``)."""
    from neo4j import GraphDatabase, basic_auth

    return GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))


# --------------------------------------------------------------------------- #
# Weaviate (READ-ONLY)
# --------------------------------------------------------------------------- #
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_HTTP_PORT = int(os.getenv("WEAVIATE_HTTP_PORT", "8085"))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50056"))
OXCART_COLLECTION = os.getenv("OXCART_COLLECTION", "Oxcart")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Optional. Set when the Weaviate instance has anonymous access disabled
# (API-key auth). Unset = anonymous, as with the bundled docker-compose.yml.
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")


def weaviate_client():
    """
    Connect to the local Oxcart Weaviate (read-only usage in this package).

    The OpenAI header is attached only so that semantic queries (near_text /
    hybrid) work via Weaviate's own vectorizer. Pure BM25 needs no key and is
    the default lexical path used here.
    """
    import weaviate

    headers = {}
    if OPENAI_API_KEY:
        headers["X-OpenAI-Api-Key"] = OPENAI_API_KEY
    auth = None
    if WEAVIATE_API_KEY:
        from weaviate.classes.init import Auth

        auth = Auth.api_key(WEAVIATE_API_KEY)
    return weaviate.connect_to_local(
        host=WEAVIATE_HOST,
        port=WEAVIATE_HTTP_PORT,
        grpc_port=WEAVIATE_GRPC_PORT,
        headers=headers or None,
        auth_credentials=auth,
    )


# --------------------------------------------------------------------------- #
# Lexical-linking tunables (prototype-specific; override via .env)
# --------------------------------------------------------------------------- #
# Minimum weighted signal score for a chunk to be linked to the First Issue.
FIRST_ISSUE_MIN_LINK_SCORE = float(os.getenv("FIRST_ISSUE_MIN_LINK_SCORE", "4"))
# A chunk must fire at least this many DISTINCT strong signal classes to link.
# This is the precision gate: it rejects chunks that match on a single ambiguous
# cue (e.g. the bare phrase "first issue") with no corroborating first-issue evidence.
FIRST_ISSUE_MIN_STRONG_CLASSES = int(os.getenv("FIRST_ISSUE_MIN_STRONG_CLASSES", "2"))
# When competing/later-issue context is present, require this many strong classes.
FIRST_ISSUE_COMPETING_MIN_CLASSES = int(os.getenv("FIRST_ISSUE_COMPETING_MIN_CLASSES", "3"))
# Minimum confidence to attach a specific stamp (denomination+color match).
FIRST_ISSUE_STAMP_MIN_CONF = float(os.getenv("FIRST_ISSUE_STAMP_MIN_CONF", "0.5"))

# --------------------------------------------------------------------------- #
# Query API payload bounds (override via .env)
# --------------------------------------------------------------------------- #
# The query endpoint serializes the whole context bundle to JSON. Left unbounded
# (``max_lexical=0`` returns EVERY clean chunk), a broad question can match ~230
# chunks at ~4.5 KB each -> a ~1.25 MB response that gets truncated in transit
# through the Next.js /api proxy (over LAN/ZeroTier) -> the browser's JSON.parse
# then fails with "Unterminated string in JSON". We cap the NUMBER of lexical hits
# (the list is already rank-ordered, so the best evidence is kept) but keep each
# chunk's FULL text, so the .txt export stays complete and the UI clamps card size
# in CSS. retrieve.context_bundle itself is unchanged (CLI/LLM path still gets all).
# Max lexical hits returned by POST /api/query (0 = no cap; not recommended).
FIRST_ISSUE_API_MAX_LEXICAL = int(os.getenv("FIRST_ISSUE_API_MAX_LEXICAL", "40"))
# Per-chunk text/snippet char cap for the DISPLAYED evidence cards in the
# POST /api/query response. Even with the count cap above, individual chunks can
# be >10 KB, so a query can still produce a >256 KB JSON body that truncates in
# transit ("Unterminated string in JSON"). The cards only need a preview, so we
# clip the displayed text here. The FULL text is never sent for display -- it is
# available only via POST /api/query/export (a file download, no browser JSON
# parse). 0 = no truncation (not recommended for the display path).
FIRST_ISSUE_API_TEXT_LIMIT = int(os.getenv("FIRST_ISSUE_API_TEXT_LIMIT", "700"))
# Max related page-figures surfaced per query (the "related pictures" gallery).
FIRST_ISSUE_QUERY_MAX_FIGURES = int(os.getenv("FIRST_ISSUE_QUERY_MAX_FIGURES", "10"))


def env_summary() -> dict:
    """Non-secret snapshot of the active configuration (for logging at init)."""
    return {
        "NEO4J_URI": NEO4J_URI,
        "NEO4J_DATABASE": NEO4J_DATABASE,
        "NEO4J_PASSWORD_set": bool(NEO4J_PASSWORD),
        "WEAVIATE": f"{WEAVIATE_HOST}:{WEAVIATE_HTTP_PORT} (grpc {WEAVIATE_GRPC_PORT})",
        "OXCART_COLLECTION": OXCART_COLLECTION,
        "OPENAI_KEY_present": bool(OPENAI_API_KEY),
        "ISSUE_ID": ISSUE_ID,
        "PROTOTYPE_TAG": PROTOTYPE_TAG,
        "MIN_LINK_SCORE": FIRST_ISSUE_MIN_LINK_SCORE,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(env_summary(), indent=2))
