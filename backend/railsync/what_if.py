"""M17 isolated what-if facts and real planning runs; never writes source state."""
import copy
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import select
from .auth import current_user, require
from .db import Session, engine, session_dependency
from .models import (PlanningRun, PlanningSnapshot, PlanRevision, SnapshotItem,
    ValidationReport, WhatIfImpact, WhatIfScenario)
from .requests import RequestInput, StrictModel, audit, digest
from .coordination_schema import ResourceProfile
from .proposal_pipeline import queue_proposal
from .staleness import invalidation_ids, lock_publication
from .freeze_state import execution_pending
from .validation import utc_now
from .validation_schema import ValidationContext

router = APIRouter(prefix='/api/v1')
VERSION = 'WHAT_IF_V1'


class TrainDelay(StrictModel):
    kind: Literal['TRAIN_DELAY']
    occupancy_id: uuid.UUID
    delay_minutes: int = Field(ge=1, le=240)


class FreightCount(StrictModel):
    kind: Literal['FREIGHT_COUNT']
    external_id: str = Field(min_length=1, max_length=100)
    expected_count: int = Field(ge=0, le=1000)


class ResourceOutage(StrictModel):
    kind: Literal['RESOURCE_OUTAGE']
    resource_id: str = Field(min_length=1, max_length=100)
    track_id: str
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode='after')
    def ordered(self):
        if self.start_at >= self.end_at: raise ValueError('positive outage interval required')
        return self


class Restriction(StrictModel):
    kind: Literal['RESTRICTION']
    track_ids: list[str] = Field(min_length=1, max_length=20)
    start_at: AwareDatetime
    end_at: AwareDatetime
    rule_id: str = Field(min_length=1, max_length=100)
    restriction_type: Literal['CLOSURE', 'WORK_PROHIBITED', 'ISOLATION_UNAVAILABLE']

    @model_validator(mode='after')
    def ordered(self):
        if self.start_at >= self.end_at or len(set(self.track_ids)) != len(self.track_ids):
            raise ValueError('positive interval and unique tracks required')
        return self


class AddRequest(StrictModel):
    kind: Literal['ADD_REQUEST']
    request_id: uuid.UUID
    data: RequestInput


ScenarioChange = Annotated[TrainDelay | FreightCount | ResourceOutage | Restriction | AddRequest,
    Field(discriminator='kind')]
change_adapter = TypeAdapter(list[ScenarioChange])


class ScenarioInput(StrictModel):
    idempotency_key: uuid.UUID
    source_snapshot_id: uuid.UUID
    expected_source_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    name: str = Field(min_length=3, max_length=120)
    changes: list[ScenarioChange] = Field(min_length=1, max_length=20)


class ImpactInput(StrictModel):
    source_plan_revision_id: uuid.UUID
    scenario_plan_revision_id: uuid.UUID


def instant(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def one(rows, predicate, code):
    found = [row for row in rows if predicate(row)]
    if len(found) != 1: raise HTTPException(422, code)
    return found[0]


def apply_changes(source, changes, scenario_id):
    """Pure replay from saved source facts. Validation replays the same declared inputs."""
    facts = copy.deepcopy(source['facts'])
    start, end = instant(source['horizon_start']), instant(source['horizon_end'])
    tracks = set(source['track_ids'])
    seen = set()
    for index, change in enumerate(change_adapter.validate_python(changes)):
        target = (change.kind, str(getattr(change, 'occupancy_id',
            getattr(change, 'external_id', getattr(change, 'resource_id',
            getattr(change, 'request_id', index))))))
        if target in seen: raise HTTPException(422, 'DUPLICATE_SCENARIO_CHANGE')
        seen.add(target)
        if isinstance(change, TrainDelay):
            row = one(facts['occupancy'], lambda r: r['id'] == str(change.occupancy_id),
                'SCENARIO_OCCUPANCY_NOT_FOUND')
            for key in ('enter_at', 'exit_at'):
                row[key] = (instant(row[key]) + timedelta(minutes=change.delay_minutes)).isoformat()
        elif isinstance(change, FreightCount):
            row = one(facts['freight'], lambda r: r['external_id'] == change.external_id,
                'SCENARIO_FORECAST_NOT_FOUND')
            if row['expected_count'] == change.expected_count:
                raise HTTPException(422, 'SCENARIO_CHANGE_NO_EFFECT')
            row['expected_count'] = change.expected_count
        elif isinstance(change, ResourceOutage):
            if change.track_id not in tracks or change.start_at < start or change.end_at > end:
                raise HTTPException(422, 'SCENARIO_OUTAGE_OUTSIDE_SCOPE')
            row = one(facts['resources'], lambda r: r['id'] == change.resource_id,
                'SCENARIO_RESOURCE_NOT_FOUND')
            if not row.get('profile'): raise HTTPException(422, 'SCENARIO_RESOURCE_PROFILE_UNKNOWN')
            row['profile']['payload']['duties'].append({'track_id': change.track_id,
                'start_at': change.start_at.isoformat(), 'end_at': change.end_at.isoformat()})
            try: ResourceProfile.model_validate(row['profile']['payload'])
            except ValidationError: raise HTTPException(422, 'SCENARIO_RESOURCE_DUTY_INVALID')
        elif isinstance(change, Restriction):
            if (not set(change.track_ids).issubset(tracks) or
                    change.start_at < start or change.end_at > end):
                raise HTTPException(422, 'SCENARIO_RESTRICTION_OUTSIDE_SCOPE')
            facts['network'].append({'id': f'WHATIF-{scenario_id.hex[:16]}-{index}',
                'kind': 'restriction', 'revision': 1,
                'payload': {'footprint': sorted(change.track_ids),
                    'start': change.start_at.isoformat(), 'end': change.end_at.isoformat(),
                    'rule_id': change.rule_id, 'type': change.restriction_type}})
        elif isinstance(change, AddRequest):
            data = change.data.model_dump(mode='json')
            if data['source_mode'] != 'SIMULATED' or not set(data['footprint']).issubset(tracks):
                raise HTTPException(422, 'SCENARIO_REQUEST_OUTSIDE_SCOPE')
            if any(r['id'] == str(change.request_id) for r in facts['requests']):
                raise HTTPException(422, 'SCENARIO_REQUEST_ID_EXISTS')
            asset = one(facts['network'], lambda r: r['id'] == data['asset_id'] and r['kind'] == 'asset',
                'SCENARIO_REQUEST_ASSET_UNKNOWN')
            if (asset['payload']['department'] != data['department'] or
                    not set(asset['payload']['footprint']).issubset(data['footprint'])):
                raise HTTPException(422, 'SCENARIO_REQUEST_ASSET_MISMATCH')
            if data['power_block_required']:
                zone = one(facts['network'], lambda r: r['id'] == data['isolation_zone']
                    and r['kind'] == 'isolation', 'SCENARIO_ISOLATION_ZONE_UNKNOWN')
                if not set(data['footprint']).issubset(zone['payload']['footprint']):
                    raise HTTPException(422, 'SCENARIO_ISOLATION_COVERAGE_MISSING')
            facts['requests'].append({'id': str(change.request_id), 'revision': 1,
                'status': 'PENDING_PLANNING', 'payload': data})
    by_run = {}
    for row in facts['occupancy']:
        by_run.setdefault(row['run_id'], []).append(row)
    for rows in by_run.values():
        ordered = sorted(rows, key=lambda row: row['sequence'])
        if any(instant(a['exit_at']) > instant(b['enter_at']) for a, b in zip(ordered, ordered[1:])):
            raise HTTPException(422, 'SCENARIO_TRAIN_ROUTE_OVERLAP')
    return facts


def serialize(db, row, duplicate=False):
    baseline = db.get(PlanningRun, row.baseline_run_id)
    optimized = db.get(PlanningRun, row.optimized_run_id)
    return {'id': str(row.id), 'duplicate': duplicate,
        'source_snapshot_id': str(row.source_snapshot_id), 'snapshot_id': str(row.snapshot_id),
        'content_hash': row.content_hash, 'payload': row.payload,
        'baseline_run': {'id': str(baseline.id), 'status': baseline.status},
        'optimized_run': {'id': str(optimized.id), 'status': optimized.status},
        'authority': 'ISOLATED_SIMULATION_ONLY', 'approval_permitted': False}


@router.post('/what-if-scenarios', status_code=202)
def create(body: ScenarioInput, user=Depends(require('ADMIN', 'PLANNER', 'CONTROLLER')),
        now=Depends(utc_now), db=Depends(session_dependency)):
    lock_publication(db)
    fingerprint = digest(body.model_dump(mode='json'))
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as consistent:
            existing = consistent.scalar(select(WhatIfScenario).where(
                WhatIfScenario.idempotency_key == body.idempotency_key))
            if existing:
                if existing.payload['request_hash'] != fingerprint:
                    raise HTTPException(409, 'SCENARIO_IDEMPOTENCY_CONFLICT')
                return serialize(consistent, existing, True)
            source = consistent.get(PlanningSnapshot, body.source_snapshot_id)
            if not source: raise HTTPException(404, 'SOURCE_SNAPSHOT_NOT_FOUND')
            if (source.scenario_id or source.content_hash != body.expected_source_hash
                    or digest(source.manifest) != source.content_hash):
                raise HTTPException(409, 'SCENARIO_SOURCE_HASH_MISMATCH')
            if source.manifest['facts'].get('replanning') or execution_pending(consistent, source):
                raise HTTPException(409, 'SCENARIO_SOURCE_EXECUTION_AWARE_REQUIRED')
            context_raw = source.manifest.get('validation_context')
            if not context_raw: raise HTTPException(409, 'SCENARIO_SOURCE_VALIDATION_CONTEXT_REQUIRED')
            context = ValidationContext.model_validate(context_raw)
            if context.scope != 'SIMULATED' or not context.received_at <= now < context.valid_until:
                raise HTTPException(409, 'SCENARIO_SOURCE_CONTEXT_NOT_CURRENT')
            if context.facts_hash != digest(source.manifest['facts']):
                raise HTTPException(409, 'SCENARIO_SOURCE_CONTEXT_HASH_MISMATCH')
            from .validation import current_hash
            if invalidation_ids(consistent, source.id) or current_hash(consistent, source) != digest(source.manifest['facts']):
                raise HTTPException(409, 'SCENARIO_SOURCE_STALE')
            scenario_id = uuid.uuid4()
            changes = [change.model_dump(mode='json') for change in body.changes]
            changed = apply_changes(source.manifest, changes, scenario_id)
            adjusted_context = context.model_copy(update={'facts_hash': digest(changed)})
            manifest = {**source.manifest, 'scenario_id': str(scenario_id),
                'facts': changed, 'counts': {key: len(rows) for key, rows in changed.items()},
                'validation_context': adjusted_context.model_dump(mode='json'),
                'scenario': {'version': VERSION, 'id': str(scenario_id),
                    'source_snapshot_id': str(source.id), 'source_snapshot_hash': source.content_hash,
                    'changes_hash': digest(changes)}}
            scenario_snapshot = PlanningSnapshot(id=uuid.uuid4(), content_hash=digest(manifest),
                horizon_start=source.horizon_start, horizon_end=source.horizon_end,
                scenario_id=str(scenario_id), manifest=manifest)
            consistent.add(scenario_snapshot); consistent.flush()
            for kind, rows in changed.items():
                for value in rows:
                    key = value.get('id') or value.get('external_id') or digest(value)
                    consistent.add(SnapshotItem(snapshot_id=scenario_snapshot.id,
                        kind=kind, item_key=str(key), payload=value))
            pipeline, runs = queue_proposal(consistent, scenario_snapshot, now, adjusted_context)
            payload = {'request_hash': fingerprint, 'name': body.name,
                'source_snapshot_hash': source.content_hash, 'scenario_snapshot_hash': scenario_snapshot.content_hash,
                'changes': changes, 'changes_hash': digest(changes), **pipeline,
                'worker_status': 'QUEUED', 'controller_approval': 'FORBIDDEN'}
            row = WhatIfScenario(id=scenario_id, idempotency_key=body.idempotency_key,
                source_snapshot_id=source.id, snapshot_id=scenario_snapshot.id,
                baseline_run_id=runs[0].id, optimized_run_id=runs[1].id,
                content_hash=digest(payload), payload=payload,
                created_by=str(user.id), created_at=now)
            consistent.add(row); consistent.flush()
            audit(consistent, user, 'WHAT_IF_SCENARIO_QUEUED', row.id,
                {'source_snapshot_id': str(source.id), 'snapshot_id': str(scenario_snapshot.id)})
            response = serialize(consistent, row)
            consistent.commit()
            return response


@router.get('/what-if-scenarios/{id}')
def read(id: uuid.UUID, user=Depends(current_user), db=Depends(session_dependency)):
    row = db.get(WhatIfScenario, id)
    if not row: raise HTTPException(404, 'WHAT_IF_SCENARIO_NOT_FOUND')
    return serialize(db, row)


def report_for(db, revision):
    return db.scalar(select(ValidationReport).where(
        ValidationReport.plan_revision_id == revision.id).order_by(
        ValidationReport.checked_at.desc(), ValidationReport.id).limit(1))


def impact_json(row, duplicate=False):
    return {'id': str(row.id), 'scenario_id': str(row.scenario_id),
        'content_hash': row.content_hash, 'content': row.content,
        'created_at': row.created_at.isoformat(), 'duplicate': duplicate,
        'authority': 'ISOLATED_SIMULATION_ONLY', 'claims_permitted': False}


@router.post('/what-if-scenarios/{id}/impacts', status_code=201)
def impact(id: uuid.UUID, body: ImpactInput,
        user=Depends(require('ADMIN', 'PLANNER', 'CONTROLLER')),
        now=Depends(utc_now), db=Depends(session_dependency)):
    scenario = db.get(WhatIfScenario, id)
    if not scenario: raise HTTPException(404, 'WHAT_IF_SCENARIO_NOT_FOUND')
    source_revision = db.get(PlanRevision, body.source_plan_revision_id)
    scenario_revision = db.get(PlanRevision, body.scenario_plan_revision_id)
    if not source_revision or not scenario_revision:
        raise HTTPException(404, 'PLAN_REVISION_NOT_FOUND')
    if (source_revision.snapshot_id != scenario.source_snapshot_id
            or scenario_revision.snapshot_id != scenario.snapshot_id):
        raise HTTPException(409, 'SCENARIO_IMPACT_SNAPSHOT_MISMATCH')
    if (source_revision.content.get('planner') != 'CP_SAT'
            or scenario_revision.content.get('planner') != 'CP_SAT'):
        raise HTTPException(422, 'SCENARIO_IMPACT_REQUIRES_CP_SAT')
    if (digest(source_revision.content) != source_revision.plan_hash
            or digest(scenario_revision.content) != scenario_revision.plan_hash):
        raise HTTPException(409, 'SCENARIO_IMPACT_PLAN_HASH_MISMATCH')
    existing = db.scalar(select(WhatIfImpact).where(
        WhatIfImpact.scenario_id == scenario.id,
        WhatIfImpact.source_plan_revision_id == source_revision.id,
        WhatIfImpact.scenario_plan_revision_id == scenario_revision.id))
    if existing:
        if digest(existing.content) != existing.content_hash:
            raise HTTPException(409, 'WHAT_IF_IMPACT_HASH_MISMATCH')
        return impact_json(existing, True)
    from .validation import usability
    reports = [report_for(db, revision) for revision in (source_revision, scenario_revision)]
    states = [usability(db, report, now) if report else (False, ['VALIDATION_REPORT_MISSING'])
        for report in reports]
    if not all(state[0] for state in states):
        raise HTTPException(409, {'code': 'SCENARIO_IMPACT_VALIDATION_NOT_USABLE',
            'source_blockers': states[0][1], 'scenario_blockers': states[1][1]})
    from .kpi_metrics import DEFINITIONS, VERSION as KPI_VERSION, metrics
    source_snapshot = db.get(PlanningSnapshot, scenario.source_snapshot_id)
    scenario_snapshot = db.get(PlanningSnapshot, scenario.snapshot_id)
    source_metrics = metrics(source_revision.content, source_snapshot)
    scenario_metrics = metrics(scenario_revision.content, scenario_snapshot)
    differences = {}
    for name, (unit, formula, direction) in DEFINITIONS.items():
        left, right = source_metrics[name], scenario_metrics[name]
        differences[name] = {'unit': unit, 'formula': formula, 'direction': direction,
            'source': left, 'scenario': right,
            'raw_delta': None if left is None or right is None else right-left,
            'status': 'NOT_AVAILABLE' if left is None or right is None else 'AVAILABLE'}
    content = {'schema_version': 1, 'metric_version': KPI_VERSION,
        'comparison_type': 'INPUT_CHANGED_SCENARIO_IMPACT',
        'claim_scope': 'ISOLATED_SIMULATION_ONLY', 'claims_permitted': False,
        'scenario_id': str(scenario.id), 'scenario_name': scenario.payload['name'],
        'changed_inputs': scenario.payload['changes'],
        'changed_inputs_hash': scenario.payload['changes_hash'],
        'source': {'snapshot_id': str(source_snapshot.id),
            'snapshot_hash': source_snapshot.content_hash,
            'plan_revision_id': str(source_revision.id), 'plan_hash': source_revision.plan_hash,
            'validation_report_id': str(reports[0].id), 'metrics': source_metrics},
        'scenario': {'snapshot_id': str(scenario_snapshot.id),
            'snapshot_hash': scenario_snapshot.content_hash,
            'plan_revision_id': str(scenario_revision.id), 'plan_hash': scenario_revision.plan_hash,
            'validation_report_id': str(reports[1].id), 'metrics': scenario_metrics},
        'observed_differences': differences,
        'limits': ['INPUTS_DIFFER_SO_DELTAS_ARE_NOT_OPTIMIZER_GAINS',
            'PLANNED_WORK_IS_NOT_COMPLETED_WORK',
            'FORECAST_EXPOSURE_IS_NOT_MEASURED_TRAIN_DELAY',
            'SCENARIO_RESULTS_CANNOT_AUTHORIZE_POSSESSIONS'],
        'generated_at': now.isoformat()}
    content_hash = digest(content)
    row = WhatIfImpact(scenario_id=scenario.id,
        source_plan_revision_id=source_revision.id,
        scenario_plan_revision_id=scenario_revision.id,
        content_hash=content_hash, content=content,
        created_by=str(user.id), created_at=now)
    db.add(row); db.flush()
    audit(db, user, 'WHAT_IF_IMPACT_CREATED', row.id,
        {'scenario_id': str(scenario.id), 'content_hash': content_hash})
    db.commit()
    return impact_json(row)


@router.get('/what-if-impacts/{id}')
def read_impact(id: uuid.UUID, user=Depends(current_user),
        db=Depends(session_dependency)):
    row = db.get(WhatIfImpact, id)
    if not row: raise HTTPException(404, 'WHAT_IF_IMPACT_NOT_FOUND')
    if digest(row.content) != row.content_hash:
        raise HTTPException(409, 'WHAT_IF_IMPACT_HASH_MISMATCH')
    return impact_json(row)
