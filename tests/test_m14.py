"""M14 exact calendar horizons, canonical schedule views and exports."""
import copy
import csv
import io
import json
import os
import uuid
from datetime import date,datetime,timedelta,timezone
import pytest
from sqlalchemy import text,select
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.db import Session,engine
from railsync.main import app
from railsync.models import PlanningSnapshot,PlanningRun,PlanRevision,CoordinationRevision
from railsync.schedules import local_period,safe_cell
from railsync.validation import utc_now
from railsync.validator import content_hash
from railsync.planning import run_one
from test_m12 import NOW
from test_m13 import prepare,decision

def expanded_revision(client,parent,start,end):
    with Session.begin() as db:
        old=db.get(PlanningSnapshot,uuid.UUID(parent['snapshot_id']))
        manifest=copy.deepcopy(old.manifest)
        # M12 correctly requires duty-history evidence one day either side of the
        # horizon. Extend the test's persisted synthetic profile revisions so
        # current-facts hashing and independent validation agree on that fact.
        profiles={}
        for resource in manifest['facts']['resources']:
            previous=db.scalar(select(CoordinationRevision).where(
                CoordinationRevision.kind=='RESOURCE_PROFILE',CoordinationRevision.entity_key==resource['id']
            ).order_by(CoordinationRevision.revision.desc()).limit(1))
            payload=copy.deepcopy(previous.payload)
            payload['history']['start_at']=(start-timedelta(days=2)).isoformat()
            payload['history']['end_at']=(end+timedelta(days=2)).isoformat()
            updated=CoordinationRevision(kind='RESOURCE_PROFILE',entity_key=resource['id'],revision=previous.revision+1,payload=payload)
            db.add(updated);db.flush()
            profiles[resource['id']]={'id':str(updated.id),'revision':updated.revision,'payload':payload}
        for resource in manifest['facts']['resources']:
            resource['profile']=profiles[resource['id']]
        manifest['horizon_start']=start.isoformat();manifest['horizon_end']=end.isoformat()
        for coverage in manifest['validation_context']['coverage']:
            coverage['start_at']=(start-timedelta(hours=1)).isoformat()
            coverage['end_at']=(end+timedelta(hours=1)).isoformat()
            coverage['evidence_reference']='SYNTHETIC M14 full-period declaration'
    # Synthetic facts are permitted; solver results must come from a real run.
    def post(path,body):
        response=client.post('/api/v1/'+path,headers=auth(),json=body)
        assert response.status_code in (201,202),response.text
        return response.json()
    body={'horizon_start':start.isoformat(),'horizon_end':end.isoformat(),'track_ids':['AB'],
        'coordination_policy_id':manifest['facts']['coordination_policies'][0]['id']}
    draft=post('snapshots',body)
    current=client.get('/api/v1/snapshots/'+draft['id'],headers=auth()).json()['manifest']
    context=manifest['validation_context']
    context['facts_hash']=content_hash(current['facts'])
    snapshot=post('snapshots',{**body,'validation_context':context})
    sid=snapshot['id']
    post('priority-assessments',{'snapshot_id':sid,'assessed_at':NOW.isoformat()})
    availability=post('corridor-availability',{'snapshot_id':sid,'track_ids':['AB']})
    opportunity=post('maintenance-opportunities',{'snapshot_id':sid,'assessed_at':NOW.isoformat(),'availability_ids':[availability['id']]})
    coordination=post('coordinated-candidates',{'opportunity_id':opportunity['id']})
    run=post('planning-runs',{'snapshot_id':sid,'coordination_id':coordination['id'],'planner_type':'CP_SAT'})
    assert str(run_one())==run['id']
    saved=client.get('/api/v1/planning-runs/'+run['id'],headers=auth()).json()
    assert saved['status']=='COMPLETED' and saved['result']['has_incumbent'],saved
    return post('plan-revisions',{'run_id':run['id'],'expected_plan_hash':content_hash(saved['result'])})

def schedule_body(revision,kind='WEEKLY'):
    if kind=='WEEKLY':return {'plan_revision_id':revision['id'],'schedule_type':'WEEKLY',
        'timezone_name':'Asia/Kolkata','week_start':'2026-09-21'}
    return {'plan_revision_id':revision['id'],'schedule_type':'MONTHLY',
        'timezone_name':'Asia/Kolkata','year':2026,'month':9}

def test_weekly_schedule_requires_full_horizon_and_uses_canonical_assignments(client):
    _,parent,_=prepare(client)
    partial=client.post('/api/v1/planning-schedules',headers=auth(),json=schedule_body(parent))
    assert partial.status_code==409 and 'PLAN_HORIZON_DOES_NOT_COVER_PERIOD' in partial.text
    start=datetime.fromisoformat('2026-09-21T00:00:00+05:30');end=datetime.fromisoformat('2026-09-28T00:00:00+05:30')
    revision=expanded_revision(client,parent,start,end)
    response=client.post('/api/v1/planning-schedules',headers=auth(),json=schedule_body(revision))
    assert response.status_code==201,response.text
    schedule=response.json();content=schedule['content']
    assert content['period']['calendar_days']==7 and content['period']['duration_minutes']==10080
    assert content['status']=='TENTATIVE_PROPOSAL'
    assert [x['id'] for x in content['assignments']]==[x['id'] for x in revision['content']['assignments']]
    assert all(x['commitment_status']=='TENTATIVE' for x in content['assignments'])

def test_monthly_uses_real_calendar_boundaries_including_leap_year():
    start,end,first,last=local_period('MONTHLY','Asia/Kolkata',year=2028,month=2)
    assert first==date(2028,2,1) and last==date(2028,3,1)
    assert (last-first).days==29 and int((end-start).total_seconds()/60)==29*1440
    start,end,first,last=local_period('MONTHLY','Asia/Kolkata',year=2026,month=12)
    assert first==date(2026,12,1) and last==date(2027,1,1) and (last-first).days==31
    start,end,_,_=local_period('WEEKLY','America/New_York',week_start=date(2026,3,8))
    assert int((end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds()/60)==6*1440+23*60

def test_validated_approved_week_is_firm_and_stale_artifact_requires_attention(client):
    _,parent,_=prepare(client)
    start=datetime.fromisoformat('2026-09-21T00:00:00+05:30');end=datetime.fromisoformat('2026-09-28T00:00:00+05:30')
    revision=expanded_revision(client,parent,start,end)
    report=client.post('/api/v1/validation-reports',headers=auth(),json={
        'plan_revision_id':revision['id'],'expected_plan_hash':revision['plan_hash']})
    assert report.status_code==201 and report.json()['status']=='PASS',report.text
    approved=client.post(f"/api/v1/plan-revisions/{revision['id']}/decisions",headers=auth('CONTROLLER'),
        json=decision(revision,report.json()))
    assert approved.status_code==201,approved.text
    current=client.post('/api/v1/planning-schedules',headers=auth(),json=schedule_body(revision)).json()
    assert current['content']['status']=='APPROVED_PROPOSAL'
    assert current['content']['counts']['firm']==len(current['content']['assignments'])
    assert all(x['reservation_scope']=='SIMULATED' for x in current['content']['assignments'])
    app.dependency_overrides[utc_now]=lambda:NOW+timedelta(hours=5)
    stale=client.post('/api/v1/planning-schedules',headers=auth(),json=schedule_body(revision))
    assert stale.status_code==201,stale.text
    assert stale.json()['content']['status']=='STALE_APPROVED_PROPOSAL'
    assert all(x['commitment_status']=='REQUIRES_ATTENTION' for x in stale.json()['content']['assignments'])

def test_monthly_json_and_csv_exports_are_deterministic_labeled_and_safe(client):
    _,parent,_=prepare(client)
    start=datetime.fromisoformat('2026-09-01T00:00:00+05:30');end=datetime.fromisoformat('2026-10-01T00:00:00+05:30')
    revision=expanded_revision(client,parent,start,end)
    response=client.post('/api/v1/planning-schedules',headers=auth(),json=schedule_body(revision,'MONTHLY'))
    assert response.status_code==201,response.text
    schedule=response.json();sid=schedule['id']
    first=client.get(f'/api/v1/planning-schedules/{sid}/export?format=json',headers=auth('AUDITOR'))
    second=client.get(f'/api/v1/planning-schedules/{sid}/export?format=json',headers=auth('AUDITOR'))
    assert first.content==second.content
    assert first.headers['x-rmaps-content-hash']==schedule['content_hash']
    assert json.loads(first.content)==schedule['content']
    exported=client.get(f'/api/v1/planning-schedules/{sid}/export?format=csv',headers=auth('AUDITOR'))
    rows=list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert rows and all(x['authority']=='SOFTWARE_PROPOSAL_ONLY' for x in rows)
    assert {x['record_type'] for x in rows}<={'ASSIGNMENT','DEFERRED'}
    assert all(x['plan_hash']==revision['plan_hash'] for x in rows)
    assert safe_cell('=2+2')=="'=2+2" and safe_cell('@cmd')=="'@cmd"
    if path:=os.environ.get('RAILSYNC_M14_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as output:
            json.dump({'fixture':'SIMULATED monthly calendar; actual canonical plan and reproducible export metadata',
                'schedule':schedule,'csv_rows':rows},output,indent=2)

def test_schedule_validation_roles_timezone_and_immutability(client):
    _,parent,_=prepare(client)
    start=datetime.fromisoformat('2026-09-21T00:00:00+05:30');end=datetime.fromisoformat('2026-09-28T00:00:00+05:30')
    revision=expanded_revision(client,parent,start,end);body=schedule_body(revision)
    assert client.post('/api/v1/planning-schedules',headers=auth('AUDITOR'),json=body).status_code==403
    assert client.post('/api/v1/planning-schedules',headers=auth(),json={**body,'timezone_name':'Mars/Olympus'}).status_code==422
    assert client.post('/api/v1/planning-schedules',headers=auth(),json={**body,'year':2026}).status_code==422
    saved=client.post('/api/v1/planning-schedules',headers=auth(),json=body)
    assert saved.status_code==201
    assert client.get('/api/v1/planning-schedules/'+saved.json()['id'],headers=auth('AUDITOR')).status_code==200
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text("UPDATE planning_schedules SET schedule_type='MONTHLY'"))
