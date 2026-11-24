"""The question path: one question in, the evidence out. Retrieval only, no written answer.

    1. embed the question            (OpenAI, from this process; never through the vector store)
    2. catalogue lookup              (the graph: vector index over issues, or full-text without an embedding)
    3. literature search             (the vector store: near_vector, or bm25 without an embedding)

Steps 2 and 3 run side by side. Each can fail on its own; the answer says which mode
produced each block (`mode`), and a block that could not be produced says "unavailable"
instead of failing the whole question. A store that has not answered by its deadline
(ASK_STORE_SECONDS) counts as unavailable too: the other's evidence is not held back by it.
How each mode scored is in EVALUATION.md.

**The literature in both languages (multi-query retrieval).** The publications are in Spanish and in
English, and a question's vector brings back passages of its own language almost only. When the caller
also gives the question in the other language (``also``; the written answer's first step makes it,
answer_graph.contextualize), both texts are embedded in one request and the literature is searched once
per text, side by side. The two lists are joined by reciprocal rank fusion (``fuse``): a passage scores
1 / (RRF_K + its rank) in each list that holds it, the scores are added, and a passage both lists hold
is kept once, by its id in the store. When one of the two searches fails, the other's list is used
alone. The catalogue lookup keeps the question's own text and vector. Without ``also`` (POST /api/ask,
or a rewriting call that failed or was late) there is one search, as before.

The first question after a start used to pay for opening the literature client and the
first connection to the embedding service. Both are now opened as the process starts, in
the background, as the graph link is (graph_link.py); the health route reports where each
one is.

The three steps are plain callables kept on ``AskDeps`` so tests replace them with fakes.
Logs carry error CLASS names only: never a question, a key, an address or a store's message.
"""

from __future__ import annotations

import collections
import hashlib
import logging
import os
import re
import threading
import time
import unicodedata
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app import figures, settings
from app.graph_link import GraphLink, Refused, Unavailable  # noqa: F401  (Unavailable is this module's error too)
from app.passage_text import tidy

from oxcart import config, language

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
    search: Callable[..., list]                       # (text, vector, limit=None) -> passages, best first
    verify_human: Callable[[str], str]
    # Several texts in one request: [vector or None, ...] in the texts' order. None: ``embed`` once per text.
    embed_all: Optional[Callable[[list], list]] = None
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
        # The last vectors, so a repeated question is not embedded twice. They are kept under a
        # digest of the question, keyed with a value made at start and held nowhere else: the
        # text of a question does not stay in this process after its request.
        # The page's privacy paragraph names this size (256): change both together.
        self._cache: "collections.OrderedDict[bytes, list]" = collections.OrderedDict()
        self._digest_key = os.urandom(32)
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
        return self._request_all(key, [text])[0]

    def _request_all(self, key: str, texts: list) -> list:
        """One request for all the texts; their vectors in the texts' order."""
        response = self._http().post(self.URL, headers={"Authorization": f"Bearer {key}"},
                                     json={"model": settings.EMBEDDING_MODEL, "input": texts if len(texts) > 1 else texts[0]})
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda row: row.get("index", 0))
        if len(rows) != len(texts):
            raise ValueError("embeddings")
        return [row["embedding"] for row in rows]

    def _slot(self, question: str) -> bytes:
        return hashlib.blake2b(question.encode("utf-8"), key=self._digest_key, digest_size=16).digest()

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
        return self.all([question])[0]

    def all(self, texts: list) -> list:
        """The vectors of several texts, in their order, from ONE request for those not in the cache (the
        question and its other-language text travel together). A text whose vector cannot be made gets None."""
        key = config.OPENAI_API_KEY
        if not key:
            return [None] * len(texts)
        slots = [self._slot(text) for text in texts]
        found: dict = {}
        with self._lock:
            for slot in slots:
                if slot in self._cache:
                    self._cache.move_to_end(slot)
                    found[slot] = self._cache[slot]
        missing = [(slot, text) for slot, text in dict(zip(slots, texts)).items() if slot not in found]
        if missing:
            for _attempt in (1, 2):
                try:
                    vectors = self._request_all(key, [text for _, text in missing])
                    with self._lock:
                        for (slot, _), vector in zip(missing, vectors):
                            self._cache[slot] = found[slot] = vector
                        while len(self._cache) > self._size:
                            self._cache.popitem(last=False)
                    self.state = "connected"
                    break
                except Exception as exc:
                    log.warning("embedding failed: %s", type(exc).__name__)
            else:
                self.state = "unavailable"
        return [found.get(slot) for slot in slots]


# --------------------------------------------------------------------------- 2. catalogue
def make_lookup(link: GraphLink) -> Callable[[str, Optional[list]], list]:
    """The catalogue lookup through the process's graph link: a refused connection is tried
    again inside the question's budget (graph_link.py) before the block is unavailable."""
    def lookup(question: str, vector: Optional[list]) -> list:
        from oxcart import catalogue_lookup

        def read(short: bool) -> list:
            more = {"use_short": True} if short else {}
            return link.read(lambda session: catalogue_lookup.lookup(
                session, question, k=settings.ASK_ISSUES, question_vector=vector, **more))

        if not (settings.ASK_SHORT_VECTOR and vector):
            return read(False)
        try:
            return read(True)
        except Refused:
            # A query the graph refuses, not a lost connection: the setting is on and the graph does not
            # hold the short vector index. The lookup of today still answers; the log says why.
            log.warning("short vector index not usable: catalogue lookup without it")
            return read(False)

    return lookup


# --------------------------------------------------------------------------- 3. literature
class Literature(WarmedInBackground):
    """One Weaviate client for the process. The OpenAI key is never given to it.

    A search that fails retires the client it used, so the next search opens a new one; a client that
    another search is still using is closed only when that search gives it back. Each client has a
    generation, so a failure retires only the client it happened on, never one made since. Any error
    retires the client: the client's errors do not tell a lost connection from a refused query by their
    class (a query error can carry either), so a failure is never taken for a query the store would refuse
    again on a sound connection."""

    def __init__(self) -> None:
        self._client = None
        self._generation = 0                 # of the current client
        self._borrowed: dict = {}            # generation -> searches using that client now
        self._retired: dict = {}             # generation -> a retired client, closed when nobody uses it
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

    def _current(self):
        """Under the lock: the current client, opened when there is none."""
        if self._client is None:
            self._client = self._connect()
            self._generation += 1
        return self._client

    def _get(self):
        with self._lock:
            return self._current()

    def _borrow(self) -> tuple:
        """(generation, client) for one search; given back with ``_give_back``."""
        with self._lock:
            client = self._current()
            self._borrowed[self._generation] = self._borrowed.get(self._generation, 0) + 1
            return self._generation, client

    def _give_back(self, generation: int, failed: bool) -> None:
        """A search is done with its client. When it failed and that client is still the current one, the
        client is retired. A retired client is closed when its last search gives it back."""
        closing = None
        with self._lock:
            left = self._borrowed.get(generation, 1) - 1
            if left > 0:
                self._borrowed[generation] = left
            else:
                self._borrowed.pop(generation, None)
            if failed and generation == self._generation and self._client is not None:
                self._retired[generation], self._client = self._client, None
            if left <= 0 and generation in self._retired:
                closing = self._retired.pop(generation)
        if closing is not None:
            try:
                closing.close()
            except Exception:
                pass

    def close(self) -> None:
        """At shutdown: every client, in use or not."""
        with self._lock:
            clients = [c for c in [self._client, *self._retired.values()] if c is not None]
            self._client, self._retired, self._borrowed = None, {}, {}
        for client in clients:
            try:
                client.close()
            except Exception:
                pass

    def search(self, question: str, vector: Optional[list], limit: Optional[int] = None) -> list:
        """The nearest passages to one text, best first: at most ``limit`` (ASK_PASSAGES when not given)."""
        from weaviate.classes.query import MetadataQuery

        limit = limit or settings.ASK_PASSAGES
        last = "unknown"
        for attempt in (1, 2):
            try:
                generation, client = self._borrow()
            except Exception as exc:                        # the client could not be opened: nothing was borrowed
                last = type(exc).__name__
                log.warning("literature search failed (attempt %d): %s", attempt, last)
                continue
            failed = True
            try:
                collection = client.collections.get(config.OXCART_COLLECTION)
                if vector:
                    result = collection.query.near_vector(
                        near_vector=vector, limit=limit, target_vector=settings.VECTOR_NAME or None,
                        return_properties=PASSAGE_PROPERTIES, return_metadata=MetadataQuery(distance=True))
                else:
                    result = collection.query.bm25(
                        query=question, limit=limit,
                        return_properties=PASSAGE_PROPERTIES, return_metadata=MetadataQuery(score=True))
                passages = []
                for o in result.objects:
                    p = o.properties
                    score = (1.0 - o.metadata.distance) if vector and o.metadata.distance is not None else o.metadata.score
                    passages.append({"id": str(o.uuid) if getattr(o, "uuid", None) else None,
                                     "doc_id": p.get("doc_id"), "page": p.get("page_number"),
                                     "chunk_type": p.get("chunk_type"),
                                     "text": p.get("text_original") or p.get("text") or "",
                                     "score": round(float(score), 4) if score is not None else None})
                failed = False
                self.state = "connected"
                return passages
            except Exception as exc:
                last = type(exc).__name__
                log.warning("literature search failed (attempt %d): %s", attempt, last)
            finally:
                self._give_back(generation, failed)         # a failed search retires its own client, no other
        self.state = "unavailable"
        raise Unavailable(last)


# --------------------------------------------------------------------------- the answer
def clip(text: str, limit: int) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "…", True


_TERM = re.compile(r"[^\W\d_]{4,}|\d{2,}")
# Words that are in every question or every passage of this collection: they tell stretches apart badly.
_COMMON = frozenset("""
what when where which whom whose were with from that this these those have does about there their
como cual cuales cuando donde quien quienes para sobre entre desde hasta esta este estos estas fueron
costa rica rican stamp stamps issue issues sello sellos emision emisiones costarricense costarricenses
""".split())
_WINDOWS = 400      # at most this many stretches of one passage are compared


def _terms(text: str) -> set:
    """Words of four letters or more, and numbers: lower case, accents removed, the common ones left out."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return set(_TERM.findall(plain)) - _COMMON


def excerpt(text: str, question: str, limit: int) -> tuple[str, bool]:
    """At most `limit` characters of a passage: the stretch that shares the most words with the question.

    No model: words are compared as written, so a question in one language finds nothing in a
    passage in the other, and then the passage's start is shown, as `clip` does. That is why the
    caller gives the question's text in the passage's own language when it has it (`wanted_for`).
    The start is also kept whenever it shares as many words as any other stretch. Otherwise the stretch is
    the middle one of the first run of best stretches, so the shared words sit inside it and
    not at its edge. A stretch starts at a word.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    wanted = _terms(question)
    starts = [0] + [m.start() for m in re.finditer(r"(?<=\s)\S", text) if m.start() + limit <= len(text)]
    starts = starts[:: max(1, len(starts) // _WINDOWS)] + [len(text) - limit]
    best_start = 0
    if wanted:
        shared = [len(wanted & _terms(text[start:start + limit])) for start in starts]
        best = max(shared)
        if shared[0] < best:
            first = shared.index(best)
            last = first
            while last + 1 < len(shared) and shared[last + 1] == best:
                last += 1
            best_start = starts[(first + last) // 2]
    stretch = text[best_start:best_start + limit].strip()
    return ("…" if best_start > 0 else "") + stretch + ("…" if best_start + limit < len(text) else ""), True


def _without_vectors(value: Any) -> Any:
    """Drop any key that could hold an embedding, at any depth."""
    if isinstance(value, dict):
        return {k: _without_vectors(v) for k, v in value.items() if "embed" not in k.lower() and "vector" not in k.lower()}
    if isinstance(value, list):
        return [_without_vectors(v) for v in value]
    return value


# --------------------------------------------------------------------------- two lists into one
RRF_K = 60          # the constant of reciprocal rank fusion, as in the paper that named it (Cormack et al., 2009)


def _same_passage(passage: dict) -> Any:
    """What tells one stored passage from another: its id in the store, or, for a list that carries none,
    its document, page and text."""
    return passage.get("id") or (passage.get("doc_id"), passage.get("page"), passage.get("text"))


def fuse(lists: list, names: list) -> list:
    """Reciprocal rank fusion of ranked lists of passages. A passage scores 1 / (RRF_K + rank) in each list that
    holds it (rank 1 is the first); the scores are added and the passages put in that order, each once. Between
    equal scores the passage with the better rank goes first, then the one of the earlier list: the question's
    own list is the first, so its passage leads a tie with the other language's.

    Each passage keeps the fields of its best-ranked appearance, its highest ``score`` (the similarity to the
    text that found it; the fusion does not use it), and ``found``: the names of the lists that hold it.
    The fusion looks at ranks only: it does not know how good a passage is."""
    merged: dict = {}
    for order, (passages, name) in enumerate(zip(lists, names)):
        seen = set()
        for rank, passage in enumerate(passages, start=1):
            key = _same_passage(passage)
            if key in seen:                         # one list naming a passage twice: its first rank counts
                continue
            seen.add(key)
            entry = merged.get(key)
            if entry is None:
                merged[key] = {"passage": dict(passage), "rrf": 1.0 / (RRF_K + rank), "best": (rank, order), "found": [name]}
                continue
            entry["rrf"] += 1.0 / (RRF_K + rank)
            entry["found"].append(name)
            scores = [x for x in (entry["passage"].get("score"), passage.get("score")) if x is not None]
            if (rank, order) < entry["best"]:
                entry["best"], entry["passage"] = (rank, order), dict(passage)
            if scores:
                entry["passage"]["score"] = max(scores)
    ranked = sorted(merged.values(), key=lambda entry: (-entry["rrf"], entry["best"]))
    return [{**entry["passage"], "found": entry["found"]} for entry in ranked]


def wanted_for(passage_text: str, texts: dict) -> str:
    """The question's text an excerpt is chosen with: the one in the passage's own language. ``texts`` is
    {"es": .., "en": ..} with one or both; a passage whose language cannot be told, or is not among them, is
    compared with every text there is."""
    return texts.get(language.of_passage(passage_text) or "") or " ".join(texts.values())


# The searches run on two pools that live as long as the process, one per store, so a store that hangs fills
# only its own pool and the other store still answers. A question uses one thread of the catalogue's and one
# or two of the literature's (one search per language); the demo's limits let a handful of questions run at
# once, and a store that hangs holds at most its own pool (a question that finds its store's pool full waits
# for a free thread and meets its deadline).
_CATALOGUE = ThreadPoolExecutor(max_workers=4, thread_name_prefix="catalogue")
_LITERATURE = ThreadPoolExecutor(max_workers=8, thread_name_prefix="literature")


def _timed(name: str, fn: Callable[[], list]) -> tuple[Optional[list], int]:
    """(what the store returned, or None when it failed; its milliseconds). Never raises: a late or failing
    thread has nobody to raise to."""
    t = time.time()
    try:
        return fn(), int((time.time() - t) * 1000)
    except Unavailable:
        return None, int((time.time() - t) * 1000)
    except Exception as exc:
        log.warning("%s failed: %s", name, type(exc).__name__)
        return None, int((time.time() - t) * 1000)


def _other(lang: str) -> str:
    return "en" if lang == "es" else "es"


def answer(question: str, deps: AskDeps, also: Optional[dict] = None) -> dict:
    """Run the three steps. Raises Unavailable only when neither store answered in time.

    ``also`` is the question in the other language, {"question": str, "lang": "es" | "en"}: the literature is
    then searched once per text and the two lists are fused (the module's note). The answer says so in
    ``searches``: both texts, each with its language and whether its search answered."""
    started = time.time()
    timings: dict[str, int] = {}
    second = " ".join(str((also or {}).get("question") or "").split())
    if not second or second.casefold() == question.casefold() or (also or {}).get("lang") not in ("es", "en"):
        also, second = None, ""
    texts = [question] + ([second] if also else [])

    t0 = time.time()
    try:
        if also and deps.embed_all is not None:
            vectors = list(deps.embed_all(texts))
        else:
            vectors = [deps.embed(text) for text in texts]
    except Exception as exc:
        log.warning("embedding failed: %s", type(exc).__name__)
        vectors = []
    vectors = (vectors + [None] * len(texts))[:len(texts)]
    vector = vectors[0]
    timings["embedding_ms"] = int((time.time() - t0) * 1000)
    if vector:
        embedding_mode = "ok"
    else:
        embedding_mode = "failed" if config.OPENAI_API_KEY else "not configured"
    if also and bool(vectors[1]) != bool(vector):
        # one text with a vector and one without would mix a vector list and a keyword list: the question alone
        also, texts, vectors = None, texts[:1], vectors[:1]

    # Both stores at once, each on the process's pool for that store, each with a deadline. A store that has
    # not answered by it is unavailable for this question; its thread is not waited for, and what it returns
    # later is dropped. With a second text the literature is searched twice, side by side, each search
    # returning ASK_FUSION_DEPTH passages (settings.py says why that many).
    futures = {"catalogue": _CATALOGUE.submit(_timed, "catalogue", lambda: deps.lookup(question, vector))}
    if also:
        depth = max(settings.ASK_FUSION_DEPTH, settings.ASK_PASSAGES)
        futures["literature"] = _LITERATURE.submit(_timed, "literature", lambda: deps.search(question, vector, depth))
        futures["literature_also"] = _LITERATURE.submit(_timed, "literature", lambda: deps.search(second, vectors[1], depth))
    else:
        futures["literature"] = _LITERATURE.submit(_timed, "literature", lambda: deps.search(question, vector))
    submitted = time.time()
    concurrent.futures.wait(futures.values(), timeout=settings.ASK_STORE_SECONDS)
    found: dict = {}
    for name, future in futures.items():
        if future.done():
            found[name], timings[f"{name}_ms"] = future.result()
        else:
            future.cancel()                     # not started yet (the pool is busy): it never will be
            found[name] = None
            timings[f"{name}_ms"] = int((time.time() - submitted) * 1000)
            log.warning("%s deadline", name)
    issues, passages = found["catalogue"], found["literature"]

    searches = None
    if also:
        other = found["literature_also"]
        own_lang = _other(also["lang"])
        searches = [{"question": question, "lang": own_lang, "state": "unavailable" if passages is None else "ok"},
                    {"question": second, "lang": also["lang"], "state": "unavailable" if other is None else "ok"}]
        if passages is not None and other is not None:
            passages = fuse([passages, other], ["question", "translation"])
        elif other is not None:                 # the question's own search failed: the other list alone
            passages = [{**p, "found": ["translation"]} for p in other]
        elif passages is not None:              # ... or the other one did
            passages = [{**p, "found": ["question"]} for p in passages]

    if issues is None and passages is None:
        raise Unavailable("both stores")

    by_lang = {searches[0]["lang"]: question, searches[1]["lang"]: second} if searches else None
    shown = []
    with_figures = figures.on()
    for p in (passages or [])[: settings.ASK_PASSAGES]:
        whole = tidy(p.get("text", ""))
        if settings.ASK_EXCERPT == "nearest":
            text, clipped = excerpt(whole, wanted_for(whole, by_lang) if by_lang else question, settings.ASK_TEXT_LIMIT)
        else:
            text, clipped = clip(whole, settings.ASK_TEXT_LIMIT)
        entry = {"doc_id": p.get("doc_id"), "page": p.get("page"), "chunk_type": p.get("chunk_type"),
                 "text": text, "clipped": clipped, "score": p.get("score")}
        if searches:
            # the passage's own language, by its words (None: it cannot be told), and which search found it
            entry["lang"] = language.of_passage(whole)
            entry["found"] = p.get("found") or []
        if with_figures:
            # the figures the whole stored passage names, not only its shown excerpt: by digest, never by name
            named = figures.of_passage(p.get("text", ""))
            if named:
                entry["figures"] = named
        shown.append(entry)
    timings["total_ms"] = int((time.time() - started) * 1000)
    return {
        "question": question,
        "mode": {
            "embedding": embedding_mode,
            "catalogue": "unavailable" if issues is None else ("vector index" if vector else "full-text index"),
            "literature": "unavailable" if passages is None else ("vector" if vector else "keyword"),
        },
        "issues": _without_vectors(issues or [])[: settings.ASK_ISSUES],
        "passages": shown,
        **({"searches": searches} if searches else {}),
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

    return AskDeps(embed=embedder, embed_all=embedder.all, lookup=make_lookup(link), search=literature.search,
                   verify_human=public_guard.verify_turnstile, close=close, warm=warm,
                   states=lambda: {"literature": literature.state, "embedding": embedder.state})
