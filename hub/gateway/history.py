"""SQLite-backed history for the hub gateway.

Records a timestamped snapshot of market probabilities each time markets are
fetched, so the dashboard can show change-over-time (deltas, sparklines) instead
of only the live "now". Keyed by a stable market identity (source + question).

Single-file, no migrations framework — the schema is created on open. The DB
path defaults to hub/gateway/hub_history.db (override with HISTORY_DB env var).
"""

import os
import sqlite3
import time
from pathlib import Path

_DB_PATH = os.getenv("HISTORY_DB", str(Path(__file__).resolve().parent / "hub_history.db"))
_RETENTION_SECONDS = int(os.getenv("HISTORY_RETENTION_DAYS", "30")) * 86400

_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                ts          INTEGER NOT NULL,
                market_key  TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                question    TEXT    NOT NULL,
                yes_pct     REAL,
                volume_24h  REAL
            )
            """
        )
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_key_ts "
            "ON market_snapshots (market_key, ts)"
        )
        _conn.commit()
    return _conn


def market_key(item: dict) -> str:
    return f"{item['source']}::{item['question']}"


def record_markets(items: list[dict]) -> None:
    """Append a snapshot row for each market. Idempotent enough — one row per
    fetch cycle; callers are already rate-limited by the fetch cache."""
    if not items:
        return
    conn = _connect()
    now = int(time.time())
    conn.executemany(
        "INSERT INTO market_snapshots "
        "(ts, market_key, source, question, yes_pct, volume_24h) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (now, market_key(i), i["source"], i["question"],
             i.get("yes_pct"), i.get("volume_24h"))
            for i in items
        ],
    )
    conn.execute("DELETE FROM market_snapshots WHERE ts < ?", (now - _RETENTION_SECONDS,))
    conn.commit()


def enrich_with_deltas(items: list[dict], window_seconds: int = 86400) -> list[dict]:
    """Attach `yes_pct_24h_ago` and `delta_24h` to each market, using the oldest
    snapshot within the window. Missing history -> deltas are None."""
    conn = _connect()
    cutoff = int(time.time()) - window_seconds
    for item in items:
        row = conn.execute(
            "SELECT yes_pct FROM market_snapshots "
            "WHERE market_key = ? AND ts >= ? AND yes_pct IS NOT NULL "
            "ORDER BY ts ASC LIMIT 1",
            (market_key(item), cutoff),
        ).fetchone()
        if row and item.get("yes_pct") is not None:
            item["yes_pct_24h_ago"] = round(row["yes_pct"])
            item["delta_24h"] = round(item["yes_pct"] - row["yes_pct"])
        else:
            item["yes_pct_24h_ago"] = None
            item["delta_24h"] = None
    return items


def sparkline(market_key_value: str, points: int = 20, window_seconds: int = 7 * 86400) -> list[float]:
    """Return up to `points` yes_pct samples (oldest→newest) for one market."""
    conn = _connect()
    cutoff = int(time.time()) - window_seconds
    rows = conn.execute(
        "SELECT yes_pct FROM market_snapshots "
        "WHERE market_key = ? AND ts >= ? AND yes_pct IS NOT NULL ORDER BY ts ASC",
        (market_key_value, cutoff),
    ).fetchall()
    values = [r["yes_pct"] for r in rows]
    if len(values) <= points:
        return values
    step = len(values) / points
    return [values[int(i * step)] for i in range(points)]
