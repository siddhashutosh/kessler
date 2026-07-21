"""Pydantic v2 DTOs — the API contract (mirrored by ui/src/types.ts)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RiskClass = Literal["CRITICAL", "WARNING", "MONITOR", "NEGLIGIBLE"]
PcType = Literal["computed", "max", "reported"]


class PcBlock(BaseModel):
    value: float
    method: str
    pc_type: PcType
    cross_check: float | None = None
    divergence_flag: bool = False


class ObjectSummary(BaseModel):
    norad_id: str
    name: str
    object_type: str = "UNKNOWN"


class EventSummary(BaseModel):
    event_id: str
    tca: datetime
    sat1: ObjectSummary
    sat2: ObjectSummary
    miss_distance_m: float
    relative_speed_ms: float | None = None
    pc: PcBlock
    risk: RiskClass
    urgency: float
    emergency_reportable: bool = False


class EventDetail(EventSummary):
    created: datetime | None = None
    source: str
    covariance_available: bool = False
    miss_rtn_m: list[float] | None = None
    action: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ConjunctionListResponse(BaseModel):
    data_mode: Literal["live", "demo"]
    generated_at: datetime
    attribution: str
    events: list[EventSummary]


class InsightResponse(BaseModel):
    event_id: str
    briefing: str
    source: Literal["ai", "template"]


class TrackPoint(BaseModel):
    t: datetime
    lat: float
    lon: float
    alt_km: float
    r_eci_km: list[float]


class TrackResponse(BaseModel):
    norad_id: str
    name: str
    points: list[TrackPoint]
    omm: dict[str, Any]


class ScreeningRequest(BaseModel):
    norad_id: str
    window_hours: int = Field(default=24, ge=1)
    threshold_km: float = Field(default=10.0, gt=0, le=100)


class CloseApproach(BaseModel):
    secondary: ObjectSummary
    tca: datetime
    miss_distance_m: float
    relative_speed_ms: float
    miss_rtn_m: list[float]
    pc_max: float
    risk: RiskClass


class ScreeningResponse(BaseModel):
    asset: ObjectSummary
    window_hours: int
    threshold_km: float
    screened_objects: int
    candidates: list[CloseApproach]


class PipelineAgent(BaseModel):
    id: str
    name: str
    status: Literal["idle", "running", "ok", "degraded", "error"]
    last_run: datetime | None = None
    duration_ms: int | None = None
    items: int = 0
    error: str | None = None


class PipelineStatusResponse(BaseModel):
    data_mode: Literal["live", "demo"]
    agents: list[PipelineAgent]


class CatalogEntry(BaseModel):
    norad_id: str
    name: str
    object_type: str = "PAYLOAD"
    apogee_km: float
    perigee_km: float
    inclination_deg: float


class HealthResponse(BaseModel):
    status: str
    version: str
    data_mode: Literal["live", "demo"]
    uptime_s: float
