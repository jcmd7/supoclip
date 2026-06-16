# Mission Control — federated tool hub

A lightweight command-center that sits on top of independent, self-hosted tools.
Each tool stays its own upstream project (own repo, own compose stack, own auth);
the hub gives you one pane of glass: live status, quick launch, and a news feed.

```
                       ┌─────────────────────────────┐
   Browser ──────────▶ │  Hub Gateway  :8090         │
                       │  (FastAPI + static dashboard)│
                       │   /api/status  /api/news     │
                       └──────┬───────┬───────┬──────┘
                       health │       │       │ checks
                              ▼       ▼       ▼
                  ┌──────────┐ ┌──────────┐ ┌──────────┐
                  │ SupoClip │ │ Flowsint │ │ MiroFish │
                  │  :3000   │ │  :5173   │ │  :3100*  │
                  │  :8000   │ │          │ │  :5001   │
                  └──────────┘ └──────────┘ └──────────┘
                   AI video     OSINT graph   swarm-agent
                   clipping     investigations prediction
```

\* MiroFish ships on port 3000; `setup.sh` remaps it to 3100 to avoid
colliding with SupoClip's frontend.

## Modules

| Module | What it does | Upstream | How it runs |
|--------|--------------|----------|-------------|
| **SupoClip** | AI video clipping — long-form video → viral 9:16 clips | this repo | repo root `docker-compose up -d` |
| **Flowsint** | Graph-based OSINT investigations (domains, IPs, ASNs, enrichers) | [reconurge/flowsint](https://github.com/reconurge/flowsint) | `make setup` → vendored |
| **MiroFish** | Swarm-intelligence simulation — agents react to seed news/data, produce prediction reports | [666ghj/MiroFish](https://github.com/666ghj/MiroFish) | `make setup` → vendored |
| **changedetection.io** | Watch any page/price/API for changes, fire notifications | [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | hub compose (always on) |
| **RSSHub** | Generates RSS for sources without feeds (X, subreddits, YouTube channels…) | [DIYgod/RSSHub](https://github.com/DIYgod/RSSHub) | hub compose (always on) |
| **OpenBB** | Open-source Bloomberg terminal — equities/options/crypto/macro | [OpenBB-finance/OpenBB](https://github.com/OpenBB-finance/OpenBB) | `pip install openbb` then `openbb-api --port 6900` |
| **Local LLM** | Ollama + Open WebUI — free local tokens for MiroFish/clip selection | [open-webui/open-webui](https://github.com/open-webui/open-webui) | `make llm` (opt-in profile, heavy images) |
| **ntfy** | Self-hosted push notifications — the watcher's delivery channel | [binwiederhier/ntfy](https://github.com/binwiederhier/ntfy) | hub compose (always on) |
| **Uptime Kuma** | Status monitoring with history, SLAs, notifications | [louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) | hub compose (always on) |
| **Firecrawl** | Any URL → clean LLM-ready markdown (feeder for sims/briefs) | [mendableai/firecrawl](https://github.com/mendableai/firecrawl) | `make setup` → vendored, run its compose |
| **Perplexica** | Private AI answer engine (Perplexity-style, cites sources) | [ItzCrazyKns/Perplexica](https://github.com/ItzCrazyKns/Perplexica) | `make setup` → vendored, run its compose (remapped to :3210) |
| **Karakeep** | AI-tagged bookmarks — the hub's memory | [karakeep-app/karakeep](https://github.com/karakeep-app/karakeep) | their compose ([docs](https://docs.karakeep.app/Installation/docker)); set port to 3300 |
| **Outline** | Knowledge base for accumulating reports/briefs | [outline/outline](https://github.com/outline/outline) | advanced — needs Postgres + auth provider ([docs](https://docs.getoutline.com/s/hosting)); set port to 3380 |
| **ComfyUI** | Local open-weights video generation (Wan/LTX) for `/clip` b-roll & intros | [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) | `make gpu` (NVIDIA GPU profile); add weights to `hub/comfyui/models/` |

After starting RSSHub, any of its [routes](https://docs.rsshub.app) can be added
to `modules.json` `feeds` using the `{host}` placeholder, e.g.
`http://{host}:1200/github/trending/daily/en-US` (one ships as an example).

## Quick start

```bash
cd hub
make setup        # clone Flowsint + MiroFish into hub/vendor/ (gitignored)
# configure each module's .env — setup.sh prints exactly what each needs
make up           # start all module stacks + the gateway
open http://localhost:8090
```

`make gateway` starts only the dashboard/gateway if you prefer to manage the
module stacks yourself. `make status` prints the health JSON. `make down`
stops everything.

## Adding a module

Everything is driven by `modules.json` — no code changes needed:

```json
{
  "id": "mytool",
  "name": "My Tool",
  "tagline": "what it does",
  "description": "...",
  "url": "http://localhost:7000",
  "tags": ["data"],
  "services": [
    { "name": "frontend", "health_url": "http://{host}:7000" }
  ]
}
```

- `url` is what the OPEN button launches in your browser.
- `health_url` is what the gateway pings; `{host}` resolves to
  `host.docker.internal` inside the gateway container (override with the
  `HEALTH_HOST` env var). Any HTTP response below 500 — including 401/404 —
  counts as "up".

News sources live in the same file under `feeds` (RSS or Atom URLs).

## Known port layout / conflicts

| Port | Service |
|------|---------|
| 8090 | Hub gateway + dashboard |
| 3000 | SupoClip frontend |
| 8000 | SupoClip API |
| 6379 | SupoClip Redis (host-published) |
| 5173 | Flowsint frontend |
| 3100 | MiroFish frontend (remapped from 3000) |
| 5001 | MiroFish API |
| 5000 | changedetection.io |
| 1200 | RSSHub |
| 6900 | OpenBB Platform API |
| 3200 | Open WebUI (`llm` profile) |
| 11434 | Ollama API (`llm` profile) |
| 8091 | ntfy push server |
| 3001 | Uptime Kuma |
| 3002 | Firecrawl API |
| 3210 | Perplexica (remapped from 3000) |
| 4000 | SearXNG (via Perplexica) |
| 3300 | Karakeep (remap from 3000 in their compose) |
| 3380 | Outline (remap from 3000 in their compose) |
| 8188 | ComfyUI (`gpu` profile) |

## Local video generation (ComfyUI)

`make gpu` starts ComfyUI on `:8188` (NVIDIA GPU required). After first start,
download open-weights models into `hub/comfyui/models/` — for text/image→video,
[Wan 2.2](https://github.com/Wan-Video) or [LTX-Video](https://github.com/Lightricks/LTX-Video)
(lighter, near-realtime). Build a workflow in the UI, export it with
**Save → API Format**, and the `/clip` skill's `comfy_gen.py` can drive it to
generate B-roll/intros with no per-render cost. `hub/comfyui/` is gitignored
(models are large).

> ComfyUI is the open path for "local model + interface". Seedance and similar
> closed models are API-only (no downloadable weights), so they can't run here.

## Storyboard Conceptor

A guided idea → film pipeline at `/storyboard.html` (linked from the brief bar):

```
idea --LLM--> world bible --LLM--> beats --LLM--> script --LLM--> shot list
per shot: SHOT TYPE → VISIBLE CONTEXT → style → (negative)  --T2I--> still
          --I2V--> clip   + 360° panorama (Seedance-2 ground truth) + 3×3 sheet
```

Every stage is editable; projects persist under `~/.mission-control/storyboards`
(or `STORYBOARD_DIR`). Export a project (json + assets) as a ZIP.

- **LLM stages** use any OpenAI-compatible endpoint —
  `STORYBOARD_LLM_BASE_URL` / `STORYBOARD_LLM_KEY` / `STORYBOARD_LLM_MODEL`
  (point at Ollama via the `llm` profile for free local generation).
- **Image/video generation** is provider-pluggable (`sb_providers.py`),
  defaulting to local **ComfyUI** (`make gpu`). Drop ComfyUI API-format
  workflows into `gateway/sb_workflows/{image,video,panorama,sheet}.json` with
  `__PROMPT__ __NEGATIVE__ __WIDTH__ __HEIGHT__ __IMAGE__` placeholders.
  Cloud T2I/I2V (incl. Seedance via BytePlus/fal) are documented hooks.

Run the gateway test suite (`cd hub/gateway && pip install pytest && pytest`) —
it covers the storyboard pipeline, watcher rules, history deltas, and market
parsing with the LLM/providers mocked (no network/GPU needed).

## Watcher → phone alerts

The gateway runs a watcher loop that turns hub data into alerts: market moves
≥ `MARKET_MOVE_THRESHOLD` points in 24h (history-backed) and HN stories over
`HN_POINTS_THRESHOLD` points. Every alert lands in the dashboard's ALERTS panel
(`/api/events`); to also get phone pushes:

1. Pick a topic name and put `NTFY_TOPIC=my-secret-topic` in `hub/.env`
2. `make gateway` (ntfy ships in the hub compose on :8091)
3. Install the ntfy app on your phone, add your server
   (`http://<your-host>:8091`) and subscribe to the topic

Optional tuning in `hub/.env`: `MARKET_MOVE_THRESHOLD` (default 8),
`HN_POINTS_THRESHOLD` (default 600), `WATCH_KEYWORDS=fed,bitcoin,ai` to only
alert on matching text. Boot backlog is logged but never pushed.

Flowsint runs its own Postgres/Neo4j/Redis bound to localhost — if its Redis
publishes 6379 it will collide with SupoClip's; remap one of them.

## Roadmap ideas

- **Unified search** across modules (SupoClip tasks + Flowsint entities + MiroFish reports)
- **Cross-module flows**: news item → MiroFish simulation → SupoClip clip of the report; Flowsint entity → MiroFish scenario seed
- **Single sign-on** in front of all modules (e.g. Authelia/Authentik + reverse proxy)
- **Activity timeline**: poll each module's API for recent jobs/investigations/simulations into one feed
