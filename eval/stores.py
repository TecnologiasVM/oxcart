"""Connections for the eval. Read-only use; nothing here prints a credential.

Which Weaviate is used comes from the environment:

    WEAVIATE_URL set          a Weaviate Cloud cluster (with WEAVIATE_API_KEY)
    otherwise                 the instance in oxcart/config.py
                              (WEAVIATE_HOST, WEAVIATE_HTTP_PORT, WEAVIATE_GRPC_PORT, WEAVIATE_API_KEY)
    OXCART_COLLECTION         collection name (default "Oxcart")
    EVAL_VECTOR_NAME          named vector to search (unset = the collection's default vector)

The OpenAI key is never passed to Weaviate from here: the eval makes the question's
embedding itself (eval/embed.py) and sends the vector.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def weaviate_target():
    """Return (client, collection name, vector name or None, label). The caller closes the client."""
    import weaviate
    from weaviate.classes.init import AdditionalConfig, Auth, Timeout

    from oxcart import config

    collection = os.getenv("OXCART_COLLECTION") or config.OXCART_COLLECTION
    vector = os.getenv("EVAL_VECTOR_NAME") or None
    key = os.getenv("WEAVIATE_API_KEY") or config.WEAVIATE_API_KEY
    auth = Auth.api_key(key) if key else None
    url = os.getenv("WEAVIATE_URL")
    if url:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=url, auth_credentials=auth,
            additional_config=AdditionalConfig(timeout=Timeout(init=30, query=60)))
        label = "cloud"
    else:
        client = weaviate.connect_to_local(
            host=config.WEAVIATE_HOST, port=config.WEAVIATE_HTTP_PORT, grpc_port=config.WEAVIATE_GRPC_PORT,
            auth_credentials=auth)
        label = f"{config.WEAVIATE_HOST}:{config.WEAVIATE_HTTP_PORT}"
    return client, collection, vector, label


def data_file(name: str) -> Path:
    """A test-set file: the working copy under local-data/eval/ when there is one, else the published one in eval/data/.

    The working copies are where the generator and the judgments converter write; they can hold
    things that are not published (a judge's wording of the answer). The scores need neither.
    """
    working = REPO / "local-data" / "eval" / name
    return working if working.exists() else REPO / "eval" / "data" / name


def neo4j_session_factory():
    """Return (driver, database). One driver for the whole run; the caller closes it."""
    from oxcart import config

    return config.neo4j_driver(), config.NEO4J_DATABASE
