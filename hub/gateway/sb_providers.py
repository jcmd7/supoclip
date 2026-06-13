"""Generation providers for the Storyboard Conceptor.

Pluggable backends for the visual stages:
  - T2I  (text → still image)
  - I2V  (still image → video clip)
  - 360  (equirectangular panorama — Seedance-2 ground truth)
  - sheet(3×3 turnaround contact sheet for consistency review)

Default backend is local ComfyUI (the `comfyui` hub module). Cloud backends
(fal/Replicate for T2I, Seedance via BytePlus/fal for I2V) are documented hooks
— wire a key and implement the marked function bodies.

Each public function returns the asset filename written under the project's
assets/ dir, or raises RuntimeError with an actionable message.
"""

import json
import os
import time
import uuid
from pathlib import Path

import httpx

COMFY_HOST = os.getenv("COMFY_HOST", "http://localhost:8188").rstrip("/")
# Workflow JSONs (API format) keyed by kind; override dir with COMFY_WORKFLOWS.
WORKFLOWS_DIR = Path(os.getenv(
    "COMFY_WORKFLOWS",
    str(Path(__file__).resolve().parent / "sb_workflows"),
))

ASPECT_DIMS = {
    "16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1024, 1024),
    "360": (2048, 1024),  # equirectangular 2:1
}


def _comfy_run(workflow: dict, host: str = COMFY_HOST, timeout: int = 600) -> bytes:
    """Submit a workflow to ComfyUI, wait, and return the produced media bytes."""
    client_id = uuid.uuid4().hex
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{host}/prompt", json={"prompt": workflow, "client_id": client_id})
        resp.raise_for_status()
        prompt_id = resp.json()["prompt_id"]
        deadline = time.time() + timeout
        outputs = None
        while time.time() < deadline:
            hist = client.get(f"{host}/history/{prompt_id}").json()
            if prompt_id in hist:
                outputs = hist[prompt_id]["outputs"]
                break
            time.sleep(2)
        if outputs is None:
            raise RuntimeError("ComfyUI render timed out")
        produced = None
        for node_out in outputs.values():
            for key in ("images", "gifs", "videos"):
                if node_out.get(key):
                    produced = node_out[key][0]
                    break
            if produced:
                break
        if not produced:
            raise RuntimeError("ComfyUI render produced no media")
        params = {"filename": produced["filename"], "type": produced.get("type", "output")}
        if produced.get("subfolder"):
            params["subfolder"] = produced["subfolder"]
        media = client.get(f"{host}/view", params=params)
        media.raise_for_status()
        return media.content


def _load_workflow(kind: str) -> dict:
    path = WORKFLOWS_DIR / f"{kind}.json"
    if not path.exists():
        raise RuntimeError(
            f"no ComfyUI workflow for '{kind}' at {path}. Export one from ComfyUI "
            "(Save → API Format) with placeholder tokens __PROMPT__, __NEGATIVE__, "
            "__WIDTH__, __HEIGHT__, __IMAGE__ and drop it there.")
    return json.loads(path.read_text())


def _fill(workflow: dict, **tokens) -> dict:
    """Replace __TOKEN__ placeholders throughout a workflow JSON."""
    text = json.dumps(workflow)
    for key, value in tokens.items():
        text = text.replace(f"__{key.upper()}__", json.dumps(str(value))[1:-1])
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Public dispatch                                                              #
# --------------------------------------------------------------------------- #

def generate_image(prompt: str, negative: str, aspect: str, out_path: Path,
                   provider: str = "comfyui", kind: str = "image") -> str:
    """T2I / 360 / sheet still generation. `kind` selects the workflow."""
    w, h = ASPECT_DIMS.get("360" if kind == "panorama" else aspect, ASPECT_DIMS["16:9"])
    if provider == "comfyui":
        wf = _fill(_load_workflow(kind), prompt=prompt, negative=negative, width=w, height=h)
        data = _comfy_run(wf)
    elif provider in ("fal", "openai", "replicate"):
        raise RuntimeError(
            f"cloud T2I provider '{provider}' not yet wired — implement in "
            "sb_providers.generate_image (needs an API key).")
    else:
        raise RuntimeError(f"unknown T2I provider: {provider}")
    out_path.write_bytes(data)
    return out_path.name


def generate_video(image_path: Path, prompt: str, out_path: Path,
                   provider: str = "comfyui") -> str:
    """I2V — animate a still into a clip."""
    if provider == "comfyui":
        # The I2V workflow loads __IMAGE__ from ComfyUI's input dir; upload first.
        uploaded = _comfy_upload(image_path)
        wf = _fill(_load_workflow("video"), image=uploaded, prompt=prompt)
        data = _comfy_run(wf)
    elif provider == "seedance":
        raise RuntimeError(
            "Seedance I2V is cloud-only (BytePlus/fal). Feed the shot's 360° "
            "panorama as ground truth and implement the API call in "
            "sb_providers.generate_video (needs a BytePlus/fal key).")
    else:
        raise RuntimeError(f"unknown I2V provider: {provider}")
    out_path.write_bytes(data)
    return out_path.name


def _comfy_upload(image_path: Path, host: str = COMFY_HOST) -> str:
    with httpx.Client(timeout=60) as client:
        with open(image_path, "rb") as f:
            resp = client.post(f"{host}/upload/image",
                               files={"image": (image_path.name, f, "image/png")})
        resp.raise_for_status()
        return resp.json()["name"]
