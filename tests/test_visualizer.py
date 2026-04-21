"""Tests for Visualizer — canvas event stream.

Tests cover: emit → subscribe flow, replay buffer bounds, profile
isolation on subscribe, and the post_tool_call hook behavior for
non-studio tools.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hermes_studio.archetypes.visualizer import Visualizer, CanvasEvent


def test_emit_adds_to_replay():
    v = Visualizer()
    v.emit(kind="image", session_id="s1", profile_id="alice", payload={"prompt": "x"})
    v.emit(kind="3d", session_id="s1", profile_id="alice", payload={"prompt": "y"})
    _, replay = v.subscribe(session_id="s1", profile_id="alice")
    assert [e.kind for e in replay] == ["image", "3d"]


def test_replay_buffer_bounded():
    v = Visualizer()
    v._replay_cap = 10  # test-only override
    for i in range(25):
        v.emit(kind="image", session_id="s1", profile_id="alice", payload={"i": i})
    assert len(v._replay) == 10
    # Ensure the most recent events are retained (not the oldest)
    kept_indices = [e.payload["i"] for e in v._replay]
    assert kept_indices == list(range(15, 25))


def test_subscribe_profile_isolation():
    v = Visualizer()
    v.emit(kind="image", session_id="s1", profile_id="alice", payload={"who": "a"})
    v.emit(kind="image", session_id="s1", profile_id="bob", payload={"who": "b"})
    _, alice_replay = v.subscribe(session_id="s1", profile_id="alice")
    _, bob_replay = v.subscribe(session_id="s1", profile_id="bob")
    assert [e.payload["who"] for e in alice_replay] == ["a"]
    assert [e.payload["who"] for e in bob_replay] == ["b"]


def test_subscribe_session_filter_optional():
    v = Visualizer()
    v.emit(kind="image", session_id="s1", profile_id="alice", payload={"i": 1})
    v.emit(kind="image", session_id="s2", profile_id="alice", payload={"i": 2})
    # empty session_id = all sessions for this profile
    _, all_replay = v.subscribe(session_id="", profile_id="alice")
    assert len(all_replay) == 2
    # specific session_id = only that session
    _, s1_replay = v.subscribe(session_id="s1", profile_id="alice")
    assert len(s1_replay) == 1
    assert s1_replay[0].session_id == "s1"


@pytest.mark.asyncio
async def test_live_emit_reaches_subscriber():
    v = Visualizer()
    q, _ = v.subscribe(session_id="s1", profile_id="alice")
    v.emit(kind="image", session_id="s1", profile_id="alice", payload={"prompt": "x"})
    evt = await asyncio.wait_for(q.get(), timeout=1.0)
    assert evt.kind == "image"
    assert evt.payload["prompt"] == "x"


def test_post_tool_call_skips_studio_tools():
    """studio_* tools emit their own rich events via Creator — we shouldn't
    double-post a generic tool_call event for them."""
    v = Visualizer()
    v.post_tool_call(tool_name="studio_render_image", result="{}", session_id="s1", profile_id="alice")
    assert v._replay == []


def test_post_tool_call_emits_for_other_tools():
    v = Visualizer()
    v.post_tool_call(tool_name="bash", result="ok", session_id="s1", profile_id="alice")
    assert len(v._replay) == 1
    assert v._replay[0].kind == "tool_call"
    assert v._replay[0].payload["tool"] == "bash"


def test_event_to_json_roundtrip():
    evt = CanvasEvent(ts=1.0, kind="image", session_id="s1", profile_id="alice", payload={"a": 1})
    doc = json.loads(Visualizer.event_to_json(evt))
    assert doc["kind"] == "image"
    assert doc["profile_id"] == "alice"
    assert doc["payload"] == {"a": 1}


def test_close_stops_emission():
    v = Visualizer()
    v.close()
    v.emit(kind="image", session_id="s1", profile_id="alice", payload={"x": 1})
    assert v._replay == []
