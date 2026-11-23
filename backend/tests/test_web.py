"""The web step (ASK_WEB): the ticket, how many searches, the results kept, the web call, its check and its
route. A fake search service and a fake model: no network, no key. Every text here is made up."""

import base64
import json
import logging
from datetime import datetime, timezone

import httpx
import pytest

from app import answer_graph, answer_model, main, settings, web_step
from app.answer_model import Reply

from test_ask import Fakes, fakes, make_client, session_of  # noqa: F401  (fakes and make_client are fixtures)
from test_chat import THREAD, FakeModel, claude, lines_of, response, text_block

QUESTION = "What was the made-up rate of a letter to a made-up place?"
PAGE_TEXT = "Made-up text: the made-up rate of a letter was 25 centavos, paid with a made-up stamp."
RESULTS = [
    {"title": "A made-up page about rates", "url": "https://stamps.example/rates.pdf", "content": PAGE_TEXT, "score": 0.9},
    {"title": "Another made-up page", "url": "https://other.example/a", "content": "Nothing about rates here.", "score": 0.5},
]
ACCOUNT_USED = 937           # a number of the account no log may hold
LATE_IN_A_MONTH = datetime(2026, 11, 30, 23, tzinfo=timezone.utc).timestamp()        # 948 searches allowed


def at(*parts):
    return datetime(*parts, tzinfo=timezone.utc).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeTavily:
    def __init__(self):
        self.configured = True
        self.used = ACCOUNT_USED                 # under the allowance late in a month (the route tests' clock)
        self.outcome = ("ok", RESULTS)
        self.queries, self.reads = [], 0

    def usage(self):
        self.reads += 1
        return self.used

    def search(self, query):
        self.queries.append(query)
        return self.outcome


class WebModel(FakeModel):
    def __init__(self):
        super().__init__()
        self.webs = []
        self.web_reply = None

    def write_web(self, question, results, earlier=""):
        self.webs.append((question, results, earlier))
        if self.web_reply is not None:
            return self.web_reply
        return Reply(state="ok", input_tokens=700, output_tokens=40, blocks=[
            {"text": "A letter to the made-up place cost 25 centavos.", "citations": [{"document": 0, "cited_text": "the made-up rate of a letter was 25 centavos"}]},
            {"text": " Nobody backs this one.", "citations": []}])


PART = Reply(state="ok", input_tokens=900, output_tokens=60, blocks=[
    {"text": "The made-up issue has one stamp.", "citations": [{"document": 0, "cited_text": "stamp 1"}]},
    {"text": f"\n{answer_model.PART_ONLY}", "citations": []}])
NOT_COVERED = Reply(state="ok", blocks=[{"text": answer_model.NOT_COVERED, "citations": []}])
OUT = Reply(state="ok", blocks=[{"text": answer_model.OUT_OF_SCOPE, "citations": []}])


@pytest.fixture
def web_on(monkeypatch):
    monkeypatch.setattr(settings, "ASK_WEB", True)
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "made-up-key")


@pytest.fixture
def model():
    return WebModel()


@pytest.fixture
def tavily():
    return FakeTavily()


@pytest.fixture
def web_client(web_on, make_client, model, tavily):
    def build(**kwargs):
        client = make_client(**kwargs)
        client.app.state.answer_model = model
        client.app.state.web.client = tavily
        client.app.state.web.searches.now = lambda: LATE_IN_A_MONTH
        return client
    return build


def chat(client, headers, question="q", thread=None):
    body = {"question": question, **({"thread": thread} if thread is not None else {})}
    evidence, answer = lines_of(client.post("/api/chat", json=body, headers=headers))
    return evidence["evidence"], answer["answer"]


def web(client, headers, question, answer, ticket):
    return client.post("/api/chat/web", json={"question": question, "answer": answer, "ticket": ticket}, headers=headers)


def logged(run):
    records = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())
    log = logging.getLogger("oxcart.ask")
    log.addHandler(handler)
    try:
        result = run()
    finally:
        log.removeHandler(handler)
    return result, records


# ---------------------------------------------------------------- off: everything as before
def test_with_the_setting_off_the_route_does_not_exist_and_answers_as_any_unknown_path(make_client):
    assert not settings.ASK_WEB
    client = make_client()
    assert client.app.state.web is None
    r = client.post("/api/chat/web", json={"question": "q", "answer": "", "ticket": "t"}, headers=session_of(client))
    unknown = client.post("/api/chat/nothing-here", json={"question": "q"})
    assert r.status_code == unknown.status_code == 404 and r.json() == unknown.json()
    # a body far too large is not even read: the route is not there
    assert client.post("/api/chat/web", content="x" * 20000, headers={"content-type": "application/json"}).status_code == 404


def test_with_the_setting_off_the_chat_reply_carries_no_ticket_and_its_log_line_is_as_before(make_client, model, tavily):
    client = make_client()
    client.app.state.answer_model = model
    model.reply = NOT_COVERED
    (_, answer), records = logged(lambda: chat(client, session_of(client)))
    assert answer == {"state": "not_covered"}
    line = json.loads(next(r for r in records if '"event": "chat"' in r))
    assert "web_ticket" not in line
    assert tavily.reads == 0 and tavily.queries == []


# ---------------------------------------------------------------- the ticket
def test_a_ticket_verifies_once_for_its_question_and_answer_and_holds_no_text():
    clock = Clock(at(2026, 11, 10, 12))
    tickets = web_step.Tickets(now=clock)
    made = tickets.make(QUESTION, "The made-up answer.", "part")
    assert made["expires_in"] == settings.WEB_TICKET_SECONDS == 120
    payload = base64.urlsafe_b64decode(made["ticket"].split(".")[0] + "==").decode()
    assert payload.startswith("w1:") and payload.endswith(":part")
    for word in ("made-up", "rate", "answer"):
        assert word not in made["ticket"] and word not in payload
    # the same words with other spaces are the same question and the same answer
    assert tickets.redeem(made["ticket"], f"  {QUESTION} ", "The made-up\nanswer.") == "part"
    assert tickets.redeem(made["ticket"], QUESTION, "The made-up answer.") is None          # used
    empty = tickets.make(QUESTION, "", "not_covered")
    assert tickets.redeem(empty["ticket"], QUESTION, "") == "not_covered"


def test_a_tampered_expired_or_mismatched_ticket_is_refused():
    clock = Clock(at(2026, 11, 10, 12))
    tickets = web_step.Tickets(now=clock)
    ticket = tickets.make(QUESTION, "An answer.", "not_covered")["ticket"]
    payload, signature = ticket.split(".")
    raw = base64.urlsafe_b64decode(payload + "==").decode()
    as_part = base64.urlsafe_b64encode(raw.replace(":not_covered", ":part").encode()).decode().rstrip("=")
    later = base64.urlsafe_b64encode(raw.replace(raw.split(":")[2], str(int(clock.t) + 9999)).encode()).decode().rstrip("=")
    flipped = signature[:-2] + ("A" if signature[-2] != "A" else "B") + signature[-1]
    for bad in (f"{as_part}.{signature}", f"{later}.{signature}", f"{payload}.{flipped}", payload, "", "a.b.c", "x" * 400):
        assert tickets.redeem(bad, QUESTION, "An answer.") is None, bad
    assert tickets.redeem(ticket, "Another question?", "An answer.") is None
    assert tickets.redeem(ticket, QUESTION, "Another answer.") is None
    clock.t += settings.WEB_TICKET_SECONDS
    assert tickets.redeem(ticket, QUESTION, "An answer.") is None              # expired
    fresh = tickets.make(QUESTION, "An answer.", "part")["ticket"]
    clock.t += settings.WEB_TICKET_SECONDS - 1
    assert tickets.redeem(fresh, QUESTION, "An answer.") == "part"           # one second before it expires


def test_the_tickets_key_is_made_at_each_start(web_on, make_client):
    first, second = web_step.Tickets(), web_step.Tickets()
    ticket = first.make(QUESTION, "", "not_covered")["ticket"]
    assert second.redeem(ticket, QUESTION, "") is None and first.redeem(ticket, QUESTION, "") == "not_covered"
    one, two = make_client().app.state.web, make_client().app.state.web
    assert one.tickets._key != two.tickets._key and len(one.tickets._key) == 32


# ---------------------------------------------------------------- how many searches
def test_the_share_of_the_month_gone_by_in_utc():
    assert web_step.month_share(at(2026, 11, 1)) == 0
    assert web_step.month_share(at(2026, 11, 16)) == pytest.approx(0.5)              # 30 days
    assert web_step.month_share(at(2026, 2, 15)) == pytest.approx(0.5)               # 28 days
    assert web_step.month_share(at(2026, 2, 8)) == pytest.approx(0.25)
    assert web_step.month_share(at(2026, 1, 16, 12)) == pytest.approx(0.5)           # 31 days
    assert web_step.month_share(at(2026, 12, 31, 23, 59, 59)) == pytest.approx(1, abs=1e-6)
    assert web_step.month_share(at(2027, 1, 1)) == 0


@pytest.mark.parametrize("when, allowed_at", [
    (at(2026, 11, 1, 0, 30), 30),            # a month's first hour: 30.64 searches allowed
    (at(2026, 11, 16), 489),                 # mid-month of 30 days: 490
    (at(2026, 2, 8), 259),                   # a quarter of a 28-day month: 260
    (at(2026, 1, 16, 12), 489),              # mid-month of 31 days: 490
    (at(2026, 12, 31, 23, 59), 949),         # the month's last minute: 949.98
])
def test_a_search_is_allowed_while_the_credits_used_are_under_the_months_share(when, allowed_at):
    for used, allowed in ((allowed_at, True), (allowed_at + 1, False)):
        searches = web_step.Searches(lambda: used, now=Clock(when))
        assert searches.allowed() is allowed, (used, allowed)
        assert searches.rule == "usage"


def test_the_usage_is_read_at_most_once_in_five_minutes_and_the_searches_made_since_are_added():
    clock, reads, used = Clock(at(2026, 11, 15, 12)), [], [465]      # 474.7 allowed, 474.8 five minutes later

    def read():
        reads.append(clock.t)
        return used[0]

    searches = web_step.Searches(read, now=clock)
    assert searches.allowed()
    for _ in range(9):
        searches.counted()
    clock.t += 299
    assert searches.allowed() and len(reads) == 1                    # 465 + 9
    searches.counted()
    assert not searches.allowed() and len(reads) == 1                # 465 + 10
    clock.t += 1
    used[0] = 466                                                    # the account counted only one of the ten
    assert searches.allowed() and len(reads) == 2                    # read again: 466, and nothing added since


def test_when_the_usage_cannot_be_read_thirty_searches_a_day_in_memory_starting_again_each_day():
    clock = Clock(at(2026, 11, 16, 23, 0))
    searches = web_step.Searches(lambda: None, now=clock)
    for _ in range(settings.WEB_SEARCHES_PER_DAY_FALLBACK):
        assert searches.allowed()
        searches.counted()
    assert not searches.allowed() and searches.rule == "per_day"
    clock.t = at(2026, 11, 17, 0, 0, 1)                              # a new day in UTC
    assert searches.allowed()


def test_one_log_line_when_the_rule_changes_naming_it_and_no_number_of_the_account():
    clock, used = Clock(at(2026, 11, 16)), [ACCOUNT_USED]
    searches = web_step.Searches(lambda: used[0], now=clock)

    def steps():
        searches.allowed()
        clock.t += 300
        searches.allowed()                                           # the same rule: no line
        used[0] = None
        clock.t += 300
        searches.allowed()
        used[0] = ACCOUNT_USED
        clock.t += 300
        searches.allowed()

    _, records = logged(steps)
    assert [json.loads(r) for r in records] == [{"event": "web_rule", "rule": "usage"}, {"event": "web_rule", "rule": "per_day"},
                                                {"event": "web_rule", "rule": "usage"}]
    assert str(ACCOUNT_USED) not in json.dumps(records)


# ---------------------------------------------------------------- the search service's client
def transport(handler):
    seen = []

    def handle(request):
        seen.append(request)
        return handler(request)
    return httpx.MockTransport(handle), seen


def test_one_search_is_the_request_asked_for(monkeypatch):
    mock, seen = transport(lambda request: httpx.Response(200, json={"results": RESULTS, "answer": None}))
    outcome = web_step.Tavily("made-up-key", mock).search("A question Costa Rica philately")
    assert outcome == ("ok", RESULTS)
    request = seen[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.tavily.com/search")
    assert request.headers["authorization"] == "Bearer made-up-key"
    assert json.loads(request.content) == {"query": "A question Costa Rica philately", "search_depth": "basic", "max_results": 5,
                                           "include_answer": False, "include_raw_content": False, "include_images": False,
                                           "topic": "general"}
    assert request.extensions["timeout"]["read"] == 6.0


def test_the_plan_used_up_a_failure_and_a_timeout_are_states_and_nothing_is_raised():
    def timeout(request):
        raise httpx.ReadTimeout("made-up", request=request)

    def broken(request):
        raise httpx.ConnectError("made-up", request=request)

    for handler, state in ((lambda r: httpx.Response(432, json={"detail": "x"}), "used_up"),
                           (lambda r: httpx.Response(500), "failed"), (lambda r: httpx.Response(200, text="not json"), "failed"),
                           (lambda r: httpx.Response(200, json={"results": "x"}), "failed"), (timeout, "timeout"), (broken, "failed")):
        assert web_step.Tavily("k", transport(handler)[0]).search("q") == (state, [])


def test_the_usage_is_read_from_its_route_and_anything_else_is_none():
    good = {"key": {"usage": 3}, "account": {"current_plan": "Made-up", "plan_usage": 12, "plan_limit": 1000}}
    mock, seen = transport(lambda request: httpx.Response(200, json=good))
    assert web_step.Tavily("made-up-key", mock).usage() == 12
    assert (seen[0].method, str(seen[0].url), seen[0].headers["authorization"]) == ("GET", "https://api.tavily.com/usage", "Bearer made-up-key")
    assert seen[0].extensions["timeout"]["read"] == 4.0

    def timeout(request):
        raise httpx.ConnectTimeout("made-up", request=request)

    for handler in (lambda r: httpx.Response(200, json={"account": {"plan_usage": "12", "plan_limit": 1000}}),
                    lambda r: httpx.Response(200, json={"account": {"plan_usage": True, "plan_limit": 1000}}),
                    lambda r: httpx.Response(200, json={"account": {"plan_usage": 12}}),
                    lambda r: httpx.Response(200, json={"usage": 12}), lambda r: httpx.Response(200, json=[1]),
                    lambda r: httpx.Response(401, json=good), timeout):
        assert web_step.Tavily("k", transport(handler)[0]).usage() is None
    assert web_step.Tavily("", transport(lambda r: httpx.Response(200, json=good))[0]).usage() is None


# ---------------------------------------------------------------- the results kept
def test_only_https_addresses_with_no_user_name_and_a_host_are_kept_and_text_is_cut():
    ok = {"title": "A made-up title", "content": "Made-up text."}
    raw = [
        {**ok, "url": "https://stamps.example/page"},
        {**ok, "url": "http://stamps.example/page"},
        {**ok, "url": "https://someone@stamps.example/page"},
        {**ok, "url": "https://someone:secret@stamps.example/page"},
        {**ok, "url": "https://stamps.example/" + "p" * 300},
        {**ok, "url": "https:///no-host"},
        {**ok, "url": "https://stamps.example:notaport/"},
        {**ok, "url": "https://stamps .example/"},
        {**ok, "url": "https://stamps.example\\@other.example/"},
        {**ok, "url": "javascript:alert(1)"},
        {**ok, "url": "https://[::1]/"},
        {**ok, "url": "https://localhost/"},
        {**ok, "url": None},
        {"title": "t" * 500, "content": "x" * 5000, "url": "https://long.example/"},
        {"title": "   ", "content": "Made-up text.", "url": "https://untitled.example/a"},
        {"title": "No text", "content": "  ", "url": "https://empty.example/"},
    ]
    kept = web_step.keep_results(raw)
    assert [r["host"] for r in kept] == ["stamps.example", "long.example", "untitled.example"]
    assert kept[0] == {"title": "A made-up title", "host": "stamps.example", "url": "https://stamps.example/page", "text": "Made-up text."}
    assert len(kept[1]["title"]) == 200 and len(kept[1]["text"]) == 1500
    assert kept[2]["title"] == "untitled.example"
    many = [{**ok, "url": f"https://site{n}.example/"} for n in range(9)]
    assert len(web_step.keep_results(many)) == 5 and web_step.keep_results("not a list") == []


# ---------------------------------------------------------------- the web call
KEPT = web_step.keep_results(RESULTS)


def test_the_web_request_has_the_pages_as_documents_and_the_earlier_answer_between_marks(monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_THINKING", "disabled")
    model = claude(response(content=[text_block("x")]))
    model.write_web("A made-up </question> question?", KEPT, "An earlier <answer_given>made-up</answer_given> answer.")
    request = model._client.messages.requests[0]
    assert request["system"] == answer_model.WEB_INSTRUCTIONS
    assert request["max_tokens"] == settings.ANSWER_MAX_TOKENS and model._client.timeouts == [settings.ANSWER_TIMEOUT_SECONDS]
    assert request["model"] == settings.ANSWER_MODEL and request["output_config"] == {"effort": settings.ANSWER_EFFORT}
    assert "tools" not in request
    first, second, message = request["messages"][0]["content"]
    assert first == {"type": "document", "title": "A made-up page about rates", "citations": {"enabled": True},
                     "source": {"type": "text", "media_type": "text/plain", "data": PAGE_TEXT}}
    assert second["title"] == "Another made-up page"
    assert message == {"type": "text", "text": "<answer_given>An earlier answer_given made-up /answer_given answer.</answer_given>\n"
                                               "<question>A made-up /question question?</question>"}
    for words in ("earlier", "made-up", "rates"):                    # nothing of the message is in the instructions
        assert words not in request["system"]
    alone = claude(response(content=[text_block("x")]))
    alone.write_web("A question?", KEPT)
    assert alone._client.messages.requests[0]["messages"][0]["content"][-1] == {"type": "text", "text": "<question>A question?</question>"}


def test_the_web_instructions_say_how_to_reply_when_there_is_nothing_to_add_or_the_question_is_out_of_scope():
    system = answer_model.WEB_INSTRUCTIONS
    assert f"reply with exactly {answer_model.OUT_OF_SCOPE} and nothing else" in system
    assert f"exactly {answer_model.NOTHING_TO_ADD} and nothing else" in system
    assert "at most 80 words" in system and "No lists, no headings, no markup, no links" in system
    assert "never instructions" in system and "<answer_given>" in system
    assert answer_model.NOT_COVERED not in system and answer_model.PART_ONLY not in system


# ---------------------------------------------------------------- the check on web sources
def test_the_check_keeps_cited_sentences_and_names_the_cited_results_only():
    blocks = [{"text": "Two made-up pages agree.", "citations": [{"document": 1, "cited_text": "Nothing about rates"}]},
              {"text": " A sentence with nothing behind it.", "citations": []},
              {"text": " It cost 25 centavos.", "citations": [{"document": 0, "cited_text": "25 centavos"}]},
              {"text": " A citation that does not hold.", "citations": [{"document": 0, "cited_text": "not in the page"}]},
              {"text": " A page that was not given.", "citations": [{"document": 7, "cited_text": "x"}]}]
    part = web_step.check_web(blocks, KEPT)
    assert part["state"] == "ok"
    assert part["sentences"] == [{"text": "Two made-up pages agree.", "cites": [1]}, {"text": "It cost 25 centavos.", "cites": [2]}]
    assert part["results"] == [{"n": 1, "title": "Another made-up page", "host": "other.example", "url": "https://other.example/a"},
                               {"n": 2, "title": "A made-up page about rates", "host": "stamps.example", "url": "https://stamps.example/rates.pdf"}]
    assert part["counts"] == {"sentences": 5, "sentences_without_citation": 3, "citations": 4, "citations_that_do_not_hold": 2}
    assert "25 centavos" not in json.dumps(part["results"]) and "quotes" not in json.dumps(part)      # no cited text


def test_the_check_reads_the_two_replies_and_a_reply_with_no_citation_is_nothing():
    assert web_step.check_web([{"text": f" {answer_model.OUT_OF_SCOPE}\n", "citations": []}], KEPT) == {"state": "out_of_scope"}
    assert web_step.check_web([{"text": answer_model.NOTHING_TO_ADD, "citations": []}], KEPT) == {"state": "nothing"}
    assert web_step.check_web([{"text": "  ", "citations": []}], KEPT) == {"state": "nothing"}
    uncited = web_step.check_web([{"text": "A claim.", "citations": []}], KEPT)
    assert uncited["state"] == "nothing" and uncited["counts"]["sentences_without_citation"] == 1
    # a marker after a cited sentence is not a sentence of the part
    tail = web_step.check_web([{"text": "It cost 25 centavos.", "citations": [{"document": 0, "cited_text": "25 centavos"}]},
                               {"text": f"\n{answer_model.NOTHING_TO_ADD}", "citations": []}], KEPT)
    assert [s["text"] for s in tail["sentences"]] == ["It cost 25 centavos."]


def test_an_answers_check_is_unchanged_by_the_shared_rule():
    evidence = {"issues": [], "passages": [{"doc_id": "D", "page": 1, "text": "Some made-up words."}]}
    draft = {"state": "ok", "blocks": [{"text": "The page holds words.", "citations": [{"document": 0, "cited_text": "made-up words"}]},
                                       {"text": " Not this.", "citations": []}]}
    answer = answer_graph.check({"evidence": evidence, "draft": draft})["answer"]
    assert answer == {"state": "ok", "sentences": [{"text": "The page holds words.", "cites": [1]}],
                      "sources": [{"n": 1, "kind": "passage", "index": 0, "title": "D, page 1", "quotes": ["made-up words"]}],
                      "counts": {"sentences": 2, "sentences_without_citation": 1, "citations": 1, "citations_that_do_not_hold": 0}}


# ---------------------------------------------------------------- the chat reply's ticket
def test_a_ticket_comes_with_not_covered_and_with_an_answer_in_part_only(web_client, model, tavily):
    client = web_client()
    headers = session_of(client)
    model.reply = PART
    _, answer = chat(client, headers)
    assert answer["state"] == "ok" and answer["covers"] == "part"
    assert set(answer["web"]) == {"ticket", "expires_in"} and answer["web"]["expires_in"] == 120
    model.reply = NOT_COVERED
    assert set(chat(client, headers)[1]) == {"state", "web"}
    for reply in (None, OUT, Reply(state="timeout")):                   # answered in full, out of scope, no answer
        model.reply = reply
        assert "web" not in chat(client, headers)[1]
    tavily.configured = False                                          # no key for the search service: never a ticket
    model.reply = NOT_COVERED
    assert "web" not in chat(client, headers)[1]


def test_no_ticket_when_no_search_is_allowed(web_client, model, tavily):
    client = web_client()
    tavily.used = 10_000
    model.reply = NOT_COVERED
    assert chat(client, session_of(client))[1] == {"state": "not_covered"}


# ---------------------------------------------------------------- the web route
def ticketed(client, model, headers, reply=PART):
    model.reply = reply
    evidence, answer = chat(client, headers, "And the rate?", THREAD)
    return evidence["question"], web_step.answer_text(answer), answer["web"]["ticket"]


def test_the_web_part_for_an_answer_in_part(web_client, model, tavily):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    assert text == "The made-up issue has one stamp."
    r = web(client, headers, question, text, ticket)
    assert r.status_code == 200, r.text
    part = r.json()
    assert part["state"] == "ok"
    assert part["sentences"] == [{"text": "A letter to the made-up place cost 25 centavos.", "cites": [1]}]
    assert part["results"] == [{"n": 1, "title": "A made-up page about rates", "host": "stamps.example", "url": "https://stamps.example/rates.pdf"}]
    assert part["counts"] == {"results_returned": 2, "results_kept": 2, "sentences": 2, "sentences_without_citation": 1,
                              "citations": 1, "citations_that_do_not_hold": 0}
    assert part["calls"] == [{"purpose": "web", "state": "ok", "input_tokens": 700, "output_tokens": 40, "seconds": 0.0}]
    # the query is the question as it was searched (the follow-up rewritten) and the fixed words, nothing else
    assert question == model.standalone and tavily.queries == [f"{question} Costa Rica philately"]
    assert model.webs == [(question, web_step.keep_results(RESULTS), text)]
    assert web(client, headers, question, text, ticket).status_code == 403            # a ticket is good once


def test_for_not_covered_no_earlier_answer_is_given_and_the_suffix_can_be_empty(web_client, model, tavily, monkeypatch):
    monkeypatch.setattr(settings, "WEB_QUERY_SUFFIX", "")
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers, NOT_COVERED)
    assert text == ""
    assert web(client, headers, question, "", ticket).json()["state"] == "ok"
    assert model.webs[0][2] == "" and tavily.queries == [question]


def test_a_ticket_is_refused_for_another_question_or_answer(web_client, model):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    for q, a, t in ((question, "Another answer.", ticket), ("Another question?", text, ticket), (question, text, "made.up")):
        r = web(client, headers, q, a, t)
        assert r.status_code == 403 and r.json()["error"] == "ticket_refused"
        assert "made-up" not in r.text
    assert model.webs == []


def test_the_web_route_has_the_chat_routes_guard(web_client, model, monkeypatch):
    monkeypatch.setattr(settings, "EVAL_ACCESS_KEY", "s" * 32)
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    assert web(client, {}, question, text, ticket).status_code == 401
    assert web(client, {"x-oxcart-eval": "wrong"}, question, text, ticket).status_code == 401
    assert web(client, {"x-oxcart-eval": "s" * 32}, question, text, ticket).status_code == 200      # the eval's way in
    big = json.dumps({"question": question, "answer": text, "ticket": "t" * (settings.WEB_MAX_BODY_BYTES)})
    r = client.post("/api/chat/web", content=big, headers={**headers, "content-type": "application/json"})
    assert r.status_code == 413
    for body in ({"question": question, "answer": text, "ticket": ticket, "thread": []}, {"question": question, "answer": "a" * 1201, "ticket": ticket},
                 {"question": "q" * 301, "answer": "", "ticket": ticket}, {"question": question, "answer": text}):
        r = client.post("/api/chat/web", json=body, headers=headers)
        assert r.status_code == 422 and r.json()["error"] == "invalid_request"


def test_a_web_request_counts_as_a_question_for_the_visitor(web_client, model, monkeypatch):
    monkeypatch.setattr(settings, "ASK_LIMIT_PER_MINUTE", 2)
    client = web_client()
    headers = {**session_of(client), "x-forwarded-for": "203.0.113.9"}
    question, text, ticket = ticketed(client, model, headers)                 # one
    assert web(client, headers, question, text, ticket).status_code == 200    # two
    r = web(client, headers, question, text, ticket)
    assert r.status_code == 429 and r.json()["error"] == "visitor_minute_limit"


def test_the_web_call_is_taken_from_the_days_allowance_before_any_search(web_client, model, tavily, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_LIMIT_PER_DAY", 3)
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)                 # calls 1 and 2: rewrite, write
    assert web(client, headers, question, text, ticket).json()["state"] == "ok"          # call 3
    model.reply = NOT_COVERED
    assert chat(client, headers)[1] == {"state": "daily_cap"}                 # the web call was counted: none left, no ticket


def test_a_web_part_with_no_model_call_left_makes_no_search(web_client, model, tavily, monkeypatch):
    monkeypatch.setattr(settings, "ANSWER_LIMIT_PER_DAY", 2)
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)                 # calls 1 and 2
    part = web(client, headers, question, text, ticket).json()
    assert part["state"] == "unavailable" and part["calls"] == []
    assert tavily.queries == [] and model.webs == []


@pytest.mark.parametrize("outcome, state", [(("used_up", []), "unavailable"), (("timeout", []), "unavailable"),
                                            (("failed", []), "unavailable"), (("ok", []), "nothing"),
                                            (("ok", [{"title": "t", "url": "http://plain.example/", "content": "x"}]), "nothing")])
def test_a_search_that_gives_nothing_to_show(web_client, model, tavily, outcome, state):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    tavily.outcome = outcome
    part = web(client, headers, question, text, ticket).json()
    assert part["state"] == state and "sentences" not in part and "results" not in part
    assert model.webs == [] and part["calls"] == []


@pytest.mark.parametrize("reply, state", [(Reply(state="ok", blocks=[{"text": answer_model.NOTHING_TO_ADD, "citations": []}]), "nothing"),
                                          (Reply(state="ok", blocks=[{"text": answer_model.OUT_OF_SCOPE, "citations": []}]), "out_of_scope"),
                                          (Reply(state="ok", blocks=[{"text": "A claim.", "citations": []}]), "nothing"),
                                          (Reply(state="timeout"), "unavailable")])
def test_what_the_web_call_replies(web_client, model, reply, state):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    model.web_reply = reply
    part = web(client, headers, question, text, ticket).json()
    assert part["state"] == state and "results" not in part
    assert [c["purpose"] for c in part["calls"]] == ["web"]


def test_with_no_search_allowed_at_the_web_request_none_is_made(web_client, model, tavily):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    client.app.state.web.searches._read_at = None                   # read again now: the month's share is spent
    tavily.used = 10_000
    assert web(client, headers, question, text, ticket).json()["state"] == "unavailable"
    assert tavily.queries == [] and model.webs == []


def test_the_web_log_line_has_counts_timings_and_states_and_no_text(web_client, model, tavily):
    client = web_client()
    headers = session_of(client)
    question, text, ticket = ticketed(client, model, headers)
    r, records = logged(lambda: web(client, headers, question, text, ticket))
    assert r.json()["state"] == "ok"
    line = json.loads(next(rec for rec in records if '"event": "web"' in rec))
    assert (line["state"], line["ticket"], line["reason"], line["rule"]) == ("ok", "part", None, "usage")
    assert line["counts"]["results_kept"] == 2 and set(line["timings"]) == {"search_ms", "write_ms", "total_ms"}
    assert [c["purpose"] for c in line["model_calls"]] == ["web"]
    # the request id is random hex: taken out, so a number is not found in it by chance
    everything = json.dumps([{k: v for k, v in json.loads(rec).items() if k != "request_id"} if rec.startswith("{") else rec for rec in records])
    for secret in (question, "made-up", "stamps.example", "rates.pdf", "https://", "centavos", str(tavily.used), ticket):
        assert secret not in everything, secret


# ---------------------------------------------------------------- later turns
def test_a_later_turn_can_carry_an_earlier_answer_and_nothing_else(web_client, model):
    client = web_client()
    headers = session_of(client)
    turn = {**THREAD[0], "web": {"state": "ok", "sentences": [{"text": "A web sentence.", "cites": [1]}]}}
    r = client.post("/api/chat", json={"question": "And then?", "thread": [turn]}, headers=headers)
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"
    chat(client, headers, "And then?", THREAD)
    assert model.rewrites[-1][1] == THREAD                                 # the earlier turns, as the page sent them


def test_the_app_holds_the_web_step_only_with_the_setting_on(make_client, monkeypatch):
    assert main.create_app(public=True).state.web is None
    monkeypatch.setattr(settings, "ASK_WEB", True)
    assert isinstance(main.create_app(public=True).state.web, web_step.WebStep)
