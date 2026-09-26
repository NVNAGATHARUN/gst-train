"""Isolated what-if overlays, real planning, validation and decision fences."""
import json
import os
import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.db import Session, engine
from railsync.main import app
from railsync.models import (MaintenanceRequest, NetworkEntity, PlanReservation,
    TrainRun, WhatIfImpact, WhatIfScenario)
from railsync.planning import run_one
from railsync.requests import digest
from railsync.validation import utc_now
from test_m02 import request_data
from test_m12 import NOW
from test_m13 import prepare, decision


def body(manifest, snapshot_id, change):
    return {'idempotency_key': str(uuid.uuid4()), 'source_snapshot_id': snapshot_id,
        'expected_source_hash': digest(manifest), 'name': 'SIMULATED alternative capacity',
        'changes': [change]}


def scenario(client, body):
    response = client.post('/api/v1/what-if-scenarios', headers=auth(), json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_train_delay_scenario_isolated_real_solved_validated_and_unapprovable(client):
    manifest, source_revision, _ = prepare(client)
    source_snapshot_id = source_revision['snapshot_id']
    original = manifest['facts']['occupancy'][0]
    payload = body(manifest, source_snapshot_id, {'kind': 'TRAIN_DELAY',
        'occupancy_id': original['id'], 'delay_minutes': 10})
    created = scenario(client, payload)
    assert created['approval_permitted'] is False
    assert created['baseline_run']['status'] == created['optimized_run']['status'] == 'QUEUED'
    assert created['payload']['controller_approval'] == 'FORBIDDEN'
    copy_snapshot = client.get('/api/v1/snapshots/' + created['snapshot_id'], headers=auth()).json()['manifest']
    assert copy_snapshot['scenario_id'] == created['id']
    assert copy_snapshot['facts']['occupancy'][0]['enter_at'] == '2026-09-21T01:10:00+05:30'
    assert client.get('/api/v1/snapshots/' + source_snapshot_id,
        headers=auth()).json()['manifest'] == manifest
    operations = client.get('/api/v1/operations/occupancy', headers=auth(), params={
        'start': manifest['horizon_start'], 'end': manifest['horizon_end']}).json()['items']
    assert operations[0]['enter_at'] == original['enter_at']
    assert run_one() is not None
    assert run_one() is not None
    current = client.get('/api/v1/what-if-scenarios/' + created['id'], headers=auth()).json()
    assert current['baseline_run']['status'] == current['optimized_run']['status'] == 'COMPLETED'
    optimized = client.get('/api/v1/planning-runs/' + created['optimized_run']['id'], headers=auth()).json()
    assert optimized['result']['solver_status'] in ('OPTIMAL', 'FEASIBLE')
    assert optimized['result']['assignments']
    revision_response = client.post('/api/v1/plan-revisions', headers=auth(), json={
        'run_id': optimized['id'], 'expected_plan_hash': digest(optimized['result'])})
    assert revision_response.status_code == 201, revision_response.text
    revision = revision_response.json()
    report_response = client.post('/api/v1/validation-reports', headers=auth(), json={
        'plan_revision_id': revision['id'], 'expected_plan_hash': revision['plan_hash']})
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()
    assert report['status'] == 'PASS' and report['usable_for_review'], report
    baseline = client.get('/api/v1/planning-runs/' + created['baseline_run']['id'],
        headers=auth()).json()
    assert baseline['result']['assignments']
    baseline_revision_response = client.post('/api/v1/plan-revisions', headers=auth(), json={
        'run_id': baseline['id'], 'expected_plan_hash': digest(baseline['result'])})
    assert baseline_revision_response.status_code == 201, baseline_revision_response.text
    baseline_revision = baseline_revision_response.json()
    baseline_report = client.post('/api/v1/validation-reports', headers=auth(), json={
        'plan_revision_id': baseline_revision['id'],
        'expected_plan_hash': baseline_revision['plan_hash']})
    assert baseline_report.status_code == 201 and baseline_report.json()['status'] == 'PASS'
    comparison_response = client.post('/api/v1/plan-comparisons', headers=auth(), json={
        'baseline_plan_revision_id': baseline_revision['id'],
        'railsync_plan_revision_id': revision['id']})
    assert comparison_response.status_code == 201, comparison_response.text
    comparison = comparison_response.json()
    assert comparison['content']['scenario_id'] == created['id']
    assert comparison['content']['claim_scope'] == 'ISOLATED_SIMULATION_ONLY'
    assert 'SCENARIO_RESULTS_CANNOT_AUTHORIZE_POSSESSIONS' in comparison['content']['limits']
    impact_response = client.post(f"/api/v1/what-if-scenarios/{created['id']}/impacts",
        headers=auth(), json={'source_plan_revision_id': source_revision['id'],
            'scenario_plan_revision_id': revision['id']})
    assert impact_response.status_code == 201, impact_response.text
    impact = impact_response.json()
    assert impact['content']['comparison_type'] == 'INPUT_CHANGED_SCENARIO_IMPACT'
    assert impact['content']['changed_inputs'] == payload['changes']
    assert impact['content']['claims_permitted'] is False
    assert 'INPUTS_DIFFER_SO_DELTAS_ARE_NOT_OPTIMIZER_GAINS' in impact['content']['limits']
    repeated_impact = client.post(f"/api/v1/what-if-scenarios/{created['id']}/impacts",
        headers=auth(), json={'source_plan_revision_id': source_revision['id'],
            'scenario_plan_revision_id': revision['id']})
    assert repeated_impact.status_code == 201 and repeated_impact.json()['duplicate']
    approval = client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",
        headers=auth('CONTROLLER'), json=decision(revision, report))
    assert approval.status_code == 409 and 'SCENARIO_DECISION_FORBIDDEN' in approval.text
    with Session() as db:
        assert db.scalar(select(WhatIfScenario).where(WhatIfScenario.id == uuid.UUID(created['id'])))
        assert db.scalar(select(WhatIfImpact).where(WhatIfImpact.id == uuid.UUID(impact['id'])))
        assert not db.scalars(select(PlanReservation)).all()
        assert len(db.scalars(select(TrainRun)).all()) == 1
    actual_change = client.post('/api/v1/operations/train-runs', headers=auth(), json={
        'train_id': 'P-BASE', 'train_name': 'Baseline Passenger',
        'train_type': 'PASSENGER', 'service_date': '2026-09-21',
        'source_mode': 'SIMULATED', 'source_revision': 2,
        'occupancies': [{'track_id': 'AB', 'route_sequence': 1,
            'enter_at': '2026-09-21T01:02:00+05:30',
            'exit_at': '2026-09-21T01:22:00+05:30'}]})
    assert actual_change.status_code == 201
    stale = client.get('/api/v1/validation-reports/' + report['id'], headers=auth()).json()
    assert not stale['usable_for_review'] and 'OPERATIONAL_STATE_CHANGED' in stale['current_blockers']
    with pytest.raises(DBAPIError, match='IMMUTABLE_RECORD'):
        with engine.begin() as db: db.execute(text('DELETE FROM what_if_impacts'))
    if path := os.environ.get('RAILSYNC_M17_EVIDENCE_OUTPUT'):
        with open(path, 'w', encoding='utf-8') as output:
            json.dump({'fixture': 'SIMULATED source snapshot plus ten-minute train delay, real worker and independent validator',
                'scenario': current, 'source_occupancy': original,
                'scenario_occupancy': copy_snapshot['facts']['occupancy'][0],
                'optimized_run': optimized, 'validation': report, 'comparison': comparison,
                'impact': impact,
                'approval_blocked': approval.json()}, output, indent=2)


@pytest.mark.parametrize('kind', ['FREIGHT_COUNT', 'RESOURCE_OUTAGE',
    'RESTRICTION', 'ADD_REQUEST'])
def test_supported_overlays_change_only_scenario_facts(client, kind):
    manifest, revision, _ = prepare(client)
    if kind == 'FREIGHT_COUNT':
        change = {'kind': kind, 'external_id': 'FF-BASE', 'expected_count': 5}
    elif kind == 'RESOURCE_OUTAGE':
        change = {'kind': kind, 'resource_id': 'CREW-1', 'track_id': 'AB',
            'start_at': '2026-09-21T03:00:00+05:30',
            'end_at': '2026-09-21T03:10:00+05:30'}
    elif kind == 'RESTRICTION':
        change = {'kind': kind, 'track_ids': ['AB'],
            'start_at': '2026-09-21T03:00:00+05:30',
            'end_at': '2026-09-21T03:15:00+05:30',
            'rule_id': 'SYNTHETIC-SCENARIO', 'restriction_type': 'WORK_PROHIBITED'}
    else:
        change = {'kind': kind, 'request_id': str(uuid.uuid4()),
            'data': request_data(work_minutes=10, setup_minutes=5, restore_minutes=5,
                mandatory=False, power_state='ANY', signalling_state='ANY')}
    created = scenario(client, body(manifest, revision['snapshot_id'], change))
    altered = client.get('/api/v1/snapshots/' + created['snapshot_id'],
        headers=auth()).json()['manifest']['facts']
    if kind == 'FREIGHT_COUNT':
        assert altered['freight'][0]['expected_count'] == 5
        assert manifest['facts']['freight'][0]['expected_count'] == 1
    elif kind == 'RESOURCE_OUTAGE':
        assert len(altered['resources'][0]['profile']['payload']['duties']) == 1
        assert manifest['facts']['resources'][0]['profile']['payload']['duties'] == []
    elif kind == 'RESTRICTION':
        assert any(row['kind'] == 'restriction' and row['id'].startswith('WHATIF-')
            for row in altered['network'])
        assert all(row['kind'] != 'restriction' for row in manifest['facts']['network'])
    else:
        assert any(row['id'] == change['request_id'] for row in altered['requests'])
        assert all(row['id'] != change['request_id'] for row in manifest['facts']['requests'])
    with Session() as db:
        assert len(db.scalars(select(NetworkEntity)).all()) == len(manifest['facts']['network'])
        assert len(db.scalars(select(MaintenanceRequest)).all()) == 2
        assert not db.scalars(select(PlanReservation)).all()
    assert run_one() is not None
    assert run_one() is not None
    optimized = client.get('/api/v1/planning-runs/' + created['optimized_run']['id'], headers=auth()).json()
    assert optimized['status'] == 'COMPLETED'
    assert optimized['result']['snapshot_hash'] == digest(client.get(
        '/api/v1/snapshots/' + created['snapshot_id'], headers=auth()).json()['manifest'])


def test_scenario_rejects_bad_scope_stale_source_and_idempotency_conflicts(client):
    manifest, revision, _ = prepare(client)
    source_id = revision['snapshot_id']
    original = manifest['facts']['occupancy'][0]
    valid = body(manifest, source_id, {'kind': 'TRAIN_DELAY',
        'occupancy_id': original['id'], 'delay_minutes': 5})
    invalid = client.post('/api/v1/what-if-scenarios', headers=auth(), json={**valid,
        'changes': [{'kind': 'TRAIN_DELAY', 'occupancy_id': str(uuid.uuid4()),
            'delay_minutes': 5}]})
    assert invalid.status_code == 422
    created = scenario(client, valid)
    repeated = client.post('/api/v1/what-if-scenarios', headers=auth(), json=valid)
    assert repeated.status_code == 202 and repeated.json()['duplicate']
    assert repeated.json()['id'] == created['id']
    changed = client.post('/api/v1/what-if-scenarios', headers=auth(), json={**valid,
        'changes': [{'kind': 'TRAIN_DELAY', 'occupancy_id': original['id'],
            'delay_minutes': 6}]})
    assert changed.status_code == 409 and 'SCENARIO_IDEMPOTENCY_CONFLICT' in changed.text
    nested = client.post('/api/v1/what-if-scenarios', headers=auth(),
        json={**valid, 'idempotency_key': str(uuid.uuid4()),
            'source_snapshot_id': created['snapshot_id'],
            'expected_source_hash': digest(client.get('/api/v1/snapshots/' + created['snapshot_id'],
                headers=auth()).json()['manifest'])})
    assert nested.status_code == 409
    source_changed = client.post('/api/v1/operations/train-runs', headers=auth(), json={
        'train_id': 'P-BASE', 'train_name': 'Baseline Passenger',
        'train_type': 'PASSENGER', 'service_date': '2026-09-21',
        'source_mode': 'SIMULATED', 'source_revision': 2,
        'occupancies': [{'track_id': 'AB', 'route_sequence': 1,
            'enter_at': '2026-09-21T01:01:00+05:30',
            'exit_at': '2026-09-21T01:21:00+05:30'}]})
    assert source_changed.status_code == 201
    stale = client.post('/api/v1/what-if-scenarios', headers=auth(), json={**valid,
        'idempotency_key': str(uuid.uuid4())})
    assert stale.status_code == 409 and 'SCENARIO_SOURCE_STALE' in stale.text
    new_job = client.post('/api/v1/planning-runs', headers=auth(), json={
        'snapshot_id': created['snapshot_id'], 'planner_type': 'BASELINE'})
    assert new_job.status_code == 409 and 'SCENARIO_SOURCE_STALE' in new_job.text
    assert run_one() is not None
    assert run_one() is not None
    superseded = client.get('/api/v1/what-if-scenarios/' + created['id'], headers=auth()).json()
    assert superseded['baseline_run']['status'] == superseded['optimized_run']['status'] == 'SUPERSEDED'
    with pytest.raises(DBAPIError, match='IMMUTABLE_RECORD'):
        with engine.begin() as db: db.execute(text('DELETE FROM what_if_scenarios'))
