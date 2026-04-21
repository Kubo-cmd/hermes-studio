"""
hermes-studio plugin API.

Registered by plugin.yaml via `api: hermes_studio.api:router`. Mounted by
Hermes's dashboard server at /api/plugins/hermes-studio/*.

Routes:
    GET  /health                         → plugin health
    GET  /timeline/{session_id}          → Keeper.list_session for this session
    WS   /ws/canvas                      → live canvas event stream
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import _ARCHETYPES
from .archetypes.visualizer import Visualizer

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "plugin": "hermes-studio",
        "archetypes_loaded": sorted(_ARCHETYPES.keys()),
    }


@router.get("/timeline/{session_id}")
async def timeline(session_id: str, profile_id: str = "default", limit: int = 500) -> dict[str, Any]:
    keeper = _ARCHETYPES.get("keeper")
    if keeper is None:
        return {"ok": False, "error": "keeper not loaded"}
    entries = keeper.list_session(session_id, profile_id=profile_id, limit=limit)
    return {"ok": True, "session_id": session_id, "profile_id": profile_id, "entries": entries}


@router.get("/shadow/recent")
async def shadow_recent(limit: int = 20) -> dict[str, Any]:
    shadow = _ARCHETYPES.get("shadow")
    if shadow is None:
        return {"ok": False, "error": "shadow not loaded"}
    reports = shadow.recent_slow_or_stuck(limit=limit)
    return {
        "ok": True,
        "reports": [
            {
                "tool": r.tool_name,
                "duration_s": r.duration_s,
                "level": r.level,
                "session_id": r.session_id,
                "profile_id": r.profile_id,
            }
            for r in reports
        ],
    }


@router.websocket("/ws/canvas")
async def ws_canvas(ws: WebSocket) -> None:
    """Live canvas event stream.

    Query params:
        session_id  — filter to one session (optional)
        profile_id  — required for isolation (defaults to "default")
    """
    await ws.accept()
    session_id = ws.query_params.get("session_id", "")
    profile_id = ws.query_params.get("profile_id", "default")

    visualizer: Visualizer | None = _ARCHETYPES.get("visualizer")
    if visualizer is None:
        await ws.send_text(json.dumps({"error": "visualizer not loaded"}))
        await ws.close()
        return

    queue, replay = visualizer.subscribe(session_id=session_id, profile_id=profile_id)

    # Flush replay buffer first so late joiners see recent history.
    for evt in replay:
        await ws.send_text(Visualizer.event_to_json(evt))

    try:
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keepalive ping — some proxies close idle websockets at 60s.
                await ws.send_text(json.dumps({"ts": 0, "kind": "ping", "payload": {}}))
                continue
            # Enforce isolation server-side as defense-in-depth
            if evt.profile_id != profile_id:
                continue
            if session_id and evt.session_id != session_id:
                continue
            await ws.send_text(Visualizer.event_to_json(evt))
    except WebSocketDisconnect:
        pass
    finally:
        visualizer.unsubscribe(queue)
