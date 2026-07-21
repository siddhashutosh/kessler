"""SGP4 propagation utilities (TEME frame) + TCA refinement (FR-SCR-3).

Pure logic: numpy + sgp4 only.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import WGS72, Satrec, jday

from app.core.exceptions import PropagationError

logger = logging.getLogger(__name__)

_EARTH_RADIUS_KM = 6378.137
_DEG = math.pi / 180.0
# SGP4 mean-motion conversion: rev/day -> rad/min
_XPDOTP = 1440.0 / (2.0 * math.pi)


def load_satrec(omm: dict) -> Satrec:
    """Build an sgp4 Satrec from an OMM dict (CelesTrak gp.php JSON fields)."""
    try:
        epoch = datetime.fromisoformat(str(omm["EPOCH"]).replace("Z", "+00:00"))
        if epoch.tzinfo is None:
            epoch = epoch.replace(tzinfo=timezone.utc)
        # sgp4 epoch: days since 1949 December 31 00:00 UT
        base = datetime(1949, 12, 31, tzinfo=timezone.utc)
        epoch_days = (epoch - base).total_seconds() / 86400.0

        sat = Satrec()
        sat.sgp4init(
            WGS72,
            "i",
            int(omm["NORAD_CAT_ID"]),
            epoch_days,
            float(omm.get("BSTAR", 0.0)),
            float(omm.get("MEAN_MOTION_DOT", 0.0)) * 2.0 * math.pi / (1440.0**2),
            float(omm.get("MEAN_MOTION_DDOT", 0.0)) * 2.0 * math.pi / (1440.0**3),
            float(omm["ECCENTRICITY"]),
            float(omm["ARG_OF_PERICENTER"]) * _DEG,
            float(omm["INCLINATION"]) * _DEG,
            float(omm["MEAN_ANOMALY"]) * _DEG,
            float(omm["MEAN_MOTION"]) / _XPDOTP,  # rad/min
            float(omm["RA_OF_ASC_NODE"]) * _DEG,
        )
        return sat
    except (KeyError, ValueError, TypeError) as exc:
        raise PropagationError(
            f"Invalid OMM element set: {exc}", detail={"norad": omm.get("NORAD_CAT_ID")}
        ) from exc


def state_teme(sat: Satrec, t: datetime) -> tuple[np.ndarray, np.ndarray]:
    """Position [km] and velocity [km/s] in TEME at time t (UTC)."""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute, t.second + t.microsecond / 1e6)
    code, r, v = sat.sgp4(jd, fr)
    if code != 0:
        raise PropagationError(
            f"SGP4 error code {code} at {t.isoformat()}",
            detail={"satnum": sat.satnum, "code": code},
        )
    return np.array(r), np.array(v)


def sample_states(
    sat: Satrec, t0: datetime, duration_s: float, step_s: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised state sampling. Returns (offsets_s, r[N,3] km, v[N,3] km/s)."""
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    n = max(2, int(duration_s / step_s) + 1)
    offsets = np.arange(n) * step_s
    jd0, fr0 = jday(t0.year, t0.month, t0.day, t0.hour, t0.minute,
                    t0.second + t0.microsecond / 1e6)
    jd = np.full(n, jd0)
    fr = fr0 + offsets / 86400.0
    codes, r, v = sat.sgp4_array(jd, fr)
    if np.all(codes != 0):
        raise PropagationError(
            f"SGP4 failed across entire window for sat {sat.satnum}",
            detail={"first_code": int(codes[0])},
        )
    bad = codes != 0
    if np.any(bad):
        # mask decayed/err samples with NaN so range math ignores them
        r = r.copy()
        r[bad] = np.nan
    return offsets, r, v


def _range_at(sat_a: Satrec, sat_b: Satrec, t: datetime) -> float:
    ra, _ = state_teme(sat_a, t)
    rb, _ = state_teme(sat_b, t)
    return float(np.linalg.norm(ra - rb))


def refine_tca(
    sat_a: Satrec,
    sat_b: Satrec,
    t_guess: datetime,
    half_window_s: float = 90.0,
    tol_s: float = 0.25,
) -> tuple[datetime, float, float]:
    """Golden-section minimisation of inter-satellite range around t_guess.

    Returns (tca, miss_distance_m, relative_speed_ms); TCA accuracy <= tol_s.
    """
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = -half_window_s, half_window_s

    def f(offset: float) -> float:
        return _range_at(sat_a, sat_b, t_guess + timedelta(seconds=offset))

    c = b - phi * (b - a)
    d = a + phi * (b - a)
    fc, fd = f(c), f(d)
    while (b - a) > tol_s:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = f(d)
    t_offset = 0.5 * (a + b)
    tca = t_guess + timedelta(seconds=t_offset)

    ra, va = state_teme(sat_a, tca)
    rb, vb = state_teme(sat_b, tca)
    miss_m = float(np.linalg.norm(ra - rb)) * 1000.0
    rel_speed_ms = float(np.linalg.norm(va - vb)) * 1000.0
    return tca, miss_m, rel_speed_ms


def rtn_components(r_primary_km: np.ndarray, v_primary_kms: np.ndarray,
                   rel_vector_km: np.ndarray) -> np.ndarray:
    """Express a relative vector in the primary's RTN frame [same units as input]."""
    r_hat = r_primary_km / np.linalg.norm(r_primary_km)
    n_vec = np.cross(r_primary_km, v_primary_kms)
    n_hat = n_vec / np.linalg.norm(n_vec)
    t_hat = np.cross(n_hat, r_hat)
    return np.array([
        float(np.dot(rel_vector_km, r_hat)),
        float(np.dot(rel_vector_km, t_hat)),
        float(np.dot(rel_vector_km, n_hat)),
    ])


def ground_track(sat: Satrec, t0: datetime, minutes: int, step_s: int) -> list[dict]:
    """Sub-satellite points (lat/lon/alt) using spherical Earth + GMST rotation.

    Triage-grade accuracy (no polar motion/nutation) — sufficient for viz.
    """
    points: list[dict] = []
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    for k in range(0, minutes * 60 + 1, step_s):
        t = t0 + timedelta(seconds=k)
        try:
            r, _ = state_teme(sat, t)
        except PropagationError:
            continue  # skip decayed samples, keep the rest of the track
        # GMST (IAU 1982 approximation)
        jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute,
                      t.second + t.microsecond / 1e6)
        tut1 = (jd + fr - 2451545.0) / 36525.0
        gmst_s = 67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * tut1 \
            + 0.093104 * tut1**2 - 6.2e-6 * tut1**3
        gmst = math.fmod(gmst_s * (math.pi / 43200.0) / 240.0 * 240.0, 2.0 * math.pi)
        norm = float(np.linalg.norm(r))
        lat = math.asin(r[2] / norm)
        lon = math.atan2(r[1], r[0]) - gmst
        lon = math.atan2(math.sin(lon), math.cos(lon))  # wrap to [-pi, pi]
        points.append({
            "t": t,
            "lat": math.degrees(lat),
            "lon": math.degrees(lon),
            "alt_km": norm - _EARTH_RADIUS_KM,
            "r_eci_km": [float(r[0]), float(r[1]), float(r[2])],
        })
    return points
