"""The graph link with a fake driver that refuses N times. No network, no database."""

import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import ask_service, main, settings
from app.graph_link import GraphLink, Unavailable

import config


class ServiceUnavailable(Exception):
    """Same class NAME as the driver's error for "no connection right now"."""


class SessionExpired(Exception):
    pass


class CypherSyntaxError(Exception):
    """A query error: retrying it would give the same error."""


class FakeDriver:
    """Each use of a session raises the next error in ``refusals``; after that it answers."""

    def __init__(self, refusals=()):
        self.refusals = list(refusals)
        self.sessions = 0
        self.session_kwargs = None

    def session(self, **kwargs):
        self.session_kwargs = kwargs
        driver = self

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def run(self, query, **params):
                driver.sessions += 1
                if driver.refusals:
                    raise driver.refusals.pop(0)
                return types.SimpleNamespace(consume=lambda: None, query=query)

        return Session()


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def link_for(driver, clock, startup=30.0, question=8.0, every=0.5):
    return GraphLink(lambda: driver, "db", startup_budget=startup, question_budget=question, every=every,
                     sleep=clock.sleep, clock=clock.time)


def test_startup_keeps_trying_until_a_connection_opens():
    driver, clock = FakeDriver([ServiceUnavailable(), SessionExpired(), ServiceUnavailable()]), Clock()
    link = link_for(driver, clock)
    assert link.state == "connecting"
    assert link.warm() is True
    assert link.state == "connected" and link.attempts == 4 and clock.slept == [0.5, 0.5, 0.5]
    assert driver.session_kwargs["default_access_mode"] == "READ" and driver.session_kwargs["database"] == "db"


def test_startup_gives_up_when_its_budget_is_spent_and_says_so():
    driver, clock = FakeDriver([ServiceUnavailable() for _ in range(1000)]), Clock()
    link = link_for(driver, clock, startup=30.0)
    assert link.warm() is False
    assert link.state == "unavailable"
    assert 55 <= link.attempts <= 61 and clock.now <= 30.0        # every half second, never past the budget


def test_a_question_retries_inside_its_own_budget():
    driver, clock = FakeDriver([ServiceUnavailable(), ServiceUnavailable()]), Clock()
    link = link_for(driver, clock)
    assert link.read(lambda session: session.run("the lookup's query") and "the card") == "the card"
    assert link.state == "connected" and clock.slept == [0.5, 0.5] and driver.sessions == 3


def test_a_question_reports_unavailable_when_its_budget_is_spent():
    driver, clock = FakeDriver([SessionExpired() for _ in range(1000)]), Clock()
    link = link_for(driver, clock, question=8.0)
    with pytest.raises(Unavailable) as error:
        link.read(lambda session: session.run("RETURN 1"))
    assert str(error.value) == "SessionExpired"                     # the class name, nothing else
    assert 15 <= link.attempts <= 17 and clock.now <= 8.0 and link.state == "unavailable"
    driver.refusals.clear()
    assert link.read(lambda session: session.run("q") and "back") == "back" and link.state == "connected"   # it recovers by itself


def test_a_query_error_is_not_retried():
    driver, clock = FakeDriver([CypherSyntaxError("near line 1")]), Clock()
    link = link_for(driver, clock)
    with pytest.raises(Unavailable) as error:
        link.read(lambda session: session.run("RETURN"))
    assert str(error.value) == "CypherSyntaxError" and link.attempts == 1 and clock.slept == []
    assert link.state == "connecting"                              # says nothing about the connection


# ---------------------------------------------------------------- through the app
@pytest.fixture
def app_with(monkeypatch):
    opened = []

    def build(driver, warm=True, every=0.01, startup=2):
        monkeypatch.setattr(settings, "GRAPH_WARM_ON_START", warm)
        monkeypatch.setattr(settings, "GRAPH_RETRY_EVERY_SECONDS", every)
        monkeypatch.setattr(settings, "GRAPH_STARTUP_BUDGET_SECONDS", startup)
        monkeypatch.setattr(settings, "GRAPH_QUESTION_BUDGET_SECONDS", 1)
        monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "k" * 40)
        monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "e" * 32)
        monkeypatch.setattr(config, "OPENAI_API_KEY", None)
        monkeypatch.setattr(config, "neo4j_driver", lambda: types.SimpleNamespace(session=driver.session, close=lambda: None))
        client = TestClient(main.create_app(public=True))
        client.__enter__()
        opened.append(client)
        return client

    yield build
    for client in opened:
        client.__exit__(None, None, None)


def test_health_answers_at_once_and_says_where_the_graph_link_is(app_with):
    gate = {"open": False}

    class Slow(FakeDriver):
        def session(self, **kwargs):
            if not gate["open"]:
                self.refusals = [ServiceUnavailable()]            # refuse for as long as the gate is shut
            return super().session(**kwargs)

    client = app_with(Slow(), startup=5)
    t0 = time.time()
    body = client.get("/api/health").json()
    assert body == {"status": "ok", "graph": "connecting"} and time.time() - t0 < 1.0   # it did not wait for the graph
    gate["open"] = True
    for _ in range(200):
        if client.get("/api/health").json()["graph"] == "connected":
            break
        time.sleep(0.01)
    assert client.get("/api/health").json() == {"status": "ok", "graph": "connected"}


def test_health_says_unavailable_when_startup_could_not_connect(app_with):
    client = app_with(FakeDriver([ServiceUnavailable() for _ in range(100000)]), startup=0)
    for _ in range(200):
        if client.get("/api/health").json()["graph"] != "connecting":
            break
        time.sleep(0.01)
    assert client.get("/api/health").json() == {"status": "ok", "graph": "unavailable"}


def test_a_question_gets_its_catalogue_block_after_refusals(app_with, monkeypatch):
    driver = FakeDriver([ServiceUnavailable(), SessionExpired()])
    client = app_with(driver, warm=False)

    def lookup(session, question, k=3, question_vector=None, use_text=None):
        session.run("the lookup's query")                           # this is where a refusal surfaces
        return [{"issue_id": "CR-1", "title": "An issue", "score": 1.0, "matched_by": ["text"], "card": {"issue_id": "CR-1"}}]

    monkeypatch.setitem(sys.modules, "catalogue_lookup", types.SimpleNamespace(lookup=lookup))
    client.app.state.ask.search = lambda question, vector: []
    r = client.post("/api/ask", json={"question": "a question"}, headers={"x-oxcart-eval": "e" * 32})
    assert r.status_code == 200
    assert r.json()["mode"]["catalogue"] == "full-text index" and r.json()["issues"][0]["issue_id"] == "CR-1"
    assert driver.sessions == 3 and client.get("/api/health").json()["graph"] == "connected"


def test_a_question_says_the_catalogue_is_unavailable_when_the_graph_keeps_refusing(app_with, monkeypatch):
    driver = FakeDriver([ServiceUnavailable() for _ in range(100000)])
    client = app_with(driver, warm=False)
    monkeypatch.setitem(sys.modules, "catalogue_lookup",
                        types.SimpleNamespace(lookup=lambda session, question, **kw: session.run("q")))
    client.app.state.ask.search = lambda question, vector: [{"doc_id": "D", "page": 1, "chunk_type": "text", "text": "t", "score": 1.0}]
    r = client.post("/api/ask", json={"question": "a question"}, headers={"x-oxcart-eval": "e" * 32})
    assert r.status_code == 200
    assert r.json()["mode"]["catalogue"] == "unavailable" and len(r.json()["passages"]) == 1
