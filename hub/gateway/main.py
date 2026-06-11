"""Mission Control gateway.

Single small service that powers the hub dashboard:
  GET /api/modules  -> module registry (from modules.json)
  GET /api/status   -> live health of every registered module/service
  GET /api/news     -> aggregated items from configured RSS/Atom feeds
  GET /             -> static dashboard

Health URLs in modules.json may contain a "{host}" placeholder, replaced
with HEALTH_HOST (defaults to "localhost" when run directly, set to
"host.docker.internal" by the hub compose file so the container can reach
services published on the host).
"""

import asyncio
import json
import os
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

HEALTH_HOST = os.getenv("HEALTH_HOST", "localhost")
HEALTH_TIMEOUT_SECONDS = float(os.getenv("HEALTH_TIMEOUT_SECONDS", "3"))
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "300"))
NEWS_ITEMS_PER_FEED = int(os.getenv("NEWS_ITEMS_PER_FEED", "10"))


def _find_path(env_var: str, candidates: list[Path]) -> Path:
    override = os.getenv(env_var)
    if override:
        return Path(override)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


_HERE = Path(__file__).resolve().parent
MODULES_FILE = _find_path(
    "MODULES_FILE", [_HERE / "modules.json", _HERE.parent / "modules.json"]
)
DASHBOARD_DIR = _find_path(
    "DASHBOARD_DIR", [_HERE / "dashboard", _HERE.parent / "dashboard"]
)

app = FastAPI(title="Mission Control Gateway")

_news_cache: dict = {"fetched_at": 0.0, "items": []}


def load_registry() -> dict:
    with open(MODULES_FILE) as f:
        return json.load(f)


@app.get("/api/modules")
async def get_modules():
    registry = load_registry()
    return {"hub_name": registry.get("hub_name", "Hub"), "modules": registry["modules"]}


async def _check_service(client: httpx.AsyncClient, service: dict) -> dict:
    url = service["health_url"].replace("{host}", HEALTH_HOST)
    started = time.monotonic()
    try:
        response = await client.get(url)
        latency_ms = round((time.monotonic() - started) * 1000)
        # Anything the server answers (including 401/404) means it is up.
        online = response.status_code < 500
        return {"name": service["name"], "online": online, "latency_ms": latency_ms}
    except httpx.HTTPError:
        return {"name": service["name"], "online": False, "latency_ms": None}


@app.get("/api/status")
async def get_status():
    registry = load_registry()
    async with httpx.AsyncClient(
        timeout=HEALTH_TIMEOUT_SECONDS, follow_redirects=True, verify=False
    ) as client:
        module_checks = [
            asyncio.gather(*(_check_service(client, s) for s in module["services"]))
            for module in registry["modules"]
        ]
        results = await asyncio.gather(*module_checks)

    statuses = []
    for module, services in zip(registry["modules"], results):
        up = sum(1 for s in services if s["online"])
        if up == len(services):
            state = "online"
        elif up > 0:
            state = "degraded"
        else:
            state = "offline"
        statuses.append({"id": module["id"], "state": state, "services": services})
    return {"checked_at": time.time(), "modules": statuses}


def _parse_feed(name: str, content: bytes) -> list[dict]:
    """Minimal RSS 2.0 / Atom parser; returns normalized items."""
    items = []
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    rss_items = root.findall(".//item")
    atom_entries = root.findall(".//atom:entry", ns)

    for item in rss_items[:NEWS_ITEMS_PER_FEED]:
        published = item.findtext("pubDate")
        timestamp = None
        if published:
            try:
                timestamp = parsedate_to_datetime(published).timestamp()
            except (ValueError, TypeError):
                pass
        items.append(
            {
                "source": name,
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "published": timestamp,
            }
        )

    for entry in atom_entries[:NEWS_ITEMS_PER_FEED]:
        link_el = entry.find("atom:link", ns)
        items.append(
            {
                "source": name,
                "title": (entry.findtext("atom:title", "", ns) or "").strip(),
                "link": link_el.get("href", "") if link_el is not None else "",
                "published": None,
            }
        )
    return items


async def _fetch_feed(client: httpx.AsyncClient, feed: dict) -> list[dict]:
    try:
        response = await client.get(feed["url"])
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    return _parse_feed(feed["name"], response.content)


@app.get("/api/news")
async def get_news():
    now = time.time()
    if now - _news_cache["fetched_at"] < NEWS_CACHE_SECONDS:
        return {"cached": True, "items": _news_cache["items"]}

    registry = load_registry()
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, headers={"User-Agent": "MissionControl/0.1"}
    ) as client:
        per_feed = await asyncio.gather(
            *(_fetch_feed(client, feed) for feed in registry.get("feeds", []))
        )

    items = [item for feed_items in per_feed for item in feed_items]
    items.sort(key=lambda i: i["published"] or 0, reverse=True)
    _news_cache.update(fetched_at=now, items=items)
    return {"cached": False, "items": items}


app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
