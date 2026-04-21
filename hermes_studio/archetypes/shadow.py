"""
Shadow — the subagent watchdog.

Addresses the *observability* half of Hermes issue #11431 (multi-round
subagent runs become very slow). The real fix for the root cause —
ThreadPoolExecutor shutdown semantics and oversized inherited toolsets —
is a PR to hermes-agent itself. Shadow's job is to make the problem
*visible* so creative workflows know when they're waiting on a stuck child.

Shadow tracks tool-call durations and emits a telemetry event when:
  - a tool call exceeds a soft threshold (default 30s): "slow"
  - a tool call exceeds the hard threshold (default 180s): "stuck"

Events are picked up by Visualizer and shown on the canvas as a
"this is taking a while" indicator, so users can /stop manually instead
of wondering if their 4-hour creative run has frozen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_SOFT_TIMEOUT_S = 30.0
DEFAULT_HARD_TIMEOUT_S = 180.0


@dataclass
class _InFlight:
    tool_name: str
    started_at: float
    profile_id: str
    session_id: str


@dataclass
class ShadowReport:
    tool_name: str
    duration_s: float
    level: str  # "ok" | "slow" | "stuck"
    session_id: str
    profile_id: str
    extras: dict[str, Any] = field(default_factory=dict)


class Shadow:
    def __init__(
        self,
        soft_timeout_s: float = DEFAULT_SOFT_TIMEOUT_S,
        hard_timeout_s: float = DEFAULT_HARD_TIMEOUT_S,
    ) -> None:
        self.soft = soft_timeout_s
        self.hard = hard_timeout_s
        self._in_flight: dict[str, _InFlight] = {}
        self._reports: list[ShadowReport] = []

    def track_start(self, call_id: str, tool_name: str, session_id: str, profile_id: str) -> None:
        """Called by the plugin context when a tool call begins.

        Note: Hermes's plugin API exposes post_tool_call but not a direct
        pre_tool_call hook with call_id. For production use, either:
          - wrap the tool handler to call this yourself, or
          - use the pluggable context engine slot (PR #7464) to inject a
            pre-tool span.
        The default flow here uses post_tool_call with duration passed in
        kwargs (Hermes supplies `duration` since v0.8).
        """
        self._in_flight[call_id] = _InFlight(
            tool_name=tool_name,
            started_at=time.time(),
            profile_id=profile_id,
            session_id=session_id,
        )

    def post_tool_call(
        self,
        tool_name: str,
        result: str,
        duration: float | None = None,
        session_id: str = "",
        profile_id: str = "default",
        **kwargs: Any,
    ) -> None:
        """Hermes post_tool_call hook.

        `duration` is supplied by Hermes in the standard hook payload.
        We classify and record; we never modify the result here
        (Guardian owns that). Returning None means no replacement.
        """
        d = float(duration) if duration is not None else 0.0
        if d >= self.hard:
            level = "stuck"
        elif d >= self.soft:
            level = "slow"
        else:
            level = "ok"

        self._reports.append(
            ShadowReport(
                tool_name=tool_name,
                duration_s=d,
                level=level,
                session_id=session_id,
                profile_id=profile_id,
            )
        )

    @property
    def reports(self) -> list[ShadowReport]:
        return list(self._reports)

    def recent_slow_or_stuck(self, limit: int = 20) -> list[ShadowReport]:
        return [r for r in self._reports if r.level != "ok"][-limit:]
