"""The web step (ASK_WEB): one web search for a question our sources do not cover, or cover only in part,
and a short part written from the pages it returned.

    POST /api/chat     an answer "not_covered", or "ok" with covers "part", and a search allowed
                       -> the answer carries web: {"ticket", "expires_in"}
    POST /api/chat/web the question as it was searched, the answer's text, the ticket
                       -> the ticket checked -> a search allowed? -> one model call taken from the day's
                          allowance -> one search -> the results kept -> the web call -> the same check as
                          an answer's -> {"state", "sentences", "results", "counts", "calls"}

It is its own request, made by the page once the answer is on screen, so the answer waits no longer
than it did before this step existed.

**The ticket** is the backend's signature (HMAC-SHA256) over a random id, a digest of the question as it
was searched, a digest of the answer's text, the state and an expiry. It holds no text. Its key is made when
the process starts and is held in memory only: no secret is configured for it, and a restart only makes the
tickets of the last two minutes invalid. A ticket is good once: its id is kept until it expires.

**How many searches.** The account's credits used this month are read from the search service's usage
route, at most once in five minutes. That route runs behind the searches made, so the searches this process
made in the last two hours are added to what it says. A search is allowed while that is under a share of the month
(settings.py, ``WEB_SEARCHES_*``, ``WEB_USAGE_LAG_SECONDS``). When the usage cannot
be read, a fixed number a day, counted in memory. Nothing is remembered across restarts: the next read gives
the true number.

**What goes where.** The query is the question as it was searched and fixed words (``WEB_QUERY_SUFFIX``):
nothing a model wrote. The model is given the kept results as documents and, in the part case, the answer
already given, as text to read. The page gets the sentences and, for each cited result only, its title, host
and address; no cited text and no uncited result.

Nothing here raises. Logs carry counts, timings, states, the rule in use and error class names: never a
question, a result, an address, a host or a number of the account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from app import settings
from app.answer_graph import _call, cited_sentences
from app.answer_model import NOT_COVERED, NOTHING_TO_ADD, OUT_OF_SCOPE
from app.public_guard import _b64, _unb64

log = logging.getLogger("oxcart.ask")

TICKET_STATES = ("not_covered", "part")
# The states of the web route's reply. The page draws the block for "ok"; under "not covered" one line for
# "nothing"; nothing at all for "unavailable" (no search was made, it failed, or the plan is used up) and for
# "out_of_scope" (the web call judged the question outside the scope).
STATES = ("ok", "nothing", "unavailable", "out_of_scope")


# --------------------------------------------------------------------------- the ticket
def _digest(text: str) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode("utf-8")).hexdigest()


def answer_text(answer: dict) -> str:
    """The answer's text as the page sends it back: its shown sentences, joined."""
    return " ".join(sentence["text"] for sentence in answer.get("sentences") or [])


class Tickets:
    """Tickets for the web step, signed with a key made when this object is (at the process's start)."""

    MAX_USED = 50_000

    def __init__(self, now: Callable[[], float] = time.time):
        self._key = os.urandom(32)
        self.now = now
        self._used: dict[str, float] = {}
        self._lock = threading.Lock()

    def _signature(self, payload: str, question: str, answer: str) -> bytes:
        message = "\n".join((payload, _digest(question), _digest(answer))).encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).digest()

    def make(self, question: str, answer: str, state: str) -> dict:
        assert state in TICKET_STATES
        expires = int(self.now() + settings.WEB_TICKET_SECONDS)
        payload = f"w1:{secrets.token_urlsafe(12)}:{expires}:{state}"
        token = f"{_b64(payload.encode('ascii'))}.{_b64(self._signature(payload, question, answer))}"
        return {"ticket": token, "expires_in": settings.WEB_TICKET_SECONDS}

    def redeem(self, token: str, question: str, answer: str) -> Optional[str]:
        """The ticket's state when it verifies for this question and answer, is not expired and was not
        used; it is then used. None otherwise."""
        if not token or token.count(".") != 1 or len(token) > 300:
            return None
        try:
            payload_part, signature_part = token.split(".")
            payload = _unb64(payload_part).decode("ascii")
            version, ticket_id, expires, state = payload.split(":")
            if version != "w1" or state not in TICKET_STATES:
                return None
            if not hmac.compare_digest(_unb64(signature_part), self._signature(payload, question, answer)):
                return None
            t = self.now()
            if int(expires) <= t:
                return None
        except Exception:
            return None
        with self._lock:
            self._used = {k: v for k, v in self._used.items() if v > t}     # an expired id is refused anyway
            if ticket_id in self._used or len(self._used) >= self.MAX_USED:
                return None
            self._used[ticket_id] = float(expires)
        return state


# --------------------------------------------------------------------------- how many searches
def month_share(t: float) -> float:
    """The share of the current month (UTC) gone by at ``t``, from 0 at its first instant to 1 at its end."""
    now = datetime.fromtimestamp(t, tz=timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    end = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
    return (t - start.timestamp()) / (end.timestamp() - start.timestamp())


class Searches:
    """Whether a web search is allowed now, by one of two rules:

    "usage"    the account's credits used, read at most once in WEB_USAGE_EVERY_SECONDS, plus the
               searches this process made in the last WEB_USAGE_LAG_SECONDS of the current month (the
               usage route runs behind, so a search just made is not in it yet), under
               WEB_SEARCHES_AT_MONTH_START + WEB_SEARCHES_OVER_THE_MONTH x month_share(now).
               After a restart the count is what the route says, which can miss the searches made
               shortly before it.
    "per_day"  when the usage could not be read: WEB_SEARCHES_PER_DAY_FALLBACK a day (UTC), in memory

    ``read_usage`` gives the credits used, or None when they could not be read. One log line each time the
    rule in use changes, naming the rule and nothing else."""

    def __init__(self, read_usage: Callable[[], Optional[int]], now: Callable[[], float] = time.time):
        self.read_usage, self.now = read_usage, now
        self._lock = threading.Lock()
        self._read_at: Optional[float] = None
        self._used = 0               # at the last read
        self._made: list = []        # when each search of this process was made, oldest first
        self._day = (0, 0)           # (day, searches made that day): every search, whatever the rule
        self.rule: Optional[str] = None

    def _set_rule(self, rule: str) -> None:
        if rule != self.rule:
            self.rule = rule
            log.info(json.dumps({"event": "web_rule", "rule": rule}))

    def allowed(self) -> bool:
        with self._lock:
            t = self.now()
            if self._read_at is None or t - self._read_at >= settings.WEB_USAGE_EVERY_SECONDS:
                used = self.read_usage()
                self._read_at = t
                if used is None:
                    self._set_rule("per_day")
                else:
                    self._used = used
                    self._set_rule("usage")
            if self.rule == "usage":
                # searches too recent to be in what the route says, and of this month (a new month starts from zero)
                now = datetime.fromtimestamp(t, tz=timezone.utc)
                since = max(t - settings.WEB_USAGE_LAG_SECONDS, datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())
                self._made = [made for made in self._made if made >= since]
                return self._used + len(self._made) < (settings.WEB_SEARCHES_AT_MONTH_START
                                                       + settings.WEB_SEARCHES_OVER_THE_MONTH * month_share(t))
            day, count = self._day
            return (count if day == int(t // 86400) else 0) < settings.WEB_SEARCHES_PER_DAY_FALLBACK

    def counted(self) -> None:
        """One search was made."""
        with self._lock:
            t = self.now()
            day = int(t // 86400)
            self._made = self._made[-5000:] + [t]
            self._day = (day, (self._day[1] if self._day[0] == day else 0) + 1)


# --------------------------------------------------------------------------- the search service
class Tavily:
    """The two calls to the search service. Tests replace this whole object, or pass an httpx transport."""

    def __init__(self, key: str, transport: Any = None):
        self.key, self.transport = key, transport

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def _request(self, method: str, url: str, timeout: float, body: Optional[dict] = None):
        import httpx

        with httpx.Client(timeout=timeout, transport=self.transport) as client:
            return client.request(method, url, json=body, headers={"Authorization": f"Bearer {self.key}"})

    def usage(self) -> Optional[int]:
        """The account's credits used this month, or None (no key, an error, a timeout, another shape)."""
        if not self.configured:
            return None
        try:
            response = self._request("GET", settings.TAVILY_USAGE_URL, settings.WEB_USAGE_TIMEOUT_SECONDS)
            if response.status_code != 200:
                return None
            account = response.json().get("account")
            used, limit = account.get("plan_usage"), account.get("plan_limit")
            if type(used) is int and type(limit) is int and used >= 0:
                return used
            return None
        except Exception as exc:
            log.warning("web usage not read: %s", type(exc).__name__)
            return None

    def search(self, query: str) -> tuple[str, list]:
        """("ok", the raw results), or ("used_up" | "timeout" | "failed", [])."""
        import httpx

        body = {"query": query, "search_depth": "basic", "max_results": settings.WEB_MAX_RESULTS,
                "include_answer": False, "include_raw_content": False, "include_images": False, "topic": "general",
                "exclude_domains": list(settings.WEB_DOMAINS_LEFT_OUT)}
        try:
            response = self._request("POST", settings.TAVILY_SEARCH_URL, settings.WEB_SEARCH_TIMEOUT_SECONDS, body)
            if response.status_code == 432:
                return "used_up", []
            if response.status_code != 200:
                return "failed", []
            results = response.json().get("results")
            return ("ok", results) if isinstance(results, list) else ("failed", [])
        except httpx.TimeoutException as exc:
            log.warning("web search failed: %s", type(exc).__name__)
            return "timeout", []
        except Exception as exc:
            log.warning("web search failed: %s", type(exc).__name__)
            return "failed", []


# --------------------------------------------------------------------------- the results kept
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+")


def host_of(url: Any) -> Optional[str]:
    """The host of an address that may be shown and linked: https, at most WEB_URL_CHARS characters, no user
    name or password, no space, control character or backslash, and a host name that parses and is a name
    (not numbers and dots). None otherwise."""
    if not isinstance(url, str) or not url or len(url) > settings.WEB_URL_CHARS:
        return None
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == "\\" for c in url) or not url.lower().startswith("https://"):
        return None
    try:
        parts = urlsplit(url)
        parts.port                                   # raises on a port that does not parse
    except ValueError:
        return None
    if parts.scheme != "https" or "@" in parts.netloc or parts.username is not None or parts.password is not None:
        return None
    host = parts.hostname or ""
    if not _HOST.fullmatch(host) or not any(c.isalpha() for c in host):     # a host of numbers and dots is an address, not a name
        return None
    return host


def left_out(host: str) -> bool:
    """Is this host one of the sites whose pages are never used (settings.WEB_HOST_LABELS_LEFT_OUT, WEB_DOMAINS_LEFT_OUT)?"""
    labels = host.split(".")
    return (any(label in settings.WEB_HOST_LABELS_LEFT_OUT for label in labels)
            or any(host == domain or host.endswith("." + domain) for domain in settings.WEB_DOMAINS_LEFT_OUT))


def keep_results(raw: Any) -> list:
    """[{"title", "host", "url", "text"}] of the results that may be shown, in the order returned."""
    kept = []
    for result in raw if isinstance(raw, list) else []:
        if len(kept) == settings.WEB_MAX_RESULTS:
            break
        if not isinstance(result, dict):
            continue
        host = host_of(result.get("url"))
        text = result.get("content")
        text = text.strip()[: settings.WEB_TEXT_CHARS] if isinstance(text, str) else ""
        if host is None or not text or left_out(host):
            continue
        title = " ".join(result["title"].split()) if isinstance(result.get("title"), str) else ""
        kept.append({"title": (title or host)[: settings.WEB_TITLE_CHARS], "host": host, "url": result["url"], "text": text})
    return kept


# --------------------------------------------------------------------------- the check
def check_web(blocks: list, results: list) -> dict:
    """The same rule as an answer's: a sentence with no citation that holds is removed. The reply's part of
    the state, sentences, cited results and counts."""
    whole = "".join(block.get("text", "") for block in blocks).strip()
    if not whole or whole.startswith(NOTHING_TO_ADD):
        return {"state": "nothing"}
    if whole.startswith(OUT_OF_SCOPE):
        return {"state": "out_of_scope"}
    sources = [{"kind": "web", "index": i, "title": r["title"], "text": r["text"]} for i, r in enumerate(results)]
    sentences, used, counts = cited_sentences(blocks, sources, (NOTHING_TO_ADD, OUT_OF_SCOPE, NOT_COVERED))
    if not sentences:
        return {"state": "nothing", "counts": counts}
    cited = [{"n": u["n"], "title": results[u["index"]]["title"], "host": results[u["index"]]["host"],
              "url": results[u["index"]]["url"]} for u in used]
    return {"state": "ok", "sentences": sentences, "results": cited, "counts": counts}


# --------------------------------------------------------------------------- the step
class WebStep:
    """What the process holds for the web step: the ticket key, the search allowance, the search client."""

    def __init__(self, client: Any = None, now: Callable[[], float] = time.time):
        self.client = client if client is not None else Tavily(settings.TAVILY_API_KEY)
        self.tickets = Tickets(now=now)
        self.searches = Searches(lambda: self.client.usage(), now=now)

    def ticket_for(self, answer: dict, question: str) -> Optional[dict]:
        """A ticket for the chat reply's answer, when it asks for the web and a search is allowed."""
        if answer.get("state") == "not_covered":
            state, text = "not_covered", ""
        elif answer.get("state") == "ok" and answer.get("covers") == "part":
            state, text = "part", answer_text(answer)
        else:
            return None                         # out of scope, answered in full, or no answer for another reason
        if not self.client.configured or not self.searches.allowed():
            return None
        return self.tickets.make(question, text, state)

    def run(self, question: str, earlier: str, state: str, model: Any, take: Callable[[], bool]) -> tuple[dict, dict]:
        """(the reply, what the log line adds) for a ticket that was redeemed with ``state``."""
        started = time.time()
        timings: dict = {}
        note: dict = {"reason": None, "results_returned": 0, "results_kept": 0}
        calls: list = []

        def done(part: dict, reason: Optional[str] = None) -> tuple[dict, dict]:
            timings["total_ms"] = round((time.time() - started) * 1000)
            note["reason"] = reason
            counts = {"results_returned": note["results_returned"], "results_kept": note["results_kept"],
                      **(part.pop("counts", None) or {})}
            return {**part, "counts": counts, "calls": calls}, {**note, "timings": timings}

        if not self.client.configured or not model.configured:
            return done({"state": "unavailable"}, "not_configured")
        if not self.searches.allowed():
            return done({"state": "unavailable"}, "not_allowed")
        # the model call is taken before the search, so a day whose calls are spent never spends a search
        if not take():
            return done({"state": "unavailable"}, "daily_cap")
        query = " ".join(f"{question} {settings.WEB_QUERY_SUFFIX}".split())
        self.searches.counted()
        searched = time.time()
        outcome, raw = self.client.search(query)
        timings["search_ms"] = round((time.time() - searched) * 1000)
        if outcome != "ok":
            return done({"state": "unavailable"}, outcome)
        results = keep_results(raw)
        note["results_returned"], note["results_kept"] = len(raw), len(results)
        if not results:
            return done({"state": "nothing"}, "no_result_kept")
        reply = model.write_web(question, results, earlier if state == "part" else "")
        calls.append(_call("web", reply))
        timings["write_ms"] = round(reply.seconds * 1000)
        if reply.state != "ok":
            return done({"state": "unavailable"}, reply.state)
        part = check_web(reply.blocks, results)
        return done(part, None if part["state"] == "ok" else part["state"])
