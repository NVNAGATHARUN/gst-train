"""Immutable, versioned comparisons with current validation shown separately."""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from .auth import current_user, require
from .db import session_dependency
from .models import PlanRevision, PlanningSnapshot, PlanComparison, PlanningRun, ValidationReport, CoordinationComputation
from .requests import StrictModel, audit, digest
from .validation import usability, utc_now
from .kpi_metrics import VERSION, metrics, comparison_metrics

router = APIRouter(prefix='/api/v1')


def normalize_json(value):
    # PostgreSQL JSONB normalizes negative zero. Hash the persisted representation.
    if isinstance(value, dict):
        return {key: normalize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, float) and value == 0:
        return 0.0
    return value


class ComparisonInput(StrictModel):
    baseline_plan_revision_id: uuid.UUID
    railsync_plan_revision_id: uuid.UUID


def latest_report(db, id):
    return db.scalar(select(ValidationReport).where(ValidationReport.plan_revision_id == id)
        .order_by(ValidationReport.checked_at.desc(), ValidationReport.id).limit(1))


def validation_state(db, revision, now):
    report = latest_report(db, revision.id)
    usable, blockers = usability(db, report, now) if report else (False, ['VALIDATION_REPORT_MISSING'])
    return {'report_id': str(report.id) if report else None, 'status': report.status if report else 'NOT_RUN',
        'usable': usable, 'blockers': blockers, 'findings_by_code': {
            code: sum(f['code'] == code for c in report.result['checks'] for f in c['findings'])
            for code in {f['code'] for c in report.result['checks'] for f in c['findings']}
        } if report else None}


def check_inputs(db, baseline, railsync):
    if baseline.id == railsync.id:
        raise HTTPException(422, 'DISTINCT_PLANS_REQUIRED')
    if baseline.snapshot_id != railsync.snapshot_id or baseline.snapshot_hash != railsync.snapshot_hash:
        raise HTTPException(409, 'SNAPSHOT_MISMATCH')
    if baseline.content.get('planner') != 'FIRST_FEASIBLE_CANDIDATE_BASELINE' or railsync.content.get('planner') != 'CP_SAT':
        raise HTTPException(422, 'PLANNER_TYPE_MISMATCH')
    snapshot = db.get(PlanningSnapshot, baseline.snapshot_id)
    if digest(snapshot.manifest) != snapshot.content_hash or snapshot.content_hash != baseline.snapshot_hash:
        raise HTTPException(409, 'SNAPSHOT_HASH_MISMATCH')
    runs = []
    for revision in (baseline, railsync):
        run = db.get(PlanningRun, revision.run_id)
        if digest(revision.content) != revision.plan_hash:
            raise HTTPException(409, 'PLAN_HASH_MISMATCH')
        if not run or run.status != 'COMPLETED' or run.snapshot_id != snapshot.id or digest(run.result) != revision.plan_hash:
            raise HTTPException(409, 'PLAN_RUN_MISMATCH')
        if not revision.content.get('comparison_eligible'):
            raise HTTPException(409, 'COMPARISON_INELIGIBLE')
        if revision.content.get('requirements_hash') != digest(snapshot.manifest['facts']['requests']):
            raise HTTPException(409, 'REQUIREMENTS_HASH_MISMATCH')
        coordination = db.get(CoordinationComputation, uuid.UUID(run.config['coordination_id']))
        if not coordination or coordination.snapshot_id != snapshot.id or coordination.input_hash != revision.content.get('coordination_hash'):
            raise HTTPException(409, 'COORDINATION_HASH_MISMATCH')
        runs.append(run)
    for key in ('requirements_hash', 'coordination_hash', 'priorities_hash'):
        if not baseline.content.get(key) or baseline.content.get(key) != railsync.content.get(key):
            raise HTTPException(409, {'code': 'COMPARISON_INPUT_MISMATCH', 'field': key})
    for key in ('coordination_id', 'clearance_minutes', 'protect_freight_envelope', 'solver_options'):
        if runs[0].config.get(key) != runs[1].config.get(key):
            raise HTTPException(409, {'code': 'COMPARISON_CONFIGURATION_MISMATCH', 'field': key})
    return snapshot


def row_json(db, row, now, duplicate=False):
    if digest(row.content) != row.content_hash:
        raise HTTPException(409, 'COMPARISON_HASH_MISMATCH')
    states = [validation_state(db, db.get(PlanRevision, id), now) for id in
        (row.baseline_plan_revision_id, row.railsync_plan_revision_id)]
    return {'id': str(row.id), 'content_hash': row.content_hash, 'content': row.content,
        'created_at': row.created_at.isoformat(), 'duplicate': duplicate,
        'current_claims_permitted': row.content.get('metric_version') == VERSION and row.content['claims_permitted'] and all(s['usable'] for s in states),
        'current_validation': {'baseline': states[0], 'railsync': states[1]},
        'metric_version_current': row.content.get('metric_version') == VERSION}


@router.post('/plan-comparisons', status_code=201)
def compare(body: ComparisonInput, user=Depends(require('ADMIN','PLANNER','CONTROLLER')), now=Depends(utc_now), db=Depends(session_dependency)):
    baseline = db.get(PlanRevision, body.baseline_plan_revision_id)
    railsync = db.get(PlanRevision, body.railsync_plan_revision_id)
    if not baseline or not railsync:
        raise HTTPException(404, 'PLAN_REVISION_NOT_FOUND')
    snapshot = check_inputs(db, baseline, railsync)
    sides = []
    for revision in (baseline, railsync):
        state = validation_state(db, revision, now)
        try:
            values = metrics(revision.content, snapshot)
            computation_error = None
        except (ValueError, KeyError, TypeError) as error:
            values = metrics({'schedule_status': 'ERROR'}, snapshot)
            computation_error = str(error)
        sides.append({'plan_revision_id': str(revision.id), 'plan_hash': revision.plan_hash,
            'planner': revision.content['planner'], 'validation_report_id': state['report_id'],
            **state, 'metrics': values, 'computation_error': computation_error,
            'schedule_status': revision.content.get('schedule_status'),
            'solver_status': revision.content.get('solver_status'),
            'quality': {key: revision.content.get(key) for key in ('objective_value','objective_terms','best_bound','relative_gap','candidate_search')},
        })
    claims = all(s['usable'] and s['computation_error'] is None and s['metrics']['outcome'] == 'COMPUTED_FROM_SAVED_INTERVALS' for s in sides)
    payload = {'schema_version': 2, 'metric_version': VERSION,
        'status': 'VALIDATED_COMPARISON' if claims else 'UNVALIDATED_COMPARISON', 'claims_permitted': claims,
        'snapshot_id': str(snapshot.id), 'snapshot_hash': snapshot.content_hash,
        'scenario_id': snapshot.scenario_id,
        'claim_scope': 'ISOLATED_SIMULATION_ONLY' if snapshot.scenario_id else 'SOURCE_SNAPSHOT_PROPOSAL',
        'horizon': {key: snapshot.manifest[key] for key in ('horizon_start','horizon_end','track_ids')},
        'requirements_hash': baseline.content['requirements_hash'], 'coordination_hash': baseline.content['coordination_hash'],
        'priorities_hash': baseline.content['priorities_hash'], 'baseline': sides[0], 'railsync': sides[1],
        'metrics': comparison_metrics(sides[0]['metrics'], sides[1]['metrics']),
        'limits': ['PLANNED_WORK_IS_NOT_COMPLETED_WORK','FORECAST_EXPOSURE_IS_NOT_MEASURED_TRAIN_DELAY',
            'MAINTENANCE_ONLY_TRACK_AVAILABILITY_IS_NOT_ASSET_RELIABILITY', 'OPTIMALITY_SCOPE_IS_GENERATED_CANDIDATE_SET']
            + (['SCENARIO_RESULTS_CANNOT_AUTHORIZE_POSSESSIONS'] if snapshot.scenario_id else []),
        'generated_at': now.isoformat()}
    payload = normalize_json(payload)
    content_hash = digest(payload)
    existing = db.scalar(select(PlanComparison).where(PlanComparison.content_hash == content_hash))
    if existing:
        return row_json(db, existing, now, True)
    row = PlanComparison(baseline_plan_revision_id=baseline.id, railsync_plan_revision_id=railsync.id,
        content_hash=content_hash, content=payload, created_by=str(user.id), created_at=now)
    db.add(row)
    db.flush()
    audit(db, user, 'PLAN_COMPARISON_CREATED', row.id, {'content_hash': content_hash, 'status': payload['status']})
    db.commit()
    return row_json(db, row, now)


@router.get('/plan-comparisons/{id}')
def read(id: uuid.UUID, user=Depends(current_user), now=Depends(utc_now), db=Depends(session_dependency)):
    row = db.get(PlanComparison, id)
    if not row:
        raise HTTPException(404, 'PLAN_COMPARISON_NOT_FOUND')
    return row_json(db, row, now)


@router.get('/plan-comparisons/{id}/export')
def export(id: uuid.UUID, user=Depends(current_user), now=Depends(utc_now), db=Depends(session_dependency)):
    row = db.get(PlanComparison, id)
    if not row:
        raise HTTPException(404, 'PLAN_COMPARISON_NOT_FOUND')
    current = row_json(db, row, now)
    return Response(json.dumps(row.content, sort_keys=True, separators=(',',':')), media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="rmaps-comparison-{id}.json"',
            'X-RMAPS-Content-Hash': row.content_hash,
            'X-RMAPS-Current-Claims-Permitted': str(current['current_claims_permitted']).lower()})
