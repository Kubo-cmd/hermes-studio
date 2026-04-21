"""Tests for Keeper — per-profile, per-session timeline.

The critical invariant (related to Hermes issue #6320) is that entries
from one profile NEVER surface in another profile's queries. Every test
here is ultimately about that boundary.
"""

from __future__ import annotations

import os

import pytest

from hermes_studio.archetypes.keeper import Keeper


@pytest.fixture
def keeper(tmp_path, monkeypatch):
    # Redirect STUDIO_MEDIA_DIR so keeper writes to a temp location.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("STUDIO_MEDIA_DIR", raising=False)
    return Keeper()


def test_append_and_list_single_session(keeper):
    keeper.on_session_start("s1", profile_id="alice")
    id1 = keeper.append("s1", role="user", kind="text", content="hello", profile_id="alice")
    id2 = keeper.append("s1", role="assistant", kind="text", content="hi", profile_id="alice")
    entries = keeper.list_session("s1", profile_id="alice")
    assert [e["id"] for e in entries] == [id1, id2]
    assert entries[0]["content"] == "hello"


def test_profile_isolation(keeper):
    """The core #6320 invariant — alice cannot see bob's timeline."""
    keeper.on_session_start("s1", profile_id="alice")
    keeper.on_session_start("s1", profile_id="bob")
    keeper.append("s1", role="user", kind="text", content="alice-secret", profile_id="alice")
    keeper.append("s1", role="user", kind="text", content="bob-secret", profile_id="bob")

    alice_entries = keeper.list_session("s1", profile_id="alice")
    bob_entries = keeper.list_session("s1", profile_id="bob")

    alice_text = " ".join(e["content"] or "" for e in alice_entries)
    bob_text = " ".join(e["content"] or "" for e in bob_entries)

    assert "alice-secret" in alice_text
    assert "bob-secret" not in alice_text
    assert "bob-secret" in bob_text
    assert "alice-secret" not in bob_text


def test_profile_id_sanitization(keeper):
    """Malicious profile IDs should not result in SQL injection or cross-profile reads."""
    evil = "alice; DROP TABLE timeline_bob; --"
    keeper.on_session_start("s1", profile_id=evil)
    # Should not raise, and should create a safe table name.
    id1 = keeper.append("s1", role="user", kind="text", content="hi", profile_id=evil)
    entries = keeper.list_session("s1", profile_id=evil)
    assert len(entries) == 1
    assert entries[0]["id"] == id1
    # bob's hypothetical table should be unaffected
    keeper.on_session_start("s1", profile_id="bob")
    keeper.append("s1", role="user", kind="text", content="bob-data", profile_id="bob")
    assert len(keeper.list_session("s1", profile_id="bob")) == 1


def test_session_isolation_within_profile(keeper):
    keeper.on_session_start("s1", profile_id="alice")
    keeper.on_session_start("s2", profile_id="alice")
    keeper.append("s1", role="user", kind="text", content="in-s1", profile_id="alice")
    keeper.append("s2", role="user", kind="text", content="in-s2", profile_id="alice")
    assert [e["content"] for e in keeper.list_session("s1", profile_id="alice")] == ["in-s1"]
    assert [e["content"] for e in keeper.list_session("s2", profile_id="alice")] == ["in-s2"]


def test_fork_copies_up_to_anchor(keeper):
    import json as _json
    keeper.on_session_start("s1", profile_id="alice")
    ids = [
        keeper.append("s1", role="user", kind="text", content=f"msg{i}", profile_id="alice")
        for i in range(5)
    ]
    # Fork from the 3rd message — the new session should contain msg0..msg2
    result = _json.loads(keeper.fork(
        args={"from_message_id": ids[2], "label": "branch"},
        session_id="s1",
        profile_id="alice",
    ))
    assert result["ok"] is True
    new_session = result["new_session_id"]
    forked = keeper.list_session(new_session, profile_id="alice")
    contents = [e["content"] for e in forked]
    assert contents == ["msg0", "msg1", "msg2"]
    # fork_of is set on the copies
    assert all(e["fork_of"] == "s1" for e in forked)


def test_fork_missing_anchor_returns_error(keeper):
    import json as _json
    keeper.on_session_start("s1", profile_id="alice")
    result = _json.loads(keeper.fork(
        args={"from_message_id": "nonexistent"},
        session_id="s1",
        profile_id="alice",
    ))
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_fork_without_session_id_errors(keeper):
    import json as _json
    result = _json.loads(keeper.fork(args={"from_message_id": "x"}))
    assert result["ok"] is False
