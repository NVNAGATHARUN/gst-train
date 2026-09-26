"""M16 event-to-fact reconciliation and atomic rolling proposal preparation."""
import copy
import json
import os
import uuid
from datetime import timedelta
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
import pytest
from conftest import auth
from railsync.db import Session, engine
from railsync.main import app
from railsync.models import EventReconciliation, PlanReservation
from railsync.planning import run_one
from railsync.requests import digest
from railsync.validation import utc_now
from test_m12 import NOW
from test_m16_events import event
from test_m16_execution import approved
from test_m16_replanning import urgent_request
from test_m13 import decision


def setup(client):
    manifest, parent, _, approval, _, _ = approved(client)
    recorded = client.post('/api/v1/disruption-events', headers=auth('CONTROLLER'),
        json=event(kind='URGENT_DEFECT', external_id='urgent-01'))
    assert recorded.status_code == 201, recorded.text
    app.dependency_overrides[utc_now] = lambda: NOW + timedelta(seconds=6)
    return manifest, parent, recorded.json(), approval


def prepare_body(client, manifest, parent):
    preview = client.get('/api/v1/rolling-replans/preview/' + parent['id'],
        headers=auth()).json()
    context = {key: value for key, value in manifest['validation_context'].items()
        if key != 'facts_hash'}
    context['received_at'] = (NOW + timedelta(seconds=6)).isoformat()
    context['commitments_known_empty'] = False
    return preview, {'idempotency_key': str(uuid.uuid4()),
        'source_plan_revision_id': parent['id'],
        'expected_plan_hash': parent['plan_hash'],
        'expected_operational_revision': 3,
        'expected_batch_generation': preview['batch_generation'],
        'expected_base_facts_hash': preview['base_facts_hash'],
        'validation_context': context}


def test_unreconciled_event_blocks_and_urgent_source_update_queues_real_runs(client):
    manifest, parent, recorded, approval = setup(client)
    preview, body = prepare_body(client, manifest, parent)
    assert preview['status'] == 'BLOCKED'
    assert preview['events'][0]['status'] == 'SOURCE_CHANGE_UNVERIFIED'
    blocked = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert blocked.status_code == 409 and 'EVENT_SOURCE_CHANGE_UNVERIFIED' in blocked.text
    urgent = urgent_request(client)
    preview, body = prepare_body(client, manifest, parent)
    assert preview['status'] == 'READY'
    assert preview['events'][0]['matches'][0]['source_id'] == urgent
    unauthorized = client.post('/api/v1/rolling-replans', headers=auth(), json=body)
    assert unauthorized.status_code == 403
    mismatch = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'),
        json={**body, 'validation_context': {**body['validation_context'],
            'clearance_after_minutes': 6}})
    assert mismatch.status_code == 422 and 'ASYMMETRIC_CLEARANCE' in mismatch.text
    prepared = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert prepared.status_code == 202, prepared.text
    proposal = prepared.json()
    assert proposal['baseline_run']['status'] == proposal['optimized_run']['status'] == 'QUEUED'
    assert proposal['payload']['events'][0]['event_id'] == recorded['id']
    assert proposal['payload']['priority_count'] == 3
    assert proposal['payload']['controller_approval'] == 'REQUIRED'
    duplicate = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert duplicate.status_code == 202 and duplicate.json()['duplicate']
    assert duplicate.json()['id'] == proposal['id']
    second = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'),
        json={**body, 'idempotency_key': str(uuid.uuid4())})
    assert second.status_code == 409 and 'REPLAN_ALREADY_PREPARED' in second.text
    assert client.get('/api/v1/rolling-replans/preview/' + parent['id'],
        headers=auth()).json()['prepared_replan_id'] == proposal['id']
    conflict = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'),
        json={**body, 'expected_base_facts_hash': '0'*64})
    assert conflict.status_code == 409 and 'REPLAN_IDEMPOTENCY_CONFLICT' in conflict.text
    with Session() as db:
        assert db.scalar(select(EventReconciliation).where(EventReconciliation.id == uuid.UUID(proposal['id'])))
        assert all(r.active for r in db.scalars(select(PlanReservation)))
    assert run_one() is not None
    assert run_one() is not None
    result = client.get('/api/v1/rolling-replans/' + proposal['id'], headers=auth()).json()
    assert result['baseline_run']['status'] == result['optimized_run']['status'] == 'COMPLETED'
    optimized = client.get('/api/v1/planning-runs/' + result['optimized_run']['id'], headers=auth()).json()
    assert optimized['result']['has_incumbent']
    assert urgent in {r for a in optimized['result']['assignments'] for r in a['request_ids']}
    revision_response = client.post('/api/v1/plan-revisions', headers=auth(), json={
        'run_id': optimized['id'], 'expected_plan_hash': digest(optimized['result'])})
    assert revision_response.status_code == 201, revision_response.text
    revision = revision_response.json()
    assert revision['parent_id'] == parent['id']
    report_response = client.post('/api/v1/validation-reports', headers=auth(), json={
        'plan_revision_id': revision['id'], 'expected_plan_hash': revision['plan_hash']})
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()
    assert report['status'] == 'PASS' and report['usable_for_review'], report
    decision_response = client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",
        headers=auth('CONTROLLER'), json=decision(revision, report, expected=3,
            supersedes_decision_id=approval['id']))
    assert decision_response.status_code == 201, decision_response.text
    assert decision_response.json()['result']['replacement']['source_decision_id'] == approval['id']
    if path := os.environ.get('RAILSYNC_M16_ROLLING_EVIDENCE_OUTPUT'):
        with open(path, 'w', encoding='utf-8') as output:
            json.dump({'fixture': 'SIMULATED urgent defect after event; actual source update, candidate generation, worker solves, validator and controller approval',
                'event': recorded, 'preview': preview, 'reconciliation': result,
                'optimized_run': optimized, 'validation': report,
                'replacement_decision': decision_response.json(),
                'urgent_request_id': urgent}, output, indent=2)
    for table in ('event_reconciliations',):
        with pytest.raises(DBAPIError, match='IMMUTABLE_RECORD'):
            with engine.begin() as db: db.execute(text('DELETE FROM ' + table))


def test_stale_preview_and_batch_debounce_fail_closed(client):
    manifest, parent, _, _ = setup(client)
    urgent_request(client)
    preview, body = prepare_body(client, manifest, parent)
    assert preview['status'] == 'READY'
    early = client.post('/api/v1/disruption-events', headers=auth('CONTROLLER'),
        json=event(kind='URGENT_DEFECT', external_id='urgent-01', source_revision=2))
    assert early.status_code == 201, early.text
    stale = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert stale.status_code == 409
    assert 'BATCH_DEBOUNCING' in stale.text


@pytest.mark.parametrize('kind', ['TRAIN_DELAY', 'FREIGHT_CHANGE',
    'RESOURCE_OUTAGE', 'RESTRICTION_CHANGE'])
def test_source_revisions_reconcile_only_after_actual_matching_change(client, kind):
    manifest, parent, _, _, _, _ = approved(client)
    recorded = client.post('/api/v1/disruption-events', headers=auth('CONTROLLER'),
        json=event(kind=kind, external_id='source-'+kind,
            resource_ids=['CREW-1'] if kind == 'RESOURCE_OUTAGE' else []))
    assert recorded.status_code == 201, recorded.text
    app.dependency_overrides[utc_now] = lambda: NOW + timedelta(seconds=6)
    route = '/api/v1/rolling-replans/preview/' + parent['id']
    assert client.get(route, headers=auth()).json()['events'][0]['status'] == 'SOURCE_CHANGE_UNVERIFIED'
    if kind == 'TRAIN_DELAY':
        changed = client.post('/api/v1/operations/train-runs', headers=auth(), json={
            'train_id': 'P-BASE', 'train_name': 'Baseline Passenger',
            'train_type': 'PASSENGER', 'service_date': '2026-09-21',
            'source_mode': 'SIMULATED', 'source_revision': 2,
            'occupancies': [{'track_id': 'AB', 'route_sequence': 1,
                'enter_at': '2026-09-21T01:05:00+05:30',
                'exit_at': '2026-09-21T01:25:00+05:30'}]})
    elif kind == 'FREIGHT_CHANGE':
        changed = client.post('/api/v1/operations/freight-forecasts', headers=auth(), json={
            'external_id': 'FF-BASE', 'source_revision': 2, 'track_id': 'AB',
            'start_at': '2026-09-21T03:00:00+05:30',
            'end_at': '2026-09-21T03:30:00+05:30',
            'issued_at': '2026-09-21T00:00:00+05:30', 'expected_count': 3,
            'confidence': 0.6, 'uncertainty_semantics': 'protected synthetic envelope',
            'source_mode': 'SIMULATED'})
    elif kind == 'RESOURCE_OUTAGE':
        profile = copy.deepcopy(next(r for r in manifest['facts']['resources']
            if r['id'] == 'CREW-1')['profile']['payload'])
        profile['duties'].append({'track_id': 'AB',
            'start_at': '2026-09-21T03:00:00+05:30',
            'end_at': '2026-09-21T03:10:00+05:30'})
        changed = client.post('/api/v1/resources/CREW-1/profiles', headers=auth(),
            json={'expected_revision': 1, 'data': profile})
    else:
        changed = client.post('/api/v1/network/restriction', headers=auth(), json={
            'id': 'EVENT-RESTRICTION', 'data': {'footprint': ['AB'],
                'start': '2026-09-21T03:00:00+05:30',
                'end': '2026-09-21T03:15:00+05:30',
                'rule_id': 'SYNTHETIC-EVENT-RULE', 'type': 'WORK_PROHIBITED'}})
    assert changed.status_code == 201, changed.text
    preview = client.get(route, headers=auth()).json()
    assert preview['status'] == 'READY', preview
    assert preview['events'][0]['matches']
    assert preview['events'][0]['event_id'] == recorded.json()['id']
    _, body = prepare_body(client, manifest, parent)
    prepared = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert prepared.status_code == 202, prepared.text
    assert run_one() is not None
    assert run_one() is not None
    optimized = client.get('/api/v1/planning-runs/' + prepared.json()['optimized_run']['id'],
        headers=auth()).json()
    assert optimized['status'] == 'COMPLETED'
    if kind == 'TRAIN_DELAY':
        assert optimized['result']['solver_status'] == 'INFEASIBLE'
        assert not optimized['result']['has_incumbent']
        assert optimized['result']['assignments'] == []
    else:
        assert optimized['result']['solver_status'] in ('OPTIMAL', 'FEASIBLE')


def test_rolling_horizon_extends_source_snapshot_with_retained_history(client):
    manifest, parent, _, _ = setup(client)
    urgent_request(client)
    extended = '2026-09-21T05:00:00+05:30'
    route = '/api/v1/rolling-replans/preview/' + parent['id']
    preview = client.get(route, headers=auth(), params={'horizon_end': extended}).json()
    assert preview['status'] == 'READY'
    _, body = prepare_body(client, manifest, parent)
    body['horizon_end'] = extended
    body['expected_base_facts_hash'] = preview['base_facts_hash']
    result = client.post('/api/v1/rolling-replans', headers=auth('CONTROLLER'), json=body)
    assert result.status_code == 202, result.text
    snapshot = client.get('/api/v1/snapshots/' + result.json()['snapshot_id'],
        headers=auth()).json()['manifest']
    assert snapshot['horizon_start'] == manifest['horizon_start']
    assert snapshot['horizon_end'] == extended
    assert snapshot['facts']['replanning'][0]['payload']['source_plan_revision_id'] == parent['id']
    assert client.get(route, headers=auth(), params={
        'horizon_end': '2026-09-21T03:00:00+05:30'}).status_code == 422
    assert client.get(route, headers=auth(), params={
        'horizon_end': '2026-11-01T04:00:00+05:30'}).status_code == 422
