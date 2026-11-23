"""The size and the time of a POST's body, held before anything reads it (app/body_limit.py).

Fake stores, a fake model, fake ASGI messages: no network, no key. Every text here is made up."""

import asyncio
import json

import pytest

from app import body_limit, settings

from test_ask import ORIGIN, Fakes, client, fakes, make_client, session_of  # noqa: F401  (client, fakes, make_client: fixtures)
from test_chat import FakeModel


class Inner:
    """Stands where the app does: says whether it was entered and what body it was given."""

    def __init__(self):
        self.entered, self.body = False, None

    async def __call__(self, scope, receive, send):
        self.entered = True
        message = await receive()
        self.body = message.get("body")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def run(limit, headers, messages, path="/api/ask"):
    """Drive the middleware with ``messages`` (a list, or a callable that makes the next one). Returns (the
    inner app, the response's status, its JSON body, how many messages were asked for)."""
    inner = Inner()
    middleware = body_limit.BodyLimit(inner, limits=lambda: {"/api/ask": limit}, default=lambda: 100)
    asked = [0]
    sent = []

    async def receive():
        asked[0] += 1
        if callable(messages):
            return await messages()
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
    asyncio.run(middleware(scope, receive, send))
    status = sent[0]["status"] if sent else None
    body = json.loads(sent[1]["body"]) if len(sent) > 1 and sent[1]["body"] and status != 200 else None
    return inner, status, body, asked[0]


def length(n):
    return [(b"content-length", str(n).encode())]


def test_a_body_over_the_limit_with_an_honest_header_is_refused_before_the_route_is_entered():
    inner, status, body, asked = run(1000, length(1001), [{"type": "http.request", "body": b"x" * 1001}])
    assert status == 413 and body == {"error": "request_too_large", "message": "The request is too large."}
    assert not inner.entered and asked == 0                     # not a byte was read


def test_a_body_that_passes_its_small_header_is_refused_once_the_bytes_received_pass_the_limit():
    async def endless():
        return {"type": "http.request", "body": b"x" * 100, "more_body": True}

    inner, status, body, asked = run(1000, length(10), endless)
    assert status == 413 and body["error"] == "request_too_large" and not inner.entered
    assert asked == 11                  # 1,100 bytes: the first message that takes the count past 1,000, and no more


def test_a_missing_or_unreadable_header_is_refused():
    for headers in ([], [(b"content-length", b"ten")], [(b"content-length", b"-5")], length(5) + length(5)):
        inner, status, body, asked = run(1000, headers, [{"type": "http.request", "body": b"{}"}])
        assert status == 413 and not inner.entered and asked == 0, headers


def test_a_slow_body_meets_the_deadline(monkeypatch):
    monkeypatch.setattr(settings, "BODY_READ_SECONDS", 0.2)
    first = [True]

    async def slow():
        if first[0]:
            first[0] = False
            return {"type": "http.request", "body": b'{"question":', "more_body": True}
        await asyncio.sleep(5)
        return {"type": "http.request", "body": b'"q"}'}

    inner, status, body, _ = run(1000, length(17), slow)
    assert status == 408 and body == {"error": "request_timeout",
                                      "message": "The request took too long to arrive. Please try again."}
    assert not inner.entered


def test_a_body_in_pieces_under_the_limit_reaches_the_route_whole():
    pieces = [{"type": "http.request", "body": b'{"question":', "more_body": True},
              {"type": "http.request", "body": b' "q"}', "more_body": False}]
    inner, status, _, _ = run(1000, length(17), pieces)
    assert status == 200 and inner.body == b'{"question": "q"}'


def test_other_methods_and_paths_are_not_held():
    inner = Inner()
    middleware = body_limit.BodyLimit(inner, limits=lambda: {}, default=lambda: 1)

    async def receive():
        return {"type": "http.request", "body": b"x" * 50}

    async def send(message):
        pass

    for method, path in (("GET", "/api/ask"), ("POST", "/elsewhere")):
        inner.entered = False
        asyncio.run(middleware({"type": "http", "method": method, "path": path, "headers": []}, receive, send))
        assert inner.entered, (method, path)


# ---------------------------------------------------------------- in the app
@pytest.fixture
def web_on(monkeypatch):
    monkeypatch.setattr(settings, "ASK_WEB", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "made-up-key")


def test_each_route_has_its_limit_and_a_body_at_the_limit_still_works(web_on, make_client, fakes):
    client = make_client()
    client.app.state.answer_model = FakeModel()
    headers = {**session_of(client), "content-type": "application/json"}

    def padded(value, size):
        text = json.dumps(value)
        return text + " " * (size - len(text))              # JSON may end in spaces: a body of exactly ``size`` bytes

    for path, limit, ok in (("/api/ask", settings.ASK_MAX_BODY_BYTES, 200),
                            ("/api/chat", settings.CHAT_MAX_BODY_BYTES, 200),
                            ("/api/chat/web", settings.WEB_MAX_BODY_BYTES, 403)):      # 403: the made-up ticket, read
        value = {"question": "q"} if path != "/api/chat/web" else {"question": "q", "answer": "", "ticket": "made-up"}
        r = client.post(path, content=padded(value, limit), headers=headers)
        assert r.status_code == ok, (path, r.text)
        if ok == 403:
            assert r.json()["error"] == "ticket_refused"
        r = client.post(path, content=padded(value, limit + 1), headers=headers)
        assert r.status_code == 413 and r.json()["error"] == "request_too_large", path
    fakes.seen.clear()
    assert client.post("/api/ask", content=padded({"question": "q"}, settings.ASK_MAX_BODY_BYTES + 1),
                       headers=headers).status_code == 413
    assert "embed" not in fakes.seen                         # the route was not entered


def test_the_session_route_takes_a_token_of_the_longest_kind_and_an_unknown_path_the_smallest_limit(client, fakes):
    r = client.post("/api/session", json={"token": "t" * settings.SESSION_TOKEN_CHARS})
    assert r.status_code == 200 and fakes.seen["verify"] == "t" * settings.SESSION_TOKEN_CHARS
    smallest = min(settings.ASK_MAX_BODY_BYTES, settings.CHAT_MAX_BODY_BYTES, settings.WEB_MAX_BODY_BYTES)
    assert client.post("/api/nothing-here", content="x" * smallest, headers={"content-type": "application/json"}).status_code == 404
    assert client.post("/api/nothing-here", content="x" * (smallest + 1),
                       headers={"content-type": "application/json"}).status_code == 413


def test_a_refused_body_carries_the_cors_headers_and_the_request_id(client):
    r = client.post("/api/ask", content="x" * (settings.ASK_MAX_BODY_BYTES + 1),
                    headers={"content-type": "application/json", "origin": ORIGIN})
    assert r.status_code == 413 and r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["x-request-id"] and r.headers["cache-control"] == "no-store"
