"""
Balancer — output formatting / presentation.

Balancer takes raw archetype outputs and formats them for the gateway
that will deliver them (Telegram markdown, Discord embeds, Slack blocks,
plain terminal). This archetype is intentionally thin in v0.1 — it's a
seam where future per-platform formatting goes, without scattering
platform-specific code across Creator.
"""

from __future__ import annotations

from typing import Any


class Balancer:
    def format_for_gateway(
        self,
        platform: str,
        kind: str,
        payload: dict[str, Any],
    ) -> str:
        """Return a gateway-appropriate string representation of an event.

        Platforms: "cli" | "telegram" | "discord" | "slack" | "signal" | "web"
        """
        if kind == "image":
            url = payload.get("url") or payload.get("local_path", "")
            if platform in {"telegram", "discord", "slack"}:
                return f"🖼 {payload.get('prompt', '')}\n{url}"
            return f"[image] {payload.get('prompt', '')} -> {url}"

        if kind == "3d":
            return f"[3D asset] {payload.get('prompt', '')} -> {payload.get('local_path', '')}"

        if kind == "audio":
            return f"🔊 {payload.get('text', '')[:80]}"

        if kind == "shadow_warning":
            return f"⚠ {payload.get('tool', 'tool')} is {payload.get('level', 'slow')} ({payload.get('duration_s', 0):.1f}s)"

        return str(payload)
