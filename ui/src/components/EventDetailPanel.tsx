import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { EventDetail, Insight } from "../types";

export default function EventDetailPanel({ eventId }: { eventId: string }) {
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setInsight(null);
    api
      .get<EventDetail>(`/api/v1/conjunctions/${encodeURIComponent(eventId)}`)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setDetail(null));
    api
      .get<Insight>(`/api/v1/conjunctions/${encodeURIComponent(eventId)}/insight`)
      .then((i) => !cancelled && setInsight(i))
      .catch(() => !cancelled && setInsight(null));
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  if (!detail) {
    return (
      <aside className="detail-panel">
        <div className="loading" style={{ height: 80 }}>
          LOADING EVENT…
        </div>
      </aside>
    );
  }

  const tca = new Date(detail.tca);

  return (
    <aside className="detail-panel">
      <h3>
        {detail.sat1.name} × {detail.sat2.name}
      </h3>
      <div className="subtitle">
        CDM {detail.event_id} · {detail.sat1.norad_id} vs {detail.sat2.norad_id}
        {detail.emergency_reportable && " · EMERGENCY REPORTABLE"}
      </div>

      <span className={`risk-badge risk-${detail.risk}`}>{detail.risk}</span>

      <div className="kv-grid">
        <div className="kv">
          <div className="k">Collision probability</div>
          <div className="v">{detail.pc.value.toExponential(2)}</div>
        </div>
        <div className="kv">
          <div className="k">Pc method</div>
          <div className="v" style={{ fontSize: 11.5 }}>
            {detail.pc.method}
            <small>({detail.pc.pc_type})</small>
          </div>
        </div>
        <div className="kv">
          <div className="k">Miss distance</div>
          <div className="v">
            {(detail.miss_distance_m / 1000).toFixed(3)}
            <small>km</small>
          </div>
        </div>
        <div className="kv">
          <div className="k">Relative speed</div>
          <div className="v">
            {detail.relative_speed_ms != null
              ? (detail.relative_speed_ms / 1000).toFixed(2)
              : "—"}
            <small>km/s</small>
          </div>
        </div>
        <div className="kv">
          <div className="k">TCA (UTC)</div>
          <div className="v" style={{ fontSize: 11.5 }}>
            {tca.toISOString().slice(0, 19).replace("T", " ")}
          </div>
        </div>
        <div className="kv">
          <div className="k">Urgency</div>
          <div className="v">
            {detail.urgency.toFixed(1)}
            <small>/100</small>
          </div>
        </div>
      </div>

      {detail.pc.pc_type === "max" && (
        <div className="flag-note">
          Pc is a covariance-free upper bound — obtain an operator CDM for
          full-fidelity probability.
        </div>
      )}
      {detail.pc.divergence_flag && (
        <div className="flag-note">
          Foster/Chan cross-check divergence &gt; 5% — treat Pc with caution.
        </div>
      )}

      <div className="action-box">{detail.action}</div>

      {insight && (
        <div className="briefing">
          <div className="src">
            {insight.source === "ai" ? "AI analyst briefing" : "Analyst briefing"}
          </div>
          {insight.briefing}
        </div>
      )}
    </aside>
  );
}
