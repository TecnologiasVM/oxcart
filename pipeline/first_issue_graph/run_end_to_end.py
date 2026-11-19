"""
End-to-end orchestrator for the First Issue GraphRAG prototype.

Runs the full prototype pipeline in order and prints a consolidated
VALIDATION REPORT. All work is delegated to the sibling modules' public APIs;
this script does NOT shell out and does NOT make direct LLM calls.

Pipeline (each step imports a sibling module and calls its public API):
  0. config.env_summary()                          - print active config
  1. sanitize_chunks.write_patched(docs)           - clean contaminated chunks
  2. build_domain_scott.build_domain_scott()       - Scott stamps + illustrations
  3. build_lexical_graph.build_lexical_graph(docs) - Document/Chunk nodes + NEXT
  4. link_lexical_to_domain.link_lexical_to_domain(docs) - MENTIONS edges
  5. retrieve.answer(question)                      - sample grounded answers

The VALIDATION REPORT summarizes per-step counts plus live graph/Weaviate
counts (# Scott nodes, # chunks, # MENTIONS edges, Weaviate overlap) read
directly from Neo4j/Weaviate, and prints one full sample answer card.

Run from repo root (the package dir is sys.path[0], so bare imports work):
    python first_issue_graphrag/run_end_to_end.py
    python first_issue_graphrag/run_end_to_end.py --docs OXCART03 OXCART50
    python first_issue_graphrag/run_end_to_end.py --skip-sanitize --skip-domain

Exit code is non-zero if any (non-skipped) step raises; the failing step and
exception are summarized in the report.
"""

from __future__ import annotations

import argparse
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence

import config

# Default sample questions used to exercise the retriever (step 5).
SAMPLE_QUESTIONS: List[str] = [
    "What is the Costa Rica first issue?",
    "Tell me about the half real blue stamp",
    "What plate varieties exist on the first issue?",
]


# --------------------------------------------------------------------------- #
# Small helpers for shape-tolerant introspection of sibling return values.
# --------------------------------------------------------------------------- #
def _as_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort coerce a sibling return value into a plain dict for reporting."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return dict(obj)
    # dataclass / simple namespace style object
    data = getattr(obj, "__dict__", None)
    if isinstance(data, dict):
        return dict(data)
    return {"value": obj}


def _stats_dict(obj: Any) -> Dict[str, Any]:
    """Coerce a sibling return value to a dict, unwrapping a nested ``stats`` block.

    ``build_lexical_graph``/``link_lexical_to_domain`` return ``{"stats": {...}}``;
    surface those inner counts for the per-step report line.
    """
    data = _as_dict(obj)
    inner = data.get("stats")
    return dict(inner) if isinstance(inner, dict) else data


def _first_int(d: Dict[str, Any], keys: Sequence[str]) -> Optional[int]:
    """Return the first present, int-coercible value among ``keys`` in ``d``."""
    for key in keys:
        if key in d:
            try:
                return int(d[key])
            except (TypeError, ValueError):
                continue
    return None


def _summarize_counts(d: Dict[str, Any], candidate_keys: Sequence[str]) -> str:
    """Render a compact 'k=v' string for whichever count-ish keys are present."""
    parts: List[str] = []
    for key in candidate_keys:
        if key in d:
            parts.append(f"{key}={d[key]}")
    if not parts:
        # fall back to any scalar (int/str/bool) fields
        for key, value in d.items():
            if isinstance(value, (int, float, str, bool)):
                parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "(no counts reported)"


# --------------------------------------------------------------------------- #
# Step runner
# --------------------------------------------------------------------------- #
class StepResult:
    """Outcome of a single pipeline step."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.skipped: bool = False
        self.ok: bool = False
        self.payload: Any = None
        self.error: Optional[BaseException] = None
        self.summary: str = ""

    def as_line(self) -> str:
        if self.skipped:
            return f"  [SKIP] {self.name}"
        status = "OK  " if self.ok else "FAIL"
        detail = self.summary or (repr(self.error) if self.error else "")
        return f"  [{status}] {self.name}: {detail}"


def _run_step(name: str, fn: Callable[[], Any], skip: bool) -> StepResult:
    """Execute a step, capturing success/skip/failure without raising."""
    result = StepResult(name)
    if skip:
        result.skipped = True
        result.summary = "skipped via flag"
        return result
    try:
        result.payload = fn()
        result.ok = True
    except BaseException as exc:  # noqa: BLE001 - we want to report any failure
        result.error = exc
        result.ok = False
    return result


# --------------------------------------------------------------------------- #
# Live graph / Weaviate read-only counts (for the validation report).
# --------------------------------------------------------------------------- #
def _neo4j_counts() -> Dict[str, Any]:
    """Read prototype-scoped counts from Neo4j (read-only)."""
    tag = config.PROTOTYPE_TAG
    issue_id = config.ISSUE_ID
    counts: Dict[str, Any] = {}
    queries: Dict[str, str] = {
        "scott_stamp_nodes": "MATCH (s:ScottStamp {prototype:$tag}) RETURN count(s) AS n",
        "illustration_nodes": "MATCH (i:Illustration {prototype:$tag}) RETURN count(i) AS n",
        "document_nodes": "MATCH (d:Document {prototype:$tag}) RETURN count(d) AS n",
        "chunk_nodes": "MATCH (c:Chunk {prototype:$tag}) RETURN count(c) AS n",
        "mentions_edges": (
            "MATCH (:Chunk {prototype:$tag})-[r:MENTIONS]->(:Issue {issue_id:$iid}) "
            "RETURN count(r) AS n"
        ),
        "mentions_stamp_edges": (
            "MATCH (:Chunk {prototype:$tag})-[r:MENTIONS_STAMP]->(:Stamp {issue_id:$iid}) "
            "RETURN count(r) AS n"
        ),
        "has_scott_stamp_edges": (
            "MATCH (:Issue {issue_id:$iid})-[r:HAS_SCOTT_STAMP]->(:ScottStamp {prototype:$tag}) "
            "RETURN count(r) AS n"
        ),
        "equivalent_to_edges": (
            "MATCH (:Stamp {issue_id:$iid})-[r:EQUIVALENT_TO]->(:ScottStamp {prototype:$tag}) "
            "RETURN count(r) AS n"
        ),
        "next_edges": "MATCH (:Chunk {prototype:$tag})-[r:NEXT]->(:Chunk {prototype:$tag}) RETURN count(r) AS n",
    }
    with config.neo4j_driver() as drv, drv.session(database=config.NEO4J_DATABASE) as session:
        for label, cypher in queries.items():
            record = session.run(cypher, tag=tag, iid=issue_id).single()
            counts[label] = int(record["n"]) if record and record["n"] is not None else 0
    return counts


def _weaviate_overlap(docs: Sequence[str]) -> Dict[str, Any]:
    """
    Read-only Weaviate sanity check: how many of our curated docs exist in the
    'Oxcart' collection (by doc_id). Never writes to Weaviate.
    """
    from weaviate.classes.query import Filter

    overlap: Dict[str, Any] = {"collection": config.OXCART_COLLECTION, "docs_present": {}}
    client = config.weaviate_client()
    try:
        collection = client.collections.get(config.OXCART_COLLECTION)
        total_present = 0
        for doc_id in docs:
            response = collection.aggregate.over_all(
                filters=Filter.by_property("doc_id").equal(doc_id),
                total_count=True,
            )
            n = int(response.total_count or 0)
            overlap["docs_present"][doc_id] = n
            if n > 0:
                total_present += 1
        overlap["docs_with_objects"] = total_present
        overlap["docs_queried"] = len(docs)
    finally:
        client.close()
    return overlap


# --------------------------------------------------------------------------- #
# Sample answer card rendering
# --------------------------------------------------------------------------- #
def _format_answer_card(question: str, answer: Any) -> str:
    """
    Render a retriever answer into a readable card. Tolerant of the exact shape
    returned by retrieve.answer() (dict or object).
    """
    lines: List[str] = []
    lines.append("-" * 70)
    lines.append(f"Q: {question}")
    lines.append("-" * 70)

    data = _as_dict(answer)
    if not data:
        lines.append("(retriever returned no structured payload)")
        lines.append(str(answer))
        return "\n".join(lines)

    # Answer text (try several common key names).
    text = None
    for key in ("answer", "text", "response", "summary", "content"):
        if key in data and data[key]:
            text = data[key]
            break
    if text is None:
        text = str(answer)
    lines.append("Answer:")
    lines.append(str(text).strip())

    # Citations / sources (try several common key names).
    citations = None
    for key in ("citations", "sources", "evidence", "chunks", "hits", "context"):
        if key in data and data[key]:
            citations = data[key]
            break
    if citations:
        lines.append("")
        lines.append("Citations:")
        if isinstance(citations, (list, tuple)):
            for idx, cite in enumerate(citations, 1):
                cd = _as_dict(cite)
                doc = cd.get("doc_id") or cd.get("doc") or cd.get("source") or "?"
                chunk = cd.get("chunk_id") or cd.get("chunk") or ""
                page = cd.get("page") or cd.get("page_number")
                snippet = cd.get("text") or cd.get("snippet") or cd.get("text_original") or ""
                snippet = str(snippet).strip().replace("\n", " ")
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                page_str = f" p.{page}" if page is not None else ""
                lines.append(f"  [{idx}] {doc} {chunk}{page_str}")
                if snippet:
                    lines.append(f"      {snippet}")
        else:
            lines.append(f"  {citations}")

    # Any score / confidence the retriever surfaced.
    for key in ("confidence", "score", "consensus", "sources_count"):
        if key in data:
            lines.append(f"{key}: {data[key]}")

    lines.append("-" * 70)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Pipeline orchestration
# --------------------------------------------------------------------------- #
def run_pipeline(
    docs: Optional[Sequence[str]] = None,
    *,
    skip_sanitize: bool = False,
    skip_domain: bool = False,
    skip_lexical: bool = False,
    skip_link: bool = False,
    questions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Run the prototype end to end and return a structured result dict:
        {
          "env": dict,
          "docs": list[str],
          "steps": list[StepResult],
          "neo4j_counts": dict | None,
          "weaviate_overlap": dict | None,
          "answers": list[(question, payload)],
          "failed": bool,
        }

    This function never raises for an in-step failure; it records it and
    continues so the report can summarize. It DOES propagate import errors for
    missing sibling modules (those are setup errors, not pipeline failures).
    """
    # Resolve curated doc subset. Prefer the canonical list defined by the
    # sanitizer; fall back to the contract's curated subset if unavailable.
    if docs is None:
        docs = _resolve_default_docs()
    docs = list(docs)

    questions = list(questions or SAMPLE_QUESTIONS)

    steps: List[StepResult] = []

    # Step 0: config snapshot (always run; cheap and informative).
    env = config.env_summary()

    # Step 1: sanitize.
    def _do_sanitize() -> Any:
        import sanitize_chunks

        # write_patched() takes a single doc_id; sanitize each curated doc and
        # aggregate the per-doc summary counts for the step report.
        agg = {"total": 0, "kept": 0, "dropped_caption": 0, "figure_noise_stripped": 0, "written": 0}
        for doc_id in docs:
            sanitize_chunks.write_patched(doc_id)
            summary = sanitize_chunks.sanitize_doc(doc_id)["summary"]
            for key in ("total", "kept", "dropped_caption", "figure_noise_stripped"):
                agg[key] += int(summary.get(key, 0))
            agg["written"] += 1
        return agg

    step1 = _run_step("1.sanitize (write_patched)", _do_sanitize, skip_sanitize)
    if step1.ok:
        summary = _as_dict(step1.payload)
        step1.summary = _summarize_counts(
            summary,
            ("total", "kept", "dropped_caption", "figure_noise_stripped", "docs", "chunks", "written"),
        )
    steps.append(step1)

    # Step 2: build domain Scott stamps + illustrations.
    def _do_domain() -> Any:
        import build_domain_scott

        return build_domain_scott.build_domain_scott()

    step2 = _run_step("2.domain (build_domain_scott)", _do_domain, skip_domain)
    if step2.ok:
        step2.summary = _summarize_counts(
            _as_dict(step2.payload),
            ("scott_stamps", "illustrations", "equivalences", "variety_edges", "stamps", "created"),
        )
    steps.append(step2)

    # Step 3: build the lexical graph (Document/Chunk nodes + NEXT).
    def _do_lexical() -> Any:
        import build_lexical_graph

        return build_lexical_graph.build_lexical_graph(docs)

    step3 = _run_step("3.lexical (build_lexical_graph)", _do_lexical, skip_lexical)
    if step3.ok:
        step3.summary = _summarize_counts(
            _stats_dict(step3.payload),
            ("documents", "chunks", "next_edges", "docs", "created"),
        )
    steps.append(step3)

    # Step 4: link lexical chunks to the domain (MENTIONS / MENTIONS_STAMP).
    def _do_link() -> Any:
        import link_lexical_to_domain

        return link_lexical_to_domain.link_lexical_to_domain(docs)

    step4 = _run_step("4.link (link_lexical_to_domain)", _do_link, skip_link)
    if step4.ok:
        step4.summary = _summarize_counts(
            _stats_dict(step4.payload),
            ("chunks_scored", "chunks_linked", "mentions_issue", "mentions_stamp"),
        )
    steps.append(step4)

    # Step 5: retrieval over the sample questions.
    answers: List[Any] = []

    def _do_retrieve() -> Any:
        import retrieve

        local_answers: List[Any] = []
        for question in questions:
            local_answers.append((question, retrieve.answer(question)))
        return local_answers

    step5 = _run_step("5.retrieve (answer)", _do_retrieve, skip=False)
    if step5.ok and step5.payload:
        answers = list(step5.payload)
        step5.summary = f"answered {len(answers)} question(s)"
    steps.append(step5)

    # Live read-only counts for the report (best-effort; failure is non-fatal
    # and reported as a note rather than failing the whole run).
    neo4j_counts: Optional[Dict[str, Any]] = None
    neo4j_error: Optional[str] = None
    try:
        neo4j_counts = _neo4j_counts()
    except BaseException as exc:  # noqa: BLE001
        neo4j_error = repr(exc)

    weaviate_overlap: Optional[Dict[str, Any]] = None
    weaviate_error: Optional[str] = None
    try:
        weaviate_overlap = _weaviate_overlap(docs)
    except BaseException as exc:  # noqa: BLE001
        weaviate_error = repr(exc)

    failed = any((not s.skipped) and (not s.ok) for s in steps)

    return {
        "env": env,
        "docs": docs,
        "questions": questions,
        "steps": steps,
        "neo4j_counts": neo4j_counts,
        "neo4j_error": neo4j_error,
        "weaviate_overlap": weaviate_overlap,
        "weaviate_error": weaviate_error,
        "answers": answers,
        "failed": failed,
    }


def _resolve_default_docs() -> List[str]:
    """Use the sanitizer's FIRST_ISSUE_DOCS if importable; else the contract list."""
    try:
        import sanitize_chunks

        docs = getattr(sanitize_chunks, "FIRST_ISSUE_DOCS", None)
        if docs:
            return list(docs)
    except Exception:  # pragma: no cover - sanitizer may not be importable yet
        pass
    return [
        "OXCART03",
        "OXCART50",
        "OXCART08",
        "OXCART09",
        "OXCART02",
        "OXCART04",
        "OXCART05",
        "OXCART06",
        "OXCART75",
        "OXCART51",
    ]


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #
def render_report(result: Dict[str, Any]) -> str:
    """Render the consolidated VALIDATION REPORT as a single string."""
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("FIRST ISSUE GRAPHRAG — VALIDATION REPORT")
    lines.append("=" * 70)

    # Config snapshot.
    lines.append("")
    lines.append("Config:")
    for key, value in result["env"].items():
        lines.append(f"  {key}: {value}")
    lines.append(f"  curated_docs ({len(result['docs'])}): {', '.join(result['docs'])}")

    # Per-step outcomes.
    lines.append("")
    lines.append("Pipeline steps:")
    for step in result["steps"]:
        lines.append(step.as_line())
        if (not step.skipped) and (not step.ok) and step.error is not None:
            tb = "".join(traceback.format_exception_only(type(step.error), step.error)).strip()
            lines.append(f"         -> {tb}")

    # Live Neo4j counts.
    lines.append("")
    lines.append("Neo4j (prototype-scoped) counts:")
    if result["neo4j_counts"] is not None:
        nc = result["neo4j_counts"]
        lines.append(f"  ScottStamp nodes:      {nc.get('scott_stamp_nodes', '?')}")
        lines.append(f"  Illustration nodes:    {nc.get('illustration_nodes', '?')}")
        lines.append(f"  Document nodes:        {nc.get('document_nodes', '?')}")
        lines.append(f"  Chunk nodes:           {nc.get('chunk_nodes', '?')}")
        lines.append(f"  MENTIONS edges:        {nc.get('mentions_edges', '?')}")
        lines.append(f"  MENTIONS_STAMP edges:  {nc.get('mentions_stamp_edges', '?')}")
        lines.append(f"  HAS_SCOTT_STAMP edges: {nc.get('has_scott_stamp_edges', '?')}")
        lines.append(f"  EQUIVALENT_TO edges:   {nc.get('equivalent_to_edges', '?')}")
        lines.append(f"  NEXT edges:            {nc.get('next_edges', '?')}")
    else:
        lines.append(f"  (unavailable: {result.get('neo4j_error')})")

    # Weaviate overlap.
    lines.append("")
    lines.append("Weaviate overlap (read-only 'Oxcart' collection):")
    if result["weaviate_overlap"] is not None:
        wo = result["weaviate_overlap"]
        lines.append(
            f"  docs with objects: {wo.get('docs_with_objects', '?')}/{wo.get('docs_queried', '?')}"
        )
        for doc_id, n in (wo.get("docs_present") or {}).items():
            lines.append(f"    {doc_id}: {n} object(s)")
    else:
        lines.append(f"  (unavailable: {result.get('weaviate_error')})")

    # One full sample answer card.
    lines.append("")
    lines.append("Sample answer card:")
    if result["answers"]:
        question, payload = result["answers"][0]
        lines.append(_format_answer_card(question, payload))
        if len(result["answers"]) > 1:
            remaining = ", ".join(q for q, _ in result["answers"][1:])
            lines.append(f"(also answered: {remaining})")
    else:
        lines.append("  (no answers produced)")

    # Verdict.
    lines.append("")
    lines.append("=" * 70)
    lines.append("RESULT: " + ("FAILED — see step errors above" if result["failed"] else "OK — all steps succeeded"))
    lines.append("=" * 70)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the First Issue GraphRAG prototype end to end and print a validation report.",
    )
    parser.add_argument(
        "--docs",
        nargs="+",
        default=None,
        help="Doc IDs to process (default: sanitize_chunks.FIRST_ISSUE_DOCS).",
    )
    parser.add_argument("--skip-sanitize", action="store_true", help="Skip step 1 (sanitize).")
    parser.add_argument("--skip-domain", action="store_true", help="Skip step 2 (build domain Scott).")
    parser.add_argument("--skip-lexical", action="store_true", help="Skip step 3 (build lexical graph).")
    parser.add_argument("--skip-link", action="store_true", help="Skip step 4 (link lexical to domain).")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)

    # Print config snapshot up front (step 0), per the contract.
    print("Config (env_summary):")
    for key, value in config.env_summary().items():
        print(f"  {key}: {value}")
    print()

    result = run_pipeline(
        docs=args.docs,
        skip_sanitize=args.skip_sanitize,
        skip_domain=args.skip_domain,
        skip_lexical=args.skip_lexical,
        skip_link=args.skip_link,
    )

    print(render_report(result))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
