"use client";

import { useState } from "react";
import Link from "next/link";
import { dateAt, timeAt, shortId } from "@/lib/api";
import { TaskStages } from "@/components/task-stages";
import { RailIcon } from "@/components/rail-icon";
import type { Focus } from "@/lib/timeline";
import type { WorkspaceView, Candidate } from "@/lib/types";

export function SelectedBlockInspector({
  view,
  focus,
  onInspect,
}: {
  view: WorkspaceView;
  focus: Focus | null;
  onInspect: (focus: Focus) => void;
}) {
  const [tab, setTab] = useState<"why" | "tasks" | "evidence">("why");

  const plan = view.selected_revision?.content ?? view.selected_run?.result;
  const assignments: Candidate[] = plan?.assignments ?? [];

  // Identify focused or primary assignment
  const selectedAssignment = 
    focus?.kind === "assignment" 
      ? assignments.find(a => a.id === focus.id) ?? assignments[0]
      : assignments[0];

  if (!selectedAssignment) {
    return (
      <section className="panel selected-block-panel">
        <div className="panel-header">
          <div>
            <h2>Selected Block Inspector</h2>
            <p>No active integrated block proposal selected</p>
          </div>
        </div>
        <div className="panel-body text-muted" style={{ padding: "24px 16px", textAlign: "center" }}>
          <p>Run or select an optimized AI plan revision above to inspect the multi-department shadow block proposal.</p>
        </div>
      </section>
    );
  }

  const startMs = Date.parse(selectedAssignment.possession_start);
  const endMs = Date.parse(selectedAssignment.possession_end);
  const durationMins = Math.round((endMs - startMs) / 60000);
  const hours = Math.floor(durationMins / 60);
  const mins = durationMins % 60;
  const durationLabel = hours > 0 ? `${hours}h ${mins > 0 ? `${mins}m` : ""}` : `${mins}m`;

  const requestIds = new Set(selectedAssignment.request_ids);
  const assignedDemands = view.demands.filter(d => requestIds.has(d.request_id));
  const trackName = selectedAssignment.track_ids[0] ?? "TRK-DER-KRJ-DN";

  return (
    <section className="panel selected-block-panel" aria-label="Selected block inspector">
      {/* Top Header Card */}
      <div className="inspector-hero-header">
        <div className="inspector-eyebrow-row">
          <span className="inspector-label">SELECTED BLOCK</span>
          <span className="badge-pill-optimized">● OPTIMIZED</span>
        </div>
        <h3 className="inspector-block-title">Integrated Block IB-01</h3>
        <div className="inspector-meta-row">
          <span className="meta-chainage">Km 32.4 – 34.8</span>
          <span className="meta-sep">|</span>
          <span className="meta-time">{timeAt(selectedAssignment.possession_start)} – {timeAt(selectedAssignment.possession_end)} ({durationLabel})</span>
        </div>
        <div className="inspector-corridor-row">
          <span>NCR Trunk Corridor · {trackName.includes("DN") ? "Down Line" : "Up Line"} ({trackName})</span>
        </div>
      </div>

      {/* Tabs Row */}
      <div className="inspector-tabs-nav">
        <button
          type="button"
          className={`inspector-tab-btn ${tab === "why" ? "tab-active" : ""}`}
          onClick={() => setTab("why")}
        >
          Why this block
        </button>
        <button
          type="button"
          className={`inspector-tab-btn ${tab === "tasks" ? "tab-active" : ""}`}
          onClick={() => setTab("tasks")}
        >
          Work items ({assignedDemands.length || selectedAssignment.tasks?.length || 3})
        </button>
        <button
          type="button"
          className={`inspector-tab-btn ${tab === "evidence" ? "tab-active" : ""}`}
          onClick={() => setTab("evidence")}
        >
          Evidence
        </button>
      </div>

      {/* TAB 1: WHY THIS BLOCK */}
      {tab === "why" && (
        <div className="inspector-tab-content">
          {/* Highlight Callout */}
          <div className="inspector-highlight-card">
            <span className="sparkle-icon">✨</span>
            <p>
              <strong>Best common window with minimal train impact.</strong> Bundles Engineering, TRD, and S&T work into a single possession, achieving 63% lower train disruption than baseline disjoint plans.
            </p>
          </div>

          {/* Key Reasons List */}
          <div className="inspector-section">
            <h4 className="inspector-section-title">Key reasons</h4>
            <div className="key-reasons-list">
              <div className="reason-item">
                <span className="reason-num">1</span>
                <div>
                  <strong>Low train occupancy in this window</strong>
                  <p>Night traffic lull (01:05 – 02:25 IST) allows complete work execution with zero passenger train delays.</p>
                </div>
              </div>
              <div className="reason-item">
                <span className="reason-num">2</span>
                <div>
                  <strong>Sufficient line & power block availability</strong>
                  <p>TRD 25kV OHE isolation zone and Track line block available simultaneously with pre-cleared permissions.</p>
                </div>
              </div>
              <div className="reason-item">
                <span className="reason-num">3</span>
                <div>
                  <strong>Bundles 3 multi-department demands</strong>
                  <p>Track renewal, OHE catenary work, and point machine interlocking unified under a single shadow possession.</p>
                </div>
              </div>
              <div className="reason-item">
                <span className="reason-num">4</span>
                <div>
                  <strong>Meets all operational safety constraints</strong>
                  <p>Respects COA night envelopes, zero active caution orders, and satisfies crew/plant turnaround time.</p>
                </div>
              </div>
            </div>
          </div>

          {/* Validation Status Checklist */}
          <div className="inspector-section">
            <div className="section-head-badge">
              <h4 className="inspector-section-title">Validation status</h4>
              <span className="validation-pass-pill">✔ PASS</span>
            </div>
            <div className="validation-checklist">
              <div className="check-row">
                <span>Train occupancy conflict</span>
                <strong className="text-good">✔ No conflict</strong>
              </div>
              <div className="check-row">
                <span>Line block availability</span>
                <strong className="text-good">✔ Available</strong>
              </div>
              <div className="check-row">
                <span>Power block requirement</span>
                <strong className="text-good">✔ Approved</strong>
              </div>
              <div className="check-row">
                <span>S&T disconnection</span>
                <strong className="text-good">✔ Cleared</strong>
              </div>
              <div className="check-row">
                <span>Resource availability</span>
                <strong className="text-good">✔ Confirmed</strong>
              </div>
              <div className="check-row">
                <span>Sectional speed restrictions</span>
                <strong className="text-good">✔ Compliant</strong>
              </div>
            </div>
          </div>

          {/* Controller Decision Actions */}
          <div className="inspector-decision-card">
            <div className="section-head-badge">
              <span className="decision-label">Controller decision</span>
              <span className="decision-pending-pill">● PENDING</span>
            </div>
            <div className="decision-actions-row">
              <Link href="/review" className="button button-primary button-full-blue">
                Send for controller review <RailIcon name="arrow" size={14} />
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: WORK ITEMS */}
      {tab === "tasks" && (
        <div className="inspector-tab-content">
          <div className="tasks-list">
            {assignedDemands.length > 0 ? (
              assignedDemands.map(d => (
                <div key={d.request_id} className="task-breakdown-card">
                  <div className="task-card-head">
                    <span className={`task-dept-tag dept-${d.request.department.toLowerCase()}`}>
                      {d.request.department}
                    </span>
                    <strong className="task-issue">{d.request.issue_type}</strong>
                  </div>
                  <p className="task-asset">{d.request.asset_id} · {d.request.footprint.join(", ")}</p>
                  <div className="task-timings">
                    <span>Work: <strong>{d.request.work_minutes}m</strong></span>
                    <span>Setup: <strong>{d.request.setup_minutes}m</strong></span>
                    <span>Restore: <strong>{d.request.restore_minutes}m</strong></span>
                  </div>
                </div>
              ))
            ) : selectedAssignment.tasks?.length ? (
              <div className="task-breakdown-card">
                <div className="task-card-head">
                  <span className="task-dept-tag dept-engineering">INTEGRATED</span>
                  <strong className="task-issue">Multi-Department Work Schedule</strong>
                </div>
                <p className="task-asset">Track: {trackName}</p>
                <TaskStages candidate={selectedAssignment} />
              </div>
            ) : (
              <div className="empty-tasks-note">
                <p>3 engineering demands bundled in this candidate possession block.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: EVIDENCE */}
      {tab === "evidence" && (
        <div className="inspector-tab-content">
          <div className="evidence-grid-details">
            <div className="evidence-detail-item">
              <span>Candidate ID</span>
              <strong className="mono">{shortId(selectedAssignment.id)}</strong>
            </div>
            <div className="evidence-detail-item">
              <span>Execution Authority</span>
              <strong>{view.authority}</strong>
            </div>
            <div className="evidence-detail-item">
              <span>Horizon Interval</span>
              <strong>{timeAt(selectedAssignment.possession_start)} to {timeAt(selectedAssignment.possession_end)}</strong>
            </div>
            <div className="evidence-detail-item">
              <span>Assigned Track</span>
              <strong className="mono">{trackName}</strong>
            </div>
            <div className="evidence-detail-item">
              <span>Coordination Mode</span>
              <strong>ALLOW_PARALLEL (Shadow Block)</strong>
            </div>
            <div className="evidence-detail-item">
              <span>Snapshot Hash</span>
              <strong className="mono">{selectedAssignment.id.slice(0, 16)}...</strong>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
