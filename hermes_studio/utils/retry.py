"""Retry helpers for Creator backend calls.

Provides exponential-backoff retry with error classification and structured
attempt logs, so failures are legible and replayable.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TransientError(Exception):
    """Retryable error - network blips, rate limits, 5xx server errors."""


class PermanentError(Exception):
    """Non-retryable error - auth, billing, malformed input."""


_PERMANENT_MARKERS = (
    "exhausted balance",
    "user is locked",
    "invalid api key",
    "unauthorized",
    "forbidden",
    "not found",
    "validation error",
    "invalid prompt",
)


def classify_error(err):
    if isinstance(err, (TransientError, PermanentError)):
        return type(err)
    msg = str(err).lower()
    for marker in _PERMANENT_MARKERS:
        if marker in msg:
            return PermanentError
    return TransientError


@dataclass
class Attempt:
    n: int
    started_at: float
    duration_s: float
    ok: bool
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class RetryReport:
    idempotency_key: str
    attempts: list = field(default_factory=list)
    total_duration_s: float = 0.0
    final_outcome: str = "pending"

    def as_dict(self):
        return {
            "idempotency_key": self.idempotency_key,
            "total_duration_s": self.total_duration_s,
            "final_outcome": self.final_outcome,
            "attempts": [
                {
                    "n": a.n,
                    "duration_s": a.duration_s,
                    "ok": a.ok,
                    "error_type": a.error_type,
                    "error_message": a.error_message,
                }
                for a in self.attempts
            ],
        }


def make_idempotency_key(prefix, payload):
    canonical = json.dumps(payload, sort_keys=True, default=str)
    h = hashlib.sha256((prefix + "::" + canonical).encode("utf-8")).hexdigest()
    return prefix + "_" + h[:16]


def call_with_retry(
    fn,
    max_attempts=3,
    base_delay_s=1.0,
    max_delay_s=8.0,
    sleep=time.sleep,
    now=time.time,
    idempotency_key="",
):
    report = RetryReport(idempotency_key=idempotency_key)
    started_overall = now()

    for n in range(1, max_attempts + 1):
        attempt_start = now()
        try:
            result = fn()
            duration = now() - attempt_start
            report.attempts.append(Attempt(
                n=n, started_at=attempt_start, duration_s=duration, ok=True,
            ))
            report.total_duration_s = now() - started_overall
            report.final_outcome = "ok"
            return result, report
        except BaseException as e:
            duration = now() - attempt_start
            err_class = classify_error(e)
            report.attempts.append(Attempt(
                n=n,
                started_at=attempt_start,
                duration_s=duration,
                ok=False,
                error_type=err_class.__name__,
                error_message=str(e)[:500],
            ))
            if err_class is PermanentError:
                report.total_duration_s = now() - started_overall
                report.final_outcome = "permanent"
                return None, report
            if n < max_attempts:
                delay = min(base_delay_s * (2 ** (n - 1)), max_delay_s)
                sleep(delay)

    report.total_duration_s = now() - started_overall
    report.final_outcome = "transient_exhausted"
    return None, report
