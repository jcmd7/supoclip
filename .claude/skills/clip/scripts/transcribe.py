#!/usr/bin/env python3
"""Transcribe a video/audio file with word-level timestamps.

Engines:
  - faster-whisper (default): local, free, downloads model on first run
  - assemblyai: cloud, needs ASSEMBLY_AI_API_KEY env var (--engine assemblyai)

Writes next to the media file:
  transcript.json  — {"words": [{"w", "s", "e"}], "segments": [{"text", "s", "e"}]}
  transcript.txt   — "[mm:ss] sentence" lines, for the agent to read

Usage:
    python3 transcribe.py <media> [--model small] [--engine faster-whisper|assemblyai]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def transcribe_whisper(path: str, model_name: str) -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(path, word_timestamps=True, vad_filter=True)

    words, sentences = [], []
    for seg in segments:
        sentences.append({"text": seg.text.strip(), "s": round(seg.start, 2), "e": round(seg.end, 2)})
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)})
    return {"words": words, "segments": sentences}


def transcribe_assemblyai(path: str) -> dict:
    import httpx

    api_key = os.environ["ASSEMBLY_AI_API_KEY"]
    headers = {"authorization": api_key}
    base = "https://api.assemblyai.com/v2"

    with httpx.Client(timeout=120) as client:
        with open(path, "rb") as f:
            upload = client.post(f"{base}/upload", headers=headers, content=f.read())
        upload.raise_for_status()
        job = client.post(
            f"{base}/transcript",
            headers=headers,
            json={"audio_url": upload.json()["upload_url"], "punctuate": True},
        )
        job.raise_for_status()
        job_id = job.json()["id"]
        while True:
            status = client.get(f"{base}/transcript/{job_id}", headers=headers).json()
            if status["status"] in ("completed", "error"):
                break
            time.sleep(5)

    if status["status"] == "error":
        raise RuntimeError(status.get("error", "transcription failed"))

    words = [
        {"w": w["text"], "s": w["start"] / 1000, "e": w["end"] / 1000}
        for w in status.get("words", [])
    ]
    # Build sentence-ish segments by splitting on terminal punctuation.
    sentences, current, start = [], [], None
    for w in words:
        if start is None:
            start = w["s"]
        current.append(w["w"])
        if w["w"].rstrip()[-1:] in ".?!":
            sentences.append({"text": " ".join(current), "s": start, "e": w["e"]})
            current, start = [], None
    if current:
        sentences.append({"text": " ".join(current), "s": start, "e": words[-1]["e"]})
    return {"words": words, "segments": sentences}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("media")
    parser.add_argument("--model", default="small", help="faster-whisper model size")
    parser.add_argument("--engine", default="faster-whisper",
                        choices=["faster-whisper", "assemblyai"])
    parser.add_argument("--force", action="store_true", help="ignore cached transcript")
    args = parser.parse_args()

    media = Path(args.media)
    json_path = media.parent / "transcript.json"
    txt_path = media.parent / "transcript.txt"

    if json_path.exists() and not args.force:
        print(json.dumps({"transcript": str(json_path), "text": str(txt_path), "cached": True}))
        return 0

    if args.engine == "assemblyai":
        data = transcribe_assemblyai(str(media))
    else:
        data = transcribe_whisper(str(media), args.model)

    json_path.write_text(json.dumps(data, ensure_ascii=False))
    txt_path.write_text(
        "\n".join(f"[{fmt_ts(s['s'])}] {s['text']}" for s in data["segments"]) + "\n"
    )
    print(json.dumps({
        "transcript": str(json_path),
        "text": str(txt_path),
        "cached": False,
        "words": len(data["words"]),
        "duration": data["words"][-1]["e"] if data["words"] else 0,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
