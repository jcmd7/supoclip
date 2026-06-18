#!/usr/bin/env python3
"""Face-swap an image or video clip via a local FaceFusion install.

Wraps FaceFusion's `headless-run` so the /clip skill can swap a consented face
onto generated footage, storyboard frames, or clips. FaceFusion uses
InsightFace / InSwapper under the hood, so this also covers the "InSwapper"
use case — no separate integration needed.

RESPONSIBLE USE: only swap faces you have the right and consent to use. Do not
create misleading impersonations of real people. This wrapper is for authorized
creative/production work (your own talent, licensed actors, fictional avatars).

Requires a local FaceFusion checkout (`make setup` clones it to
hub/vendor/facefusion) and its environment installed. NVIDIA GPU recommended;
CPU works but is slow for video. CLI flags track the installed FaceFusion
version — if a run fails, check `python facefusion.py headless-run --help`.

Usage:
    python3 face_swap.py --source face.jpg --target clip.mp4 --out swapped.mp4 \
        [--facefusion-dir hub/vendor/facefusion] [--enhance] [--extra "--flag val"]
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="face image to swap IN")
    parser.add_argument("--target", required=True, help="image or video to swap ONTO")
    parser.add_argument("--out", required=True)
    parser.add_argument("--facefusion-dir", default="hub/vendor/facefusion")
    parser.add_argument("--enhance", action="store_true",
                        help="also run the face enhancer for sharper results")
    parser.add_argument("--python", default=sys.executable,
                        help="python that has FaceFusion's deps (e.g. its conda env)")
    parser.add_argument("--extra", default="", help="extra flags passed through verbatim")
    args = parser.parse_args()

    ff_dir = Path(args.facefusion_dir)
    entry = ff_dir / "facefusion.py"
    if not entry.exists():
        print(f"FaceFusion not found at {entry} — run `make setup` first, or pass "
              "--facefusion-dir.", file=sys.stderr)
        return 1
    for p in (args.source, args.target):
        if not Path(p).exists():
            print(f"input not found: {p}", file=sys.stderr)
            return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    processors = ["face_swapper"] + (["face_enhancer"] if args.enhance else [])
    cmd = [args.python, "facefusion.py", "headless-run",
           "-s", str(Path(args.source).resolve()),
           "-t", str(Path(args.target).resolve()),
           "-o", str(out.resolve()),
           "--processors", *processors]
    if args.extra:
        cmd += shlex.split(args.extra)

    result = subprocess.run(cmd, cwd=ff_dir)
    if result.returncode != 0:
        print("FaceFusion headless-run failed — verify flags against your version "
              "(`python facefusion.py headless-run --help`).", file=sys.stderr)
        return result.returncode

    print(f'{{"out": "{out}", "source": "{args.source}", "target": "{args.target}"}}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
