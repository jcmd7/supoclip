#!/usr/bin/env python3
"""Cut a single clip from a source video using ffmpeg.

Given a start/end window it produces a vertical (9:16) or original-ratio clip,
optionally burning in word-synced captions read from transcript.json.

Captions are rendered as ffmpeg ASS subtitles (karaoke-style highlight on the
active word), positioned ~75% down the frame.

Usage:
    python3 cut_clip.py SOURCE --start 12.5 --end 38.0 --out clip1.mp4 \
        [--transcript transcript.json] [--aspect 9:16|original] \
        [--title "HOOK TEXT"] [--no-captions]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(words, start, end, play_w, play_h, title=None, group_size=4):
    """Emit an ASS subtitle file for the [start, end) window, time-rebased to 0."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Cap,Arial,{int(play_h*0.055)},&H00FFFFFF,&H00000000,&H64000000,1,{max(2,int(play_h*0.004))},0,2,40,40,{int(play_h*0.18)}
Style: Title,Arial,{int(play_h*0.07)},&H0000F0FF,&H00000000,&H96000000,1,{max(2,int(play_h*0.005))},0,8,40,40,{int(play_h*0.06)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []

    if title:
        lines.append(
            f"Dialogue: 0,{ass_time(0)},{ass_time(min(3.0, end-start))},Title,,0,0,0,,{ass_escape(title)}"
        )

    window = [w for w in words if w["e"] > start and w["s"] < end]
    for i in range(0, len(window), group_size):
        group = window[i:i + group_size]
        g_start = max(group[0]["s"] - start, 0)
        g_end = min(group[-1]["e"] - start, end - start)
        # Karaoke: each word highlighted as it's spoken.
        parts = []
        for w in group:
            dur_cs = max(int((w["e"] - w["s"]) * 100), 1)
            parts.append(f"{{\\kf{dur_cs}}}{ass_escape(w['w'])} ")
        lines.append(
            f"Dialogue: 0,{ass_time(g_start)},{ass_time(g_end)},Cap,,0,0,0,,{''.join(parts).strip()}"
        )

    return header + "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "original"])
    parser.add_argument("--title", help="static hook text shown at top for first 3s")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--crop-x", type=float, default=0.5,
                        help="horizontal focus 0..1 for 9:16 crop (0.5=center)")
    args = parser.parse_args()

    duration = args.end - args.start
    if duration <= 0:
        print("end must be greater than start", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.aspect == "9:16":
        play_w, play_h = 1080, 1920
        # Scale to fill height, crop width around the focus point.
        focus = min(max(args.crop_x, 0.0), 1.0)
        vf = (
            f"scale=-2:{play_h},"
            f"crop={play_w}:{play_h}:(iw-{play_w})*{focus}:0,"
            f"setsar=1"
        )
    else:
        play_w, play_h = 1920, 1080
        vf = f"scale={play_w}:-2,setsar=1"

    filters = [vf]

    if not args.no_captions and args.transcript and Path(args.transcript).exists():
        data = json.loads(Path(args.transcript).read_text())
        ass_text = build_ass(data["words"], args.start, args.end, play_w, play_h, args.title)
        ass_path = out.with_suffix(".ass")
        ass_path.write_text(ass_text)
        # ffmpeg subtitles filter needs escaped path
        esc = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"subtitles='{esc}'")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(args.start), "-to", str(args.end),
        "-i", args.source,
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        return result.returncode

    print(json.dumps({"out": str(out), "duration": round(duration, 2), "aspect": args.aspect}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
