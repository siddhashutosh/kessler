"""Pipeline orchestrator: ingest -> parse -> Pc -> risk -> publish (HLD §2.2).

Stage failures degrade to last-known-good data and mark the agent 'degraded';
the pipeline never aborts the application (FR-ING-5).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import (
    CdmParseError,
    DataSourceError,
    NotFoundError,
    RateLimitError,
    ValidationFailure,
)
from app.logic import risk_engine
from app.logic.cdm_parser import Cdm, parse_cdm_public_row
from app.logic.collision_probability import compute_pc
from app.logic.screening import screen
from app.logic import propagation
from app.service.cache_service import CacheService
from app.service.celestrak_client import CelestrakClient
from app.service.insight_service import InsightService
from app.service.pipeline_service import PipelineService
from app.service.spacetrack_client import SpaceTrackClient

logger = logging.getLogger(__name__)

_ATTRIBUTION = (
    "Orbital data courtesy of Space-Track.org (USSPACECOM) and CelesTrak. "
    "Screening results are triage-grade (SGP4/GP accuracy limits apply)."
)


def _dedupe_cdms(cdms: list[Cdm]) -> list[Cdm]:
    """Collapse duplicate perspectives (A x B / B x A) and superseded updates.

    Space-Track publishes one cdm_public row per object perspective and a new
    row per screening update. Key on the unordered object pair + TCA (rounded
    to the second); keep the most recently CREATED row.
    """
    best: dict[tuple, Cdm] = {}
    for cdm in cdms:
        pair = tuple(sorted((cdm.sat1.designator, cdm.sat2.designator)))
        key = (pair, cdm.tca.replace(microsecond=0))
        current = best.get(key)
        if current is None:
            best[key] = cdm
            continue
        # missing CREATED ranks oldest — a dated row always supersedes it
        oldest = datetime.min.replace(tzinfo=timezone.utc)
        if (cdm.created or oldest) > (current.created or oldest):
            best[key] = cdm
    return list(best.values())


class ConjunctionService:
    def __init__(self):
        self.cache = CacheService(settings.data_dir / "cache.db")
        self.pipeline = PipelineService(self.cache)
        self.celestrak = CelestrakClient()
        self.spacetrack = SpaceTrackClient()
        self.insight = InsightService()
        self._generated_at: datetime | None = None

    # --------------------------------------------------------------- mode
    @property
    def data_mode(self) -> str:
        return "demo" if settings.effective_demo_mode else "live"

    def _load_sample(self, filename: str) -> list[dict]:
        path = Path(settings.data_dir) / filename
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise DataSourceError(
                f"Bundled sample dataset unreadable: {filename}",
                detail={"cause": str(exc)},
            ) from exc

    # ------------------------------------------------------------ ingestion
    def load_catalog(self) -> list[dict]:
        if self.data_mode == "demo":
            return self._load_sample("sample_gp.json")
        return self.cache.get_or_fetch(
            "gp:active",
            settings.gp_ttl_seconds,
            lambda: self.celestrak.fetch_group("active"),
        )

    def load_raw_cdms(self) -> list[dict]:
        if self.data_mode == "demo":
            return self._load_sample("sample_cdms.json")
        return self.cache.get_or_fetch(
            "cdm:latest",
            settings.cdm_ttl_seconds,
            lambda: self.spacetrack.fetch_cdm_public(limit=200),
        )

    # ------------------------------------------------------------- pipeline
    def refresh(self) -> int:
        """Run the full agent pipeline; returns number of published events."""
        logger.info("Pipeline refresh starting (mode=%s)", self.data_mode)

        with self.pipeline.stage("celestrak") as st, self.pipeline.stage("catalog") as st2:
            try:
                catalog = self.load_catalog()
                st["items"] = st2["items"] = len(catalog)
            except (DataSourceError, RateLimitError) as exc:
                logger.warning("Catalog sync degraded: %s", exc)
                st["status"] = st2["status"] = "degraded"
                st2["error"] = str(exc)
                catalog = []

        with self.pipeline.stage("spacetrack") as st, self.pipeline.stage("ingest") as st2:
            try:
                raw_cdms = self.load_raw_cdms()
                st["items"] = st2["items"] = len(raw_cdms)
            except (DataSourceError, RateLimitError) as exc:
                logger.warning("CDM ingest degraded: %s", exc)
                st["status"] = st2["status"] = "degraded"
                st2["error"] = str(exc)
                raw_cdms = []

        cdms: list[Cdm] = []
        with self.pipeline.stage("parser") as st:
            quarantined = 0
            for row in raw_cdms:
                try:
                    cdms.append(parse_cdm_public_row(row))
                except CdmParseError as exc:
                    quarantined += 1
                    logger.warning("CDM quarantined (%s): %s",
                                   row.get("CDM_ID", "?"), exc.detail)
            deduped = len(cdms)
            cdms = _dedupe_cdms(cdms)
            deduped -= len(cdms)
            st["items"] = len(cdms)
            if quarantined:
                st["status"] = "degraded"
                st["error"] = f"{quarantined} record(s) quarantined"
            if deduped:
                logger.info("Parser: collapsed %d duplicate/superseded CDM rows", deduped)

        published = 0
        with self.pipeline.stage("pc") as st_pc, self.pipeline.stage("risk") as st_risk, \
                self.pipeline.stage("publish") as st_pub:
            self.cache.clear_events()
            for cdm in cdms:
                try:
                    document = self._enrich(cdm)
                except Exception as exc:  # single bad event never kills the batch
                    logger.error("Enrichment failed for %s: %s", cdm.cdm_id, exc)
                    continue
                self.cache.upsert_event(
                    document["event_id"], document["tca"], document["risk"],
                    document["urgency"], document,
                )
                published += 1
            st_pc["items"] = st_risk["items"] = st_pub["items"] = published

        self._generated_at = datetime.now(timezone.utc)
        logger.info("Pipeline refresh complete: %d events published", published)
        return published

    def _enrich(self, cdm: Cdm) -> dict:
        pc_result = compute_pc(
            miss_m=cdm.miss_distance_m,
            hbr_m=settings.default_hbr_m,
            r_rel_m=cdm.rel_position_rtn_m,
            v_rel_ms=cdm.rel_velocity_rtn_ms,
            cov1_m2=cdm.sat1.cov_rtn_m2,
            cov2_m2=cdm.sat2.cov_rtn_m2,
            pc_reported=cdm.pc_reported,
        )
        risk = risk_engine.classify(
            pc_result.value, pc_result.pc_type,
            cdm.miss_distance_m, cdm.covariance_available,
        )
        urgency = risk_engine.urgency(risk, cdm.tca, cdm.created)
        action = risk_engine.recommend(risk, cdm.tca, cdm.covariance_available)
        return {
            "event_id": cdm.cdm_id,
            "tca": cdm.tca.isoformat(),
            "created": cdm.created.isoformat() if cdm.created else None,
            "sat1": {
                "norad_id": cdm.sat1.designator,
                "name": cdm.sat1.name,
                "object_type": cdm.sat1.object_type,
            },
            "sat2": {
                "norad_id": cdm.sat2.designator,
                "name": cdm.sat2.name,
                "object_type": cdm.sat2.object_type,
            },
            "miss_distance_m": cdm.miss_distance_m,
            "relative_speed_ms": cdm.relative_speed_ms,
            "pc": {
                "value": pc_result.value,
                "method": pc_result.method,
                "pc_type": pc_result.pc_type,
                "cross_check": pc_result.cross_check,
                "divergence_flag": pc_result.divergence_flag,
            },
            "risk": risk,
            "urgency": urgency,
            "action": action,
            "emergency_reportable": cdm.emergency_reportable,
            "covariance_available": cdm.covariance_available,
            "source": cdm.source,
            "data_mode": self.data_mode,
        }

    # -------------------------------------------------------------- queries
    def list_conjunctions(self, limit: int = 100, min_risk: str | None = None) -> dict:
        events = self.cache.list_events(limit=limit)
        if min_risk:
            order = ["NEGLIGIBLE", "MONITOR", "WARNING", "CRITICAL"]
            if min_risk not in order:
                raise NotFoundError(f"Unknown risk class {min_risk!r}")
            threshold = order.index(min_risk)
            events = [e for e in events if order.index(e["risk"]) >= threshold]
        return {
            "data_mode": self.data_mode,
            "generated_at": (self._generated_at or datetime.now(timezone.utc)).isoformat(),
            "attribution": _ATTRIBUTION,
            "events": events,
        }

    def get_conjunction(self, event_id: str) -> dict:
        event = self.cache.get_event(event_id)
        if event is None:
            raise NotFoundError(f"Conjunction event {event_id!r} not found")
        return event

    def get_insight(self, event_id: str) -> dict:
        event = self.get_conjunction(event_id)
        briefing, source = self.insight.briefing(event)
        return {"event_id": event_id, "briefing": briefing, "source": source}

    # ------------------------------------------------------------ satellites
    def find_omm(self, norad_id: str) -> dict:
        catalog = self.load_catalog()
        for omm in catalog:
            if str(omm.get("NORAD_CAT_ID")) == str(norad_id):
                return omm
        raise NotFoundError(f"NORAD {norad_id} not in loaded catalogue")

    def track(self, norad_id: str, minutes: int, step_s: int) -> dict:
        omm = self.find_omm(norad_id)
        sat = propagation.load_satrec(omm)
        points = propagation.ground_track(
            sat, datetime.now(timezone.utc), minutes, step_s
        )
        return {
            "norad_id": str(norad_id),
            "name": str(omm.get("OBJECT_NAME", "UNKNOWN")),
            "points": points,
            "omm": omm,
        }

    def run_screening(self, norad_id: str, window_hours: int,
                      threshold_km: float) -> dict:
        if window_hours > settings.screening_max_window_hours:
            raise ValidationFailure(
                f"Screening window exceeds {settings.screening_max_window_hours} h limit",
                detail={"requested": window_hours},
            )
        asset_omm = self.find_omm(norad_id)
        catalog = self.load_catalog()
        screened, hits = screen(
            asset_omm, catalog,
            start=datetime.now(timezone.utc),
            window_hours=window_hours,
            threshold_km=threshold_km,
            hbr_m=settings.default_hbr_m,
        )
        return {
            "asset": {
                "norad_id": str(norad_id),
                "name": str(asset_omm.get("OBJECT_NAME", "UNKNOWN")),
                "object_type": str(asset_omm.get("OBJECT_TYPE", "PAYLOAD")),
            },
            "window_hours": window_hours,
            "threshold_km": threshold_km,
            "screened_objects": screened,
            "candidates": [
                {
                    "secondary": {
                        "norad_id": h.norad_id,
                        "name": h.name,
                        "object_type": h.object_type,
                    },
                    "tca": h.tca.isoformat(),
                    "miss_distance_m": h.miss_distance_m,
                    "relative_speed_ms": h.relative_speed_ms,
                    "miss_rtn_m": h.miss_rtn_m,
                    "pc_max": h.pc_max,
                    "risk": risk_engine.classify(h.pc_max, "max",
                                                 h.miss_distance_m, False),
                }
                for h in hits
            ],
        }

    def catalog_summary(self, query: str | None, limit: int) -> list[dict]:
        from app.logic.screening import altitude_band

        results = []
        for omm in self.load_catalog():
            name = str(omm.get("OBJECT_NAME", ""))
            if query and query.upper() not in name.upper() \
                    and query != str(omm.get("NORAD_CAT_ID")):
                continue
            try:
                perigee, apogee = altitude_band(omm)
            except (KeyError, ValueError, ZeroDivisionError):
                continue
            results.append({
                "norad_id": str(omm.get("NORAD_CAT_ID")),
                "name": name,
                "object_type": str(omm.get("OBJECT_TYPE", "PAYLOAD")),
                "apogee_km": round(apogee, 1),
                "perigee_km": round(perigee, 1),
                "inclination_deg": float(omm.get("INCLINATION", 0.0)),
            })
            if len(results) >= limit:
                break
        return results
