"""Tests for hermes_studio.utils.retry."""

from __future__ import annotations
import pytest

from hermes_studio.utils.retry import (
    Attempt,
    PermanentError,
    RetryReport,
    TransientError,
    call_with_retry,
    classify_error,
    make_idempotency_key,
)


class _FakeClock:
    def __init__(self, start=1000.0):
        self.t = start
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, d):
        self.sleeps.append(d)
        self.t += d


def test_classify_explicit_transient():
    assert classify_error(TransientError("boom")) is TransientError


def test_classify_explicit_permanent():
    assert classify_error(PermanentError("nope")) is PermanentError


def test_classify_billing_message_is_permanent():
    err = RuntimeError("User is locked. Reason: Exhausted balance.")
    assert classify_error(err) is PermanentError


def test_classify_auth_message_is_permanent():
    assert classify_error(RuntimeError("Invalid API key")) is PermanentError
    assert classify_error(RuntimeError("Unauthorized")) is PermanentError
    assert classify_error(RuntimeError("Forbidden access")) is PermanentError


def test_classify_validation_is_permanent():
    assert classify_error(ValueError("validation error: bad prompt")) is PermanentError


def test_classify_unknown_defaults_to_transient():
    assert classify_error(ConnectionError("network timeout")) is TransientError
    assert classify_error(RuntimeError("503 service unavailable")) is TransientError


def test_idempotency_key_stable_for_same_input():
    k1 = make_idempotency_key("image", {"prompt": "x", "aspect": "1:1"})
    k2 = make_idempotency_key("image", {"prompt": "x", "aspect": "1:1"})
    assert k1 == k2


def test_idempotency_key_different_for_different_input():
    k1 = make_idempotency_key("image", {"prompt": "x"})
    k2 = make_idempotency_key("image", {"prompt": "y"})
    assert k1 != k2


def test_idempotency_key_uses_prefix():
    k = make_idempotency_key("image", {"prompt": "x"})
    assert k.startswith("image_")
    assert len(k) > len("image_")


def test_idempotency_key_dict_order_does_not_matter():
    k1 = make_idempotency_key("image", {"a": 1, "b": 2})
    k2 = make_idempotency_key("image", {"b": 2, "a": 1})
    assert k1 == k2


def test_successful_call_returns_result_and_ok_outcome():
    clock = _FakeClock()
    result, report = call_with_retry(lambda: "yay", sleep=clock.sleep, now=clock.now)
    assert result == "yay"
    assert report.final_outcome == "ok"
    assert len(report.attempts) == 1
    assert report.attempts[0].ok is True
    assert clock.sleeps == []


def test_permanent_error_stops_immediately():
    clock = _FakeClock()
    def fail():
        raise RuntimeError("Exhausted balance. Top up.")
    result, report = call_with_retry(fail, sleep=clock.sleep, now=clock.now)
    assert result is None
    assert report.final_outcome == "permanent"
    assert len(report.attempts) == 1
    assert report.attempts[0].ok is False
    assert report.attempts[0].error_type == "PermanentError"
    assert clock.sleeps == []


def test_transient_error_exhausts_max_attempts():
    clock = _FakeClock()
    def always_fail():
        raise ConnectionError("network blip")
    result, report = call_with_retry(
        always_fail, max_attempts=3, sleep=clock.sleep, now=clock.now,
    )
    assert result is None
    assert report.final_outcome == "transient_exhausted"
    assert len(report.attempts) == 3
    assert all(not a.ok for a in report.attempts)
    assert len(clock.sleeps) == 2
    assert clock.sleeps == [1.0, 2.0]


def test_transient_then_success_returns_result():
    clock = _FakeClock()
    state = {"calls": 0}
    def flaky():
        state["calls"] += 1
        if state["calls"] < 2:
            raise ConnectionError("transient")
        return "ok-on-retry"
    result, report = call_with_retry(flaky, sleep=clock.sleep, now=clock.now)
    assert result == "ok-on-retry"
    assert report.final_outcome == "ok"
    assert len(report.attempts) == 2
    assert report.attempts[0].ok is False
    assert report.attempts[1].ok is True
    assert len(clock.sleeps) == 1


def test_idempotency_key_passed_through():
    clock = _FakeClock()
    _, report = call_with_retry(
        lambda: "x",
        idempotency_key="image_abc123",
        sleep=clock.sleep,
        now=clock.now,
    )
    assert report.idempotency_key == "image_abc123"


def test_max_delay_caps_backoff():
    clock = _FakeClock()
    def always_fail():
        raise ConnectionError("blip")
    _, report = call_with_retry(
        always_fail,
        max_attempts=5,
        base_delay_s=10.0,
        max_delay_s=15.0,
        sleep=clock.sleep,
        now=clock.now,
    )
    assert clock.sleeps == [10.0, 15.0, 15.0, 15.0]


def test_retry_report_as_dict_serializable():
    import json
    report = RetryReport(idempotency_key="image_123")
    report.attempts.append(Attempt(
        n=1, started_at=100.0, duration_s=0.5, ok=True,
    ))
    d = report.as_dict()
    encoded = json.dumps(d)
    assert "image_123" in encoded
    assert "attempts" in d
    assert d["attempts"][0]["n"] == 1
    assert d["attempts"][0]["ok"] is True
