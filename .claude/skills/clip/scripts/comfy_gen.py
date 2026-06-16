#!/usr/bin/env python3
"""Generate a short video via a local ComfyUI instance (Wan / LTX-Video).

Submits a workflow to ComfyUI's HTTP API, waits for the render, and downloads
the resulting mp4. Use it to make B-roll, intros, or animated backgrounds for
/clip with no per-render cost (local GPU).

This calls ComfyUI's API, so it needs a workflow JSON exported from the UI
(Save (API Format)) with a prompt-injection point. Point --workflow at it and
mark the positive-prompt node id with --prompt-node. A starter text-to-video
workflow for Wan lives at workflows/wan_t2v.json if present.

Usage:
    python3 comfy_gen.py --prompt "cinematic city skyline at dusk" \
        --workflow workflows/wan_t2v.json --prompt-node 6 --out broll/city.mp4 \
        [--host http://localhost:8188] [--timeout 600]
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--workflow", required=True, help="ComfyUI API-format workflow JSON")
    parser.add_argument("--prompt-node", required=True,
                        help="node id whose inputs.text receives the prompt")
    parser.add_argument("--out", required=True)
    parser.add_argument("--host", default="http://localhost:8188")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    workflow_path = Path(args.workflow)
    if not workflow_path.exists():
        print(f"workflow not found: {workflow_path}", file=sys.stderr)
        return 1
    workflow = json.loads(workflow_path.read_text())

    if args.prompt_node not in workflow:
        print(f"prompt-node {args.prompt_node} not in workflow (nodes: "
              f"{', '.join(list(workflow)[:10])}…)", file=sys.stderr)
        return 1
    workflow[args.prompt_node]["inputs"]["text"] = args.prompt

    client_id = uuid.uuid4().hex
    host = args.host.rstrip("/")
    with httpx.Client(timeout=30) as client:
        try:
            resp = client.post(f"{host}/prompt",
                               json={"prompt": workflow, "client_id": client_id})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"failed to queue prompt (is ComfyUI running on {host}?): {e}",
                  file=sys.stderr)
            return 1
        prompt_id = resp.json()["prompt_id"]

        # Poll history until the prompt completes.
        deadline = time.time() + args.timeout
        outputs = None
        while time.time() < deadline:
            hist = client.get(f"{host}/history/{prompt_id}").json()
            if prompt_id in hist:
                outputs = hist[prompt_id]["outputs"]
                break
            time.sleep(2)
        if outputs is None:
            print("timed out waiting for ComfyUI render", file=sys.stderr)
            return 1

        # Find the produced video/gif/image file in the outputs.
        produced = None
        for node_out in outputs.values():
            for key in ("gifs", "videos", "images"):
                if node_out.get(key):
                    produced = node_out[key][0]
                    break
            if produced:
                break
        if not produced:
            print("render finished but no media output found", file=sys.stderr)
            return 1

        params = {"filename": produced["filename"], "type": produced.get("type", "output")}
        if produced.get("subfolder"):
            params["subfolder"] = produced["subfolder"]
        media = client.get(f"{host}/view", params=params)
        media.raise_for_status()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(media.content)
    print(json.dumps({"out": str(out), "prompt": args.prompt, "source": produced["filename"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
