"""Query service: wraps the prototype's ``retrieve.context_bundle`` (NO LLM).

This module is the business layer behind ``POST /api/query`` and
``GET /api/examples``. It does three things and nothing else:

* :func:`run_query` -- calls ``retrieve.context_bundle`` (synchronous; it
  self-manages its own Neo4j + Weaviate connections) off the event loop via
  ``fastapi.concurrency.run_in_threadpool``, then sanitizes every payload so no
  embedding/vector field can leak.
* :func:`build_query_subgraph` -- turns the (sanitized) bundle into a small
  :class:`~app.schemas.GraphResponse` for visualisation. It introduces **no new
  Cypher** -- the subgraph is derived purely from data already in the bundle.
* :func:`list_examples` -- maps ``examples_runner.DEMO`` tuples to
  :class:`~app.schemas.ExampleQuery`.

Owner contracts upheld here:

* No direct LLM/OpenAI/Anthropic calls. There is no answer-generation phase.
* Weaviate is read-only (only ``retrieve.context_bundle`` touches it, via BM25).
* Neo4j is read-only (only ``retrieve.context_bundle`` touches it).
* Embedding/vector fields are never exposed -- every dict that leaves this
  module is passed through :func:`app.deps.sanitize_props`.

Graph consistency
-----------------
Node ids, captions, chunk-data shaping, and the node/edge accumulator are reused
from :mod:`app.graph_service` when it imports cleanly, so the query subgraph is
byte-for-byte consistent with the ``/api/graph`` endpoints -- in particular a
node clicked in a query-result subgraph resolves through
``GET /api/graph/node/{id}`` (mint scheme ``issue:``/``stamp:``/``doc:``/
``chunk:``). ``graph_service`` currently imports ``app.config_bridge`` at module
load, which may not exist while sibling modules are still landing; if importing
it fails, a self-contained fallback that replicates the SAME id/label/builder
behaviour is used instead. Either way the emitted ids are identical.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi.concurrency import run_in_threadpool

# Importing settings first bootstraps sys.path for the prototype modules.
from app import settings  # noqa: F401  (import for side effect: sys.path)
from app.deps import sanitize_props
from app.schemas import ExampleQuery, GraphEdge, GraphNode, GraphResponse

import config as _proto_config  # prototype config (resolved via app.settings)
import examples_runner  # prototype module
import figure_refs  # prototype module (page-figure association)
import retrieve  # prototype module

# Visualisation budget knobs (kept small; <~60 nodes total).
_MAX_DOCS = 8
_MAX_CHUNKS_PER_DOC = 3
_PREVIEW_LEN = 180
_DEFAULT_ISSUE_TITLE = "First Issue 1863"

# Query API payload bounds (read from prototype config; override via .env). The
# display path (POST /api/query) caps BOTH the lexical-hit COUNT and each chunk's
# DISPLAYED text length, so the JSON body stays small (~tens of KB) and cannot be
# truncated in transit (which surfaces as "Unterminated string in JSON" in the
# browser). The FULL text is never sent for display -- it is delivered only by the
# export endpoint (build_export_text -> a text/plain file download, no browser JSON
# parse). retrieve.context_bundle itself is untouched (CLI / export get full text).
_API_MAX_LEXICAL = _proto_config.FIRST_ISSUE_API_MAX_LEXICAL
_API_TEXT_LIMIT = _proto_config.FIRST_ISSUE_API_TEXT_LIMIT
_QUERY_MAX_FIGURES = _proto_config.FIRST_ISSUE_QUERY_MAX_FIGURES
# Defense-in-depth cap on the Weaviate tail (retrieve already clamps k_weaviate to
# <=25, and QueryRequest validates le=25, but cap here too so this layer is safe
# regardless of caller).
_API_MAX_WEAVIATE = 25
# Long free-text keys clipped to _API_TEXT_LIMIT in the DISPLAY response only.
_TEXT_KEYS = ("text", "snippet")


# ---------------------------------------------------------------------------
# Reuse graph_service helpers when importable; otherwise fall back to faithful
# local equivalents that produce the IDENTICAL id/label/builder behaviour.
# graph_service imports app.config_bridge at load time, which may not yet exist
# while sibling modules are still being authored.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - which branch runs depends on sibling-module presence
    from app.graph_service import (  # type: ignore
        _GraphBuilder as _Builder,
        _chunk_data as _chunk_data,
        _chunk_label as _chunk_label,
        _document_label as _document_label,
        _issue_label as _issue_label,
        _stamp_label as _stamp_label,
        chunk_id as _mint_chunk_id,
        document_id as _mint_document_id,
        issue_id as _mint_issue_id,
        stamp_id as _mint_stamp_id,
    )

    _USING_GRAPH_SERVICE = True
except Exception:  # noqa: BLE001 - any import failure -> use local equivalents
    _USING_GRAPH_SERVICE = False

    # --- mint ids (mirror app.graph_service exactly) ---
    def _mint_issue_id(value: str) -> str:  # type: ignore[misc]
        return f"issue:{value}"

    def _mint_stamp_id(catalog_no: str) -> str:  # type: ignore[misc]
        return f"stamp:{catalog_no}"

    def _mint_document_id(doc_id: str) -> str:  # type: ignore[misc]
        return f"doc:{doc_id}"

    def _mint_chunk_id(chunk_id_value: str) -> str:  # type: ignore[misc]
        return f"chunk:{chunk_id_value}"

    # --- captions (mirror app.graph_service exactly) ---
    def _issue_label(props: dict[str, Any]) -> str:  # type: ignore[misc]
        return props.get("title") or _DEFAULT_ISSUE_TITLE

    def _stamp_label(props: dict[str, Any]) -> str:  # type: ignore[misc]
        catalog_no = props.get("catalog_no", "")
        denom = props.get("denomination_value")
        unit = props.get("denomination_unit") or ""
        denom_part = f" {denom}{unit}".rstrip() if denom is not None else ""
        return f"Mena {catalog_no}{denom_part}".strip()

    def _document_label(props: dict[str, Any]) -> str:  # type: ignore[misc]
        return str(props.get("doc_id") or "document")

    def _chunk_label(props: dict[str, Any]) -> str:  # type: ignore[misc]
        return f"{props.get('doc_id', '')} p.{props.get('page', '')}".strip()

    def _chunk_data(props: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
        """Sanitize chunk props, add a short preview, and drop the full text."""
        data = sanitize_props(props)
        text = props.get("text") or ""
        data["preview"] = text[:_PREVIEW_LEN]
        data.pop("text", None)
        return data

    class _Builder:  # type: ignore[no-redef]
        """Local clone of app.graph_service._GraphBuilder (same id/stats shape)."""

        def __init__(self) -> None:
            self._nodes: dict[str, GraphNode] = {}
            self._edges: dict[str, GraphEdge] = {}

        def add_node(self, node_id: str, label: str, node_type: str, data: dict[str, Any]) -> None:
            if node_id not in self._nodes:
                self._nodes[node_id] = GraphNode(id=node_id, label=label, type=node_type, data=data)

        def add_edge(
            self,
            source: str,
            target: str,
            edge_type: str,
            data: Optional[dict[str, Any]] = None,
        ) -> None:
            edge_id = f"{source}->{target}:{edge_type}"
            if edge_id not in self._edges:
                self._edges[edge_id] = GraphEdge(
                    id=edge_id,
                    source=source,
                    target=target,
                    type=edge_type,
                    data=sanitize_props(data or {}),
                )

        def stats(self) -> dict[str, int]:
            counts: dict[str, int] = {}
            for node in self._nodes.values():
                counts[node.type] = counts.get(node.type, 0) + 1
            counts["edges"] = len(self._edges)
            return counts

        def build(self) -> GraphResponse:
            return GraphResponse(
                nodes=list(self._nodes.values()),
                edges=list(self._edges.values()),
                stats=self.stats(),
            )


# ---------------------------------------------------------------------------
# Sanitization of the full bundle
# ---------------------------------------------------------------------------
def _sanitize_list(items: list[Any]) -> list[Any]:
    """Pass dict items through ``sanitize_props``; leave non-dicts untouched."""
    out: list[Any] = []
    for it in items or []:
        out.append(sanitize_props(it) if isinstance(it, dict) else it)
    return out


def _truncate_text(value: Any) -> Any:
    """Clip a free-text value to ``_API_TEXT_LIMIT`` chars (append an ellipsis)."""
    if _API_TEXT_LIMIT and isinstance(value, str) and len(value) > _API_TEXT_LIMIT:
        return value[: _API_TEXT_LIMIT - 1].rstrip() + "…"
    return value


def _sanitize_evidence_list(items: list[Any], max_items: int = 0) -> list[Any]:
    """Sanitize an evidence list for DISPLAY: cap COUNT and clip long text.

    This is for the ``lexical``/``weaviate`` hit lists shown as cards. It caps the
    number of items (the lists are already rank-ordered, so the best evidence is
    kept) AND clips each item's long ``text``/``snippet`` to ``_API_TEXT_LIMIT``,
    so the JSON body stays small and the cards stay short. The FULL text is NOT in
    this path -- it is served only by the export endpoint. ``max_items <= 0`` keeps
    every item (count-wise); text is still clipped.
    """
    src = items or []
    if max_items and max_items > 0:
        src = src[:max_items]
    out: list[Any] = []
    for it in src:
        if not isinstance(it, dict):
            out.append(it)
            continue
        clean = sanitize_props(it)
        for key in _TEXT_KEYS:
            if key in clean:
                clean[key] = _truncate_text(clean[key])
        out.append(clean)
    return out


def _sanitize_domain(domain: dict[str, Any]) -> dict[str, Any]:
    """Strip embedding/vector keys from the domain block and its nested stamps."""
    clean = sanitize_props(domain) if isinstance(domain, dict) else {}
    if isinstance(clean.get("stamps"), list):
        stamps_clean: list[Any] = []
        for st in clean["stamps"]:
            if not isinstance(st, dict):
                stamps_clean.append(st)
                continue
            st_clean = sanitize_props(st)
            if isinstance(st_clean.get("equivalent_scott"), list):
                st_clean["equivalent_scott"] = _sanitize_list(st_clean["equivalent_scott"])
            stamps_clean.append(st_clean)
        clean["stamps"] = stamps_clean
    if isinstance(clean.get("scott_roster"), list):
        clean["scott_roster"] = _sanitize_list(clean["scott_roster"])
    return clean


def _sanitize_related(related: dict[str, Any]) -> dict[str, Any]:
    """Strip embedding/vector keys from the related block."""
    clean = sanitize_props(related) if isinstance(related, dict) else {}
    if isinstance(clean.get("stamp_varieties"), list):
        clean["stamp_varieties"] = _sanitize_list(clean["stamp_varieties"])
    return clean


def _sanitize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return a fully sanitized copy of the ``context_bundle`` payload."""
    lexical = _sanitize_evidence_list(bundle.get("lexical") or [], max_items=_API_MAX_LEXICAL)
    weaviate = _sanitize_evidence_list(bundle.get("weaviate") or [], max_items=_API_MAX_WEAVIATE)
    counts = sanitize_props(bundle.get("counts") or {})
    # Reconcile the displayed counts with the (capped) lists actually returned, so
    # the UI "lexical hits" stat matches the number of evidence cards rendered.
    counts["lexical"] = len(lexical)
    counts["weaviate"] = len(weaviate)
    return {
        "domain": _sanitize_domain(bundle.get("domain") or {}),
        "related": _sanitize_related(bundle.get("related") or {}),
        "sources": _sanitize_list(bundle.get("sources") or []),
        "lexical": lexical,
        "weaviate": weaviate,
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# Public: run_query
# ---------------------------------------------------------------------------
async def run_query(
    question: str,
    stamp: Optional[str] = None,
    min_link: float = 6.0,
    max_lexical: int = 0,
    k_weaviate: int = 5,
    exclude_competing: bool = True,
    driver: Any = None,
) -> dict[str, Any]:
    """Run the read-only retrieval bundle for ``question`` (no LLM).

    ``retrieve.context_bundle`` is synchronous, so it is offloaded to a worker
    thread with ``run_in_threadpool`` to avoid blocking the event loop. It reuses
    ``driver`` (the process-wide Neo4j driver from ``app.state``) instead of
    opening a new one per question, and opens/closes its own Weaviate client. The returned bundle
    is sanitized so no embedding/vector field is ever surfaced.

    Parameters
    ----------
    question:
        Natural-language question to retrieve context for.
    stamp:
        Optional Mena scope code (1=half real, 2=2 reales, 3=4 reales, 4=1 peso).
    min_link:
        Minimum ``MENTIONS`` link score for the CLEAN tier.
    max_lexical:
        Max lexical chunks to include (0 = all that pass the gate).
    k_weaviate:
        Number of Weaviate BM25 backup hits to retrieve.
    exclude_competing:
        Drop chunks whose ``MENTIONS`` signals include ``"COMPETING"``.

    Returns
    -------
    dict
        Sanitized bundle with keys ``domain``, ``related``, ``sources``,
        ``lexical``, ``weaviate``, ``counts``.
    """
    bundle = await run_in_threadpool(
        retrieve.context_bundle,
        question,
        stamp=stamp,
        max_lexical=max_lexical,
        k_weaviate=k_weaviate,
        min_link_score=min_link,
        exclude_competing=exclude_competing,
        driver=driver,
    )
    return _sanitize_bundle(bundle)


# ---------------------------------------------------------------------------
# Public: build_query_subgraph
# ---------------------------------------------------------------------------
def _scoped_stamps(domain: dict[str, Any], stamp: Optional[str]) -> list[dict[str, Any]]:
    """Return the Mena stamps to draw: only the scoped one, or all of them."""
    stamps = [s for s in (domain.get("stamps") or []) if isinstance(s, dict)]
    if stamp:
        scoped = [s for s in stamps if str(s.get("catalog_no")) == str(stamp)]
        if scoped:
            return scoped
    return stamps


def _chunk_mentions_stamp(chunk: dict[str, Any], catalog_no: str) -> bool:
    """True if a lexical chunk references ``catalog_no``.

    The bundle's lexical rows carry a ``signals`` list and may carry a
    ``stamps`` list of catalog numbers (from ``MENTIONS_STAMP`` expansion). We
    treat either as evidence of a chunk->stamp mention.
    """
    cat = str(catalog_no)
    stamps_field = chunk.get("stamps")
    if isinstance(stamps_field, (list, tuple)) and cat in {str(x) for x in stamps_field}:
        return True
    signals = chunk.get("signals")
    if isinstance(signals, (list, tuple)) and cat in {str(x) for x in signals}:
        return True
    return False


def build_query_subgraph(bundle: dict[str, Any], stamp: Optional[str] = None) -> GraphResponse:
    """Build a small result subgraph from an (already sanitized) bundle.

    Nodes
    -----
    * one ``Issue`` node (graph centre),
    * the in-scope Mena ``Stamp`` node(s) (all, or only the scoped one),
    * the top ~8 source ``Document`` nodes (``bundle["sources"]``),
    * up to ~3 ``Chunk`` nodes per top doc (matched from ``bundle["lexical"]``).

    Edges
    -----
    * ``HAS_STAMP``      Issue -> Stamp,
    * ``HAS_CHUNK``      Document -> Chunk,
    * ``MENTIONS``       Chunk -> Issue,
    * ``MENTIONS_STAMP`` Chunk -> Stamp (only when the chunk references it).

    No Cypher is issued -- everything is derived from ``bundle``. Node ids,
    captions, and chunk-data shaping mirror :mod:`app.graph_service` so this
    subgraph is consistent with the ``/api/graph`` endpoints (clicking a node
    resolves through ``GET /api/graph/node/{id}``). The chunk node's
    ``data.preview`` is the first 180 chars of the chunk text and the full
    ``text`` is dropped; raw embeddings are never present (the bundle is
    sanitized before it reaches here).
    """
    domain = bundle.get("domain") or {}
    sources = [s for s in (bundle.get("sources") or []) if isinstance(s, dict)]
    lexical = [c for c in (bundle.get("lexical") or []) if isinstance(c, dict)]

    builder = _Builder()

    # 1) Issue node (centre). Use the configured issue id so the mint id matches
    #    the graph endpoints even when the bundle's domain lacks issue_id.
    iid = str(domain.get("issue_id") or _proto_config.ISSUE_ID)
    issue_nid = _mint_issue_id(iid)
    issue_props = sanitize_props(
        {
            "issue_id": domain.get("issue_id"),
            "title": domain.get("title"),
            "country": domain.get("country"),
            "perforation": domain.get("perforation"),
            "issue_dates": domain.get("issue_dates"),
        }
    )
    builder.add_node(issue_nid, _issue_label(issue_props), "Issue", issue_props)

    # 2) In-scope Mena Stamp node(s) + HAS_STAMP edges.
    stamp_nids: dict[str, str] = {}
    for st in _scoped_stamps(domain, stamp):
        cat = str(st.get("catalog_no") or "")
        if not cat:
            continue
        snid = _mint_stamp_id(cat)
        stamp_nids[cat] = snid
        sprops = sanitize_props(
            {
                "catalog_no": st.get("catalog_no"),
                "denomination_value": st.get("denomination_value"),
                "denomination_unit": st.get("denomination_unit"),
                "color": st.get("color"),
                "perforation": st.get("perforation"),
                "status": st.get("status"),
                "quantity_reported": st.get("quantity_reported"),
            }
        )
        builder.add_node(snid, _stamp_label(sprops), "Stamp", sprops)
        builder.add_edge(issue_nid, snid, "HAS_STAMP")

    # 3) Top source Documents + their representative Chunks (from the lexical set).
    lexical_by_doc: dict[str, list[dict[str, Any]]] = {}
    for c in lexical:
        lexical_by_doc.setdefault(str(c.get("doc_id")), []).append(c)

    for src in sources[:_MAX_DOCS]:
        doc_raw = str(src.get("doc_id") or "")
        if not doc_raw:
            continue
        dnid = _mint_document_id(doc_raw)
        builder.add_node(
            dnid,
            _document_label({"doc_id": doc_raw}),
            "Document",
            sanitize_props(
                {
                    "doc_id": src.get("doc_id"),
                    "chunks": src.get("chunks"),
                    "best_score": src.get("best_score"),
                    "best_link": src.get("best_link"),
                    "pages": src.get("pages"),
                }
            ),
        )

        for chunk in lexical_by_doc.get(doc_raw, [])[:_MAX_CHUNKS_PER_DOC]:
            cid = chunk.get("chunk_id")
            if not cid:
                continue
            cnid = _mint_chunk_id(str(cid))
            # _chunk_data sanitizes, adds preview (180 chars), and drops full text.
            builder.add_node(cnid, _chunk_label(chunk), "Chunk", _chunk_data(chunk))
            builder.add_edge(dnid, cnid, "HAS_CHUNK")
            builder.add_edge(
                cnid,
                issue_nid,
                "MENTIONS",
                {"score": chunk.get("link_score"), "signals": chunk.get("signals")},
            )
            for cat, snid in stamp_nids.items():
                if _chunk_mentions_stamp(chunk, cat):
                    builder.add_edge(cnid, snid, "MENTIONS_STAMP")

    return builder.build()


# ---------------------------------------------------------------------------
# Public: collect_query_figures
# ---------------------------------------------------------------------------
def collect_query_figures(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Related page figures for the query, from its (already sanitized) bundle.

    Delegates to :func:`figure_refs.figures_for_query`, which maps the ranked
    lexical hits to the figures cropped from their ``(doc_id, page)`` — the
    sanitized chunk text no longer carries the inline ``![Figure](...)`` embeds,
    so the association is by page, not by text. Returns at most
    ``FIRST_ISSUE_QUERY_MAX_FIGURES`` figures, de-duplicated and rank-ordered.
    """
    lexical = [c for c in (bundle.get("lexical") or []) if isinstance(c, dict)]
    return figure_refs.figures_for_query(lexical, max_figures=_QUERY_MAX_FIGURES)


# ---------------------------------------------------------------------------
# Public: build_export_text (FULL text, server-side; for the file download)
# ---------------------------------------------------------------------------
_DATE_LABELS = {
    "announced": "announced",
    "placed_on_sale": "placed on sale",
    "probable_first_circulation": "first circulation",
    "second_plate_sale": "second plate",
    "demonetized": "demonetized",
}
# Display-only denomination fix mirroring the frontend (Mena 1A = 0.5 real).
_DENOM_OVERRIDES = {"1A": (0.5, "real")}


def _issue_dates_text(value: Any) -> str:
    """Render the issue_dates map (a JSON string) as 'label value · ...'."""
    if value in (None, ""):
        return "—"
    obj: Any = value
    if isinstance(value, str):
        s = value.strip()
        if not s.startswith("{"):
            return s
        try:
            obj = json.loads(s)
        except ValueError:
            return s
    if not isinstance(obj, dict):
        return str(value)
    parts = [
        f"{_DATE_LABELS.get(k, k.replace('_', ' '))} {v}"
        for k, v in obj.items()
        if v not in (None, "")
    ]
    return " · ".join(parts) if parts else "—"


def _display_denom(catalog_no: Any, value: Any, unit: Any) -> str:
    """Format a Mena denomination, applying the known 1A source-data override."""
    override = _DENOM_OVERRIDES.get(str(catalog_no or ""))
    if override:
        value, unit = override
    if value in (None, ""):
        return str(unit) if unit else ""
    return f"{value} {unit or ''}".strip()


def _page_token(page: Any) -> str:
    return str(page) if page not in (None, "") else "?"


def build_export_text(
    question: str,
    stamp: Optional[str] = None,
    min_link: float = 6.0,
    max_lexical: int = 0,
    k_weaviate: int = 5,
    exclude_competing: bool = True,
    driver: Any = None,
) -> str:
    """Build the FULL-text, LLM-ready .txt export for a question (server-side).

    This is the ONLY path that exposes full chunk text. It runs
    ``retrieve.context_bundle`` with full text (no display truncation) and formats
    a grounded, citation-first prompt. The router returns it as a ``text/plain``
    file download, so the browser never JSON-parses a large body (which is what
    causes "Unterminated string in JSON" on the display path). Embedding/vector
    fields are stripped via the same sanitizers as the display path.
    """
    question = (question or "").strip()
    bundle = retrieve.context_bundle(
        question,
        stamp=stamp,
        max_lexical=max_lexical,
        k_weaviate=k_weaviate,
        min_link_score=min_link,
        exclude_competing=exclude_competing,
        driver=driver,
    )
    domain = _sanitize_domain(bundle.get("domain") or {})
    sources = [s for s in (bundle.get("sources") or []) if isinstance(s, dict)]
    lexical = [c for c in (bundle.get("lexical") or []) if isinstance(c, dict)]
    weaviate = [w for w in (bundle.get("weaviate") or []) if isinstance(w, dict)]

    out: list[str] = [
        "# Costa Rica 1863 First Issue — grounded retrieval bundle",
        "",
        "ROLE: You are a philatelic research assistant for the Costa Rica 1863",
        "First Issue. Using ONLY the evidence in this file, answer the QUESTION.",
        "Cite every claim as [doc_id p.PAGE]. If the evidence is insufficient,",
        "say so plainly instead of guessing. Treat DOMAIN FACTS as authoritative",
        "for denominations, colours, dates and Scott/Mena equivalences.",
        "",
        "## QUESTION",
        question or "(none provided)",
        "",
        "## DOMAIN FACTS (authoritative catalog)",
    ]
    if domain.get("title"):
        country = f" — {domain['country']}" if domain.get("country") else ""
        out.append(f"Issue: {domain['title']}{country}")
    if domain.get("issue_dates"):
        out.append(f"Dates: {_issue_dates_text(domain.get('issue_dates'))}")
    if domain.get("perforation"):
        out.append(f"Perforation: {domain['perforation']}")
    stamps = [s for s in (domain.get("stamps") or []) if isinstance(s, dict)]
    if stamps:
        out.append("Stamps (Mena → Scott):")
        for s in stamps:
            denom = _display_denom(
                s.get("catalog_no"), s.get("denomination_value"), s.get("denomination_unit")
            )
            scotts = ", ".join(
                f"Scott {x.get('scott_number')}"
                for x in (s.get("equivalent_scott") or [])
                if isinstance(x, dict) and x.get("scott_number") not in (None, "")
            )
            bits = " ".join(b for b in (denom, s.get("color") or "") if b)
            tail = f" = {scotts}" if scotts else ""
            out.append(f"  - Mena {s.get('catalog_no')}: {bits}{tail}")
    note = domain.get("plain_raw_text_excerpt")
    if note:
        out.extend(["", "Catalog note:", str(note)])
    out.append("")

    if sources:
        out.append("## SOURCE DOCUMENTS (ranked by relevance)")
        for s in sources:
            pages = ", ".join(str(p) for p in (s.get("pages") or [])) or "?"
            out.append(f"  - {s.get('doc_id')} — {s.get('chunks')} chunk(s), pp {pages}")
        out.append("")

    if lexical:
        out.append("## EVIDENCE PASSAGES (graph-linked, full text)")
        for i, h in enumerate(lexical, start=1):
            sigs = h.get("signals")
            sig = (
                f" — signals: {', '.join(str(x) for x in sigs)}"
                if isinstance(sigs, (list, tuple)) and sigs
                else ""
            )
            out.append("")
            out.append(f"[{i}] {h.get('doc_id')} p.{_page_token(h.get('page'))}{sig}")
            out.append(str(h.get("text") or "").strip())
        out.append("")

    if weaviate:
        out.append("## ADDITIONAL PASSAGES (BM25 keyword backup)")
        for i, h in enumerate(weaviate, start=1):
            out.append("")
            out.append(f"[W{i}] {h.get('doc_id')} p.{_page_token(h.get('page'))}")
            out.append(str(h.get("snippet") or "").strip())
        out.append("")

    out.extend(
        [
            "---",
            "This is a retrieval-only bundle: no answer was generated by the system.",
            "The documents above are the grounding for your answer.",
        ]
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Public: list_examples
# ---------------------------------------------------------------------------
def list_examples() -> list[ExampleQuery]:
    """Map ``examples_runner.DEMO`` tuples to :class:`ExampleQuery` models."""
    out: list[ExampleQuery] = []
    for item in examples_runner.DEMO:
        question, stamp = item[0], (item[1] if len(item) > 1 else None)
        out.append(ExampleQuery(question=question, stamp=stamp))
    return out
