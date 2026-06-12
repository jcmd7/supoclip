#!/usr/bin/env python3
"""Register a finished clip into the shared library the hub dashboard reads.

Copies the clip into CLIPS_DIR (default ~/.mission-control/clips, shared with
the gateway), generates a poster thumbnail, and upserts an entry in
library.json. Call this from the clip skill's deliver step so produced clips
show up in Mission Control's CLIP LIBRARY panel.

Usage:
    python3 library.py register clip.mp4 --title "Hook" --range "2:04-2:32" \
        [--source-title "Podcast #42"] [--scores hook=22,engagement=20,...] \
        [--virality 85] [--template hormozi] [--published-url https://...]
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

CLIPS_DIR = Path(os.path.expanduser(os.getenv("CLIPS_DIR", "~/.mission-control/clips")))


def load_manifest() -> list:
    path = CLIPS_DIR / "library.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save_manifest(items: list) -> None:
    (CLIPS_DIR / "library.json").write_text(json.dumps(items, indent=2))


def make_poster(clip: Path, poster: Path) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", "0.5", "-i", str(clip), "-frames:v", "1",
         "-vf", "scale=216:-2", str(poster)],
        capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["register"])
    parser.add_argument("clip")
    parser.add_argument("--title", required=True)
    parser.add_argument("--range", help="timestamp range in the source, e.g. 2:04-2:32")
    parser.add_argument("--source-title")
    parser.add_argument("--scores", help="comma k=v list, e.g. hook=22,value=19")
    parser.add_argument("--virality", type=int)
    parser.add_argument("--template")
    parser.add_argument("--published-url")
    args = parser.parse_args()

    src = Path(args.clip)
    if not src.exists():
        print(f"clip not found: {src}", file=sys.stderr)
        return 1

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    clip_id = uuid.uuid4().hex[:12]
    dest = CLIPS_DIR / f"{clip_id}.mp4"
    dest.write_bytes(src.read_bytes())

    poster_name = None
    if make_poster(dest, CLIPS_DIR / f"{clip_id}.jpg"):
        poster_name = f"{clip_id}.jpg"

    scores = {}
    if args.scores:
        for pair in args.scores.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                try:
                    scores[k.strip()] = int(v)
                except ValueError:
                    pass

    entry = {
        "id": clip_id,
        "title": args.title,
        "file": f"{clip_id}.mp4",
        "poster": poster_name,
        "range": args.range,
        "source_title": args.source_title,
        "scores": scores,
        "virality": args.virality,
        "template": args.template,
        "published": bool(args.published_url),
        "published_url": args.published_url,
        "created_at": time.time(),
    }

    items = load_manifest()
    items.append(entry)
    save_manifest(items)

    print(json.dumps({"registered": clip_id, "library": str(CLIPS_DIR), "total": len(items)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
