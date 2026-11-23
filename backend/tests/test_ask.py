"""The question path, with fakes in place of the three stores. No network, no database, no key."""

import json
import logging
import string
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import ask_service, main, public_guard, settings

from oxcart import config

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
    monkeypatch.setattr(settings, "VISITOR_ADDRESS_HEADER", "")
    monkeypatch.setattr(settings, "GRAPH_WARM_ON_START", False)     # no graph in these tests: the steps are fakes
    monkeypatch.setattr(settings, "ASK_WARM_ON_START", False)       # ... and nothing is opened at startup
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
    assert client.get("/api/health").json() == {"status": "ok", "graph": "connecting",
                                                "literature": "not started", "embedding": "not started"}
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


def test_the_eval_skips_the_token_count_too(client, monkeypatch):
    monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "s" * 32)
    client.app.state.limiter = public_guard.Limiter(per_minute=1, per_day=1, global_per_day=10)
    headers = {**session_of(client), "x-oxcart-eval": "s" * 32}          # the same session token every time
    assert [client.post("/api/ask", json={"question": "q"}, headers=headers).status_code for _ in range(3)] == [200, 200, 200]


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


class Hanging:
    """A store's step that blocks until ``release`` is set, then returns ``value``. ``returned`` is set as it ends."""

    def __init__(self, value):
        self.value, self.release, self.returned, self.calls = value, threading.Event(), threading.Event(), []

    def __call__(self, question, vector):
        self.calls.append((question, vector))
        self.release.wait(10)
        self.returned.set()
        return self.value


def logged_warnings(run):
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    log = logging.getLogger("oxcart.ask")
    log.addHandler(handler)
    try:
        return run(), records
    finally:
        log.removeHandler(handler)


@pytest.mark.parametrize("hung", ["catalogue", "literature"])
def test_a_store_that_does_not_answer_in_time_does_not_hold_back_the_other(client, fakes, monkeypatch, hung):
    monkeypatch.setattr(settings, "ASK_STORE_SECONDS", 0.3)
    stuck = Hanging([{"issue_id": "CR-LATE"}] if hung == "catalogue" else [{"doc_id": "LATE", "text": "late"}])
    deps = fakes.deps()
    if hung == "catalogue":
        deps.lookup = stuck
    else:
        deps.search = stuck
    client.app.state.ask = deps
    try:
        t0 = time.time()
        r, records = logged_warnings(lambda: client.post("/api/ask", json={"question": "a made-up question"},
                                                         headers=session_of(client)))
        elapsed = time.time() - t0
        body = r.json()
        assert r.status_code == 200 and elapsed < 3
        assert body["mode"][hung] == "unavailable" and body["timings"][f"{hung}_ms"] >= 300
        if hung == "catalogue":
            assert body["issues"] == [] and len(body["passages"]) == 5 and body["mode"]["literature"] == "vector"
        else:
            assert body["passages"] == [] and len(body["issues"]) == 1 and body["mode"]["catalogue"] == "vector index"
        assert f"{hung} deadline" in records and not any("made-up" in line for line in records)
        # the embedding step is as it was: made once from the question, its vector given to both stores
        assert fakes.seen["embed"] == "a made-up question" and stuck.calls == [("a made-up question", fakes.vector)]
    finally:
        stuck.release.set()


def test_when_both_stores_are_late_neither_answered(fakes, monkeypatch):
    monkeypatch.setattr(settings, "ASK_STORE_SECONDS", 0.2)
    lookup, search = Hanging([]), Hanging([])
    deps = ask_service.AskDeps(embed=fakes.embed, lookup=lookup, search=search, verify_human=fakes.verify)
    try:
        with pytest.raises(ask_service.Unavailable, match="both stores"):
            ask_service.answer("q", deps)
    finally:
        lookup.release.set()
        search.release.set()


def test_a_late_stores_result_is_dropped_and_does_not_reach_the_next_question(fakes, monkeypatch):
    monkeypatch.setattr(settings, "ASK_STORE_SECONDS", 0.2)
    late = Hanging([{"issue_id": "CR-LATE", "title": "Late"}])
    deps = ask_service.AskDeps(embed=fakes.embed, lookup=late, search=fakes.search, verify_human=fakes.verify)
    try:
        first = ask_service.answer("q", deps)
        kept = json.dumps(first, sort_keys=True)
    finally:
        late.release.set()
    assert late.returned.wait(5)
    time.sleep(0.05)                                   # the late thread has ended
    assert json.dumps(first, sort_keys=True) == kept    # nothing it did changed the answer already given
    assert first["issues"] == [] and first["mode"]["catalogue"] == "unavailable"
    deps.lookup = fakes.lookup
    second = ask_service.answer("q", deps)
    assert [issue["issue_id"] for issue in second["issues"]] == ["CR-1"]          # its own, not the late one's


def test_a_failing_store_thread_raises_into_no_request(fakes, monkeypatch):
    monkeypatch.setattr(settings, "ASK_STORE_SECONDS", 0.2)
    release = threading.Event()

    def late_then_fails(question, vector):
        release.wait(10)
        raise RuntimeError("made-up failure")

    deps = ask_service.AskDeps(embed=fakes.embed, lookup=late_then_fails, search=fakes.search, verify_human=fakes.verify)
    assert ask_service.answer("q", deps)["mode"]["catalogue"] == "unavailable"
    release.set()
    time.sleep(0.05)
    deps.lookup = fakes.lookup
    assert ask_service.answer("q", deps)["mode"]["catalogue"] == "vector index"


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
    headers = session_of(client)                                          # another visitor comes with its own token
    assert ask_from("203.0.113.10").status_code == 200


def test_the_named_header_is_the_visitor_when_the_setting_names_it(client, monkeypatch):
    monkeypatch.setattr(settings, "VISITOR_ADDRESS_HEADER", "cf-connecting-ip")
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)

    def ask_from(named, forwarded):
        headers = {"x-forwarded-for": forwarded, **({"cf-connecting-ip": named} if named else {})}
        return client.post("/api/ask", json={"question": "q"}, headers={**headers, **session_of(client)})   # a new token each time

    assert ask_from("203.0.113.9", "192.0.2.1").status_code == 200
    assert ask_from("203.0.113.9", "192.0.2.2, 192.0.2.3").status_code == 200     # a made-up X-Forwarded-For changes nothing
    r = ask_from("203.0.113.9", "192.0.2.4")
    assert r.status_code == 429 and r.json()["error"] == "visitor_minute_limit"
    assert ask_from("203.0.113.10", "192.0.2.4").status_code == 200              # another visitor has its own count
    # a request without the header falls back to the X-Forwarded-For rule
    assert [ask_from(None, "192.0.2.50").status_code for _ in range(3)] == [200, 200, 429]
    assert ask_from(None, "192.0.2.51").status_code == 200


def test_without_the_setting_a_named_header_from_a_client_changes_nothing(client):
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)
    codes = [client.post("/api/ask", json={"question": "q"},
                         headers={"x-forwarded-for": "203.0.113.9", "cf-connecting-ip": f"198.51.100.{n}", **session_of(client)}).status_code
             for n in range(3)]
    assert codes == [200, 200, 429]


def test_a_session_token_is_counted_whatever_address_it_comes_from(client):
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)
    token = session_of(client)

    def ask_from(forwarded, headers):
        return client.post("/api/ask", json={"question": "q"}, headers={**headers, "x-forwarded-for": forwarded})

    assert ask_from("203.0.113.1", token).status_code == 200
    assert ask_from("203.0.113.2", token).status_code == 200
    r = ask_from("203.0.113.3", token)                                    # a third address, the same token
    assert r.status_code == 429 and r.json()["error"] == "visitor_minute_limit" and int(r.headers["retry-after"]) > 0
    assert ask_from("203.0.113.3", session_of(client)).status_code == 200  # the refusal did not count against that address


def test_a_new_token_does_not_buy_a_new_allowance_for_the_same_address(client):
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)

    def ask_from(forwarded, headers):
        return client.post("/api/ask", json={"question": "q"}, headers={**headers, "x-forwarded-for": forwarded})

    assert ask_from("203.0.113.1", session_of(client)).status_code == 200
    assert ask_from("203.0.113.1", session_of(client)).status_code == 200
    fresh = session_of(client)
    assert ask_from("203.0.113.1", fresh).status_code == 429               # the address is at its limit
    assert [ask_from(f"203.0.113.{n}", fresh).status_code for n in (7, 8, 9)] == [200, 200, 429]   # ... and that refusal did not count against the token


def other_spellings(token):
    """The same token written in other ways that still decode to the same bytes."""
    alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"     # url-safe base64, in order
    payload, signature = token.split(".")
    flipped = signature[:-1] + alphabet[alphabet.index(signature[-1]) ^ 1]      # an unused bit of the last character
    return [payload + "=." + signature, token + "~~", payload + "." + flipped]


def test_one_token_has_one_count_however_it_is_written():
    key = "k" * 40
    token = public_guard.issue_session(key, 3600)
    payload = public_guard.session_payload(token, key)
    assert payload is not None and public_guard.session_is_valid(token, key)
    variants = other_spellings(token)
    assert len(set(variants + [token])) == 4                                    # four different strings
    for variant in variants:
        seen = public_guard.session_payload(variant, key)
        assert seen is None or public_guard.token_key(seen) == public_guard.token_key(payload), variant[-6:]
    another = public_guard.session_payload(public_guard.issue_session(key, 3600), key)
    assert public_guard.token_key(another) != public_guard.token_key(payload)   # a different token has its own count


def test_a_token_at_its_limit_stays_there_in_every_spelling_and_from_any_address(client):
    client.app.state.limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=1000)
    token = session_of(client)["x-oxcart-session"]

    def ask_with(session, forwarded):
        return client.post("/api/ask", json={"question": "q"}, headers={"x-oxcart-session": session, "x-forwarded-for": forwarded})

    assert ask_with(token, "203.0.113.1").status_code == 200 and ask_with(token, "203.0.113.2").status_code == 200
    codes = [ask_with(variant, f"203.0.113.{10 + n}").status_code for n, variant in enumerate(other_spellings(token))]
    assert all(code in (429, 401) for code in codes), codes                     # counted as the same token, or not a token at all


def test_refused_questions_leave_nothing_behind():
    clock = [1_000_000.0]
    limiter = public_guard.Limiter(per_minute=2, per_day=100, global_per_day=100_000, now=lambda: clock[0])
    assert limiter.check("a", "token:1")[0] and limiter.check("b", "token:1")[0]
    before = (len(limiter._minute), len(limiter._day))
    assert before == (3, 3)
    for n in range(500):                                                        # the token is at its limit: every new address is refused
        assert limiter.check(f"new-address-{n}", "token:1") == (False, "visitor_minute_limit", 61)
    assert (len(limiter._minute), len(limiter._day)) == before
    assert limiter.check("a", "token:2")[0]                                     # "a" reaches its own limit; "token:2" is counted once
    for n in range(500):                                                        # ... and a new token each time does not get it through
        assert limiter.check("a", f"token:new-{n}")[0] is False
    assert (len(limiter._minute), len(limiter._day)) == (4, 4)
    clock[0] += 30
    assert limiter.check("new-address", "token:1")[2] == 31                     # the wait is still told from the oldest question


def test_limiter_counts_two_keys_together_or_not_at_all():
    clock = [1_000_000.0]
    limiter = public_guard.Limiter(per_minute=100, per_day=2, global_per_day=100, now=lambda: clock[0])
    assert limiter.check("a", "token:1")[0] and limiter.check("b", "token:1")[0]
    assert limiter.check("c", "token:1") == (False, "visitor_daily_limit", limiter.check("c", "token:1")[2])   # the token is at its day's limit
    assert limiter.check("c")[0] and limiter.check("c")[0] and not limiter.check("c")[0]                      # "c" was not charged for the refusals
    assert limiter.check("a", "token:2")[0] and not limiter.check("a", "token:3")[0]                          # "a" reaches its own limit
    assert [limiter.check("d", "token:3")[0] for _ in range(3)] == [True, True, False]                        # token 3 was not charged either
    assert limiter.check(None, "token:1")[0]                                                                   # the eval: neither key is asked
    clock[0] += 86400
    assert limiter.check("a", "token:1")[0]


def test_limiter_day_and_service_limits_reset_the_next_day():
    clock = [1_000_000.0]
    limiter = public_guard.Limiter(per_minute=100, per_day=2, global_per_day=3, now=lambda: clock[0])
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, False]
    assert limiter.check("a")[1] == "visitor_daily_limit"
    assert limiter.check("b")[0] is True
    assert limiter.check("c")[1] == "service_daily_limit"
    clock[0] += 86400
    assert limiter.check("a")[0] is True and limiter.check("c")[0] is True


def test_visitor_key_prefers_the_named_value_and_falls_back_without_it(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    named = public_guard.visitor_key("192.0.2.1", "192.0.2.9", "203.0.113.5")
    assert named == public_guard.visitor_key("198.51.100.77, 192.0.2.44", "192.0.2.10", " 203.0.113.5 ")
    assert named != public_guard.visitor_key("192.0.2.1", "192.0.2.9", "203.0.113.6")
    for absent in (None, "", "   "):
        assert public_guard.visitor_key("192.0.2.1", "192.0.2.9", absent) == public_guard.visitor_key("192.0.2.1", "192.0.2.9")
    assert "203.0.113.5" not in named
    token = public_guard.token_key(b"v1:1900000000:a-nonce")
    assert token.startswith("token:") and "a-nonce" not in token
    assert token == public_guard.token_key(b"v1:1900000000:a-nonce") != public_guard.token_key(b"v1:1900000000:another")


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

    clients = set()

    def post(self, url, **kwargs):
        clients.add(id(self))
        calls.append((url, kwargs))
        return Reply()

    monkeypatch.setattr(config, "OPENAI_API_KEY", "the-key")
    monkeypatch.setattr(httpx.Client, "post", post)
    embed = ask_service.Embedder()
    assert embed("¿Qué es esto?") == [0.5, 0.25] and embed("¿Qué es esto?") == [0.5, 0.25]
    assert len(calls) == 1                                                         # the second one came from the cache
    url, kwargs = calls[0]
    assert url == "https://api.openai.com/v1/embeddings"
    assert kwargs["json"] == {"model": "text-embedding-3-large", "input": "¿Qué es esto?"}
    assert kwargs["headers"] == {"Authorization": "Bearer the-key"}
    assert embed("a second question") == [0.5, 0.25] and len(clients) == 1         # one client: the connection is reused
    kept = repr(list(embed._cache)) + repr(vars(embed))                            # everything the embedder holds
    assert "esto" not in kept and "second question" not in kept                    # no question's text among it
    assert len(embed._cache) == 2 and all(isinstance(slot, bytes) and len(slot) == 16 for slot in embed._cache)
    other = ask_service.Embedder()
    assert other._slot("a second question") != embed._slot("a second question")    # the digest's key is each process's own
    assert embed.state == "connected"

    def failing(self, url, **kwargs):
        calls.append((url, kwargs))
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", failing)
    assert embed("another question") is None and len(calls) == 4                   # one retry, then give up
    assert embed.state == "unavailable"
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    assert ask_service.Embedder()("no key") is None and len(calls) == 4
    embed.close()


# ---------------------------------------------------------------- what is opened at startup
def test_the_embedding_connection_is_opened_with_one_tiny_embedding(monkeypatch):
    import httpx

    calls = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.5, 0.25]}]}

    def post(self, url, **kwargs):
        calls.append(kwargs["json"]["input"])
        return Reply()

    monkeypatch.setattr(httpx.Client, "post", post)
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    embed = ask_service.Embedder()
    assert embed.state == "not started"
    assert embed.warm() is False and embed.state == "not configured" and calls == []     # no key: nothing is sent
    monkeypatch.setattr(config, "OPENAI_API_KEY", "the-key")
    embed.warm_in_background().join(5)
    assert embed.state == "connected" and calls == ["warm-up"]
    assert embed("warm-up") == [0.5, 0.25] and len(calls) == 2                           # the warm-up's vector was not kept

    def failing(self, url, **kwargs):
        calls.append("failed")
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", failing)
    assert embed.warm() is False and embed.state == "unavailable" and calls[2:] == ["failed", "failed"]
    embed.close()


class FakeStore:
    """Stands for a Weaviate client: one collection whose searches return two passages."""

    def __init__(self):
        found = types.SimpleNamespace(objects=[
            types.SimpleNamespace(properties={"doc_id": "D", "page_number": n, "chunk_type": "text", "text": "t"},
                                  metadata=types.SimpleNamespace(distance=0.25, score=1.0)) for n in (1, 2)])
        query = types.SimpleNamespace(near_vector=lambda **kw: found, bm25=lambda **kw: found)
        self.collections = types.SimpleNamespace(get=lambda name: types.SimpleNamespace(query=query))
        self.closed = False

    def close(self):
        self.closed = True


def test_the_literature_client_is_opened_in_the_background_and_a_question_uses_that_one(monkeypatch):
    gate, opened = threading.Event(), []

    def connect(self):
        gate.wait(5)
        opened.append(FakeStore())
        return opened[-1]

    monkeypatch.setattr(ask_service.Literature, "_connect", connect)
    literature = ask_service.Literature()
    assert literature.state == "not started"
    thread = literature.warm_in_background()
    assert literature.state == "connecting"                          # said at once, before the client is open
    gate.set()
    thread.join(5)
    assert literature.state == "connected" and len(opened) == 1
    assert len(literature.search("q", [0.1])) == 2 and len(opened) == 1     # the question did not open a second client
    literature.close()
    assert opened[0].closed


def test_a_literature_client_that_cannot_be_opened_is_reported_and_recovers(monkeypatch):
    attempts = []

    def refuse(self):
        attempts.append(1)
        raise ConnectionError("an address would be in here")

    monkeypatch.setattr(ask_service.Literature, "_connect", refuse)
    literature = ask_service.Literature()
    assert literature.warm() is False and literature.state == "unavailable" and len(attempts) == 2
    monkeypatch.setattr(ask_service.Literature, "_connect", lambda self: FakeStore())
    assert len(literature.search("q", None)) == 2 and literature.state == "connected"


def test_startup_opens_both_in_the_background_and_health_says_where_they_are(make_client, monkeypatch):
    gate = threading.Event()

    def connect(self):
        gate.wait(5)
        return FakeStore()

    monkeypatch.setattr(ask_service.Literature, "_connect", connect)
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "ASK_WARM_ON_START", True)
    opened = []
    real = ask_service.default_deps
    monkeypatch.setattr(ask_service, "default_deps", lambda link: opened.append(real(link)) or opened[-1])
    client = make_client()
    client.app.state.ask = opened[0]                                 # the real steps, not the fixture's fakes
    t0 = time.time()
    body = client.get("/api/health").json()
    assert body["literature"] == "connecting" and time.time() - t0 < 1.0     # startup and health did not wait
    gate.set()
    for _ in range(200):
        body = client.get("/api/health").json()
        if body["literature"] == "connected" and body["embedding"] != "connecting":
            break
        time.sleep(0.01)
    assert body == {"status": "ok", "graph": "connecting", "literature": "connected", "embedding": "not configured"}


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


def test_the_short_vector_is_asked_only_when_the_setting_is_on_and_a_refusal_falls_back(monkeypatch):
    from app import ask_service
    from oxcart import catalogue_lookup

    asked = []

    class Link:
        refuse_short = False
        refusal = ask_service.Refused("ClientError")

        def read(self, fn):
            return fn("a session")

    def fake_lookup(session, question, k, question_vector, use_short=False):
        asked.append(use_short)
        if use_short and Link.refuse_short:
            raise Link.refusal                             # what the link raises when the graph refuses a query
        return [{"issue_id": "CR-1901-MADE-UP", "short": use_short}]

    monkeypatch.setattr(catalogue_lookup, "lookup", fake_lookup)
    lookup = ask_service.make_lookup(Link())

    monkeypatch.setattr(settings, "ASK_SHORT_VECTOR", False)
    assert lookup("a question", [0.1])[0]["short"] is False and asked == [False]

    asked.clear()
    monkeypatch.setattr(settings, "ASK_SHORT_VECTOR", True)
    assert lookup("a question", [0.1])[0]["short"] is True and asked == [True]
    asked.clear()
    assert lookup("a question", None)[0]["short"] is False and asked == [False]     # no embedding, no vector index

    asked.clear()
    Link.refuse_short = True                                                         # the graph has no such index
    assert lookup("a question", [0.1])[0]["short"] is False and asked == [True, False]

    asked.clear()
    Link.refusal = ask_service.Unavailable("ClientError")                            # a failure of another kind, whatever its name:
    with pytest.raises(ask_service.Unavailable):                                     # the lookup is not asked again
        lookup("a question", [0.1])
    assert asked == [True]


def test_an_ipv6_visitor_is_counted_by_the_first_64_bits_of_its_address(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    key = lambda address: public_guard.visitor_key(address, "192.0.2.9")
    # one subscriber's addresses (documentation range 2001:db8::/32): the last 64 bits are theirs to change
    assert key("2001:db8:12:34::1") == key("2001:db8:12:34:ffff:ffff:ffff:fffe") == key("[2001:DB8:12:34::9]")
    assert key("2001:db8:12:34::1") != key("2001:db8:12:35::1")                      # another subscriber
    assert key("2001:db8:12:34::1") == public_guard.visitor_key("192.0.2.1", "192.0.2.9", "2001:db8:12:34:a:b:c:d")
    # an IPv4 address is counted whole, also when it is written inside an IPv6 one
    assert key("::ffff:198.51.100.4") == key("198.51.100.4") != key("198.51.100.5")
    assert public_guard.counted_address("2001:db8:12:34:a:b:c:d") == "2001:db8:12:34::/64"
    assert public_guard.counted_address("198.51.100.4") == "198.51.100.4"
    for text in ("unknown", "", "not an address"):                                   # counted as given, nothing raised
        assert public_guard.counted_address(text) == text
