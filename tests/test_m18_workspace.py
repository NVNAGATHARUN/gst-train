"""Workspace values must come from one chosen saved snapshot/plan, never live UI defaults."""
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
import pytest
from sqlalchemy import select
from conftest import auth
from railsync.db import Session
from railsync.main import app
from railsync.models import PlanRevision, PlanningSnapshot, PriorityAssessment
from railsync.requests import digest
from railsync.validation import utc_now
from railsync.workspace import access_requirements
from test_m12 import NOW
from test_m13 import prepare


def test_workspace_exact_saved_values_access_readiness_and_stale_transition(client):
    manifest, revision, report = prepare(client)
    url = f"/api/v1/snapshots/{revision['snapshot_id']}/workspace"
    response = client.get(url, headers=auth(), params={'plan_revision_id': revision['id']})
    assert response.status_code == 200, response.text
    view = response.json()
    assert view['facts'] == manifest['facts']
    assert view['selected_revision']['content'] == revision['content']
    assert view['validation']['id'] == report['id']
    assert view['source_state'] == 'CURRENT' and view['current_blockers'] == []
    assert view['availability'] and view['opportunity'] and view['coordination']
    assert view['authority'] == 'SOFTWARE_PROPOSAL_ONLY'
    for item in view['demands']:
        raw = next(r for r in manifest['facts']['requests'] if r['id'] == item['request_id'])
        assert item['request'] == raw['payload']
        assert item['access_requirements']['line_block'] == ('REQUIRED' if raw['payload']['block_required'] else 'NOT_REQUIRED')
        assert item['access_requirements']['provision_status'] == 'NOT_EVIDENCED'
        assert item['readiness']['execution_authorized'] is False
        if item['scheduling_outcome'] == 'SCHEDULED':
            assert item['readiness']['status'] == 'READY'
            assert item['readiness']['selected_candidate_ids']
            assert item['priority']['method'] == 'RULE'
    # A later assessment must not silently replace the saved run's priority context.
    with Session.begin() as db:
        rid = uuid.UUID(view['demands'][0]['request_id'])
        db.add(PriorityAssessment(snapshot_id=uuid.UUID(revision['snapshot_id']), request_id=rid,
            policy_version='UNRELATED-LATER', method='RULE', score_basis_points=1,
            priority_band='LOW', features={}, contributions={}, assessed_at=NOW + timedelta(days=1)))
    again = client.get(url, headers=auth(), params={'plan_revision_id': revision['id']}).json()
    assert again['demands'][0]['priority'] == view['demands'][0]['priority']
    app.dependency_overrides[utc_now] = lambda: NOW + timedelta(days=1)
    stale = client.get(url, headers=auth(), params={'plan_revision_id': revision['id']}).json()
    assert stale['source_state'] == 'BLOCKED' and not stale['validation']['usable_for_review']
    assert all(d['readiness']['status'] != 'READY' for d in stale['demands'])
    assert stale['selected_revision']['content'] == revision['content']
    if output := os.environ.get('RAILSYNC_M18_WORKSPACE_EVIDENCE_OUTPUT'):
        Path(output).write_text(json.dumps({'fixture': 'SIMULATED; genuine solved/validated saved proposal',
            'workspace': view, 'stale_blockers': stale['current_blockers'],
            'stale_readiness': [d['readiness'] for d in stale['demands']]}, indent=2), encoding='utf-8')


def test_workspace_explicit_selection_never_invents_plan_or_combines_snapshots(client):
    _, revision, _ = prepare(client)
    sid = revision['snapshot_id']
    plain = client.get(f'/api/v1/snapshots/{sid}/workspace', headers=auth()).json()
    assert plain['selected_run'] is None and plain['selected_revision'] is None
    assert plain['availability'] == [] and plain['validation'] is None
    assert all(d['readiness']['status'] == 'NOT_ASSESSED' for d in plain['demands'])
    assert all(d['priority'] is None for d in plain['demands'])
    with Session() as db:
        other = db.scalar(select(PlanningSnapshot).where(PlanningSnapshot.id != uuid.UUID(sid)))
        other_id = str(other.id)
    mixed = client.get(f'/api/v1/snapshots/{other_id}/workspace', headers=auth(),
        params={'plan_revision_id': revision['id']})
    assert mixed.status_code == 409 and mixed.json()['detail'] == 'WORKSPACE_ARTIFACT_MISMATCH'
    assert client.get(f'/api/v1/snapshots/{sid}/workspace', headers=auth(),
        params={'run_id': str(uuid.uuid4())}).status_code == 404
    assert client.get(f'/api/v1/snapshots/{sid}/workspace', headers=auth(),
        params={'plan_revision_id': revision['id'], 'run_id': str(uuid.uuid4())}).status_code == 409


def test_workspace_pagination_filters_and_query_bound_cursors(client):
    _, revision, _ = prepare(client)
    pages = []
    params = {'limit': 1, 'scenario': 'SOURCE', 'track_id': 'AB'}
    while True:
        response = client.get('/api/v1/workspace/snapshots', headers=auth(), params=params)
        assert response.status_code == 200, response.text
        page = response.json(); pages.extend(page['items'])
        if not page['next_cursor']: break
        params['cursor'] = page['next_cursor']
    assert len(pages) >= 2 and len({x['id'] for x in pages}) == len(pages)
    assert client.get('/api/v1/workspace/snapshots', headers=auth(),
        params={'track_id': 'DOES-NOT-EXIST'}).json()['items'] == []
    assert client.get('/api/v1/workspace/snapshots', headers=auth(),
        params={'scenario': 'SCENARIO'}).json()['items'] == []
    assert client.get('/api/v1/workspace/snapshots', headers=auth(),
        params={**params, 'track_id': 'DIFFERENT'}).status_code == 422
    assert client.get('/api/v1/workspace/snapshots', headers=auth(), params={'cursor': '!'}).status_code == 422
    assert client.get('/api/v1/workspace/snapshots', headers=auth(), params={'limit': 101}).status_code == 422
    listed = client.get('/api/v1/workspace/runs', headers=auth(),
        params={'snapshot_id': revision['snapshot_id']}).json()
    selected = next(r for r in listed['items'] if r['id'] == revision['run_id'])
    assert selected['job_status'] == 'COMPLETED' and selected['solver_status'] in ('FEASIBLE', 'OPTIMAL')
    assert revision['id'] in selected['revision_ids'] and selected['has_incumbent']


@pytest.mark.parametrize('route', ['/api/v1/workspace/snapshots',
    '/api/v1/workspace/runs?snapshot_id=00000000-0000-0000-0000-000000000000',
    '/api/v1/snapshots/00000000-0000-0000-0000-000000000000/workspace'])
def test_workspace_department_cannot_read_cross_department_aggregate(client, route):
    assert client.get(route).status_code == 401
    assert client.get(route, headers=auth('ENGINEERING')).status_code == 403
    assert client.get(route, headers=auth('TRD')).status_code == 403


def test_access_requirements_unknown_is_not_invented_disconnection_or_grant():
    unknown = access_requirements({})
    assert unknown['line_block'] == unknown['power_block'] == unknown['snt_disconnection'] == 'UNKNOWN'
    actual = access_requirements({'block_required': True, 'power_block_required': True,
        'isolation_zone': 'EZ-1', 'signalling_state': 'DISCONNECTED'})
    assert actual['line_block'] == actual['power_block'] == actual['snt_disconnection'] == 'REQUIRED'
    assert actual['electrical_isolation_zone'] == 'EZ-1'
    assert actual['provision_status'] == 'NOT_EVIDENCED'
