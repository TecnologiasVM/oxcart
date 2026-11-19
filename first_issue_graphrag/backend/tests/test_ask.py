"""The question path, with fakes in place of the three stores. No network, no database, no key."""

import pytest
from fastapi.testclient import TestClient

from app import ask_service, main, public_guard, settings

import config

ORIGIN = "https://demo.example"
LONG = "x" * 2000


class Fakes:
    def __init__(self):
        self.vector = [0.1, 0.2, 0.3]
        self.human = "ok"
        self.lookup_error = self.search_error = None
        self.seen = {}

    def embed(self, question):
        self.seen["embed"] = question
        return self.vector

    def lookup(self, question, vector):
        self.seen["lookup"] = (question, vector)
        if self.lookup_error:
            raise self.lookup_error
        return [{"issue_id": "CR-1", "title": "An issue", "score": 4.0, "matched_by": ["vector"],
                 "card": {"issue_id": "CR-1", "embedding": [1.0, 2.0], "stamps": [{"catalog_no": "1", "text_vector": [3.0]}]}}]

    def search(self, question, vector):
        self.seen["search"] = (question, vector)
        if self.search_error:
            raise self.search_error
        return [{"doc_id": f"DOC {n}", "page": n, "chunk_type": "text", "text": LONG, "score": 0.9} for n in range(7)]

    def verify(self, token):
        self.seen["verify"] = token
        return self.human

    def deps(self):
        return ask_service.AskDeps(embed=self.embed, lookup=self.lookup, search=self.search, verify_human=self.verify)


@pytest.fixture
def fakes():
    return Fakes()


@pytest.fixture
def make_client(monkeypatch, fakes):
    monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "k" * 40)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET", "configured")
    monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "")
    monkeypatch.setattr(settings, "CORS_ORIGINS", [ORIGIN])
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "set-for-the-mode-label")
    opened = []

    def build(public=True, **kwargs):
        client = TestClient(main.create_app(public=public), **kwargs)
        client.__enter__()
        client.app.state.ask = fakes.deps()
        opened.append(client)
        return client

    yield build
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()


def session_of(client):
    r = client.post("/api/session", json={"token": "from-the-page"})
    assert r.status_code == 200, r.text
    return {"x-oxcart-session": r.json()["session"]}


def keys_of(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from keys_of(v)
    elif isinstance(value, list):
        for v in value:
            yield from keys_of(v)


# ---------------------------------------------------------------- what the hosted mode exposes
def test_hosted_mode_mounts_the_question_path_only(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ask/examples").status_code == 200
    for path in ("/docs", "/redoc", "/openapi.json", "/api/graph", "/api/node?node_id=chunk:1", "/api/overview",
                 "/api/examples", "/api/mena/surface-mail", "/api/figures/x.png"):
        assert client.get(path).status_code == 404, path
    for path in ("/api/query", "/api/query/export"):
        assert client.post(path, json={"question": "q"}).status_code == 404, path
    assert "docs" not in client.get("/").json()


def test_local_mode_keeps_the_explorer_and_needs_no_session(make_client):
    local = make_client(public=False)
    assert local.get("/openapi.json").status_code == 200
    assert local.get("/api/examples").status_code == 200
    assert local.post("/api/ask", json={"question": "a question"}).status_code == 200


# ---------------------------------------------------------------- the human check
def test_a_question_needs_a_session_in_hosted_mode(client):
    r = client.post("/api/ask", json={"question": "a question"})
    assert r.status_code == 401 and r.json()["error"] == "session_required"
    assert client.post("/api/ask", json={"question": "a question"}, headers={"x-oxcart-session": "not.atoken"}).status_code == 401


def test_a_passed_check_gives_a_session_that_opens_the_question_path(client, fakes):
    headers = session_of(client)
    assert fakes.seen["verify"] == "from-the-page"
    r = client.post("/api/ask", json={"question": "a question"}, headers=headers)
    assert r.status_code == 200
    assert client.post("/api/ask", json={"question": "another"}, headers=headers).status_code == 200   # once per session


def test_a_failed_check_is_refused_and_an_unavailable_one_says_so(client, fakes, monkeypatch):
    fakes.human = "failed"
    r = client.post("/api/session", json={"token": "t"})
    assert r.status_code == 403 and r.json()["error"] == "human_check_failed"
    fakes.human = "unavailable"
    r = client.post("/api/session", json={"token": "t"})
    assert r.status_code == 503 and r.json()["error"] == "human_check_unavailable" and "try again" in r.json()["message"]
    fakes.human = "ok"
    monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "")
    assert client.post("/api/session", json={"token": "t"}).status_code == 503


def test_session_tokens_expire_and_cannot_be_forged():
    token = public_guard.issue_session("key-one", 60, now=1000.0)
    assert public_guard.session_is_valid(token, "key-one", now=1059.0)
    assert not public_guard.session_is_valid(token, "key-one", now=1061.0)
    assert not public_guard.session_is_valid(token, "key-two", now=1000.0)
    payload, signature = token.split(".")
    assert not public_guard.session_is_valid(payload[:-2] + "AA." + signature, "key-one", now=1000.0)
    assert not public_guard.session_is_valid("", "key-one") and not public_guard.session_is_valid(token, "")


def test_turnstile_verdicts(monkeypatch):
    import httpx

    class Reply:
        def __init__(self, status, body):
            self.status_code, self._body = status, body

        def json(self):
            return self._body

    sent = {}

    def post_returning(reply):
        def post(url, **kwargs):
            sent.update(url=url, **kwargs)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return post

    monkeypatch.setattr(settings, "TURNSTILE_SECRET", "the-secret")
    monkeypatch.setattr(httpx, "post", post_returning(Reply(200, {"success": True})))
    assert public_guard.verify_turnstile("tok") == "ok"
    assert sent["url"] == settings.TURNSTILE_VERIFY_URL and sent["data"] == {"secret": "the-secret", "response": "tok"}
    monkeypatch.setattr(httpx, "post", post_returning(Reply(200, {"success": False, "error-codes": ["invalid-input-response"]})))
    assert public_guard.verify_turnstile("tok") == "failed"
    monkeypatch.setattr(httpx, "post", post_returning(Reply(200, {"success": False, "error-codes": ["internal-error"]})))
    assert public_guard.verify_turnstile("tok") == "unavailable"
    monkeypatch.setattr(httpx, "post", post_returning(Reply(500, {})))
    assert public_guard.verify_turnstile("tok") == "unavailable"
    monkeypatch.setattr(httpx, "post", post_returning(httpx.ConnectError("down")))
    assert public_guard.verify_turnstile("tok") == "unavailable"
    monkeypatch.setattr(settings, "TURNSTILE_SECRET", "")
    assert public_guard.verify_turnstile("tok") == "unavailable"


# ---------------------------------------------------------------- the eval's way in
def test_the_eval_header_opens_only_with_the_configured_secret(client, monkeypatch):
    assert client.post("/api/ask", json={"question": "q"}, headers={"x-oxcart-eval": "anything"}).status_code == 401
    monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "s" * 32)
    assert client.post("/api/ask", json={"question": "q"}, headers={"x-oxcart-eval": "wrong"}).status_code == 401
    assert client.post("/api/ask", json={"question": "q"}, headers={"x-oxcart-eval": "s" * 32}).status_code == 200


def test_the_eval_skips_the_visitor_limit_but_not_the_service_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "s" * 32)
    client.app.state.limiter = public_guard.Limiter(per_minute=1, per_day=1, global_per_day=3)
    codes = [client.post("/api/ask", json={"question": "q"}, headers={"x-oxcart-eval": "s" * 32}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# ---------------------------------------------------------------- the answer and its modes
def test_the_answer_says_which_mode_produced_each_block(client, fakes):
    r = client.post("/api/ask", json={"question": "  a   question "}, headers=session_of(client))
    body = r.json()
    assert body["mode"] == {"embedding": "ok", "catalogue": "vector index", "literature": "vector"}
    assert fakes.seen["embed"] == "a question"                       # sent as asked, whitespace tidied, no prefix
    assert fakes.seen["lookup"] == ("a question", fakes.vector) and fakes.seen["search"] == ("a question", fakes.vector)
    assert len(body["passages"]) == settings.ASK_PASSAGES == 5
    assert all(len(p["text"]) <= settings.ASK_TEXT_LIMIT + 1 and p["clipped"] for p in body["passages"])
    assert set(body["passages"][0]) == {"doc_id", "page", "chunk_type", "text", "clipped", "score"}
    from_the_stores = [body["issues"], body["passages"]]
    assert not [k for k in keys_of(from_the_stores) if "embed" in k.lower() or "vector" in k.lower()]   # no vectors leave
    assert body["issues"][0]["card"] == {"issue_id": "CR-1", "stamps": [{"catalog_no": "1"}]}
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"


def test_without_an_embedding_it_falls_back_to_keyword_and_full_text(client, fakes):
    fakes.vector = None
    body = client.post("/api/ask", json={"question": "a question"}, headers=session_of(client)).json()
    assert body["mode"] == {"embedding": "failed", "catalogue": "full-text index", "literature": "keyword"}
    assert fakes.seen["lookup"][1] is None and fakes.seen["search"][1] is None


def test_one_store_down_leaves_the_other_block_and_says_so(client, fakes):
    headers = session_of(client)
    fakes.lookup_error = ask_service.Unavailable("ServiceUnavailable")
    body = client.post("/api/ask", json={"question": "q"}, headers=headers).json()
    assert body["mode"]["catalogue"] == "unavailable" and body["issues"] == [] and len(body["passages"]) == 5
    fakes.lookup_error, fakes.search_error = None, RuntimeError("boom with an address in it")
    body = client.post("/api/ask", json={"question": "q"}, headers=headers).json()
    assert body["mode"]["literature"] == "unavailable" and body["passages"] == [] and len(body["issues"]) == 1
    fakes.lookup_error = ask_service.Unavailable("SessionExpired")
    r = client.post("/api/ask", json={"question": "q"}, headers=headers)
    assert r.status_code == 503 and r.json()["error"] == "stores_unavailable" and "address" not in r.text


def test_an_unexpected_error_is_a_short_json_without_a_trace(make_client, monkeypatch):
    client = make_client(raise_server_exceptions=False)
    headers = session_of(client)
    monkeypatch.setattr(ask_service, "answer", lambda question, deps: 1 / 0)
    r = client.post("/api/ask", json={"question": "q"}, headers=headers)
    assert r.status_code == 500 and r.json()["error"] == "internal"
    assert "Traceback" not in r.text and "ZeroDivision" not in r.text


# ---------------------------------------------------------------- limits and bounds
def test_the_visitor_limit_counts_by_the_address_the_proxy_reports(client):
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)
    headers = session_of(client)

    def ask_from(forwarded):
        return client.post("/api/ask", json={"question": "q"}, headers={**headers, "x-forwarded-for": forwarded})

    assert ask_from("203.0.113.9").status_code == 200
    assert ask_from("192.0.2.99, 203.0.113.9").status_code == 200          # what the client put on the left changes nothing
    r = ask_from("198.51.100.1, 203.0.113.9")
    assert r.status_code == 429 and r.json()["error"] == "visitor_minute_limit" and int(r.headers["retry-after"]) > 0
    assert ask_from("203.0.113.10").status_code == 200                    # another visitor


def test_limiter_day_and_service_limits_reset_the_next_day():
    clock = [1_000_000.0]
    limiter = public_guard.Limiter(per_minute=100, per_day=2, global_per_day=3, now=lambda: clock[0])
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, False]
    assert limiter.check("a")[1] == "visitor_daily_limit"
    assert limiter.check("b")[0] is True
    assert limiter.check("c")[1] == "service_daily_limit"
    clock[0] += 86400
    assert limiter.check("a")[0] is True and limiter.check("c")[0] is True


def test_visitor_key_reads_from_the_right(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    a = public_guard.visitor_key("192.0.2.1, 192.0.2.2, 192.0.2.3", "192.0.2.9")
    assert a == public_guard.visitor_key("192.0.2.7, 192.0.2.2, 192.0.2.4", "192.0.2.9")
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    assert public_guard.visitor_key("192.0.2.1", "192.0.2.9") == public_guard.visitor_key(None, "192.0.2.9")
    assert "192.0.2.9" not in public_guard.visitor_key(None, "192.0.2.9")


def test_bad_requests_are_refused_without_echoing_them(client):
    headers = session_of(client)
    r = client.post("/api/ask", json={"question": "secret words " * 40}, headers=headers)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request" and "secret words" not in r.text
    assert client.post("/api/ask", json={"question": "q", "k": 500}, headers=headers).status_code == 422
    assert client.post("/api/ask", json={"question": "   "}, headers=headers).status_code == 422
    assert client.post("/api/ask", content=b'{"question": "' + b"a" * 3000 + b'"}',
                       headers={**headers, "content-type": "application/json"}).status_code == 413


def test_cors_allows_the_demo_origin_only(client):
    ask = {"access-control-request-method": "POST", "access-control-request-headers": "content-type,x-oxcart-session"}
    ok = client.options("/api/ask", headers={"origin": ORIGIN, **ask})
    assert ok.headers.get("access-control-allow-origin") == ORIGIN
    assert "access-control-allow-credentials" not in ok.headers
    other = client.options("/api/ask", headers={"origin": "https://elsewhere.example", **ask})
    assert "access-control-allow-origin" not in other.headers


# ---------------------------------------------------------------- the real steps, without a network
def test_the_embedding_is_made_here_from_the_question_as_asked(monkeypatch):
    import httpx

    calls = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.5, 0.25]}]}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Reply()

    monkeypatch.setattr(config, "OPENAI_API_KEY", "the-key")
    monkeypatch.setattr(httpx, "post", post)
    embed = ask_service.Embedder()
    assert embed("¿Qué es esto?") == [0.5, 0.25] and embed("¿Qué es esto?") == [0.5, 0.25]
    assert len(calls) == 1                                                         # the second one came from the cache
    url, kwargs = calls[0]
    assert url == "https://api.openai.com/v1/embeddings"
    assert kwargs["json"] == {"model": "text-embedding-3-large", "input": "¿Qué es esto?"}

    def failing(url, **kwargs):
        calls.append((url, kwargs))
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", failing)
    assert embed("another question") is None and len(calls) == 3                   # one retry, then give up
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    assert ask_service.Embedder()("no key") is None and len(calls) == 3


def test_the_vector_store_client_is_never_given_the_openai_key(monkeypatch):
    import weaviate

    captured = {}

    def connect(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("no store in this test")

    monkeypatch.setattr(config, "OPENAI_API_KEY", "the-openai-key")
    monkeypatch.setattr(config, "WEAVIATE_API_KEY", "the-read-only-key")
    monkeypatch.setattr(settings, "WEAVIATE_URL", "")
    monkeypatch.setattr(weaviate, "connect_to_local", connect)
    with pytest.raises(ask_service.Unavailable):
        ask_service.Literature().search("q", [0.1])
    assert "headers" not in captured and "the-openai-key" not in repr(captured)
    captured.clear()
    monkeypatch.setattr(settings, "WEAVIATE_URL", "https://cluster.example")
    monkeypatch.setattr(weaviate, "connect_to_weaviate_cloud", connect)
    with pytest.raises(ask_service.Unavailable):
        ask_service.Literature().search("q", None)
    assert captured["cluster_url"] == "https://cluster.example"
    assert "headers" not in captured and "the-openai-key" not in repr(captured)
