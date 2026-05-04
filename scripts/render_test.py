"""
scripts/render_test.py - Day 12 CLI verification for the FAL image pipeline.

Generates a single image through Creator.render_image() without needing the
full Hermes runtime. Useful for smoke testing, screenshots, and debugging.

Usage:
    setx FAL_KEY "your-key"  # restart shell after, then:
    python scripts/render_test.py "your prompt here"
    python scripts/render_test.py "cyberpunk ramen shop" --aspect 16:9
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes_studio.archetypes.creator import Creator
from hermes_studio.archetypes.guardian import Guardian
from hermes_studio.archetypes.visualizer import Visualizer
from hermes_studio.archetypes.balancer import Balancer


def main() -> int:
    parser = argparse.ArgumentParser(description="hermes-studio FAL render test")
    parser.add_argument("prompt", help="The image prompt to render")
    parser.add_argument("--aspect", default="1:1",
                        choices=["1:1", "16:9", "9:16", "4:3", "3:4"])
    parser.add_argument("--style", default=None, help="Optional style hint")
    parser.add_argument("--session-id", default="render_test_session")
    parser.add_argument("--profile-id", default="default")
    args = parser.parse_args()

    if not os.environ.get("FAL_KEY"):
        print("ERROR: FAL_KEY environment variable not set.")
        print("Set it with:")
        print('    $env:FAL_KEY = "your-key"   (PowerShell, current session)')
        print('    setx FAL_KEY "your-key"     (Windows, persistent)')
        return 1

    guardian = Guardian()
    visualizer = Visualizer()
    balancer = Balancer()
    creator = Creator(guardian=guardian, visualizer=visualizer, balancer=balancer)

    print(f"\n-> Rendering: {args.prompt!r}")
    print(f"   Aspect: {args.aspect}  Style: {args.style or '(none)'}")
    print(f"   Calling FAL Flux...\n")

    result_str = creator.render_image(
        args={"prompt": args.prompt, "aspect_ratio": args.aspect, "style": args.style},
        session_id=args.session_id,
        profile_id=args.profile_id,
    )
    result = json.loads(result_str)

    if not result.get("ok"):
        print(f"X Render failed: {result}")
        return 2

    print(f"OK Rendered successfully")
    print(f"   Local path: {result['local_path']}")
    print(f"   URL:        {result['url']}")
    print(f"\n   Canvas events captured: {len(visualizer._replay)}")
    if visualizer._replay:
        evt = visualizer._replay[-1]
        print(f"   Last event kind: {evt.kind}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
