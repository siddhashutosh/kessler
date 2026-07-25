"""Space-Track.org client — strict rate governor, persistent session, and a
circuit breaker (CON-1).

Space-Track suspends accounts for over-frequent logins/queries. This client:
  * persists the login cookie to disk so process restarts do NOT re-login;
  * rate-limits logins themselves (not just queries);
  * opens a circuit breaker on auth failure that survives a fresh login
    (the suspension signature) and stops all live calls for a long cooldown,
    so a bad state can never turn into a request storm.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.exceptions import ConfigError, DataSourceError, RateLimitError

logger = logging.getLogger(__name__)

_BASE = "https://www.space-track.org"
_TIMEOUT = 30.0


class SpaceTrackClient:
    MIN_INTERVAL_S = 6.0            # >=6 s between queries -> <10/min (generous margin)
    HOURLY_BUDGET = 100            # far under the 300/hr cap
    MIN_LOGIN_INTERVAL_S = 1800    # never log in more than once per 30 min
    SESSION_MAX_AGE_S = 3600 * 3   # reuse a persisted cookie for up to 3 h
    SUSPENSION_COOLDOWN_S = 3600 * 24   # on suspension signature, stand down 24 h
    AUTH_FAIL_COOLDOWN_S = 3600 * 2     # on a plain auth failure, back off 2 h

    def __init__(self, username: str | None = None, password: str | None = None):
        self._username = username or settings.spacetrack_user
        self._password = password or settings.spacetrack_pass
        self._lock = threading.Lock()
        self._last_request_ts = 0.0
        self._request_times: deque[float] = deque()
        self._client: httpx.Client | None = None
        self._state_file = Path(settings.data_dir) / "spacetrack_state.json"
        self._state = self._load_state()

    @property
    def enabled(self) -> bool:
        return bool(self._username and self._password)

    # -------------------------------------------------------- persisted state
    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"cookies": {}, "saved_at": 0.0, "last_login": 0.0,
                    "circuit_until": 0.0}

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps(self._state), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not persist Space-Track state: %s", exc)

    def _circuit_open(self) -> float:
        """Seconds remaining on the circuit breaker (0 if closed)."""
        return max(0.0, self._state.get("circuit_until", 0.0) - time.time())

    def _open_circuit(self, seconds: float, reason: str) -> None:
        self._state["circuit_until"] = time.time() + seconds
        self._save_state()
        self._client = None
        logger.error("Space-Track circuit OPEN for %.0f h — %s",
                     seconds / 3600, reason)

    # ------------------------------------------------------------ governor
    def _throttle(self) -> None:
        now = time.monotonic()
        while self._request_times and now - self._request_times[0] > 3600:
            self._request_times.popleft()
        if len(self._request_times) >= self.HOURLY_BUDGET:
            raise RateLimitError("Space-Track hourly budget exhausted; serving cache")
        wait = self.MIN_INTERVAL_S - (now - self._last_request_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_request_ts = time.monotonic()
        self._request_times.append(self._last_request_ts)

    # ---------------------------------------------------------------- auth
    def _client_from_cookies(self) -> httpx.Client | None:
        cookies = self._state.get("cookies") or {}
        age = time.time() - self._state.get("saved_at", 0.0)
        if cookies and age < self.SESSION_MAX_AGE_S:
            return httpx.Client(base_url=_BASE, timeout=_TIMEOUT,
                                follow_redirects=True, cookies=cookies)
        return None

    def _login(self) -> httpx.Client:
        # hard login-rate limit — the original suspension cause was too many logins
        since_login = time.time() - self._state.get("last_login", 0.0)
        if since_login < self.MIN_LOGIN_INTERVAL_S:
            raise RateLimitError(
                "Space-Track login suppressed (too soon since last login); serving cache",
                detail={"seconds_since_login": round(since_login)},
            )
        client = httpx.Client(base_url=_BASE, timeout=_TIMEOUT, follow_redirects=True)
        try:
            resp = client.post("/ajaxauth/login",
                               data={"identity": self._username, "password": self._password})
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            client.close()
            self._open_circuit(self.AUTH_FAIL_COOLDOWN_S, f"login failed: {exc}")
            raise DataSourceError("Space-Track login failed", detail={"cause": str(exc)}) from exc
        self._state["cookies"] = dict(client.cookies)
        self._state["saved_at"] = time.time()
        self._state["last_login"] = time.time()
        self._save_state()
        logger.info("Space-Track: authenticated as %s (login rate-limited to 1/30min)",
                    self._username)
        return client

    def _ensure_session(self) -> httpx.Client:
        if not self.enabled:
            raise ConfigError("Space-Track credentials not configured; live mode unavailable")
        if self._client is not None:
            return self._client
        self._client = self._client_from_cookies() or self._login()
        return self._client

    def _query(self, path: str) -> list[dict]:
        with self._lock:
            remaining = self._circuit_open()
            if remaining > 0:
                raise DataSourceError(
                    "Space-Track live access paused by circuit breaker; serving cache",
                    detail={"cooldown_hours": round(remaining / 3600, 1)},
                )
            self._throttle()
            client = self._ensure_session()
            try:
                resp = client.get(path)
                if resp.status_code == 401:
                    # Could be an expired cookie OR a suspended account. Try ONE
                    # rate-limited re-login; if the query is STILL 401 after a
                    # fresh login, the account itself is the problem — stand down.
                    logger.info("Space-Track 401; attempting one rate-limited re-login")
                    self._client = None
                    self._state["cookies"] = {}  # force real login
                    try:
                        client = self._login()
                        self._client = client
                    except RateLimitError:
                        self._open_circuit(self.AUTH_FAIL_COOLDOWN_S,
                                           "401 with login rate-limited")
                        raise DataSourceError("Space-Track auth unavailable; serving cache")
                    resp = client.get(path)
                    if resp.status_code == 401:
                        self._open_circuit(
                            self.SUSPENSION_COOLDOWN_S,
                            "401 persists after fresh login — account may be suspended; "
                            "contact admin@space-track.org before re-enabling live mode",
                        )
                        raise DataSourceError("Space-Track rejected an authenticated query")
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise DataSourceError("Space-Track query failed",
                                      detail={"path": path, "cause": str(exc)}) from exc
        if not isinstance(data, list):
            raise DataSourceError("Space-Track unexpected payload", detail={"path": path})
        return data

    # ------------------------------------------------------------- queries
    def fetch_cdm_public(self, limit: int = 200) -> list[dict]:
        rows = self._query(
            f"/basicspacedata/query/class/cdm_public/TCA/%3Enow/orderby/TCA asc/limit/{limit}/format/json"
        )
        logger.info("Space-Track: fetched %d cdm_public rows", len(rows))
        return rows

    def fetch_gp(self, norad_ids: list[str]) -> list[dict]:
        ids = ",".join(sorted(set(norad_ids)))
        rows = self._query(f"/basicspacedata/query/class/gp/NORAD_CAT_ID/{ids}/format/json")
        logger.info("Space-Track: fetched %d GP rows for %d ids", len(rows), len(norad_ids))
        return rows

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
