"""REST API (FR-API). All errors surface as the standard envelope via
the global handlers registered in main.py."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Query, Request

from app.core.config import settings
from app.models.schemas import (
    ConjunctionListResponse,
    EventDetail,
    HealthResponse,
    InsightResponse,
    PipelineStatusResponse,
    ScreeningRequest,
    ScreeningResponse,
    TrackResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

_START_TIME = time.monotonic()


def _svc(request: Request):
    return request.app.state.conjunctions


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    return {
        "status": "ok",
        "version": settings.version,
        "data_mode": _svc(request).data_mode,
        "uptime_s": round(time.monotonic() - _START_TIME, 1),
    }


@router.get("/conjunctions", response_model=ConjunctionListResponse)
def list_conjunctions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    min_risk: str | None = Query(default=None),
):
    return _svc(request).list_conjunctions(limit=limit, min_risk=min_risk)


@router.get("/conjunctions/{event_id}", response_model=EventDetail)
def get_conjunction(request: Request, event_id: str):
    return _svc(request).get_conjunction(event_id)


@router.get("/conjunctions/{event_id}/insight", response_model=InsightResponse)
def get_insight(request: Request, event_id: str):
    return _svc(request).get_insight(event_id)


@router.get("/satellites/{norad_id}/track", response_model=TrackResponse)
def get_track(
    request: Request,
    norad_id: str,
    minutes: int = Query(default=100, ge=1, le=360),
    step_s: int = Query(default=30, ge=10, le=300),
):
    return _svc(request).track(norad_id, minutes, step_s)


@router.post("/screening/run", response_model=ScreeningResponse)
def run_screening(request: Request, body: ScreeningRequest):
    return _svc(request).run_screening(
        body.norad_id, body.window_hours, body.threshold_km
    )


@router.get("/pipeline/status", response_model=PipelineStatusResponse)
def pipeline_status(request: Request):
    svc = _svc(request)
    return {"data_mode": svc.data_mode, "agents": svc.pipeline.status()}


@router.post("/pipeline/refresh")
def pipeline_refresh(request: Request, background: BackgroundTasks):
    svc = _svc(request)
    background.add_task(svc.refresh)
    return {"status": "scheduled"}


@router.get("/catalog")
def catalog(
    request: Request,
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return _svc(request).catalog_summary(q, limit)
