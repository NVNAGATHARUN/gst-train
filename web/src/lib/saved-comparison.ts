import type {PlanComparison} from "./types";

/** Bind a persisted comparison to the exact runs shown in the two columns. */
export function comparisonMatchesRuns(comparison:PlanComparison,snapshotId:string,snapshotHash:string,
  baselineRevisionIds:string[],railsyncRevisionIds:string[]):boolean {
  return comparison.content.snapshot_id===snapshotId&&comparison.content.snapshot_hash===snapshotHash&&
    baselineRevisionIds.includes(comparison.content.baseline.plan_revision_id)&&
    railsyncRevisionIds.includes(comparison.content.railsync.plan_revision_id);
}
