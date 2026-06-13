#!/usr/bin/env python3
"""Generate an animated title card / intro MP4 via HeyGen HyperFrames.

HyperFrames renders HTML/CSS/animation compositions into deterministic MP4s
(headless Chrome + ffmpeg, no GPU, no API keys). This wrapper scaffolds a
parametrized title-card composition, renders it, and copies the result to --out
— ideal for /clip intros, outros, and lower-thirds that stitch in via stitch.py.

Requires Node.js 22+ and ffmpeg (hyperframes runs via npx).

NOTE: the composition schema (data-* attributes) tracks the installed
HyperFrames version. If render fails, open the scaffolded project with
`npx hyperframes preview` and reconcile templates/title_card.html with the
version's docs, then re-run.

Usage:
    python3 hyperframes_gen.py --text "THIS CHANGED EVERYTHING" \
        --out .clips/<id>/assets/intro.mp4 \
        [--subtitle "ep. 42"] [--duration 3] [--bg "#0a0e14"] [--color "#35c9dd"] \
        [--width 1080] [--height 1920] [--project-dir .clips/<id>/hf] [--scaffold-only]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "templates" / "title_card.html"


def render_template(text, subtitle, duration, bg, color, width, height) -> str:
    html = TEMPLATE.read_text()
    fps = 30
    frames = int(duration * fps)
    replacements = {
        "{{TEXT}}": text,
        "{{SUBTITLE}}": subtitle or "",
        "{{DURATION}}": str(duration),
        "{{FRAMES}}": str(frames),
        "{{BG}}": bg,
        "{{COLOR}}": color,
        "{{WIDTH}}": str(width),
        "{{HEIGHT}}": str(height),
    }
    for k, v in replacements.items():
        html = html.replace(k, v)
    return html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--subtitle")
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--bg", default="#0a0e14")
    parser.add_argument("--color", default="#35c9dd")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--project-dir", default=".clips/hf")
    parser.add_argument("--scaffold-only", action="store_true",
                        help="write the composition but don't render (for preview/tweaking)")
    args = parser.parse_args()

    if not TEMPLATE.exists():
        print(f"template missing: {TEMPLATE}", file=sys.stderr)
        return 1

    project = Path(args.project_dir)
    project.mkdir(parents=True, exist_ok=True)

    # Scaffold the hyperframes project on first use (creates package.json etc.).
    if not (project / "package.json").exists():
        init = subprocess.run(
            ["npx", "--yes", "hyperframes", "init", "."],
            cwd=project, capture_output=True, text=True,
        )
        if init.returncode != 0:
            print("hyperframes init failed (is Node 22+ installed?):\n"
                  + init.stderr.strip()[-1500:], file=sys.stderr)
            return 1

    composition = render_template(args.text, args.subtitle, args.duration,
                                  args.bg, args.color, args.width, args.height)
    (project / "index.html").write_text(composition)

    if args.scaffold_only:
        print(json.dumps({"scaffolded": str(project / "index.html"),
                          "preview": f"npx hyperframes preview (in {project})"}))
        return 0

    before = {p: p.stat().st_mtime for p in project.rglob("*.mp4")}
    render = subprocess.run(["npx", "--yes", "hyperframes", "render"],
                            cwd=project, capture_output=True, text=True)
    if render.returncode != 0:
        print("hyperframes render failed:\n" + render.stderr.strip()[-1500:], file=sys.stderr)
        return render.returncode

    # Find the freshest mp4 produced by the render.
    candidates = [p for p in project.rglob("*.mp4")
                  if p not in before or p.stat().st_mtime > before[p]]
    if not candidates:
        print("render reported success but no new mp4 found in project", file=sys.stderr)
        return 1
    produced = max(candidates, key=lambda p: p.stat().st_mtime)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(produced.read_bytes())
    print(json.dumps({"out": str(out), "text": args.text,
                      "duration": args.duration, "source": str(produced)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
