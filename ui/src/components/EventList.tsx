import type { EventSummary } from "../types";

function fmtPc(v: number): string {
  if (v === 0) return "0";
  return v.toExponential(1).replace("e-", "e-");
}

function countdown(tca: string): string {
  const ms = new Date(tca).getTime() - Date.now();
  if (ms <= 0) return "TCA passed";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  if (h >= 48) return `T-${Math.floor(h / 24)}d ${h % 24}h`;
  return `T-${h}h ${String(m).padStart(2, "0")}m`;
}

export default function EventList({
  events,
  selectedId,
  onSelect,
}: {
  events: EventSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="event-list">
      {events.map((e) => (
        <div
          key={e.event_id}
          className={`event-row ${selectedId === e.event_id ? "selected" : ""}`}
          onClick={() => onSelect(e.event_id)}
        >
          <div className={`bar risk-${e.risk}`} />
          <div className="names">
            <div className="pair">
              {e.sat1.name}
              <span className="vs">×</span>
              {e.sat2.name}
            </div>
            <div className="meta">
              <span>Pc {fmtPc(e.pc.value)}</span>
              <span>{(e.miss_distance_m / 1000).toFixed(2)} km</span>
              {e.relative_speed_ms != null && (
                <span>{(e.relative_speed_ms / 1000).toFixed(1)} km/s</span>
              )}
            </div>
          </div>
          <div className="right">
            <span className={`risk-badge risk-${e.risk}`}>{e.risk}</span>
            <div className="countdown">{countdown(e.tca)}</div>
          </div>
        </div>
      ))}
      {events.length === 0 && (
        <div className="loading" style={{ height: 120 }}>
          NO EVENTS
        </div>
      )}
    </div>
  );
}
