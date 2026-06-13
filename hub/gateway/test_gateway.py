"""Gateway test suite — runs without network/GPU by monkeypatching the LLM and
generation providers. Covers the storyboard orchestration (the new logic), the
watcher rules, the history deltas, and market parsing.

    cd hub/gateway && pip install -r requirements.txt pytest && pytest
"""

import json
import os
import tempfile

import pytest


# --------------------------------------------------------------------------- #
# Storyboard                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def sb(tmp_path, monkeypatch):
    monkeypatch.setenv("STORYBOARD_DIR", str(tmp_path / "sb"))
    import importlib
    import storyboard
    importlib.reload(storyboard)
    return storyboard


def test_assemble_prompt_order(sb):
    shot = {"shot_type": "wide 24mm", "visible_context": "a wet ferry slip at night"}
    settings = {"style": "cinematic, film grain", "negative": "blurry, text"}
    out = sb.assemble_prompt(shot, settings)
    # SHOT TYPE → VISIBLE CONTEXT → style, joined and terminated; negative separate.
    assert out["prompt"] == "wide 24mm. a wet ferry slip at night. cinematic, film grain."
    assert out["negative"] == "blurry, text"


def test_assemble_prompt_skips_empty(sb):
    out = sb.assemble_prompt({"shot_type": "", "visible_context": "x"}, {"style": ""})
    assert out["prompt"] == "x."


def test_create_and_load_roundtrip(sb):
    p = sb.create_project("a heist on a midnight ferry", title="Ferry")
    assert p["title"] == "Ferry"
    assert p["settings"]["t2i_provider"] == "comfyui"
    loaded = sb.load_project(p["id"])
    assert loaded["idea"] == "a heist on a midnight ferry"


def test_list_projects_sorted(sb):
    a = sb.create_project("first")
    b = sb.create_project("second")
    ids = [x["id"] for x in sb.list_projects()]
    assert set(ids) == {a["id"], b["id"]}


def test_run_stage_world(sb, monkeypatch):
    monkeypatch.setattr(sb, "_llm", lambda *a, **k: "A rain-soaked 1990s port town.")
    p = sb.create_project("ferry heist")
    p = sb.run_stage(p, "world")
    assert "port town" in p["world"]


def test_run_stage_shots_parses_json(sb, monkeypatch):
    payload = {"shots": [
        {"name": "river road", "shot_type": "POV 24mm", "visible_context": "wet road"},
        {"name": "ferry stop", "shot_type": "wide", "visible_context": "empty slip"},
    ]}
    monkeypatch.setattr(sb, "_llm", lambda *a, **k: json.dumps(payload))
    p = sb.create_project("ferry heist")
    p = sb.run_stage(p, "shots")
    assert len(p["shots"]) == 2
    assert p["shots"][0]["name"] == "river road"
    assert p["shots"][0]["status"] == "draft"
    assert all(s["id"] for s in p["shots"])  # ids assigned


def test_run_stage_unknown_raises(sb):
    p = sb.create_project("x")
    with pytest.raises(ValueError):
        sb.run_stage(p, "bogus")


# --------------------------------------------------------------------------- #
# Watcher rules                                                                 #
# --------------------------------------------------------------------------- #

@pytest.fixture
def watcher(monkeypatch):
    monkeypatch.setenv("MARKET_MOVE_THRESHOLD", "8")
    monkeypatch.setenv("HN_POINTS_THRESHOLD", "600")
    import importlib
    import watcher as w
    importlib.reload(w)
    return w


def test_watcher_fires_on_threshold(watcher):
    markets = [{"source": "polymarket", "question": "Fed cut?", "yes_pct": 81,
                "delta_24h": 11, "url": "http://x"}]
    new = watcher.evaluate(markets, [])
    assert len(new) == 1 and new[0]["kind"] == "market"


def test_watcher_ignores_small_move(watcher):
    markets = [{"source": "kalshi", "question": "CPI?", "yes_pct": 54,
                "delta_24h": 3, "url": "http://x"}]
    assert watcher.evaluate(markets, []) == []


def test_watcher_dedups(watcher):
    markets = [{"source": "polymarket", "question": "Fed cut?", "yes_pct": 81,
                "delta_24h": 11, "url": "http://x"}]
    assert len(watcher.evaluate(markets, [])) == 1
    assert watcher.evaluate(markets, []) == []  # same bucket → no re-fire


def test_watcher_high_priority_on_big_move(watcher):
    markets = [{"source": "polymarket", "question": "X?", "yes_pct": 90,
                "delta_24h": 20, "url": "http://x"}]
    new = watcher.evaluate(markets, [])
    assert new[0]["priority"] == "high"


# --------------------------------------------------------------------------- #
# History deltas                                                               #
# --------------------------------------------------------------------------- #

def test_history_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB", str(tmp_path / "h.db"))
    import importlib
    import history
    importlib.reload(history)
    base = [{"source": "polymarket", "question": "Fed?", "yes_pct": 70, "volume_24h": 1}]
    history.record_markets(base)
    history._connect().execute("UPDATE market_snapshots SET ts = ts - 72000")
    history._connect().commit()
    now = [{"source": "polymarket", "question": "Fed?", "yes_pct": 81, "volume_24h": 1}]
    history.record_markets(now)
    enriched = history.enrich_with_deltas(now)
    assert enriched[0]["delta_24h"] == 11


# --------------------------------------------------------------------------- #
# Market parsing                                                               #
# --------------------------------------------------------------------------- #

def test_parse_polymarket():
    import main
    data = [{"question": "Q?", "slug": "q", "events": [{"slug": "ev"}],
             "outcomePrices": '["0.62", "0.38"]', "volume24hr": 1000,
             "endDate": "2026-07-01"}]
    items = main.parse_polymarket(data)
    assert items[0]["yes_pct"] == 62 and items[0]["source"] == "polymarket"
