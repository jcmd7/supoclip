# Mission Control

A personal command center — one pane of glass over a fleet of self-hosted,
open-source tools, plus an AI video-clipping workflow. Sense → remember → judge
→ act → review, with everything running on your own infrastructure.

```
                       ┌──────────────────────────────────┐
   Browser ──────────▶ │  Hub Gateway  :8090              │
   Phone   ◀── ntfy ── │  status · markets · HN · feeds   │
                       │  history · brief · clips · watcher│
                       └───────────────┬──────────────────┘
                                       │ health + data
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼               ▼              ▼
    SupoClip       Flowsint        MiroFish        Firecrawl      …9 more
   (clipping)     (OSINT graph)   (prediction)    (scrape→md)
```

## Layout

| Path | What it is |
|------|------------|
| `hub/` | **The product.** FastAPI gateway + dashboard, module registry, watcher, history. See [hub/README.md](hub/README.md). |
| `.claude/skills/clip/` | The `/clip` skill — AI video clipper (YouTube/Twitch/Kick → captioned 9:16 clips). See its [SKILL.md](.claude/skills/clip/SKILL.md). |
| `apps/supoclip/` | The SupoClip app — AI video clipping web service, one of the hub's modules. Fork of [SupoClip](https://github.com/sami-hindi/supoclip), AGPL-3.0. |

Other modules (Flowsint, MiroFish, Firecrawl, Perplexica, …) are cloned into
`hub/vendor/` by `make setup` and stay their own upstream projects.

## Quick start

```bash
# Zero-key tier — dashboard + always-on modules (changedetection, RSSHub, ntfy, Uptime Kuma)
make hub
open http://localhost:8090

# Add the rest (SupoClip + vendored module stacks)
make setup     # clone vendored modules; prints what each .env needs
make up
```

`make help` lists every target. The `/clip` skill's core loop
(yt-dlp → faster-whisper → ffmpeg) also needs no keys.

## What's where

- **13 modules**, live health on the dashboard — see [hub/README.md](hub/README.md) for the full table, ports, and per-module setup.
- **Markets** (Polymarket + Kalshi), **Hacker News**, and **RSS/Atom feeds**, with **24h history** and deltas.
- **Watcher → ntfy**: market moves and HN spikes pushed to your phone.
- **Morning brief**: a no-LLM daily summary from stored history.
- **Clip library**: clips produced by `/clip` surfaced in the dashboard, with virality scores and publish status.

## License

`apps/supoclip/` is AGPL-3.0 (inherited from SupoClip) — see [LICENSE](LICENSE).
The hub and clip skill are part of this repository under the same terms.
