// TS mirrors of the backend Pydantic DTOs (LLD §5).

export type RiskClass = "CRITICAL" | "WARNING" | "MONITOR" | "NEGLIGIBLE";
export type PcType = "computed" | "max" | "reported";

export interface PcBlock {
  value: number;
  method: string;
  pc_type: PcType;
  cross_check: number | null;
  divergence_flag: boolean;
}

export interface ObjectSummary {
  norad_id: string;
  name: string;
  object_type: string;
}

export interface EventSummary {
  event_id: string;
  tca: string;
  sat1: ObjectSummary;
  sat2: ObjectSummary;
  miss_distance_m: number;
  relative_speed_ms: number | null;
  pc: PcBlock;
  risk: RiskClass;
  urgency: number;
  emergency_reportable: boolean;
}

export interface EventDetail extends EventSummary {
  created: string | null;
  source: string;
  covariance_available: boolean;
  action: string;
}

export interface ConjunctionList {
  data_mode: "live" | "demo";
  generated_at: string;
  attribution: string;
  events: EventSummary[];
}

export interface Insight {
  event_id: string;
  briefing: string;
  source: "ai" | "template";
}

export interface TrackPoint {
  t: string;
  lat: number;
  lon: number;
  alt_km: number;
  r_eci_km: [number, number, number];
}

export interface Track {
  norad_id: string;
  name: string;
  points: TrackPoint[];
}

export interface PipelineAgent {
  id: string;
  name: string;
  status: "idle" | "running" | "ok" | "degraded" | "error";
  last_run: string | null;
  duration_ms: number | null;
  items: number;
  error: string | null;
}

export interface PipelineStatus {
  data_mode: "live" | "demo";
  agents: PipelineAgent[];
}

export interface Health {
  status: string;
  version: string;
  data_mode: "live" | "demo";
  uptime_s: number;
}
