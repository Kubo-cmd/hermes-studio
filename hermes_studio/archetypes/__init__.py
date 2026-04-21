"""hermes-studio archetypes package.

Each archetype is a single-responsibility component with a clearly
scoped integration point into the Hermes plugin system.

    Architect  — pre_llm_call hook, plan extraction
    Guardian   — pre_llm_call + post_tool_call hooks, secret redaction
    Keeper     — session lifecycle + timeline storage
    Shadow     — post_tool_call hook, tool-call classification
    Creator    — tool handlers for multi-modal rendering
    Visualizer — canvas event stream + FastAPI websocket
    Balancer   — per-gateway output formatting
    Seeker     — optional trajectory logging for training data
"""

from .architect import Architect
from .balancer import Balancer
from .creator import Creator
from .guardian import Guardian, redact
from .keeper import Keeper
from .seeker import Seeker
from .shadow import Shadow, ShadowReport
from .visualizer import CanvasEvent, Visualizer

__all__ = [
    "Architect",
    "Balancer",
    "CanvasEvent",
    "Creator",
    "Guardian",
    "Keeper",
    "Seeker",
    "Shadow",
    "ShadowReport",
    "Visualizer",
    "redact",
]
