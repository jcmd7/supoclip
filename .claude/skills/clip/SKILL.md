---
name: clip
description: AI video clipper — turn a YouTube / Twitch / Kick (or ~1800 other sites) video link into short vertical captioned clips. Use when the user gives a video URL or local file and wants highlights, shorts, viral moments, or specific moments cut out ("clip every time X happens", "find the funniest 3 parts", "make shorts from this VOD"). The agent reads the transcript and chooses moments against the user's brief, then cuts captioned 9:16 clips.
---

# Clip — AI video clipper

Turn any long video into short, captioned, vertical clips. Unlike a fixed
pipeline, **you (the agent) select the moments** by reading the transcript
against whatever the user asked for. That is the whole point — the user's brief
drives selection, not a hardcoded prompt.

## Pipeline

```
URL/file → download.py → transcribe.py → [you read transcript + pick moments] → cut_clip.py (per clip)
```

All scripts live in `scripts/` next to this file and print JSON to stdout.
Work inside a `.clips/<video-id>/` working dir (download.py creates it).

### 0. Setup (first run only)

Ensure tools exist; install if missing:
```bash
yt-dlp --version || pip install -q yt-dlp
ffmpeg -version || (apt-get update && apt-get install -y ffmpeg)
python3 -c "import faster_whisper" || pip install -q faster-whisper
```

### 1. Download

```bash
python3 scripts/download.py "<URL>" --outdir .clips
```
Returns `{"file","id","title","duration","uploader"}`. Works for YouTube,
Twitch VODs/clips, Kick, Vimeo, X, TikTok, direct mp4, etc. For a local file,
skip this step and use the path directly.

- **Age-gated / subscriber-only / private:** ask the user to export a
  `cookies.txt` (browser extension) and pass `--cookies cookies.txt`.
- **Very long streams (multi-hour Twitch/Kick VODs):** confirm with the user
  before downloading — it can be several GB. Offer to clip a time range only
  (yt-dlp supports `--download-sections "*HH:MM-HH:MM"` — add it to the command
  if the user names a range).

### 2. Transcribe

```bash
python3 scripts/transcribe.py .clips/<id>/source.mp4 --model small
```
Writes `transcript.json` (word-level) and `transcript.txt` (timestamped
sentences). Defaults to local faster-whisper (free). For speed/accuracy on long
files, use `--engine assemblyai` if `ASSEMBLY_AI_API_KEY` is set. Model sizes:
`tiny`/`base`/`small`/`medium`/`large-v3` — bigger = slower but more accurate.

### 3. Select moments (YOUR job)

Read `transcript.txt`. Based on the user's brief, choose time windows. Default
heuristics when the user is vague ("make some clips"):
- 3–6 clips, each 15–60s, each a self-contained moment with a hook in the first
  3 seconds.
- Prefer complete thoughts — start at a sentence boundary, end on a payoff.
- Favor: strong opinions, surprising claims, emotional spikes, jokes, "how to"
  payoffs, numbers/stats, conflict.

When the brief is specific ("every time they mention $SOL", "rage moments",
"the part about cold plunges"), grep the transcript and select only matches.

For each chosen clip decide: `start`, `end`, a short uppercase `title` hook
(optional), and `crop-x` (0=left, 0.5=center, 1=right) if the speaker isn't
centered. Present the proposed list to the user before cutting if there's any
ambiguity; otherwise proceed and show results.

### 4. Cut clips

One call per clip:
```bash
python3 scripts/cut_clip.py .clips/<id>/source.mp4 \
  --start 124.0 --end 152.5 --out .clips/<id>/clips/clip1.mp4 \
  --transcript .clips/<id>/transcript.json \
  --title "THIS CHANGED EVERYTHING" --aspect 9:16
```
Options: `--aspect original` for 16:9, `--no-captions` to skip burn-in,
`--crop-x` to reframe. Run multiple cuts in parallel (independent ffmpeg jobs).

### 5. Deliver

Use SendUserFile to send the finished clips (status `proactive` if the user
stepped away). Summarize each: timestamp range, the hook, why you picked it.

## Notes / gotchas

- **Network-restricted sandboxes** (e.g. Claude Code web) block YouTube and the
  Whisper model CDN — download/transcribe will fail with 403. This skill is
  meant to run where the box can reach the internet (local terminal via
  `claude --teleport`, or a self-hosted runner). Tell the user if you hit this.
- **Captions look wrong / off-sync:** the transcript word timings drive them; a
  larger Whisper model fixes most drift.
- **No face-tracking yet:** crop is a fixed `--crop-x`. For talking-head videos
  centered framing is usually fine; for two-person podcasts pick per-clip.
- Keep `.clips/` out of git (add to `.gitignore`).
