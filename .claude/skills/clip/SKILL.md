---
name: clip
description: AI video clipper — turn a YouTube / Twitch / Kick (or ~1800 other sites) video link into short vertical captioned clips. Use when the user gives a video URL or local file and wants highlights, shorts, viral moments, or specific moments cut out ("clip every time X happens", "find the funniest 3 parts", "make shorts from this VOD"). The agent reads the transcript and chooses moments against the user's brief, then cuts captioned 9:16 clips with face-centered cropping, caption templates, virality scoring, b-roll, and platform presets.
---

# Clip — AI video clipper

Turn any long video into short, captioned, vertical clips. Unlike a fixed
pipeline, **you (the agent) select the moments** by reading the transcript
against whatever the user asked for. The user's brief drives selection, not a
hardcoded prompt.

## Pipeline

```
URL/file → download.py → transcribe.py → [you read transcript + pick + score] → cut_clip.py (per clip)
```

All scripts live in `scripts/` next to this file and print JSON to stdout
(errors to stderr). Work inside `.clips/<video-id>/` (download.py creates it).

### 0. Setup (first run only)

```bash
yt-dlp --version || pip install -q yt-dlp
ffmpeg -version || (apt-get update && apt-get install -y ffmpeg)
python3 -c "import faster_whisper" || pip install -q faster-whisper
# optional, for --crop-x auto (face-centered cropping):
python3 -c "import cv2" || pip install -q opencv-python-headless
```

### 1. Download

```bash
python3 scripts/download.py "<URL>" --outdir .clips
```
Returns `{"file","id","title","duration","uploader"}`. Works for YouTube,
Twitch VODs/clips, Kick, Vimeo, X, TikTok, direct mp4, etc. For a local file,
skip this step.

- **Age-gated / subscriber-only / private:** ask the user for a `cookies.txt`
  export and pass `--cookies cookies.txt`.
- **Very long streams (multi-hour VODs):** confirm before downloading (can be
  several GB). To clip a named time range only, add
  `--download-sections "*HH:MM-HH:MM"` to the yt-dlp command inside.

### 2. Transcribe

```bash
python3 scripts/transcribe.py .clips/<id>/source.mp4 --model small
```
Writes `transcript.json` (word-level) and `transcript.txt` (timestamped
sentences). Engines:
- `faster-whisper` (default) — local, free
- `whisperx` — sharper word alignment; add `--diarize` for speaker labels
  (`SPEAKER_00` etc. in transcript + words) — ideal for podcasts ("clip only
  the guest"). Needs `pip install whisperx`, and `HF_TOKEN` for diarization.
- `assemblyai` — cloud, needs `ASSEMBLY_AI_API_KEY`

Models: `tiny`→`large-v3` (bigger = better).

### 3. Select & score moments (YOUR job)

Read `transcript.txt`. Based on the user's brief, choose time windows. When the
brief is specific ("every time they mention $SOL", "rage moments"), grep the
transcript and select only matches. When vague: 3–6 clips, 15–60s each, each a
self-contained moment with a hook in the first 3 seconds; prefer complete
thoughts — start at a sentence boundary, end on a payoff.

**Score every candidate** on SupoClip's virality rubric (0–25 each, sum 0–100):
- `hook` — do the first 3s stop the scroll? (question, bold claim, conflict)
- `engagement` — emotion, stakes, pacing through the middle
- `value` — does the viewer learn/feel something complete?
- `shareability` — would someone send this to a friend / quote it?

Rank by total. Present the scored list (timestamps, title hook, scores, one-line
reason) to the user before cutting if there's any ambiguity; otherwise cut the
top picks and include the score table with the results.

For each clip decide: `start`, `end`, uppercase `title` hook (optional),
caption `template`, and crop strategy.

### 4. Cut clips

```bash
python3 scripts/cut_clip.py .clips/<id>/source.mp4 \
  --start 124.0 --end 152.5 --out .clips/<id>/clips/clip1.mp4 \
  --transcript .clips/<id>/transcript.json \
  --title "THIS CHANGED EVERYTHING" \
  --template hormozi --preset tiktok --crop-x auto \
  --fontsdir apps/supoclip/backend/fonts
```

| Option | Values | Notes |
|---|---|---|
| `--template` | `default` (white+gold), `hormozi` (green highlight, boxed), `mrbeast` (yellow+red, pop-in), `minimal` (small, boxed), `tiktok` (pink highlight) | karaoke word-sync in all |
| `--preset` | `tiktok` (10M), `reels` (12M), `shorts` (10M) | platform bitrates, forces 1080×1920; omit for CRF 20 |
| `--crop-x` | `auto` or `0`–`1` | `auto` = face-centered (MediaPipe → Haar fallback); number = manual focus, 0.5 center |
| `--broll` | `file.mp4:START:END` (repeatable, clip-relative seconds) | overlays b-roll video, keeps main audio, captions stay on top |
| `--fontsdir` | dir of .ttf files | in this repo use `apps/supoclip/backend/fonts` (Anton, Archivo Black, Bangers, Inter, Montserrat); omit → system font fallback |
| `--tighten` | max silence gap in seconds (e.g. `0.6`) | jump-cuts longer pauses, captions auto-retimed; not combinable with `--broll` (b-roll on a second pass) |
| `--aspect` | `9:16` (default) / `original` | |
| `--no-captions` | | |

Run independent cuts in parallel. Cut without `--broll` first; add b-roll on
request or when a clip has a visual dead spot (b-roll windows should not cover
the hook — keep the first ~3s clean).

**B-roll sourcing** (needs `PEXELS_API_KEY`, free):
```bash
python3 scripts/broll.py "ocean waves" --out .clips/<id>/broll/ocean.mp4
```
Returns the file plus `credit`/`source` — mention the Pexels credit in your
summary.

### 4b. Stitch (optional)

To combine several cut clips into one video (compilation, multi-moment short):

```bash
python3 scripts/stitch.py clips/c1.mp4 clips/c2.mp4 clips/c3.mp4 \
  --out clips/final.mp4 --transition crossfade --fade 0.4
```
Transitions: `cut` (default), `crossfade`, or `stinger --stinger FILE` (this
repo bundles `apps/supoclip/backend/transitions/circle_transition.mp4` and
`flat_transition_1.mp4`). Inputs are auto-normalized to the first clip's
resolution / 30fps / 48kHz, so mixed sources work.

### 5. Review

Use SendUserFile to send finished clips (status `proactive` if the user stepped
away). Summarize each: timestamp range, hook, virality scores, why you picked
it, template used.

Also register each clip into the hub's shared library so it appears in Mission
Control's CLIP LIBRARY panel:
```bash
python3 scripts/library.py register clips/clip1.mp4 \
  --title "THIS CHANGED EVERYTHING" --range "2:04-2:32" \
  --source-title "Podcast #42" --virality 85 \
  --scores hook=22,engagement=21,value=20,shareability=22 --template hormozi
```
After publishing (step 6), re-register with `--published-url` so the panel shows
it as published. Library lives at `~/.mission-control/clips` (override
`CLIPS_DIR`; the gateway reads the same path).

### 6. Approve → publish (NEVER skip approval)

Publishing is opt-in and gated on explicit approval **every time**:

1. After the user has seen the clips, use AskUserQuestion (multiSelect) listing
   each clip so they pick exactly which to publish, plus target and privacy.
   Past approval never carries over to new clips.
2. Publish only the approved ones:

```bash
python3 scripts/publish.py clips/clip1.mp4 --target youtube \
  --title "THIS CHANGED EVERYTHING" --tags shorts,clips --privacy unlisted
python3 scripts/publish.py clips/clip1.mp4 --target webhook --url https://...
```

- `youtube`: official Data API. One-time setup: OAuth Desktop-app client from
  console.cloud.google.com with YouTube Data API v3 enabled → save as
  `~/.config/clip-skill/client_secrets.json` (or set `YT_CLIENT_SECRETS`).
  First publish opens a browser consent; token is cached after. Default
  privacy is `unlisted` — use `public` only if the user said so.
- `webhook`: multipart POST (file + title/description/tags fields) to any URL
  (`--url` or `WEBHOOK_URL`). The path for TikTok/IG via n8n.
- `--dry-run` prints what would be uploaded without sending.

## Notes / gotchas

- **Network-restricted sandboxes** (e.g. Claude Code web) block YouTube, the
  Whisper model CDN, and Pexels — those steps 403 there. Run where the box has
  internet (local terminal via `claude --teleport`, or a self-hosted runner).
- **Captions off-sync:** word timings drive them; a larger Whisper model fixes
  most drift.
- **Face crop quality:** `auto` averages detections across 7 sampled frames; if
  it picks the wrong subject (two-person podcast), set `--crop-x` manually per
  clip (~0.25 left speaker, ~0.75 right).
- Keep `.clips/` out of git.
