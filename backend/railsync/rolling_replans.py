"""M16: reconcile recorded disruptions with changed source facts, then queue a proposal.

Events are evidence, not source updates. No reservation or controller decision is
written here. All derived stages are committed together, before worker execution.
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field
from sqlalchemy import select
from .auth import current_user, require
from .db import Session, engine, session_dependency
from .models import (DisruptionEvent, EventReconciliation, PlanningRun,
    PlanningSnapshot, PlanRevision, ReplanningBatch,
    ReplanningCapture, SnapshotInvalidation)
from .requests import StrictModel, audit, digest
from .decision_support import lock_state
from .staleness import lock_publication, invalidated_facts
from .replanning_state import BASE_FACT_KEYS, capture_payload
from .snapshots import SnapshotInput, facts, persist_snapshot
from .validation_schema import ValidationContext
from .validation import utc_now
from .proposal_pipeline import queue_proposal

router = APIRouter(prefix='/api/v1')


class PrepareInput(StrictModel):
    idempotency_key: uuid.UUID
    source_plan_revision_id: uuid.UUID
    expected_plan_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_operational_revision: int = Field(ge=0)
    expected_batch_generation: int = Field(ge=1)
    expected_base_facts_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    horizon_end: AwareDatetime | None = None
    validation_context: dict


def source_input(snapshot, horizon_end=None):
    manifest = snapshot.manifest
    original_end = datetime.fromisoformat(manifest['horizon_end'])
    if horizon_end and (horizon_end < original_end or
            (horizon_end - original_end).total_seconds() > 30 * 86400):
        raise HTTPException(422, 'ROLLING_HORIZON_EXTENSION_INVALID')
    return SnapshotInput(horizon_start=datetime.fromisoformat(manifest['horizon_start']),
        horizon_end=horizon_end or original_end,
        track_ids=manifest['track_ids'],
        require_freight_forecast=manifest['require_freight_forecast'],
        coordination_policy_id=uuid.UUID(manifest['facts']['coordination_policies'][0]['id'])
            if manifest['facts']['coordination_policies'] else None)


def changed_rows(before, after, key):
    prior = {key(row): row for row in before}
    return [(prior.get(key(row)), row) for row in after
        if prior.get(key(row)) != row]


def event_evidence(event, old, new, horizon):
    payload = event.payload
    tracks = set(payload['track_ids'])
    resources = set(payload['resource_ids'])
    kind = event.kind
    matches = []
    if kind == 'TRAIN_DELAY':
        for previous, row in changed_rows(old['occupancy'], new['occupancy'],
                lambda r: (r['train_id'], r['service_date'], r['track_id'], r['sequence'])):
            if (previous and row['track_id'] in tracks
                    and row['source_revision'] > previous['source_revision']
                    and datetime.fromisoformat(row['enter_at']) >= datetime.fromisoformat(previous['enter_at'])
                    and datetime.fromisoformat(row['exit_at']) >= datetime.fromisoformat(previous['exit_at'])
                    and (row['enter_at'], row['exit_at']) != (previous['enter_at'], previous['exit_at'])):
                matches.append({'source_id': row['run_id'], 'previous_id': previous['run_id'],
                    'source_revision': row['source_revision'], 'track_id': row['track_id']})
    elif kind == 'FREIGHT_CHANGE':
        for previous, row in changed_rows(old['freight'], new['freight'],
                lambda r: (r['external_id'], r['track_id'])):
            if (previous and row['track_id'] in tracks
                    and row['source_revision'] > previous['source_revision']
                    and (row['start_at'], row['end_at'], row['expected_count'], row['confidence_basis_points'])
                    != (previous['start_at'], previous['end_at'], previous['expected_count'], previous['confidence_basis_points'])):
                matches.append({'source_id': row['id'], 'previous_id': previous['id'],
                    'source_revision': row['source_revision'], 'track_id': row['track_id']})
    elif kind == 'RESOURCE_OUTAGE':
        for previous, row in changed_rows(old['resources'], new['resources'], lambda r: r['id']):
            if not previous or row['id'] not in resources: continue
            prior_profile = (previous.get('profile') or {}).get('payload') or {}
            profile = (row.get('profile') or {}).get('payload') or {}
            old_duties = {digest(d) for d in prior_profile.get('duties', [])}
            new_duties = [d for d in profile.get('duties', []) if digest(d) not in old_duties]
            removed_qualifications = ({digest(q) for q in prior_profile.get('qualifications', [])}
                - {digest(q) for q in profile.get('qualifications', [])})
            removed_calendar = ({digest(c) for c in prior_profile.get('calendar', [])}
                - {digest(c) for c in profile.get('calendar', [])})
            start, end = (datetime.fromisoformat(horizon[k]) for k in ('start', 'end'))
            new_duty_in_horizon = any(datetime.fromisoformat(d['start_at']) < end
                and datetime.fromisoformat(d['end_at']) > start for d in new_duties)
            reduced = (datetime.fromisoformat(row['available_start']) > datetime.fromisoformat(previous['available_start'])
                or datetime.fromisoformat(row['available_end']) < datetime.fromisoformat(previous['available_end'])
                or new_duty_in_horizon or bool(removed_qualifications) or bool(removed_calendar))
            if reduced: matches.append({'source_id': row['id'], 'profile_revision':
                (row.get('profile') or {}).get('revision'), 'resource_id': row['id']})
    elif kind == 'URGENT_DEFECT':
        prior_ids = {r['id'] for r in old['requests']}
        for row in new['requests']:
            data = row['payload']
            if row['id'] not in prior_ids and tracks.intersection(data['footprint']) and (
                    data['mandatory'] or data['severity'] >= 4 or data['urgency'] >= 4):
                matches.append({'source_id': row['id'], 'request_revision': row['revision'],
                    'track_ids': sorted(tracks.intersection(data['footprint']))})
    elif kind == 'RESTRICTION_CHANGE':
        prior = {r['id']: r for r in old['network'] if r['kind'] == 'restriction'}
        for row in new['network']:
            if row['kind'] != 'restriction' or row == prior.get(row['id']): continue
            data = row['payload']
            if (tracks.intersection(data['footprint'])
                    and datetime.fromisoformat(data['end']) > datetime.fromisoformat(horizon['start'])
                    and datetime.fromisoformat(data['start']) < datetime.fromisoformat(horizon['end'])):
                matches.append({'source_id': row['id'], 'source_revision': row['revision'],
                    'track_ids': sorted(tracks.intersection(data['footprint']))})
    return {'event_id': str(event.id), 'kind': kind, 'matches': matches,
        'status': 'RECONCILED' if matches else 'SOURCE_CHANGE_UNVERIFIED'}


def inspect(db, parent_id, now, horizon_end=None):
    parent = db.get(PlanRevision, parent_id)
    if not parent: raise HTTPException(404, 'PLAN_REVISION_NOT_FOUND')
    source = db.get(PlanningSnapshot, parent.snapshot_id)
    if source.scenario_id or (source.manifest.get('validation_context') or {}).get('scope') != 'SIMULATED':
        raise HTTPException(409, 'SIMULATED_NON_SCENARIO_REPLANNING_ONLY')
    batch = db.get(ReplanningBatch, 'SIMULATED')
    if not batch: raise HTTPException(409, 'NO_REPLANNING_EVENTS')
    events = db.scalars(select(DisruptionEvent).join(SnapshotInvalidation,
        SnapshotInvalidation.event_id == DisruptionEvent.id).where(
        SnapshotInvalidation.snapshot_id == source.id).order_by(
        DisruptionEvent.source, DisruptionEvent.external_id, DisruptionEvent.source_revision)).all()
    latest = {}
    for event in events:
        key = (event.source, event.external_id)
        if key in latest and latest[key].kind != event.kind:
            raise HTTPException(409, 'EVENT_KIND_CHANGED')
        latest[key] = event
    if not latest: raise HTTPException(409, 'SOURCE_SNAPSHOT_HAS_NO_EVENTS')
    old = {key: source.manifest['facts'][key] for key in BASE_FACT_KEYS}
    source_body = source_input(source, horizon_end)
    base = facts(db, source_body)
    horizon = {'start': source.manifest['horizon_start'], 'end': source_body.horizon_end.isoformat()}
    evidence = [event_evidence(e, old, base, horizon) for e in latest.values()]
    return parent, source, batch, base, evidence


def preview_result(parent, source, batch, base, evidence, now):
    blockers = []
    if now < batch.ready_at: blockers.append('BATCH_DEBOUNCING')
    if invalidated_facts_for_base(base, source): blockers.append('SOURCE_FACTS_UNCHANGED')
    if any(e['status'] != 'RECONCILED' for e in evidence): blockers.append('EVENT_SOURCE_CHANGE_UNVERIFIED')
    return {'source_plan_revision_id': str(parent.id), 'source_snapshot_id': str(source.id),
        'batch_generation': batch.generation, 'ready_at': batch.ready_at.isoformat(),
        'base_facts_hash': digest(base), 'events': evidence, 'blockers': blockers,
        'status': 'READY' if not blockers else 'BLOCKED', 'authority': 'SOFTWARE_PROPOSAL_ONLY'}


def invalidated_facts_for_base(base, source):
    return digest(base) == digest({key: source.manifest['facts'][key] for key in BASE_FACT_KEYS})


@router.get('/rolling-replans/preview/{source_plan_revision_id}')
def preview(source_plan_revision_id: uuid.UUID, horizon_end: AwareDatetime | None = None,
        user=Depends(current_user),
        now=Depends(utc_now), db=Depends(session_dependency)):
    parent, source, batch, base, evidence = inspect(db, source_plan_revision_id, now, horizon_end)
    result = preview_result(parent, source, batch, base, evidence, now)
    existing = db.scalar(select(EventReconciliation).where(
        EventReconciliation.source_plan_revision_id == parent.id,
        EventReconciliation.batch_generation == batch.generation))
    if existing:
        result['blockers'].append('REPLAN_ALREADY_PREPARED')
        result['prepared_replan_id'] = str(existing.id)
        result['status'] = 'BLOCKED'
    return result


def serialize(db, row, duplicate=False):
    baseline = db.get(PlanningRun, row.baseline_run_id)
    optimized = db.get(PlanningRun, row.optimized_run_id)
    return {'id': str(row.id), 'duplicate': duplicate, 'payload_hash': row.payload_hash,
        'payload': row.payload, 'capture_id': str(row.capture_id), 'snapshot_id': str(row.snapshot_id),
        'baseline_run': {'id': str(baseline.id), 'status': baseline.status},
        'optimized_run': {'id': str(optimized.id), 'status': optimized.status},
        'authority': 'SOFTWARE_PROPOSAL_ONLY'}


@router.post('/rolling-replans', status_code=202)
def prepare(body: PrepareInput, user=Depends(require('CONTROLLER')),
        now=Depends(utc_now), db=Depends(session_dependency)):
    state = lock_state(db, 'SIMULATED')
    lock_publication(db)
    fingerprint = digest(body.model_dump(mode='json'))
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as consistent:
            existing = consistent.scalar(select(EventReconciliation).where(
                EventReconciliation.idempotency_key == body.idempotency_key))
            if existing:
                if existing.payload['request_hash'] != fingerprint:
                    raise HTTPException(409, 'REPLAN_IDEMPOTENCY_CONFLICT')
                return serialize(consistent, existing, True)
            parent, source, batch, base, evidence = inspect(
                consistent, body.source_plan_revision_id, now, body.horizon_end)
            prepared = consistent.scalar(select(EventReconciliation).where(
                EventReconciliation.source_plan_revision_id == parent.id,
                EventReconciliation.batch_generation == batch.generation))
            if prepared:
                raise HTTPException(409, 'REPLAN_ALREADY_PREPARED')
            current = preview_result(parent, source, batch, base, evidence, now)
            if current['blockers']:
                raise HTTPException(409, {'code': 'REPLAN_SOURCE_NOT_READY', 'blockers': current['blockers']})
            if (parent.plan_hash != body.expected_plan_hash or digest(parent.content) != parent.plan_hash):
                raise HTTPException(409, 'SOURCE_PLAN_HASH_MISMATCH')
            if (state.revision != body.expected_operational_revision
                    or batch.generation != body.expected_batch_generation
                    or current['base_facts_hash'] != body.expected_base_facts_hash):
                raise HTTPException(409, 'REPLAN_PREVIEW_STALE')
            capture_data = capture_payload(consistent, parent, now)
            if capture_data['blockers']:
                raise HTTPException(409, {'code': 'REPLANNING_CAPTURE_BLOCKED',
                    'blockers': capture_data['blockers']})
            capture_hash = digest(capture_data)
            capture = ReplanningCapture(plan_revision_id=parent.id, content_hash=capture_hash,
                payload=capture_data, created_by=str(user.id), created_at=now)
            consistent.add(capture); consistent.flush()
            source_body = source_input(source, body.horizon_end)
            with_capture = source_body.model_copy(update={'replanning_capture_id': capture.id})
            full_facts = facts(consistent, with_capture)
            if invalidated_facts(consistent, full_facts):
                raise HTTPException(409, 'INVALIDATED_SOURCE_FACTS_REQUIRE_UPDATE')
            if 'facts_hash' in body.validation_context:
                raise HTTPException(422, 'FACTS_HASH_IS_SERVER_BOUND')
            context = ValidationContext.model_validate({**body.validation_context,
                'facts_hash': digest(full_facts)})
            if context.scope != 'SIMULATED' or context.received_at < now or context.valid_until <= now:
                raise HTTPException(422, 'VALIDATION_CONTEXT_NOT_CURRENT')
            if context.clearance_before_minutes != context.clearance_after_minutes:
                raise HTTPException(422, 'ASYMMETRIC_CLEARANCE_NOT_SUPPORTED_BY_BASELINE')
            if context.commitments_known_empty != (not bool(full_facts['commitments'])):
                raise HTTPException(422, 'COMMITMENT_DECLARATION_MISMATCH')
            saved = persist_snapshot(with_capture.model_copy(update={'validation_context': context}),
                user, consistent, commit=False)
            snapshot = consistent.get(PlanningSnapshot, uuid.UUID(saved['id']))
            pipeline, runs = queue_proposal(consistent, snapshot, now, context)
            result = {'request_hash': fingerprint, 'source_snapshot_hash': source.content_hash,
                'base_facts_hash': current['base_facts_hash'], 'events': evidence,
                'capture_hash': capture_hash, 'snapshot_hash': snapshot.content_hash,
                **pipeline,
                'worker_status': 'QUEUED', 'controller_approval': 'REQUIRED'}
            row = EventReconciliation(idempotency_key=body.idempotency_key,
                source_plan_revision_id=parent.id, batch_generation=batch.generation,
                source_snapshot_id=source.id, capture_id=capture.id, snapshot_id=snapshot.id,
                baseline_run_id=runs[0].id, optimized_run_id=runs[1].id,
                payload_hash=digest(result), payload=result, created_by=str(user.id), created_at=now)
            consistent.add(row); consistent.flush()
            audit(consistent, user, 'ROLLING_REPLAN_QUEUED', row.id,
                {'snapshot_id': str(snapshot.id), 'event_ids': [e['event_id'] for e in evidence]})
            response = serialize(consistent, row)
            consistent.commit()
            return response


@router.get('/rolling-replans/{id}')
def read(id: uuid.UUID, user=Depends(current_user), db=Depends(session_dependency)):
    row = db.get(EventReconciliation, id)
    if not row: raise HTTPException(404, 'ROLLING_REPLAN_NOT_FOUND')
    return serialize(db, row)
