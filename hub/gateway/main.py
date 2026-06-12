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

import history

HEALTH_HOST = os.getenv("HEALTH_HOST", "localhost")
HEALTH_TIMEOUT_SECONDS = float(os.getenv("HEALTH_TIMEOUT_SECONDS", "3"))
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "300"))
NEWS_ITEMS_PER_FEED = int(os.getenv("NEWS_ITEMS_PER_FEED", "10"))
MARKETS_CACHE_SECONDS = int(os.getenv("MARKETS_CACHE_SECONDS", "60"))
HN_CACHE_SECONDS = int(os.getenv("HN_CACHE_SECONDS", "120"))
# Directory of {polymarket,kalshi,hn}.json files used instead of live HTTP
# (offline demos / tests).
FIXTURES_DIR = os.getenv("FIXTURES_DIR")

POLYMARKET_URL = (
    "https://gamma-api.polymarket.com/markets"
    "?active=true&closed=false&order=volume24hr&ascending=false&limit=15"
)
KALSHI_URL = "https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=100"
HN_URL = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=20"


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
        # Local feed generators (e.g. RSSHub) are addressed like health URLs.
        response = await client.get(feed["url"].replace("{host}", HEALTH_HOST))
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


def parse_polymarket(data) -> list[dict]:
    items = []
    for m in data or []:
        try:
            prices = m.get("outcomePrices")
            if isinstance(prices, str):
                prices = json.loads(prices)
            yes_pct = round(float(prices[0]) * 100) if prices else None
            events = m.get("events") or []
            slug = events[0]["slug"] if events else m.get("slug", "")
            items.append({
                "source": "polymarket",
                "question": m.get("question", ""),
                "yes_pct": yes_pct,
                "volume_24h": round(float(m.get("volume24hr") or 0)),
                "closes": m.get("endDate"),
                "url": f"https://polymarket.com/event/{slug}",
            })
        except (KeyError, ValueError, TypeError, IndexError):
            continue
    return items


def parse_kalshi(data) -> list[dict]:
    items = []
    for m in (data or {}).get("markets", []):
        try:
            price = m.get("last_price")
            if not price:
                bid, ask = m.get("yes_bid") or 0, m.get("yes_ask") or 0
                price = (bid + ask) / 2 if (bid or ask) else None
            items.append({
                "source": "kalshi",
                "question": m.get("title", ""),
                "yes_pct": round(price) if price is not None else None,  # cents == %
                "volume_24h": round(float(m.get("volume_24h") or 0)),
                "closes": m.get("close_time"),
                "url": "https://kalshi.com/search?query=" + (m.get("title", "")).replace(" ", "+"),
            })
        except (ValueError, TypeError):
            continue
    items.sort(key=lambda i: i["volume_24h"], reverse=True)
    return items[:15]


def parse_hn(data) -> list[dict]:
    items = []
    for hit in (data or {}).get("hits", []):
        items.append({
            "title": hit.get("title", ""),
            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "points": hit.get("points") or 0,
            "comments": hit.get("num_comments") or 0,
            "created_at": hit.get("created_at"),
        })
    return items


async def _fetch_json(client: httpx.AsyncClient, url: str, fixture: str):
    if FIXTURES_DIR:
        path = Path(FIXTURES_DIR) / f"{fixture}.json"
        if path.exists():
            return json.loads(path.read_text())
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError:
        return None


_markets_cache: dict = {"fetched_at": 0.0, "items": []}
_hn_cache: dict = {"fetched_at": 0.0, "items": []}


@app.get("/api/markets")
async def get_markets(source: str = "all", q: str = ""):
    now = time.time()
    if now - _markets_cache["fetched_at"] >= MARKETS_CACHE_SECONDS:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": "MissionControl/0.1"}
        ) as client:
            poly, kalshi = await asyncio.gather(
                _fetch_json(client, POLYMARKET_URL, "polymarket"),
                _fetch_json(client, KALSHI_URL, "kalshi"),
            )
        items = parse_polymarket(poly) + parse_kalshi(kalshi)
        items.sort(key=lambda i: i["volume_24h"], reverse=True)
        history.record_markets(items)
        _markets_cache.update(fetched_at=now, items=items)

    items = history.enrich_with_deltas(list(_markets_cache["items"]))
    if source != "all":
        items = [i for i in items if i["source"] == source]
    if q:
        needle = q.lower()
        items = [i for i in items if needle in i["question"].lower()]
    return {"items": items}


@app.get("/api/markets/history")
async def get_market_history(key: str):
    """Sparkline samples (oldest→newest yes_pct) for one market key."""
    return {"key": key, "values": history.sparkline(key)}


@app.get("/api/hn")
async def get_hn():
    now = time.time()
    if now - _hn_cache["fetched_at"] >= HN_CACHE_SECONDS:
        async with httpx.AsyncClient(
            timeout=10, follow_redirects=True, headers={"User-Agent": "MissionControl/0.1"}
        ) as client:
            data = await _fetch_json(client, HN_URL, "hn")
        _hn_cache.update(fetched_at=now, items=parse_hn(data))
    return {"items": _hn_cache["items"]}


CLIPS_DIR = Path(os.path.expanduser(
    os.getenv("CLIPS_DIR", "~/.mission-control/clips")
))


@app.get("/api/clips")
async def get_clips():
    """Clip library — reads library.json written by the clip skill."""
    manifest = CLIPS_DIR / "library.json"
    if not manifest.exists():
        return {"items": []}
    try:
        items = json.loads(manifest.read_text())
    except (json.JSONDecodeError, OSError):
        return {"items": []}
    items.sort(key=lambda c: c.get("created_at", 0), reverse=True)
    return {"items": items}


@app.get("/api/brief")
async def get_brief():
    """Deterministic morning brief assembled from cached + stored data.
    No LLM required — always free, always renders."""
    lines = []

    # Warm the markets/HN caches so the brief works regardless of call order.
    await get_markets()
    await get_hn()

    # Biggest market movers over 24h (needs history).
    markets = history.enrich_with_deltas(list(_markets_cache["items"]))
    movers = sorted(
        (m for m in markets if m.get("delta_24h")),
        key=lambda m: abs(m["delta_24h"]), reverse=True,
    )[:3]
    for m in movers:
        d = m["delta_24h"]
        arrow = "up" if d > 0 else "down"
        lines.append({
            "kind": "market",
            "text": f"{m['question']} moved {arrow} {abs(d)} pts to {m['yes_pct']}%",
            "url": m["url"],
        })

    # Top HN discussion right now.
    hn = sorted(_hn_cache["items"], key=lambda h: h["points"], reverse=True)[:2]
    for h in hn:
        lines.append({
            "kind": "hn",
            "text": f"HN: {h['title']} ({h['points']} pts, {h['comments']} comments)",
            "url": h["hn_url"],
        })

    # Clip activity in the last 24h.
    clips = (await get_clips())["items"]
    day_ago = time.time() - 86400
    recent = [c for c in clips if c.get("created_at", 0) >= day_ago]
    if recent:
        published = sum(1 for c in recent if c.get("published"))
        lines.append({
            "kind": "clips",
            "text": f"{len(recent)} clip(s) made in the last 24h, {published} published",
            "url": None,
        })

    return {
        "generated_at": time.time(),
        "headline": _brief_headline(len(movers), len(hn), len(recent) if recent else 0),
        "lines": lines,
    }


def _brief_headline(n_movers: int, n_hn: int, n_clips: int) -> str:
    if not (n_movers or n_hn or n_clips):
        return "Quiet so far — no tracked movement yet. History fills in as the hub runs."
    bits = []
    if n_movers:
        bits.append(f"{n_movers} market move{'s' if n_movers != 1 else ''}")
    if n_clips:
        bits.append(f"{n_clips} new clip{'s' if n_clips != 1 else ''}")
    return "Since yesterday: " + ", ".join(bits) + "." if bits else "Latest signals below."


# Serve clip library files (videos + posters) before the SPA catch-all.
if CLIPS_DIR.exists():
    app.mount("/clips", StaticFiles(directory=str(CLIPS_DIR)), name="clips")

app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
