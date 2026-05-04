"""Tests for Seeker - the trajectory logging archetype."""

from __future__ import annotations

import json
import pytest

from hermes_studio.archetypes.seeker import Seeker, _maybe_extract_retry_metadata


def test_extract_retry_metadata_from_full_payload():
    payload = json.dumps({
        "ok": True,
        "tool": "studio_render_image",
        "url": "http://x",
        "idempotency_key": "image_abc123",
        "retry_report": {"final_outcome": "ok", "attempts": []},
    })
    report, key = _maybe_extract_retry_metadata(payload)
    assert report == {"final_outcome": "ok", "attempts": []}
    assert key == "image_abc123"


def test_extract_retry_metadata_handles_missing_fields():
    payload = json.dumps({"ok": True, "url": "http://x"})
    report, key = _maybe_extract_retry_metadata(payload)
    assert report is None
    assert key is None


def test_extract_retry_metadata_handles_non_json():
    report, key = _maybe_extract_retry_metadata("plain string")
    assert report is None
    assert key is None


def test_extract_retry_metadata_handles_non_string():
    report, key = _maybe_extract_retry_metadata(12345)
    assert report is None
    assert key is None


def test_extract_retry_metadata_handles_json_array():
    """JSON valid but not a dict - should not crash."""
    payload = json.dumps([1, 2, 3])
    report, key = _maybe_extract_retry_metadata(payload)
    assert report is None
    assert key is None


def test_seeker_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("STUDIO_RECORD_TRAJECTORIES", raising=False)
    seeker = Seeker()
    seeker.post_tool_call(
        tool_name="t", result="x", duration=0.1,
        session_id="s1", profile_id="p1",
    )
    traj = tmp_path / "studio" / "trajectories.jsonl"
    assert not traj.exists()


def test_seeker_enabled_writes_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("STUDIO_RECORD_TRAJECTORIES", "1")
    seeker = Seeker()
    seeker.post_tool_call(
        tool_name="bash", result="ok", duration=0.5,
        session_id="s1", profile_id="alice", args={"cmd": "ls"},
    )
    traj = tmp_path / "studio" / "trajectories.jsonl"
    assert traj.exists()
    line = traj.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert entry["tool"] == "bash"
    assert entry["session_id"] == "s1"
    assert entry["profile_id"] == "alice"
    assert entry["args"] == {"cmd": "ls"}
    assert entry["duration_s"] == 0.5
    assert "retry_report" not in entry  # no retry metadata in result
    assert "idempotency_key" not in entry


def test_seeker_writes_retry_metadata_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("STUDIO_RECORD_TRAJECTORIES", "1")
    seeker = Seeker()
    result_payload = json.dumps({
        "ok": True,
        "tool": "studio_render_image",
        "idempotency_key": "image_xyz",
        "retry_report": {
            "final_outcome": "ok",
            "attempts": [{"n": 1, "ok": True, "duration_s": 0.3}],
        },
    })
    seeker.post_tool_call(
        tool_name="studio_render_image", result=result_payload,
        duration=0.3, session_id="s1", profile_id="alice",
    )
    traj = tmp_path / "studio" / "trajectories.jsonl"
    line = traj.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert entry["idempotency_key"] == "image_xyz"
    assert entry["retry_report"]["final_outcome"] == "ok"
    assert entry["retry_report"]["attempts"][0]["n"] == 1


def test_seeker_writes_failed_retry_report(tmp_path, monkeypatch):
    """Permanent failures still get logged for replay/diagnosis."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("STUDIO_RECORD_TRAJECTORIES", "1")
    seeker = Seeker()
    result_payload = json.dumps({
        "ok": False,
        "error": "fal_call_failed",
        "outcome": "permanent",
        "retry_report": {
            "final_outcome": "permanent",
            "attempts": [{
                "n": 1, "ok": False,
                "error_type": "PermanentError",
                "error_message": "Exhausted balance",
            }],
        },
    })
    seeker.post_tool_call(
        tool_name="studio_render_image", result=result_payload,
        duration=0.2, session_id="s1", profile_id="alice",
    )
    traj = tmp_path / "studio" / "trajectories.jsonl"
    entry = json.loads(traj.read_text(encoding="utf-8").strip())
    assert entry["retry_report"]["final_outcome"] == "permanent"
    assert entry["retry_report"]["attempts"][0]["error_type"] == "PermanentError"
