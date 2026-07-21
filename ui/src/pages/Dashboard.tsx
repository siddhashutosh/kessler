import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ConjunctionList, EventSummary, Track } from "../types";
import EventList from "../components/EventList";
import EventDetailPanel from "../components/EventDetailPanel";
import Globe3D from "../components/Globe3D";

export default function Dashboard() {
  const [list, setList] = useState<ConjunctionList | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [primaryTrack, setPrimaryTrack] = useState<Track | null>(null);
  const [secondaryTrack, setSecondaryTrack] = useState<Track | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadEvents = useCallback(async () => {
    try {
      const data = await api.get<ConjunctionList>("/api/v1/conjunctions?limit=100");
      setList(data);
      setError(null);
      setSelectedId((prev) => prev ?? data.events[0]?.event_id ?? null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load conjunctions");
    }
  }, []);

  useEffect(() => {
    loadEvents();
    const id = setInterval(loadEvents, 60_000);
    return () => clearInterval(id);
  }, [loadEvents]);

  const selected: EventSummary | null = useMemo(
    () => list?.events.find((e) => e.event_id === selectedId) ?? null,
    [list, selectedId],
  );

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const fetchTrack = async (norad: string): Promise<Track | null> => {
      try {
        return await api.get<Track>(
          `/api/v1/satellites/${encodeURIComponent(norad)}/track?minutes=110&step_s=30`,
        );
      } catch {
        return null; // object not in catalogue — keep last-good scene (FR-UI-5)
      }
    };
    (async () => {
      const [p, s] = await Promise.all([
        fetchTrack(selected.sat1.norad_id),
        fetchTrack(selected.sat2.norad_id),
      ]);
      if (!cancelled) {
        setPrimaryTrack(p);
        setSecondaryTrack(s);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  return (
    <div className="dash">
      <div className="left">
        <div className="panel-head">
          <h2>Conjunction events</h2>
          <span className="count">
            {list ? `${list.events.length} tracked` : "loading…"}
          </span>
        </div>
        <EventList
          events={list?.events ?? []}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        {list && <div className="footer-attribution">{list.attribution}</div>}
      </div>

      <div className="scene">
        <Globe3D primary={primaryTrack} secondary={secondaryTrack} />
        <div className="scene-legend">
          <div className="item">
            <span className="swatch" style={{ background: "#59d8ff" }} />
            {primaryTrack?.name ?? "primary orbit"}
          </div>
          <div className="item">
            <span className="swatch" style={{ background: "#ffb454" }} />
            {secondaryTrack?.name ?? "secondary orbit"}
          </div>
          <div className="item">
            <span
              className="swatch"
              style={{ background: "#ff5d5d", height: 8, width: 8, borderRadius: 4 }}
            />
            closest sampled approach
          </div>
        </div>
        <div className="scene-hint">drag to rotate · wheel to zoom · TEME frame, 1 unit = R⊕</div>
        {selectedId && <EventDetailPanel eventId={selectedId} />}
      </div>

      {error && (
        <div className="toast">
          {error}
          <button onClick={loadEvents}>Retry</button>
        </div>
      )}
    </div>
  );
}
