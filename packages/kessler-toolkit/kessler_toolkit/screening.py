# GENERATED from backend/app/logic — edit there, then run packages/sync.py
"""Catalogue screening: altitude sieve -> coarse scan -> TCA refinement (FR-SCR)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from kessler_toolkit.exceptions import PropagationError
from kessler_toolkit import propagation
from kessler_toolkit.collision_probability import pc_max

logger = logging.getLogger(__name__)

_MU_EARTH = 398600.4418  # km^3/s^2
_EARTH_RADIUS_KM = 6378.137


@dataclass
class CloseApproachHit:
    norad_id: str
    name: str
    object_type: str
    tca: datetime
    miss_distance_m: float
    relative_speed_ms: float
    miss_rtn_m: list[float]
    pc_max: float


def altitude_band(omm: dict) -> tuple[float, float]:
    """(perigee_km, apogee_km) altitude band from mean elements."""
    n_rad_s = float(omm["MEAN_MOTION"]) * 2.0 * math.pi / 86400.0
    a_km = (_MU_EARTH / (n_rad_s**2)) ** (1.0 / 3.0)
    ecc = float(omm["ECCENTRICITY"])
    perigee = a_km * (1.0 - ecc) - _EARTH_RADIUS_KM
    apogee = a_km * (1.0 + ecc) - _EARTH_RADIUS_KM
    return perigee, apogee


def bands_overlap(band_a: tuple[float, float], band_b: tuple[float, float],
                  pad_km: float) -> bool:
    return band_a[0] - pad_km <= band_b[1] and band_b[0] - pad_km <= band_a[1]


def screen(
    asset_omm: dict,
    catalog: list[dict],
    start: datetime,
    window_hours: int,
    threshold_km: float = 10.0,
    hbr_m: float = 20.0,
    coarse_step_s: float = 60.0,
) -> tuple[int, list[CloseApproachHit]]:
    """Screen an asset against the catalogue. Returns (objects_screened, hits)."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    duration_s = window_hours * 3600.0

    asset_sat = propagation.load_satrec(asset_omm)
    asset_band = altitude_band(asset_omm)
    asset_id = str(asset_omm["NORAD_CAT_ID"])

    _, asset_r, asset_v = propagation.sample_states(asset_sat, start, duration_s, coarse_step_s)

    screened = 0
    hits: list[CloseApproachHit] = []
    coarse_gate_km = max(threshold_km * 5.0, 50.0)

    for omm in catalog:
        norad = str(omm.get("NORAD_CAT_ID", ""))
        if norad == asset_id:
            continue
        try:
            band = altitude_band(omm)
        except (KeyError, ValueError, ZeroDivisionError):
            logger.warning("Skipping catalogue object with bad elements: %s", norad)
            continue
        if not bands_overlap(asset_band, band, pad_km=threshold_km + 5.0):
            continue  # FR-SCR-2 sieve

        screened += 1
        try:
            _, obj_r, _ = propagation.sample_states(
                propagation.load_satrec(omm), start, duration_s, coarse_step_s
            )
        except PropagationError as exc:
            logger.warning("Propagation failed for %s: %s", norad, exc.message)
            continue

        n = min(len(asset_r), len(obj_r))
        ranges = np.linalg.norm(asset_r[:n] - obj_r[:n], axis=1)
        if np.all(np.isnan(ranges)):
            continue

        # local minima below the coarse gate (NaN-safe)
        with np.errstate(invalid="ignore"):
            candidates = [
                i for i in range(1, n - 1)
                if ranges[i] == ranges[i] and ranges[i] < coarse_gate_km
                and ranges[i] <= ranges[i - 1] and ranges[i] <= ranges[i + 1]
            ]

        obj_sat = propagation.load_satrec(omm)
        seen_tca: list[datetime] = []
        for idx in candidates:
            t_guess = start + timedelta(seconds=idx * coarse_step_s)
            try:
                tca, miss_m, rel_speed = propagation.refine_tca(
                    asset_sat, obj_sat, t_guess, half_window_s=coarse_step_s * 1.5
                )
            except PropagationError as exc:
                logger.warning("TCA refinement failed for %s: %s", norad, exc.message)
                continue
            if miss_m > threshold_km * 1000.0:
                continue
            if any(abs((tca - prev).total_seconds()) < 30.0 for prev in seen_tca):
                continue  # duplicate minimum from adjacent samples
            seen_tca.append(tca)

            r_a, v_a = propagation.state_teme(asset_sat, tca)
            r_b, _ = propagation.state_teme(obj_sat, tca)
            rtn_km = propagation.rtn_components(r_a, v_a, r_b - r_a)

            hits.append(CloseApproachHit(
                norad_id=norad,
                name=str(omm.get("OBJECT_NAME", "UNKNOWN")),
                object_type=str(omm.get("OBJECT_TYPE", "UNKNOWN")),
                tca=tca,
                miss_distance_m=miss_m,
                relative_speed_ms=rel_speed,
                miss_rtn_m=[c * 1000.0 for c in rtn_km],
                pc_max=pc_max(miss_m, hbr_m),
            ))

    hits.sort(key=lambda h: h.miss_distance_m)
    return screened, hits
