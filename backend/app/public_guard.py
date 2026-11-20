"""What stands between an anonymous visitor and the question path.

Three things, none of which needs a database:

* **Human check.** The page solves a Cloudflare Turnstile challenge once; this process
  verifies the result with Cloudflare and answers with a short-lived signed token. The
  page sends that token with each question. The token says only "a human check passed,
  until this time": it carries no identity and nothing is stored about the visitor.
* **Limits.** Questions per minute and per day for one visitor, and per day for the whole
  service, counted in this process's memory. A visitor is the address the host's proxy
  reports, kept only as a salted hash that dies with the process. The session token is
  counted too, with the same numbers: a question passes only when both the address and
  the token are under the limits, so changing address does not buy a new allowance.
* **The eval's way in.** A secret header, compared in constant time. With no secret
  configured that door does not exist. It skips the human check and the per-visitor
  limits, never the service's daily limit.

Nothing here logs a question, an address or a token.
"""

from __future__ import annotations

import base64
import collections
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Callable, Optional

from app import settings

SESSION_HEADER = "x-oxcart-session"
EVAL_HEADER = "x-oxcart-eval"


# --------------------------------------------------------------------------- session token
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_session(key: str, ttl: int, now: Optional[float] = None) -> str:
    """A signed token valid for ``ttl`` seconds. Raises when no signing key is configured."""
    if not key:
        raise RuntimeError("no session signing key")
    expires = int((now if now is not None else time.time()) + ttl)
    payload = f"v1:{expires}:{secrets.token_urlsafe(8)}".encode("ascii")
    signature = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def session_is_valid(token: str, key: str, now: Optional[float] = None) -> bool:
    if not key or not token or token.count(".") != 1 or len(token) > 300:
        return False
    try:
        payload_part, signature_part = token.split(".")
        payload, signature = _unb64(payload_part), _unb64(signature_part)
        expected = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        version, expires, _nonce = payload.decode("ascii").split(":")
        return version == "v1" and int(expires) > (now if now is not None else time.time())
    except Exception:
        return False


def eval_key_matches(given: str) -> bool:
    configured = settings.EVAL_ACCESS_KEY
    return bool(configured) and bool(given) and hmac.compare_digest(given.encode("utf-8"), configured.encode("utf-8"))


# --------------------------------------------------------------------------- human check
def verify_turnstile(token: str) -> str:
    """Ask Cloudflare whether the page's token is good: "ok", "failed" or "unavailable".

    "unavailable" covers every case where no verdict was obtained (no secret configured,
    network error, an answer that is not Cloudflare's JSON): the caller then refuses.
    """
    if not settings.TURNSTILE_SECRET or not token or len(token) > 2048:
        return "unavailable" if not settings.TURNSTILE_SECRET else "failed"
    try:
        import httpx

        response = httpx.post(settings.TURNSTILE_VERIFY_URL, timeout=6.0,
                              data={"secret": settings.TURNSTILE_SECRET, "response": token})
        if response.status_code != 200:
            return "unavailable"
        body = response.json()
        if body.get("success") is True:
            return "ok"
        if "internal-error" in (body.get("error-codes") or []):
            return "unavailable"
        return "failed"
    except Exception:
        return "unavailable"


# --------------------------------------------------------------------------- visitor key
_SALT = os.urandom(16)


def visitor_key(forwarded_for: Optional[str], peer: Optional[str], named: Optional[str] = None) -> str:
    """A salted hash of the visitor's address. The address itself is not kept.

    ``named`` is what the request carries in the header the host's edge sets with the
    visitor's address (settings.VISITOR_ADDRESS_HEADER); the caller passes it only when
    that setting names a header. With it, the visitor is that value. Without it (setting
    empty, or a request that does not carry the header) the rule is the older one: the
    entry TRUSTED_PROXY_HOPS from the right of X-Forwarded-For, or the socket's peer.
    """
    address = peer or "unknown"
    named = (named or "").strip()
    if named:
        address = named
    else:
        hops = settings.TRUSTED_PROXY_HOPS
        if hops > 0 and forwarded_for:
            entries = [e.strip() for e in forwarded_for.split(",") if e.strip()]
            if len(entries) >= hops:
                address = entries[-hops]      # counted from the right: the left side is whatever the client sent
    return hashlib.sha256(_SALT + address.encode("utf-8", "replace")).hexdigest()[:24]


def token_key(token: str) -> str:
    """A salted hash of a session token, to count the questions asked with it. The prefix
    keeps it apart from every visitor key."""
    return "token:" + hashlib.sha256(_SALT + b"token:" + token.encode("utf-8", "replace")).hexdigest()[:24]


# --------------------------------------------------------------------------- limits
class Limiter:
    """Per-visitor minute and day limits and a service-wide day limit, in memory.

    A question can be counted under two keys, the visitor's address and its session token:
    it passes only when both are under the limits, and it is then counted under both. A
    refused question is counted under neither.
    """

    MAX_VISITORS = 50_000

    def __init__(self, per_minute: int, per_day: int, global_per_day: int, now: Callable[[], float] = time.time):
        self.per_minute, self.per_day, self.global_per_day, self.now = per_minute, per_day, global_per_day, now
        self._lock = threading.Lock()
        self._minute: dict[str, collections.deque] = {}
        self._day: dict[str, tuple[int, int]] = {}
        self._global: tuple[int, int] = (0, 0)

    def check(self, visitor: Optional[str], token: Optional[str] = None) -> tuple[bool, str, int]:
        """(allowed, reason, seconds to wait). ``visitor=None`` is the eval: service limit only.
        ``token`` is the key of the session token the question came with, when there is one."""
        t = self.now()
        day = int(t // 86400)
        until_tomorrow = int((day + 1) * 86400 - t) + 1
        with self._lock:
            g_day, g_count = self._global
            if g_day != day:
                g_day, g_count = day, 0
            if g_count >= self.global_per_day:
                return False, "service_daily_limit", until_tomorrow
            keys = [key for key in (visitor, token) if key is not None] if visitor is not None else []
            for key in keys:                                 # first every key is asked, then every key is counted
                window = self._minute.setdefault(key, collections.deque())
                while window and window[0] <= t - 60:
                    window.popleft()
                if len(window) >= self.per_minute:
                    return False, "visitor_minute_limit", int(window[0] + 60 - t) + 1
                v_day, v_count = self._day.get(key, (day, 0))
                if v_day == day and v_count >= self.per_day:
                    return False, "visitor_daily_limit", until_tomorrow
            for key in keys:
                self._minute[key].append(t)
                v_day, v_count = self._day.get(key, (day, 0))
                self._day[key] = (day, v_count + 1 if v_day == day else 1)
            if len(self._day) > self.MAX_VISITORS:           # bound the memory: forget everyone but today's counts
                self._day = {k: v for k, v in self._day.items() if v[0] == day}
                self._minute = {k: w for k, w in self._minute.items() if w and w[-1] > t - 60}
            self._global = (g_day, g_count + 1)
            return True, "", 0
