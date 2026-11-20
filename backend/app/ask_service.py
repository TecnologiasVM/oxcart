"""The question path: one question in, the evidence out. Retrieval only, no written answer.

    1. embed the question            (OpenAI, from this process; never through the vector store)
    2. catalogue lookup              (the graph: vector index over issues, or full-text without an embedding)
    3. literature search             (the vector store: near_vector, or bm25 without an embedding)

Steps 2 and 3 run side by side. Each can fail on its own; the answer says which mode
produced each block (`mode`), and a block that could not be produced says "unavailable"
instead of failing the whole question. How each mode scored is in EVALUATION.md.

The first question after a start used to pay for opening the literature client and the
first connection to the embedding service. Both are now opened as the process starts, in
the background, as the graph link is (graph_link.py); the health route reports where each
one is.

The three steps are plain callables kept on ``AskDeps`` so tests replace them with fakes.
Logs carry error CLASS names only: never a question, a key, an address or a store's message.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app import settings
from app.graph_link import GraphLink, Unavailable  # noqa: F401  (Unavailable is this module's error too)

from oxcart import config

log = logging.getLogger("oxcart.ask")

PASSAGE_PROPERTIES = ["doc_id", "page_number", "chunk_type", "text", "text_original"]

# Shown on the page as things to try. From the published test set (eval/data).
EXAMPLES = [
    {"lang": "es", "question": "¿Por qué se resellaron sellos con la palabra \"Guanacaste\" en 1885?"},
    {"lang": "en", "question": "Who printed Costa Rica's first issue of 1863, and where?"},
    {"lang": "es", "question": "¿Qué sellos se emitieron por el vuelo de Lindbergh a Costa Rica en 1928?"},
    {"lang": "en", "question": "When was the Bernardo Soto 1889 issue placed on sale?"},
    {"lang": "es", "question": "¿Qué muestra la emisión de la Isla del Coco de 1936, y por qué se emitió?"},
    {"lang": "en", "question": "What were the first airmail stamps of Costa Rica, and which flights did they serve?"},
]


@dataclass
class AskDeps:
    embed: Callable[[str], Optional[list]]
    lookup: Callable[[str, Optional[list]], list]
    search: Callable[[str, Optional[list]], list]
    verify_human: Callable[[str], str]
    close: Callable[[], None] = lambda: None
    warm: Callable[[], None] = lambda: None          # start opening, in the background, what the first question needs
    states: Callable[[], dict] = lambda: {"literature": "not started", "embedding": "not started"}   # for the health route


class WarmedInBackground:
    """A step that can open its connection before the first question asks for it.

    ``state`` is what the health route reports: ``not started`` (nothing was opened yet),
    ``connecting``, ``connected`` or ``unavailable``. A later question that succeeds or
    fails updates it.
    """

    state = "not started"

    def warm(self) -> bool:
        raise NotImplementedError

    def warm_in_background(self) -> threading.Thread:
        self.state = "connecting"            # set here, not in the thread: the health route may be asked first
        thread = threading.Thread(target=self.warm, name=f"{type(self).__name__.lower()}-warm-up", daemon=True)
        thread.start()
        return thread


# --------------------------------------------------------------------------- 1. embedding
class Embedder(WarmedInBackground):
    """The question's embedding, with a small cache. Returns None when it cannot be made.

    One HTTP client for the process, so a question can reuse a connection that is already
    open instead of opening its own. An idle connection is kept for a minute.
    """

    URL = "https://api.openai.com/v1/embeddings"
    KEEP_ALIVE_SECONDS = 60.0
    WARM_UP_TEXT = "warm-up"                 # the one tiny embedding made at startup; its vector is not kept

    def __init__(self, cache_size: int = 256):
        self._cache: "collections.OrderedDict[str, list]" = collections.OrderedDict()
        self._size = cache_size
        self._lock = threading.Lock()
        self._client = None

    def _http(self):
        with self._lock:
            if self._client is None:
                import httpx

                self._client = httpx.Client(timeout=settings.EMBED_TIMEOUT_SECONDS,
                                            limits=httpx.Limits(keepalive_expiry=self.KEEP_ALIVE_SECONDS))
            return self._client

    def _request(self, key: str, text: str) -> list:
        response = self._http().post(self.URL, headers={"Authorization": f"Bearer {key}"},
                                     json={"model": settings.EMBEDDING_MODEL, "input": text})
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    def warm(self) -> bool:
        """Open the connection with one tiny embedding. Meant for a thread."""
        key = config.OPENAI_API_KEY
        if not key:
            self.state = "not configured"
            return False
        for attempt in (1, 2):
            try:
                self._request(key, self.WARM_UP_TEXT)
                self.state = "connected"
                log.info("embedding connected after %d attempt(s)", attempt)
                return True
            except Exception as exc:
                log.warning("embedding warm-up failed (attempt %d): %s", attempt, type(exc).__name__)
        self.state = "unavailable"
        return False

    def close(self) -> None:
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def __call__(self, question: str) -> Optional[list]:
        key = config.OPENAI_API_KEY
        if not key:
            return None
        with self._lock:
            if question in self._cache:
                self._cache.move_to_end(question)
                return self._cache[question]
        for _attempt in (1, 2):
            try:
                vector = self._request(key, question)
                with self._lock:
                    self._cache[question] = vector
                    while len(self._cache) > self._size:
                        self._cache.popitem(last=False)
                self.state = "connected"
                return vector
            except Exception as exc:
                log.warning("embedding failed: %s", type(exc).__name__)
        self.state = "unavailable"
        return None


# --------------------------------------------------------------------------- 2. catalogue
def make_lookup(link: GraphLink) -> Callable[[str, Optional[list]], list]:
    """The catalogue lookup through the process's graph link: a refused connection is tried
    again inside the question's budget (graph_link.py) before the block is unavailable."""
    def lookup(question: str, vector: Optional[list]) -> list:
        from oxcart import catalogue_lookup

        return link.read(lambda session: catalogue_lookup.lookup(session, question, k=settings.ASK_ISSUES, question_vector=vector))

    return lookup


# --------------------------------------------------------------------------- 3. literature
class Literature(WarmedInBackground):
    """One Weaviate client for the process. The OpenAI key is never given to it."""

    def __init__(self) -> None:
        self._client = None
        self._lock = threading.Lock()

    def warm(self) -> bool:
        """Open the client: that, not the search, is what the first question waited for.
        Two tries, as a search has. A question that arrives meanwhile waits for this same
        client instead of opening a second one. Meant for a thread."""
        for attempt in (1, 2):
            try:
                self._get()
                self.state = "connected"
                log.info("literature connected after %d attempt(s)", attempt)
                return True
            except Exception as exc:
                log.warning("literature warm-up failed (attempt %d): %s", attempt, type(exc).__name__)
        self.state = "unavailable"
        return False

    def _connect(self):
        import weaviate
        from weaviate.classes.init import AdditionalConfig, Auth, Timeout

        auth = Auth.api_key(config.WEAVIATE_API_KEY) if config.WEAVIATE_API_KEY else None
        extra = AdditionalConfig(timeout=Timeout(init=15, query=10, insert=10))
        if settings.WEAVIATE_URL:
            return weaviate.connect_to_weaviate_cloud(cluster_url=settings.WEAVIATE_URL, auth_credentials=auth,
                                                      additional_config=extra)
        return weaviate.connect_to_local(host=config.WEAVIATE_HOST, port=config.WEAVIATE_HTTP_PORT,
                                         grpc_port=config.WEAVIATE_GRPC_PORT, auth_credentials=auth,
                                         additional_config=extra)

    def _get(self):
        with self._lock:
            if self._client is None:
                self._client = self._connect()
            return self._client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None

    def search(self, question: str, vector: Optional[list]) -> list:
        from weaviate.classes.query import MetadataQuery

        last = "unknown"
        for attempt in (1, 2):
            try:
                collection = self._get().collections.get(config.OXCART_COLLECTION)
                if vector:
                    result = collection.query.near_vector(
                        near_vector=vector, limit=settings.ASK_PASSAGES, target_vector=settings.VECTOR_NAME or None,
                        return_properties=PASSAGE_PROPERTIES, return_metadata=MetadataQuery(distance=True))
                else:
                    result = collection.query.bm25(
                        query=question, limit=settings.ASK_PASSAGES,
                        return_properties=PASSAGE_PROPERTIES, return_metadata=MetadataQuery(score=True))
                passages = []
                for o in result.objects:
                    p = o.properties
                    score = (1.0 - o.metadata.distance) if vector and o.metadata.distance is not None else o.metadata.score
                    passages.append({"doc_id": p.get("doc_id"), "page": p.get("page_number"),
                                     "chunk_type": p.get("chunk_type"),
                                     "text": p.get("text_original") or p.get("text") or "",
                                     "score": round(float(score), 4) if score is not None else None})
                self.state = "connected"
                return passages
            except Exception as exc:
                last = type(exc).__name__
                log.warning("literature search failed (attempt %d): %s", attempt, last)
                self.close()        # a broken connection is not kept
        self.state = "unavailable"
        raise Unavailable(last)


# --------------------------------------------------------------------------- the answer
def clip(text: str, limit: int) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "…", True


def _without_vectors(value: Any) -> Any:
    """Drop any key that could hold an embedding, at any depth."""
    if isinstance(value, dict):
        return {k: _without_vectors(v) for k, v in value.items() if "embed" not in k.lower() and "vector" not in k.lower()}
    if isinstance(value, list):
        return [_without_vectors(v) for v in value]
    return value


def answer(question: str, deps: AskDeps) -> dict:
    """Run the three steps. Raises Unavailable only when neither store answered."""
    started = time.time()
    timings: dict[str, int] = {}

    t0 = time.time()
    try:
        vector = deps.embed(question)
    except Exception as exc:
        log.warning("embedding failed: %s", type(exc).__name__)
        vector = None
    timings["embedding_ms"] = int((time.time() - t0) * 1000)
    if vector:
        embedding_mode = "ok"
    else:
        embedding_mode = "failed" if config.OPENAI_API_KEY else "not configured"

    def timed(name: str, fn: Callable[[], list]) -> tuple[Optional[list], Optional[str]]:
        t = time.time()
        try:
            return fn(), None
        except Unavailable as exc:
            return None, str(exc)
        except Exception as exc:
            log.warning("%s failed: %s", name, type(exc).__name__)
            return None, type(exc).__name__
        finally:
            timings[f"{name}_ms"] = int((time.time() - t) * 1000)

    with ThreadPoolExecutor(max_workers=2) as pool:
        catalogue_future = pool.submit(timed, "catalogue", lambda: deps.lookup(question, vector))
        literature_future = pool.submit(timed, "literature", lambda: deps.search(question, vector))
        issues, catalogue_error = catalogue_future.result()
        passages, literature_error = literature_future.result()

    if issues is None and passages is None:
        raise Unavailable("both stores")

    shown = []
    for p in passages or []:
        text, clipped = clip(p.get("text", ""), settings.ASK_TEXT_LIMIT)
        shown.append({"doc_id": p.get("doc_id"), "page": p.get("page"), "chunk_type": p.get("chunk_type"),
                      "text": text, "clipped": clipped, "score": p.get("score")})
    timings["total_ms"] = int((time.time() - started) * 1000)
    return {
        "question": question,
        "mode": {
            "embedding": embedding_mode,
            "catalogue": "unavailable" if issues is None else ("vector index" if vector else "full-text index"),
            "literature": "unavailable" if passages is None else ("vector" if vector else "keyword"),
        },
        "issues": _without_vectors(issues or [])[: settings.ASK_ISSUES],
        "passages": shown[: settings.ASK_PASSAGES],
        "timings": timings,
    }


def default_deps(link: GraphLink) -> AskDeps:
    from app import public_guard

    embedder, literature = Embedder(), Literature()

    def warm() -> None:
        literature.warm_in_background()
        embedder.warm_in_background()

    def close() -> None:
        literature.close()
        embedder.close()

    return AskDeps(embed=embedder, lookup=make_lookup(link), search=literature.search,
                   verify_human=public_guard.verify_turnstile, close=close, warm=warm,
                   states=lambda: {"literature": literature.state, "embedding": embedder.state})
