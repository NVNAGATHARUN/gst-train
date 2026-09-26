"""Synthetic execution evidence processed by real APIs, planners and validation."""
import copy
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
import pytest
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.main import app
from railsync.db import Session,engine
from railsync.models import PlanReservation,OperationalState,PossessionRelease
from railsync.requests import digest
from railsync.validation import utc_now
from railsync.validator import validate
from test_m10 import profile
from test_m16_execution import observation,post_record
from test_m16_replanning import started,post,capture,snapshot,coordinate,run,urgent_request


def stopped(client,all_completed=False,known=None):
    manifest,parent,approval,state,now=started(client)
    block=parent['content']['assignments'][0]
    at=now+timedelta(minutes=20);records={}
    for task in block['tasks']:
        status='COMPLETED' if all_completed or task['department']=='TRD' else 'INTERRUPTED'
        result=post_record(client,parent,observation(parent,approval,block,task,status=status,
            expected_sequence=1,expected_operational_revision=state,observed_at=at.isoformat(),
            remaining_work_minutes=0 if status=='COMPLETED' else known))
        assert result.status_code==201,result.text
        records[task['request_id']]=result.json();state+=1
    return manifest,parent,approval,block,records,state,at


def reconcile_body(records,state,remaining=40,earliest=None):
    interrupted=next(r for r in records.values() if r['status']=='INTERRUPTED')
    return {'idempotency_key':str(uuid.uuid4()),'execution_record_id':interrupted['id'],
        'expected_operational_revision':state,'expected_revision':0,'expected_request_revision':2,
        'remaining_work_minutes':remaining,'restart_setup_minutes':5,'restart_restore_minutes':5,
        'earliest_restart_at':earliest or interrupted['observed_at'],'verified':True,
        'evidence_reference':'SYNTHETIC crew assessment: explicitly measured outstanding work'}


def release_body(approval,block,records,state,at,reconciliations=None):
    return {'idempotency_key':str(uuid.uuid4()),'decision_id':approval['id'],'candidate_id':block['id'],
        'expected_assignment_hash':digest(block),'expected_operational_revision':state,
        'expected_execution_ids':{rid:r['id'] for rid,r in records.items()},
        'reconciliation_ids':reconciliations or {},'actual_possession_start':block['possession_start'],
        'restoration_started_at':at.isoformat(),'restored_at':(at+timedelta(minutes=10)).isoformat(),
        'verified':True,'track_restored':True,'electrical_restored':True,'signalling_restored':True,'all_resources_clear':True,
        'evidence_reference':'SYNTHETIC controller verified restoration and full-possession crew accounting'}


def released(client,remaining=40,earliest=None,all_completed=False):
    manifest,parent,approval,block,records,state,at=stopped(client,all_completed=all_completed)
    reconciliations={}
    if not all_completed:
        reconciliation=post(client,'work-reconciliations',reconcile_body(records,state,remaining,earliest),role='CONTROLLER')
        reconciliations[reconciliation['result']['request_id']]=reconciliation['id'];state+=1
    body=release_body(approval,block,records,state,at,reconciliations)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    release=post(client,'possession-releases',body,role='CONTROLLER');state+=1
    return manifest,parent,records,state,release


def test_reconciled_remaining_work_is_replanned_after_verified_shared_release(client):
    manifest,parent,records,state,release=released(client)
    source=next(r for r in manifest['facts']['requests'] if r['payload']['department']=='ENGINEERING')
    captured=capture(client,parent,state)
    assert captured['status']=='CAPTURED' and captured['payload']['commitments']==[]
    saved=snapshot(client,manifest,captured);facts=saved['manifest']['facts']
    assert len(facts['requests'])==1 and facts['requests'][0]['id']==source['id']
    residual=facts['requests'][0]
    assert residual['payload']['work_minutes']==40
    assert residual['payload']['setup_minutes']==residual['payload']['restore_minutes']==5
    assert residual['payload']['deadline_at']==source['payload']['deadline_at']
    assert residual['source_request']==source and residual['payload']['mandatory']==source['payload']['mandatory']
    assert facts['completed_work'][0]['restoration_verified']
    assert all(len(r['profile']['payload']['duties'])==1 for r in facts['resources'])
    coord,_=coordinate(client,saved);optimized=run(client,saved,coord);baseline=run(client,saved,coord,'BASELINE')
    assert optimized['result']['counts']['scheduled']==baseline['result']['counts']['scheduled']==1
    task=optimized['result']['assignments'][0]['tasks'][0]
    assert (datetime.fromisoformat(task['work_end'])-datetime.fromisoformat(task['work_start'])).total_seconds()==2400
    assert datetime.fromisoformat(task['setup_start'])>=datetime.fromisoformat(release['payload']['restored_at'])
    revision=post(client,'plan-revisions',{'run_id':optimized['id'],'expected_plan_hash':digest(optimized['result'])})
    report=post(client,'validation-reports',{'plan_revision_id':revision['id'],'expected_plan_hash':revision['plan_hash']})
    assert report['status']=='PASS' and report['usable_for_review'],report
    with Session() as db:
        assert not any(r.active for r in db.scalars(select(PlanReservation)))
        assert db.get(OperationalState,'OPERATIONAL') is None
    if path:=os.environ.get('RAILSYNC_M16_RESTORATION_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as out:json.dump({'fixture':'SIMULATED completed TRD, interrupted ENG, explicit 40-minute remaining work and verified restoration',
            'release':release,'snapshot':saved,'optimized':optimized,'baseline':baseline,'validation':report},out,indent=2)


def test_completed_bundle_is_not_rescheduled_and_new_work_can_use_released_capacity(client):
    manifest,parent,records,state,release=released(client,all_completed=True)
    urgent=urgent_request(client)
    # Preserve the dependency: a restored, completed task satisfies precedence.
    request=client.get('/api/v1/maintenance-requests/'+urgent,headers=auth('ENGINEERING')).json()
    from test_m10 import submit
    edited=client.patch('/api/v1/maintenance-requests/'+urgent,headers=auth('ENGINEERING'),json={
        'expected_revision':request['revision'],'data':{**request['data'],'predecessors':[next(iter(records))]}}).json()
    submit(client,edited)
    saved=snapshot(client,manifest,capture(client,parent,state))
    assert {r['id'] for r in saved['manifest']['facts']['requests']}=={urgent}
    coord,_=coordinate(client,saved);result=run(client,saved,coord)['result']
    assert result['has_incumbent'] and result['counts']['scheduled']==1
    now=datetime.fromisoformat(release['payload']['restored_at'])
    report=validate(saved['manifest'],saved['content_hash'],result,digest(result),now,digest(saved['manifest']['facts']))
    assert report['status']=='PASS',report


def test_unknown_bundle_member_or_missing_reconciliation_cannot_release(client):
    manifest,parent,approval,block,records,state,at=stopped(client)
    body=release_body(approval,block,records,state,at)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    result=client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json=body)
    assert result.status_code==409 and 'CURRENT_RECONCILIATION_REQUIRED' in result.text
    incomplete={**body,'expected_execution_ids':{next(iter(records)):next(iter(records.values()))['id']}}
    assert client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json=incomplete).status_code==422
    with Session() as db:assert all(r.active for r in db.scalars(select(PlanReservation)))


def test_reconciliation_is_versioned_and_known_remaining_work_cannot_be_overridden(client):
    _,_,_,_,records,state,_=stopped(client,known=40)
    wrong=reconcile_body(records,state,remaining=20)
    response=client.post('/api/v1/work-reconciliations',headers=auth('CONTROLLER'),json=wrong)
    assert response.status_code==409 and 'OBSERVED_REMAINING_WORK_MISMATCH' in response.text
    body=reconcile_body(records,state)
    assert client.post('/api/v1/work-reconciliations',headers=auth(),json=body).status_code==403
    first=post(client,'work-reconciliations',body,role='CONTROLLER')
    assert client.get('/api/v1/work-reconciliations/'+first['id'],headers=auth('AUDITOR')).json()['payload']==first['payload']
    assert post(client,'work-reconciliations',body,role='CONTROLLER')['id']==first['id']
    second={**body,'idempotency_key':str(uuid.uuid4()),'expected_operational_revision':state+1,
        'expected_revision':1,'restart_setup_minutes':10}
    assert post(client,'work-reconciliations',second,role='CONTROLLER')['id']!=first['id']
    stale={**body,'idempotency_key':str(uuid.uuid4()),'expected_operational_revision':state+2}
    assert client.post('/api/v1/work-reconciliations',headers=auth('CONTROLLER'),json=stale).status_code==409
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text('DELETE FROM work_reconciliations'))


def test_concurrent_release_is_idempotent_and_append_only(client):
    _,_,approval,block,records,state,at=stopped(client,all_completed=True)
    body=release_body(approval,block,records,state,at)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(client.post,'/api/v1/possession-releases',headers=auth('CONTROLLER'),json=body) for _ in range(2)]
        results=[f.result() for f in futures]
    assert all(r.status_code==201 for r in results),[r.text for r in results]
    assert results[0].json()['id']==results[1].json()['id']
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state+1
        assert len(db.scalars(select(PossessionRelease)).all())==1
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text('DELETE FROM possession_releases'))


def test_release_identity_roles_timestamps_and_restoration_flags_fail_closed(client):
    _,_,approval,block,records,state,at=stopped(client,all_completed=True)
    body=release_body(approval,block,records,state,at)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    assert client.post('/api/v1/possession-releases',headers=auth(),json=body).status_code==403
    for changes,code in [({'expected_assignment_hash':'0'*64},409),({'expected_operational_revision':0},409),
            ({'track_restored':False},422),({'all_resources_clear':False},422),
            ({'restored_at':(at+timedelta(minutes=9)).isoformat()},422),
            ({'restored_at':(at+timedelta(minutes=11)).isoformat()},422),
            ({'actual_possession_start':at.isoformat()},422)]:
        result=client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json={**body,**changes})
        assert result.status_code==code,result.text


def test_superseded_assessment_cannot_release_and_release_freezes_assessment_versions(client):
    _,parent,approval,block,records,state,at=stopped(client)
    body=reconcile_body(records,state)
    first=post(client,'work-reconciliations',body,role='CONTROLLER');state+=1
    second=post(client,'work-reconciliations',{**body,'idempotency_key':str(uuid.uuid4()),
        'expected_operational_revision':state,'expected_revision':1,'restart_setup_minutes':10},role='CONTROLLER');state+=1
    rid=first['result']['request_id']
    release=release_body(approval,block,records,state,at,{rid:first['id']})
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(release['restored_at'])
    failed=client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json=release)
    assert failed.status_code==409 and 'CURRENT_RECONCILIATION_REQUIRED' in failed.text
    post(client,'possession-releases',{**release,'reconciliation_ids':{rid:second['id']}},role='CONTROLLER')
    changed={**body,'idempotency_key':str(uuid.uuid4()),'expected_operational_revision':state+1,'expected_revision':2}
    assert client.post('/api/v1/work-reconciliations',headers=auth('CONTROLLER'),json=changed).status_code==409


def test_unknown_or_active_work_cannot_be_reconciled_or_released(client):
    _,parent,approval,state,now=started(client)
    block=parent['content']['assignments'][0]
    records=client.get(f"/api/v1/plan-revisions/{parent['id']}/execution-records",headers=auth()).json()['items']
    by_id={r['request_id']:r for r in records}
    body=release_body(approval,block,by_id,state,now)
    app.dependency_overrides[utc_now]=lambda:now+timedelta(minutes=10)
    result=client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json=body)
    assert result.status_code==409 and 'WORK_STILL_ACTIVE_OR_UNKNOWN' in result.text
    with Session() as db:assert all(r.active for r in db.scalars(select(PlanReservation)))


def test_utc_release_times_retain_consistent_hashes_and_history(client):
    from datetime import timezone
    manifest,parent,approval,block,records,state,at=stopped(client,all_completed=True)
    body=release_body(approval,block,records,state,at)
    for key in ('actual_possession_start','restoration_started_at','restored_at'):
        body[key]=datetime.fromisoformat(body[key]).astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    post(client,'possession-releases',body,role='CONTROLLER')
    urgent_request(client)
    saved=snapshot(client,manifest,capture(client,parent,state+1));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result']
    report=validate(saved['manifest'],saved['content_hash'],plan,digest(plan),datetime.fromisoformat(body['restored_at']),digest(saved['manifest']['facts']))
    assert report['status']=='PASS',report


def test_actual_possession_history_enforces_resource_rest_and_rolling_duty(client):
    manifest,parent,_,state,release=released(client,remaining=20,earliest='2026-09-21T02:20:00+05:30')
    post(client,'resources/CREW-1/profiles',{'expected_revision':1,'data':profile(min_rest_minutes=30)})
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result']
    assert plan['counts']['scheduled']==1
    assert plan['assignments'][0]['possession_start']=='2026-09-21T03:30:00+05:30'
    # 40 minutes in observed possession plus 30 minutes of remaining setup/work/
    # restoration exceeds this explicit 60-minute synthetic daily limit.
    post(client,'resources/CREW-1/profiles',{'expected_revision':2,'data':profile(min_rest_minutes=30,max_duty_minutes_per_24h=60)})
    limited=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,limited)
    result=run(client,limited,coord)['result']
    assert result['counts']['scheduled']==0 and result['counts']['deferred']==1


@pytest.mark.parametrize('corruption',['remaining','duties','restoration','completion'])
def test_validator_independently_rejects_corrupted_release_or_remaining_facts(client,corruption):
    manifest,parent,_,state,release=released(client)
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result'];raw=copy.deepcopy(saved['manifest']);bad=copy.deepcopy(plan)
    if corruption=='remaining':raw['facts']['requests'][0]['payload']['work_minutes']-=1
    if corruption=='duties':raw['facts']['resources'][0]['profile']['payload']['duties']=[]
    if corruption=='restoration':
        raw['facts']['replanning'][0]['payload']['ledger']['releases'][0]['payload']['track_restored']=False
    if corruption=='completion':raw['facts']['completed_work'][0]['restoration_verified']=False
    raw['validation_context']['facts_hash']=digest(raw['facts']);bad['snapshot_hash']=digest(raw)
    result=validate(raw,digest(raw),bad,digest(bad),datetime.fromisoformat(release['payload']['restored_at']),digest(raw['facts']))
    assert result['status']!='PASS' and result['approval_blocked']
    expected={'remaining':'RESIDUAL_REQUEST_DERIVATION_MISMATCH','duties':'EXECUTION_DUTY_HISTORY_MISMATCH',
        'restoration':'RESTORATION_UNVERIFIED','completion':'COMPLETED_RESTORATION_EVIDENCE_MISMATCH'}
    assert expected[corruption] in {f['code'] for c in result['checks'] for f in c['findings']},result
