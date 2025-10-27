# neo4j_index_and_embed.py
# -*- coding: utf-8 -*-
import os, time, argparse
from typing import List, Any
from neo4j import GraphDatabase, basic_auth
from openai import OpenAI
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-...")


print(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

EMBED_MODEL = "text-embedding-3-large"  # 3072 dims
EMBED_DIM   = 3072

def driver():
    return GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))

def debug(msg): print(f"[INDEXER] {msg}", flush=True)

# ---------- Cypher ----------
UNIQUE_ISSUE = """
CREATE CONSTRAINT issue_id_unique IF NOT EXISTS
FOR (i:Issue) REQUIRE i.issue_id IS UNIQUE;
"""

FULLTEXT_IDX = """
CREATE FULLTEXT INDEX issue_text_idx IF NOT EXISTS
FOR (i:Issue)
ON EACH [i.plain_raw_text, i.pictures_raw_text, i.title];
"""

VECTOR_IDX = """
CREATE VECTOR INDEX issue_vec_idx IF NOT EXISTS
FOR (i:Issue) ON (i.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: $dim,
    `vector.similarity_function`: 'cosine'
  }
};
"""

BUILD_CORPUS = """
MATCH (i:Issue)
SET i.search_corpus =
  coalesce(i.title,'') + ' ' +
  coalesce(i.plain_raw_text,'') + ' ' +
  coalesce(i.pictures_raw_text,'');
"""

GET_ISSUES_TO_EMBED = """
MATCH (i:Issue)
WHERE i.search_corpus IS NOT NULL
  AND ($mode = 'missing' AND (i.embedding IS NULL OR size(i.embedding)=0)
       OR $mode = 'all')
RETURN i.issue_id AS issue_id, i.search_corpus AS corpus
ORDER BY i.issue_id
"""

UPSERT_EMBED = """
MATCH (i:Issue {issue_id:$issue_id})
SET i.embedding = $embedding
RETURN i.issue_id AS issue_id
"""

# ---------- OpenAI ----------
def openai_client():
    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-..."):
        raise RuntimeError("OPENAI_API_KEY no configurada.")
    return OpenAI(api_key=OPENAI_API_KEY)

def embed_batch(client: OpenAI, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

# ---------- Index + Embeddings ----------
def create_indexes():
    with driver() as d, d.session() as s:
        debug("Creando constraint único Issue...")
        s.run(UNIQUE_ISSUE)
        debug("Creando índice FULLTEXT issue_text_idx...")
        s.run(FULLTEXT_IDX)
        debug(f"Creando índice VECTOR issue_vec_idx (dim={EMBED_DIM})...")
        s.run(VECTOR_IDX, dim=EMBED_DIM)
        debug("Construyendo i.search_corpus...")
        s.run(BUILD_CORPUS)
    debug("Índices/listo.")

def chunked(lst: List[Any], size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

def generate_embeddings(mode="missing", batch=64, sleep_sec=0.0):
    client = openai_client()
    with driver() as d, d.session() as s:
        rows = s.run(GET_ISSUES_TO_EMBED, mode=mode).data()
        total = len(rows)
        debug(f"Issues a embeddear (mode={mode}): {total}")
        done = 0
        for batch_rows in chunked(rows, batch):
            texts = [r["corpus"] or "" for r in batch_rows]
            ids   = [r["issue_id"] for r in batch_rows]
            vecs  = embed_batch(client, texts)
            for iid, vec in zip(ids, vecs):
                s.run(UPSERT_EMBED, issue_id=iid, embedding=vec)
            done += len(batch_rows)
            debug(f"Embeddings upsert: {done}/{total}")
            if sleep_sec > 0:
                time.sleep(sleep_sec)
    debug("Embeddings listos.")

# ---------- CLI ----------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="One-time: crear índices y generar embeddings en Neo4j")
    p.add_argument("--skip-indexes", action="store_true", help="No crear índices (solo embeddings)")
    p.add_argument("--mode", choices=["missing","all"], default="missing", help="Embeddings a generar")
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--sleep", type=float, default=0.0)
    args = p.parse_args()

    if not args.skip_indexes:
        create_indexes()
    generate_embeddings(mode=args.mode, batch=args.batch, sleep_sec=args.sleep)
