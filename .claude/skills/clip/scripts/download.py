#!/usr/bin/env python3
"""Download a video for clipping via yt-dlp.

Supports YouTube, Twitch (VODs/clips), Kick, and ~1800 other sites.
Prints a JSON summary to stdout: {"file", "id", "title", "duration", "uploader"}.

Usage:
    python3 download.py <url> [--outdir DIR] [--max-height 1080] [--cookies FILE]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--outdir", default=".clips")
    parser.add_argument("--max-height", type=int, default=1080)
    parser.add_argument("--cookies", help="cookies.txt for sub-only/age-gated content")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fmt = (
        f"bv*[height<={args.max_height}][ext=mp4]+ba[ext=m4a]"
        f"/bv*[height<={args.max_height}]+ba/b[height<={args.max_height}]/b"
    )
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--no-playlist",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "-o", str(outdir / "%(id)s" / "source.%(ext)s"),
        "--print-json",
        "--no-simulate",
        args.url,
    ]
    if args.cookies:
        cmd += ["--cookies", args.cookies]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        return result.returncode

    info = json.loads(result.stdout.splitlines()[-1])
    video_dir = outdir / info["id"]
    files = sorted(video_dir.glob("source.*"))
    if not files:
        print("yt-dlp reported success but no source file found", file=sys.stderr)
        return 1

    print(json.dumps({
        "file": str(files[0]),
        "id": info.get("id"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
