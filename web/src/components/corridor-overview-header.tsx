"use client";

import { dateAt, shortId } from "@/lib/api";
import type { WorkspaceView } from "@/lib/types";

export function CorridorOverviewHeader({ view }: { view: WorkspaceView }) {
  const occupancyCount = view.facts.occupancy?.length ?? 0;
  const freightCount = view.facts.freight?.length ?? 0;
  const coaCount = view.facts.coa?.length ?? 0;
  const capacityCount = view.availability.reduce(
    (count, computation) => count + (computation.result.windows?.length ?? 0),
    0,
  );
  const tracks = view.snapshot.track_ids;

  return (
    <section className="corridor-overview-card panel" aria-label="Selected corridor evidence">
      <div className="corridor-overview-meta">
        <div className="corridor-title-group">
          <span className="corridor-eyebrow">SELECTED PLANNING CORRIDOR</span>
          <div className="corridor-main-spec">
            <h2>Snapshot {shortId(view.snapshot.id)}</h2>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">{tracks.length ? tracks.join(", ") : "No tracks recorded"}</span>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">{dateAt(view.snapshot.horizon_start)} – {dateAt(view.snapshot.horizon_end)}</span>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">{view.snapshot.source_scope}</span>
          </div>
        </div>
      </div>

      <div className="corridor-kpi-pills">
        <div className="kpi-pill"><span className="kpi-pill-icon kpi-blue">🚆</span><div className="kpi-pill-content"><strong>{occupancyCount} occupancy records</strong><small>Saved train-section evidence</small></div></div>
        <div className="kpi-pill"><span className="kpi-pill-icon kpi-green">📦</span><div className="kpi-pill-content"><strong>{freightCount} freight records</strong><small>Saved forecast envelopes</small></div></div>
        <div className="kpi-pill"><span className="kpi-pill-icon kpi-amber">⏱️</span><div className="kpi-pill-content"><strong>{coaCount} COA windows</strong><small>Source windows in this snapshot</small></div></div>
        <div className="kpi-pill"><span className="kpi-pill-icon kpi-orange">⚠️</span><div className="kpi-pill-content"><strong>{view.current_blockers.length} current blockers</strong><small>Readiness and freshness evidence</small></div></div>
        <div className="kpi-pill"><span className="kpi-pill-icon kpi-teal">▤</span><div className="kpi-pill-content"><strong>{capacityCount} derived windows</strong><small>Saved availability computation</small></div></div>
      </div>
    </section>
  );
}
