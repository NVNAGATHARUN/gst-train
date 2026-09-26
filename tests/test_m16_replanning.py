"""Execution-aware replacement solving on labeled inputs, never canned schedules."""
import copy
import json
import os
import uuid
from datetime import datetime,timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.main import app
from railsync.db import engine
from railsync.requests import digest
from railsync.planning import run_one
from railsync.solver import solve,SolverOptions
from railsync.validation import utc_now
from railsync.validator import validate
from test_m02 import request_data
from test_m10 import submit,profile
from test_m13 import decision
from test_m16_execution import approved,observation,post_record
from test_m16_events import event


def post(client,path,body,role='PLANNER',status=201):
    result=client.post('/api/v1/'+path,headers=auth(role),json=body)
    assert result.status_code==status,result.text
    return result.json()


def started(client):
    manifest,parent,report,approval,assignment,task=approved(client)
    state=2
    for block in parent['content']['assignments']:
        for t in block['tasks']:
            post_record_result=post_record(client,parent,observation(parent,approval,block,t,
                expected_operational_revision=state))
            assert post_record_result.status_code==201,post_record_result.text
            state+=1
    now=max(datetime.fromisoformat(t['work_start']) for b in parent['content']['assignments'] for t in b['tasks'])
    app.dependency_overrides[utc_now]=lambda:now
    return manifest,parent,approval,state,now


def capture(client,parent,state):
    return post(client,f"plan-revisions/{parent['id']}/replanning-captures",{
        'expected_plan_hash':parent['plan_hash'],'expected_operational_revision':state},role='CONTROLLER')


def snapshot(client,manifest,captured):
    body={'horizon_start':manifest['horizon_start'],'horizon_end':manifest['horizon_end'],
        'track_ids':manifest['track_ids'],'coordination_policy_id':manifest['facts']['coordination_policies'][0]['id'],
        'replanning_capture_id':captured['id']}
    draft=post(client,'snapshots',body)
    draft_manifest=client.get('/api/v1/snapshots/'+draft['id'],headers=auth()).json()['manifest']
    context={**manifest['validation_context'],'facts_hash':digest(draft_manifest['facts']),
        'received_at':captured['payload']['captured_at'],'commitments_known_empty':not bool(draft_manifest['facts']['commitments'])}
    result=post(client,'snapshots',{**body,'validation_context':context})
    result['manifest']=client.get('/api/v1/snapshots/'+result['id'],headers=auth()).json()['manifest']
    return result


def coordinate(client,saved):
    sid=saved['id'];at=saved['manifest']['facts']['replanning'][0]['payload']['captured_at']
    post(client,'priority-assessments',{'snapshot_id':sid,'assessed_at':at})
    availability=post(client,'corridor-availability',{'snapshot_id':sid,'track_ids':['AB']})
    opportunity=post(client,'maintenance-opportunities',{'snapshot_id':sid,'assessed_at':at,'availability_ids':[availability['id']]})
    result=post(client,'coordinated-candidates',{'opportunity_id':opportunity['id']})
    return result,opportunity


def run(client,saved,coord,planner='CP_SAT'):
    queued=post(client,'planning-runs',{'snapshot_id':saved['id'],'planner_type':planner,'coordination_id':coord['id']},status=202)
    assert str(run_one())==queued['id']
    output=client.get('/api/v1/planning-runs/'+queued['id'],headers=auth()).json()
    assert output['status']=='COMPLETED',output
    return output


def urgent_request(client):
    request=post(client,'maintenance-requests',request_data(work_minutes=5,setup_minutes=5,restore_minutes=5,
        mandatory=True,deadline_at='2026-09-21T04:00:00+05:30',power_state='ANY',signalling_state='ANY'),role='ENGINEERING')
    submit(client,request)
    return request['id']


def test_started_bundle_is_preserved_while_new_urgent_work_is_really_solved(client):
    manifest,parent,approval,state,now=started(client)
    urgent=urgent_request(client)
    captured=capture(client,parent,state)
    assert captured['status']=='CAPTURED' and captured['current']
    saved=snapshot(client,manifest,captured)
    assert saved['manifest']['facts']['execution']==captured['payload']['ledger']['execution']
    coord,opportunity=coordinate(client,saved)
    assert all(datetime.fromisoformat(c['possession_start'])>=now for c in opportunity['result']['candidates'])
    assert set(parent['content']['selected_candidate_ids'])<=set(coord['result']['preserved_candidate_ids'])
    output=run(client,saved,coord);plan=output['result']
    assert plan['solver_status'] in ('OPTIMAL','FEASIBLE') and plan['has_incumbent']
    assert plan['counts']['scheduled']==3 and plan['objective_terms']['commitment_change']['raw']==0
    by_id={a['id']:a for a in plan['assignments']}
    for original in parent['content']['assignments']:assert by_id[original['id']]==original
    new=next(a for a in plan['assignments'] if urgent in a['request_ids'])
    assert datetime.fromisoformat(new['possession_start'])>=max(
        datetime.fromisoformat(a['possession_end']) for a in parent['content']['assignments'])
    assert (datetime.fromisoformat(new['possession_end'])-datetime.fromisoformat(new['possession_start'])).total_seconds()==900
    baseline=run(client,saved,coord,'BASELINE')
    assert baseline['result']['counts']['scheduled']==3
    assert baseline['result']['objective_terms']['commitment_change']['raw']==0
    revision=post(client,'plan-revisions',{'run_id':output['id'],'expected_plan_hash':digest(plan)})
    assert revision['lineage_id']==parent['lineage_id'] and revision['parent_id']==parent['id']
    differences=client.get(f"/api/v1/plan-revisions/{revision['id']}/differences",headers=auth()).json()
    assert differences['content_hash']==revision['edit']['replacement']['content_hash']
    assert differences['payload']['counts']=={'NEWLY_SCHEDULED':1,'UNCHANGED':2}
    assert next(x for x in differences['payload']['changes'] if x['request_id']==urgent)['change']=='NEWLY_SCHEDULED'
    report=post(client,'validation-reports',{'plan_revision_id':revision['id'],'expected_plan_hash':revision['plan_hash']})
    assert report['status']=='PASS' and report['usable_for_review'],report
    approval_result=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=
        decision(revision,report,expected=state,supersedes_decision_id=approval['id']))
    assert approval_result.status_code==201,approval_result.text
    replacement_approval=approval_result.json()
    assert replacement_approval['result']['replacement']['difference_hash']==differences['content_hash']
    assert replacement_approval['result']['replacement']['source_decision_id']==approval['id']
    assert len(replacement_approval['reservations'])==len(plan['assignments'])
    assert all(r['scope']=='SIMULATED' and r['active'] for r in replacement_approval['reservations'])
    assert client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=
        decision(revision,report,expected=state,supersedes_decision_id=approval['id'])).status_code==409
    if path:=os.environ.get('RAILSYNC_M16_REPLANNING_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as file:json.dump({'fixture':'SIMULATED ongoing ENG/TRD plus urgent request; real candidate generation, baseline and CP-SAT',
            'capture':captured,'snapshot':saved,'coordination':coord,'baseline':baseline,'optimized':output,
            'validation':report,'differences':differences,'replacement_decision':replacement_approval,
            'urgent_request_id':urgent},file,indent=2)


@pytest.mark.parametrize('change',['restriction','resource'])
def test_new_conflict_makes_frozen_candidate_infeasible_without_fallback(client,change):
    manifest,parent,_,state,_=started(client)
    if change=='restriction':
        post(client,'network/restriction',{'id':'SYNTHETIC-CLOSURE','data':{'footprint':['AB'],
            'start':'2026-09-21T02:00:00+05:30','end':'2026-09-21T02:10:00+05:30',
            'rule_id':'SYNTHETIC-EMERGENCY','type':'WORK_PROHIBITED'}})
    else:
        post(client,'resources/CREW-1/profiles',{'expected_revision':1,'data':profile(
            qualifications=[{'skill':'UNRELATED','start_at':manifest['horizon_start'],'end_at':manifest['horizon_end']}])})
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    assert not set(parent['content']['selected_candidate_ids'])&set(coord['result']['preserved_candidate_ids'])
    assert any(e['code']=='APPROVED_CANDIDATE_RECHECK_FAILED' for e in coord['result']['exclusions'])
    result=run(client,saved,coord)['result']
    assert result['solver_status']=='INFEASIBLE' and not result['has_incumbent'] and result['assignments']==[]
    assert result['diagnostics']['missing_frozen_candidates']


def test_completed_request_is_captured_and_excluded_until_restoration_is_verified(client):
    manifest,parent,approval,state,_=started(client)
    assignment=parent['content']['assignments'][0];task=min(assignment['tasks'],key=lambda t:t['work_end'])
    completed=post_record(client,parent,observation(parent,approval,assignment,task,status='COMPLETED',
        expected_sequence=1,expected_operational_revision=state,remaining_work_minutes=0,observed_at=task['work_end']))
    assert completed.status_code==201
    captured=capture(client,parent,state+1)
    assert captured['status']=='BLOCKED' and 'COMPLETED_WORK_RESTORATION_UNVERIFIED' in captured['payload']['blockers']
    saved=snapshot(client,manifest,captured)
    assert task['request_id'] not in {r['id'] for r in saved['manifest']['facts']['requests']}
    assert saved['manifest']['facts']['completed_work'][0]['request_id']==task['request_id']
    coord,_=coordinate(client,saved)
    assert coord['result']['status']=='BLOCKED' and coord['result']['candidates']==[]
    blocked=client.post('/api/v1/planning-runs',headers=auth(),json={
        'snapshot_id':saved['id'],'planner_type':'CP_SAT','coordination_id':coord['id']})
    assert blocked.status_code==409


def test_later_execution_invalidates_capture_and_snapshot_without_mutating_evidence(client):
    manifest,parent,approval,state,now=started(client)
    captured=capture(client,parent,state);saved=snapshot(client,manifest,captured);coord,_=coordinate(client,saved)
    a=parent['content']['assignments'][0];task=a['tasks'][0]
    result=post_record(client,parent,observation(parent,approval,a,task,status='INTERRUPTED',
        expected_sequence=1,expected_operational_revision=state,observed_at=(now+timedelta(minutes=1)).isoformat()))
    assert result.status_code==201
    current=client.get('/api/v1/replanning-captures/'+captured['id'],headers=auth()).json()
    assert not current['current'] and current['payload']==captured['payload']
    blocked=client.post('/api/v1/planning-runs',headers=auth(),json={
        'snapshot_id':saved['id'],'planner_type':'CP_SAT','coordination_id':coord['id']})
    assert blocked.status_code==409 and 'EXECUTION_AWARE_SNAPSHOT_REQUIRED' in blocked.text
    fresh=capture(client,parent,state+1)
    assert 'REMAINING_WORK_RECONCILIATION_REQUIRED' in fresh['payload']['blockers']


def test_capture_roles_hashes_revision_and_append_only_provenance(client):
    _,parent,_,state,_=started(client)
    url=f"/api/v1/plan-revisions/{parent['id']}/replanning-captures"
    body={'expected_plan_hash':parent['plan_hash'],'expected_operational_revision':state}
    assert client.post(url,headers=auth(),json=body).status_code==403
    assert client.post(url,headers=auth('CONTROLLER'),json={**body,'expected_plan_hash':'0'*64}).status_code==409
    assert client.post(url,headers=auth('CONTROLLER'),json={**body,'expected_operational_revision':0}).status_code==409
    captured=capture(client,parent,state)
    assert capture(client,parent,state)['id']==captured['id']
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text('DELETE FROM replanning_captures'))


def test_capture_metadata_cannot_repair_unchanged_disrupted_facts(client):
    manifest,parent,_,state,_=started(client)
    post(client,'disruption-events',event())
    captured=capture(client,parent,state+1)
    result=client.post('/api/v1/snapshots',headers=auth(),json={
        'horizon_start':manifest['horizon_start'],'horizon_end':manifest['horizon_end'],'track_ids':['AB'],
        'coordination_policy_id':manifest['facts']['coordination_policies'][0]['id'],'replanning_capture_id':captured['id']})
    assert result.status_code==409 and 'INVALIDATED_SOURCE_FACTS_REQUIRE_UPDATE' in result.text


@pytest.mark.parametrize('corruption',['unfreeze','omit','execution','past'])
def test_independent_validator_recomputes_capture_obligations(client,corruption):
    manifest,parent,_,state,now=started(client)
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result'];raw=copy.deepcopy(saved['manifest']);bad=copy.deepcopy(plan)
    if corruption=='unfreeze':raw['facts']['commitments'][0]['frozen']=False
    if corruption=='omit':raw['facts']['commitments']=[]
    if corruption=='execution':
        raw['facts']['replanning'][0]['payload']['ledger']['execution'][0]['observed_at']=(now-timedelta(minutes=1)).isoformat()
    if corruption=='past':
        bad['assignments'][0]['id']='synthetic-corrupted-identity'
        raw['facts']['commitments']=[]
    raw['validation_context']['facts_hash']=digest(raw['facts']);bad['snapshot_hash']=digest(raw)
    result=validate(raw,digest(raw),bad,digest(bad),now,digest(raw['facts']))
    assert result['status']!='PASS' and result['approval_blocked']
    codes={f['code'] for c in result['checks'] for f in c['findings']}
    expected={'unfreeze':'FROZEN_DERIVATION_MISMATCH','omit':'APPROVED_COMMITMENT_COVERAGE_MISMATCH',
        'execution':'EXECUTION_TIMING_RECONCILIATION_REQUIRED','past':'NEW_WORK_BEFORE_REPLANNING_TIME'}
    assert expected[corruption] in codes,result


def test_solver_rejects_candidate_content_substituted_under_frozen_identity(client):
    manifest,parent,_,state,_=started(client)
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    mutated=copy.deepcopy(coord['result'])
    cid=parent['content']['selected_candidate_ids'][0]
    next(c for c in mutated['candidates'] if c['id']==cid)['costs']['reserved_track_minutes']+=1
    priorities={r['id']:5000 for r in saved['manifest']['facts']['requests']}
    with pytest.raises(ValueError,match='COMMITMENT_CANDIDATE_HASH_MISMATCH'):
        solve(saved['manifest'],mutated,priorities,SolverOptions().model_dump())


def test_validation_does_not_assume_unobserved_work_completion_as_time_passes(client):
    manifest,parent,_,state,_=started(client)
    saved=snapshot(client,manifest,capture(client,parent,state));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result']
    later=min(datetime.fromisoformat(t['work_end']) for a in parent['content']['assignments'] for t in a['tasks'])
    result=validate(saved['manifest'],saved['content_hash'],plan,digest(plan),later,digest(saved['manifest']['facts']))
    assert result['status']=='ERROR'
    assert any(f['code']=='EXECUTION_TIMING_RECONCILIATION_REQUIRED' for c in result['checks'] for f in c['findings'])


def test_future_capture_requires_execution_evidence_when_possession_start_is_reached(client):
    manifest,parent,_,_,assignment,_=approved(client)
    saved=snapshot(client,manifest,capture(client,parent,2));coord,_=coordinate(client,saved)
    plan=run(client,saved,coord)['result']
    later=datetime.fromisoformat(assignment['possession_start'])
    result=validate(saved['manifest'],saved['content_hash'],plan,digest(plan),later,digest(saved['manifest']['facts']))
    assert result['status']=='ERROR'
    assert any(f['code']=='EXECUTION_STATE_UNKNOWN' for c in result['checks'] for f in c['findings'])
