# GENERATED from backend/app/logic — edit there, then run packages/sync.py
"""CCSDS Conjunction Data Message parsing (KVN + Space-Track cdm_public JSON).

Pure logic: no I/O, no framework imports. Raises CdmParseError with the full
list of violations (FR-CDM-3).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from dateutil import parser as dtparser

from kessler_toolkit.exceptions import CdmParseError

logger = logging.getLogger(__name__)

# CCSDS 508.0-B-1 RTN covariance keys (position block, m**2)
_COV_KEYS = ["CR_R", "CT_R", "CT_T", "CN_R", "CN_T", "CN_N"]


@dataclass
class CdmObject:
    designator: str
    name: str = "UNKNOWN"
    object_type: str = "UNKNOWN"
    r_rtn_m: np.ndarray | None = None  # position in RTN relative frame [m]
    v_rtn_ms: np.ndarray | None = None
    cov_rtn_m2: np.ndarray | None = None  # 3x3 position covariance [m^2]


@dataclass
class Cdm:
    cdm_id: str
    tca: datetime
    miss_distance_m: float
    sat1: CdmObject
    sat2: CdmObject
    created: datetime | None = None
    relative_speed_ms: float | None = None
    rel_position_rtn_m: np.ndarray | None = None
    rel_velocity_rtn_ms: np.ndarray | None = None
    pc_reported: float | None = None
    emergency_reportable: bool = False
    source: str = "unknown"
    raw: dict = field(default_factory=dict)

    @property
    def covariance_available(self) -> bool:
        return self.sat1.cov_rtn_m2 is not None and self.sat2.cov_rtn_m2 is not None


def _parse_dt(value: str, errors: list[str], label: str) -> datetime | None:
    try:
        dt = dtparser.parse(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        errors.append(f"{label}: unparseable datetime {value!r}")
        return None


def _finite(value, errors: list[str], label: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label}: not numeric ({value!r})")
        return None
    if not math.isfinite(f):
        errors.append(f"{label}: non-finite value")
        return None
    return f


def _validate_covariance(cov: np.ndarray, label: str) -> np.ndarray | None:
    """Symmetrise and check positive semi-definiteness; None if unusable."""
    cov = 0.5 * (cov + cov.T)
    try:
        eigvals = np.linalg.eigvalsh(cov)
    except np.linalg.LinAlgError:
        logger.warning("%s: covariance eigendecomposition failed; dropping", label)
        return None
    if np.any(eigvals < -1e-6 * max(1.0, float(np.max(np.abs(eigvals))))):
        logger.warning("%s: covariance not PSD (eig min %.3e); dropping", label, eigvals.min())
        return None
    return cov


# ---------------------------------------------------------------- KVN format
def parse_cdm_kvn(text: str) -> Cdm:
    """Parse a CCSDS 508.0-B-1 KVN Conjunction Data Message."""
    errors: list[str] = []
    header: dict[str, str] = {}
    objects: dict[str, dict[str, str]] = {"OBJECT1": {}, "OBJECT2": {}}
    current = None

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.split("COMMENT")[0].strip() if raw_line.strip().startswith("COMMENT") else raw_line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().upper(), value.strip()
        # strip trailing units like "[km]"
        if value.endswith("]") and "[" in value:
            value = value[: value.rindex("[")].strip()
        if key == "OBJECT":
            current = value.upper()
            if current not in objects:
                errors.append(f"line {lineno}: unknown OBJECT block {value!r}")
                current = None
            continue
        if current:
            objects[current][key] = value
        else:
            header[key] = value

    tca = _parse_dt(header.get("TCA", ""), errors, "TCA")
    miss = _finite(header.get("MISS_DISTANCE"), errors, "MISS_DISTANCE")
    if miss is None:
        errors.append("MISS_DISTANCE: missing")

    def build_object(block_key: str) -> CdmObject:
        block = objects[block_key]
        designator = block.get("OBJECT_DESIGNATOR", "")
        if not designator:
            errors.append(f"{block_key}: OBJECT_DESIGNATOR missing")
        obj = CdmObject(
            designator=designator or "?",
            name=block.get("OBJECT_NAME", "UNKNOWN"),
            object_type=block.get("OBJECT_TYPE", "UNKNOWN"),
        )
        if all(k in block for k in _COV_KEYS):
            vals = [_finite(block[k], errors, f"{block_key}.{k}") for k in _COV_KEYS]
            if all(v is not None for v in vals):
                cr_r, ct_r, ct_t, cn_r, cn_t, cn_n = vals  # type: ignore[misc]
                cov = np.array(
                    [[cr_r, ct_r, cn_r], [ct_r, ct_t, cn_t], [cn_r, cn_t, cn_n]],
                    dtype=float,
                )
                obj.cov_rtn_m2 = _validate_covariance(cov, block_key)
        return obj

    sat1, sat2 = build_object("OBJECT1"), build_object("OBJECT2")

    rel_r = rel_v = None
    rel_keys_r = ["RELATIVE_POSITION_R", "RELATIVE_POSITION_T", "RELATIVE_POSITION_N"]
    rel_keys_v = ["RELATIVE_VELOCITY_R", "RELATIVE_VELOCITY_T", "RELATIVE_VELOCITY_N"]
    if all(k in header for k in rel_keys_r):
        comps = [_finite(header[k], errors, k) for k in rel_keys_r]
        if all(c is not None for c in comps):
            rel_r = np.array(comps, dtype=float)
    if all(k in header for k in rel_keys_v):
        comps = [_finite(header[k], errors, k) for k in rel_keys_v]
        if all(c is not None for c in comps):
            rel_v = np.array(comps, dtype=float)

    if errors:
        raise CdmParseError("CDM KVN validation failed", detail=errors)
    assert tca is not None and miss is not None  # guaranteed by errors check

    rel_speed = _finite(header.get("RELATIVE_SPEED"), [], "RELATIVE_SPEED")
    if rel_speed is None and rel_v is not None:
        rel_speed = float(np.linalg.norm(rel_v))

    return Cdm(
        cdm_id=header.get("MESSAGE_ID", f"KVN-{tca.isoformat()}"),
        tca=tca,
        miss_distance_m=miss,
        sat1=sat1,
        sat2=sat2,
        created=_parse_dt(header.get("CREATION_DATE", ""), [], "CREATION_DATE"),
        relative_speed_ms=rel_speed,
        rel_position_rtn_m=rel_r,
        rel_velocity_rtn_ms=rel_v,
        source="kvn",
        raw={"header": header},
    )


# ------------------------------------------------- Space-Track cdm_public row
def parse_cdm_public_row(row: dict) -> Cdm:
    """Parse one Space-Track `cdm_public` JSON row.

    Public rows carry no covariance/state vectors — only summary fields
    (CDM_ID, CREATED, TCA, MIN_RNG [km], PC, SAT_1_ID, SAT_1_NAME,
    SAT1_OBJECT_TYPE, SAT_2_*, EMERGENCY_REPORTABLE). Pc falls back to the
    max-Pc path downstream (FR-PC-3).
    """
    errors: list[str] = []
    tca = _parse_dt(str(row.get("TCA", "")), errors, "TCA")

    min_rng_km = _finite(row.get("MIN_RNG"), errors, "MIN_RNG")
    if min_rng_km is None:
        errors.append("MIN_RNG: missing")

    sat1_id = str(row.get("SAT_1_ID") or "").strip()
    sat2_id = str(row.get("SAT_2_ID") or "").strip()
    if not sat1_id:
        errors.append("SAT_1_ID: missing")
    if not sat2_id:
        errors.append("SAT_2_ID: missing")

    if errors:
        raise CdmParseError("cdm_public row validation failed", detail=errors)
    assert tca is not None and min_rng_km is not None

    pc = _finite(row.get("PC"), [], "PC")
    rel_speed_kms = _finite(row.get("REL_SPEED") or row.get("RELATIVE_SPEED"), [], "REL_SPEED")

    return Cdm(
        cdm_id=str(row.get("CDM_ID") or f"ST-{sat1_id}-{sat2_id}-{tca.isoformat()}"),
        tca=tca,
        miss_distance_m=min_rng_km * 1000.0,
        sat1=CdmObject(
            designator=sat1_id,
            name=str(row.get("SAT_1_NAME") or "UNKNOWN"),
            object_type=str(row.get("SAT1_OBJECT_TYPE") or "UNKNOWN"),
        ),
        sat2=CdmObject(
            designator=sat2_id,
            name=str(row.get("SAT_2_NAME") or "UNKNOWN"),
            object_type=str(row.get("SAT2_OBJECT_TYPE") or "UNKNOWN"),
        ),
        created=_parse_dt(str(row.get("CREATED", "")), [], "CREATED"),
        relative_speed_ms=rel_speed_kms * 1000.0 if rel_speed_kms is not None else None,
        pc_reported=pc,
        emergency_reportable=str(row.get("EMERGENCY_REPORTABLE", "N")).upper() in ("Y", "YES", "TRUE", "1"),
        source="spacetrack:cdm_public",
        raw=dict(row),
    )
