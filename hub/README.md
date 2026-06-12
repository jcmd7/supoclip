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

Flowsint runs its own Postgres/Neo4j/Redis bound to localhost — if its Redis
publishes 6379 it will collide with SupoClip's; remap one of them.

## Roadmap ideas

- **Unified search** across modules (SupoClip tasks + Flowsint entities + MiroFish reports)
- **Cross-module flows**: news item → MiroFish simulation → SupoClip clip of the report; Flowsint entity → MiroFish scenario seed
- **Single sign-on** in front of all modules (e.g. Authelia/Authentik + reverse proxy)
- **Activity timeline**: poll each module's API for recent jobs/investigations/simulations into one feed
