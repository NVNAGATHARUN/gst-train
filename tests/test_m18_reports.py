"""M18 read-only report discovery and append-only audit projections."""
import uuid
from datetime import timedelta
from sqlalchemy import select
from conftest import auth
from railsync.db import Session
from railsync.models import AuditEvent, PlanningSchedule, PlanComparison
from railsync.requests import digest
from test_m12 import NOW
from test_m13 import prepare


def test_report_artifacts_are_bound_to_one_hash_checked_revision(client):
    _, revision, report = prepare(client)
    schedule_content = {'status': 'VALIDATED_TENTATIVE_PROPOSAL', 'counts': {'assignments': 1},
        'authority': 'SOFTWARE_PROPOSAL_ONLY'}
    comparison_content = {'status': 'VALIDATED_COMPARISON', 'claim_scope': 'SOURCE_SNAPSHOT_PROPOSAL',
        'claims_permitted': True, 'metric_version': 'KPI_V2',
        'metrics': {'requests_scheduled': {'unit': 'requests', 'baseline': 1, 'railsync': 1,
            'raw_delta': 0, 'status': 'COMPUTED'}}}
    with Session.begin() as db:
        schedule = PlanningSchedule(plan_revision_id=uuid.UUID(revision['id']), schedule_type='WEEKLY',
            timezone_name='Asia/Kolkata', period_start=NOW, period_end=NOW + timedelta(days=7),
            content_hash=digest(schedule_content), content=schedule_content, created_by='test', created_at=NOW)
        comparison = PlanComparison(baseline_plan_revision_id=uuid.UUID(revision['id']),
            railsync_plan_revision_id=uuid.UUID(revision['id']), content_hash=digest(comparison_content),
            content=comparison_content, created_by='test', created_at=NOW)
        db.add_all([schedule, comparison]); db.flush()
        schedule_id, comparison_id = str(schedule.id), str(comparison.id)
    response = client.get('/api/v1/workspace/report-artifacts', headers=auth('AUDITOR'),
        params={'plan_revision_id': revision['id']})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['revision']['id'] == revision['id']
    assert payload['revision']['plan_hash'] == revision['plan_hash']
    assert payload['revision']['snapshot_hash'] == payload['revision']['snapshot_content_hash']
    assert payload['validations'][0]['id'] == report['id']
    assert payload['schedules'][0]['id'] == schedule_id
    assert payload['comparisons'][0]['id'] == comparison_id
    assert payload['comparisons'][0]['metrics'] == comparison_content['metrics']
    assert payload['authority'] == 'READ_ONLY_EVIDENCE'
    assert client.get('/api/v1/workspace/report-artifacts', headers=auth('ENGINEERING'),
        params={'plan_revision_id': revision['id']}).status_code == 403
    assert client.get('/api/v1/workspace/report-artifacts', headers=auth(),
        params={'plan_revision_id': uuid.uuid4()}).status_code == 404


def test_audit_projection_is_paginated_filter_bound_and_role_guarded(client):
    _, revision, _ = prepare(client)
    exact = client.get('/api/v1/workspace/audit-events', headers=auth('AUDITOR'),
        params={'action': 'PLAN_REVISION_CREATED', 'entity': revision['id']})
    assert exact.status_code == 200, exact.text
    events = exact.json()['items']
    assert len(events) == 1 and events[0]['action'] == 'PLAN_REVISION_CREATED'
    assert events[0]['entity'] == revision['id'] and events[0]['data']['plan_hash'] == revision['plan_hash']
    first = client.get('/api/v1/workspace/audit-events', headers=auth('AUDITOR'), params={'limit': 1}).json()
    assert len(first['items']) == 1 and first['next_cursor']
    second = client.get('/api/v1/workspace/audit-events', headers=auth('AUDITOR'),
        params={'limit': 1, 'cursor': first['next_cursor']})
    assert second.status_code == 200 and second.json()['items'][0]['id'] != first['items'][0]['id']
    mismatch = client.get('/api/v1/workspace/audit-events', headers=auth('AUDITOR'),
        params={'limit': 1, 'action': 'PLAN_REVISION_CREATED', 'cursor': first['next_cursor']})
    assert mismatch.status_code == 422
    assert client.get('/api/v1/workspace/audit-events', headers=auth('ENGINEERING')).status_code == 403
    with Session() as db:
        saved = db.scalar(select(AuditEvent).where(AuditEvent.id == uuid.UUID(events[0]['id'])))
        assert saved.action == events[0]['action']
