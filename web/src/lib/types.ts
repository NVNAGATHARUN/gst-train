export type Department = "ENGINEERING" | "TRD" | "SNT";
export type SessionUser = { id: string; name: string; role: string; department: Department | null };
export type BrowserSession = { user: SessionUser; expires_at: string; csrf_token: string; authentication: string };
export type Page<T> = { items: T[]; next_cursor?: string | null; next_offset?: number | null };
export type SourceScope = "SIMULATED" | "IMPORTED" | "ISOLATED_SCENARIO" | "UNKNOWN";
export type SnapshotSummary = {
  id: string; content_hash: string; created_at: string; horizon_start: string;
  horizon_end: string; track_ids: string[]; scenario_id: string | null; source_scope: SourceScope;
};
export type AccessRequirement = "REQUIRED" | "NOT_REQUIRED" | "UNKNOWN";
export type AccessRequirements = {
  line_block: AccessRequirement; power_block: AccessRequirement;
  electrical_isolation_zone: string | null; signalling_requirement: string;
  snt_disconnection: AccessRequirement; provision_status: "NOT_EVIDENCED";
};
export type Readiness = {
  status: "READY" | "CONDITIONAL" | "NOT_READY" | "NOT_ASSESSED";
  scope: "SELECTED_PROPOSAL_CONTEXT"; reasons: string[]; candidate_ids: string[];
  selected_candidate_ids: string[]; resource_assignments: Allocation[];
  predecessor_request_ids: string[]; rule_ids: string[];
  validation_report_id: string | null; execution_authorized: false;
};
export type RequirementPayload = {
  department: Department; asset_id: string; footprint: string[]; issue_type: string;
  description: string; severity: number; urgency: number; criticality: number;
  impact: number; work_minutes: number; setup_minutes: number; restore_minutes: number;
  earliest_at: string; deadline_at: string; deadline_kind: string; mandatory: boolean;
  block_required: boolean; power_block_required: boolean; isolation_zone: string | null;
  power_state: string; signalling_state: string; requirements: Array<{type:string;quantity:number;qualification:string|null}>;
  predecessors: string[]; source_mode: "SIMULATED" | "IMPORTED";
};
export type MaintenanceRequest = { id: string; revision: number; status: string; created_at: string; data: RequirementPayload };
export type ImportPreview = {id:string;hash:string;valid:Array<{external_id:string;source_revision:number;data:RequirementPayload}>;errors:Array<{row:number;code:string;message:string}>};
export type ImportResult = {request_ids:string[];applied:number;duplicates:number;quarantined:number};
export type ImportBatchSummary = {id:string;source:"TMS"|"SMMS"|"TDMS";hash:string;state:"PREVIEWED"|"COMMITTED";valid_count:number;error_count:number;result:ImportResult|null};
export type SourceRecord = {id:string;source:"TMS"|"SMMS"|"TDMS";external_id:string;source_revision:number;payload_hash:string;request_id:string;department:Department};
export type CoverageDeclaration = {source:"OCCUPANCY"|"COA"|"FREIGHT"|"NETWORK"|"REQUESTS"|"RESOURCES"|"COMMITMENTS";track_id:string|null;start_at:string;end_at:string;complete:boolean;evidence_reference:string};
export type SnapshotDetail = {facts_hash:string;id:string;content_hash:string;created_at:string;manifest:{schema_version:number;horizon_start:string;horizon_end:string;track_ids:string[];scenario_id:string|null;require_freight_forecast:boolean;counts:Record<string,number>;facts:{requests:Array<Record<string,unknown>>;occupancy:Array<Record<string,unknown>>;coa:Array<Record<string,unknown>>;freight:Array<Record<string,unknown>>;network:Array<Record<string,unknown>>;resources:Array<Record<string,unknown>>;[key:string]:Array<Record<string,unknown>>};validation_context?:{scope:"SIMULATED"|"IMPORTED";facts_hash:string;received_at:string;valid_until:string;coverage:CoverageDeclaration[];coa_semantics:"ACCESS_ENVELOPE"|"TRAFFIC_FREE"|"UNKNOWN";clearance_before_minutes:number;clearance_after_minutes:number;protect_freight_envelope:boolean;commitments_known_empty:boolean;rule_reference:string}}};
export type Demand = {
  request_id: string; revision: number; lifecycle_status: string; request: RequirementPayload;
  access_requirements: AccessRequirements; priority: null | {
    method: string; score_basis_points: number; priority_band: string;
    contributions: Record<string, number>; policy_version: string;
  };
  scheduling_outcome: "SCHEDULED" | "DEFERRED" | "NOT_PLANNED";
  deferred_evidence: null | { reason: string; [key: string]: unknown };
  readiness: Readiness;
};
export type Occupancy = { id: string; train_id: string; track_id: string; enter_at: string; exit_at: string; timing_source: string; source_mode: string };
export type Window = { id: string; track_ids: string[]; start_at: string; end_at: string; usable_minutes: number };
export type CoaWindow = { id: string; external_id: string; track_id: string; start_at: string; end_at: string; source_mode: string; source_revision?:number };
export type Freight = { id: string; external_id: string; track_id: string; start_at: string; end_at: string; expected_count: number; uncertainty_semantics: string; source_mode: string };
export type NetworkRecord = { id: string; kind: string; payload: Record<string, unknown> };
export type Allocation = { request_id: string; resource_id: string; resource_type: string; track_id: string; start_at: string; end_at: string };
export type TaskStage = {
  request_id: string; request_revision?: number; department: Department; issue_type: string; setup_start: string;
  setup_end: string; work_start: string; work_end: string; restore_start: string;
  restore_end: string; track_ids: string[];
};
export type Candidate = {
  id: string; request_ids: string[]; track_ids: string[]; possession_start: string;
  possession_end: string; mode: string; tasks: TaskStage[]; allocations: Allocation[];
  rule_ids: string[]; costs?: Record<string, number>;
};
export type ScheduleAssignment = Candidate & {
  commitment_status: "FIRM" | "TENTATIVE" | "REQUIRES_ATTENTION";
  reservation_scope: string | null;
  forecast_coverage_status: "DECLARED_COMPLETE" | "UNKNOWN_OR_INCOMPLETE";
};
export type PlanningSchedule = {
  id: string; plan_revision_id: string; schedule_type: "WEEKLY" | "MONTHLY";
  timezone: string; period_start: string; period_end: string; content_hash: string; created_at: string; duplicate: boolean;
  content: {
    schema_version: number; schedule_type: "WEEKLY" | "MONTHLY"; timezone: string;
    period: {local_start:string;local_end_exclusive:string;start_at:string;end_at:string;duration_minutes:number;calendar_days:number};
    status:string;authority:"SOFTWARE_PROPOSAL_ONLY";
    plan_revision:{id:string;revision:number;plan_hash:string;snapshot_hash:string};
    validation:{report_id:string|null;status:string;currently_usable:boolean;blockers:string[]};
    controller_decision:{id:string;action:string;scope:string}|null;
    uncertainty:{data_valid_until:string|null;freight_coverage_declared_until_by_track:Record<string,string|null>};
    assignments:ScheduleAssignment[];deferred:Array<{request_id:string;reason:string}>;
    counts:{assignments:number;tasks:number;firm:number;tentative:number;requires_attention:number;deferred:number};
    generated_at:string;planning_method:string;
  };
};
export type WhatIfScenario = {
  id:string;duplicate:boolean;source_snapshot_id:string;snapshot_id:string;content_hash:string;
  payload:{name:string;changes:Array<Record<string,unknown>>;changes_hash:string;source_snapshot_hash:string;scenario_snapshot_hash:string;controller_approval:"FORBIDDEN";worker_status:string;candidate_count?:Record<string,number>};
  baseline_run:{id:string;status:string};optimized_run:{id:string;status:string};authority:"ISOLATED_SIMULATION_ONLY";approval_permitted:false;
};
export type WhatIfImpact = {id:string;scenario_id:string;content_hash:string;created_at:string;authority:"ISOLATED_SIMULATION_ONLY";claims_permitted:false;content:{
  comparison_type:string;claim_scope:string;changed_inputs:Array<Record<string,unknown>>;
  source:{snapshot_id:string;plan_revision_id:string;plan_hash:string;validation_report_id:string};
  scenario:{snapshot_id:string;plan_revision_id:string;plan_hash:string;validation_report_id:string};
  observed_differences:Record<string,{unit:string;source:number|null;scenario:number|null;raw_delta:number|null;status:string}>;limits:string[];
}};
export type ReplanPreview = {source_plan_revision_id:string;source_snapshot_id:string;batch_generation:number;ready_at:string;base_facts_hash:string;
  events:Array<{event_id:string;kind:string;matches:Array<Record<string,unknown>>;status:string}>;blockers:string[];status:string;prepared_replan_id?:string;authority:string};
export type DisruptionRecord = {id:string;scope:"SIMULATED";kind:string;payload:Record<string,unknown>;payload_hash:string;occurred_at:string;received_at:string;
  result:{status:string;batch_generation:number;ready_at:string;invalidated_snapshot_ids:string[];superseded_run_ids:string[];operational_revision:number;source_facts_applied:false;authority:string};duplicate:boolean};
export type RollingReplan = {id:string;duplicate:boolean;payload_hash:string;payload:{events:ReplanPreview["events"];source_snapshot_hash:string;base_facts_hash:string;snapshot_hash:string;worker_status:string;controller_approval:"REQUIRED"};capture_id:string;snapshot_id:string;baseline_run:{id:string;status:string};optimized_run:{id:string;status:string};authority:string};
export type PlanResult = {
  solver_status?: string; has_incumbent?: boolean; assignments?: Candidate[];
  selected_candidate_ids?: string[];
  deferred?: Array<{request_id:string;reason:string}>; objective_value?: number;
  best_bound?: number; wall_time_seconds?: number; branches?: number;
  conflicts?: number; counts?: Record<string, number>;
  [key: string]: unknown;
};
export type ValidationFinding = {category:string;status:"FAIL"|"ERROR";code:string;evidence:Record<string,unknown>};
export type ValidationCheck = {category:string;status:"PASS"|"FAIL"|"ERROR"|"NOT_RUN";findings:ValidationFinding[]};
export type ValidationReport = {
  id: string; plan_revision_id:string|null; run_id:string; status: "PASS" | "FAIL" | "ERROR"; usable_for_review: boolean;
  current_blockers: string[]; checked_at: string; plan_hash:string; snapshot_hash:string;
  result: {checks?:ValidationCheck[];validator_version?:string;checks_performed?:number;scope?:string;authority?:string};
};
export type WorkspaceView = {
  snapshot: SnapshotSummary; facts: {
    occupancy: Occupancy[]; coa: CoaWindow[]; freight: Freight[]; network: NetworkRecord[];
    resources?: Array<Record<string,unknown>>;
    requests: Array<{id:string;revision:number;status:string;payload:RequirementPayload}>;
    commitments?: Array<Record<string, unknown>>;
    released_possessions?: Array<Record<string, unknown>>;
  };
  current_blockers: string[]; source_state: "CURRENT" | "BLOCKED" | "UNKNOWN";
  selected_run: null | {id:string;planner_type:string;status:string;config:Record<string,unknown>;result:PlanResult|null};
  selected_revision: null | {id:string;revision:number;plan_hash:string;content:PlanResult;authority:string};
  validation: ValidationReport | null;
  availability: Array<{id:string;policy:Record<string,unknown>;result:{windows:Window[];excluded:Array<Record<string,unknown>>;source_conflicts:Array<Record<string,unknown>>;rounding?:Record<string,string>;counts?:Record<string,number>}}>;
  opportunity: null | {id:string;result:{candidates:Candidate[];exclusions:Array<Record<string,unknown>>}};
  coordination: null | {id:string;result:{status:string;candidates:Candidate[];exclusions:Array<Record<string,unknown>>;counts:Record<string,number>}};
  demands: Demand[]; explanations: Array<Record<string,unknown>>; authority: "SOFTWARE_PROPOSAL_ONLY";
};
export type PlanningRunSummary = {
  id: string; planner_type: "BASELINE" | "CP_SAT"; status: string;
  solver_status: string | null; has_incumbent: boolean | null; result_hash: string | null;
};
export type PlanningSession = {
  id: string; snapshot_id: string; status: string; preparation_status: string;
  runs: PlanningRunSummary[]; artifacts: {coordination_id?:string;opportunity_id?:string;availability_ids?:string[];priority_count?:number;candidate_count?:Record<string,number>};
  error: null | {code?:string;detail?:string}; request_hash:string; created_at:string;
  validation:string; authority:string;
};
export type PlanningRun = { id:string; snapshot_id:string; planner_type:string; status:string; result:PlanResult|null; result_hash:string|null };
export type RunIndexItem = {id:string;snapshot_id:string;created_at:string;planner_type:string;job_status:string;solver_status:string|null;has_incumbent:boolean|null;revision_ids:string[]};
export type ComparisonMetric = {unit:string;formula:string;direction:string;baseline:number|null;railsync:number|null;raw_delta:number|null;favorable_change:number|null;percent_change:number|null;improvement_percent:number|null;status:string};
export type ComparisonSide = {plan_revision_id:string;plan_hash:string;planner:string;status:string;usable:boolean;blockers:string[];schedule_status:string|null;solver_status:string|null;metrics:Record<string,number|string|boolean|null|Record<string,unknown>>;computation_error:string|null;quality:Record<string,unknown>};
export type PlanComparison = {id:string;content_hash:string;created_at:string;current_claims_permitted:boolean;metric_version_current:boolean;current_validation:{baseline:{status:string;usable:boolean;blockers:string[]};railsync:{status:string;usable:boolean;blockers:string[]}};content:{status:string;claims_permitted:boolean;claim_scope:string;snapshot_id:string;snapshot_hash:string;metric_version:string;horizon:{horizon_start:string;horizon_end:string;track_ids:string[]};baseline:ComparisonSide;railsync:ComparisonSide;metrics:Record<string,ComparisonMetric>;limits:string[]}};

export type ControllerDecision = {id:string;plan_revision_id:string;action:"APPROVE"|"REJECT"|"REPLAN";scope:string;created_at:string;resulting_operational_revision:number};
export type ExecutionRevision = {id:string;revision:number;snapshot_id:string;plan_hash:string;content:{assignments?:Candidate[];deferred?:Array<{request_id:string;reason:string}>};decisions:ControllerDecision[];current_state:{status:string;disruption_event_ids:string[]}};
export type FreezeCommitment = {candidate_id:string;assignment_hash:string;plan_revision_id:string;decision_id:string;frozen:boolean;reasons:string[];blockers:string[]};
export type FreezeContext = {scope:string;operational_revision:number;checked_at:string;status:string;policy:null|{id:string;revision:number;freeze_minutes:number};commitments:FreezeCommitment[]};
export type ExecutionRecord = {id:string;plan_revision_id:string;decision_id:string;request_id:string;candidate_id:string;assignment_hash:string;scope:string;sequence:number;status:"STARTED"|"INTERRUPTED"|"RESUMED"|"COMPLETED";observed_at:string;received_at:string;payload:{remaining_work_minutes:number|null;evidence_reference:string;note:string;[key:string]:unknown};result:{authority:string;execution_authorized:false;reservations_released:false;source_plan_stale:boolean;outside_planned_work_interval:boolean;remaining_work_known:boolean;requires_execution_aware_replan:boolean;operational_revision:number;track_ids:string[];resource_ids:string[];continuation?:Record<string,unknown>};duplicate:boolean};
export type ExecutionRecordList = {plan_revision_id:string;items:ExecutionRecord[]};
export type SavedExecutionArtifact = {id:string;payload_hash:string;payload:Record<string,unknown>;result:Record<string,unknown>;created_at:string};
export type DifferenceAssignment = {candidate_id:string;assignment_hash:string;possession_start:string;possession_end:string;work_start:string;work_end:string;track_ids:string[];resource_ids:string[]};
export type RevisionDifferenceItem = {request_id:string;change:string;before:DifferenceAssignment|null;after:DifferenceAssignment|null;work_start_shift_minutes:number|null;source_deferred_reason?:string|null;replacement_deferred_reason?:string|null};
export type RevisionDifference = {plan_revision_id:string;content_hash:string;payload:{version:string;capture_id:string;capture_hash:string;source_plan_revision_id:string;source_decision_id:string;source_plan_hash:string;replacement_snapshot_id:string;replacement_plan_hash:string;changes:RevisionDifferenceItem[];counts:Record<string,number>;authority:string}};
export type AuditEvent = {id:string;actor:string;action:string;entity:string;data:Record<string,unknown>;created_at:string};
export type AuditEventPage = {items:AuditEvent[];next_cursor:string|null};
export type ReportArtifactIndex = {revision:{id:string;revision:number;lineage_id:string;parent_id:string|null;run_id:string;snapshot_id:string;plan_hash:string;snapshot_hash:string;snapshot_content_hash:string;planner_type:string;run_status:string;created_by:string;created_at:string;source_scope:string};
  validations:Array<{id:string;status:string;validator_version:string;plan_hash:string;snapshot_hash:string;checked_at:string;result:Record<string,unknown>}>;
  schedules:Array<{id:string;schedule_type:string;period_start:string;period_end:string;content_hash:string;created_at:string;status:string|null;counts:Record<string,number>;authority:string|null}>;
  comparisons:Array<{id:string;role:"BASELINE"|"RAILSYNC";content_hash:string;created_at:string;status:string|null;claim_scope:string|null;saved_claims_permitted:boolean;metric_version:string|null;metrics:Record<string,ComparisonMetric>}>;
  decisions:Array<{id:string;validation_report_id:string|null;action:string;scope:string;reason:string;expected_operational_revision:number;resulting_operational_revision:number;created_at:string}>;
  execution:Array<{id:string;decision_id:string;request_id:string;candidate_id:string;sequence:number;status:string;observed_at:string;received_at:string;result:Record<string,unknown>}>;
  authority:"READ_ONLY_EVIDENCE"};
