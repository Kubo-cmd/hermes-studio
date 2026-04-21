"""Tests for Shadow — tool-call duration classifier.

Shadow maps tool-call durations to visibility levels (ok / slow / stuck)
so long creative runs don't silently hang. Related: Hermes issue #11431.
"""

from __future__ import annotations

import pytest

from hermes_studio.archetypes.shadow import Shadow, DEFAULT_SOFT_TIMEOUT_S, DEFAULT_HARD_TIMEOUT_S


def test_fast_call_is_ok():
    s = Shadow()
    s.post_tool_call(tool_name="bash", result="done", duration=0.5, session_id="s1")
    assert s.reports[-1].level == "ok"


def test_slow_call_is_flagged():
    s = Shadow()
    s.post_tool_call(tool_name="bash", result="done", duration=DEFAULT_SOFT_TIMEOUT_S + 1, session_id="s1")
    assert s.reports[-1].level == "slow"


def test_stuck_call_is_flagged():
    s = Shadow()
    s.post_tool_call(tool_name="bash", result="done", duration=DEFAULT_HARD_TIMEOUT_S + 1, session_id="s1")
    assert s.reports[-1].level == "stuck"


def test_recent_slow_or_stuck_filter():
    s = Shadow()
    s.post_tool_call(tool_name="a", result="", duration=0.1)
    s.post_tool_call(tool_name="b", result="", duration=DEFAULT_SOFT_TIMEOUT_S + 1)
    s.post_tool_call(tool_name="c", result="", duration=DEFAULT_HARD_TIMEOUT_S + 1)
    recent = s.recent_slow_or_stuck()
    assert {r.tool_name for r in recent} == {"b", "c"}


def test_missing_duration_defaults_to_ok():
    """If Hermes doesn't pass duration for some reason, don't crash."""
    s = Shadow()
    s.post_tool_call(tool_name="bash", result="done", session_id="s1")
    assert s.reports[-1].level == "ok"
    assert s.reports[-1].duration_s == 0.0


def test_custom_thresholds():
    s = Shadow(soft_timeout_s=1.0, hard_timeout_s=5.0)
    s.post_tool_call(tool_name="a", result="", duration=0.5)
    s.post_tool_call(tool_name="b", result="", duration=2.0)
    s.post_tool_call(tool_name="c", result="", duration=6.0)
    assert [r.level for r in s.reports] == ["ok", "slow", "stuck"]
