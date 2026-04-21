"""
Visualizer — the canvas event stream.

This is the archetype that actually solves "Hermes is text-only": it
provides an in-process event stream that the dashboard plugin consumes
over a websocket, giving the user a live, visual feed of what the agent
is making.

Canvas events have a stable schema so the frontend can render them
without knowing which tool produced them. Every event includes the
session_id + profile_id so the canvas enforces the same isolation
boundary Keeper does — no cross-profile leakage.

In v0.1 we use a simple in-memory asyncio.Queue plus a FastAPI
/ws/canvas websocket route. For multi-process deployments the queue
can be replaced with Redis pub/sub without changing the event schema.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class CanvasEvent:
    ts: float
    kind: str              # image | 3d | video | audio | text | tool_call | shadow_warning
    session_id: str
    profile_id: str
    payload: dict[str, Any]


class Visualizer:
    def __init__(self, ctx: Any = None) -> None:
        self.ctx = ctx
        # Fan-out queues — one per active websocket subscriber.
        self._subscribers: list[asyncio.Queue[CanvasEvent]] = []
        # Bounded replay buffer so a subscriber that connects mid-session
        # can catch up on the last N events.
        self._replay: list[CanvasEvent] = []
        self._replay_cap = 500
        self._closed = False

    # ---- emission (called from Creator, Shadow, hooks) ----

    def emit(
        self,
        kind: str,
        session_id: str,
        profile_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._closed:
            return
        evt = CanvasEvent(
            ts=time.time(),
            kind=kind,
            session_id=session_id,
            profile_id=profile_id,
            payload=payload,
        )
        self._replay.append(evt)
        if len(self._replay) > self._replay_cap:
            self._replay = self._replay[-self._replay_cap :]
        for q in list(self._subscribers):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                # Slow subscriber — drop. Replay buffer lets them resync.
                pass

    # ---- post_tool_call hook (records tool activity on canvas) ----

    def post_tool_call(
        self,
        tool_name: str,
        result: str,
        session_id: str = "",
        profile_id: str = "default",
        **kwargs: Any,
    ) -> None:
        # Don't double-emit: Creator's own render_* handlers already emit
        # rich events. For other tools (bash, web_search, etc.) we emit
        # a thin tool_call event so the canvas timeline stays coherent.
        if tool_name.startswith("studio_"):
            return
        self.emit(
            kind="tool_call",
            session_id=session_id,
            profile_id=profile_id,
            payload={"tool": tool_name, "result_preview": result[:200] if isinstance(result, str) else ""},
        )

    # ---- subscription (called by the websocket route) ----

    def subscribe(self, session_id: str, profile_id: str) -> tuple[asyncio.Queue[CanvasEvent], list[CanvasEvent]]:
        """Return a live queue plus the replay buffer filtered to (profile, session)."""
        q: asyncio.Queue[CanvasEvent] = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        replay = [
            e for e in self._replay
            if e.profile_id == profile_id and (not session_id or e.session_id == session_id)
        ]
        return q, replay

    def unsubscribe(self, q: asyncio.Queue[CanvasEvent]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def close(self) -> None:
        self._closed = True
        self._subscribers.clear()

    @staticmethod
    def event_to_json(evt: CanvasEvent) -> str:
        return json.dumps(asdict(evt))
