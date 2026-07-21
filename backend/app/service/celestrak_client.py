"""CelesTrak GP (OMM/JSON) client — no auth required (FR-ING-1)."""
from __future__ import annotations

import logging
import time

import httpx

from app.core.exceptions import DataSourceError

logger = logging.getLogger(__name__)

_BASE = "https://celestrak.org/NORAD/elements/gp.php"
_TIMEOUT = 30.0
_RETRIES = 2


class CelestrakClient:
    def fetch_group(self, group: str = "active", limit: int | None = None) -> list[dict]:
        """Fetch an OMM JSON group (e.g. 'active', 'stations', 'last-30-days')."""
        params = {"GROUP": group, "FORMAT": "json"}
        last_error: Exception | None = None
        for attempt in range(_RETRIES + 1):
            try:
                with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                    resp = client.get(_BASE, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                if not isinstance(data, list):
                    raise DataSourceError(
                        "CelesTrak returned unexpected payload shape",
                        detail={"group": group, "type": type(data).__name__},
                    )
                logger.info("CelesTrak: fetched %d OMM records for group=%s", len(data), group)
                return data[:limit] if limit else data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "CelesTrak fetch attempt %d/%d failed for group=%s: %s",
                    attempt + 1, _RETRIES + 1, group, exc,
                )
                if attempt < _RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        raise DataSourceError(
            f"CelesTrak fetch failed for group={group}",
            detail={"cause": str(last_error)},
        ) from last_error
