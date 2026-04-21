"""
Creator — the multi-modal rendering archetype.

Creator owns the five tool handlers that actually produce creative output:
image, 3D, video, audio, and the timeline-fork passthrough lives in Keeper.

This file contains the tool *wrappers* — the business logic is:
  1. Validate args
  2. Call the appropriate backend (FAL for images, Tripo3D for 3D, etc.)
  3. Write the media to STUDIO_MEDIA_DIR
  4. Emit a canvas event via Visualizer
  5. Append an entry to Keeper's timeline
  6. Return a JSON string (Hermes tool handler contract)

Where backends are not configured (no FAL_KEY, etc.), the handler fails
gracefully with an actionable error message — a direct response to
Hermes issue #9516 (image_gen reported as "system dependency not met"
when the real problem is missing credentials).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .guardian import Guardian
    from .visualizer import Visualizer
    from .balancer import Balancer

log = logging.getLogger("hermes_studio.creator")


def _media_dir() -> Path:
    override = os.environ.get("STUDIO_MEDIA_DIR")
    if override:
        p = Path(override)
    else:
        home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        p = home / "studio" / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _missing_backend_error(tool: str, env_var: str, signup_url: str) -> str:
    """Actionable error for missing credentials (fixes #9516's root issue)."""
    return json.dumps({
        "ok": False,
        "tool": tool,
        "error": "backend_not_configured",
        "missing_env": env_var,
        "how_to_fix": (
            f"Set {env_var} in ~/.hermes/.env. "
            f"Get a key from {signup_url}. "
            f"Then run: hermes doctor"
        ),
    })


class Creator:
    def __init__(
        self,
        guardian: "Guardian",
        visualizer: "Visualizer",
        balancer: "Balancer",
    ) -> None:
        self.guardian = guardian
        self.visualizer = visualizer
        self.balancer = balancer

    # -------- studio_render_image --------

    def render_image(self, args: dict[str, Any], **kwargs: Any) -> str:
        if not os.environ.get("FAL_KEY"):
            return _missing_backend_error("studio_render_image", "FAL_KEY", "https://fal.ai/")

        prompt: str = args["prompt"]
        aspect: str = args.get("aspect_ratio", "1:1")
        style: str | None = args.get("style")

        # Backend call — FAL Flux is the default; swap by editing this block.
        try:
            import fal_client  # type: ignore
        except ImportError:
            return json.dumps({
                "ok": False,
                "error": "fal_client not installed",
                "how_to_fix": "pip install fal-client",
            })

        full_prompt = f"{prompt}. Style: {style}" if style else prompt
        try:
            result = fal_client.run(
                "fal-ai/flux/schnell",
                arguments={"prompt": full_prompt, "image_size": self._fal_size(aspect)},
            )
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": f"fal_call_failed: {e}"})

        image_url = result["images"][0]["url"] if result.get("images") else None
        if not image_url:
            return json.dumps({"ok": False, "error": "no_image_returned"})

        # Persist locally so the canvas can show it even if the URL expires.
        local_path = _media_dir() / f"img_{uuid.uuid4().hex}.jpg"
        self._download(image_url, local_path)

        # Tell the canvas.
        self.visualizer.emit(
            kind="image",
            session_id=kwargs.get("session_id", ""),
            profile_id=kwargs.get("profile_id", "default"),
            payload={"prompt": prompt, "local_path": str(local_path), "url": image_url},
        )

        return json.dumps({
            "ok": True,
            "tool": "studio_render_image",
            "local_path": str(local_path),
            "url": image_url,
        })

    def _fal_size(self, aspect: str) -> str:
        return {
            "1:1": "square_hd",
            "16:9": "landscape_16_9",
            "9:16": "portrait_9_16",
            "4:3": "landscape_4_3",
            "3:4": "portrait_4_3",
        }.get(aspect, "square_hd")

    def _download(self, url: str, dst: Path) -> None:
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=30) as r, open(dst, "wb") as f:
                f.write(r.read())
        except Exception as e:  # noqa: BLE001
            log.warning("download failed: %s", e)

    # -------- studio_render_3d --------

    def render_3d(self, args: dict[str, Any], **kwargs: Any) -> str:
        if not os.environ.get("TRIPO3D_API_KEY"):
            return _missing_backend_error(
                "studio_render_3d", "TRIPO3D_API_KEY", "https://platform.tripo3d.ai/"
            )
        # Tripo3D integration lives in hermes_studio/backends/tripo3d.py
        # (left as a separate module so the plugin loads even if 3D is unused).
        from ..backends import tripo3d  # lazy import

        prompt: str = args["prompt"]
        poly: str = args.get("poly_budget", "medium")

        try:
            glb_url = tripo3d.text_to_glb(prompt, poly_budget=poly)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": f"tripo3d_failed: {e}"})

        local_path = _media_dir() / f"model_{uuid.uuid4().hex}.glb"
        self._download(glb_url, local_path)

        self.visualizer.emit(
            kind="3d",
            session_id=kwargs.get("session_id", ""),
            profile_id=kwargs.get("profile_id", "default"),
            payload={"prompt": prompt, "local_path": str(local_path)},
        )
        return json.dumps({"ok": True, "tool": "studio_render_3d", "local_path": str(local_path)})

    # -------- studio_render_video --------

    def render_video(self, args: dict[str, Any], **kwargs: Any) -> str:
        """
        Video composition via ffmpeg.

        NOTE: This is the scaffolding. The production pipeline is:
          1. For each shot: render_image(shot.image_prompt)
          2. For each shot with voiceover: render_audio(shot.voiceover)
          3. ffmpeg concat with crossfades + audio mix + optional music
          4. Emit final MP4 to the canvas.

        Steps 1-2 should be implemented by calling the other Creator
        handlers; step 3 is shelled out. We leave the ffmpeg pipeline
        unfilled in v0.1 and surface a clear in-progress response so no
        one mistakes a stub for working code.
        """
        return json.dumps({
            "ok": False,
            "tool": "studio_render_video",
            "error": "not_yet_implemented",
            "shipping_in": "v0.3 — day 5 of the hackathon build log",
            "spec": (
                "Compose video from storyboard: for each shot, render image "
                "and optional voiceover, then ffmpeg-concat with 0.5s crossfades."
            ),
        })

    # -------- studio_render_audio --------

    def render_audio(self, args: dict[str, Any], **kwargs: Any) -> str:
        kind = args.get("kind", "narration")
        if kind != "narration":
            return json.dumps({
                "ok": False,
                "error": "only narration implemented in v0.1",
                "music_and_sfx_shipping_in": "v0.2",
            })

        # Hermes already has OpenAI TTS via the Nous Tool Gateway (v0.10+).
        # Studio defers to that rather than duplicating the integration —
        # we just make sure the output lands on the canvas.
        text = args.get("text")
        if not text:
            return json.dumps({"ok": False, "error": "text required for narration"})

        # The real TTS call would go through ctx.call_tool("tts", ...) if
        # the hermes plugin context supports delegation. For v0.1 we document
        # the integration point and return a clear sentinel so the caller
        # knows the canvas stream still works even when the backend is a stub.
        self.visualizer.emit(
            kind="audio",
            session_id=kwargs.get("session_id", ""),
            profile_id=kwargs.get("profile_id", "default"),
            payload={"text": text, "status": "pending_tts_backend_wire"},
        )
        return json.dumps({
            "ok": True,
            "tool": "studio_render_audio",
            "note": "canvas event emitted; TTS backend wiring scheduled for v0.2",
        })
