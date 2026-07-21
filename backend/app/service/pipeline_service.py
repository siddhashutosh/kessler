"""Tracks per-agent pipeline stage status powering the live n8n diagram (FR-UI-3)."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from app.service.cache_service import CacheService

logger = logging.getLogger(__name__)

AGENTS = [
    ("celestrak", "CelesTrak GP"),
    ("spacetrack", "Space-Track CDM"),
    ("catalog", "Catalog Sync"),
    ("ingest", "CDM Ingest"),
    ("parser", "Parser & Validator"),
    ("pc", "Pc Engine"),
    ("risk", "Risk Analyst"),
    ("publish", "Publisher"),
]


class PipelineService:
    def __init__(self, cache: CacheService):
        self._cache = cache

    @contextmanager
    def stage(self, agent_id: str):
        """Context manager recording a stage run; never raises past its scope
        decisions — callers decide fallback, we just record faithfully."""
        run_id = self._cache.record_run_start(agent_id)
        state = {"items": 0}
        try:
            yield state
        except Exception as exc:
            self._cache.record_run_finish(run_id, "error", state["items"], str(exc))
            logger.error("Pipeline stage %s failed: %s", agent_id, exc)
            raise
        else:
            status = state.get("status", "ok")
            self._cache.record_run_finish(run_id, status, state["items"],
                                          state.get("error"))

    def status(self) -> list[dict]:
        runs = self._cache.latest_runs()
        agents = []
        for agent_id, name in AGENTS:
            run = runs.get(agent_id)
            if run is None:
                agents.append({
                    "id": agent_id, "name": name, "status": "idle",
                    "last_run": None, "duration_ms": None, "items": 0, "error": None,
                })
                continue
            status = run["status"] if run["finished_at"] else "running"
            duration_ms = None
            if run["finished_at"]:
                started = datetime.fromisoformat(run["started_at"])
                finished = datetime.fromisoformat(run["finished_at"])
                duration_ms = int((finished - started).total_seconds() * 1000)
            agents.append({
                "id": agent_id,
                "name": name,
                "status": status if status in ("ok", "error", "degraded", "running") else "idle",
                "last_run": run["started_at"],
                "duration_ms": duration_ms,
                "items": run["items"],
                "error": run["error"],
            })
        return agents

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
