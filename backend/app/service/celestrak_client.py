"""CelesTrak GP (OMM/JSON) client — no auth, but IP-rate-limited (FR-ING-1).

CelesTrak blocks IPs (HTTP 403) that fetch too aggressively. This client adds a
minimum inter-request interval and a circuit breaker: on a 403 (block) it stops
all live fetches for a multi-hour cooldown so the pipeline serves cache instead
of hammering a provider that has already said no.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from app.core.exceptions import DataSourceError, RateLimitError

logger = logging.getLogger(__name__)

_BASE = "https://celestrak.org/NORAD/elements/gp.php"
_TIMEOUT = 30.0
_RETRIES = 2
_MIN_INTERVAL_S = 5.0            # polite spacing between CelesTrak calls
_BLOCK_COOLDOWN_S = 3600 * 6     # on a 403 block, stand down 6 h


class CelestrakClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ts = 0.0
        self._circuit_until = 0.0

    def fetch_single(self, norad_id: str) -> dict:
        rows = self._get({"CATNR": str(norad_id), "FORMAT": "json"})
        if not rows:
            raise DataSourceError(
                f"CelesTrak has no GP data for NORAD {norad_id}", detail={"norad": norad_id}
            )
        return rows[0]

    def fetch_group(self, group: str = "active", limit: int | None = None) -> list[dict]:
        data = self._get({"GROUP": group, "FORMAT": "json"})
        logger.info("CelesTrak: fetched %d OMM records for group=%s", len(data), group)
        return data[:limit] if limit else data

    def _get(self, params: dict) -> list[dict]:
        with self._lock:
            remaining = self._circuit_until - time.time()
            if remaining > 0:
                raise DataSourceError(
                    "CelesTrak live access paused by circuit breaker; serving cache",
                    detail={"cooldown_hours": round(remaining / 3600, 1)},
                )
            wait = _MIN_INTERVAL_S - (time.monotonic() - self._last_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_ts = time.monotonic()

            last_error: Exception | None = None
            for attempt in range(_RETRIES + 1):
                try:
                    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                        resp = client.get(_BASE, params=params)
                        if resp.status_code in (403, 429):
                            self._circuit_until = time.time() + _BLOCK_COOLDOWN_S
                            logger.error(
                                "CelesTrak returned %d (IP throttled/blocked); circuit OPEN "
                                "for %d h — serving cache", resp.status_code,
                                _BLOCK_COOLDOWN_S // 3600,
                            )
                            raise RateLimitError("CelesTrak blocked this IP; serving cache")
                        resp.raise_for_status()
                        text = resp.text.strip()
                    if text.startswith("No GP data found"):
                        return []
                    data = resp.json()
                    if not isinstance(data, list):
                        raise DataSourceError("CelesTrak unexpected payload", detail={"params": params})
                    return data
                except RateLimitError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    logger.warning("CelesTrak attempt %d/%d failed (%s): %s",
                                   attempt + 1, _RETRIES + 1, params, exc)
                    if attempt < _RETRIES:
                        time.sleep(1.5 * (attempt + 1))
            raise DataSourceError(f"CelesTrak fetch failed ({params})",
                                  detail={"cause": str(last_error)}) from last_error
