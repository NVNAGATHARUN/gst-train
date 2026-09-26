"""Durable preparation followed by the existing leased baseline and CP-SAT worker.

Preparation is one bounded database transaction. On worker interruption it rolls
back to QUEUED_PREPARATION, so no orphan half-pipeline or artificial progress exists.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, text
from .auth import require
from .db import Session, session_dependency
from .models import PlanningRun, PlanningSession, PlanningSnapshot
from .requests import StrictModel, audit, digest
from .solver import SolverOptions
from .staleness import invalidation_ids, lock_publication
from .freeze_state import execution_pending
from .validation import current_hash, utc_now
from .validation_schema import ValidationContext
from .proposal_pipeline import queue_proposal
from .workspace import cursor_condition, cursor_for

router = APIRouter(prefix='/api/v1')
staff = require('ADMIN', 'PLANNER', 'CONTROLLER', 'AUDITOR')


class PlanningSessionInput(StrictModel):
    idempotency_key: uuid.UUID
    snapshot_id: uuid.UUID
    expected_snapshot_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    solver_options: SolverOptions = Field(default_factory=SolverOptions)


class SessionRunView(StrictModel):
    id: uuid.UUID
    planner_type: str
    status: str
    solver_status: str | None
    has_incumbent: bool | None
    result_hash: str | None


class PlanningSessionView(StrictModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    request_hash: str
    request: PlanningSessionInput
    preparation_status: str
    status: str
    runs: list[SessionRunView]
    artifacts: dict
    error: dict | None
    created_at: datetime
    prepared_at: datetime | None
    duplicate: bool
    authority: str
    validation: str


class PlanningSessionPage(StrictModel):
    items: list[PlanningSessionView]
    next_cursor: str | None


def checked_snapshot(db, payload, now):
    snapshot = db.get(PlanningSnapshot, uuid.UUID(payload['snapshot_id']))
    if not snapshot: raise HTTPException(404, 'SNAPSHOT_NOT_FOUND')
    if snapshot.content_hash != payload['expected_snapshot_hash'] or digest(snapshot.manifest) != snapshot.content_hash:
        raise HTTPException(409, 'SNAPSHOT_HASH_MISMATCH')
    if snapshot.scenario_id: raise HTTPException(409, 'USE_ISOLATED_SCENARIO_WORKFLOW')
    if snapshot.manifest['facts'].get('replanning') or execution_pending(db, snapshot):
        raise HTTPException(409, 'USE_ROLLING_REPLAN_WORKFLOW')
    if invalidation_ids(db, snapshot.id): raise HTTPException(409, 'SNAPSHOT_INVALIDATED_BY_EVENT')
    if current_hash(db, snapshot) != digest(snapshot.manifest['facts']):
        raise HTTPException(409, 'SNAPSHOT_SOURCE_STALE_OR_UNKNOWN')
    context = snapshot.manifest.get('validation_context')
    if not context: raise HTTPException(409, 'VALIDATION_CONTEXT_REQUIRED')
    context = ValidationContext.model_validate(context)
    if (not context.received_at <= now < context.valid_until or not all(c.complete for c in context.coverage)
            or context.coa_semantics == 'UNKNOWN'):
        raise HTTPException(409, 'SOURCE_DECLARATIONS_STALE_OR_INCOMPLETE')
    if context.clearance_before_minutes != context.clearance_after_minutes:
        raise HTTPException(409, 'ASYMMETRIC_CLEARANCE_UNSUPPORTED_BY_RUN_CONTRACT')
    return snapshot, context


def serialize(db, row, duplicate=False):
    if digest(row.payload) != row.request_hash:
        raise HTTPException(409, 'PLANNING_SESSION_HASH_MISMATCH')
    runs = [db.get(PlanningRun, rid) if rid else None for rid in (row.baseline_run_id, row.optimized_run_id)]
    result = []
    for run in runs:
        if run:
            result.append({'id': str(run.id), 'planner_type': run.planner_type, 'status': run.status,
                'solver_status': (run.result or {}).get('solver_status'),
                'has_incumbent': (run.result or {}).get('has_incumbent'),
                'result_hash': digest(run.result) if run.result is not None else None})
    state = row.status
    if state == 'PREPARED':
        if len(result) != 2: raise HTTPException(409, 'PLANNING_SESSION_RUNS_MISSING')
        statuses = {r['status'] for r in result}
        state = ('SUPERSEDED' if 'SUPERSEDED' in statuses else 'FAILED' if 'FAILED' in statuses
            else 'COMPLETED' if statuses == {'COMPLETED'} else 'RUNNING' if 'RUNNING' in statuses else 'QUEUED_SOLVE')
    return {'id': str(row.id), 'snapshot_id': str(row.snapshot_id), 'request_hash': row.request_hash,
        'request': row.payload, 'preparation_status': row.status, 'status': state,
        'runs': result, 'artifacts': row.artifacts, 'error': row.error,
        'created_at': row.created_at, 'prepared_at': row.prepared_at, 'duplicate': duplicate,
        'authority': 'SOFTWARE_PROPOSAL_ONLY', 'validation': 'SEPARATE_REQUIRED_STEP'}


@router.post('/planning-sessions', status_code=202, response_model=PlanningSessionView)
def create(body: PlanningSessionInput, user=Depends(require('ADMIN', 'PLANNER')),
        db=Depends(session_dependency), now=Depends(utc_now)):
    payload = body.model_dump(mode='json'); fingerprint = digest(payload)
    lock_publication(db)
    previous = db.scalar(select(PlanningSession).where(PlanningSession.idempotency_key == body.idempotency_key))
    if previous:
        if previous.request_hash != fingerprint or previous.created_by != str(user.id):
            raise HTTPException(409, 'IDEMPOTENCY_KEY_REUSED')
        return serialize(db, previous, True)
    checked_snapshot(db, payload, now)
    row = PlanningSession(snapshot_id=body.snapshot_id, idempotency_key=body.idempotency_key,
        request_hash=fingerprint, payload=payload, status='QUEUED_PREPARATION',
        artifacts={}, created_by=str(user.id), created_at=now)
    db.add(row); db.flush()
    audit(db, user, 'PLANNING_SESSION_QUEUED', row.id, {'snapshot_id': str(row.snapshot_id), 'request_hash': fingerprint})
    db.commit()
    return serialize(db, row)


@router.get('/planning-sessions/{id}', response_model=PlanningSessionView)
def read(id: uuid.UUID, user=Depends(staff), db=Depends(session_dependency)):
    row = db.get(PlanningSession, id)
    if not row: raise HTTPException(404, 'PLANNING_SESSION_NOT_FOUND')
    return serialize(db, row)


@router.get('/workspace/planning-sessions', response_model=PlanningSessionPage)
def browse(snapshot_id: uuid.UUID, limit: int = Query(default=25, ge=1, le=100),
        cursor: str | None = Query(default=None, max_length=1024),
        user=Depends(staff), db=Depends(session_dependency)):
    if not db.get(PlanningSnapshot, snapshot_id): raise HTTPException(404, 'SNAPSHOT_NOT_FOUND')
    filters = {'kind': 'planning_sessions', 'snapshot_id': str(snapshot_id)}
    query = select(PlanningSession).where(PlanningSession.snapshot_id == snapshot_id)
    if cursor: query = query.where(cursor_condition(PlanningSession, cursor, filters))
    rows = db.scalars(query.order_by(PlanningSession.created_at.desc(), PlanningSession.id.desc()).limit(limit + 1)).all()
    return {'items': [serialize(db, row) for row in rows[:limit]],
        'next_cursor': cursor_for(rows[limit - 1], filters) if len(rows) > limit else None}


def prepare_one(now=None):
    fixed_clock = now is not None
    now = now or datetime.now(timezone.utc)
    with Session.begin() as db:
        # Fail closed and bound DB waits; a crash/timeout before commit leaves the
        # request queued. No preparation status is guessed by the browser.
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        row = db.scalar(select(PlanningSession).where(PlanningSession.status == 'QUEUED_PREPARATION')
            .order_by(PlanningSession.created_at, PlanningSession.id).with_for_update(skip_locked=True).limit(1))
        if not row: return None
        lock_publication(db)
        try:
            with db.begin_nested():
                if digest(row.payload) != row.request_hash: raise HTTPException(409, 'PLANNING_SESSION_HASH_MISMATCH')
                snapshot, context = checked_snapshot(db, row.payload, now)
                artifacts, runs = queue_proposal(db, snapshot, row.created_at, context,
                    SolverOptions.model_validate(row.payload['solver_options']))
                checked_snapshot(db, row.payload, now if fixed_clock else datetime.now(timezone.utc))
                row.artifacts = artifacts
                row.baseline_run_id, row.optimized_run_id = runs[0].id, runs[1].id
                row.status = 'PREPARED'; row.prepared_at = now
        except HTTPException as error:
            row.status = 'BLOCKED'; row.error = {'detail': error.detail}
        except Exception as error:
            row.status = 'FAILED'; row.error = {'code': 'PREPARATION_ERROR', 'exception_type': type(error).__name__}
        from .models import AuditEvent
        db.add(AuditEvent(actor=row.created_by, action='PLANNING_SESSION_' + row.status, entity=str(row.id),
            data={'request_hash': row.request_hash, 'status': row.status, 'error': row.error}))
        return str(row.id)
