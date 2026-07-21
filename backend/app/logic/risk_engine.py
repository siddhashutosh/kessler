"""Risk classification, urgency scoring, recommended actions (FR-RSK)."""
from __future__ import annotations

from datetime import datetime, timezone

# Operator-community Pc thresholds (NASA CARA heritage), FR-RSK-1
_CRITICAL = 1e-4
_WARNING = 1e-5
_MONITOR = 1e-7

_ESCALATION_MISS_M = 1000.0  # <1 km miss without covariance escalates one class

_ORDER = ["NEGLIGIBLE", "MONITOR", "WARNING", "CRITICAL"]


def classify(pc: float, pc_type: str, miss_m: float, covariance_available: bool) -> str:
    if pc >= _CRITICAL:
        risk = "CRITICAL"
    elif pc >= _WARNING:
        risk = "WARNING"
    elif pc >= _MONITOR:
        risk = "MONITOR"
    else:
        risk = "NEGLIGIBLE"

    if not covariance_available and miss_m < _ESCALATION_MISS_M:
        idx = _ORDER.index(risk)
        risk = _ORDER[min(idx + 1, len(_ORDER) - 1)]
    return risk


def urgency(risk: str, tca: datetime, created: datetime | None,
            now: datetime | None = None) -> float:
    """0-100 score: base by class + up to 20 for imminent TCA + up to 10 for stale data."""
    now = now or datetime.now(timezone.utc)
    base = {"CRITICAL": 70.0, "WARNING": 45.0, "MONITOR": 20.0, "NEGLIGIBLE": 5.0}[risk]

    hours_to_tca = (tca - now).total_seconds() / 3600.0
    if hours_to_tca <= 0:
        time_score = 0.0  # event passed
    elif hours_to_tca >= 24.0:
        time_score = 2.0
    else:
        time_score = 20.0 * (1.0 - hours_to_tca / 24.0)

    stale_score = 0.0
    if created is not None:
        age_h = (now - created).total_seconds() / 3600.0
        stale_score = min(10.0, max(0.0, (age_h - 8.0) / 4.0))

    return round(min(100.0, base + time_score + stale_score), 1)


def recommend(risk: str, tca: datetime, covariance_available: bool,
              now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    hours = max(0.0, (tca - now).total_seconds() / 3600.0)
    horizon = f"T-{hours:.0f} h" if hours >= 1 else "imminent TCA"

    if risk == "CRITICAL":
        base = ("Treat as actionable: contact secondary operator, request refreshed "
                "operator CDM with covariance, evaluate manoeuvre options")
    elif risk == "WARNING":
        base = "Elevated: request CDM refresh and re-screen every update cycle"
    elif risk == "MONITOR":
        base = "Track: re-screen at next catalogue update"
    else:
        base = "No action required; routine monitoring"

    cov_note = "" if covariance_available else \
        " (Pc is a covariance-free upper bound — obtain operator CDM for full-fidelity Pc)"
    return f"{base} ({horizon}){cov_note}."
