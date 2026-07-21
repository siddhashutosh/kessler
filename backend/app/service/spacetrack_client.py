"""Space-Track.org client with a strict rate-limit governor (CON-1).

Space-Track mandates <30 req/min and <300 req/hr, cache-first architecture,
and account-suspension for violations. This client enforces a minimum
inter-request interval and an hourly budget as hard guards.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

import httpx

from app.core.config import settings
from app.core.exceptions import ConfigError, DataSourceError, RateLimitError

logger = logging.getLogger(__name__)

_BASE = "https://www.space-track.org"
_TIMEOUT = 30.0


class SpaceTrackClient:
    MIN_INTERVAL_S = 3.0   # >=3 s between calls -> <20/min (margin under the 30/min cap)
    HOURLY_BUDGET = 250    # margin under the 300/hr cap

    def __init__(self, username: str | None = None, password: str | None = None):
        self._username = username or settings.spacetrack_user
        self._password = password or settings.spacetrack_pass
        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self._request_times: deque[float] = deque()
        self._client: httpx.Client | None = None

    @property
    def enabled(self) -> bool:
        return bool(self._username and self._password)

    # ------------------------------------------------------------ governor
    def _throttle(self) -> None:
        now = time.monotonic()
        while self._request_times and now - self._request_times[0] > 3600:
            self._request_times.popleft()
        if len(self._request_times) >= self.HOURLY_BUDGET:
            raise RateLimitError(
                "Space-Track hourly request budget exhausted; serving cache only",
                detail={"budget": self.HOURLY_BUDGET},
            )
        wait = self.MIN_INTERVAL_S - (now - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()
        self._request_times.append(self._last_request_ts)

    # ---------------------------------------------------------------- auth
    def _ensure_session(self) -> httpx.Client:
        if not self.enabled:
            raise ConfigError(
                "Space-Track credentials not configured; live mode unavailable"
            )
        if self._client is not None:
            return self._client
        client = httpx.Client(base_url=_BASE, timeout=_TIMEOUT, follow_redirects=True)
        try:
            resp = client.post(
                "/ajaxauth/login",
                data={"identity": self._username, "password": self._password},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            client.close()
            raise DataSourceError(
                "Space-Track login failed", detail={"cause": str(exc)}
            ) from exc
        logger.info("Space-Track: authenticated as %s", self._username)
        self._client = client
        return client

    def _query(self, path: str) -> list[dict]:
        with self._lock:
            self._throttle()
            client = self._ensure_session()
            try:
                resp = client.get(path)
                if resp.status_code == 401:  # session expired -> one re-login
                    logger.info("Space-Track session expired; re-authenticating")
                    self._client = None
                    client = self._ensure_session()
                    resp = client.get(path)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise DataSourceError(
                    "Space-Track query failed",
                    detail={"path": path, "cause": str(exc)},
                ) from exc
        if not isinstance(data, list):
            raise DataSourceError(
                "Space-Track returned unexpected payload shape", detail={"path": path}
            )
        return data

    # ------------------------------------------------------------- queries
    def fetch_cdm_public(self, limit: int = 200) -> list[dict]:
        """Latest public conjunction messages, soonest TCA first."""
        rows = self._query(
            f"/basicspacedata/query/class/cdm_public/orderby/TCA asc/limit/{limit}/format/json"
        )
        logger.info("Space-Track: fetched %d cdm_public rows", len(rows))
        return rows

    def fetch_gp(self, norad_ids: list[str]) -> list[dict]:
        """GP/OMM elements for a comma-delimited batch (Space-Track guidance)."""
        ids = ",".join(sorted(set(norad_ids)))
        rows = self._query(
            f"/basicspacedata/query/class/gp/NORAD_CAT_ID/{ids}/format/json"
        )
        logger.info("Space-Track: fetched %d GP rows for %d ids", len(rows), len(norad_ids))
        return rows

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
