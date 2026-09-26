"""M16 execution/freeze slice: genuine CP-SAT proposals plus explicit observations."""
import copy
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.main import app
from railsync.db import Session,engine
from railsync.models import ExecutionRecord,PlanReservation,OperationalState,PlanningRun
from railsync.requests import digest
from railsync.freeze_state import assess_freeze,enforce_replacement
from railsync.planning import claim_run,execute_run,publish_run
from railsync.validation import utc_now
from test_m12 import NOW
from test_m13 import prepare,decision
from test_m16_events import event


def approved(client,policy=True):
    manifest,revision,report=prepare(client)
    response=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(revision,report))
    assert response.status_code==201,response.text
    if policy:
        configured=client.post('/api/v1/freeze-policies',headers=auth('ADMIN'),json={
            'expected_revision':0,'freeze_minutes':180,'reason':'SYNTHETIC demonstration freeze policy'})
        assert configured.status_code==201,configured.text
    assignment=revision['content']['assignments'][0]
    task=max(assignment['tasks'],key=lambda t:t['work_end'])
    return manifest,revision,report,response.json(),assignment,task


def observation(revision,approval,assignment,task,**changes):
    return {'idempotency_key':str(uuid.uuid4()),'decision_id':approval['id'],
        'expected_plan_hash':revision['plan_hash'],'candidate_id':assignment['id'],
        'expected_assignment_hash':digest(assignment),'request_id':task['request_id'],
        'expected_sequence':0,'expected_operational_revision':2,'status':'STARTED',
        'observed_at':task['work_start'],'verified':True,
        'evidence_reference':'SYNTHETIC controller work log','note':'Observed task execution in prototype fixture',**changes}


def post_record(client,revision,body,at=None):
    app.dependency_overrides[utc_now]=lambda:at or datetime.fromisoformat(body['observed_at'])
    return client.post(f"/api/v1/plan-revisions/{revision['id']}/execution-records",headers=auth('CONTROLLER'),json=body)


def test_execution_lifecycle_is_explicit_immutable_and_does_not_release_reservations(client):
    _,revision,report,approval,assignment,task=approved(client)
    body=observation(revision,approval,assignment,task)
    start=post_record(client,revision,body)
    assert start.status_code==201,start.text
    assert start.json()['status']=='STARTED' and start.json()['sequence']==1
    work_start=datetime.fromisoformat(task['work_start'])
    completed_body=observation(revision,approval,assignment,task,status='COMPLETED',remaining_work_minutes=0,
        expected_sequence=1,expected_operational_revision=3,observed_at=task['work_end'])
    done=post_record(client,revision,completed_body)
    assert done.status_code==201,done.text
    assert done.json()['result']['reservations_released'] is False
    assert done.json()['result']['execution_authorized'] is False
    assert done.json()['sequence']==2
    saved=client.get(f"/api/v1/plan-revisions/{revision['id']}/execution-records",headers=auth('AUDITOR')).json()
    assert [r['status'] for r in saved['items']]==['STARTED','COMPLETED']
    report_view=client.get('/api/v1/validation-reports/'+report['id'],headers=auth()).json()
    assert not report_view['usable_for_review'] and 'EXECUTION_AWARE_SNAPSHOT_REQUIRED' in report_view['current_blockers']
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==4
        assert db.get(OperationalState,'OPERATIONAL') is None
        assert all(r.active for r in db.scalars(select(PlanReservation)))
    for table in ('execution_records','freeze_policies'):
        with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
            with engine.begin() as db:db.execute(text('DELETE FROM '+table))
    terminal=post_record(client,revision,observation(revision,approval,assignment,task,
        expected_sequence=2,expected_operational_revision=4,observed_at=(work_start+timedelta(hours=2)).isoformat()))
    assert terminal.status_code==409 and 'INVALID_EXECUTION_TRANSITION' in terminal.text
    if path:=os.environ.get('RAILSYNC_M16_EXECUTION_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED inputs processed through actual CP-SAT, validation and approval',
                'plan_revision_id':revision['id'],'assignment':assignment,'execution':saved,
                'validation':report_view,'freeze_context':client.get(
                    f"/api/v1/plan-revisions/{revision['id']}/freeze-context",headers=auth()).json()},output,indent=2)


def test_execution_input_identity_roles_and_lifecycle_guards(client):
    _,revision,_,approval,assignment,task=approved(client)
    body=observation(revision,approval,assignment,task)
    endpoint=f"/api/v1/plan-revisions/{revision['id']}/execution-records"
    assert client.post(endpoint,headers=auth(),json=body).status_code==403
    for changes,code in [({'expected_plan_hash':'0'*64},409),({'expected_assignment_hash':'0'*64},409),
            ({'decision_id':str(uuid.uuid4())},409),({'request_id':str(uuid.uuid4())},422),
            ({'expected_sequence':2},409),({'expected_operational_revision':0},409),
            ({'status':'COMPLETED','remaining_work_minutes':0},409),
            ({'status':'COMPLETED'},422),({'status':'RESUMED'},422),({'verified':False},422),
            ({'observed_at':'2026-09-21T01:00:00'},422),({'received_at':NOW.isoformat()},422)]:
        result=post_record(client,revision,{**body,**changes})
        assert result.status_code==code,result.text
    assert post_record(client,revision,body,at=NOW).status_code==422
    first=post_record(client,revision,body);assert first.status_code==201,first.text
    out_of_order={**body,'idempotency_key':str(uuid.uuid4()),'status':'INTERRUPTED',
        'expected_sequence':1,'expected_operational_revision':3}
    result=post_record(client,revision,out_of_order)
    assert result.status_code==409 and 'OUT_OF_ORDER' in result.text


def test_concurrent_execution_redelivery_advances_state_once(client):
    _,revision,_,approval,assignment,task=approved(client)
    body=observation(revision,approval,assignment,task)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(task['work_start'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(client.post,f"/api/v1/plan-revisions/{revision['id']}/execution-records",
            headers=auth('CONTROLLER'),json=body) for _ in range(2)]
        results=[j.result() for j in jobs]
    assert all(r.status_code==201 for r in results),[r.text for r in results]
    assert results[0].json()['id']==results[1].json()['id']
    assert sorted(r.json()['duplicate'] for r in results)==[False,True]
    changed=post_record(client,revision,{**body,'note':'Changed assertion under reused identity'})
    assert changed.status_code==409 and 'IDEMPOTENCY' in changed.text
    with Session() as db:
        assert len(db.scalars(select(ExecutionRecord)).all())==1
        assert db.get(OperationalState,'SIMULATED').revision==3


def test_interruption_keeps_unknown_remaining_work_visible_and_requires_reconciliation(client):
    _,revision,_,approval,assignment,task=approved(client)
    assert post_record(client,revision,observation(revision,approval,assignment,task)).status_code==201
    start=datetime.fromisoformat(task['work_start'])
    paused=post_record(client,revision,observation(revision,approval,assignment,task,status='INTERRUPTED',
        expected_sequence=1,expected_operational_revision=3,observed_at=(start+timedelta(minutes=1)).isoformat()))
    assert paused.status_code==201,paused.text
    view=client.get(f"/api/v1/plan-revisions/{revision['id']}/freeze-context",headers=auth()).json()
    entry=next(c for c in view['commitments'] if c['candidate_id']==assignment['id'])
    assert entry['frozen'] and {'INTERRUPTED_WORK_REQUIRES_RECONCILIATION','REMAINING_WORK_UNKNOWN'}<=set(entry['blockers'])
    resumed=post_record(client,revision,observation(revision,approval,assignment,task,status='RESUMED',
        remaining_work_minutes=59,expected_sequence=2,expected_operational_revision=4,
        observed_at=(start+timedelta(minutes=2)).isoformat()))
    assert resumed.status_code==201,resumed.text
    assert resumed.json()['payload']['remaining_work_minutes']==59


def test_freeze_policy_and_controller_changes_are_enforced(client):
    _,revision,_,_,_,_=approved(client,policy=False)
    edit={'expected_revision':1,'expected_plan_hash':revision['plan_hash'],'selected_candidate_ids':[],
        'reason':'Attempt to remove approved work'}
    url=f"/api/v1/plan-revisions/{revision['id']}/modifications"
    unknown=client.post(url,headers=auth('CONTROLLER'),json=edit)
    assert unknown.status_code==409 and 'FREEZE_POLICY_UNKNOWN' in unknown.text
    config={'expected_revision':0,'freeze_minutes':180,'reason':'SYNTHETIC test policy'}
    assert client.post('/api/v1/freeze-policies',headers=auth(),json=config).status_code==403
    assert client.post('/api/v1/freeze-policies',headers=auth('ADMIN'),json=config).status_code==201
    assert client.post('/api/v1/freeze-policies',headers=auth('ADMIN'),json=config).status_code==409
    frozen=client.post(url,headers=auth('CONTROLLER'),json=edit)
    assert frozen.status_code==409 and 'FROZEN_WORK_CHANGED' in frozen.text
    with Session() as db:
        altered=copy.deepcopy(revision['content']['assignments'])
        altered[0]['tasks'][0]['work_end']=altered[0]['tasks'][0]['work_start']
        with pytest.raises(HTTPException) as error:
            enforce_replacement(db,'SIMULATED',uuid.UUID(revision['lineage_id']),altered,NOW)
        assert error.value.detail['code']=='FROZEN_WORK_CHANGED'
    preserved=client.post(url,headers=auth('CONTROLLER'),json={**edit,
        'selected_candidate_ids':revision['content']['selected_candidate_ids']})
    assert preserved.status_code==201,preserved.text


@pytest.mark.parametrize('stamp',['2028-02-29T23:30:00+05:30','2026-12-31T23:30:00+05:30'])
def test_freeze_boundary_is_half_open_across_calendar_boundaries(stamp):
    # Minimal synthetic inputs to the freeze calculation, never solver output.
    now=datetime.fromisoformat(stamp)
    assignment={'id':'synthetic-freeze-input','request_ids':['R'],
        'possession_start':(now+timedelta(minutes=60)).isoformat()}
    assert not assess_freeze([assignment],[],60,now)[0]['frozen']
    inside=assess_freeze([assignment],[],60,now+timedelta(microseconds=1))[0]
    assert inside['frozen'] and inside['reasons']==['APPROVED_WITHIN_FREEZE_INTERVAL']
    at_start=assess_freeze([assignment],[],0,now+timedelta(minutes=60))[0]
    assert at_start['frozen'] and 'EXECUTION_STATE_UNKNOWN' in at_start['blockers']
    observed=[{'sequence':1,'request_id':'R','status':'COMPLETED','remaining_work_minutes':0}]
    assert 'EXECUTION_COMPLETED' in assess_freeze([assignment],observed,0,now)[0]['reasons']


def test_execution_supersedes_jobs_and_blocks_reuse_of_execution_unaware_snapshot(client):
    _,revision,report,approval,assignment,task=approved(client)
    config=client.get('/api/v1/planning-runs/'+revision['run_id'],headers=auth()).json()['config']
    queued=client.post('/api/v1/planning-runs',headers=auth(),json=config)
    assert queued.status_code==202
    run_id,token=claim_run();computed=execute_run(run_id)
    assert post_record(client,revision,observation(revision,approval,assignment,task)).status_code==201
    assert publish_run(run_id,token,computed) is False
    with Session() as db:assert db.get(PlanningRun,run_id).status=='SUPERSEDED'
    again=client.post('/api/v1/planning-runs',headers=auth(),json=config)
    assert again.status_code==409 and 'EXECUTION_AWARE_SNAPSHOT_REQUIRED' in again.text
    view=client.get('/api/v1/plan-revisions/'+revision['id'],headers=auth()).json()
    assert view['current_state']['status']=='STALE_REQUIRES_ATTENTION'
    approval_attempt=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(revision,report,expected=3))
    assert approval_attempt.status_code==409 and 'EXECUTION_AWARE_SNAPSHOT_REQUIRED' in approval_attempt.text


def test_stale_approved_execution_can_be_observed_without_authorizing_work(client):
    _,revision,_,approval,assignment,task=approved(client)
    response=client.post('/api/v1/disruption-events',headers=auth(),json=event())
    assert response.status_code==201
    started=post_record(client,revision,observation(revision,approval,assignment,task,expected_operational_revision=3))
    assert started.status_code==201,started.text
    assert started.json()['result']['source_plan_stale'] is True
    assert started.json()['result']['execution_authorized'] is False


def test_approval_rechecks_freeze_after_an_earlier_edit(client):
    _,revision,_,approval,assignment,_=approved(client,policy=False)
    assert client.post('/api/v1/freeze-policies',headers=auth('ADMIN'),json={
        'expected_revision':0,'freeze_minutes':1,'reason':'SYNTHETIC one minute freeze test'}).status_code==201
    # Outside the freeze interval, a proposal may omit optional requests. It must
    # still be independently validated and rechecked at approval time.
    child=client.post(f"/api/v1/plan-revisions/{revision['id']}/modifications",headers=auth('CONTROLLER'),json={
        'expected_revision':1,'expected_plan_hash':revision['plan_hash'],'selected_candidate_ids':[],
        'reason':'Defer optional work outside freeze interval'})
    assert child.status_code==201,child.text
    child=child.json()
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(assignment['possession_start'])-timedelta(seconds=30)
    report=client.post('/api/v1/validation-reports',headers=auth(),json={
        'plan_revision_id':child['id'],'expected_plan_hash':child['plan_hash']})
    assert report.status_code==201 and report.json()['status']=='PASS',report.text
    blocked=client.post(f"/api/v1/plan-revisions/{child['id']}/decisions",headers=auth('CONTROLLER'),json=
        decision(child,report.json(),expected=2,supersedes_decision_id=approval['id']))
    assert blocked.status_code==409 and 'FROZEN_WORK_CHANGED' in blocked.text
    with Session() as db:assert all(r.active for r in db.scalars(select(PlanReservation)))


def test_second_lineage_cannot_approve_already_committed_requests(client):
    _,revision,_,_,_,_=approved(client)
    config=client.get('/api/v1/planning-runs/'+revision['run_id'],headers=auth()).json()['config']
    response=client.post('/api/v1/planning-runs',headers=auth(),json=config)
    assert response.status_code==202
    run_id,token=claim_run();computed=execute_run(run_id)
    assert publish_run(run_id,token,computed)
    replacement=client.post('/api/v1/plan-revisions',headers=auth(),json={
        'run_id':str(run_id),'expected_plan_hash':digest(computed)}).json()
    report=client.post('/api/v1/validation-reports',headers=auth(),json={
        'plan_revision_id':replacement['id'],'expected_plan_hash':replacement['plan_hash']}).json()
    assert report['status']=='PASS'
    blocked=client.post(f"/api/v1/plan-revisions/{replacement['id']}/decisions",headers=auth('CONTROLLER'),json=
        decision(replacement,report,expected=2))
    assert blocked.status_code==409 and 'REQUEST_ALREADY_APPROVED' in blocked.text
