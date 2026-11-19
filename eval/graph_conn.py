"""One Neo4j driver for a whole eval run, with a log of every connection attempt.

New connections to a hosted Neo4j instance can fail. The eval must tell an infrastructure
failure from a miss, and the failure rate is itself a result. So every attempt to use the
graph is written to local-data/eval/graph_connections.jsonl:

    when, purpose, attempt, outcome (ok | failed), error class, step, seconds, inner errors

`step` says where it failed, from the driver's own error:
    routing_table    the driver could not fetch the routing table
    routed_address   it had a routing table and could not connect to the address in it
    query            the connection worked and the query itself failed
    other            anything else

Nothing that could hold an address is written: error CLASSES only, never messages.
Each attempt already includes the driver's own internal retries.

OXCART_GRAPH_LOG names another log file (inside local-data/), for a run against another
instance whose attempts must not be mixed with the first one's.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from eval import stores

LOG = stores.REPO / "local-data" / "eval" / os.environ.get("OXCART_GRAPH_LOG", "graph_connections.jsonl")
_ERROR_NAME = re.compile(r"\b([A-Z][A-Za-z]+(?:Error|Exception|Unavailable|Expired|Timeout))\b")


def step_of(exc: BaseException) -> str:
    name, message = type(exc).__name__, str(exc)
    if "routing information" in message or name == "RoutingServiceUnavailable":
        return "routing_table"
    if name in ("SessionExpired", "ReadServiceUnavailable", "WriteServiceUnavailable") or "Failed to obtain connection" in message:
        return "routed_address"
    if name in ("CypherSyntaxError", "ClientError", "CypherTypeError", "ConstraintError", "DatabaseError"):
        return "query"
    return "other"


class _Collector(logging.Handler):
    """Keeps the error class names the driver mentions while it works. Never the text around them."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.names: list[str] = []
        self.opened = 0   # sockets the driver opened during this attempt ("<OPEN>" in its debug log)

    def emit(self, record):
        try:
            message = record.getMessage()
            if "<OPEN>" in message:
                self.opened += 1
            for name in _ERROR_NAME.findall(message):
                if name not in self.names:
                    self.names.append(name)
        except Exception:
            pass


class Graph:
    """Use as a context manager. `read(purpose, fn)` runs fn(session) with spaced retries and logs each try."""

    def __init__(self, attempts: int = 4, pause: float = 20.0, log_path: Path = LOG, sleep=time.sleep):
        self.attempts, self.pause, self.log_path, self.sleep = attempts, pause, log_path, sleep
        self.driver, self.database = None, None
        self.records: list[dict] = []

    def __enter__(self):
        self.driver, self.database = stores.neo4j_session_factory()
        return self

    def __exit__(self, *exc):
        if self.driver is not None:
            self.driver.close()
        return False

    def _write(self, record: dict) -> None:
        self.records.append(record)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def read(self, purpose: str, fn):
        """Run fn(session) in a read session. Retries infrastructure failures; a query error is raised at once."""
        driver_log = logging.getLogger("neo4j")
        last: BaseException | None = None
        for attempt in range(1, self.attempts + 1):
            collector = _Collector()
            previous = driver_log.level
            driver_log.addHandler(collector)
            driver_log.setLevel(logging.DEBUG)
            t0 = time.time()
            record = {"when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "purpose": purpose, "attempt": attempt}
            try:
                with self.driver.session(database=self.database, default_access_mode="READ") as session:
                    result = fn(session)
                record.update(outcome="ok", seconds=round(time.time() - t0, 2), inner_errors=collector.names,
                              sockets_opened=collector.opened)
                self._write(record)
                return result
            except Exception as exc:
                last = exc
                step = step_of(exc)
                record.update(outcome="failed", error_class=type(exc).__name__, step=step,
                              seconds=round(time.time() - t0, 2), inner_errors=collector.names,
                              sockets_opened=collector.opened)
                self._write(record)
                if step == "query":
                    raise
            finally:
                driver_log.removeHandler(collector)
                driver_log.setLevel(previous)
            if attempt < self.attempts:
                self.sleep(self.pause)
        raise InfrastructureError(type(last).__name__ if last else "unknown")


class InfrastructureError(RuntimeError):
    """The graph could not be reached after every attempt. Carries the last error's class name only."""


def summary(log_path: Path = LOG) -> dict:
    """Failure rate over every logged attempt, by step and by error class."""
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()] if log_path.exists() else []
    failed = [r for r in rows if r["outcome"] == "failed"]
    by_step: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for r in failed:
        by_step[r.get("step", "other")] = by_step.get(r.get("step", "other"), 0) + 1
        by_class[r.get("error_class", "?")] = by_class.get(r.get("error_class", "?"), 0) + 1
    fresh = [r for r in rows if r.get("sockets_opened") or r["outcome"] == "failed"]
    return {"attempts": len(rows), "failed": len(failed), "failure_rate": (len(failed) / len(rows)) if rows else None,
            "attempts_that_opened_a_connection_or_failed": len(fresh),
            "failure_rate_of_those": (len(failed) / len(fresh)) if fresh else None,
            "by_step": by_step, "by_error_class": by_class,
            "first": rows[0]["when"] if rows else None, "last": rows[-1]["when"] if rows else None}


if __name__ == "__main__":
    print(json.dumps(summary(), indent=1))
