"""The route of the written answer.

    POST /api/chat    one question, and the earlier turns of its conversation when it is a
                      follow-up -> the evidence, then a short answer that cites it

It stands behind the same guard as ``POST /api/ask``: the session token of the human
check, the limits per visitor and per token, the service's daily limit, a body limit, and
the eval's way in. A question here counts as a question there.

The answer comes as lines of JSON (``application/x-ndjson``), sent as they are ready:

    {"type": "evidence", "rewritten": false, "evidence": {...}}    what POST /api/ask returns, for the question
                                                                  that was searched (``evidence.question``)
    {"type": "answer", "answer": {"state": "ok", "sentences": [...], "sources": [...]}}

``answer.state`` is "ok", "not_covered" (the evidence does not answer the question), or
the reason no answer was written (no key, the day's allowance spent, a timeout, ...): the
page then shows the evidence, as it did before there was a written answer. A refusal
(limits, no session, a body too large, no store answering) is a JSON error with its
status, as on ``/api/ask``, and comes before any line.

The earlier turns come from the browser, which is where a conversation is kept. They are
bounded here and read by one step only (``answer_graph.contextualize``). Nothing of a
request is kept after its answer, and neither a question nor an answer is logged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from typing import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app import answer_graph, ask_service, settings
from app.routers.ask import MESSAGES, ApiError, access

log = logging.getLogger("oxcart.ask")

router = APIRouter(tags=["chat"])


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)
    answer: str = Field("", max_length=settings.CHAT_THREAD_ANSWER_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(..., min_length=1, max_length=settings.ASK_MAX_QUESTION_CHARS)
    thread: list[Turn] = Field(default_factory=list, max_length=settings.CHAT_THREAD_TURNS)


async def body_limit(request: Request) -> None:
    length = request.headers.get("content-length", "")
    if not length.isdigit() or int(length) > settings.CHAT_MAX_BODY_BYTES:
        raise ApiError(413, "request_too_large", "The request is too large.")


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


def _results(out: "queue.Queue") -> Iterator[tuple]:
    """(node, what it returned) until the graph ends. Raises what the graph raised."""
    while True:
        update = out.get()
        if update is None:
            return
        if isinstance(update, Exception):
            raise update
        for node, change in update.items():
            yield node, change or {}


def _until_retrieved(out: "queue.Queue", seen: dict) -> None:
    """Wait for the end of ``retrieve``, keeping what the nodes returned so far."""
    for node, change in _results(out):
        seen["calls"] += change.get("calls", [])
        seen.update({k: v for k, v in change.items() if k != "calls"})
        if node == "retrieve":
            return


@router.post("/chat", dependencies=[Depends(body_limit)])
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    question = " ".join(payload.question.split())
    if not question:
        raise ApiError(422, "invalid_request", "Write a question first.")
    visitor, token = access(request)
    allowed, reason, wait = request.app.state.limiter.check(visitor, token)
    if not allowed:
        raise ApiError(429, reason, MESSAGES[reason], wait)

    state = request.app.state
    deps = answer_graph.Deps(retrieve=lambda q: ask_service.answer(q, state.ask),
                             model=state.answer_model, take=state.answer_allowance.take)
    asked = {"question": question,
             "thread": [{"question": " ".join(t.question.split()), "answer": t.answer} for t in payload.thread]}
    out: "queue.Queue" = queue.Queue()
    threading.Thread(target=_run, args=(asked, deps, out), name="chat-graph", daemon=True).start()
    seen: dict = {"calls": []}
    try:
        await asyncio.wait_for(run_in_threadpool(_until_retrieved, out, seen), timeout=settings.ASK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise ApiError(504, "timeout", "The search took too long. Please try again.")
    if seen.get("error") or "evidence" not in seen:
        raise ApiError(503, "stores_unavailable",
                       "Neither the catalogue nor the literature could be reached. Please try again in a minute.")
    evidence = seen["evidence"]

    def lines() -> Iterator[bytes]:
        yield _line({"type": "evidence", "rewritten": bool(seen.get("rewritten")), "evidence": evidence})
        answer = {"state": "failed"}
        try:
            for node, change in _results(out):
                seen["calls"] += change.get("calls", [])
                if change.get("answer"):
                    answer = change["answer"]
        except Exception as exc:                # the evidence was sent: the answer says it failed
            log.warning("chat failed after the evidence: %s", type(exc).__name__)
            answer = {"state": "failed"}
        yield _line({"type": "answer", "answer": answer})
        log.info(json.dumps({"event": "chat", "request_id": getattr(request.state, "request_id", None),
                             "who": "eval" if visitor is None else "visitor", "chars": len(question),
                             "turns": len(payload.thread), "rewritten": bool(seen.get("rewritten")),
                             "mode": evidence["mode"], "issues": len(evidence["issues"]),
                             "passages": len(evidence["passages"]), "timings": evidence["timings"],
                             "answer": answer["state"], "counts": answer.get("counts"),
                             "model_calls": [{k: c[k] for k in ("purpose", "state", "input_tokens", "output_tokens", "seconds")}
                                             for c in seen["calls"]]}))

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})
