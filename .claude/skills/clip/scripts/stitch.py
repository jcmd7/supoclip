#!/usr/bin/env python3
"""Stitch multiple clips into one video with optional transitions.

Modes:
  cut        — straight concatenation (default)
  crossfade  — video xfade + audio acrossfade between every pair
  stinger    — insert a transition video between clips (e.g. the mp4s in
               backend/transitions/)

All inputs are normalized to the first clip's resolution, 30fps, 48kHz stereo,
so clips from cut_clip.py (already uniform) and stingers of any size both work.

Usage:
    python3 stitch.py clip1.mp4 clip2.mp4 clip3.mp4 --out final.mp4 \
        [--transition cut|crossfade|stinger] [--fade 0.4] [--stinger FILE]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=width,height,codec_type",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    return {
        "duration": float(data["format"]["duration"]),
        "w": video["width"], "h": video["height"],
        "has_audio": has_audio,
    }


def norm_filters(idx: int, w: int, h: int, has_audio: bool, duration: float):
    """Per-input normalization; returns (video_chain, audio_chain)."""
    v = (
        f"[{idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},fps=30,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{idx}]"
    )
    if has_audio:
        a = (
            f"[{idx}:a]aresample=48000,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS[a{idx}]"
        )
    else:
        a = (
            f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f},"
            f"asetpts=PTS-STARTPTS[a{idx}]"
        )
    return v, a


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("clips", nargs="+")
    parser.add_argument("--out", required=True)
    parser.add_argument("--transition", default="cut",
                        choices=["cut", "crossfade", "stinger"])
    parser.add_argument("--fade", type=float, default=0.4,
                        help="crossfade duration in seconds")
    parser.add_argument("--stinger",
                        help="transition video (e.g. backend/transitions/circle_transition.mp4)")
    args = parser.parse_args()

    if len(args.clips) < 2:
        print("need at least 2 clips to stitch", file=sys.stderr)
        return 1
    if args.transition == "stinger" and not args.stinger:
        print("--stinger FILE is required for stinger transitions", file=sys.stderr)
        return 1

    inputs = list(args.clips)
    if args.transition == "stinger":
        # Interleave: c1, stinger, c2, stinger, c3 ...
        interleaved = []
        for clip in inputs:
            interleaved += [clip, args.stinger]
        inputs = interleaved[:-1]

    infos = [probe(p) for p in inputs]
    w, h = infos[0]["w"], infos[0]["h"]

    graph = []
    for i, info in enumerate(infos):
        v, a = norm_filters(i, w, h, info["has_audio"], info["duration"])
        graph += [v, a]

    n = len(inputs)
    if args.transition == "crossfade":
        fade = args.fade
        # Chain pairwise xfade/acrossfade; offset is in the running output's time.
        cur_v, cur_a, cur_dur = "v0", "a0", infos[0]["duration"]
        for i in range(1, n):
            offset = max(cur_dur - fade, 0)
            graph.append(
                f"[{cur_v}][v{i}]xfade=transition=fade:duration={fade}:offset={offset:.3f}[xv{i}]"
            )
            graph.append(f"[{cur_a}][a{i}]acrossfade=d={fade}[xa{i}]")
            cur_v, cur_a = f"xv{i}", f"xa{i}"
            cur_dur = offset + fade + (infos[i]["duration"] - fade)
        graph.append(f"[{cur_v}]null[vout]")
        graph.append(f"[{cur_a}]anull[aout]")
    else:
        pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
        graph.append(f"{pairs}concat=n={n}:v=1:a=1[vout][aout]")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y"]
    for path in inputs:
        cmd += ["-i", path]
    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        return result.returncode

    print(json.dumps({
        "out": str(out),
        "clips": len(args.clips),
        "transition": args.transition,
        "duration": round(probe(str(out))["duration"], 2),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
