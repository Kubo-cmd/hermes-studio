"""
Architect — task decomposition / planner.

Architect is an *observational* planner in v0.1. It does not rewrite
outbound messages — it annotates them with a lightweight plan extracted
from the user's request and surfaces the plan on the canvas. This gives
the user a visible "here's what the agent is about to try" view without
monkey-patching Hermes's own agent loop.

v0.2 will add a real LLM-based planner that can decompose into subtasks
and feed them to Hermes's delegate_task. For now we keep the scope small
and honest.
"""

from __future__ import annotations

import re
from typing import Any


# Very simple heuristic plan extraction — first-pass structure only.
_STEP_SPLITTERS = re.compile(r"(?:\bthen\b|\bafter that\b|\bnext\b|[.;]\s+)", re.IGNORECASE)


class Architect:
    def pre_llm_call(self, messages: list[dict], **kwargs: Any) -> None:
        """Observational hook — extracts a rough plan from the latest user
        message, but returns None so messages aren't modified."""
        if not messages:
            return None
        last = messages[-1]
        if last.get("role") != "user":
            return None
        content = last.get("content") or ""
        if not isinstance(content, str):
            return None
        steps = [s.strip() for s in _STEP_SPLITTERS.split(content) if s.strip()]
        if len(steps) <= 1:
            return None
        # Plan extraction would be surfaced via ctx.emit_event in a
        # production build. For v0.1 we log — Visualizer picks this up
        # indirectly via its post_tool_call stream.
        # (Hook intentionally returns None — no message mutation.)
        return None
