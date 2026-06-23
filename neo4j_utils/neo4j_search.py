# neo4j_search.py
# -*- coding: utf-8 -*-
import os
from typing import List, Dict, Any, Tuple, Optional
from neo4j import GraphDatabase, basic_auth
from openai import OpenAI

from dotenv import load_dotenv

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-...")

EMBED_MODEL   = "text-embedding-3-large"
DEFAULT_TOPK  = 10
DEFAULT_ALPHA = 0.35
DEFAULT_MIN_SCORE = 0.4

def driver():
    return GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

def oai():
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-..."):
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=OPENAI_API_KEY)

# ---------- Cypher (queries) ----------
FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes('issue_text_idx', $q)
YIELD node AS iss, score
RETURN iss.issue_id AS issue_id, score
ORDER BY score DESC
LIMIT $k;
"""

VECTOR_QUERY = """
CALL db.index.vector.queryNodes('issue_vec_idx', $k, $qe)
YIELD node AS iss, score
RETURN iss.issue_id AS issue_id, score
ORDER BY score DESC;
"""

HYBRID_QUERY = """
// Vector
CALL db.index.vector.queryNodes('issue_vec_idx', $k, $qe)
YIELD node AS n1, score AS vscore
WITH collect({id:n1.issue_id, s:vscore}) AS vrows

// Full-text
CALL db.index.fulltext.queryNodes('issue_text_idx', $q)
YIELD node AS n2, score AS fscore
WITH vrows, collect({id:n2.issue_id, s:fscore}) AS frows

WITH vrows, frows,
     CASE WHEN size(vrows)>0 THEN reduce(m=1e9, x IN vrows | CASE WHEN x.s<m THEN x.s ELSE m END) ELSE 0 END AS vmin,
     CASE WHEN size(vrows)>0 THEN reduce(m=-1e9, x IN vrows | CASE WHEN x.s>m THEN x.s ELSE m END) ELSE 1 END AS vmax,
     CASE WHEN size(frows)>0 THEN reduce(m=1e9, x IN frows | CASE WHEN x.s<m THEN x.s ELSE m END) ELSE 0 END AS fmin,
     CASE WHEN size(frows)>0 THEN reduce(m=-1e9, x IN frows | CASE WHEN x.s>m THEN x.s ELSE m END) ELSE 1 END AS fmax,
     $alpha AS a

WITH
  [x IN vrows | {id:x.id, sv: CASE WHEN vmax=vmin THEN 1.0 ELSE (x.s - vmin)/(vmax - vmin) END}] AS vn,
  [y IN frows | {id:y.id, sf: CASE WHEN fmax=fmin THEN 1.0 ELSE (y.s - fmin)/(fmax - fmin) END}] AS fn,
  a

WITH vn + fn AS allrows, a
UNWIND allrows AS r
WITH r.id AS iid,
     max(coalesce(r.sv,0.0)) AS sv,
     max(coalesce(r.sf,0.0)) AS sf,
     a
WITH iid, a*sv + (1.0-a)*sf AS hybrid
ORDER BY hybrid DESC
LIMIT $k

MATCH (iss:Issue {issue_id:iid})
RETURN iss.issue_id AS issue_id, hybrid AS score
ORDER BY score DESC;
"""

EXPAND_GRAPH = """
UNWIND $issue_ids AS iid
MATCH (iss:Issue {issue_id:iid})
OPTIONAL MATCH p1 = (iss)-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH p2 = (s)-[:HAS_VARIETY]->(v:Variety)
OPTIONAL MATCH p3 = (s)-[:USES_PLATE]->(pl:Plate)
OPTIONAL MATCH ppos = (v)-[:AT_POSITION]->(pp:PlatePosition)
OPTIONAL MATCH p4 = (iss)-[:PRINTED_BY|HAS_DOCUMENT|HAS_PRODUCTION_ORDER
                     |HAS_REMAINDERS|HAS_PROOF|HAS_SPECIMEN|HAS_ESSAY]->(d)
OPTIONAL MATCH p5 = (d)-[:SIGNED_BY|INCLUDES|SOLD_TO]->(m)
WITH iss, [p IN [p1,p2,p3,ppos,p4,p5] WHERE p IS NOT NULL] AS paths
WITH iss, apoc.coll.flatten(paths) AS ps
UNWIND ps AS p
RETURN p
LIMIT $limit;
"""

SUMMARY = """
UNWIND $issue_ids AS iid
MATCH (iss:Issue {issue_id:iid})
OPTIONAL MATCH (iss)-[:HAS_STAMP]->(s:Stamp)
OPTIONAL MATCH (s)-[:HAS_VARIETY]->(v:Variety)
RETURN iss.issue_id AS issue_id,
       collect(DISTINCT s.catalog_no) AS stamps,
       collect(DISTINCT v.suffix)     AS varieties
ORDER BY issue_id;
"""

# ---------- Helpers ----------
def embed_query(text: str):
    emb = oai().embeddings.create(model=EMBED_MODEL, input=[text]).data[0].embedding
    return emb

def fulltext(q: str, k: int):
    with driver() as d, d.session() as s:
        return s.run(FULLTEXT_QUERY, q=q, k=k).data()

def vector(text: str, k: int):
    qe = embed_query(text)
    with driver() as d, d.session() as s:
        return s.run(VECTOR_QUERY, qe=qe, k=k).data()

def hybrid(q: str, text: str, alpha: float, k: int):
    qe = embed_query(text)
    with driver() as d, d.session() as s:
        return s.run(HYBRID_QUERY, q=q, qe=qe, alpha=alpha, k=k).data()

def expand(issue_ids: List[str], limit_paths: int = 2000) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    with driver() as d, d.session() as s:
        paths = s.run(EXPAND_GRAPH, issue_ids=issue_ids, limit=limit_paths).data()
        table = s.run(SUMMARY, issue_ids=issue_ids).data()
        return paths, table

def _filter_by_score(rows: List[Dict[str, Any]], min_score: Optional[float]) -> List[Dict[str, Any]]:
    """Return only rows whose score is >= min_score."""
    if min_score is None:
        return rows
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        score = row.get("score")
        if isinstance(score, (int, float)) and score >= min_score:
            filtered.append(row)
    return filtered

def run_search(
    mode: str,
    *,
    q: Optional[str] = None,
    text: Optional[str] = None,
    alpha: float = DEFAULT_ALPHA,
    k: int = DEFAULT_TOPK,
    include_graph: bool = False,
    graph_limit: int = 2000,
    min_score: Optional[float] = DEFAULT_MIN_SCORE,
) -> Dict[str, Any]:
    """
    Execute the requested search and return a dictionary with the results.
    Designed to be consumed from other modules without relying on argparse.
    """
    mode_norm = mode.lower()

    if mode_norm == "fulltext":
        if not q:
            raise ValueError("Search mode 'fulltext' requires parameter 'q'.")
        rows = fulltext(q, k)
        filtered = _filter_by_score(rows, min_score)
        return {"mode": "fulltext", "results": filtered}

    if mode_norm == "vector":
        if not text:
            raise ValueError("Search mode 'vector' requires parameter 'text'.")
        rows = vector(text, k)
        filtered = _filter_by_score(rows, min_score)
        return {"mode": "vector", "results": filtered}

    if mode_norm == "hybrid":
        if not q or not text:
            raise ValueError("Search mode 'hybrid' requires parameters 'q' and 'text'.")
        rows = hybrid(q, text, alpha, k)
        filtered = _filter_by_score(rows, min_score)
        payload: Dict[str, Any] = {"mode": "hybrid", "results": filtered}
        if include_graph and filtered:
            ids = [r.get("issue_id") for r in filtered if r.get("issue_id")]
            if ids:
                paths, table = expand(ids, limit_paths=graph_limit)
                payload["paths"] = paths
                payload["summary"] = table
        return payload

    raise ValueError(f"Unsupported search mode: {mode}")

def build_issue_graph_cypher(issues) -> str:
    """
    Given a list of issue identifiers (either ['CR-...', ...] or
    [{'issue_id': 'CR-...', 'score': ...}, ...]) returns a Cypher query
    for Neo4j (new syntax, no deprecation warnings).
    """
    # Extract ids
    def _iid(x):
        return x if isinstance(x, str) else x.get("issue_id")
    issue_ids = [iid for iid in map(_iid, issues) if iid]

    if not issue_ids:
        raise ValueError("No issue_ids provided.")

    # Quote for Cypher
    ids_literal = ", ".join(f"'{iid}'" for iid in issue_ids)

    cypher = f"""
            WITH [{ids_literal}] AS issue_ids
            UNWIND issue_ids AS issue_id
            MATCH (iss:Issue {{issue_id: issue_id}})

            // Core one-hop from Issue (updated and deprecation-free)
            OPTIONAL MATCH p_issue =
            (iss)-[:PRINTED_BY|AUTHORIZED_BY|HAS_PLATE|HAS_STAMP|HAS_PROOF
                    |HAS_PRODUCTION_ORDER|HAS_REMAINDERS|HAS_SPECIMEN|HAS_ESSAY]->(n)

            // LegalAct and officials
            OPTIONAL MATCH p_legal = (iss)-[:AUTHORIZED_BY]->(la:LegalAct)-[:SIGNED_BY]->(ofc:Person)

            // Stamps and neighborhood
            OPTIONAL MATCH (iss)-[:HAS_STAMP]->(st:Stamp)
            OPTIONAL MATCH p_stamp_neigh = (st)-[:USES_PLATE|HAS_VARIETY|OVERPRINTED_ON]-(x)
            OPTIONAL MATCH p_var_pos = (st)-[:HAS_VARIETY]->(v:Variety)-[:AT_POSITION]->(pp:PlatePosition)
            OPTIONAL MATCH p_over_base = (st)-[:OVERPRINTED_ON]->(base:Stamp)
            OPTIONAL MATCH p_plate = (st)-[:USES_PLATE]->(pl:Plate)

            // Proofs
            OPTIONAL MATCH p_proofs = (iss)-[:HAS_PROOF]->(pr:Proof)

            // Production orders and remainders
            OPTIONAL MATCH p_po = (iss)-[:HAS_PRODUCTION_ORDER]->(po:ProductionOrder)-[:INCLUDES]->(q:Quantity)
            OPTIONAL MATCH p_rem = (iss)-[:HAS_REMAINDERS]->(rem:RemaindersEvent)-[:INCLUDES]->(rq:Quantity)
            OPTIONAL MATCH p_sold = (rem)-[:SOLD_TO]->(buyer:Person)

            // Essays, provenance, and bibliography
            OPTIONAL MATCH p_essay = (iss)-[:HAS_ESSAY]->(es:Essay)
            OPTIONAL MATCH p_prov = (es)-[:PROVENANCE|EX_PROVENANCE]->(prov)
            OPTIONAL MATCH p_cite = (es)-[:CITED_IN]->(br:BiblioRef)

            WITH
            collect(p_issue) + collect(p_legal) + collect(p_stamp_neigh) + collect(p_var_pos) +
            collect(p_over_base) + collect(p_plate) + collect(p_proofs) + collect(p_po) +
            collect(p_rem) + collect(p_sold) + collect(p_essay) + collect(p_prov) + collect(p_cite) AS paths
            UNWIND paths AS p
            WITH DISTINCT p WHERE p IS NOT NULL
            RETURN p
            LIMIT 10000
            """.strip()

    return cypher

def main(
    mode: str = "fulltext",
    *,
    q: Optional[str] = None,
    text: Optional[str] = None,
    alpha: float = DEFAULT_ALPHA,
    k: int = DEFAULT_TOPK,
    include_graph: bool = False,
    graph_limit: int = 2000,
    min_score: Optional[float] = DEFAULT_MIN_SCORE,
) -> Dict[str, Any]:
    """
    Optional entry point for quick local tests.
    Adjust the arguments when calling main(...) or set environment variables
    such as SEARCH_MODE, SEARCH_Q, etc., before running the file.
    """
    result = run_search(
        mode,
        q=q,
        text=text,
        alpha=alpha,
        k=k,
        include_graph=include_graph,
        graph_limit=graph_limit,
        min_score=min_score,
    )

    print(f"\n== {result['mode'].upper()} ==")
    for row in result["results"]:
        print(row)

    # Capture issues so we can feed them into the graph builder
    issues = result["results"]

    #print("\nCypher Generation:")
    # output_cypher = build_issue_graph_cypher(issues)
    #print(output_cypher)
    

    return issues

if __name__ == "__main__":
    # Override these defaults by editing the main() call or setting environment variables.
    search_mode = os.getenv("SEARCH_MODE", "hybrid")

    # Demonstration fallback based on real examples from the Mena catalog.
    lucene_query =  "+((snake* OR serpiente* OR serpents OR cobra* OR viper* OR boa* OR piton* OR pitón* OR culebra* OR culebr*)) OR ((snake* OR serpiente* OR serpents OR cobra* OR viper* OR rattlesnake* OR python* OR piton* OR pitón* OR culebra* OR culebr*) OR (reptile*))"
    user_query = "Tell me all about snake stamps of costa rica"


    search_q = lucene_query
    search_text = user_query

    try:
        search_alpha = float(os.getenv("SEARCH_ALPHA", str(DEFAULT_ALPHA)))
    except (TypeError, ValueError):
        search_alpha = DEFAULT_ALPHA

    try:
        search_k = int(os.getenv("SEARCH_TOPK", str(DEFAULT_TOPK)))
    except (TypeError, ValueError):
        search_k = DEFAULT_TOPK

    include_graph = os.getenv("SEARCH_INCLUDE_GRAPH", "false").lower() in {"1", "true", "yes"}

    try:
        search_min_score = float(os.getenv("SEARCH_MIN_SCORE", str(DEFAULT_MIN_SCORE)))
    except (TypeError, ValueError):
        search_min_score = DEFAULT_MIN_SCORE

    main(
        mode=search_mode,
        q=search_q,
        text=search_text,
        alpha=search_alpha,
        k=search_k,
        include_graph=include_graph,
        min_score=search_min_score,
    )
