"""SQLite-backed cache + read-model store (CON-1 cache-first architecture).

This is the single seam for the later AWS migration (NFR-5): swap this class
for a DynamoDB/RDS implementation without touching the logic layer.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS kv_cache (
  key TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  ttl_seconds INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  tca TEXT NOT NULL,
  risk TEXT NOT NULL,
  urgency REAL NOT NULL,
  document TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_urgency ON events(urgency DESC);
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  items INTEGER DEFAULT 0,
  error TEXT
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CacheService:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_DDL)
            logger.info("Cache store ready at %s", db_path)
        except sqlite3.Error as exc:
            logger.error("Failed to initialise cache store: %s", exc)
            raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------- kv cache
    def get(self, key: str, *, allow_stale: bool = False) -> Any | None:
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT payload, fetched_at, ttl_seconds FROM kv_cache WHERE key = ?",
                    (key,),
                ).fetchone()
        except sqlite3.Error as exc:
            logger.error("Cache read failed for %s: %s", key, exc)
            return None
        if row is None:
            return None
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        age = (_now() - fetched_at).total_seconds()
        if age > row["ttl_seconds"] and not allow_stale:
            return None
        try:
            return json.loads(row["payload"])
        except json.JSONDecodeError as exc:
            logger.error("Corrupt cache payload for %s: %s", key, exc)
            return None

    def put(self, key: str, payload: Any, ttl_seconds: int) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO kv_cache (key, payload, fetched_at, ttl_seconds) "
                    "VALUES (?, ?, ?, ?)",
                    (key, json.dumps(payload, default=str), _now().isoformat(), ttl_seconds),
                )
        except sqlite3.Error as exc:
            logger.error("Cache write failed for %s: %s", key, exc)

    def get_or_fetch(self, key: str, ttl_seconds: int, loader: Callable[[], Any]) -> Any:
        """Serve from cache within TTL; on loader failure fall back to
        last-known-good stale data (FR-ING-5) before giving up."""
        cached = self.get(key)
        if cached is not None:
            logger.debug("Cache hit: %s", key)
            return cached
        try:
            fresh = loader()
        except Exception as exc:
            stale = self.get(key, allow_stale=True)
            if stale is not None:
                logger.warning(
                    "Loader failed for %s (%s); serving last-known-good stale data", key, exc
                )
                return stale
            raise
        self.put(key, fresh, ttl_seconds)
        return fresh

    # ------------------------------------------------------------ read model
    def upsert_event(self, event_id: str, tca: str, risk: str,
                     urgency: float, document: dict) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO events (event_id, tca, risk, urgency, document, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (event_id, tca, risk, urgency,
                     json.dumps(document, default=str), _now().isoformat()),
                )
        except sqlite3.Error as exc:
            logger.error("Event upsert failed for %s: %s", event_id, exc)

    def list_events(self, limit: int = 100) -> list[dict]:
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT document FROM events ORDER BY urgency DESC LIMIT ?", (limit,)
                ).fetchall()
            return [json.loads(r["document"]) for r in rows]
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            logger.error("Event list read failed: %s", exc)
            return []

    def get_event(self, event_id: str) -> dict | None:
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT document FROM events WHERE event_id = ?", (event_id,)
                ).fetchone()
            return json.loads(row["document"]) if row else None
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            logger.error("Event read failed for %s: %s", event_id, exc)
            return None

    def clear_events(self) -> None:
        try:
            with self._lock, self._connect() as conn:
                conn.execute("DELETE FROM events")
        except sqlite3.Error as exc:
            logger.error("Event clear failed: %s", exc)

    # -------------------------------------------------------- pipeline runs
    def record_run_start(self, agent: str) -> int:
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO pipeline_runs (agent, started_at, status) VALUES (?, ?, 'running')",
                    (agent, _now().isoformat()),
                )
                return int(cur.lastrowid)
        except sqlite3.Error as exc:
            logger.error("Pipeline run insert failed for %s: %s", agent, exc)
            return -1

    def record_run_finish(self, run_id: int, status: str, items: int,
                          error: str | None = None) -> None:
        if run_id < 0:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "UPDATE pipeline_runs SET finished_at = ?, status = ?, items = ?, error = ? "
                    "WHERE id = ?",
                    (_now().isoformat(), status, items, error, run_id),
                )
        except sqlite3.Error as exc:
            logger.error("Pipeline run update failed for #%s: %s", run_id, exc)

    def latest_runs(self) -> dict[str, dict]:
        """Most recent run per agent."""
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT r.* FROM pipeline_runs r "
                    "JOIN (SELECT agent, MAX(id) AS mid FROM pipeline_runs GROUP BY agent) m "
                    "ON r.agent = m.agent AND r.id = m.mid"
                ).fetchall()
            return {r["agent"]: dict(r) for r in rows}
        except sqlite3.Error as exc:
            logger.error("Pipeline run read failed: %s", exc)
            return {}
