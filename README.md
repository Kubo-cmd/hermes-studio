# hermes-studio

A creative surface for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Hermes is the most powerful open-source agent runtime. It's also text-first — you run a 4-hour creative session and all you get is terminal scrollback. `hermes-studio` is a first-class Hermes plugin that gives the agent a real visual surface: a canvas that renders what the agent makes as it makes it, a timeline of the session's full creative history, and multi-modal tools (image, 3D, video, audio) that stream output live.

Built for the [Hermes Agent Creative Hackathon](https://x.com/NousResearch/status/2045225469088326039).

---

## Status

This is a **work in progress** — shipped publicly on day 1 of the 16-day hackathon. See the [build log](https://x.com/Kubo100x) for daily progress. Expect breakage. PRs welcome.

## The archetype architecture

hermes-studio organises its functionality into eight named components. Each hooks into Hermes through the documented plugin API — none of them monkey-patch or replace core Hermes functionality.

| Archetype | What it does | Hermes integration point |
|---|---|---|
| **Architect** | Observational plan extraction | `pre_llm_call` hook |
| **Guardian** | Secret redaction (addresses leaked credentials in tool output) | `pre_llm_call` + `post_tool_call` hooks |
| **Keeper** | Per-profile, per-session append-only timeline | `on_session_start` / `on_session_end` |
| **Shadow** | Tool-call classification (slow / stuck) for visibility during long runs | `post_tool_call` hook |
| **Creator** | Multi-modal rendering: image, 3D, video, audio | tool handlers |
| **Visualizer** | Canvas event stream + FastAPI websocket | plugin API router |
| **Balancer** | Per-gateway output formatting (Telegram, Discord, CLI) | called by Creator |
| **Seeker** | Opt-in trajectory logging for training data | `post_tool_call` hook |

## What works in v0.1

- [x] Plugin manifest (`plugin.yaml`) and Hermes plugin registration
- [x] Guardian: pattern-based secret redaction, hooked into both pre-LLM context and post-tool output
- [x] Keeper: SQLite-backed timeline with per-profile schema isolation, append + list + fork APIs
- [x] Shadow: tool-call duration classification and reporting
- [x] Visualizer: in-memory canvas event stream with replay buffer, FastAPI websocket route
- [x] Creator: `studio_render_image` via FAL Flux (requires `FAL_KEY`)
- [x] Creator: `studio_render_3d` via Tripo3D (requires `TRIPO3D_API_KEY`)
- [x] FastAPI router mounted at `/api/plugins/hermes-studio/*`

## What's in progress

- [ ] Dashboard plugin (the React tab that consumes the websocket). Scheduled for v0.2
- [ ] `studio_render_video` ffmpeg composition pipeline. Scheduled for v0.3
- [ ] `studio_render_audio` real TTS backend wiring (emits canvas events now, doesn't produce audio). Scheduled for v0.2
- [ ] Music and SFX in audio tool. Scheduled for v0.2
- [ ] LLM-based decomposition in Architect. Scheduled for v0.3
- [ ] Three.js 3D viewport in the dashboard. Scheduled for v0.2

**The code is explicit about the distinction.** Handlers for not-yet-implemented features return structured error payloads with a `shipping_in` field so no one mistakes a stub for a working integration.

## Install

```bash
# Coming soon — during the hackathon, install from source:
git clone https://github.com/Kubo100x/hermes-studio.git
cd hermes-studio
pip install -e .

# Link into Hermes's plugin directory:
ln -s "$(pwd)" ~/.hermes/plugins/hermes-studio

# Enable (Hermes disables all plugins by default):
hermes plugins enable hermes-studio

# Add credentials for the backends you want:
echo "FAL_KEY=..." >> ~/.hermes/.env
echo "TRIPO3D_API_KEY=..." >> ~/.hermes/.env

# Start Hermes and the tools appear alongside built-ins:
hermes
```

## How it fits into Hermes

```
┌──────────────────────────────────────────────────────────────┐
│                        Hermes Agent                          │
│                                                              │
│   ┌─────────────────┐      ┌────────────────────┐            │
│   │   Agent loop    │─────▶│  Plugin system     │            │
│   └─────────────────┘      │  (hooks + tools)   │            │
│            │               └─────────┬──────────┘            │
│            │                         │                       │
│            ▼                         ▼                       │
│   ┌─────────────────┐      ┌────────────────────┐            │
│   │ LLM providers   │      │  hermes-studio     │            │
│   │ (Kimi, Claude,  │      │  ─── archetypes    │            │
│   │  GPT, MiMo…)    │      │                    │            │
│   └─────────────────┘      └─────────┬──────────┘            │
│                                      │                       │
└──────────────────────────────────────┼───────────────────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │  Dashboard plugin      │
                          │  (React + Three.js)    │
                          │  over /ws/canvas       │
                          └────────────────────────┘
```

hermes-studio is a normal Hermes plugin. It extends; it does not replace.

## Related Hermes issues this touches

- [#10520](https://github.com/NousResearch/hermes-agent/issues/10520) — Guardian redacts browser-automation password leaks before they stream to gateways
- [#6320](https://github.com/NousResearch/hermes-agent/issues/6320) — Keeper stores timeline data per-profile with schema-level isolation; complements but does not replace Hermes's own per-instance fix
- [#9516](https://github.com/NousResearch/hermes-agent/issues/9516) — Creator returns actionable `how_to_fix` errors instead of generic "system dependency not met" when a backend is misconfigured
- [#11431](https://github.com/NousResearch/hermes-agent/issues/11431) — Shadow makes slow subagent calls visible on the canvas so long creative runs don't silently hang

These are partial, additive fixes — the upstream root-cause fixes belong in hermes-agent itself and should be submitted as PRs there.

## License

MIT.

## Acknowledgements

Built on [hermes-agent](https://github.com/NousResearch/hermes-agent) by Nous Research. Co-sponsored by [Moonshot AI](https://www.moonshot.ai/) (Kimi K2 is the default model for the showcase run).
