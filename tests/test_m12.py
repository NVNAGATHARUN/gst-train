"""Independent validator: real solved fixtures, mutation tests and persisted evidence."""
import ast
import copy
import json
import os
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from test_m10 import coordinated_pipeline,START,END,profile
from railsync.main import app
from railsync.planning import run_one
from railsync.db import engine
from railsync.validator import validate,content_hash,instant,Inspector
from railsync.validation import utc_now

NOW=datetime.fromisoformat('2026-09-21T00:00:00+05:30')

def context(manifest):
    coverage=[]
    for source,track in [(s,None) for s in ['NETWORK','REQUESTS','RESOURCES','COMMITMENTS']]+[(s,'AB') for s in ['OCCUPANCY','COA','FREIGHT']]:
        coverage.append({'source':source,'track_id':track,'start_at':'2026-09-20T23:00:00+05:30',
            'end_at':'2026-09-21T05:00:00+05:30','complete':True,'evidence_reference':'SYNTHETIC fixture: declared complete input dataset'})
    return {'scope':'SIMULATED','facts_hash':content_hash(manifest['facts']),
        'received_at':(NOW-timedelta(hours=1)).isoformat(),'valid_until':(NOW+timedelta(hours=4)).isoformat(),
        'coverage':coverage,'coa_semantics':'ACCESS_ENVELOPE','clearance_before_minutes':5,
        'clearance_after_minutes':5,'protect_freight_envelope':True,'commitments_known_empty':True,
        'rule_reference':'SYNTHETIC M12 rule set; not an operating authority'}

def run_fixture(client,with_context=True):
    coordination,_,snapshot_body=coordinated_pipeline(client)
    if with_context:
        old=client.get('/api/v1/snapshots/'+coordination['snapshot_id'],headers=auth()).json()['manifest']
        response=client.post('/api/v1/snapshots',headers=auth(),json={**snapshot_body,'validation_context':context(old)})
        assert response.status_code==201,response.text
        sid=response.json()['id']
        assert client.post('/api/v1/priority-assessments',headers=auth(),json={'snapshot_id':sid,'assessed_at':START}).status_code==201
        availability=client.post('/api/v1/corridor-availability',headers=auth(),json={'snapshot_id':sid,'track_ids':['AB']}).json()
        opportunity=client.post('/api/v1/maintenance-opportunities',headers=auth(),json={'snapshot_id':sid,'assessed_at':START,'availability_ids':[availability['id']]}).json()
        coordination=client.post('/api/v1/coordinated-candidates',headers=auth(),json={'opportunity_id':opportunity['id']}).json()
    queued=client.post('/api/v1/planning-runs',headers=auth(),json={'snapshot_id':coordination['snapshot_id'],
        'coordination_id':coordination['id'],'planner_type':'CP_SAT'}).json()
    assert run_one() is not None # old fixture baseline
    assert run_one() is not None
    run=client.get('/api/v1/planning-runs/'+queued['id'],headers=auth()).json()
    assert run['status']=='COMPLETED',run
    manifest=client.get('/api/v1/snapshots/'+coordination['snapshot_id'],headers=auth()).json()['manifest']
    return manifest,run['result'],queued['id']

@pytest.fixture
def solved(client):
    return run_fixture(client)

def inspect(manifest,plan,**options):
    return validate(manifest,content_hash(manifest),plan,content_hash(plan),NOW,
                    content_hash(manifest['facts']),**options)

def reseal(manifest,plan):
    manifest['validation_context']['facts_hash']=content_hash(manifest['facts'])
    plan['snapshot_hash']=content_hash(manifest)

def codes(report):return {f['code'] for check in report['checks'] for f in check['findings']}

def test_valid_solved_plan_persisted_report_and_no_client_clock(client,solved):
    manifest,plan,run_id=solved
    report=inspect(manifest,plan)
    assert report['status']=='PASS',report
    assert all(check['status']=='PASS' for check in report['checks'])
    app.dependency_overrides[utc_now]=lambda:NOW
    try:
        response=client.post('/api/v1/validation-reports',headers=auth(),json={'run_id':run_id,'expected_plan_hash':content_hash(plan)})
        assert response.status_code==201,response.text
        saved=response.json()
        assert saved['status']=='PASS' and saved['usable_for_review']
        assert client.get('/api/v1/validation-reports/'+saved['id'],headers=auth('AUDITOR')).json()==saved
        assert client.post('/api/v1/validation-reports',headers=auth(),json={'run_id':run_id,'expected_plan_hash':content_hash(plan),'checked_at':START}).status_code==422
        if path:=os.environ.get('RAILSYNC_M12_EVIDENCE_OUTPUT'):
            Path(path).write_text(json.dumps({'fixture':'SIMULATED; actual CP-SAT plan and independent report',
                'plan':plan,'validation_report':saved},indent=2),encoding='utf-8')
    finally:app.dependency_overrides.clear()
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text("UPDATE validation_reports SET status='FAIL'"))

@pytest.mark.parametrize('mutation,expected',[
    ('short_work','TASK_STAGE_MISMATCH'),('remove_crew','RESOURCE_REQUIREMENTS_NOT_MET'),
    ('duplicate_task','DUPLICATE_TASK'),('wrong_revision','REQUEST_REVISION_MISMATCH'),
    ('wrong_rule','POLICY_REVISION_MISMATCH'),('wrong_footprint','POSSESSION_FOOTPRINT_MISMATCH'),
    ('short_restoration','TASK_STAGE_MISMATCH'),('extra_resource','RESOURCE_REQUIREMENTS_NOT_MET'),
    ('naive_time','MALFORMED_OR_UNSUPPORTED_INPUT'),('unknown_mode','MALFORMED_OR_UNSUPPORTED_INPUT')])
def test_plan_corruption_cannot_pass(solved,mutation,expected):
    manifest,plan,_=solved
    b=plan['assignments'][0];t=b['tasks'][0]
    if mutation=='short_work':t['work_end']=(instant(t['work_end'])-timedelta(minutes=1)).isoformat()
    elif mutation=='remove_crew':b['allocations'].pop()
    elif mutation=='duplicate_task':plan['assignments'].append(copy.deepcopy(b))
    elif mutation=='wrong_revision':t['request_revision']+=1
    elif mutation=='wrong_rule':b['policy_revision_id']='changed'
    elif mutation=='wrong_footprint':b['track_ids']=[]
    elif mutation=='short_restoration':t['restore_end']=(instant(t['restore_end'])-timedelta(minutes=1)).isoformat()
    elif mutation=='extra_resource':b['allocations'].append(copy.deepcopy(b['allocations'][0]))
    elif mutation=='naive_time':t['work_start']='2026-09-21T01:35:00'
    elif mutation=='unknown_mode':b['mode']='MYSTERY'
    report=inspect(manifest,plan)
    assert report['status'] in ['FAIL','ERROR'] and report['approval_blocked']
    assert expected in codes(report),report

def shift_plan(plan,minutes):
    delta=timedelta(minutes=minutes)
    for b in plan['assignments']:
        for field in ['possession_start','possession_end']:b[field]=(instant(b[field])+delta).isoformat()
        for t in b['tasks']:
            for key in ['setup_start','setup_end','work_start','work_end','restore_start','restore_end','resource_start','resource_end']:
                t[key]=(instant(t[key])+delta).isoformat()
        for a in b['allocations']:
            for key in ['start_at','end_at']:a[key]=(instant(a[key])+delta).isoformat()

def test_raw_train_clearance_and_half_open_boundary(solved):
    manifest,plan,_=solved
    b=plan['assignments'][0]
    # Align to exactly 01:25; fixed train finishes 01:20 plus five-minute clearance.
    delta=(instant('2026-09-21T01:25:00+05:30')-instant(b['possession_start'])).total_seconds()/60
    shift_plan(plan,delta)
    assert inspect(manifest,plan)['status']=='PASS'
    shift_plan(plan,-1)
    assert 'TRAIN_CLEARANCE_VIOLATION' in codes(inspect(manifest,plan))

@pytest.mark.parametrize('mutation,expected',[
    ('mandatory','MANDATORY_UNSCHEDULED'),('deadline','DEADLINE_VIOLATION'),('earliest','EARLIEST_VIOLATION'),
    ('closed','TRACK_CLOSED'),('restriction','RESTRICTION_OVERLAP'),('isolation','ISOLATION_MISSING'),
    ('qualification','QUALIFICATION_MISSING_OR_EXPIRED'),('calendar','RESOURCE_CALENDAR_GAP'),
    ('capacity','POOL_CAPACITY_EXCEEDED'),('duty','ROLLING_DUTY_LIMIT'),('forbid','WORK_INCOMPATIBLE'),
    ('precedence','PRECEDENCE_VIOLATION'),('coa','COA_SOURCE_CONFLICT'),('expired','DATA_STALE_OR_FUTURE_RECEIPT'),
    ('coverage','CRITICAL_COVERAGE_GAP'),('imported','IMPORTED_AUTHORITY_UNVERIFIED')])
def test_changed_raw_facts_are_recomputed(solved,mutation,expected):
    m,p,_=solved
    facts=m['facts'];request=facts['requests'][0]['payload']
    if mutation=='mandatory':
        request['mandatory']=True;request['deadline_at']=END;p['assignments']=[]
    elif mutation=='deadline':request['deadline_at']='2026-09-21T01:30:00+05:30'
    elif mutation=='earliest':request['earliest_at']='2026-09-21T03:00:00+05:30'
    elif mutation=='closed':next(n for n in facts['network'] if n['id']=='AB')['payload']['status']='CLOSED'
    elif mutation=='restriction':facts['network'].append({'id':'X','kind':'restriction','revision':1,
        'payload':{'type':'CLOSURE','footprint':['AB'],'start':START,'end':END,'rule_id':'SYNTHETIC'}})
    elif mutation=='isolation':request['power_block_required']=True;request['isolation_zone']='missing'
    elif mutation=='qualification':facts['resources'][0]['profile']['payload']['qualifications'][0]['end_at']='2026-09-21T00:01:00+05:30'
    elif mutation=='calendar':facts['resources'][0]['profile']['payload']['calendar'][0]['end_at']='2026-09-21T00:01:00+05:30'
    elif mutation=='capacity':
        # Two same-type named units, actual combined demand 2, pool capacity 1.
        for r in facts['resources']:r['resource_type']='TRACK_CREW';r['profile']['payload']['pool_id']='P'
        for r in facts['requests']:r['payload']['requirements'][0]['type']='TRACK_CREW'
        for a in p['assignments'][0]['allocations']:a['resource_type']='TRACK_CREW'
        facts['coordination_policies'][0]['payload']['pools']=[{'id':'P','resource_type':'TRACK_CREW','calendar':[{'start_at':START,'end_at':END,'capacity':1}]}]
    elif mutation=='duty':facts['resources'][0]['profile']['payload']['max_duty_minutes_per_24h']=1
    elif mutation=='forbid':facts['coordination_policies'][0]['payload']['pairs'][0]['mode']='FORBID'
    elif mutation=='precedence':request['predecessors']=[facts['requests'][1]['id']]
    elif mutation=='coa':m['validation_context']['coa_semantics']='TRAFFIC_FREE'
    elif mutation=='expired':m['validation_context']['valid_until']=NOW.isoformat()
    elif mutation=='coverage':m['validation_context']['coverage']=[c for c in m['validation_context']['coverage'] if c['source']!='OCCUPANCY']
    elif mutation=='imported':m['validation_context']['scope']='IMPORTED'
    reseal(m,p)
    report=inspect(m,p)
    assert report['status']!='PASS' and expected in codes(report),report

def test_hash_mismatch_exception_timeout_and_missing_context(solved,monkeypatch):
    m,p,_=solved
    report=validate(m,'0'*64,p,content_hash(p),NOW,content_hash(m['facts']))
    assert report['status']=='FAIL' and 'SNAPSHOT_HASH_MISMATCH' in codes(report)
    assert 'PLAN_HASH_MISMATCH' in codes(validate(m,content_hash(m),p,'0'*64,NOW,content_hash(m['facts'])))
    assert 'VALIDATION_BUDGET_EXCEEDED' in codes(inspect(m,p,max_seconds=0))
    del m['validation_context'];p['snapshot_hash']=content_hash(m)
    assert inspect(m,p)['status']=='ERROR'
    def crash(self):raise RuntimeError('deliberate validator failure')
    monkeypatch.setattr(Inspector,'run',crash)
    report=inspect(m,p)
    assert report['status']=='ERROR' and 'VALIDATOR_EXCEPTION' in codes(report)

def test_reports_expire_on_time_and_current_resource_revision(client,solved):
    m,p,run_id=solved
    app.dependency_overrides[utc_now]=lambda:NOW
    try:
        saved=client.post('/api/v1/validation-reports',headers=auth(),json={'run_id':run_id,'expected_plan_hash':content_hash(p)}).json()
        assert saved['usable_for_review']
        app.dependency_overrides[utc_now]=lambda:NOW+timedelta(hours=5)
        current=client.get('/api/v1/validation-reports/'+saved['id'],headers=auth()).json()
        assert current['status']=='PASS' and not current['usable_for_review']
        assert 'DATA_STALE_OR_UNKNOWN' in current['current_blockers']
        app.dependency_overrides[utc_now]=lambda:NOW
        changed=profile(max_duty_minutes_per_24h=1)
        assert client.post('/api/v1/resources/CREW-1/profiles',headers=auth(),json={'expected_revision':1,'data':changed}).status_code==201
        current=client.get('/api/v1/validation-reports/'+saved['id'],headers=auth()).json()
        assert not current['usable_for_review'] and 'OPERATIONAL_STATE_CHANGED' in current['current_blockers']
        fresh=client.post('/api/v1/validation-reports',headers=auth(),json={'run_id':run_id,'expected_plan_hash':content_hash(p)}).json()
        assert fresh['status']=='FAIL' and 'OPERATIONAL_STATE_CHANGED' in codes(fresh['result'])
    finally:app.dependency_overrides.clear()

def test_api_roles_and_stale_expected_plan_hash(client,solved):
    _,p,run_id=solved
    body={'run_id':run_id,'expected_plan_hash':content_hash(p)}
    assert client.post('/api/v1/validation-reports',headers=auth('AUDITOR'),json=body).status_code==403
    assert client.post('/api/v1/validation-reports',headers=auth(),json={**body,'expected_plan_hash':'0'*64}).status_code==409

def test_no_scheduler_feasibility_imports_and_poisoned_cached_output(solved,monkeypatch):
    from railsync import validator,validator_resources,resource_engine,coordination_engine,availability,solver
    forbidden={'solver','planning','resource_engine','coordination_engine','availability','opportunities','intervals'}
    for module in [validator,validator_resources]:
        tree=ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):assert not forbidden.intersection((node.module or '').split('.'))
    def poison(*args,**kwargs):raise AssertionError('validator called scheduler predicate')
    for module,name in [(resource_engine,'resource_feasible'),(coordination_engine,'task_checks'),(availability,'compute_availability'),(solver,'solve')]:
        monkeypatch.setattr(module,name,poison)
    m,p,_=solved
    p['counts']={'scheduled':999999};p['objective_value']=-999999
    # Informational/cached optimizer fields are not feasibility evidence.
    assert inspect(m,p)['status']=='PASS'
    p['assignments'][0]['allocations']=[]
    assert 'RESOURCE_REQUIREMENTS_NOT_MET' in codes(inspect(m,p))

def test_frozen_content_and_completed_work_cannot_be_changed(solved):
    m,p,_=solved
    b=p['assignments'][0]
    m['facts']['commitments']=[{'id':'FROZEN','candidate_id':b['id'],'frozen':True,'assignment_hash':content_hash(b)}]
    m['validation_context']['commitments_known_empty']=False
    reseal(m,p)
    assert inspect(m,p)['status']=='PASS'
    b['tasks'][0]['work_end']=(instant(b['tasks'][0]['work_end'])-timedelta(minutes=1)).isoformat()
    assert 'FROZEN_WORK_CHANGED' in codes(inspect(m,p))
    m['facts']['completed_work']=[{'request_id':b['request_ids'][0],'verified':True}]
    reseal(m,p)
    assert 'COMPLETED_WORK_RESCHEDULED' in codes(inspect(m,p))

def test_travel_rest_missing_history_and_overlap_recomputed(solved):
    original,plan,_=solved
    for mutation,expected in [('travel','TRAVEL_TIME_UNKNOWN'),('home','HOME_TRAVEL_VIOLATION'),
            ('rest','TRAVEL_OR_REST_VIOLATION'),('overlap','RESOURCE_OVERLAP'),('history','DUTY_HISTORY_UNKNOWN')]:
        m,p=copy.deepcopy(original),copy.deepcopy(plan)
        resource=m['facts']['resources'][0]
        profile=resource['profile']['payload']
        begin=instant(p['assignments'][0]['possession_start'])
        if mutation in ['travel','home']:
            profile['home_track']='BC'
            if mutation=='home':m['facts']['coordination_policies'][0]['payload']['travel']=[
                {'resource_type':resource['resource_type'],'from_track':'BC','to_track':'AB','minutes':240}]
        elif mutation in ['rest','overlap']:
            end=begin-timedelta(minutes=5) if mutation=='rest' else begin+timedelta(minutes=5)
            profile['duties']=[{'start_at':(begin-timedelta(minutes=30)).isoformat(),'end_at':end.isoformat(),'track_id':'AB'}]
            profile['min_rest_minutes']=10
        else:profile['history']['end_at']=END
        reseal(m,p)
        report=inspect(m,p)
        assert report['status']!='PASS' and expected in codes(report),report

def test_triple_group_hazard_overrides_pair_permissions(solved):
    m,p,_=solved
    block=p['assignments'][0]
    original=next(r for r in m['facts']['requests'] if r['payload']['department']=='ENGINEERING')
    r=copy.deepcopy(original);r['id']='SYNTHETIC-THIRD-REQUEST';r['payload']['issue_type']='OTHER_WORK'
    m['facts']['requests'].append(r)
    t=copy.deepcopy(next(t for t in block['tasks'] if t['request_id']==original['id']))
    t['request_id']=r['id'];t['issue_type']='OTHER_WORK'
    block['tasks'].append(t);block['request_ids'].append(r['id'])
    unit=copy.deepcopy(next(u for u in m['facts']['resources'] if u['department']=='ENGINEERING'))
    unit['id']='SYNTHETIC-THIRD-CREW';unit['profile']['id']='THIRD-PROFILE'
    unit['profile']['payload']['qualifications'][0]['skill']='OTHER_WORK'
    m['facts']['resources'].append(unit)
    a=copy.deepcopy(next(a for a in block['allocations'] if a['request_id']==original['id']))
    a.update(request_id=r['id'],resource_id=unit['id'],qualification='OTHER_WORK')
    block['allocations'].append(a)
    signatures=[{'department':r['payload']['department'],'issue_type':r['payload']['issue_type'],
        'power_state':'ANY','signalling_state':'ANY'} for r in m['facts']['requests']]
    third=next(s for s in signatures if s['issue_type']=='OTHER_WORK')
    policy=m['facts']['coordination_policies'][0]['payload']
    for index,signature in enumerate(s for s in signatures if s!=third):
        policy['pairs'].append({'id':'EXPLICIT-PAIR-'+str(index),'left':signature,'right':third,'footprint_relation':'SAME',
            'mode':'ALLOW_PARALLEL','shared_setup':True,'shared_restoration':True})
    policy['groups']=[{'id':'EXPLICIT-TRIPLE','members':signatures,'mode':'ALLOW_PARALLEL'}]
    block['rule_ids']=[r['id'] for r in policy['pairs']]+['EXPLICIT-TRIPLE']
    reseal(m,p)
    assert inspect(m,p)['status']=='PASS'
    policy['groups'][0]['mode']='FORBID'
    reseal(m,p)
    assert 'GROUP_WORK_INCOMPATIBLE' in codes(inspect(m,p))

def test_snapshot_includes_adjacent_occupancy_and_refuses_stale_declaration(client):
    from test_m06 import prepare_baseline
    prepare_baseline(client)
    train={'train_id':'PRE-HORIZON','train_name':'SYNTHETIC adjacent train','train_type':'PASSENGER','service_date':'2026-09-20',
        'source_mode':'SIMULATED','source_revision':1,'occupancies':[{'track_id':'AB','route_sequence':1,
        'enter_at':'2026-09-20T23:55:00+05:30','exit_at':'2026-09-20T23:59:00+05:30'}]}
    assert client.post('/api/v1/operations/train-runs',headers=auth(),json=train).status_code==201
    body={'horizon_start':START,'horizon_end':END,'track_ids':['AB']}
    snapshot=client.post('/api/v1/snapshots',headers=auth(),json=body).json()
    manifest=client.get('/api/v1/snapshots/'+snapshot['id'],headers=auth()).json()['manifest']
    assert any(o['train_id']=='PRE-HORIZON' for o in manifest['facts']['occupancy'])
    invalid=context(manifest);invalid['facts_hash']='0'*64
    assert client.post('/api/v1/snapshots',headers=auth(),json={**body,'validation_context':invalid}).status_code==409

def test_validation_api_persists_error_for_legacy_context_missing(client):
    _,plan,run_id=run_fixture(client,with_context=False)
    app.dependency_overrides[utc_now]=lambda:NOW
    try:
        response=client.post('/api/v1/validation-reports',headers=auth(),json={'run_id':run_id,'expected_plan_hash':content_hash(plan)})
        assert response.status_code==201
        report=response.json()
        assert report['status']=='ERROR' and not report['usable_for_review']
        assert 'COVERAGE_DECLARATION_MISSING' in codes(report['result'])
    finally:app.dependency_overrides.clear()

def test_malformed_top_level_and_unknown_deadline_fail_closed(solved):
    assert validate(None,'0'*64,{},'0'*64,None)['status']=='ERROR'
    m,p,_=solved
    m['facts']['requests'][0]['payload']['deadline_kind']='UNKNOWN_RULE'
    reseal(m,p)
    assert inspect(m,p)['status']=='ERROR'
    assert inspect(m,p,max_checks=1)['status']=='ERROR'
