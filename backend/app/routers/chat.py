"""The route of the written answer.

    POST /api/chat    one question, and the earlier turns of its conversation when it is a
                      follow-up -> the evidence, then a short answer that cites it

With ASK_WEB on, a second route (``web_router``, mounted only then; app/web_step.py):

    POST /api/chat/web    the question as it was searched, the answer's text and the ticket the chat
                          reply's answer carried -> a short part written from a web search

It stands behind the same guard as ``POST /api/ask``: the session token of the human
check, the limits per visitor and per token, the service's daily limit, a body limit (held
before the route reads the body: app/body_limit.py), and the eval's way in. A question here
counts as a question there.

The answer comes as lines of JSON (``application/x-ndjson``), sent as they are ready:

    {"type": "evidence", "rewritten": false, "evidence": {...}}    what POST /api/ask returns, for the question
                                                                  that was searched (``evidence.question``); with
                                                                  ``evidence.searches`` when the literature was
                                                                  searched in both languages (ask_service.py)
    {"type": "answer", "answer": {"state": "ok", "sentences": [...], "sources": [...]}, "calls": [...]}

``answer.state`` is "ok", "not_covered" (the evidence does not answer the question), or
the reason no answer was written (no key, the day's allowance spent, a timeout, ...): the
page then shows the evidence, as it did before there was a written answer. ``calls`` has
one entry per model call made for the question: what it was for, its state, its token
counts and its seconds; that is what a cost is measured from. A refusal
(limits, no session, a body too large, no store answering) is a JSON error with its
status, as on ``/api/ask``, and comes before any line.

When nobody waits for the answer any more (the route gave up at ASK_TIMEOUT_SECONDS, it
refused for want of a store, or the visitor left before the answer line), the graph is told
(``Deps.gone``) and makes no model call and takes none from the day's allowance. The answer
is waited for at most ``answer_wait_seconds()`` after the evidence; past it, it says "failed".

Every question passes the rewriting step first (``answer_graph.contextualize``): one model
call before the search, which makes a follow-up stand alone and gives the question in the
other of the two languages. So a question takes two model calls, and the first is made
before it is known whether a store answers or the visitor stays.

The earlier turns come from the browser, which is where a conversation is kept. They are
bounded here and read by that one step only. Nothing of a request is kept after its answer,
and neither a question nor an answer is logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from typing import AsyncIterator, Iterator

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import answer_graph, answer_model, ask_service, settings, web_step
from app.routers.ask import MESSAGES, ApiError, access

log = logging.getLogger("oxcart.ask")

router = APIRouter(tags=["chat"])
web_router = APIRouter(tags=["chat"])


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)
    answer: str = Field("", max_length=settings.CHAT_THREAD_ANSWER_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)
    thread: list[Turn] = Field(default_factory=list, max_length=settings.CHAT_THREAD_TURNS)


def _line(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _run(asked: dict, deps: answer_graph.Deps, out: "queue.Queue") -> None:
    """The whole graph in one thread of its own, each node's result put on ``out`` as the
    node ends; then the error, if there was one; then None."""
    try:
        for update in answer_graph.GRAPH.stream(asked, context=deps, stream_mode="updates"):
            out.put(update)
    except Exception as exc:
        out.put(exc)
    finally:
        out.put(None)


def _results(out: "queue.Queue", deadline: float) -> Iterator[tuple]:
    """(node, what it returned) until the graph ends. Raises what the graph raised, and TimeoutError when
    nothing came by ``deadline`` (time.monotonic())."""
    while True:
        try:
            update = out.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            raise TimeoutError from None
        if update is None:
            return
        if isinstance(update, Exception):
            raise update
        for node, change in update.items():
            yield node, change or {}


def _until_retrieved(out: "queue.Queue", seen: dict, deadline: float) -> None:
    """Wait for the end of ``retrieve``, keeping what the nodes returned so far."""
    for node, change in _results(out, deadline):
        seen["calls"] += change.get("calls", [])
        seen.update({k: v for k, v in change.items() if k != "calls"})
        if node == "retrieve":
            return


def _the_answer(out: "queue.Queue", seen: dict, deadline: float) -> dict:
    """The answer, once the evidence was sent: what ``check`` returned, or "failed"."""
    answer = {"state": "failed"}
    try:
        for node, change in _results(out, deadline):
            seen["calls"] += change.get("calls", [])
            if change.get("answer"):
                answer = change["answer"]
    except Exception as exc:                # the evidence was sent: the answer says it failed
        log.warning("chat failed after the evidence: %s", type(exc).__name__)
        answer = {"state": "failed"}
    return answer


def answer_wait_seconds() -> float:
    """How long the answer is waited for once the evidence was sent: the one model call left (``write``; the
    rewriting call was made before the evidence, inside ASK_TIMEOUT_SECONDS), as many times as the
    SDK makes it, and a margin. Past it the answer says "failed"."""
    return settings.ANSWER_TIMEOUT_SECONDS * (answer_model.MAX_RETRIES + 1) + ANSWER_WAIT_MARGIN_SECONDS


ANSWER_WAIT_MARGIN_SECONDS = 5.0
LEFT_CHECK_SECONDS = 0.02


async def _left(request: Request) -> bool:
    """Has the visitor gone? After the body, the only message a request can still receive is the disconnect:
    it is looked for, briefly."""
    try:
        message = await asyncio.wait_for(request.receive(), timeout=LEFT_CHECK_SECONDS)
    except asyncio.TimeoutError:
        return False
    return message.get("type") == "http.disconnect"


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    question = " ".join(payload.question.split())
    if not question:
        raise ApiError(422, "invalid_request", "Write a question first.")
    visitor, token = access(request)
    allowed, reason, wait = request.app.state.limiter.check(visitor, token)
    if not allowed:
        raise ApiError(429, reason, MESSAGES[reason], wait)

    state = request.app.state
    deps = answer_graph.Deps(retrieve=lambda q, also=None: ask_service.answer(q, state.ask, also),
                             model=state.answer_model, take=state.answer_allowance.take,
                             evidence_sent=threading.Event())
    asked = {"question": question,
             "thread": [{"question": " ".join(t.question.split()), "answer": t.answer} for t in payload.thread]}
    out: "queue.Queue" = queue.Queue()
    threading.Thread(target=_run, args=(asked, deps, out), name="chat-graph", daemon=True).start()
    seen: dict = {"calls": []}
    try:
        await asyncio.wait_for(run_in_threadpool(_until_retrieved, out, seen,
                                                 time.monotonic() + settings.ASK_TIMEOUT_SECONDS + 1),
                               timeout=settings.ASK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        deps.gone.set()                     # nobody waits for this answer: no model call is made for it
        raise ApiError(504, "timeout", "The search took too long. Please try again.")
    if seen.get("error") or "evidence" not in seen:
        deps.gone.set()
        raise ApiError(503, "stores_unavailable",
                       "Neither the catalogue nor the literature could be reached. Please try again in a minute.")
    evidence = seen["evidence"]

    async def lines() -> AsyncIterator[bytes]:
        answered = False
        try:
            yield _line({"type": "evidence", "rewritten": bool(seen.get("rewritten")), "evidence": evidence})
            if await _left(request):
                return                      # the visitor left with the evidence: the answer is not written
            deps.evidence_sent.set()
            answer = await run_in_threadpool(_the_answer, out, seen, time.monotonic() + answer_wait_seconds())
            calls = [{k: c[k] for k in ("purpose", "state", "input_tokens", "output_tokens", "seconds")} for c in seen["calls"]]
            web = getattr(state, "web", None)               # set only with ASK_WEB on
            # no ticket when a store did not answer: that our sources do not cover the question is not known then
            answered_by_both = "unavailable" not in (evidence["mode"]["catalogue"], evidence["mode"]["literature"])
            ticket = None
            if web is not None and answered_by_both:         # it can read the search service's usage: not on the loop
                ticket = await run_in_threadpool(web.ticket_for, answer, evidence["question"])
            if ticket:
                answer = {**answer, "web": ticket}
            yield _line({"type": "answer", "answer": answer, "calls": calls})
            answered = True
            log.info(json.dumps({"event": "chat", "request_id": getattr(request.state, "request_id", None),
                                 "who": "eval" if visitor is None else "visitor", "chars": len(question),
                                 "turns": len(payload.thread), "rewritten": bool(seen.get("rewritten")),
                                 "texts_searched": len(evidence.get("searches") or []) or 1,
                                 "mode": evidence["mode"], "issues": len(evidence["issues"]),
                                 "passages": len(evidence["passages"]), "timings": evidence["timings"],
                                 "answer": answer["state"], "counts": answer.get("counts"),
                                 "model_calls": calls, **({"web_ticket": bool(ticket)} if web is not None else {})}))
        finally:
            if not answered:
                deps.gone.set()             # closed before the answer line was sent: nobody waits for it

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- the web step (ASK_WEB)
class WebRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)   # as it was searched
    answer: str = Field("", max_length=settings.WEB_ANSWER_CHARS)                         # empty for "not covered"
    ticket: str = Field(..., min_length=1, max_length=300)


@web_router.post("/chat/web")
async def chat_web(payload: WebRequest, request: Request) -> dict:
    """One web part, for the answer a ticket was made for. The same guard as the chat route: the session in
    hosted mode, both visitor counts (it counts as a question), the service's daily limit, the eval's way in.
    Then the ticket; then the search allowance and one model call of the day's allowance (web_step.py)."""
    visitor, token = access(request)
    allowed, reason, wait = request.app.state.limiter.check(visitor, token)
    if not allowed:
        raise ApiError(429, reason, MESSAGES[reason], wait)
    web = request.app.state.web
    state = web.tickets.redeem(payload.ticket, payload.question, payload.answer)
    if state is None:
        raise ApiError(403, "ticket_refused", "This web search can no longer be made.")
    question = " ".join(payload.question.split())
    allowance = request.app.state.answer_allowance
    reply, note = await run_in_threadpool(web.run, question, payload.answer, state, request.app.state.answer_model,
                                          allowance.take, allowance.give_back)
    log.info(json.dumps({"event": "web", "request_id": getattr(request.state, "request_id", None),
                         "who": "eval" if visitor is None else "visitor", "ticket": state, "state": reply["state"],
                         "reason": note["reason"], "rule": web.searches.rule, "counts": reply["counts"],
                         "timings": note["timings"], "model_calls": reply["calls"]}))
    return reply
