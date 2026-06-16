#!/usr/bin/env python3
"""Cut a single clip from a source video using ffmpeg.

Features:
  - 9:16 vertical (or original) framing with manual or automatic face-centered crop
  - Word-synced karaoke captions in selectable templates (default, hormozi,
    mrbeast, minimal, tiktok)
  - Platform export presets (tiktok / reels / shorts) with matching bitrates
  - B-roll overlays for chosen time windows (original audio kept)
  - Optional static hook title for the first 3 seconds

Usage:
    python3 cut_clip.py SOURCE --start 12.5 --end 38.0 --out clip1.mp4 \
        [--transcript transcript.json] [--template hormozi] [--preset tiktok] \
        [--crop-x auto|0..1] [--broll file.mp4:3.0:7.5] [--title "HOOK"] \
        [--fontsdir DIR] [--aspect 9:16|original] [--no-captions]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

CAPTION_TEMPLATES = {
    # name: font family, size (frac of height), text, highlight, outline colors,
    # outline width (frac of height), opaque box, vertical position, pop-in
    "default": {
        "font": "Anton", "size": 0.052, "color": "FFFFFF", "highlight": "FFD700",
        "outline": "000000", "outline_w": 0.004, "box": False, "pos_y": 0.75, "pop": False,
    },
    "hormozi": {
        "font": "Archivo Black", "size": 0.055, "color": "FFFFFF", "highlight": "00FF00",
        "outline": "000000", "outline_w": 0.005, "box": True, "pos_y": 0.75, "pop": False,
    },
    "mrbeast": {
        "font": "Bangers", "size": 0.068, "color": "FFFF00", "highlight": "FF0000",
        "outline": "000000", "outline_w": 0.006, "box": False, "pos_y": 0.70, "pop": True,
    },
    "minimal": {
        "font": "Inter", "size": 0.042, "color": "FFFFFF", "highlight": "CCCCCC",
        "outline": None, "outline_w": 0.0, "box": True, "pos_y": 0.80, "pop": False,
    },
    "tiktok": {
        "font": "Montserrat", "size": 0.052, "color": "FFFFFF", "highlight": "FE2C55",
        "outline": "000000", "outline_w": 0.004, "box": False, "pos_y": 0.75, "pop": False,
    },
}

# Matches SupoClip's EXPORT_PRESETS: (video_bitrate, audio_bitrate)
EXPORT_PRESETS = {
    "tiktok": ("10M", "192k"),
    "reels": ("12M", "192k"),
    "shorts": ("10M", "192k"),
}


def ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H{alpha:02X}{b}{g}{r}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def build_ass(words, start, end, play_w, play_h, template, title=None, group_size=4):
    """Emit an ASS subtitle file for the [start, end) window, time-rebased to 0."""
    t = CAPTION_TEMPLATES[template]
    fontsize = int(play_h * t["size"])
    outline_w = max(2, int(play_h * t["outline_w"])) if t["outline"] else 0
    margin_v = int(play_h * (1 - t["pos_y"]))
    primary = ass_color(t["color"])
    secondary = ass_color(t["highlight"])
    if t["box"]:
        border_style, outline_col, back_col = 3, "&H66000000", "&H66000000"
        outline_w = max(outline_w, int(play_h * 0.008))
    else:
        border_style = 1
        outline_col = ass_color(t["outline"] or "000000")
        back_col = "&H64000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Cap,{t['font']},{fontsize},{primary},{secondary},{outline_col},{back_col},1,{border_style},{outline_w},0,2,40,40,{margin_v}
Style: Title,{t['font']},{int(play_h*0.06)},&H0000F0FF,&H0000F0FF,&H00000000,&H96000000,1,1,{max(2,int(play_h*0.005))},0,8,40,40,{int(play_h*0.06)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if title:
        lines.append(
            f"Dialogue: 1,{ass_time(0)},{ass_time(min(3.0, end-start))},Title,,0,0,0,,{ass_escape(title)}"
        )

    pop_tag = r"{\fscx80\fscy80\t(0,120,\fscx100\fscy100)}" if t["pop"] else ""
    window = [w for w in words if w["e"] > start and w["s"] < end]
    for i in range(0, len(window), group_size):
        group = window[i:i + group_size]
        g_start = max(group[0]["s"] - start, 0)
        g_end = min(group[-1]["e"] - start, end - start)
        parts = []
        for w in group:
            dur_cs = max(int((w["e"] - w["s"]) * 100), 1)
            parts.append(f"{{\\kf{dur_cs}}}{ass_escape(w['w'])} ")
        lines.append(
            f"Dialogue: 0,{ass_time(g_start)},{ass_time(g_end)},Cap,,0,0,0,,{pop_tag}{''.join(parts).strip()}"
        )

    return header + "\n".join(lines) + "\n"


def detect_crop_x(source: str, start: float, end: float, target_w: int, target_h: int) -> float:
    """Face-centered crop focus (0..1) via MediaPipe, falling back to Haar cascade.

    Samples frames across the window and weights face centers by area,
    mirroring SupoClip's video_utils approach. Returns 0.5 (center) when no
    faces are found or OpenCV is unavailable.
    """
    try:
        import cv2
    except ImportError:
        print("opencv not installed; using center crop (pip install opencv-python-headless)",
              file=sys.stderr)
        return 0.5

    detector = None
    try:
        import mediapipe as mp
        detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        )
    except Exception:
        pass
    haar = None
    if detector is None:
        haar = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return 0.5
    centers = []  # (cx_norm, weight)
    frame_w = frame_h = None
    for i in range(7):
        ts = start + (end - start) * (i + 0.5) / 7
        cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        frame_h, frame_w = frame.shape[:2]
        if detector is not None:
            result = detector.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            for det in result.detections or []:
                box = det.location_data.relative_bounding_box
                centers.append((box.xmin + box.width / 2, box.width * box.height))
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for (x, y, w, h) in haar.detectMultiScale(gray, 1.1, 5, minSize=(40, 40)):
                centers.append(((x + w / 2) / frame_w, (w * h) / (frame_w * frame_h)))
    cap.release()

    if not centers or not frame_w:
        print("no faces detected; using center crop", file=sys.stderr)
        return 0.5

    total = sum(weight for _, weight in centers)
    cx = sum(c * weight for c, weight in centers) / total

    # Convert face center to crop focus: after scaling to target height, the
    # crop window of target_w slides across scaled width sw.
    sw = frame_w * target_h / frame_h
    if sw <= target_w:
        return 0.5
    focus = (cx * sw - target_w / 2) / (sw - target_w)
    focus = min(max(focus, 0.0), 1.0)
    print(f"face-centered crop: {len(centers)} detections, focus={focus:.2f}", file=sys.stderr)
    return focus


def parse_broll(spec: str):
    path, start, end = spec.rsplit(":", 2)
    return path, float(start), float(end)


def tighten_intervals(words, start, end, max_gap, pad=0.15):
    """Keep-intervals (clip-relative) that drop silences longer than max_gap.

    Returns (intervals, remapped_words): intervals are [(s, e), ...] within
    [0, end-start]; remapped_words carry timings on the tightened timeline so
    captions stay word-synced.
    """
    window = [w for w in words if w["e"] > start and w["s"] < end]
    if not window:
        return [(0.0, end - start)], []

    rel = [{"w": w["w"], "s": max(w["s"] - start, 0.0), "e": min(w["e"] - start, end - start)}
           for w in window]
    clip_len = end - start

    intervals = []
    cur_s = max(rel[0]["s"] - pad, 0.0)
    cur_e = rel[0]["e"]
    for w in rel[1:]:
        if w["s"] - cur_e > max_gap:
            intervals.append((cur_s, min(cur_e + pad, clip_len)))
            cur_s = max(w["s"] - pad, 0.0)
        cur_e = w["e"]
    intervals.append((cur_s, min(cur_e + pad, clip_len)))

    # Remap word timings onto the tightened timeline.
    remapped, offset = [], 0.0
    it = iter(intervals)
    cur = next(it)
    for w in rel:
        while w["s"] >= cur[1]:
            offset += cur[1] - cur[0]
            cur = next(it)
        new_s = offset + (w["s"] - cur[0])
        remapped.append({"w": w["w"], "s": round(max(new_s, 0), 3),
                         "e": round(max(new_s, 0) + (w["e"] - w["s"]), 3)})
    return intervals, remapped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "original"])
    parser.add_argument("--template", default="default", choices=sorted(CAPTION_TEMPLATES))
    parser.add_argument("--preset", choices=sorted(EXPORT_PRESETS),
                        help="platform export preset (forces 9:16)")
    parser.add_argument("--title", help="static hook text shown at top for first 3s")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--crop-x", default="0.5",
                        help="horizontal focus 0..1, or 'auto' for face-centered crop")
    parser.add_argument("--broll", action="append", default=[], metavar="FILE:START:END",
                        help="overlay b-roll video during clip-relative window (repeatable)")
    parser.add_argument("--fontsdir", help="directory of .ttf fonts for captions")
    parser.add_argument("--tighten", type=float, metavar="MAX_GAP",
                        help="jump-cut silences longer than MAX_GAP seconds "
                             "(needs --transcript; not combinable with --broll)")
    args = parser.parse_args()

    if args.tighten and args.broll:
        print("--tighten cannot be combined with --broll (apply b-roll on a second pass)",
              file=sys.stderr)
        return 1
    if args.tighten and not args.transcript:
        print("--tighten needs --transcript for word timings", file=sys.stderr)
        return 1

    duration = args.end - args.start
    if duration <= 0:
        print("end must be greater than start", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.preset:
        args.aspect = "9:16"

    if args.aspect == "9:16":
        play_w, play_h = 1080, 1920
        if args.crop_x == "auto":
            focus = detect_crop_x(args.source, args.start, args.end, play_w, play_h)
        else:
            focus = min(max(float(args.crop_x), 0.0), 1.0)
        base_vf = (
            f"scale=-2:{play_h},crop={play_w}:{play_h}:(iw-{play_w})*{focus}:0,setsar=1"
        )
    else:
        play_w, play_h = 1920, 1080
        base_vf = f"scale={play_w}:-2,setsar=1"

    words = None
    if args.transcript and Path(args.transcript).exists():
        words = json.loads(Path(args.transcript).read_text())["words"]

    intervals = None
    if args.tighten:
        if not words:
            print("transcript file missing or empty", file=sys.stderr)
            return 1
        intervals, remapped = tighten_intervals(words, args.start, args.end, args.tighten)
        tight_dur = sum(e - s for s, e in intervals)
        caption_words, cap_start, cap_end = remapped, 0.0, tight_dur
    else:
        caption_words, cap_start, cap_end = words, args.start, args.end

    subs_filter = ""
    if not args.no_captions and caption_words:
        ass_text = build_ass(
            caption_words, cap_start, cap_end, play_w, play_h, args.template, args.title
        )
        ass_path = out.with_suffix(".ass")
        ass_path.write_text(ass_text)
        esc = str(ass_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        subs_filter = f"subtitles='{esc}'"
        if args.fontsdir and Path(args.fontsdir).is_dir():
            fd = str(Path(args.fontsdir)).replace("\\", "\\\\").replace(":", "\\:")
            subs_filter += f":fontsdir='{fd}'"

    cmd = ["ffmpeg", "-y", "-ss", str(args.start), "-to", str(args.end), "-i", args.source]

    brolls = [parse_broll(s) for s in args.broll]
    for path, _, _ in brolls:
        cmd += ["-stream_loop", "-1", "-i", path]

    if brolls:
        # Build overlay graph: main video -> overlay each b-roll window -> subtitles.
        graph = [f"[0:v]{base_vf}[main0]"]
        for idx, (_, b_start, b_end) in enumerate(brolls):
            b_dur = b_end - b_start
            graph.append(
                f"[{idx+1}:v]trim=duration={b_dur},setpts=PTS-STARTPTS+{b_start}/TB,"
                f"scale={play_w}:{play_h}:force_original_aspect_ratio=increase,"
                f"crop={play_w}:{play_h},setsar=1[b{idx}]"
            )
            graph.append(
                f"[main{idx}][b{idx}]overlay=enable='between(t,{b_start},{b_end})':eof_action=pass[main{idx+1}]"
            )
        last = f"main{len(brolls)}"
        if subs_filter:
            graph.append(f"[{last}]{subs_filter}[vout]")
        else:
            graph.append(f"[{last}]null[vout]")
        cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "0:a?"]
    elif intervals:
        # Jump-cut graph: trim each keep-interval, concat, then frame + captions.
        graph = []
        for i, (s, e) in enumerate(intervals):
            graph.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[tv{i}]")
            graph.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[ta{i}]")
        pairs = "".join(f"[tv{i}][ta{i}]" for i in range(len(intervals)))
        graph.append(f"{pairs}concat=n={len(intervals)}:v=1:a=1[cv][ca]")
        tail = base_vf + (f",{subs_filter}" if subs_filter else "")
        graph.append(f"[cv]{tail}[vout]")
        cmd += ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[ca]"]
    else:
        vf = base_vf + (f",{subs_filter}" if subs_filter else "")
        cmd += ["-vf", vf]

    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if args.preset:
        v_rate, a_rate = EXPORT_PRESETS[args.preset]
        double = str(int(v_rate.rstrip("M")) * 2) + "M"
        cmd += ["-b:v", v_rate, "-maxrate", double, "-bufsize", double, "-b:a", a_rate]
    else:
        cmd += ["-crf", "20", "-b:a", "128k"]
    cmd += ["-c:a", "aac", "-movflags", "+faststart", str(out)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip()[-2000:], file=sys.stderr)
        return result.returncode

    print(json.dumps({
        "out": str(out), "duration": round(duration, 2), "aspect": args.aspect,
        "template": args.template, "preset": args.preset,
        "broll": len(brolls),
        "tightened": round(tight_dur, 2) if intervals else None,
        "cuts": len(intervals) - 1 if intervals else 0,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
