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
    def fetch_single(self, norad_id: str) -> dict:
        """Fetch one object's OMM by catalogue number (covers debris/rocket
        bodies absent from the 'active' group)."""
        rows = self._get({"CATNR": str(norad_id), "FORMAT": "json"})
        if not rows:
            raise DataSourceError(
                f"CelesTrak has no GP data for NORAD {norad_id}",
                detail={"norad": norad_id},
            )
        return rows[0]

    def fetch_group(self, group: str = "active", limit: int | None = None) -> list[dict]:
        """Fetch an OMM JSON group (e.g. 'active', 'stations', 'last-30-days')."""
        data = self._get({"GROUP": group, "FORMAT": "json"})
        logger.info("CelesTrak: fetched %d OMM records for group=%s", len(data), group)
        return data[:limit] if limit else data

    def _get(self, params: dict) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(_RETRIES + 1):
            try:
                with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                    resp = client.get(_BASE, params=params)
                    resp.raise_for_status()
                    text = resp.text.strip()
                # CATNR misses return a plain-text message, not JSON
                if text.startswith("No GP data found"):
                    return []
                data = resp.json()
                if not isinstance(data, list):
                    raise DataSourceError(
                        "CelesTrak returned unexpected payload shape",
                        detail={"params": params, "type": type(data).__name__},
                    )
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "CelesTrak fetch attempt %d/%d failed (%s): %s",
                    attempt + 1, _RETRIES + 1, params, exc,
                )
                if attempt < _RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        raise DataSourceError(
            f"CelesTrak fetch failed ({params})",
            detail={"cause": str(last_error)},
        ) from last_error
