"use client";

import { useState } from "react";
import Link from "next/link";
import { timeAt, shortId } from "@/lib/api";
import { TaskStages } from "@/components/task-stages";
import { RailIcon } from "@/components/rail-icon";
import type { Focus } from "@/lib/timeline";
import type { WorkspaceView, Candidate } from "@/lib/types";

export function SelectedBlockInspector({ view, focus }: {
  view: WorkspaceView;
  focus: Focus | null;
  onInspect: (focus: Focus) => void;
}) {
  const [tab, setTab] = useState<"why" | "tasks" | "evidence">("why");
  const plan = view.selected_revision?.content ?? view.selected_run?.result;
  const assignments: Candidate[] = plan?.assignments ?? [];
  const selectedAssignment = focus?.kind === "assignment"
    ? assignments.find((assignment) => assignment.id === focus.id) ?? assignments[0]
    : assignments[0];

  if (!selectedAssignment) {
    return (
      <section className="panel selected-block-panel">
        <div className="panel-header"><div><h2>Selected Block Inspector</h2><p>No saved assignment is selected</p></div></div>
        <div className="panel-body text-muted" style={{ padding: "24px 16px", textAlign: "center" }}>
          <p>Select a saved plan revision with assignments to inspect its evidence.</p>
        </div>
      </section>
    );
  }

  const startMs = Date.parse(selectedAssignment.possession_start);
  const endMs = Date.parse(selectedAssignment.possession_end);
  const durationMins = Math.round((endMs - startMs) / 60_000);
  const durationLabel = Number.isFinite(durationMins) && durationMins >= 0 ? `${durationMins} min` : "N/A";
  const requestIds = new Set(selectedAssignment.request_ids);
  const assignedDemands = view.demands.filter((demand) => requestIds.has(demand.request_id));
  const trackLabel = selectedAssignment.track_ids.length ? selectedAssignment.track_ids.join(", ") : "No track recorded";
  const validation = view.validation;
  const validationLabel = validation?.status ?? "NOT RECORDED";
  const reviewUsable = validation?.status === "PASS" && validation.usable_for_review;

  return (
    <section className="panel selected-block-panel" aria-label="Selected block inspector">
      <div className="inspector-hero-header">
        <div className="inspector-eyebrow-row"><span className="inspector-label">SAVED ASSIGNMENT</span><span className="badge-pill-optimized">{selectedAssignment.mode}</span></div>
        <h3 className="inspector-block-title">Block {shortId(selectedAssignment.id)}</h3>
        <div className="inspector-meta-row">
          <span className="meta-chainage">{selectedAssignment.request_ids.length} request(s)</span><span className="meta-sep">|</span>
          <span className="meta-time">{timeAt(selectedAssignment.possession_start)} – {timeAt(selectedAssignment.possession_end)} ({durationLabel})</span>
        </div>
        <div className="inspector-corridor-row"><span>{trackLabel}</span></div>
      </div>

      <div className="inspector-tabs-nav">
        <button type="button" className={`inspector-tab-btn ${tab === "why" ? "tab-active" : ""}`} onClick={() => setTab("why")}>Selection evidence</button>
        <button type="button" className={`inspector-tab-btn ${tab === "tasks" ? "tab-active" : ""}`} onClick={() => setTab("tasks")}>Work items ({assignedDemands.length || selectedAssignment.tasks?.length || 0})</button>
        <button type="button" className={`inspector-tab-btn ${tab === "evidence" ? "tab-active" : ""}`} onClick={() => setTab("evidence")}>Provenance</button>
      </div>

      {tab === "why" && (
        <div className="inspector-tab-content">
          <div className="inspector-highlight-card"><p><strong>Saved optimizer assignment.</strong> The interval, footprint, work list and resources below come from the selected backend plan. Use the comparison and validation screens for evaluated claims.</p></div>
          <div className="inspector-section">
            <h4 className="inspector-section-title">Recorded evidence</h4>
            <div className="key-reasons-list">
              <div className="reason-item"><span className="reason-num">1</span><div><strong>Possession interval</strong><p>{selectedAssignment.possession_start} to {selectedAssignment.possession_end}</p></div></div>
              <div className="reason-item"><span className="reason-num">2</span><div><strong>Covered demand</strong><p>{selectedAssignment.request_ids.length ? selectedAssignment.request_ids.map(shortId).join(", ") : "No request IDs recorded"}</p></div></div>
              <div className="reason-item"><span className="reason-num">3</span><div><strong>Track footprint</strong><p>{trackLabel}</p></div></div>
              <div className="reason-item"><span className="reason-num">4</span><div><strong>Concrete resources</strong><p>{selectedAssignment.allocations.length ? `${selectedAssignment.allocations.length} saved allocation(s)` : "No resource allocations recorded"}</p></div></div>
            </div>
          </div>
          <div className="inspector-section">
            <div className="section-head-badge"><h4 className="inspector-section-title">Independent validation</h4><span className={reviewUsable ? "validation-pass-pill" : "decision-pending-pill"}>{validationLabel}</span></div>
            <div className="validation-checklist">
              <div className="check-row"><span>Currently usable for review</span><strong>{validation ? (validation.usable_for_review ? "Yes" : "No") : "Not assessed"}</strong></div>
              <div className="check-row"><span>Recorded blockers</span><strong>{validation?.current_blockers.length ?? view.current_blockers.length}</strong></div>
              <div className="check-row"><span>Execution authority</span><strong>{view.authority}</strong></div>
            </div>
          </div>
          <div className="inspector-decision-card"><div className="section-head-badge"><span className="decision-label">Controller workflow</span><span className="decision-pending-pill">HUMAN DECISION</span></div><div className="decision-actions-row"><Link href="/review" className="button button-primary button-full-blue">Open controller review <RailIcon name="arrow" size={14} /></Link></div></div>
        </div>
      )}

      {tab === "tasks" && (
        <div className="inspector-tab-content"><div className="tasks-list">
          {assignedDemands.length > 0 ? assignedDemands.map((demand) => (
            <div key={demand.request_id} className="task-breakdown-card">
              <div className="task-card-head"><span className={`task-dept-tag dept-${demand.request.department.toLowerCase()}`}>{demand.request.department}</span><strong className="task-issue">{demand.request.issue_type}</strong></div>
              <p className="task-asset">{demand.request.asset_id} · {demand.request.footprint.join(", ")}</p>
              <div className="task-timings"><span>Work: <strong>{demand.request.work_minutes}m</strong></span><span>Setup: <strong>{demand.request.setup_minutes}m</strong></span><span>Restore: <strong>{demand.request.restore_minutes}m</strong></span></div>
            </div>
          )) : selectedAssignment.tasks?.length ? (
            <div className="task-breakdown-card"><div className="task-card-head"><span className="task-dept-tag dept-engineering">SAVED TASKS</span><strong className="task-issue">Assignment stages</strong></div><p className="task-asset">Track: {trackLabel}</p><TaskStages candidate={selectedAssignment} /></div>
          ) : <div className="empty-tasks-note"><p>No task-stage evidence is recorded for this assignment.</p></div>}
        </div></div>
      )}

      {tab === "evidence" && (
        <div className="inspector-tab-content"><div className="evidence-grid-details">
          <div className="evidence-detail-item"><span>Candidate ID</span><strong className="mono">{selectedAssignment.id}</strong></div>
          <div className="evidence-detail-item"><span>Plan authority</span><strong>{view.authority}</strong></div>
          <div className="evidence-detail-item"><span>Assigned tracks</span><strong className="mono">{trackLabel}</strong></div>
          <div className="evidence-detail-item"><span>Coordination mode</span><strong>{selectedAssignment.mode}</strong></div>
          <div className="evidence-detail-item"><span>Rule IDs</span><strong>{selectedAssignment.rule_ids.length ? selectedAssignment.rule_ids.join(", ") : "None recorded"}</strong></div>
          <div className="evidence-detail-item"><span>Snapshot hash</span><strong className="mono">{view.snapshot.content_hash}</strong></div>
        </div></div>
      )}
    </section>
  );
}
