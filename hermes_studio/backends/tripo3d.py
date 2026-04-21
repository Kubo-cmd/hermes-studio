"""Tripo3D text-to-3D backend.

Thin HTTP client for the Tripo3D API. v0.1 is synchronous and polls for
task completion. Replace with async + websocket in v0.2 when Studio's
render_3d handler goes non-blocking.

Docs: https://platform.tripo3d.ai/docs
"""

from __future__ import annotations

import os
import time
from typing import Literal

import urllib.request
import json

API_BASE = "https://api.tripo3d.ai/v2/openapi"


class Tripo3DError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    key = os.environ["TRIPO3D_API_KEY"]
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API_BASE}{path}", headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def text_to_glb(
    prompt: str,
    poly_budget: Literal["low", "medium", "high"] = "medium",
    poll_interval_s: float = 5.0,
    timeout_s: float = 600.0,
) -> str:
    """Submit a text-to-3D job, poll until complete, return a GLB URL."""
    create = _post("/task", {"type": "text_to_model", "prompt": prompt, "model_version": "v2.0"})
    task_id = create["data"]["task_id"]

    start = time.time()
    while True:
        if time.time() - start > timeout_s:
            raise Tripo3DError(f"timeout waiting for task {task_id}")
        status = _get(f"/task/{task_id}")
        state = status["data"]["status"]
        if state == "success":
            return status["data"]["output"]["model"]
        if state in {"failed", "cancelled", "banned"}:
            raise Tripo3DError(f"task {task_id} {state}")
        time.sleep(poll_interval_s)
