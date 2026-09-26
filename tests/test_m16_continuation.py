"""Controller observations across a validated simulated replacement approval."""
import json
import os
import uuid
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from sqlalchemy import select
from conftest import auth
from railsync.db import Session
from railsync.models import ExecutionRecord,OperationalState,PlanReservation
from railsync.main import app
from railsync.requests import digest
from railsync.validation import utc_now
from railsync.validator import validate
from test_m16_approval import replacement,approve
from test_m16_execution import observation,post_record
from test_m16_restoration import release_body
from test_m16_replanning import capture,snapshot,coordinate,run,post


def approved_replacement(client,released=False):
    parent,source,state,captured,revision,report,_=replacement(client,with_urgent=not released,with_release=released)
    approved,_=approve(client,revision,report,state,source)
    assert approved.status_code==201,approved.text
    return parent,source,state+1,captured,revision,approved.json()


def test_preserved_ongoing_work_continues_under_new_approval(client):
    parent,source,state,captured,revision,approval=approved_replacement(client)
    original=parent['content']['assignments'][0]
    assignment=next(a for a in revision['content']['assignments'] if a['id']==original['id'])
    task=max(assignment['tasks'],key=lambda t:t['work_end'])
    with Session() as db:
        prior=db.scalar(select(ExecutionRecord).where(ExecutionRecord.request_id==task['request_id']))
        assert prior.status=='STARTED' and str(prior.decision_id)==source
        prior_id=str(prior.id)
    body=observation(revision,approval,assignment,task,status='COMPLETED',remaining_work_minutes=0,
        expected_sequence=1,expected_operational_revision=state,observed_at=task['work_end'])
    result=post_record(client,revision,body)
    assert result.status_code==201,result.text
    saved=result.json()
    assert saved['sequence']==2 and saved['status']=='COMPLETED'
    assert saved['result']['continuation']=={'kind':'PRESERVED_ASSIGNMENT','source_decision_id':source,
        'source_execution_record_id':prior_id,'source_assignment_hash':digest(original),
        'release_id':None,'reconciliation_id':None}
    assert saved['result']['execution_authorized'] is False and saved['result']['reservations_released'] is False
    old=post_record(client,parent,observation(parent,{'id':source},original,task,status='INTERRUPTED',
        expected_sequence=2,expected_operational_revision=state+1,
        observed_at=(datetime.fromisoformat(task['work_end'])+timedelta(minutes=1)).isoformat()))
    assert old.status_code==409 and 'APPROVAL_NO_LONGER_ACTIVE' in old.text
    old_capture=client.post(f"/api/v1/plan-revisions/{parent['id']}/replanning-captures",
        headers=auth('CONTROLLER'),json={'expected_plan_hash':parent['plan_hash'],
            'expected_operational_revision':state+1})
    assert old_capture.status_code==409 and 'SOURCE_APPROVAL_SUPERSEDED' in old_capture.text
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state+1
        assert all(not r.active for r in db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(source))))
    if path:=os.environ.get('RAILSYNC_M16_CONTINUATION_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED approved source ENG/TRD shared work preserved exactly in CP-SAT replacement',
                'source_revision_id':parent['id'],'replacement_revision_id':revision['id'],
                'captured_source_decision_id':captured['payload']['source_decision_id'],
                'replacement_decision_id':approval['id'],'observation':saved},output,indent=2)


def test_verified_residual_work_resumes_and_completes_after_release(client):
    parent,source,state,captured,revision,approval=approved_replacement(client,released=True)
    assignment=revision['content']['assignments'][0];task=assignment['tasks'][0]
    # The new snapshot binds the request to a specific release and assessment.
    with Session() as db:
        prior=db.scalar(select(ExecutionRecord).where(ExecutionRecord.request_id==task['request_id'])
            .order_by(ExecutionRecord.sequence.desc()).limit(1))
        assert prior.status=='INTERRUPTED' and str(prior.decision_id)==source
    resume=observation(revision,approval,assignment,task,status='RESUMED',remaining_work_minutes=40,
        expected_sequence=2,expected_operational_revision=state,observed_at=task['work_start'])
    first=post_record(client,revision,resume)
    assert first.status_code==201,first.text
    assert first.json()['sequence']==3 and first.json()['result']['continuation']['kind']=='VERIFIED_RESIDUAL_RESTART'
    assert first.json()['result']['continuation']['release_id']
    assert first.json()['result']['continuation']['reconciliation_id']
    done=post_record(client,revision,observation(revision,approval,assignment,task,status='COMPLETED',
        remaining_work_minutes=0,expected_sequence=3,expected_operational_revision=state+1,
        observed_at=task['work_end']))
    assert done.status_code==201,done.text
    assert done.json()['sequence']==4 and done.json()['status']=='COMPLETED'
    at=datetime.fromisoformat(task['work_end']);records={task['request_id']:done.json()}
    body=release_body(approval,assignment,records,state+2,at)
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['restored_at'])
    released=client.post('/api/v1/possession-releases',headers=auth('CONTROLLER'),json=body)
    assert released.status_code==201,released.text
    assert released.json()['result']['reservation_released'] is True
    with Session() as db:
        assert not any(r.active for r in db.scalars(select(PlanReservation).where(PlanReservation.decision_id==uuid.UUID(approval['id']))))
    manifest=client.get(f"/api/v1/snapshots/{parent['snapshot_id']}",headers=auth()).json()['manifest']
    later_capture=capture(client,revision,state+3)
    assert later_capture['status']=='CAPTURED',later_capture
    assert len(later_capture['payload']['ledger']['approvals'])==2
    later_snapshot=snapshot(client,manifest,later_capture)
    assert len(later_snapshot['manifest']['facts']['completed_work'])==2
    assert later_snapshot['manifest']['facts']['requests']==[]
    later_coord,_=coordinate(client,later_snapshot)
    later_run=run(client,later_snapshot,later_coord)
    assert later_run['result']['counts']['scheduled']==0
    later_revision=post(client,'plan-revisions',{'run_id':later_run['id'],
        'expected_plan_hash':digest(later_run['result'])})
    later_report=post(client,'validation-reports',{'plan_revision_id':later_revision['id'],
        'expected_plan_hash':later_revision['plan_hash']})
    assert later_report['status']=='PASS' and later_report['usable_for_review'],later_report
    corrupted=copy.deepcopy(later_snapshot['manifest'])
    chain=corrupted['facts']['replanning'][0]
    bridged=next(r for r in chain['payload']['ledger']['execution'] if r['result'].get('continuation'))
    bridged['result']['continuation']['source_decision_id']=str(uuid.uuid4())
    chain['payload']['ledger_hash']=digest(chain['payload']['ledger'])
    chain['content_hash']=digest(chain['payload'])
    corrupted['facts']['execution']=copy.deepcopy(chain['payload']['ledger']['execution'])
    corrupted['validation_context']['facts_hash']=digest(corrupted['facts'])
    bad_plan=copy.deepcopy(later_run['result']);bad_plan['snapshot_hash']=digest(corrupted)
    checked=validate(corrupted,digest(corrupted),bad_plan,digest(bad_plan),
        datetime.fromisoformat(body['restored_at']),digest(corrupted['facts']))
    assert checked['status']!='PASS' and checked['approval_blocked']
    assert any(f['code']=='CONTINUATION_RECORD_LINK_MISMATCH' for c in checked['checks'] for f in c['findings'])
    if path:=os.environ.get('RAILSYNC_M16_CONTINUATION_RESIDUAL_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED interrupted ENG work after verified whole-possession restoration and 40-minute assessment',
                'source_revision_id':parent['id'],'replacement_revision_id':revision['id'],
                'replacement_decision_id':approval['id'],'resumed_observation':first.json(),
                'completed_observation':done.json(),'restoration_release':released.json()},output,indent=2)


def test_residual_resume_requires_exact_assessed_minutes_and_restoration_time(client):
    _,source,state,captured,revision,approval=approved_replacement(client,released=True)
    assignment=revision['content']['assignments'][0];task=assignment['tasks'][0]
    valid=observation(revision,approval,assignment,task,status='RESUMED',remaining_work_minutes=40,
        expected_sequence=2,expected_operational_revision=state,observed_at=task['work_start'])
    wrong=post_record(client,revision,{**valid,'remaining_work_minutes':39,'idempotency_key':str(uuid.uuid4())})
    assert wrong.status_code==409 and 'RESIDUAL_CONTINUATION_EVIDENCE_MISMATCH' in wrong.text
    restored=datetime.fromisoformat(captured['payload']['released_possessions'][0]['payload']['restored_at'])
    early=post_record(client,revision,{**valid,'observed_at':(restored-timedelta(seconds=1)).isoformat(),
        'idempotency_key':str(uuid.uuid4())})
    assert early.status_code==409 and 'RESIDUAL_CONTINUATION_EVIDENCE_MISMATCH' in early.text
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state
        assert not db.scalars(select(ExecutionRecord).where(ExecutionRecord.decision_id==uuid.UUID(approval['id']))).all()


def test_concurrent_continuation_redelivery_advances_sequence_once(client):
    parent,source,state,_,revision,approval=approved_replacement(client)
    assignment=next(a for a in revision['content']['assignments'] if a['id']==parent['content']['assignments'][0]['id'])
    task=assignment['tasks'][0]
    body=observation(revision,approval,assignment,task,status='COMPLETED',remaining_work_minutes=0,
        expected_sequence=1,expected_operational_revision=state,observed_at=task['work_end'])
    app.dependency_overrides[utc_now]=lambda:datetime.fromisoformat(body['observed_at'])
    url=f"/api/v1/plan-revisions/{revision['id']}/execution-records"
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(client.post,url,headers=auth('CONTROLLER'),json=body) for _ in range(2)]
        responses=[job.result() for job in jobs]
    assert all(r.status_code==201 for r in responses),[r.text for r in responses]
    assert responses[0].json()['id']==responses[1].json()['id']
    with Session() as db:
        assert db.get(OperationalState,'SIMULATED').revision==state+1
        assert len(db.scalars(select(ExecutionRecord).where(ExecutionRecord.decision_id==uuid.UUID(approval['id']))).all())==1
