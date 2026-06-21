# Desktop Setup — Mission Control

Run the whole hub on one machine (your desktop). Three tiers so you only run
what you want. The download is one-time per machine; after that it's one command.

## 0. Prerequisites (install once)

| Need | For | Notes |
|------|-----|-------|
| **Docker Desktop** | every module | the only hard requirement for the core |
| **Git** | cloning source modules | |
| **Python 3.11+ & ffmpeg** | the `/clip` skill | `brew install ffmpeg` / `apt install ffmpeg` |
| **NVIDIA GPU + drivers + NVIDIA Container Toolkit** | ComfyUI, FaceFusion, local LLM at speed | only if you want local generation |

Disk: ~10 GB for the lite/full images, **+15–40 GB** if you add GPU model
weights (Wan, FaceFusion, an LLM). RAM: 16 GB fine for lite/full; 32 GB+ comfy
for GPU work.

## 1. Get the code

```bash
git clone -b claude/gracious-franklin-05758s https://github.com/jcmd7/supoclip.git
cd supoclip
```

## 2. One-time install

```bash
make install     # creates .env, clones source modules, pulls all images
```

Then edit `.env` — **everything is optional for the core**; add keys only for
features you turn on (see the file's comments). Free/near-free keys worth
grabbing: AssemblyAI, a Gemini key, Pexels.

## 3. Start — pick your tier

```bash
make lite     # hub + alerts + markets/HN/feeds. Zero keys. ~2 GB. Start here.
make full     # + SupoClip + Flowsint + MiroFish + Firecrawl + Perplexica (CPU)
make gpu      # + ComfyUI (needs NVIDIA GPU). Add local LLM: make -C hub llm
```

Open **http://localhost:8090**. Module cards turn green as each stack finishes
booting. Stop everything with `make down`.

## 4. The `/clip` skill (separate from the hub)

Runs through Claude Code, not Docker. From the repo:

```bash
pip install -r hub/gateway/requirements.txt
# core clip deps:
pip install yt-dlp faster-whisper
```

Then in a Claude Code session: `/clip <url> "3 best moments"`. Add‑ons
(`PEXELS_API_KEY`, `HF_TOKEN`, ComfyUI/FaceFusion running) unlock B‑roll,
diarization, generation, and face‑swap.

## 5. What runs where (one desktop)

All of it can run on one machine. The split only matters if you later move the
always‑on pieces to a cheap VPS so alerts run 24/7 while your desktop sleeps:

- **Always‑on (light):** hub gateway, changedetection, RSSHub, ntfy, Uptime Kuma
- **On‑demand (heavy/GPU):** SupoClip render, ComfyUI, FaceFusion, local LLM,
  MiroFish sims

## Tier cheat‑sheet

| Tier | Command | Needs | Approx. disk |
|------|---------|-------|--------------|
| Core | `make lite` | Docker only | ~2 GB |
| Full (CPU) | `make full` | Docker | ~8–10 GB |
| GPU | `make gpu` + weights | NVIDIA GPU | +15–40 GB |
