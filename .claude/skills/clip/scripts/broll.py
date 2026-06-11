#!/usr/bin/env python3
"""Fetch a B-roll video from Pexels (free stock footage).

Needs PEXELS_API_KEY in the environment (free at https://www.pexels.com/api/).
Picks the best portrait-orientation match and downloads it.

Usage:
    python3 broll.py "ocean waves" --out broll/ocean.mp4 [--min-duration 5]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

SEARCH_URL = "https://api.pexels.com/videos/search"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-duration", type=int, default=4)
    args = parser.parse_args()

    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        print("PEXELS_API_KEY not set — get a free key at https://www.pexels.com/api/",
              file=sys.stderr)
        return 1

    with httpx.Client(timeout=60, headers={"Authorization": api_key}) as client:
        resp = client.get(SEARCH_URL, params={
            "query": args.query, "orientation": "portrait", "per_page": 10,
        })
        resp.raise_for_status()
        videos = [v for v in resp.json().get("videos", [])
                  if v["duration"] >= args.min_duration]
        if not videos:
            print(f"no portrait b-roll found for: {args.query}", file=sys.stderr)
            return 1

        video = videos[0]
        # Prefer the file closest to 1080 wide without massive overkill.
        files = sorted(
            (f for f in video["video_files"] if f.get("width")),
            key=lambda f: abs(f["width"] - 1080),
        )
        url = files[0]["link"]

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with client.stream("GET", url) as stream:
            stream.raise_for_status()
            with open(out, "wb") as f:
                for chunk in stream.iter_bytes(1 << 16):
                    f.write(chunk)

    print(json.dumps({
        "out": str(out),
        "query": args.query,
        "duration": video["duration"],
        "credit": video["user"]["name"],
        "source": video["url"],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
