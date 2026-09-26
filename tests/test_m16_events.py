"""M16 event-intake slice. Full M16 is not gated by these tests."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.main import app
from railsync.db import Session,engine
from railsync.models import PlanReservation,PlanningRun,OperationalState
from railsync.planning import claim_run,execute_run,publish_run
from railsync.validation import utc_now
from test_m12 import NOW
from test_m13 import prepare,decision


def event(**changes):
    return {'source':'SYNTHETIC_CONTROL_OFFICE','external_id':'delay-01','source_revision':1,
        'scope':'SIMULATED','kind':'TRAIN_DELAY','occurred_at':NOW.isoformat(),
        'track_ids':['AB'],'resource_ids':[],
        'evidence_reference':'SYNTHETIC M16 event fixture',
        'description':'Delay observed; updated occupancy and new validation required',**changes}


def test_event_invalidates_approved_plan_without_releasing_reservations(client):
    _,revision,report=prepare(client)
    approved=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(revision,report))
    assert approved.status_code==201,approved.text
    saved=client.post('/api/v1/disruption-events',headers=auth('CONTROLLER'),json=event())
    assert saved.status_code==201,saved.text
    result=saved.json()
    assert result['result']['source_facts_applied'] is False
    assert result['received_at']==NOW.isoformat()
    assert revision['snapshot_id'] in result['result']['invalidated_snapshot_ids']
    current=client.get('/api/v1/validation-reports/'+report['id'],headers=auth()).json()
    assert current['status']=='PASS' and not current['usable_for_review']
    assert 'SNAPSHOT_INVALIDATED_BY_EVENT' in current['current_blockers']
    view=client.get('/api/v1/plan-revisions/'+revision['id'],headers=auth()).json()
    assert view['current_state']['status']=='STALE_REQUIRES_ATTENTION'
    assert view['content']==revision['content']
    blocked=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(revision,report,expected=2))
    assert blocked.status_code==409 and 'SNAPSHOT_INVALIDATED_BY_EVENT' in blocked.text
    with Session() as db:
        reservations=db.scalars(select(PlanReservation)).all()
        assert reservations and all(r.active and r.scope=='SIMULATED' for r in reservations)
        assert db.get(OperationalState,'OPERATIONAL') is None
    if path:=os.environ.get('RAILSYNC_M16_EVENTS_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED actual solved, validated and approved proposal; event intake only',
                'event':result,'plan_state':view['current_state'],'validation':current,
                'reservations_preserved':True},output,indent=2)


def test_pending_and_running_jobs_are_superseded_and_late_result_is_fenced(client):
    _,revision,_=prepare(client)
    config=client.get('/api/v1/planning-runs/'+revision['run_id'],headers=auth()).json()['config']
    first=client.post('/api/v1/planning-runs',headers=auth(),json=config).json()
    run_id,token=claim_run()
    assert str(run_id)==first['id']
    computed=execute_run(run_id)
    second=client.post('/api/v1/planning-runs',headers=auth(),json=config).json()
    saved=client.post('/api/v1/disruption-events',headers=auth(),json=event()).json()
    assert set(saved['result']['superseded_run_ids'])=={first['id'],second['id']}
    assert publish_run(run_id,token,computed) is False
    with Session() as db:
        late=db.get(PlanningRun,run_id)
        assert late.status=='SUPERSEDED' and late.result is None
    blocked=client.post('/api/v1/planning-runs',headers=auth(),json=config)
    assert blocked.status_code==409 and 'SNAPSHOT_INVALIDATED_BY_EVENT' in blocked.text


def test_duplicate_events_are_idempotent_under_concurrent_delivery(client):
    prepare(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(client.post,'/api/v1/disruption-events',headers=auth(),json=event()) for _ in range(2)]
        results=[future.result() for future in futures]
    assert all(r.status_code==201 for r in results)
    assert results[0].json()['id']==results[1].json()['id']
    assert sorted(r.json()['duplicate'] for r in results)==[False,True]
    with Session() as db:assert db.get(OperationalState,'SIMULATED').revision==1
    conflict=client.post('/api/v1/disruption-events',headers=auth(),json=event(description='Different event under same identity'))
    assert conflict.status_code==409 and 'EVENT_REVISION_CONFLICT' in conflict.text


def test_debounce_generation_late_delivery_and_append_only_evidence(client):
    prepare(client)
    first=client.post('/api/v1/disruption-events',headers=auth(),json=event()).json()
    assert client.get('/api/v1/replanning-batches/SIMULATED',headers=auth()).json()['status']=='DEBOUNCING'
    app.dependency_overrides[utc_now]=lambda:NOW+timedelta(seconds=3)
    second=client.post('/api/v1/disruption-events',headers=auth(),json=event(source_revision=2)).json()
    assert second['result']['batch_generation']==2
    app.dependency_overrides[utc_now]=lambda:NOW+timedelta(seconds=6)
    assert client.get('/api/v1/replanning-batches/SIMULATED',headers=auth()).json()['status']=='DEBOUNCING'
    app.dependency_overrides[utc_now]=lambda:NOW+timedelta(seconds=8)
    batch=client.get('/api/v1/replanning-batches/SIMULATED',headers=auth()).json()
    assert batch['status']=='READY_FOR_NEW_SNAPSHOT' and batch['generation']==2
    duplicate=client.post('/api/v1/disruption-events',headers=auth(),json=event()).json()
    assert duplicate['id']==first['id'] and duplicate['duplicate']
    for table in ('disruption_events','snapshot_invalidations'):
        with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
            with engine.begin() as db:db.execute(text('DELETE FROM '+table))


def test_event_scope_roles_and_input_boundaries(client):
    prepare(client)
    assert client.post('/api/v1/disruption-events',headers=auth('AUDITOR'),json=event()).status_code==403
    assert client.post('/api/v1/disruption-events',headers=auth(),json=event(scope='OPERATIONAL')).status_code==422
    assert client.post('/api/v1/disruption-events',headers=auth(),json=event(track_ids=[])).status_code==422
    assert client.post('/api/v1/disruption-events',headers=auth(),json=event(resource_ids=['missing'])).status_code==422
    assert client.post('/api/v1/disruption-events',headers=auth(),json=event(occurred_at=(NOW+timedelta(seconds=1)).isoformat())).status_code==422
    assert client.post('/api/v1/disruption-events',headers=auth(),json={**event(),'received_at':NOW.isoformat()}).status_code==422


def test_fresh_receipt_cannot_revalidate_unchanged_invalidated_source_facts(client):
    manifest,revision,_=prepare(client)
    assert client.post('/api/v1/disruption-events',headers=auth(),json=event()).status_code==201
    context={**manifest['validation_context'],'received_at':NOW.isoformat()}
    response=client.post('/api/v1/snapshots',headers=auth(),json={
        'horizon_start':manifest['horizon_start'],'horizon_end':manifest['horizon_end'],
        'track_ids':manifest['track_ids'],'coordination_policy_id':manifest['facts']['coordination_policies'][0]['id'],
        'validation_context':context})
    assert response.status_code==409 and 'INVALIDATED_SOURCE_FACTS_REQUIRE_UPDATE' in response.text
