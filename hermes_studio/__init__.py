"""
hermes-studio — a creative surface for Hermes Agent.

This is the plugin entry point. It registers eight archetype components
with the Hermes plugin system:

    Architect  — task decomposition (pre_llm_call hook)
    Guardian   — secret redaction (pre_llm_call + post_tool_call hooks)
    Keeper     — session-scoped memory (session lifecycle hooks)
    Shadow     — subagent watchdog (post_tool_call hook)
    Creator    — multi-modal rendering tools
    Visualizer — canvas event stream (websocket via FastAPI)
    Balancer   — output formatting (not a hook; called by Creator)
    Seeker     — self-improvement telemetry (post_tool_call hook)

Each archetype is a self-contained component in hermes_studio/archetypes/.
None of them monkey-patch Hermes or replace core functionality — they hook
in alongside it using the documented plugin API.
"""

from __future__ import annotations

import logging
from typing import Any

from .archetypes.architect import Architect
from .archetypes.guardian import Guardian
from .archetypes.keeper import Keeper
from .archetypes.shadow import Shadow
from .archetypes.creator import Creator
from .archetypes.visualizer import Visualizer
from .archetypes.balancer import Balancer
from .archetypes.seeker import Seeker
from .schemas import (
    STUDIO_RENDER_IMAGE_SCHEMA,
    STUDIO_RENDER_3D_SCHEMA,
    STUDIO_RENDER_VIDEO_SCHEMA,
    STUDIO_RENDER_AUDIO_SCHEMA,
    STUDIO_TIMELINE_FORK_SCHEMA,
)

log = logging.getLogger("hermes_studio")


# Module-level archetype instances. The plugin context holds these for the
# lifetime of the Hermes process.
_ARCHETYPES: dict[str, Any] = {}


def register(ctx) -> None:
    """Entry point called by Hermes at plugin load time.

    `ctx` is the Hermes plugin context. We use it to:
      - register tool schemas + handlers
      - register lifecycle hooks
      - optionally register skills the agent can discover

    Contract reference:
      https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin
    """
    # Instantiate archetypes once. Pass the plugin ctx so they can emit
    # events on the Visualizer's websocket.
    guardian = Guardian()
    keeper = Keeper()
    visualizer = Visualizer(ctx=ctx)
    shadow = Shadow()
    balancer = Balancer()
    creator = Creator(guardian=guardian, visualizer=visualizer, balancer=balancer)
    architect = Architect()
    seeker = Seeker()

    _ARCHETYPES.update(
        architect=architect,
        guardian=guardian,
        keeper=keeper,
        shadow=shadow,
        creator=creator,
        visualizer=visualizer,
        balancer=balancer,
        seeker=seeker,
    )

    # ----- Tools (Creator + Timeline) -----
    ctx.register_tool(
        name="studio_render_image",
        schema=STUDIO_RENDER_IMAGE_SCHEMA,
        handler=lambda args, **kw: creator.render_image(args, **kw),
    )
    ctx.register_tool(
        name="studio_render_3d",
        schema=STUDIO_RENDER_3D_SCHEMA,
        handler=lambda args, **kw: creator.render_3d(args, **kw),
    )
    ctx.register_tool(
        name="studio_render_video",
        schema=STUDIO_RENDER_VIDEO_SCHEMA,
        handler=lambda args, **kw: creator.render_video(args, **kw),
    )
    ctx.register_tool(
        name="studio_render_audio",
        schema=STUDIO_RENDER_AUDIO_SCHEMA,
        handler=lambda args, **kw: creator.render_audio(args, **kw),
    )
    ctx.register_tool(
        name="studio_timeline_fork",
        schema=STUDIO_TIMELINE_FORK_SCHEMA,
        handler=lambda args, **kw: keeper.fork(args, **kw),
    )

    # ----- Lifecycle hooks -----
    ctx.register_hook("on_session_start", keeper.on_session_start)
    ctx.register_hook("on_session_end", keeper.on_session_end)

    # Pre-LLM: Guardian sanitizes outgoing context; Architect annotates plan.
    ctx.register_hook("pre_llm_call", guardian.pre_llm_call)
    ctx.register_hook("pre_llm_call", architect.pre_llm_call)

    # Post tool-call: Guardian redacts results, Shadow records timings,
    # Seeker logs trajectories, Visualizer pushes to canvas.
    ctx.register_hook("post_tool_call", guardian.post_tool_call)
    ctx.register_hook("post_tool_call", shadow.post_tool_call)
    ctx.register_hook("post_tool_call", seeker.post_tool_call)
    ctx.register_hook("post_tool_call", visualizer.post_tool_call)

    log.info("hermes-studio registered: 8 archetypes, 5 tools, 4 hooks")


def shutdown() -> None:
    """Called on plugin unload / Hermes shutdown. Flush anything buffered."""
    vis = _ARCHETYPES.get("visualizer")
    if vis is not None:
        vis.close()
