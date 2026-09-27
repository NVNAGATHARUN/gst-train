"use client";

import type { WorkspaceView } from "@/lib/types";

export function CorridorOverviewHeader({ view }: { view: WorkspaceView }) {
  const trainCount = view.facts.occupancy?.length ?? 0;
  const freightCount = view.facts.freight?.length ?? 0;
  const coaCount = view.facts.coa?.length ?? 0;
  
  // Passenger vs Freight calculation from real data
  const paxCount = view.facts.occupancy?.filter(o => !o.train_id.toLowerCase().includes("freight")).length ?? 0;
  const directFreight = trainCount - paxCount;
  const totalFreight = directFreight + freightCount;

  return (
    <div className="corridor-overview-card panel">
      <div className="corridor-overview-meta">
        <div className="corridor-title-group">
          <span className="corridor-eyebrow">CORRIDOR OVERVIEW</span>
          <div className="corridor-main-spec">
            <h2>NCR Trunk Corridor</h2>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">GZB – ALJN</span>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">82.5 km</span>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">Double line</span>
            <span className="corridor-sep">|</span>
            <span className="corridor-spec-item">ELEC (25 kV)</span>
          </div>
        </div>
      </div>

      <div className="corridor-kpi-pills">
        <div className="kpi-pill">
          <span className="kpi-pill-icon kpi-blue">🚆</span>
          <div className="kpi-pill-content">
            <strong>{trainCount > 0 ? `${trainCount} Scheduled trains` : "5 Key Trunk Trains"}</strong>
            <small>{paxCount} Passenger · {totalFreight} Freight</small>
          </div>
        </div>

        <div className="kpi-pill">
          <span className="kpi-pill-icon kpi-green">📦</span>
          <div className="kpi-pill-content">
            <strong>{freightCount > 0 ? `${freightCount} EDFC Envelopes` : "Freight active"}</strong>
            <small>EDFC / WDFC interchange</small>
          </div>
        </div>

        <div className="kpi-pill">
          <span className="kpi-pill-icon kpi-amber">⏱️</span>
          <div className="kpi-pill-content">
            <strong>{coaCount > 0 ? `${coaCount} Active COA slots` : "COA declared"}</strong>
            <small>Night freight gap window</small>
          </div>
        </div>

        <div className="kpi-pill">
          <span className="kpi-pill-icon kpi-orange">⚠️</span>
          <div className="kpi-pill-content">
            <strong>0 Restrictions</strong>
            <small>No active caution order</small>
          </div>
        </div>

        <div className="kpi-pill">
          <span className="kpi-pill-icon kpi-teal">🟢</span>
          <div className="kpi-pill-content">
            <strong>{view.availability?.length ? "Window computed" : "Night Block Ready"}</strong>
            <small>01:00 – 05:00 IST lull</small>
          </div>
        </div>
      </div>
    </div>
  );
}
