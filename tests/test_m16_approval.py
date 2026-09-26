"""Controlled SIMULATED replacement approval and source-bound differences."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from sqlalchemy import select
from conftest import auth
from railsync.db import Session
from railsync.models import OperationalState,PlanReservation,ControllerDecision
from railsync.main import app
from railsync.requests import digest
from railsync.validation import utc_now
from test_m13 import decision
from test_m16_replanning import started,capture,snapshot,coordinate,run,post,urgent_request
from test_m16_restoration import released
from test_m16_execution import observation,post_record


def replacement(client,with_urgent=True,with_release=False):
    if with_release:
        manifest,parent,_,state,_=released(client)
        # The source decision remains in the immutable capture ledger after release.
        from railsync.models import PlanRevision
        with Session() as db:
            old=db.scalar(select(ControllerDecision).where(ControllerDecision.plan_revision_id==uuid.UUID(parent['id']),
                ControllerDecision.action=='APPROVE'))
            source_decision_id=str(old.id)
    else:
        manifest,parent,old,state,_=started(client);source_decision_id=old['id']
    urgent=urgent_request(client) if with_urgent else None
    captured=capture(client,parent,state);assert captured['status']=='CAPTURED'
    saved=snapshot(client,manifest,captured)
    coord,_=coordinate(client,saved)
    output=run(client,saved,coord)
    assert output['result']['has_incumbent']
    revision=post(client,'plan-revisions',{'run_id':output['id'],'expected_plan_hash':digest(output['result'])})
    report=post(client,'validation-reports',{'plan_revision_id':revision['id'],'expected_plan_hash':revision['plan_hash']})
    assert report['status']=='PASS' and report['usable_for_review'],report
    return parent,source_decision_id,state,captured,revision,report,urgent


def approve(client,revision,report,state,source,key=None):
    body=decision(revision,report,expected=state,key=key,supersedes_decision_id=source)
    return client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=body),body


def test_atomic_supersede_and_difference_history(client):
    parent,source,state,captured,revision,report,urgent=replacement(client)
    differences=client.get(f"/api/v1/plan-revisions/{revision['id']}/differences",headers=auth('AUDITOR')).json()
    assert differences['payload']['capture_id']==captured['id']
    assert differences['payload']['source_plan_revision_id']==parent['id']
    assert differences['payload']['counts']=={'NEWLY_SCHEDULED':1,'UNCHANGED':2}
    repeated=post(client,'plan-revisions',{'run_id':revision['run_id'],'expected_plan_hash':revision['plan_hash']})
    assert repeated['id']==revision['id']
    response,body=approve(client,revision,report,state,source)
    assert response.status_code==201,response.text
    approved=response.json();assert approved['result']['replacement']['difference_hash']==differences['content_hash']
    assert len(approved['reservations'])==2 and all(r['scope']=='SIMULATED' for r in approved['reservations'])
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state+1
        assert db.get(OperationalState,'OPERATIONAL') is None
        old=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(source))).all()
        new=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(approved['id']))).all()
        assert old and all(not r.active for r in old)
        assert len(new)==2 and all(r.active for r in new)
        assert not db.scalars(select(PlanReservation).where(PlanReservation.scope=='OPERATIONAL')).all()
        old_active_count=sum(r.active for r in old);new_active_count=sum(r.active for r in new)
    if path:=os.environ.get('RAILSYNC_M16_APPROVAL_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED active ENG/TRD shared possession plus new urgent work',
                'source_revision':parent,'capture':captured,'replacement_revision':revision,
                'validation':report,'differences':differences,'controller_decision':approved,
                'old_active_reservations':old_active_count,
                'new_active_reservations':new_active_count,
                'operational_reservation_count':0},output,indent=2)
    assert client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),json=body).json()['id']==approved['id']
    # The difference is historical evidence even though approval itself advances the ledger.
    assert client.get(f"/api/v1/plan-revisions/{revision['id']}/differences",headers=auth('AUDITOR')).json()==differences


def test_released_residual_approval_identifies_completed_and_rescheduled_work(client):
    parent,source,state,_,revision,report,_=replacement(client,with_urgent=False,with_release=True)
    diff=revision['edit']['replacement']['payload']
    assert diff['counts']=={'COMPLETED_VERIFIED':1,'REMAINING_WORK_RESCHEDULED':1}
    residual=next(x for x in diff['changes'] if x['change']=='REMAINING_WORK_RESCHEDULED')
    assert residual['before'] and residual['after'] and residual['before']['assignment_hash']!=residual['after']['assignment_hash']
    response,_=approve(client,revision,report,state,source)
    assert response.status_code==201,response.text
    with Session() as db:
        assert not any(r.active for r in db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(source))))
        assert len(db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(response.json()['id']))).all())==1


def test_wrong_source_stale_state_and_missing_report_leave_reservations_intact(client):
    _,source,state,_,revision,report,_=replacement(client)
    url=f"/api/v1/plan-revisions/{revision['id']}/decisions"
    cases=[(decision(revision,report,expected=state,supersedes_decision_id=str(uuid.uuid4())),
            'REPLACEMENT_SOURCE_SUPERSEDE_REQUIRED'),
           (decision(revision,report,expected=state-1,supersedes_decision_id=source),
            'OPERATIONAL_REVISION_CONFLICT'),
           (decision(revision,None,expected=state,supersedes_decision_id=source),
            'VALIDATION_REPORT_REQUIRED')]
    for body,reason in cases:
        response=client.post(url,headers=auth('CONTROLLER'),json=body)
        assert response.status_code in (409,422) and reason in response.text,response.text
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state
        assert all(r.active for r in db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(source))))
        assert not db.scalars(select(PlanReservation).where(PlanReservation.plan_revision_id==uuid.UUID(revision['id']))).all()


def test_execution_change_after_validation_blocks_replacement_without_release(client):
    parent,source,state,_,revision,report,_=replacement(client)
    old=parent['content']['assignments'][0];task=old['tasks'][0]
    at=datetime.fromisoformat(task['work_start'])+timedelta(minutes=1)
    app.dependency_overrides[utc_now]=lambda:at
    observed=post_record(client,parent,observation(parent,{'id':source},old,task,status='INTERRUPTED',
        expected_sequence=1,expected_operational_revision=state,observed_at=at.isoformat()))
    assert observed.status_code==201,observed.text
    response,_=approve(client,revision,report,state+1,source)
    assert response.status_code==409 and 'REPLANNING_CAPTURE_STALE_OR_BLOCKED' in response.text
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state+1
        assert all(r.active for r in db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(source))))


def test_concurrent_identical_replacement_decision_is_idempotent(client):
    _,source,state,_,revision,report,_=replacement(client)
    key=uuid.uuid4();body=decision(revision,report,expected=state,key=key,supersedes_decision_id=source)
    url=f"/api/v1/plan-revisions/{revision['id']}/decisions"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(client.post,url,headers=auth('CONTROLLER'),json=body) for _ in range(2)]
        results=[f.result() for f in futures]
    assert all(x.status_code==201 for x in results),[x.text for x in results]
    assert results[0].json()['id']==results[1].json()['id']
    with Session() as db:assert db.get(OperationalState,'SIMULATED').revision==state+1


def test_controller_edit_creates_new_difference_and_requires_fresh_validation(client):
    _,source,state,_,revision,report,_=replacement(client)
    selected=revision['content']['selected_candidate_ids']
    child=post(client,f"plan-revisions/{revision['id']}/modifications",{
        'expected_revision':revision['revision'],'expected_plan_hash':revision['plan_hash'],
        'selected_candidate_ids':selected,'reason':'Controller reselected the verified candidates'},role='CONTROLLER')
    assert child['parent_id']==revision['id'] and child['lineage_id']==revision['lineage_id']
    assert child['edit']['replacement']['payload']['source_decision_id']==source
    assert child['edit']['replacement']['content_hash']==digest(child['edit']['replacement']['payload'])
    blocked,_=approve(client,revision,report,state,source)
    assert blocked.status_code==409 and 'PLAN_REVISION_NOT_LATEST' in blocked.text
    mismatched,_=approve(client,child,report,state,source)
    assert mismatched.status_code==409 and 'VALIDATION_REPORT_MISMATCH' in mismatched.text
    fresh=post(client,'validation-reports',{'plan_revision_id':child['id'],'expected_plan_hash':child['plan_hash']})
    assert fresh['status']=='PASS' and fresh['usable_for_review'],fresh
    approved,_=approve(client,child,fresh,state,source)
    assert approved.status_code==201,approved.text
