"""The Weaviate arms of the eval: keyword, vector, hybrid. Read-only.

Every arm returns passages in rank order as plain dicts:
    {"doc_id", "page", "chunk_id", "chunk_type", "score", "uuid"}
No passage text is returned or stored: results files hold ids, ranks and scores only.
"""

from __future__ import annotations

from typing import Any

import weaviate.classes as wvc

PROPERTIES = ["doc_id", "chunk_id", "page_number", "chunk_type"]


def _hits(objects, score_of) -> list[dict[str, Any]]:
    out = []
    for o in objects or []:
        p = o.properties or {}
        out.append({
            "doc_id": p.get("doc_id"), "page": p.get("page_number"), "chunk_id": p.get("chunk_id"),
            "chunk_type": p.get("chunk_type"), "score": score_of(o), "uuid": str(o.uuid),
        })
    return out


def keyword(coll, question: str, k: int) -> list[dict]:
    """BM25 over the collection's searchable properties (the app's default path)."""
    response = coll.query.bm25(
        query=question, limit=k, return_properties=PROPERTIES,
        return_metadata=wvc.query.MetadataQuery(score=True))
    return _hits(response.objects, lambda o: o.metadata.score)


def vector(coll, question_vector: list[float], k: int, target: str | None = None) -> list[dict]:
    """Nearest passages to a question vector made by the eval."""
    kwargs = {"target_vector": target} if target else {}
    response = coll.query.near_vector(
        near_vector=question_vector, limit=k, return_properties=PROPERTIES,
        return_metadata=wvc.query.MetadataQuery(distance=True), **kwargs)
    return _hits(response.objects, lambda o: None if o.metadata.distance is None else 1.0 - o.metadata.distance)


def hybrid(coll, question: str, question_vector: list[float], alpha: float, k: int,
           target: str | None = None) -> list[dict]:
    """Keyword and vector fused by Weaviate. alpha = weight of the vector side (0.35 in the app today)."""
    kwargs = {"target_vector": target} if target else {}
    response = coll.query.hybrid(
        query=question, vector=question_vector, alpha=alpha, limit=k, return_properties=PROPERTIES,
        return_metadata=wvc.query.MetadataQuery(score=True), **kwargs)
    return _hits(response.objects, lambda o: o.metadata.score)


def all_arms(alphas=(0.25, 0.35, 0.5, 0.75)) -> dict:
    """Name -> callable(coll, question, question_vector, k, target)."""
    arms = {
        "keyword": lambda coll, q, v, k, t: keyword(coll, q, k),
        "vector": lambda coll, q, v, k, t: vector(coll, v, k, t),
    }
    for a in alphas:
        arms[f"hybrid-{a:g}"] = (lambda a: lambda coll, q, v, k, t: hybrid(coll, q, v, a, k, t))(a)
    return arms
