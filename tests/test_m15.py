"""M15 fair, same-fact KPI comparison with no manufactured gains."""
import json,os,uuid,copy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from railsync.db import engine,Session
from railsync.models import PlanningRun
from railsync.kpi_metrics import metrics,comparison_metrics,DEFINITIONS
from railsync.main import app
from railsync.planning import run_one
from railsync.validation import utc_now
from railsync.validator import content_hash
from test_m12 import run_fixture,NOW

def plans(client):
    _,cp,cp_run=run_fixture(client)
    config=client.get('/api/v1/planning-runs/'+cp_run,headers=auth()).json()['config']
    queued=client.post('/api/v1/planning-runs',headers=auth(),json={**config,'planner_type':'BASELINE'});assert queued.status_code==202
    assert run_one() is not None
    baseline=client.get('/api/v1/planning-runs/'+queued.json()['id'],headers=auth()).json()['result']
    out=[]
    for run,plan in [(queued.json()['id'],baseline),(cp_run,cp)]:
        revision=client.post('/api/v1/plan-revisions',headers=auth(),json={'run_id':run,'expected_plan_hash':content_hash(plan)});assert revision.status_code==201
        report=client.post('/api/v1/validation-reports',headers=auth(),json={'plan_revision_id':revision.json()['id'],'expected_plan_hash':revision.json()['plan_hash']});assert report.status_code==201 and report.json()['status']=='PASS'
        out.append(revision.json())
    return out

def test_same_snapshot_comparison_uses_persisted_intervals_and_honest_nulls(client):
    app.dependency_overrides[utc_now]=lambda:NOW
    baseline,railsync=plans(client)
    response=client.post('/api/v1/plan-comparisons',headers=auth(),json={'baseline_plan_revision_id':baseline['id'],'railsync_plan_revision_id':railsync['id']})
    assert response.status_code==201,response.text
    content=response.json()['content'];assert content['status']=='VALIDATED_COMPARISON' and content['claims_permitted']
    assert content['baseline']['metrics']['planned_not_completed'] is True
    assert content['metrics']['measured_train_delay_minutes']['status']=='NOT_AVAILABLE'
    assert content['metrics']['forecast_exposure_train_track_seconds']['formula'].startswith('sum assignment')
    assert content['metrics']['requests_scheduled']['baseline']==baseline['content']['counts']['scheduled']
    assert content['metrics']['reserved_track_minutes']['percent_change'] is None or isinstance(content['metrics']['reserved_track_minutes']['percent_change'],(int,float))
    if path:=os.environ.get('RAILSYNC_M15_EVIDENCE_OUTPUT'):
        with open(path,'w',encoding='utf-8') as f:json.dump({'fixture':'SIMULATED same-snapshot baseline and CP-SAT plans','comparison':response.json()},f,indent=2)

def test_comparison_rejects_wrong_planners_roles_and_immutable_output(client):
    app.dependency_overrides[utc_now]=lambda:NOW
    baseline,railsync=plans(client)
    body={'baseline_plan_revision_id':baseline['id'],'railsync_plan_revision_id':railsync['id']}
    assert client.post('/api/v1/plan-comparisons',headers=auth('AUDITOR'),json=body).status_code==403
    assert client.post('/api/v1/plan-comparisons',headers=auth(),json={'baseline_plan_revision_id':railsync['id'],'railsync_plan_revision_id':baseline['id']}).status_code==422
    saved=client.post('/api/v1/plan-comparisons',headers=auth(),json=body);assert saved.status_code==201
    assert client.get('/api/v1/plan-comparisons/'+saved.json()['id'],headers=auth('AUDITOR')).status_code==200
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text("UPDATE plan_comparisons SET content='{}'"))


def test_hand_calculated_parallel_union_coverage_and_fractional_minutes():
    # Explicit synthetic input to the metric calculator, never a persisted solver output.
    at=lambda minutes:(NOW+timedelta(minutes=minutes)).isoformat()
    requests=[{'id':rid,'payload':{'criticality':5,'mandatory':True,'deadline_at':at(100),
        'deadline_kind':'RESTORED_BY'}} for rid in ('a','b','deferred')]
    def block(id,rid,begin,finish):
        return {'id':id,'request_ids':[rid],'track_ids':['AB'],
            'possession_start':at(begin),'possession_end':at(finish),
            'tasks':[{'request_id':rid,'work_start':at(begin+10),'work_end':at(finish-10),'restore_end':at(finish)}]}
    first=block('1','a',0,60)
    first['tasks'].append({'request_id':'b','work_start':at(10),'work_end':at(40),'restore_end':at(60)})
    first['request_ids'].append('b')
    snapshot=SimpleNamespace(manifest={'horizon_start':at(0),'horizon_end':at(120),'track_ids':['AB'],
        'facts':{'requests':requests,'freight':[]}})
    plan={'schedule_status':'DEVELOPMENT_ARTIFACT','planner':'CP_SAT','solver_status':'OPTIMAL','assignments':[first]}
    result=metrics(plan,snapshot)
    assert result['task_work_minutes']==70
    assert result['reserved_track_minutes']==60
    assert result['block_utilization_basis_points']==pytest.approx(40/60*10000)
    assert result['mandatory_coverage_basis_points']==pytest.approx(2/3*10000)
    assert result['denominators']['on_time_coverage_basis_points']=={'numerator':2,'denominator':3,'unit':'requests'}
    assert result['maintenance_track_availability_basis_points']==5000
    # Overlapping reservations are counted once per track, including seconds.
    plan['assignments']=[block('1','a',0,60.5),block('2','b',30,90)]
    assert metrics(plan,snapshot)['reserved_track_minutes']==90
    plan['assignments']=[block('1','a',0,60.5)]
    assert metrics(plan,snapshot)['reserved_track_minutes']==60.5
    unknown=metrics({**plan,'solver_status':'UNKNOWN','schedule_status':'UNKNOWN','assignments':[]},snapshot)
    assert unknown['requests_scheduled'] is None and unknown['reserved_track_minutes'] is None
    empty=metrics({**plan,'assignments':[]},snapshot)
    assert empty['requests_scheduled']==0 and empty['block_utilization_basis_points'] is None


def test_negative_percentage_is_percent_and_zero_denominator_is_na():
    left={k:None for k in DEFINITIONS};right=dict(left)
    left['reserved_track_minutes']=100;right['reserved_track_minutes']=125
    left['requests_scheduled']=4;right['requests_scheduled']=3
    left['possession_count']=0;right['possession_count']=1
    output=comparison_metrics(left,right)
    assert output['reserved_track_minutes']['percent_change']==25
    assert output['reserved_track_minutes']['improvement_percent']==-25
    assert output['requests_scheduled']['improvement_percent']==-25
    assert output['possession_count']['improvement_percent'] is None
    assert output['possession_count']['raw_delta']==1
    assert output['forecast_exposure_train_track_seconds']['unit']=='expected_train_track_seconds'


def test_config_mismatch_and_run_provenance_are_rejected(client):
    app.dependency_overrides[utc_now]=lambda:NOW
    baseline,railsync=plans(client)
    body={'baseline_plan_revision_id':baseline['id'],'railsync_plan_revision_id':railsync['id']}
    with Session.begin() as db:
        run=db.get(PlanningRun,uuid.UUID(baseline['run_id']))
        old=copy.deepcopy(run.config)
        run.config={**old,'clearance_minutes':0}
    response=client.post('/api/v1/plan-comparisons',headers=auth(),json=body)
    assert response.status_code==409 and 'COMPARISON_CONFIGURATION_MISMATCH' in response.text
    with Session.begin() as db:
        run=db.get(PlanningRun,uuid.UUID(baseline['run_id']))
        run.config=old
        run.result={**run.result,'counts':{'scheduled':999}}
    response=client.post('/api/v1/plan-comparisons',headers=auth(),json=body)
    assert response.status_code==409 and 'PLAN_RUN_MISMATCH' in response.text


def test_comparison_export_is_stable_but_current_claims_expire(client):
    app.dependency_overrides[utc_now]=lambda:NOW
    baseline,railsync=plans(client)
    saved=client.post('/api/v1/plan-comparisons',headers=auth(),json={
        'baseline_plan_revision_id':baseline['id'],'railsync_plan_revision_id':railsync['id']}).json()
    assert saved['current_claims_permitted']
    path='/api/v1/plan-comparisons/'+saved['id']
    exported=client.get(path+'/export',headers=auth('AUDITOR'))
    assert exported.json()==saved['content']
    app.dependency_overrides[utc_now]=lambda:NOW+timedelta(hours=5)
    stale=client.get(path,headers=auth('AUDITOR')).json()
    assert not stale['current_claims_permitted'] and stale['content']==saved['content']
    after=client.get(path+'/export',headers=auth('AUDITOR'))
    assert after.content==exported.content
    assert after.headers['x-rmaps-current-claims-permitted']=='false'
