"""The size and the time of a request's body, held before anything reads it.

FastAPI reads and parses the whole body of a route that takes one before the route's
dependencies run, so a limit kept in a dependency comes too late. This middleware stands in
front of the app and, for every POST under ``/api/``:

* answers 413 at once when ``Content-Length`` is missing, is not a number, or is over the
  path's limit;
* reads the body itself, counting the bytes that actually arrive, and answers 413 as soon as
  they pass the limit, whatever the header said;
* gives the whole body a deadline (``BODY_READ_SECONDS``) and answers 408 past it.

The route is then given the body it read, in one piece. An error has the shape of the app's
other errors (``{"error", "message"}``). It is added inside the CORS middleware, so a browser
can read a 413 as it reads any other refusal (main.py).

Nothing of a body is logged.
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Mapping

from app import settings

Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

TOO_LARGE = (413, "request_too_large", "The request is too large.")
TOO_SLOW = (408, "request_timeout", "The request took too long to arrive. Please try again.")


class _TooLarge(Exception):
    pass


class _Gone(Exception):
    pass


async def _refuse(send: Send, refusal: tuple) -> None:
    status, code, message = refusal
    body = json.dumps({"error": code, "message": message}).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii")),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class BodyLimit:
    """A pure ASGI middleware. ``limits`` maps a path to its limit in bytes; any other POST under ``/api/``
    gets ``default``. Both are callables so a test's change to a setting is seen."""

    def __init__(self, app, limits: Callable[[], Mapping[str, int]], default: Callable[[], int]):
        self.app, self.limits, self.default = app, limits, default

    def limit_for(self, path: str) -> int:
        return self.limits().get(path.rstrip("/") or path, self.default())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope["path"])
        lengths = [v for k, v in scope.get("headers") or [] if k.lower() == b"content-length"]
        length = lengths[0].decode("latin-1").strip() if len(lengths) == 1 else ""
        if not length.isdigit() or int(length) > limit:
            await _refuse(send, TOO_LARGE)
            return

        chunks: list = []

        async def read_all() -> None:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    raise _Gone
                body = message.get("body", b"")
                size += len(body)
                if size > limit:
                    raise _TooLarge
                chunks.append(body)
                if not message.get("more_body", False):
                    return

        try:
            await asyncio.wait_for(read_all(), timeout=settings.BODY_READ_SECONDS)
        except _TooLarge:
            await _refuse(send, TOO_LARGE)
            return
        except asyncio.TimeoutError:
            await _refuse(send, TOO_SLOW)
            return
        except _Gone:
            return                                  # the client left: nobody to answer

        given = False

        async def replay() -> Message:
            nonlocal given
            if not given:
                given = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()                  # after the body: a disconnect, when it comes

        await self.app(scope, replay, send)
