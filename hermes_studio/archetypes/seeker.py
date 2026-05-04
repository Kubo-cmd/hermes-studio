"""Seeker - opt-in trajectory logging for replay and analysis.

v0.2: trajectories now capture retry_report when present in the result
payload. This makes any failed render replayable and any successful
render auditable.

Schema (one JSON object per line):
    ts: float           epoch seconds
    profile_id: str     scoping
    session_id: str
    tool: str           tool name
    args: dict          input args
    result_preview: str first 500 chars of result string
    duration_s: float   wall-clock duration
    retry_report: dict  optional - present if Creator returned one
    idempotency_key: str optional - present if Creator returned one
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _traj_path():
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    d = home / "studio"
    d.mkdir(parents=True, exist_ok=True)
    return d / "trajectories.jsonl"


def _maybe_extract_retry_metadata(result):
    """Pull retry_report and idempotency_key out of result JSON if present.

    Returns (retry_report, idempotency_key). Both default to None.
    Never raises - if the result is not JSON, just returns (None, None).
    """
    if not isinstance(result, str):
        return None, None
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    return parsed.get("retry_report"), parsed.get("idempotency_key")


class Seeker:
    def __init__(self):
        self._enabled = os.environ.get("STUDIO_RECORD_TRAJECTORIES") == "1"
        self._path = _traj_path()

    def post_tool_call(
        self,
        tool_name,
        result,
        duration=None,
        session_id="",
        profile_id="default",
        args=None,
        **kwargs,
    ):
        if not self._enabled:
            return

        retry_report, idem_key = _maybe_extract_retry_metadata(result)

        entry = {
            "ts": time.time(),
            "profile_id": profile_id,
            "session_id": session_id,
            "tool": tool_name,
            "args": args or {},
            "result_preview": (result[:500] if isinstance(result, str) else ""),
            "duration_s": float(duration) if duration is not None else None,
        }
        if retry_report is not None:
            entry["retry_report"] = retry_report
        if idem_key is not None:
            entry["idempotency_key"] = idem_key

        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass
