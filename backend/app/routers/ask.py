"""The question path's routes.

    GET  /api/health          hosted mode only: a light "I am up" with no store round trip, and where the graph
                              link, the literature client and the embedding's connection are
    GET  /api/ask/examples    questions to try, and the bounds the page should respect
    POST /api/session         a passed human check -> a short-lived signed token
    POST /api/ask             one question -> catalogue issues, literature passages, and the mode that answered

Every refusal is a small JSON object ``{"error": <code>, "message": <text a visitor can read>}``.
The request's question is never echoed in an error and never logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app import ask_service, public_guard, settings

log = logging.getLogger("oxcart.ask")

router = APIRouter(tags=["ask"])
health_router = APIRouter(tags=["ask"])


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: Optional[int] = None):
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after


MESSAGES = {
    "visitor_minute_limit": "Too many questions in a minute. Please wait a little and ask again.",
    "visitor_daily_limit": "You have reached today's limit of questions. Please come back tomorrow.",
    "service_daily_limit": "The demo has reached its limit of questions for today. Please come back tomorrow.",
}


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(..., min_length=1, max_length=2048)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)


async def body_limit(request: Request) -> None:
    length = request.headers.get("content-length", "")
    if not length.isdigit() or int(length) > settings.ASK_MAX_BODY_BYTES:
        raise ApiError(413, "request_too_large", "The request is too large.")


def _visitor(request: Request) -> str:
    named = request.headers.get(settings.VISITOR_ADDRESS_HEADER) if settings.VISITOR_ADDRESS_HEADER else None
    return public_guard.visitor_key(request.headers.get("x-forwarded-for"),
                                    request.client.host if request.client else None, named)


def access(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Who is asking, as the keys the limits count: (None, None) for the eval's secret
    header, otherwise the visitor's key and the key of its session token (None when the
    request has no valid token, which only local mode lets through).
    In hosted mode a visitor needs a valid session token."""
    if public_guard.eval_key_matches(request.headers.get(public_guard.EVAL_HEADER, "")):
        return None, None
    token = request.headers.get(public_guard.SESSION_HEADER, "")
    valid = public_guard.session_is_valid(token, settings.SESSION_SIGNING_KEY)
    if request.app.state.public and not valid:
        raise ApiError(401, "session_required", "Please complete the human check to ask a question.")
    return _visitor(request), public_guard.token_key(token) if valid else None


@health_router.get("/health")
async def health(request: Request) -> dict:
    """Light: no store round trip. `graph`, `literature` and `embedding` are what the
    process already knows about each connection (connecting, connected or unavailable;
    not started when it was not opened at startup; the embedding also not configured),
    so a page can show "starting" while any of them is still connecting."""
    link = getattr(request.app.state, "graph", None)
    deps = getattr(request.app.state, "ask", None)
    states = deps.states() if deps is not None else {}
    return {"status": "ok", "graph": link.state if link is not None else "unavailable",
            "literature": states.get("literature", "not started"), "embedding": states.get("embedding", "not started")}


@router.get("/ask/examples")
async def examples() -> dict:
    return {"examples": ask_service.EXAMPLES, "max_question_chars": settings.ASK_MAX_QUESTION_CHARS}


@router.post("/session", dependencies=[Depends(body_limit)])
async def session(payload: SessionRequest, request: Request) -> dict:
    allowed, reason, wait = request.app.state.session_limiter.check(_visitor(request))
    if not allowed:
        raise ApiError(429, reason, "Too many attempts. Please wait a little and try again.", wait)
    unavailable = ApiError(503, "human_check_unavailable",
                           "The human check is not available right now, so questions cannot be accepted. "
                           "Please try again in a few minutes.")
    if not settings.SESSION_SIGNING_KEY:
        raise unavailable
    verdict = await run_in_threadpool(request.app.state.ask.verify_human, payload.token)
    if verdict == "ok":
        return {"session": public_guard.issue_session(settings.SESSION_SIGNING_KEY, settings.SESSION_TTL_SECONDS),
                "expires_in": settings.SESSION_TTL_SECONDS}
    if verdict == "failed":
        raise ApiError(403, "human_check_failed", "The human check did not pass. Please try it again.")
    raise unavailable


@router.post("/ask", dependencies=[Depends(body_limit)])
async def ask(payload: AskRequest, request: Request) -> dict:
    question = " ".join(payload.question.split())
    if not question:
        raise ApiError(422, "invalid_request", "Write a question first.")
    visitor, token = access(request)
    allowed, reason, wait = request.app.state.limiter.check(visitor, token)
    if not allowed:
        raise ApiError(429, reason, MESSAGES[reason], wait)
    try:
        result = await asyncio.wait_for(run_in_threadpool(ask_service.answer, question, request.app.state.ask),
                                        timeout=settings.ASK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise ApiError(504, "timeout", "The search took too long. Please try again.")
    except ask_service.Unavailable:
        raise ApiError(503, "stores_unavailable",
                       "Neither the catalogue nor the literature could be reached. Please try again in a minute.")
    log.info(json.dumps({"event": "ask", "request_id": getattr(request.state, "request_id", None),
                         "who": "eval" if visitor is None else "visitor", "chars": len(question),
                         "mode": result["mode"], "issues": len(result["issues"]),
                         "passages": len(result["passages"]), "timings": result["timings"]}))
    return result
