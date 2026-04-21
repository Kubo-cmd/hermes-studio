"""Tool schemas — the JSON-schema definitions the LLM sees when deciding
which tool to call. Follows the Hermes plugin tool schema format
(OpenAI-compatible function calling).
"""

STUDIO_RENDER_IMAGE_SCHEMA = {
    "name": "studio_render_image",
    "description": (
        "Generate an image and display it on the Studio canvas. "
        "Use this whenever you want to produce a visual output the user "
        "should SEE rather than read about. Streams to the canvas websocket "
        "so the user sees it live."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed image description.",
            },
            "aspect_ratio": {
                "type": "string",
                "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                "default": "1:1",
            },
            "style": {
                "type": "string",
                "description": "Optional style hint (e.g. 'cinematic', 'anime', 'technical diagram').",
            },
        },
        "required": ["prompt"],
    },
}

STUDIO_RENDER_3D_SCHEMA = {
    "name": "studio_render_3d",
    "description": (
        "Generate a 3D asset (GLB format) and display it on the Studio canvas "
        "in an interactive viewport. Use when the user wants a 3D object, "
        "scene, or character."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "What to generate in 3D.",
            },
            "poly_budget": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "default": "medium",
                "description": "Polygon budget for the mesh.",
            },
        },
        "required": ["prompt"],
    },
}

STUDIO_RENDER_VIDEO_SCHEMA = {
    "name": "studio_render_video",
    "description": (
        "Compose a short video from a storyboard. Each shot is an image "
        "prompt + duration + optional voiceover line. Studio composites "
        "via ffmpeg and renders on the canvas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "shots": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "image_prompt": {"type": "string"},
                        "duration_seconds": {"type": "number"},
                        "voiceover": {"type": "string"},
                    },
                    "required": ["image_prompt", "duration_seconds"],
                },
            },
            "music_prompt": {"type": "string"},
        },
        "required": ["shots"],
    },
}

STUDIO_RENDER_AUDIO_SCHEMA = {
    "name": "studio_render_audio",
    "description": "Generate audio (narration, music, or sfx) and show it on the canvas.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Narration text (for TTS)."},
            "kind": {
                "type": "string",
                "enum": ["narration", "music", "sfx"],
                "default": "narration",
            },
            "voice": {"type": "string", "description": "Optional voice ID for narration."},
        },
        "required": ["kind"],
    },
}

STUDIO_TIMELINE_FORK_SCHEMA = {
    "name": "studio_timeline_fork",
    "description": (
        "Fork the current session from a past message. Creates a new "
        "branch in the Keeper's timeline, preserving the original."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_message_id": {"type": "string"},
            "label": {"type": "string", "description": "Optional name for the fork."},
        },
        "required": ["from_message_id"],
    },
}
