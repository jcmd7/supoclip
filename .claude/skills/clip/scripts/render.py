#!/usr/bin/env python3
"""Render selected segments into 9:16 vertical clips with word-synced captions.

Usage:
    python3 render.py <video> <segments.json> <transcript.json>
        [--outdir DIR] [--crop center|left|right] [--no-captions]
        [--font NAME] [--highlight HEX] [--caption-v-pct 75]

segments.json schema (written by the agent after reading the transcript):
{
  "segments": [
    {"id": 1, "title": "short-slug-title", "start": 12.3, "end": 41.2,
     "virality_score": 84, "reason": "why this moment"}
  ]
}

Captions: words grouped 3-at-a-time, all visible, active word highlighted —
the OpusClip/SupoClip style. Positioned at --caption-v-pct down the frame.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OUT_W, OUT_H = 1080, 1920
MAX_WORDS_PER_GROUP = 3
MAX_CHARS_PER_GROUP = 18

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,6,2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text: str) -> str:
    return text.replace("\\", "").