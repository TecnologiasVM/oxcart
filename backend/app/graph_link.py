"""The process's link to the graph, built so that nothing depends on a lucky first try.

A hosted graph can refuse a new connection and accept the next one half a second later
(a refusal comes back in well under a second). So:

* **At startup** the process opens a connection in the background, retrying inside a time
  budget. Startup itself does not wait: the health route answers at once and says whether
  the graph is `connecting`, `connected` or `unavailable`. `unavailable` is the verdict of
  every warm-up that did not open a connection, whatever the reason.
* **One driver for the life of the process.** Once a connection is open the driver's pool
  keeps it; calls on an open connection are not the ones that fail.
* **A question that finds no connection** retries inside its own, shorter budget before
  the catalogue block is reported as unavailable.

Only connection failures are retried. An error in a query is not: retrying it would give
the same error again.

Logs carry error class names only, never a message or an address.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

log = logging.getLogger("oxcart.ask")

# Error classes of the Neo4j driver (and of the sockets under it) that mean "no connection
# right now", by name so this module needs no import of the driver.
RETRYABLE = frozenset({
    "ServiceUnavailable", "SessionExpired", "RoutingServiceUnavailable", "ReadServiceUnavailable",
    "WriteServiceUnavailable", "IncompleteCommit", "ConnectionAcquisitionTimeoutError", "TransientError",
    "ConnectionError", "ConnectionResetError", "ConnectionRefusedError", "BrokenPipeError", "TimeoutError", "OSError",
})


class Unavailable(Exception):
    """The store could not answer. Carries the last error's class name only."""


class Refused(Unavailable):
    """The graph answered and refused the query (it names an index or a procedure the graph does not have, or
    is not valid): not a lost connection, and the same query would be refused again."""


# The status codes of the Neo4j server for a query it refuses, by their start. A refused login is not one.
REFUSED_CODES = ("Neo.ClientError.Procedure.", "Neo.ClientError.Statement.", "Neo.ClientError.Schema.")


def refused(exc: BaseException) -> bool:
    return str(getattr(exc, "code", None) or "").startswith(REFUSED_CODES)


def retryable(exc: BaseException) -> bool:
    return type(exc).__name__ in RETRYABLE


class GraphLink:
    """Wraps the process's driver: a background warm-up at startup and reads that retry."""

    def __init__(self, get_driver: Callable[[], Any], database: str, startup_budget: float, question_budget: float,
                 every: float, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self._get_driver, self._database = get_driver, database
        self._startup_budget, self._question_budget, self._every = startup_budget, question_budget, every
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self.state = "connecting"            # connecting | connected | unavailable
        self.attempts = 0                    # connection attempts so far, for the log

    def _set(self, state: str) -> None:
        with self._lock:
            changed = state != self.state
            self.state = state
        if changed:
            log.info("graph %s after %d attempt(s)", state, self.attempts)

    def _session(self):
        # Notices off: under Cypher 25 the vector-index procedure answers with a deprecation
        # notice on every call (it "is replaced by SEARCH"), which would fill the log.
        return self._get_driver().session(database=self._database, default_access_mode="READ",
                                          notifications_min_severity="OFF")

    def read(self, fn: Callable[[Any], Any], budget: Optional[float] = None) -> Any:
        """Run ``fn(session)`` in a read session. A connection failure is tried again every
        ``every`` seconds until ``budget`` seconds have passed; then ``Unavailable``."""
        budget = self._question_budget if budget is None else budget
        deadline = self._clock() + budget
        while True:
            self.attempts += 1
            try:
                with self._session() as session:
                    result = fn(session)
                self._set("connected")
                return result
            except Exception as exc:
                name = type(exc).__name__
                if not retryable(exc):
                    log.warning("graph read failed, not retried: %s", name)
                    raise (Refused if refused(exc) else Unavailable)(name) from None
                if self._clock() + self._every > deadline:
                    self._set("unavailable")
                    log.warning("graph not reachable inside %.0f s: %s", budget, name)
                    raise Unavailable(name) from None
                self._sleep(self._every)

    def warm(self) -> bool:
        """Open the first connection, retrying inside the startup budget. Meant for a thread."""
        try:
            self.read(lambda session: session.run("RETURN 1 AS ok").consume(), budget=self._startup_budget)
            return True
        except Unavailable:
            # Also when the failure was one that is not retried (a refused password): the first
            # connection did not open, and "connecting" would be said for ever.
            self._set("unavailable")
            return False

    def warm_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.warm, name="graph-warm-up", daemon=True)
        thread.start()
        return thread
