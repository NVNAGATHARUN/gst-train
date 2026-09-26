import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Boolean, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID
from .db import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(24))
    department: Mapped[str | None] = mapped_column(String(24), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class BrowserSession(Base):
    __tablename__ = 'browser_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True)
    credential_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class WorkerHeartbeat(Base):
    __tablename__ = 'worker_heartbeats'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class LoginThrottle(Base):
    __tablename__ = 'login_throttles'
    client_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)

class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="RAISED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class RequestRevision(Base):
    __tablename__ = "request_revisions"
    __table_args__ = (UniqueConstraint("request_id", "revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_requests.id"))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("source", "external_id", "source_revision"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(24))
    external_id: Mapped[str] = mapped_column(String(100))
    source_revision: Mapped[int] = mapped_column(Integer)
    payload_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_requests.id"))

class NetworkEntity(Base):
    __tablename__='network_entities'
    id: Mapped[str] = mapped_column(String(100),primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    revision: Mapped[int] = mapped_column(Integer,default=1)

class NetworkRevision(Base):
    __tablename__='network_revisions'
    __table_args__=(UniqueConstraint('entity_id','revision'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    entity_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'))
    revision: Mapped[int]=mapped_column(Integer)
    payload: Mapped[dict]=mapped_column(JSONB)

class NetworkLink(Base):
    __tablename__='network_links'
    parent_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'),primary_key=True)
    child_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'),primary_key=True)
    relation: Mapped[str]=mapped_column(String(30),primary_key=True)

class Train(Base):
    __tablename__='trains'
    id: Mapped[str]=mapped_column(String(100),primary_key=True)
    name: Mapped[str]=mapped_column(String(120))
    train_type: Mapped[str]=mapped_column(String(24))

class TrainRun(Base):
    __tablename__='train_runs'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    train_id: Mapped[str]=mapped_column(ForeignKey('trains.id'))
    service_date: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    source_mode: Mapped[str]=mapped_column(String(16))
    source_revision: Mapped[int]=mapped_column(Integer)
    payload_hash: Mapped[str]=mapped_column(String(64))

class TrainOccupancy(Base):
    __tablename__='train_occupancies'
    __table_args__=(UniqueConstraint('run_id','route_sequence'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('train_runs.id'))
    track_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'))
    route_sequence: Mapped[int]=mapped_column(Integer)
    enter_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    exit_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    timing_source: Mapped[str]=mapped_column(String(24))

class CoaWindow(Base):
    __tablename__='coa_windows'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    external_id: Mapped[str]=mapped_column(String(100))
    source_revision: Mapped[int]=mapped_column(Integer)
    track_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'))
    start_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    source_mode: Mapped[str]=mapped_column(String(16))
    payload_hash: Mapped[str]=mapped_column(String(64))

class FreightForecast(Base):
    __tablename__='freight_forecasts'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    external_id: Mapped[str]=mapped_column(String(100))
    source_revision: Mapped[int]=mapped_column(Integer)
    track_id: Mapped[str]=mapped_column(ForeignKey('network_entities.id'))
    start_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    expected_count: Mapped[int]=mapped_column(Integer)
    confidence_basis_points: Mapped[int]=mapped_column(Integer)
    uncertainty_semantics: Mapped[str]=mapped_column(String(80))
    source_mode: Mapped[str]=mapped_column(String(16))
    payload_hash: Mapped[str]=mapped_column(String(64))

class PlanningSnapshot(Base):
    __tablename__='planning_snapshots'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    content_hash: Mapped[str]=mapped_column(String(64),unique=True)
    horizon_start: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    horizon_end: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    scenario_id: Mapped[str | None]=mapped_column(String(100),nullable=True)
    manifest: Mapped[dict]=mapped_column(JSONB)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class SnapshotItem(Base):
    __tablename__='snapshot_items'
    __table_args__=(UniqueConstraint('snapshot_id','kind','item_key'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    kind: Mapped[str]=mapped_column(String(40))
    item_key: Mapped[str]=mapped_column(String(160))
    payload: Mapped[dict]=mapped_column(JSONB)

class ResourceUnit(Base):
    __tablename__='resource_units'
    id: Mapped[str]=mapped_column(String(100),primary_key=True)
    resource_type: Mapped[str]=mapped_column(String(60))
    department: Mapped[str | None]=mapped_column(String(24),nullable=True)
    available_start: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    available_end: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    source_mode: Mapped[str]=mapped_column(String(16))

class PlanningRun(Base):
    __tablename__='planning_runs'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    planner_type: Mapped[str]=mapped_column(String(24))
    status: Mapped[str]=mapped_column(String(24),default='QUEUED')
    config: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict | None]=mapped_column(JSONB,nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    completed_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)

class PlanningSession(Base):
    __tablename__ = 'planning_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('planning_snapshots.id'))
    request_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), default='QUEUED_PREPARATION')
    artifacts: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('planning_runs.id'), nullable=True)
    optimized_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('planning_runs.id'), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class PriorityAssessment(Base):
    __tablename__='priority_assessments'
    __table_args__=(UniqueConstraint('snapshot_id','request_id','policy_version','assessed_at'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    request_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[str]=mapped_column(String(40))
    method: Mapped[str]=mapped_column(String(24))
    score_basis_points: Mapped[int]=mapped_column(Integer)
    priority_band: Mapped[str]=mapped_column(String(20))
    features: Mapped[dict]=mapped_column(JSONB)
    contributions: Mapped[dict]=mapped_column(JSONB)
    assessed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))

class ModelExperiment(Base):
    __tablename__='model_experiments'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    algorithm: Mapped[str]=mapped_column(String(24))
    target_definition: Mapped[str]=mapped_column(String(500))
    label_provenance: Mapped[str]=mapped_column(String(40))
    dataset_hash: Mapped[str]=mapped_column(String(64))
    metrics: Mapped[dict]=mapped_column(JSONB)
    evaluation: Mapped[dict]=mapped_column(JSONB)
    status: Mapped[str]=mapped_column(String(24),default='EXPERIMENTAL')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class AvailabilityComputation(Base):
    __tablename__='availability_computations'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    input_hash: Mapped[str]=mapped_column(String(64),unique=True)
    policy: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class OpportunityComputation(Base):
    __tablename__='opportunity_computations'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    input_hash: Mapped[str]=mapped_column(String(64),unique=True)
    configuration: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class CoordinationRevision(Base):
    __tablename__ = 'coordination_revisions'
    __table_args__ = (UniqueConstraint('kind', 'entity_key', 'revision'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(30))
    entity_key: Mapped[str] = mapped_column(String(100))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CoordinationComputation(Base):
    __tablename__ = 'coordination_computations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('planning_snapshots.id'))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('opportunity_computations.id'))
    input_hash: Mapped[str] = mapped_column(String(64), unique=True)
    configuration: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class WorkerLease(Base):
    __tablename__='worker_leases'
    run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'),primary_key=True)
    token: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))

class ValidationReport(Base):
    __tablename__='validation_reports'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    plan_hash: Mapped[str]=mapped_column(String(64))
    snapshot_hash: Mapped[str]=mapped_column(String(64))
    validator_version: Mapped[str]=mapped_column(String(80))
    status: Mapped[str]=mapped_column(String(16))
    checked_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    result: Mapped[dict]=mapped_column(JSONB)
    plan_revision_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey('plan_revisions.id'),nullable=True)

class PlanRevision(Base):
    __tablename__='plan_revisions'
    __table_args__=(UniqueConstraint('lineage_id','revision'),UniqueConstraint('run_id','revision'))
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    lineage_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    revision: Mapped[int]=mapped_column(Integer)
    run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    parent_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey('plan_revisions.id'),nullable=True)
    plan_hash: Mapped[str]=mapped_column(String(64))
    snapshot_hash: Mapped[str]=mapped_column(String(64))
    edit: Mapped[dict]=mapped_column(JSONB,default=dict)
    content: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class DecisionExplanation(Base):
    __tablename__='decision_explanations'
    __table_args__=(UniqueConstraint('plan_revision_id','request_id'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    request_id: Mapped[str]=mapped_column(String(100))
    outcome: Mapped[str]=mapped_column(String(24))
    payload: Mapped[dict]=mapped_column(JSONB)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class OperationalState(Base):
    __tablename__='operational_states'
    scope: Mapped[str]=mapped_column(String(16),primary_key=True)
    revision: Mapped[int]=mapped_column(Integer,default=0)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ControllerDecision(Base):
    __tablename__='controller_decisions'
    __table_args__=(UniqueConstraint('idempotency_key'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    validation_report_id: Mapped[uuid.UUID|None]=mapped_column(ForeignKey('validation_reports.id'),nullable=True)
    action: Mapped[str]=mapped_column(String(24))
    scope: Mapped[str]=mapped_column(String(16))
    expected_operational_revision: Mapped[int]=mapped_column(Integer)
    resulting_operational_revision: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(String(1000))
    actor: Mapped[str]=mapped_column(String(100))
    result: Mapped[dict]=mapped_column(JSONB,default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class PlanReservation(Base):
    __tablename__='plan_reservations'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    decision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('controller_decisions.id'))
    scope: Mapped[str]=mapped_column(String(16))
    track_ids: Mapped[dict]=mapped_column(JSONB)
    resource_ids: Mapped[dict]=mapped_column(JSONB)
    start_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class PlanningSchedule(Base):
    __tablename__='planning_schedules'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    schedule_type: Mapped[str]=mapped_column(String(16))
    timezone_name: Mapped[str]=mapped_column(String(80))
    period_start: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str]=mapped_column(String(64),unique=True)
    content: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class PlanComparison(Base):
    __tablename__='plan_comparisons'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    baseline_plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    railsync_plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    content_hash: Mapped[str]=mapped_column(String(64),unique=True)
    content: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class DisruptionEvent(Base):
    __tablename__='disruption_events'
    __table_args__=(UniqueConstraint('source','external_id','source_revision'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    source: Mapped[str]=mapped_column(String(80))
    external_id: Mapped[str]=mapped_column(String(100))
    source_revision: Mapped[int]=mapped_column(Integer)
    scope: Mapped[str]=mapped_column(String(16))
    kind: Mapped[str]=mapped_column(String(32))
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    actor: Mapped[str]=mapped_column(String(100))

class SnapshotInvalidation(Base):
    __tablename__='snapshot_invalidations'
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'),primary_key=True)
    event_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('disruption_events.id'),primary_key=True)

class ReplanningBatch(Base):
    __tablename__='replanning_batches'
    scope: Mapped[str]=mapped_column(String(16),primary_key=True)
    generation: Mapped[int]=mapped_column(Integer)
    ready_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    latest_event_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('disruption_events.id'))

class EventReconciliation(Base):
    __tablename__='event_reconciliations'
    __table_args__=(UniqueConstraint('source_plan_revision_id','batch_generation'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),unique=True)
    source_plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    batch_generation: Mapped[int]=mapped_column(Integer)
    source_snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    capture_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('replanning_captures.id'))
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    baseline_run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    optimized_run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    payload_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class WhatIfScenario(Base):
    __tablename__='what_if_scenarios'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),unique=True)
    source_snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'))
    snapshot_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_snapshots.id'),unique=True)
    baseline_run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    optimized_run_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('planning_runs.id'))
    content_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class WhatIfImpact(Base):
    __tablename__='what_if_impacts'
    __table_args__=(UniqueConstraint('scenario_id','source_plan_revision_id','scenario_plan_revision_id'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('what_if_scenarios.id'))
    source_plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    scenario_plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    content_hash: Mapped[str]=mapped_column(String(64),unique=True)
    content: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class FreezePolicy(Base):
    __tablename__='freeze_policies'
    __table_args__=(UniqueConstraint('scope','revision'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    scope: Mapped[str]=mapped_column(String(16))
    revision: Mapped[int]=mapped_column(Integer)
    freeze_minutes: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(String(1000))
    actor: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ExecutionRecord(Base):
    __tablename__='execution_records'
    __table_args__=(UniqueConstraint('idempotency_key'),UniqueConstraint('request_id','sequence'))
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True))
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    decision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('controller_decisions.id'))
    request_id: Mapped[str]=mapped_column(String(100))
    candidate_id: Mapped[str]=mapped_column(String(100))
    assignment_hash: Mapped[str]=mapped_column(String(64))
    scope: Mapped[str]=mapped_column(String(16))
    sequence: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(16))
    observed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    payload_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    actor: Mapped[str]=mapped_column(String(100))

class ReplanningCapture(Base):
    __tablename__='replanning_captures'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    plan_revision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_revisions.id'))
    content_hash: Mapped[str]=mapped_column(String(64),unique=True)
    payload: Mapped[dict]=mapped_column(JSONB)
    created_by: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class WorkReconciliation(Base):
    __tablename__='work_reconciliations'
    __table_args__=(UniqueConstraint('execution_record_id','revision'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    execution_record_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('execution_records.id'))
    revision: Mapped[int]=mapped_column(Integer)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),unique=True)
    payload_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    actor: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class PossessionRelease(Base):
    __tablename__='possession_releases'
    __table_args__=(UniqueConstraint('decision_id','candidate_id'),)
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('controller_decisions.id'))
    candidate_id: Mapped[str]=mapped_column(String(100))
    reservation_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('plan_reservations.id'),unique=True)
    idempotency_key: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),unique=True)
    payload_hash: Mapped[str]=mapped_column(String(64))
    payload: Mapped[dict]=mapped_column(JSONB)
    result: Mapped[dict]=mapped_column(JSONB)
    actor: Mapped[str]=mapped_column(String(100))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
