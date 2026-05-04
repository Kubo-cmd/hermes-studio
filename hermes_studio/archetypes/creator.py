"""
Creator - the multi-modal rendering archetype.

v0.2: now uses retry helpers for legible, idempotent backend calls.
Each render generates an idempotency key from the input args. Retry
attempts and outcomes are captured in the response payload so the
agent (and Seeker) can replay or diagnose failures.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..utils.retry import (
    call_with_retry,
    make_idempotency_key,
    PermanentError,
    TransientError,
)

if TYPE_CHECKING:
    from .guardian import Guardian
    from .visualizer import Visualizer
    from .balancer import Balancer

log = logging.getLogger("hermes_studio.creator")


def _media_dir():
    override = os.environ.get("STUDIO_MEDIA_DIR")
    if override:
        p = Path(override)
    else:
        home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        p = home / "studio" / "media"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _missing_backend_error(tool, env_var, signup_url):
    return json.dumps({
        "ok": False,
        "tool": tool,
        "error": "backend_not_configured",
        "missing_env": env_var,
        "how_to_fix": (
            "Set " + env_var + " in ~/.hermes/.env. "
            "Get a key from " + signup_url + ". "
            "Then run: hermes doctor"
        ),
    })


class Creator:
    def __init__(self, guardian, visualizer, balancer):
        self.guardian = guardian
        self.visualizer = visualizer
        self.balancer = balancer

    def render_image(self, args, **kwargs):
        if not os.environ.get("FAL_KEY"):
            return _missing_backend_error("studio_render_image", "FAL_KEY", "https://fal.ai/")
        prompt = args["prompt"]
        aspect = args.get("aspect_ratio", "1:1")
        style = args.get("style")

        try:
            import fal_client
        except ImportError:
            return json.dumps({
                "ok": False,
                "error": "fal_client not installed",
                "how_to_fix": "pip install fal-client",
            })

        idem = make_idempotency_key("image", {
            "prompt": prompt, "aspect": aspect, "style": style,
        })
        full_prompt = (prompt + ". Style: " + style) if style else prompt

        def _do_call():
            return fal_client.run(
                "fal-ai/flux/schnell",
                arguments={"prompt": full_prompt, "image_size": self._fal_size(aspect)},
            )

        result, report = call_with_retry(_do_call, idempotency_key=idem)

        if report.final_outcome != "ok":
            return json.dumps({
                "ok": False,
                "tool": "studio_render_image",
                "error": "fal_call_failed",
                "outcome": report.final_outcome,
                "retry_report": report.as_dict(),
            })

        image_url = result["images"][0]["url"] if result.get("images") else None
        if not image_url:
            return json.dumps({
                "ok": False,
                "error": "no_image_returned",
                "retry_report": report.as_dict(),
            })

        local_path = _media_dir() / ("img_" + uuid.uuid4().hex + ".jpg")
        self._download(image_url, local_path)
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
            "idempotency_key": idem,
            "retry_report": report.as_dict(),
        })

    def _fal_size(self, aspect):
        return {
            "1:1": "square_hd", "16:9": "landscape_16_9", "9:16": "portrait_9_16",
            "4:3": "landscape_4_3", "3:4": "portrait_4_3",
        }.get(aspect, "square_hd")

    def _download(self, url, dst):
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=30) as r, open(dst, "wb") as f:
                f.write(r.read())
        except Exception as e:
            log.warning("download failed: %s", e)

    def render_3d(self, args, **kwargs):
        if not os.environ.get("TRIPO3D_API_KEY"):
            return _missing_backend_error(
                "studio_render_3d", "TRIPO3D_API_KEY", "https://platform.tripo3d.ai/"
            )
        from ..backends import tripo3d

        prompt = args["prompt"]
        poly = args.get("poly_budget", "medium")
        idem = make_idempotency_key("3d", {"prompt": prompt, "poly": poly})

        def _do_call():
            return tripo3d.text_to_glb(prompt, poly_budget=poly)

        glb_url, report = call_with_retry(_do_call, idempotency_key=idem)

        if report.final_outcome != "ok":
            return json.dumps({
                "ok": False,
                "tool": "studio_render_3d",
                "error": "tripo3d_call_failed",
                "outcome": report.final_outcome,
                "retry_report": report.as_dict(),
            })

        local_path = _media_dir() / ("model_" + uuid.uuid4().hex + ".glb")
        self._download(glb_url, local_path)
        self.visualizer.emit(
            kind="3d",
            session_id=kwargs.get("session_id", ""),
            profile_id=kwargs.get("profile_id", "default"),
            payload={"prompt": prompt, "local_path": str(local_path)},
        )
        return json.dumps({
            "ok": True,
            "tool": "studio_render_3d",
            "local_path": str(local_path),
            "idempotency_key": idem,
            "retry_report": report.as_dict(),
        })

    def render_video(self, args, **kwargs):
        return json.dumps({
            "ok": False,
            "tool": "studio_render_video",
            "error": "not_yet_implemented",
            "shipping_in": "v0.3 - day 5 of the hackathon build log",
            "spec": (
                "Compose video from storyboard: for each shot, render image "
                "and optional voiceover, then ffmpeg-concat with 0.5s crossfades."
            ),
        })

    def render_audio(self, args, **kwargs):
        kind = args.get("kind", "narration")
        if kind != "narration":
            return json.dumps({
                "ok": False,
                "error": "only narration implemented in v0.1",
                "music_and_sfx_shipping_in": "v0.2",
            })
        text = args.get("text")
        if not text:
            return json.dumps({"ok": False, "error": "text required for narration"})
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
