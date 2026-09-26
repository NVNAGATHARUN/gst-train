"""M13 decision support: real plan evidence, concurrency and fail-closed approval."""
import uuid
import json
import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.db import Session,engine
from railsync.main import app
from railsync.models import AuditEvent,OperationalState,PlanReservation
from railsync.planning import run_one
from railsync.validation import utc_now
from railsync.validator import content_hash
from test_m12 import run_fixture,NOW

def prepare(client):
    manifest,plan,run_id=run_fixture(client)
    response=client.post('/api/v1/plan-revisions',headers=auth(),json={
        'run_id':run_id,'expected_plan_hash':content_hash(plan)})
    assert response.status_code==201,response.text
    revision=response.json()
    app.dependency_overrides[utc_now]=lambda:NOW
    response=client.post('/api/v1/validation-reports',headers=auth(),json={
        'plan_revision_id':revision['id'],'expected_plan_hash':revision['plan_hash']})
    assert response.status_code==201,response.text
    report=response.json();assert report['status']=='PASS' and report['usable_for_review'],report
    return manifest,revision,report

def decision(revision,report,action='APPROVE',expected=0,key=None,**extra):
    return {'action':action,'idempotency_key':str(key or uuid.uuid4()),
        'expected_plan_hash':revision['plan_hash'],'expected_operational_revision':expected,
        'validation_report_id':report['id'] if report else None,'reason':'Controller test decision',**extra}

def test_materialize_explain_and_validate_exact_revision(client):
    _,revision,report=prepare(client)
    response=client.post(f"/api/v1/plan-revisions/{revision['id']}/explanations",headers=auth(),json={})
    assert response.status_code==201,response.text
    items=response.json()['items'];assert items
    assert {x['outcome'] for x in items}<={'SCHEDULED','DEFERRED'}
    scheduled=next(x for x in items if x['outcome']=='SCHEDULED')
    assert scheduled['selected_candidate_id'] in revision['content']['selected_candidate_ids']
    assert scheduled['priority']['method']=='RULE' and scheduled['resource_assignments']
    assert report['plan_revision_id']==revision['id']
    assert client.get(f"/api/v1/plan-revisions/{revision['id']}/explanations",headers=auth('AUDITOR')).json()['items']==items

def test_controller_approval_is_hash_bound_idempotent_and_simulation_scoped(client):
    _,revision,report=prepare(client);key=uuid.uuid4()
    body=decision(revision,report,key=key)
    approved=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=body)
    assert approved.status_code==201,approved.text
    result=approved.json()
    assert result['action']=='APPROVE' and result['authority']=='SOFTWARE_PROPOSAL_ONLY'
    assert result['scope']=='SIMULATED' and result['result']['operational_reservation_written'] is False
    assert result['reservations'] and all(r['scope']=='SIMULATED' and r['active'] for r in result['reservations'])
    repeated=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=body)
    assert repeated.status_code==201 and repeated.json()['id']==result['id']
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==1
        operational=db.get(OperationalState,'OPERATIONAL')
        assert operational is None or operational.revision==0
        assert not db.scalars(select(PlanReservation).where(PlanReservation.scope=='OPERATIONAL')).all()
    if path:=os.environ.get('RAILSYNC_M13_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED; actual CP-SAT plan, independent PASS report and controller decision',
                'plan_revision':revision,'validation_report':report,'controller_decision':result},output,indent=2)

def test_concurrent_approvals_only_one_can_commit(client):
    _,revision,report=prepare(client)
    def call():
        return client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
            json=decision(revision,report,key=uuid.uuid4())).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(call) for _ in range(2)]
        codes=sorted(future.result() for future in futures)
    assert codes==[201,409]
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==1

def test_controller_edit_creates_child_and_demands_fresh_validation(client):
    _,parent,parent_report=prepare(client)
    selected=parent['content']['selected_candidate_ids'][:1]
    response=client.post(f"/api/v1/plan-revisions/{parent['id']}/modifications",headers=auth('CONTROLLER'),json={
        'expected_revision':1,'expected_plan_hash':parent['plan_hash'],'selected_candidate_ids':selected,
        'reason':'Use the verified single candidate alternative'})
    assert response.status_code==201,response.text
    child=response.json();assert child['parent_id']==parent['id'] and child['revision']==2
    bad=client.post(f"/api/v1/plan-revisions/{child['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(child,parent_report))
    assert bad.status_code==409 and 'VALIDATION_REPORT_MISMATCH' in bad.text
    fresh=client.post('/api/v1/validation-reports',headers=auth(),json={
        'plan_revision_id':child['id'],'expected_plan_hash':child['plan_hash']})
    assert fresh.status_code==201 and fresh.json()['plan_revision_id']==child['id']

def test_reject_and_replan_are_audited_and_revision_guarded(client):
    _,revision,_=prepare(client)
    rejected=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json={
        **decision(revision,None,action='REJECT'),'validation_report_id':None})
    assert rejected.status_code==201,rejected.text
    assert rejected.json()['resulting_operational_revision']==1
    conflict=client.post(f"/api/v1/plan-revisions/{revision['id']}/replan",headers=auth('CONTROLLER'),json={
        'idempotency_key':str(uuid.uuid4()),'expected_plan_hash':revision['plan_hash'],
        'expected_operational_revision':0,'reason':'Recompute current proposal'})
    assert conflict.status_code==409 and 'OPERATIONAL_REVISION_CONFLICT' in conflict.text
    replanned=client.post(f"/api/v1/plan-revisions/{revision['id']}/replan",headers=auth('CONTROLLER'),json={
        'idempotency_key':str(uuid.uuid4()),'expected_plan_hash':revision['plan_hash'],
        'expected_operational_revision':1,'reason':'Recompute current proposal'})
    assert replanned.status_code==202,replanned.text
    assert replanned.json()['result']['status']=='QUEUED'
    assert run_one() is not None
    with Session() as db:
        actions={x.action for x in db.scalars(select(AuditEvent))}
        assert {'CONTROLLER_REJECT','CONTROLLER_REPLAN'}<=actions

def test_roles_hashes_reports_and_immutable_evidence_fail_closed(client):
    _,revision,report=prepare(client)
    endpoint=f"/api/v1/plan-revisions/{revision['id']}/decisions"
    assert client.post(endpoint,headers=auth('PLANNER'),json=decision(revision,report)).status_code==403
    bad=decision(revision,report);bad['expected_plan_hash']='0'*64
    assert client.post(endpoint,headers=auth('CONTROLLER'),json=bad).status_code==409
    missing=decision(revision,None)
    assert client.post(endpoint,headers=auth('CONTROLLER'),json=missing).status_code==422
    key=uuid.uuid4();original=decision(revision,report,key=key)
    assert client.post(endpoint,headers=auth('CONTROLLER'),json=original).status_code==201
    changed={**original,'reason':'Different request under reused key'}
    assert client.post(endpoint,headers=auth('CONTROLLER'),json=changed).status_code==409
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text("UPDATE plan_revisions SET revision=99"))
