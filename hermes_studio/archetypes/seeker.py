"""
Seeker — self-improvement telemetry.

Seeker logs tool-call trajectories in a format compatible with Nous's
Atropos RL environment framework, so Studio sessions can be replayed
as training data for improving the agent's creative workflow behavior.

In v0.1 Seeker writes to a JSONL file at ~/.hermes/studio/trajectories.jsonl.
Each line is a single tool call with inputs, outputs, duration, and the
Shadow classification. Opt-in via STUDIO_RECORD_TRAJECTORIES=1.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _traj_path() -> Path:
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    d = home / "studio"
    d.mkdir(parents=True, exist_ok=True)
    return d / "trajectories.jsonl"


class Seeker:
    def __init__(self) -> None:
        self._enabled = os.environ.get("STUDIO_RECORD_TRAJECTORIES") == "1"
        self._path = _traj_path()

    def post_tool_call(
        self,
        tool_name: str,
        result: str,
        duration: float | None = None,
        session_id: str = "",
        profile_id: str = "default",
        args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self._enabled:
            return
        entry = {
            "ts": time.time(),
            "profile_id": profile_id,
            "session_id": session_id,
            "tool": tool_name,
            "args": args or {},
            "result_preview": (result[:500] if isinstance(result, str) else ""),
            "duration_s": float(duration) if duration is not None else None,
        }
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Never block the agent loop on logging IO.
            pass
