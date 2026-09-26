"""Durable preparation, idempotency, real paired solving and failure boundaries."""
import json
import os
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.db import Session, engine
from railsync.models import PlanningRun, PlanningSession
from railsync.planning import run_one
from railsync.planning_sessions import prepare_one
from railsync import planning_sessions
from railsync.requests import digest
from test_m12 import NOW
from test_m13 import prepare


def session_body(manifest, revision, key=None):
    return {'idempotency_key': str(key or uuid.uuid4()), 'snapshot_id': revision['snapshot_id'],
        'expected_snapshot_hash': digest(manifest),
        'solver_options': {'max_time_seconds': 2, 'weights': {'possession': 2}}}


def create(client, body):
    response = client.post('/api/v1/planning-sessions', headers=auth(), json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_idempotent_planning_session_actual_pair_and_shared_artifacts(client):
    manifest, revision, _ = prepare(client)
    body = session_body(manifest, revision)
    created = create(client, body)
    assert created['status'] == 'QUEUED_PREPARATION' and created['runs'] == []
    repeated = create(client, body)
    assert repeated['id'] == created['id'] and repeated['duplicate']
    changed = {**body, 'solver_options': {'max_time_seconds': 0}}
    assert client.post('/api/v1/planning-sessions', headers=auth(), json=changed).status_code == 409
    assert prepare_one(NOW) == created['id']
    ready = client.get('/api/v1/planning-sessions/' + created['id'], headers=auth()).json()
    assert ready['preparation_status'] == 'PREPARED' and ready['status'] == 'QUEUED_SOLVE'
    assert {r['planner_type'] for r in ready['runs']} == {'BASELINE', 'CP_SAT'}
    configs = [client.get('/api/v1/planning-runs/' + r['id'], headers=auth()).json()['config'] for r in ready['runs']]
    assert configs[0]['coordination_id'] == configs[1]['coordination_id'] == ready['artifacts']['coordination_id']
    assert configs[0]['solver_options'] == configs[1]['solver_options']
    assert configs[0]['solver_options']['weights']['possession'] == 2
    assert run_one() and run_one()
    solved = client.get('/api/v1/planning-sessions/' + created['id'], headers=auth()).json()
    assert solved['status'] == 'COMPLETED' and all(r['status'] == 'COMPLETED' for r in solved['runs'])
    optimized_id = next(r['id'] for r in solved['runs'] if r['planner_type'] == 'CP_SAT')
    optimized = client.get('/api/v1/planning-runs/' + optimized_id, headers=auth()).json()
    assert optimized['result_hash'] == digest(optimized['result'])
    assert next(r for r in solved['runs'] if r['id'] == optimized_id)['result_hash'] == optimized['result_hash']
    assert optimized['result']['solver_status'] in ('FEASIBLE', 'OPTIMAL')
    assert optimized['result']['assignments']
    assert solved['validation'] == 'SEPARATE_REQUIRED_STEP'
    # A deliberate fresh run reuses immutable candidate artifacts, not a canned solution.
    another = create(client, session_body(manifest, revision))
    assert prepare_one(NOW) == another['id']
    fresh = client.get('/api/v1/planning-sessions/' + another['id'], headers=auth()).json()
    assert fresh['artifacts'] == ready['artifacts']
    assert {r['id'] for r in fresh['runs']}.isdisjoint({r['id'] for r in solved['runs']})
    assert all(r['status'] == 'QUEUED' and r['solver_status'] is None for r in fresh['runs'])
    first_page = client.get('/api/v1/workspace/planning-sessions', headers=auth(),
        params={'snapshot_id': revision['snapshot_id'], 'limit': 1}).json()
    assert first_page['next_cursor']
    next_page = client.get('/api/v1/workspace/planning-sessions', headers=auth(),
        params={'snapshot_id': revision['snapshot_id'], 'limit': 1, 'cursor': first_page['next_cursor']}).json()
    assert next_page['items'][0]['id'] != first_page['items'][0]['id']
    with pytest.raises(DBAPIError, match='IMMUTABLE_SESSION_REQUEST'):
        with engine.begin() as db: db.execute(text("UPDATE planning_sessions SET payload='{}'::jsonb"))
    if output := os.environ.get('RAILSYNC_M18_PLANNING_EVIDENCE_OUTPUT'):
        Path(output).write_text(json.dumps({'fixture': 'SIMULATED, durable request, real pipeline and workers',
            'queued': created, 'prepared': ready, 'completed': solved,
            'optimized_result': optimized['result'], 'duplicate_session_id': repeated['id'],
            'repeat_new_jobs': fresh}, indent=2), encoding='utf-8')


def test_worker_interruption_rolls_back_preparation_then_can_resume(client, monkeypatch):
    manifest, revision, _ = prepare(client)
    created = create(client, session_body(manifest, revision))
    original = planning_sessions.queue_proposal
    with Session() as db: before = db.scalar(select(func.count()).select_from(PlanningRun))
    def crash(*args, **kwargs):
        original(*args, **kwargs)
        raise KeyboardInterrupt('simulate worker interruption before commit')
    monkeypatch.setattr(planning_sessions, 'queue_proposal', crash)
    with pytest.raises(KeyboardInterrupt): prepare_one(NOW)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(PlanningRun)) == before
        row = db.get(PlanningSession, uuid.UUID(created['id']))
        assert row.status == 'QUEUED_PREPARATION' and row.baseline_run_id is None
    monkeypatch.setattr(planning_sessions, 'queue_proposal', original)
    assert prepare_one(NOW) == created['id']
    assert client.get('/api/v1/planning-sessions/' + created['id'], headers=auth()).json()['preparation_status'] == 'PREPARED'


def test_queued_session_rechecks_changed_sources_without_publishing_runs(client):
    manifest, revision, _ = prepare(client)
    created = create(client, session_body(manifest, revision))
    response = client.post('/api/v1/operations/train-runs', headers=auth(), json={
        'train_id': 'P-BASE', 'train_name': 'Baseline Passenger', 'train_type': 'PASSENGER',
        'service_date': '2026-09-21', 'source_mode': 'SIMULATED', 'source_revision': 2,
        'occupancies': [{'track_id': 'AB', 'route_sequence': 1,
            'enter_at': '2026-09-21T01:02:00+05:30', 'exit_at': '2026-09-21T01:22:00+05:30'}]})
    assert response.status_code == 201
    assert prepare_one(NOW) == created['id']
    blocked = client.get('/api/v1/planning-sessions/' + created['id'], headers=auth()).json()
    assert blocked['status'] == 'BLOCKED' and blocked['runs'] == []
    assert blocked['error']['detail'] == 'SNAPSHOT_SOURCE_STALE_OR_UNKNOWN'
    assert create(client, session_body(manifest, revision, body_key := uuid.UUID(created['request']['idempotency_key'])))['id'] == created['id']
    response = client.post('/api/v1/planning-sessions', headers=auth(), json=session_body(manifest, revision))
    assert response.status_code == 409


def test_failed_preparation_visible_without_fabricated_runs(client, monkeypatch):
    manifest, revision, _ = prepare(client)
    created = create(client, session_body(manifest, revision))
    def fail(*args, **kwargs): raise RuntimeError('private connection secret is not public evidence')
    monkeypatch.setattr(planning_sessions, 'queue_proposal', fail)
    prepare_one(NOW)
    response = client.get('/api/v1/planning-sessions/' + created['id'], headers=auth())
    assert response.json()['status'] == 'FAILED' and response.json()['runs'] == []
    assert response.json()['error'] == {'code': 'PREPARATION_ERROR', 'exception_type': 'RuntimeError'}
    assert 'private connection' not in response.text


def test_concurrent_duplicate_creation_and_workers_do_not_duplicate_pipeline(client):
    manifest, revision, _ = prepare(client)
    body = session_body(manifest, revision)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post('/api/v1/planning-sessions', headers=auth(), json=body), range(2)))
    assert all(r.status_code == 202 for r in responses), [r.text for r in responses]
    assert responses[0].json()['id'] == responses[1].json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared = list(pool.map(lambda _: prepare_one(NOW), range(2)))
    assert sum(x is not None for x in prepared) == 1
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(PlanningSession)) == 1


def test_planning_session_authorization_and_wrong_hash(client):
    manifest, revision, _ = prepare(client)
    body = session_body(manifest, revision)
    for role in ('ENGINEERING', 'CONTROLLER', 'AUDITOR'):
        assert client.post('/api/v1/planning-sessions', headers=auth(role), json=body).status_code == 403
    assert client.post('/api/v1/planning-sessions', headers=auth(),
        json={**body, 'expected_snapshot_hash': '0' * 64}).status_code == 409
    assert client.get('/api/v1/workspace/planning-sessions', headers=auth('ENGINEERING'),
        params={'snapshot_id': revision['snapshot_id']}).status_code == 403
