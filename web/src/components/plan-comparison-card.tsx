"use client";

import Link from "next/link";
import { shortId } from "@/lib/api";
import type { WorkspaceView } from "@/lib/types";

function possessionMinutes(start: string, end: string) {
  const value = Math.round((Date.parse(end) - Date.parse(start)) / 60_000);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function PlanComparisonCard({ view }: { view: WorkspaceView }) {
  const plan = view.selected_revision?.content ?? view.selected_run?.result;
  const assignments = plan?.assignments ?? [];
  const requestIds = new Set(assignments.flatMap((assignment) => assignment.request_ids));
  const totalMinutes = assignments.reduce<number | null>((sum, assignment) => {
    const minutes = possessionMinutes(assignment.possession_start, assignment.possession_end);
    return sum === null || minutes === null ? null : sum + minutes;
  }, 0);
  const status = plan?.solver_status ?? view.selected_run?.status ?? "No saved result";

  return (
    <section className="panel plan-comparison-card" aria-label="Selected proposal evidence">
      <div className="comparison-card-header">
        <div className="comparison-header-left">
          <h3>Selected proposal evidence</h3>
          <p>Values below come from the selected saved run or plan revision. Open Baseline comparison for a same-snapshot KPI comparison.</p>
        </div>
        <Link href="/evaluation" className="button button-outline">Open Baseline comparison</Link>
      </div>

      <div className="comparison-metrics-grid">
        <div className="comp-metric-box"><span className="comp-metric-label">Saved assignments</span><div className="comp-metric-values"><strong className="comp-optimized-val">{assignments.length}</strong></div><small className="comp-subtext">Concrete candidates in this proposal</small></div>
        <div className="comp-metric-box"><span className="comp-metric-label">Requests covered</span><div className="comp-metric-values"><strong className="comp-optimized-val">{requestIds.size}</strong></div><small className="comp-subtext">Unique request IDs in saved assignments</small></div>
        <div className="comp-metric-box"><span className="comp-metric-label">Possession minutes</span><div className="comp-metric-values"><strong className="comp-optimized-val">{totalMinutes ?? "N/A"}</strong></div><small className="comp-subtext">Sum of saved possession intervals</small></div>
        <div className="comp-metric-box"><span className="comp-metric-label">Run status</span><div className="comp-metric-values"><strong className="comp-optimized-val">{status}</strong></div><small className="comp-subtext">Reported by the planning backend</small></div>
        <div className="comp-metric-box"><span className="comp-metric-label">Evidence identity</span><div className="comp-metric-values"><strong className="comp-optimized-val mono">{shortId(view.selected_revision?.id ?? view.selected_run?.id)}</strong></div><small className="comp-subtext">Selected revision or run</small></div>
      </div>
    </section>
  );
}
