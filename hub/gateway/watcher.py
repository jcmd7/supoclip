"""Watcher — turns hub data into alerts.

Runs as a background asyncio loop inside the gateway. On each tick it pulls the
current markets (with 24h deltas from history) and the HN cache, evaluates a set
of rules, and for anything new fires:
  - an ntfy push (if NTFY_TOPIC is set), and
  - an entry in the in-memory event log (served at /api/events).

Rules are intentionally simple and declarative (see DEFAULT_RULES). Dedup is by
a stable event key so the same alert doesn't re-fire every tick.

Env:
  NTFY_URL      base url of the ntfy server (default http://localhost:8091)
  NTFY_TOPIC    topic to publish to; if unset, pushes are skipped (log only)
  WATCH_INTERVAL_SECONDS   tick interval (default 300)
  MARKET_MOVE_THRESHOLD    pct points for a market-move alert (default 8)
  HN_POINTS_THRESHOLD      points for an HN alert (default 600)
  WATCH_KEYWORDS           comma list; HN/market alerts only fire if the text
                           matches one of these (empty = match all)
"""

import asyncio
import os
import time

import httpx

NTFY_URL = os.getenv("NTFY_URL", "http://localhost:8091").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC")
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL_SECONDS", "300"))
MARKET_MOVE_THRESHOLD = float(os.getenv("MARKET_MOVE_THRESHOLD", "8"))
HN_POINTS_THRESHOLD = int(os.getenv("HN_POINTS_THRESHOLD", "600"))
_KEYWORDS = [k.strip().lower() for k in os.getenv("WATCH_KEYWORDS", "").split(",") if k.strip()]

MAX_EVENTS = 100
_events: list[dict] = []
_seen: set[str] = set()


def recent_events(limit: int = 50) -> list[dict]:
    return _events[:limit]


def _keyword_ok(text: str) -> bool:
    if not _KEYWORDS:
        return True
    low = text.lower()
    return any(k in low for k in _KEYWORDS)


def _emit(key: str, kind: str, title: str, body: str, url: str | None, priority: str):
    """Record an event (deduped by key) and return it if new, else None."""
    if key in _seen:
        return None
    _seen.add(key)
    event = {
        "id": key,
        "kind": kind,
        "title": title,
        "body": body,
        "url": url,
        "priority": priority,
        "ts": time.time(),
    }
    _events.insert(0, event)
    del _events[MAX_EVENTS:]
    return event


async def _push_ntfy(client: httpx.AsyncClient, event: dict):
    if not NTFY_TOPIC:
        return
    # JSON publish format: UTF-8 safe (header-based publishing chokes on
    # non-latin-1 chars like arrows in titles).
    payload = {
        "topic": NTFY_TOPIC,
        "title": event["title"],
        "message": event["body"],
        "priority": 4 if event["priority"] == "high" else 3,
        "tags": [{"market": "chart_with_upwards_trend", "hn": "newspaper",
                  "alert": "warning"}.get(event["kind"], "bell")],
    }
    if event.get("url"):
        payload["click"] = event["url"]
        payload["actions"] = [{"action": "view", "label": "Open", "url": event["url"]}]
    try:
        await client.post(NTFY_URL, json=payload, timeout=10)
    except httpx.HTTPError:
        pass


def evaluate(markets: list[dict], hn: list[dict]) -> list[dict]:
    """Pure rule evaluation → list of new events (also appended to the log)."""
    new = []

    for m in markets:
        delta = m.get("delta_24h")
        if delta is None or abs(delta) < MARKET_MOVE_THRESHOLD:
            continue
        if not _keyword_ok(m["question"]):
            continue
        # Bucket the move so a drifting market re-alerts only on a bigger swing.
        bucket = int(abs(delta) // MARKET_MOVE_THRESHOLD)
        key = f"market::{m['source']}::{m['question']}::{'up' if delta > 0 else 'down'}{bucket}"
        arrow = "▲" if delta > 0 else "▼"
        ev = _emit(
            key, "market",
            f"{arrow} {abs(round(delta))}pt move",
            f"{m['question']} → {m['yes_pct']}% ({m['source']})",
            m.get("url"),
            "high" if abs(delta) >= 2 * MARKET_MOVE_THRESHOLD else "default",
        )
        if ev:
            new.append(ev)

    for h in hn:
        if h.get("points", 0) < HN_POINTS_THRESHOLD or not _keyword_ok(h.get("title", "")):
            continue
        key = f"hn::{h.get('hn_url')}"
        ev = _emit(
            key, "hn",
            f"HN {h['points']}↑",
            f"{h['title']} ({h['comments']} comments)",
            h.get("hn_url"),
            "default",
        )
        if ev:
            new.append(ev)

    return new


async def run(get_markets, get_hn):
    """Background loop. `get_markets`/`get_hn` are the gateway's async endpoints."""
    # Prime the seen-set on first pass so we don't alert the entire backlog at boot.
    first = True
    async with httpx.AsyncClient() as client:
        while True:
            try:
                markets = (await get_markets())["items"]
                hn = (await get_hn())["items"]
                events = evaluate(markets, hn)
                if first:
                    first = False  # logged but not pushed on boot
                else:
                    for ev in events:
                        await _push_ntfy(client, ev)
            except Exception:
                pass
            await asyncio.sleep(WATCH_INTERVAL)
