"use client";

import type { WorkspaceView, Candidate } from "@/lib/types";

export function CorridorSchematic({ view }: { view: WorkspaceView }) {
  // Extract assignments from active plan revision or completed planning run
  const plan = view.selected_revision?.content ?? view.selected_run?.result;
  const assignments: Candidate[] = plan?.assignments ?? [];
  const blockedTracks = new Set(assignments.flatMap(a => a.track_ids));
  
  // Dynamic section status: true only if an optimized plan has scheduled blocks on this section
  const isSectionActive = (from: string, to: string) => {
    if (assignments.length === 0) return false;
    return Array.from(blockedTracks).some(t => 
      (t.includes(from) && t.includes(to)) || 
      (from === "DER" && to === "KRJ" && (t.includes("DER") || t.includes("KRJ")))
    );
  };

  const derKrjActive = isSectionActive("DER", "KRJ");
  const gzbDerActive = isSectionActive("GZB", "DER");
  const krjAljnActive = isSectionActive("KRJ", "ALJN");

  // Station active status: highlighted only when bounding an active block section
  const isStationActive = (code: string) => {
    if (assignments.length === 0) return false;
    if (derKrjActive && (code === "DER" || code === "KRJ")) return true;
    if (gzbDerActive && (code === "GZB" || code === "DER")) return true;
    if (krjAljnActive && (code === "KRJ" || code === "ALJN")) return true;
    return false;
  };

  // Stations along the NCR Trunk Corridor (GZB - ALJN)
  const stations = [
    { code: "GZB", name: "Ghaziabad Jn", km: "0.0", trains: 12, pax: 8, freight: 4 },
    { code: "DER", name: "Dadri ICD", km: "18.5", trains: 10, pax: 6, freight: 4 },
    { code: "KRJ", name: "Khurja Jn", km: "60.5", trains: 9, pax: 5, freight: 4 },
    { code: "ALJN", name: "Aligarh Jn", km: "82.5", trains: 7, pax: 4, freight: 3 },
  ];

  const sections = [
    { from: "GZB", to: "DER", distance: "18.5 km", track: "SEC-GZB-DER", active: gzbDerActive },
    { from: "DER", to: "KRJ", distance: "42.0 km", track: "SEC-DER-KRJ", active: derKrjActive },
    { from: "KRJ", to: "ALJN", distance: "22.0 km", track: "SEC-KRJ-ALJN", active: krjAljnActive },
  ];

  return (
    <div className="corridor-schematic-card panel">
      <div className="schematic-track-container">
        {/* Track Line Visual with rails */}
        <div className="rail-track-line">
          <div className="rail-steel-top"></div>
          <div className="rail-sleepers"></div>
          <div className="rail-steel-bottom"></div>
        </div>

        {/* Stations & Section Segments */}
        <div className="schematic-nodes-row">
          {stations.map((st) => (
            <div key={st.code} className="schematic-station-col">
              <div className={`station-badge ${isStationActive(st.code) ? "station-active" : ""}`}>
                <strong>{st.code}</strong>
              </div>
              <span className="station-name">{st.name}</span>
              <span className="station-chainage">Km {st.km}</span>
              <div className="station-density">
                <span className="dot-blue">●</span> {st.pax} PAX
                <span className="dot-green" style={{ marginLeft: 6 }}>●</span> {st.freight} FGT
              </div>
            </div>
          ))}
        </div>

        {/* Section distance callouts between stations */}
        <div className="section-distances-overlay">
          {sections.map((sec, idx) => (
            <div 
              key={sec.track} 
              className={`section-distance-pill ${sec.active ? "section-active-pill" : ""}`}
              style={{
                left: idx === 0 ? "17%" : idx === 1 ? "50%" : "83%",
              }}
            >
              <span>{sec.distance}</span>
              {sec.active && <small className="active-tag">● Block Scheduled</small>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
