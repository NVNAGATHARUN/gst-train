"""Read-only, hash-bound planning workspace projections; no scheduling predicates."""
import base64
import json
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field
from sqlalchemy import and_, or_, select
from .auth import require
from .db import session_dependency
from .decision_support import revision_json
from .models import (AvailabilityComputation, CoordinationComputation, DecisionExplanation,
    OpportunityComputation, PlanRevision, PlanningRun, PlanningSnapshot, PriorityAssessment,
    ValidationReport, AuditEvent, PlanningSchedule, PlanComparison, ControllerDecision,
    ExecutionRecord)
from .requests import StrictModel, digest
from .staleness import invalidation_ids
from .freeze_state import execution_pending
from .validation import current_hash, report_json, usability, utc_now

router = APIRouter(prefix='/api/v1')
staff = require('ADMIN', 'PLANNER', 'CONTROLLER', 'AUDITOR')


class SnapshotSummary(StrictModel):
    id: uuid.UUID
    content_hash: str
    created_at: AwareDatetime
    horizon_start: AwareDatetime
    horizon_end: AwareDatetime
    track_ids: list[str]
    scenario_id: str | None
    source_scope: str


class SnapshotPage(StrictModel):
    items: list[SnapshotSummary]
    next_cursor: str | None


class RunSummary(StrictModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    created_at: AwareDatetime
    planner_type: str
    job_status: str
    solver_status: str | None
    has_incumbent: bool | None
    revision_ids: list[uuid.UUID]


class RunPage(StrictModel):
    items: list[RunSummary]
    next_cursor: str | None


class AuditItem(StrictModel):
    id: uuid.UUID
    actor: str
    action: str
    entity: str
    data: dict
    created_at: AwareDatetime


class AuditPage(StrictModel):
    items: list[AuditItem]
    next_cursor: str | None


class ReportArtifactIndex(StrictModel):
    revision: dict
    validations: list[dict]
    schedules: list[dict]
    comparisons: list[dict]
    decisions: list[dict]
    execution: list[dict]
    authority: Literal['READ_ONLY_EVIDENCE'] = 'READ_ONLY_EVIDENCE'


class AccessRequirements(StrictModel):
    line_block: Literal['REQUIRED', 'NOT_REQUIRED', 'UNKNOWN']
    power_block: Literal['REQUIRED', 'NOT_REQUIRED', 'UNKNOWN']
    electrical_isolation_zone: str | None
    signalling_requirement: str
    snt_disconnection: Literal['REQUIRED', 'NOT_REQUIRED', 'UNKNOWN']
    provision_status: Literal['NOT_EVIDENCED'] = 'NOT_EVIDENCED'


class Readiness(StrictModel):
    status: Literal['READY', 'CONDITIONAL', 'NOT_READY', 'NOT_ASSESSED']
    scope: Literal['SELECTED_PROPOSAL_CONTEXT'] = 'SELECTED_PROPOSAL_CONTEXT'
    reasons: list[str]
    candidate_ids: list[str]
    selected_candidate_ids: list[str]
    resource_assignments: list[dict]
    predecessor_request_ids: list[str]
    rule_ids: list[str]
    validation_report_id: str | None
    execution_authorized: Literal[False] = False


class DemandItem(StrictModel):
    request_id: str
    revision: int
    lifecycle_status: str
    request: dict
    access_requirements: AccessRequirements
    priority: dict | None
    scheduling_outcome: Literal['SCHEDULED', 'DEFERRED', 'NOT_PLANNED']
    deferred_evidence: dict | None
    readiness: Readiness


class WorkspaceView(StrictModel):
    snapshot: SnapshotSummary
    facts: dict
    current_blockers: list[str]
    source_state: Literal['CURRENT', 'BLOCKED', 'UNKNOWN']
    selected_run: dict | None
    selected_revision: dict | None
    validation: dict | None
    availability: list[dict]
    opportunity: dict | None
    coordination: dict | None
    demands: list[DemandItem]
    explanations: list[dict]
    authority: Literal['SOFTWARE_PROPOSAL_ONLY'] = 'SOFTWARE_PROPOSAL_ONLY'


def scope(snapshot):
    if snapshot.scenario_id:
        return 'ISOLATED_SCENARIO'
    return (snapshot.manifest.get('validation_context') or {}).get('scope', 'UNKNOWN')


def summary(row):
    return dict(id=row.id, content_hash=row.content_hash, created_at=row.created_at,
        horizon_start=row.horizon_start, horizon_end=row.horizon_end,
        track_ids=row.manifest['track_ids'], scenario_id=row.scenario_id, source_scope=scope(row))


def cursor_for(row, filters):
    payload = {'at': row.created_at.isoformat(), 'id': str(row.id), 'query': digest(filters)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def cursor_condition(model, cursor, filters):
    try:
        data = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
        if not isinstance(data, dict) or set(data) != {'at', 'id', 'query'} or data['query'] != digest(filters):
            raise ValueError()
        instant, item_id = datetime.fromisoformat(data['at']), uuid.UUID(data['id'])
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise HTTPException(422, 'INVALID_OR_MISMATCHED_CURSOR')
    return or_(model.created_at < instant, and_(model.created_at == instant, model.id < item_id))


@router.get('/workspace/snapshots', response_model=SnapshotPage)
def snapshots(track_id: str | None = Query(default=None, max_length=100),
        scenario: Literal['ANY', 'SOURCE', 'SCENARIO'] = 'SOURCE',
        limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        user=Depends(staff), db=Depends(session_dependency)):
    filters = {'kind': 'snapshots', 'track_id': track_id, 'scenario': scenario}
    query = select(PlanningSnapshot)
    if track_id:
        query = query.where(PlanningSnapshot.manifest['track_ids'].contains([track_id]))
    if scenario == 'SOURCE': query = query.where(PlanningSnapshot.scenario_id.is_(None))
    if scenario == 'SCENARIO': query = query.where(PlanningSnapshot.scenario_id.is_not(None))
    if cursor: query = query.where(cursor_condition(PlanningSnapshot, cursor, filters))
    rows = db.scalars(query.order_by(PlanningSnapshot.created_at.desc(), PlanningSnapshot.id.desc())
        .limit(limit + 1)).all()
    return {'items': [summary(row) for row in rows[:limit]],
        'next_cursor': cursor_for(rows[limit - 1], filters) if len(rows) > limit else None}


@router.get('/workspace/runs', response_model=RunPage)
def runs(snapshot_id: uuid.UUID, limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        user=Depends(staff), db=Depends(session_dependency)):
    if not db.get(PlanningSnapshot, snapshot_id): raise HTTPException(404, 'SNAPSHOT_NOT_FOUND')
    filters = {'kind': 'runs', 'snapshot_id': str(snapshot_id)}
    query = select(PlanningRun).where(PlanningRun.snapshot_id == snapshot_id)
    if cursor: query = query.where(cursor_condition(PlanningRun, cursor, filters))
    rows = db.scalars(query.order_by(PlanningRun.created_at.desc(), PlanningRun.id.desc()).limit(limit + 1)).all()
    revisions = db.scalars(select(PlanRevision).where(PlanRevision.run_id.in_([r.id for r in rows[:limit]]))
        .order_by(PlanRevision.revision)).all() if rows else []
    items = [{'id': r.id, 'snapshot_id': r.snapshot_id, 'created_at': r.created_at,
        'planner_type': r.planner_type, 'job_status': r.status,
        'solver_status': (r.result or {}).get('solver_status'),
        'has_incumbent': (r.result or {}).get('has_incumbent'),
        'revision_ids': [v.id for v in revisions if v.run_id == r.id]} for r in rows[:limit]]
    return {'items': items, 'next_cursor': cursor_for(rows[limit - 1], filters) if len(rows) > limit else None}


@router.get('/workspace/audit-events', response_model=AuditPage)
def audit_events(action: str | None = Query(default=None, min_length=1, max_length=100),
        entity: str | None = Query(default=None, min_length=1, max_length=100),
        actor: str | None = Query(default=None, min_length=1, max_length=100),
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        user=Depends(staff), db=Depends(session_dependency)):
    filters = {'kind': 'audit-events', 'action': action, 'entity': entity, 'actor': actor}
    query = select(AuditEvent)
    if action: query = query.where(AuditEvent.action == action)
    if entity: query = query.where(AuditEvent.entity == entity)
    if actor: query = query.where(AuditEvent.actor == actor)
    if cursor: query = query.where(cursor_condition(AuditEvent, cursor, filters))
    rows = db.scalars(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)).all()
    items = [{'id': row.id, 'actor': row.actor, 'action': row.action, 'entity': row.entity,
        'data': row.data, 'created_at': row.created_at} for row in rows[:limit]]
    return {'items': items,
        'next_cursor': cursor_for(rows[limit - 1], filters) if len(rows) > limit else None}


@router.get('/workspace/report-artifacts', response_model=ReportArtifactIndex)
def report_artifacts(plan_revision_id: uuid.UUID, user=Depends(staff), db=Depends(session_dependency)):
    revision = db.get(PlanRevision, plan_revision_id)
    if not revision: raise HTTPException(404, 'PLAN_REVISION_NOT_FOUND')
    snapshot = db.get(PlanningSnapshot, revision.snapshot_id)
    run = db.get(PlanningRun, revision.run_id)
    if not snapshot or not run: raise HTTPException(409, 'REPORT_PROVENANCE_INCOMPLETE')
    if digest(revision.content) != revision.plan_hash or digest(snapshot.manifest) != snapshot.content_hash:
        raise HTTPException(409, 'REPORT_PROVENANCE_HASH_MISMATCH')
    reports = db.scalars(select(ValidationReport).where(ValidationReport.plan_revision_id == revision.id)
        .order_by(ValidationReport.checked_at.desc(), ValidationReport.id.desc())).all()
    schedules = db.scalars(select(PlanningSchedule).where(PlanningSchedule.plan_revision_id == revision.id)
        .order_by(PlanningSchedule.created_at.desc(), PlanningSchedule.id.desc())).all()
    comparisons = db.scalars(select(PlanComparison).where(or_(
        PlanComparison.baseline_plan_revision_id == revision.id,
        PlanComparison.railsync_plan_revision_id == revision.id))
        .order_by(PlanComparison.created_at.desc(), PlanComparison.id.desc())).all()
    decisions = db.scalars(select(ControllerDecision).where(ControllerDecision.plan_revision_id == revision.id)
        .order_by(ControllerDecision.created_at.desc(), ControllerDecision.id.desc())).all()
    execution = db.scalars(select(ExecutionRecord).where(ExecutionRecord.plan_revision_id == revision.id)
        .order_by(ExecutionRecord.received_at.desc(), ExecutionRecord.id.desc())).all()
    if any(digest(row.content) != row.content_hash for row in [*schedules, *comparisons]):
        raise HTTPException(409, 'REPORT_ARTIFACT_HASH_MISMATCH')
    return {'revision': {'id': str(revision.id), 'revision': revision.revision,
            'lineage_id': str(revision.lineage_id), 'parent_id': str(revision.parent_id) if revision.parent_id else None,
            'run_id': str(revision.run_id), 'snapshot_id': str(revision.snapshot_id),
            'plan_hash': revision.plan_hash, 'snapshot_hash': revision.snapshot_hash,
            'snapshot_content_hash': snapshot.content_hash, 'planner_type': run.planner_type,
            'run_status': run.status, 'created_by': revision.created_by,
            'created_at': revision.created_at.isoformat(), 'source_scope': scope(snapshot)},
        'validations': [{'id': str(row.id), 'status': row.status, 'validator_version': row.validator_version,
            'plan_hash': row.plan_hash, 'snapshot_hash': row.snapshot_hash,
            'checked_at': row.checked_at.isoformat(), 'result': row.result} for row in reports],
        'schedules': [{'id': str(row.id), 'schedule_type': row.schedule_type,
            'period_start': row.period_start.isoformat(), 'period_end': row.period_end.isoformat(),
            'content_hash': row.content_hash, 'created_at': row.created_at.isoformat(),
            'status': row.content.get('status'), 'counts': row.content.get('counts', {}),
            'authority': row.content.get('authority')} for row in schedules],
        'comparisons': [{'id': str(row.id), 'role': ('BASELINE' if row.baseline_plan_revision_id == revision.id else 'RAILSYNC'),
            'content_hash': row.content_hash, 'created_at': row.created_at.isoformat(),
            'status': row.content.get('status'), 'claim_scope': row.content.get('claim_scope'),
            'saved_claims_permitted': row.content.get('claims_permitted', False),
            'metric_version': row.content.get('metric_version'), 'metrics': row.content.get('metrics', {})} for row in comparisons],
        'decisions': [{'id': str(row.id), 'validation_report_id': str(row.validation_report_id) if row.validation_report_id else None,
            'action': row.action, 'scope': row.scope, 'reason': row.reason,
            'expected_operational_revision': row.expected_operational_revision,
            'resulting_operational_revision': row.resulting_operational_revision,
            'created_at': row.created_at.isoformat()} for row in decisions],
        'execution': [{'id': str(row.id), 'decision_id': str(row.decision_id), 'request_id': row.request_id,
            'candidate_id': row.candidate_id, 'sequence': row.sequence, 'status': row.status,
            'observed_at': row.observed_at.isoformat(), 'received_at': row.received_at.isoformat(),
            'result': row.result} for row in execution], 'authority': 'READ_ONLY_EVIDENCE'}


def access_requirements(payload):
    def boolean(key):
        value = payload.get(key)
        return 'REQUIRED' if value is True else 'NOT_REQUIRED' if value is False else 'UNKNOWN'
    signalling = payload.get('signalling_state', 'UNKNOWN')
    return {'line_block': boolean('block_required'), 'power_block': boolean('power_block_required'),
        'electrical_isolation_zone': payload.get('isolation_zone'),
        'signalling_requirement': signalling,
        'snt_disconnection': ('REQUIRED' if signalling == 'DISCONNECTED' else
            'NOT_REQUIRED' if signalling in ('ANY', 'CONNECTED') else 'UNKNOWN'),
        'provision_status': 'NOT_EVIDENCED'}


def demand_view(request, candidates, plan, report, blockers, assessed, explanation):
    rid = request['id']; payload = request['payload']
    alternatives = [c for c in candidates if rid in c.get('request_ids', [])]
    selected = [c for c in (plan or {}).get('assignments', []) if rid in c.get('request_ids', [])]
    deferred = next((x for x in (plan or {}).get('deferred', []) if x.get('request_id') == rid), None)
    # Readiness is a conservative projection of existing candidate/report evidence.
    # It does not repeat feasibility logic or claim execution readiness.
    reasons = list(blockers)
    if plan is None:
        state = 'NOT_ASSESSED'; reasons.append('NO_SELECTED_PLAN')
    elif blockers:
        unknown = {'CURRENT_SOURCE_STATE_UNKNOWN', 'VALIDATION_CONTEXT_MISSING',
            'DATA_STALE_OR_UNKNOWN', 'VALIDATOR_VERSION_CHANGED'}
        state = 'CONDITIONAL' if any(b in unknown for b in blockers) or report and report['status'] == 'ERROR' else 'NOT_READY'
    elif selected and report and report['usable_for_review']:
        state = 'READY'; reasons.append('SELECTED_ASSIGNMENT_HAS_CURRENT_INDEPENDENT_PASS')
    else:
        state = 'CONDITIONAL'
        reasons.append('INDEPENDENT_CURRENT_PASS_REQUIRED' if selected else 'NO_SELECTED_ASSIGNMENT')
        if not alternatives: reasons.append('NO_GENERATED_CANDIDATE_EVIDENCE')
    priority = None
    if assessed:
        priority = {'method': assessed.method, 'score_basis_points': assessed.score_basis_points,
            'priority_band': assessed.priority_band, 'contributions': assessed.contributions,
            'policy_version': assessed.policy_version, 'assessed_at': assessed.assessed_at.isoformat()}
    return {'request_id': rid, 'revision': request['revision'], 'lifecycle_status': request['status'],
        'request': payload, 'access_requirements': access_requirements(payload), 'priority': priority,
        'scheduling_outcome': 'SCHEDULED' if selected else 'DEFERRED' if deferred else 'NOT_PLANNED',
        'deferred_evidence': deferred,
        'readiness': {'status': state, 'reasons': sorted(set(reasons)),
            'candidate_ids': [c['id'] for c in alternatives],
            'selected_candidate_ids': [c['id'] for c in selected],
            'resource_assignments': [a for c in selected for a in c.get('allocations', [])],
            'predecessor_request_ids': payload.get('predecessors', []),
            'rule_ids': sorted({r for c in selected for r in c.get('rule_ids', [])}),
            'validation_report_id': report['id'] if report else None}}


@router.get('/snapshots/{id}/workspace', response_model=WorkspaceView)
def workspace(id: uuid.UUID, run_id: uuid.UUID | None = None, plan_revision_id: uuid.UUID | None = None,
        user=Depends(staff), db=Depends(session_dependency), now=Depends(utc_now)):
    snapshot = db.get(PlanningSnapshot, id)
    if not snapshot: raise HTTPException(404, 'SNAPSHOT_NOT_FOUND')
    if digest(snapshot.manifest) != snapshot.content_hash: raise HTTPException(409, 'SNAPSHOT_HASH_MISMATCH')
    revision = db.get(PlanRevision, plan_revision_id) if plan_revision_id else None
    if plan_revision_id and not revision: raise HTTPException(404, 'PLAN_REVISION_NOT_FOUND')
    if revision and (revision.snapshot_id != id or run_id and revision.run_id != run_id):
        raise HTTPException(409, 'WORKSPACE_ARTIFACT_MISMATCH')
    run = db.get(PlanningRun, revision.run_id if revision else run_id) if revision or run_id else None
    if (revision or run_id) and not run: raise HTTPException(404, 'RUN_NOT_FOUND')
    if run and run.snapshot_id != id: raise HTTPException(409, 'WORKSPACE_ARTIFACT_MISMATCH')
    if revision and (digest(revision.content) != revision.plan_hash or revision.snapshot_hash != snapshot.content_hash):
        raise HTTPException(409, 'PLAN_HASH_MISMATCH')
    blockers = []
    if invalidation_ids(db, id): blockers.append('SNAPSHOT_INVALIDATED_BY_EVENT')
    if execution_pending(db, snapshot): blockers.append('EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    actual_hash = current_hash(db, snapshot)
    if actual_hash is None: blockers.append('CURRENT_SOURCE_STATE_UNKNOWN')
    elif actual_hash != digest(snapshot.manifest['facts']): blockers.append('OPERATIONAL_STATE_CHANGED')
    context = snapshot.manifest.get('validation_context')
    if not context: blockers.append('VALIDATION_CONTEXT_MISSING')
    elif not datetime.fromisoformat(context['received_at']) <= now < datetime.fromisoformat(context['valid_until']):
        blockers.append('SOURCE_DECLARATIONS_EXPIRED_OR_NOT_YET_VALID')
    report = None
    if revision:
        row = db.scalar(select(ValidationReport).where(ValidationReport.plan_revision_id == revision.id)
            .order_by(ValidationReport.checked_at.desc(), ValidationReport.id.desc()).limit(1))
        if row:
            usable, reasons = usability(db, row, now)
            report = report_json(row, usable, reasons)
            blockers.extend(reasons)
    coordination = opportunity = None
    available = []
    if run and run.config.get('coordination_id'):
        coordination = db.get(CoordinationComputation, uuid.UUID(run.config['coordination_id']))
        if not coordination or coordination.snapshot_id != id: raise HTTPException(409, 'WORKSPACE_ARTIFACT_MISMATCH')
        opportunity = db.get(OpportunityComputation, coordination.opportunity_id)
        if not opportunity or opportunity.snapshot_id != id: raise HTTPException(409, 'WORKSPACE_ARTIFACT_MISMATCH')
        for aid in opportunity.configuration['availability_ids']:
            a = db.get(AvailabilityComputation, uuid.UUID(aid))
            if not a or a.snapshot_id != id: raise HTTPException(409, 'WORKSPACE_ARTIFACT_MISMATCH')
            available.append({'id': str(a.id), 'input_hash': a.input_hash, 'policy': a.policy, 'result': a.result})
    explanations = db.scalars(select(DecisionExplanation).where(DecisionExplanation.plan_revision_id == revision.id)
        .order_by(DecisionExplanation.request_id)).all() if revision else []
    by_request = {x.request_id: x.payload for x in explanations}
    assessments = []
    if opportunity:
        # Use the assessment instant bound to the actual opportunity, never latest-live priority.
        assessments = db.scalars(select(PriorityAssessment).where(PriorityAssessment.snapshot_id == id,
            PriorityAssessment.policy_version == opportunity.configuration['priority_policy_version'],
            PriorityAssessment.assessed_at == datetime.fromisoformat(opportunity.configuration['assessed_at']))).all()
    priorities = {str(a.request_id): a for a in assessments}
    plan = revision.content if revision else run.result if run and run.status == 'COMPLETED' else None
    candidates = coordination.result.get('candidates', []) if coordination else []
    source_state = 'UNKNOWN' if actual_hash is None else 'BLOCKED' if blockers else 'CURRENT'
    return {'snapshot': summary(snapshot), 'facts': snapshot.manifest['facts'],
        'current_blockers': sorted(set(blockers)), 'source_state': source_state,
        'selected_run': ({'id': str(run.id), 'snapshot_id': str(id), 'planner_type': run.planner_type,
            'status': run.status, 'config': run.config, 'result': run.result} if run else None),
        'selected_revision': revision_json(revision) if revision else None, 'validation': report,
        'availability': available,
        'opportunity': ({'id': str(opportunity.id), 'input_hash': opportunity.input_hash,
            'configuration': opportunity.configuration, 'result': opportunity.result} if opportunity else None),
        'coordination': ({'id': str(coordination.id), 'input_hash': coordination.input_hash,
            'configuration': coordination.configuration, 'result': coordination.result} if coordination else None),
        'demands': [demand_view(r, candidates, plan, report, blockers, priorities.get(r['id']), by_request.get(r['id']))
            for r in snapshot.manifest['facts']['requests']],
        'explanations': [x.payload for x in explanations]}
