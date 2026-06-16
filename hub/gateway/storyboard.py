"""Storyboard Conceptor — guided idea → world → ideas → script → shots → film.

Pipeline (every stage editable, persisted as a project under STORYBOARD_DIR):

    idea --LLM--> world bible --LLM--> beat ideas --LLM--> script --LLM--> shots
    per shot: assembled prompt --T2I--> still --I2V--> clip
              + 360° equirect panorama (Seedance-2 ground truth)
              + 3×3 turnaround sheet

Generation is provider-pluggable (`providers.py`): ComfyUI local by default,
cloud hooks documented. The LLM is any OpenAI-compatible chat endpoint
(OpenAI, Gemini-compat, Ollama, ...), configured via STORYBOARD_LLM_* env.

This module owns project state + the LLM stages + prompt assembly. It is
written for testability: the LLM call (`_llm`) and the generation dispatch are
module-level functions that tests monkeypatch — no network needed to exercise
the orchestration.
"""

import json
import os
import time
import uuid
from pathlib import Path

import httpx

STORYBOARD_DIR = Path(os.path.expanduser(
    os.getenv("STORYBOARD_DIR", "~/.mission-control/storyboards")
))

STAGES = ["world", "ideas", "script", "shots"]

DEFAULT_SETTINGS = {
    "style": "cinematic, dramatic low-key lighting, shallow depth of field, "
             "film grain, photorealistic",
    "negative": "blurry, low quality, watermark, text, deformed, extra limbs",
    "aspect": "16:9",
    "t2i_provider": "comfyui",
    "i2v_provider": "comfyui",
}


# --------------------------------------------------------------------------- #
# LLM (OpenAI-compatible chat completions)                                     #
# --------------------------------------------------------------------------- #

def _llm(messages: list[dict], json_mode: bool = False, model: str | None = None) -> str:
    base = os.getenv("STORYBOARD_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("STORYBOARD_LLM_KEY") or os.getenv("OPENAI_API_KEY", "")
    model = model or os.getenv("STORYBOARD_LLM_MODEL", "gpt-4o-mini")
    body = {"model": model, "messages": messages, "temperature": 0.8}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    resp = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------- #
# Stages                                                                       #
# --------------------------------------------------------------------------- #

def stage_world(project: dict) -> str:
    return _llm([
        {"role": "system", "content":
            "You are a film art director. From a one-line idea, write a concise "
            "WORLD BIBLE: setting, era, mood, color palette, lens/film stock, and "
            "recurring visual motifs. 150 words max. This anchors visual "
            "consistency across every shot."},
        {"role": "user", "content": project["idea"]},
    ])


def stage_ideas(project: dict) -> list[str]:
    out = _llm([
        {"role": "system", "content":
            "Given an idea and world bible, propose 5-8 distinct visual beats "
            "(locations/moments) that tell the story. Return JSON: "
            '{"beats": ["...", "..."]}.'},
        {"role": "user", "content":
            f"IDEA: {project['idea']}\n\nWORLD:\n{project.get('world', '')}"},
    ], json_mode=True)
    return json.loads(out).get("beats", [])


def stage_script(project: dict) -> str:
    beats = "\n".join(f"- {b}" for b in project.get("ideas", []))
    return _llm([
        {"role": "system", "content":
            "Write a tight shot-by-shot script/treatment from these beats. "
            "Plain prose, present tense, visual. No camera jargon yet."},
        {"role": "user", "content":
            f"IDEA: {project['idea']}\n\nWORLD:\n{project.get('world','')}\n\n"
            f"BEATS:\n{beats}"},
    ])


def stage_shots(project: dict) -> list[dict]:
    out = _llm([
        {"role": "system", "content":
            "Break the script into a shot list. For each shot return: name (2-3 "
            "words), shot_type (camera framing/lens/movement), visible_context "
            "(detailed description of exactly what is in frame). Return JSON: "
            '{"shots": [{"name","shot_type","visible_context"}]}.'},
        {"role": "user", "content":
            f"WORLD:\n{project.get('world','')}\n\nSCRIPT:\n{project.get('script','')}"},
    ], json_mode=True)
    shots = json.loads(out).get("shots", [])
    return [
        {
            "id": uuid.uuid4().hex[:8],
            "name": s.get("name", f"shot {i+1}"),
            "shot_type": s.get("shot_type", ""),
            "visible_context": s.get("visible_context", ""),
            "image": None, "video": None, "panorama": None, "sheet": None,
            "ref": None, "status": "draft",
        }
        for i, s in enumerate(shots)
    ]


_STAGE_FN = {"world": stage_world, "ideas": stage_ideas,
             "script": stage_script, "shots": stage_shots}


def run_stage(project: dict, stage: str) -> dict:
    if stage not in _STAGE_FN:
        raise ValueError(f"unknown stage: {stage}")
    project[stage] = _STAGE_FN[stage](project)
    project["updated_at"] = time.time()
    return project


# --------------------------------------------------------------------------- #
# Prompt assembly — SHOT TYPE → VISIBLE CONTEXT → style addition (+ negative)   #
# --------------------------------------------------------------------------- #

def assemble_prompt(shot: dict, settings: dict) -> dict:
    parts = [shot.get("shot_type", ""), shot.get("visible_context", ""),
             settings.get("style", "")]
    positive = ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())
    if positive:
        positive += "."
    return {"prompt": positive, "negative": settings.get("negative", "")}


# --------------------------------------------------------------------------- #
# Persistence                                                                  #
# --------------------------------------------------------------------------- #

def _project_dir(project_id: str) -> Path:
    return STORYBOARD_DIR / project_id


def create_project(idea: str, title: str | None = None, settings: dict | None = None) -> dict:
    project_id = uuid.uuid4().hex[:12]
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    project = {
        "id": project_id,
        "title": title or (idea[:48] if idea else "untitled"),
        "idea": idea,
        "settings": merged,
        "world": None, "ideas": [], "script": None, "shots": [],
        "created_at": time.time(), "updated_at": time.time(),
    }
    save_project(project)
    return project


def save_project(project: dict) -> None:
    d = _project_dir(project["id"])
    (d / "assets").mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps(project, indent=2))


def load_project(project_id: str) -> dict | None:
    path = _project_dir(project_id) / "project.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_projects() -> list[dict]:
    if not STORYBOARD_DIR.exists():
        return []
    out = []
    for p in STORYBOARD_DIR.glob("*/project.json"):
        try:
            proj = json.loads(p.read_text())
            out.append({"id": proj["id"], "title": proj["title"],
                        "idea": proj["idea"], "shots": len(proj.get("shots", [])),
                        "updated_at": proj.get("updated_at", 0)})
        except (json.JSONDecodeError, KeyError):
            continue
    out.sort(key=lambda x: x["updated_at"], reverse=True)
    return out
