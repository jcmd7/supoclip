# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this repo is

**Mission Control** — a personal hub over self-hosted open-source tools, plus an
AI video-clipping skill. The hub is the product; SupoClip is one module.

## Layout

| Path | What it is | Detail |
|------|------------|--------|
| `hub/` | The hub: FastAPI gateway (`hub/gateway/`), static dashboard (`hub/dashboard/`), module registry (`hub/modules.json`), compose, watcher, SQLite history | [hub/README.md](hub/README.md) |
| `.claude/skills/clip/` | The `/clip` skill — agent-driven video clipper | [SKILL.md](.claude/skills/clip/SKILL.md) |
| `apps/supoclip/` | The SupoClip web app (AGPL fork), one hub module | [apps/supoclip/CLAUDE.md](apps/supoclip/CLAUDE.md) |

Vendored modules (Flowsint, MiroFish, Firecrawl, Perplexica) are cloned into
`hub/vendor/` by `make setup` and are gitignored — treat them as upstream
projects, don't edit them in this repo.

## Working here

- **Hub gateway**: `hub/gateway/main.py` (FastAPI). Endpoints under `/api/*`;
  static dashboard mounted at `/`. Test locally with
  `uvicorn main:app --port 8090` from `hub/gateway/`. The `FIXTURES_DIR` env
  serves recorded API responses for offline dev.
- **Adding a hub module**: edit `hub/modules.json` (no code). `{host}` in a
  `health_url` resolves to `HEALTH_HOST` (the docker host).
- **Clip skill**: pure Python scripts in `.claude/skills/clip/scripts/`, driven
  by the agent per `SKILL.md`. Needs ffmpeg + yt-dlp; fonts/transitions live in
  `apps/supoclip/backend/`.
- **SupoClip app**: see `apps/supoclip/CLAUDE.md` — its paths (`backend/...`,
  `frontend/...`) are relative to `apps/supoclip/`.
- **Make targets**: `make help` at root. `make hub` (no keys), `make up`
  (everything), `make setup` (vendor clones).

## Conventions

- Keys live in gitignored `.env` files, never committed.
- The hub gateway has no build step (vanilla JS dashboard) — keep it that way.
- `hub/gateway/hub_history.db*` and `hub/vendor/` are gitignored.
