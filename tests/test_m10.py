"""Labeled synthetic operating rules. Assertions are hand-calculated expectations."""
import copy
import json
import os
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from conftest import auth
from test_m02 import request_data
from test_m06 import prepare_baseline
from railsync.db import engine
from railsync.coordination import CoordinationInput
from railsync.coordination_engine import compatibility
from railsync.resource_engine import (dt, resource_feasible, allocate, pool_constraints, duty_constraints)

START='2026-09-21T00:00:00+05:30'
END='2026-09-21T04:00:00+05:30'
HORIZON=(dt(START),dt(END))

def sig(department='ENGINEERING',issue_type='INSPECTION',**changes):
    return {'department':department,'issue_type':issue_type,'power_state':'ANY','signalling_state':'ANY',**changes}

def policy(mode='ALLOW_PARALLEL'):
    return {'source_mode':'SIMULATED','rule_reference':'SYNTHETIC-M10-NOT-AN-OPERATING-RULE',
        'pairs':[{'id':'PAIR-ENG-TRD','left':sig(),'right':sig('TRD','OHE_WORK'),
                  'footprint_relation':'SAME','mode':mode,'shared_setup':True,'shared_restoration':True}],
        'groups':[],'travel':[],'pools':[]}

def profile(department='ENGINEERING',skill='INSPECTION',**changes):
    return {'source_mode':'SIMULATED','rule_reference':'SYNTHETIC-CREW-POLICY',
        'departments':[department],'qualifications':[{'skill':skill,'start_at':START,'end_at':END}],
        'calendar':[{'start_at':START,'end_at':END}],'home_track':'AB',
        'history':{'start_at':'2026-09-20T00:00:00+05:30','end_at':'2026-09-22T04:00:00+05:30'},
        'duties':[],'min_rest_minutes':0,'max_duty_minutes_per_24h':480,'pool_id':None,**changes}

def unit(id='CREW-1',**changes):
    return {'id':id,'resource_type':'TRACK_CREW','department':'ENGINEERING',
        'available_start':START,'available_end':END,'source_mode':'SIMULATED',
        'profile':{'id':'PROFILE-1','revision':1,'payload':profile()},**changes}

def allocation(start='2026-09-21T01:00:00+05:30',end='2026-09-21T02:00:00+05:30',**changes):
    return {'request_id':'r1','resource_id':'CREW-1','resource_type':'TRACK_CREW','qualification':'INSPECTION',
        'department':'ENGINEERING','track_id':'AB','start_at':start,'end_at':end,**changes}

def submit(client,request):
    for action in ['VALIDATE','SUBMIT']:
        response=client.post(f"/api/v1/maintenance-requests/{request['id']}/transitions",
            json={'action':action,'expected_revision':request['revision'],'reason':'SYNTHETIC M10 fixture'},
            headers=auth(request['data']['department']))
        assert response.status_code==200,response.text

def coordinated_pipeline(client,mode='ALLOW_PARALLEL',work=60,policy_override=None,profile_override=None):
    h=auth()
    prepare_baseline(client,work_minutes=work)
    request=client.get('/api/v1/maintenance-requests',headers=auth('ENGINEERING')).json()['items'][0]
    request=client.patch('/api/v1/maintenance-requests/'+request['id'],headers=auth('ENGINEERING'),
        json={'expected_revision':1,'data':{**request['data'],'power_state':'ANY','signalling_state':'ANY'}}).json()
    submit(client,request)
    response=client.post('/api/v1/network/asset',headers=h,json={'id':'AS-TRD','data':{
        'department':'TRD','asset_type':'OHE','footprint':['AB']}})
    assert response.status_code==201,response.text
    second=client.post('/api/v1/maintenance-requests',headers=auth('TRD'),json=request_data(
        department='TRD',asset_id='AS-TRD',issue_type='OHE_WORK',work_minutes=20,
        power_state='ANY',signalling_state='ANY',requirements=[{'type':'OHE_CREW','quantity':1}])).json()
    submit(client,second)
    response=client.post('/api/v1/resources',headers=h,json={'id':'CREW-2','resource_type':'OHE_CREW',
        'department':'TRD','available_start':START,'available_end':END,'source_mode':'SIMULATED'})
    assert response.status_code==201,response.text
    for id,p in [('CREW-1',profile_override or profile()),('CREW-2',profile('TRD','OHE_WORK'))]:
        response=client.post(f'/api/v1/resources/{id}/profiles',headers=h,json={'expected_revision':0,'data':p})
        assert response.status_code==201,response.text
    response=client.post('/api/v1/coordination-policies/DEMO',headers=h,
        json={'expected_revision':0,'data':policy_override or policy(mode)})
    assert response.status_code==201,response.text
    policy_id=response.json()['id']
    snapshot_body={'horizon_start':START,'horizon_end':END,'track_ids':['AB'],'coordination_policy_id':policy_id}
    snapshot=client.post('/api/v1/snapshots',headers=h,json=snapshot_body).json()
    assert 'id' in snapshot,snapshot
    snapshot_id=snapshot['id']
    assert client.post('/api/v1/priority-assessments',headers=h,json={'snapshot_id':snapshot_id,'assessed_at':START}).status_code==201
    avail=client.post('/api/v1/corridor-availability',headers=h,json={'snapshot_id':snapshot_id,'track_ids':['AB']}).json()
    opportunity=client.post('/api/v1/maintenance-opportunities',headers=h,json={
        'snapshot_id':snapshot_id,'assessed_at':START,'availability_ids':[avail['id']]}).json()
    body={'opportunity_id':opportunity['id']}
    response=client.post('/api/v1/coordinated-candidates',headers=h,json=body)
    assert response.status_code==201,response.text
    return response.json(),body,snapshot_body

def test_parallel_exact_backend_output_persistence_and_snapshot_isolation(client):
    output,body,snapshot_body=coordinated_pipeline(client)
    bundles=[c for c in output['result']['candidates'] if len(c['request_ids'])==2]
    first=next(c for c in bundles if c['possession_start']=='2026-09-21T01:25:00+05:30')
    assert first['possession_end']=='2026-09-21T02:45:00+05:30'
    assert first['costs']=={'reserved_track_minutes':80,'forecast_exposure_train_track_seconds':0,
                           'incremental_travel_minutes_against_fixed_duties':0}
    assert {a['resource_id'] for a in first['allocations']}=={'CREW-1','CREW-2'}
    assert {t['work_start'] for t in first['tasks']}=={'2026-09-21T01:35:00+05:30'}
    by_department={t['department']:t for t in first['tasks']}
    assert by_department['ENGINEERING']['work_end']=='2026-09-21T02:35:00+05:30'
    assert by_department['TRD']['work_end']=='2026-09-21T01:55:00+05:30'
    assert all(t['restore_start']=='2026-09-21T02:35:00+05:30' for t in first['tasks'])
    assert 'SIMULATED_RULES_NOT_OPERATIONAL_AUTHORITY' in output['result']['review_blockers']
    saved=client.get('/api/v1/coordinated-candidates/'+output['id'],headers=auth()).json()
    assert saved['result']==output['result']
    assert client.post('/api/v1/coordinated-candidates',headers=auth(),json=body).json()['duplicate'] is True
    # Later loss of a qualification changes a NEW snapshot, never this computation.
    expired=profile(qualifications=[{'skill':'UNRELATED','start_at':START,'end_at':END}])
    assert client.post('/api/v1/resources/CREW-1/profiles',headers=auth(),json={'expected_revision':1,'data':expired}).status_code==201
    fresh=client.post('/api/v1/snapshots',headers=auth(),json=snapshot_body).json()
    assert fresh['id']!=output['snapshot_id']
    assert client.get('/api/v1/coordinated-candidates/'+output['id'],headers=auth()).json()['result']==saved['result']
    if path:=os.environ.get('RAILSYNC_M18_DEMO_BUNDLE_OUTPUT') or os.environ.get('RAILSYNC_EVIDENCE_OUTPUT'):
        Path(path).write_text(json.dumps({'fixture':'SIMULATED M10 parallel ENG/TRD','verified_candidate':first,
            'persisted_computation':saved},indent=2),encoding='utf-8')

def test_sequential_uses_sum_and_stage_order(client):
    output,_,_=coordinated_pipeline(client,mode='ALLOW_SEQUENTIAL',work=20)
    bundles=[c for c in output['result']['candidates'] if len(c['request_ids'])==2]
    assert bundles
    for c in bundles:
        assert c['costs']['reserved_track_minutes']==80 # 2 * (10 + 20 + 10)
        left,right=c['tasks']
        assert left['restore_end']==right['setup_start']
        assert left['work_end']!=right['work_end']

def test_unknown_compatibility_keeps_singles_and_rejects_bundle(client):
    p=policy()
    p['pairs']=[]
    output,_,_=coordinated_pipeline(client,policy_override=p)
    assert output['result']['candidates']
    assert all(len(c['request_ids'])==1 for c in output['result']['candidates'])
    assert any(e['code']=='COMPATIBILITY_UNKNOWN' for e in output['result']['exclusions'])
    if path:=os.environ.get('RAILSYNC_M18_DEMO_DISABLED_OUTPUT'):
        Path(path).write_text(json.dumps({'fixture':'SIMULATED M10 compatibility-disabled variant',
            'candidate_count':len(output['result']['candidates']),
            'bundle_count':sum(len(c['request_ids'])>1 for c in output['result']['candidates']),
            'exclusions':output['result']['exclusions'],
            'review_blockers':output['result']['review_blockers']},indent=2),encoding='utf-8')

def test_unqualified_resources_and_search_caps_are_visible(client):
    p=profile(qualifications=[{'skill':'OTHER','start_at':START,'end_at':END}])
    output,body,_=coordinated_pipeline(client,profile_override=p)
    assert all(t['department']=='TRD' for c in output['result']['candidates'] for t in c['tasks'])
    assert any('QUALIFICATION_MISSING_OR_EXPIRED' in e.get('details',[]) for e in output['result']['exclusions'])
    limited=client.post('/api/v1/coordinated-candidates',headers=auth(),json={**body,'max_candidates':1}).json()['result']
    assert len(limited['candidates'])==1
    assert limited['search']['pruning'] and not limited['search']['complete_within_declared_search']

def test_rule_revision_auth_validation_and_database_immutability(client):
    p=policy()
    body={'expected_revision':0,'data':p}
    assert client.post('/api/v1/coordination-policies/P',json=body,headers=auth('AUDITOR')).status_code==403
    response=client.post('/api/v1/coordination-policies/P',json=body,headers=auth())
    assert response.status_code==201
    assert client.post('/api/v1/coordination-policies/P',json=body,headers=auth()).status_code==409
    p['pairs']*=2
    assert client.post('/api/v1/coordination-policies/Q',json={'expected_revision':0,'data':p},headers=auth()).status_code==422
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as db:db.execute(text("UPDATE coordination_revisions SET revision=9"))

def test_group_and_electrical_hazards_override_pair_permissions():
    a={'payload':{**request_data(),**sig(),'power_block_required':False}}
    b={'payload':{**request_data(),**sig('TRD','OHE_WORK'),'power_block_required':False}}
    c={'payload':{**request_data(),**sig('SNT','TEST'),'power_block_required':False}}
    p=policy()
    p['pairs'] += [{**p['pairs'][0],'id':'a-c','right':sig('SNT','TEST')},
                  {**p['pairs'][0],'id':'b-c','left':sig('TRD','OHE_WORK'),'right':sig('SNT','TEST')}]
    assert compatibility([a,b,c],p)[2]=='GROUP_COMPATIBILITY_UNKNOWN'
    p['groups']=[{'id':'TRIPLE','members':[sig(),sig('TRD','OHE_WORK'),sig('SNT','TEST')],'mode':'FORBID'}]
    assert compatibility([a,b,c],p)[2]=='GROUP_COMPATIBILITY_FORBIDDEN'
    a['payload']['power_state']='OFF'
    b['payload']['power_state']='ON'
    p['pairs'][0]['left']['power_state']='OFF'
    p['pairs'][0]['right']['power_state']='ON'
    assert compatibility([a,b],p)[2]=='CONTRADICTORY_POWER_STATES'

def test_qualification_expiry_calendar_history_and_repeated_resource_demand():
    r=unit()
    assert resource_feasible(r,[allocation()],policy(),HORIZON)[0]
    r['profile']['payload']['qualifications'][0]['end_at']='2026-09-21T01:59:59+05:30'
    assert resource_feasible(r,[allocation()],policy(),HORIZON)[1]=='QUALIFICATION_MISSING_OR_EXPIRED'
    r=unit()
    r['profile']['payload']['history']['start_at']=START
    assert resource_feasible(r,[allocation()],policy(),HORIZON)[1]=='DUTY_HISTORY_COVERAGE_UNKNOWN'
    r=unit()
    task={'request_id':'r','department':'ENGINEERING','issue_type':'INSPECTION','resource_location':'AB',
          'resource_start':'2026-09-21T01:00:00+05:30','resource_end':'2026-09-21T02:00:00+05:30',
          'requirements':[{'type':'TRACK_CREW','quantity':1},{'type':'TRACK_CREW','quantity':1}]}
    assignments,reasons,_=allocate([task],[r],policy(),HORIZON,CoordinationInput(opportunity_id='00000000-0000-0000-0000-000000000001').model_dump())
    assert assignments==[] and 'NAMED_RESOURCE_OVERLAP' in reasons
    r['profile']['payload']['calendar'][0]['end_at']='2026-09-21T01:59:00+05:30'
    assert resource_feasible(r,[allocation()],policy(),HORIZON)[1]=='RESOURCE_CALENDAR_GAP'

def test_travel_and_rest_across_midnight_and_half_open_boundary():
    r=unit()
    r['profile']['payload']['duties']=[{'start_at':'2026-09-20T23:00:00+05:30','end_at':START,'track_id':'BC'}]
    r['profile']['payload']['min_rest_minutes']=30
    assert resource_feasible(r,[allocation()],policy(),HORIZON)[1]=='TRAVEL_TIME_UNKNOWN'
    p=policy()
    p['travel']=[{'resource_type':'TRACK_CREW','from_track':'BC','to_track':'AB','minutes':30}]
    assert resource_feasible(r,[allocation()],p,HORIZON)[0] # exactly 30 travel + 30 rest
    too_soon=allocation(start='2026-09-21T00:59:00+05:30')
    assert resource_feasible(r,[too_soon],p,HORIZON)[1]=='TRAVEL_OR_REST_SHORTFALL'
    r=unit()
    adjacent=[allocation(),allocation(start='2026-09-21T02:00:00+05:30',end='2026-09-21T03:00:00+05:30')]
    assert resource_feasible(r,adjacent,policy(),HORIZON)[0]

def test_pool_triple_and_rolling_duty_have_aggregate_constraints():
    resources=[unit(str(i)) for i in range(3)]
    for r in resources:r['profile']['payload']['pool_id']='SHARED'
    p=policy()
    p['pools']=[{'id':'SHARED','resource_type':'TRACK_CREW','calendar':[{'start_at':START,'end_at':END,'capacity':2}]}]
    candidates=[{'id':str(i),'allocations':[allocation(resource_id=str(i))]} for i in range(3)]
    constraints=pool_constraints(candidates,resources,p)
    assert len(constraints)==1
    assert constraints[0]['capacity']==2 and constraints[0]['coefficients']=={'0':1,'1':1,'2':1}
    # Every pair fits; the triple does not. Selector must enforce this row.
    r=unit()
    r['profile']['payload']['max_duty_minutes_per_24h']=90
    candidates=[{'id':'A','allocations':[allocation()]},{'id':'B','allocations':[
        allocation(start='2026-09-21T02:00:00+05:30',end='2026-09-21T03:00:00+05:30')]}]
    constraints=duty_constraints(candidates,[r])
    assert any(c['coefficients']=={'A':3600,'B':3600} and c['capacity']==5400 for c in constraints)
    assert resource_feasible(r,[a for c in candidates for a in c['allocations']],p,HORIZON)[1]=='ROLLING_24H_DUTY_LIMIT'

def test_old_snapshot_without_policy_stays_blocked(client):
    from test_m09 import pipeline
    _,opportunity=pipeline(client)
    response=client.post('/api/v1/coordinated-candidates',headers=auth(),json={'opportunity_id':opportunity.json()['id']})
    assert response.status_code==201
    result=response.json()['result']
    assert result['status']=='BLOCKED' and result['candidates']==[]
    assert 'COORDINATION_POLICY_UNKNOWN' in result['review_blockers']

def test_precedence_and_rest_generate_explicit_candidate_incompatibilities():
    from railsync.coordination_engine import candidate_conflicts
    p=policy()
    r=unit()
    r['profile']['payload']['min_rest_minutes']=30
    requests={id:{'payload':{'predecessors':[]}} for id in ['a','b']}
    def c(id,start,end,track):
        return {'id':id,'request_ids':[id],'track_ids':[track],'possession_start':start,'possession_end':end,
                'tasks':[{'request_id':id,'setup_start':start,'restore_end':end}],
                'allocations':[allocation(start=start,end=end,request_id=id)]}
    a=c('a','2026-09-21T01:00:00+05:30','2026-09-21T02:00:00+05:30','AB')
    b=c('b','2026-09-21T02:15:00+05:30','2026-09-21T03:00:00+05:30','CD')
    conflicts=candidate_conflicts([a,b],[r],p,HORIZON,requests)
    assert conflicts==[{'left':'a','right':'b','reasons':['TRAVEL_OR_REST_SHORTFALL']}]
    requests['a']['payload']['predecessors']=['b']
    assert 'PRECEDENCE_VIOLATION' in candidate_conflicts([a,b],[r],p,HORIZON,requests)[0]['reasons']

def test_resource_pool_capacity_missing_and_slot_limits_fail_closed():
    r=unit()
    r['profile']['payload']['pool_id']='P'
    p=policy()
    p['pools']=[{'id':'P','resource_type':'TRACK_CREW','calendar':[{'start_at':START,
                 'end_at':'2026-09-21T01:30:00+05:30','capacity':1}]}]
    task={'request_id':'r','department':'ENGINEERING','issue_type':'INSPECTION','resource_location':'AB',
          'resource_start':'2026-09-21T01:00:00+05:30','resource_end':'2026-09-21T02:00:00+05:30',
          'requirements':[{'type':'TRACK_CREW','quantity':1}]}
    config=CoordinationInput(opportunity_id='00000000-0000-0000-0000-000000000001').model_dump()
    assignments,reasons,_=allocate([task],[r],p,HORIZON,config)
    assert assignments==[] and 'POOL_CAPACITY_OR_COVERAGE' in reasons
    task['requirements'][0]['quantity']=101
    assert allocate([task],[r],p,HORIZON,config)==([],['RESOURCE_DEMAND_SEARCH_LIMIT'],True)

def test_power_zone_expansion_requires_every_track_and_closed_tracks_excluded(client):
    from railsync.coordination_engine import coordinate
    output,body,_=coordinated_pipeline(client)
    manifest=client.get('/api/v1/snapshots/'+output['snapshot_id'],headers=auth()).json()['manifest']
    opportunity=client.get('/api/v1/maintenance-opportunities/'+body['opportunity_id'],headers=auth()).json()['result']
    availability=client.post('/api/v1/corridor-availability',headers=auth(),json={'snapshot_id':output['snapshot_id'],'track_ids':['AB']}).json()
    availability={'policy':availability['result']['policy'],'result':availability['result']}
    manifest['facts']['network'].append({'id':'Z','kind':'isolation','revision':1,'payload':{'footprint':['AB','CD']}})
    for r in manifest['facts']['requests']:
        r['payload']['power_state']='OFF'
        r['payload']['isolation_zone']='Z'
    result=coordinate(manifest,opportunity,[availability],CoordinationInput(**body).model_dump())
    assert result['candidates']==[]
    assert all(e['code']=='FOOTPRINT_AVAILABILITY_UNKNOWN' for e in result['exclusions'])
    for r in manifest['facts']['requests']:r['payload']['power_state']='ANY'
    next(n for n in manifest['facts']['network'] if n['id']=='AB')['payload']['status']='CLOSED'
    assert all(e['code']=='TRACK_CLOSED' for e in coordinate(manifest,opportunity,[availability],CoordinationInput(**body).model_dump())['exclusions'])

def test_earliest_is_work_time_and_unprotected_forecast_exposure_is_computed():
    from railsync.opportunities import generate
    payload=request_data(earliest_at='2026-09-21T01:35:01+05:30',deadline_kind='RESTORED_BY')
    snapshot=SimpleNamespace(manifest={'horizon_start':START,'facts':{'requests':[
        {'id':'r','revision':1,'payload':payload}], 'freight':[
        {'external_id':'f','track_id':'AB','source_revision':1,'start_at':'2026-09-21T02:00:00+05:30',
         'end_at':'2026-09-21T02:10:00+05:30','expected_count':2}]}})
    availability=SimpleNamespace(policy={'track_ids':['AB']},result={'windows':[
        {'id':'w','start_at':'2026-09-21T01:25:00+05:30','end_at':'2026-09-21T03:00:00+05:30'}]})
    result=generate(snapshot,[availability],[SimpleNamespace(request_id='r',score_basis_points=5000)],
        {'start_grid_minutes':15,'max_candidates_per_request':20})
    first=result['candidates'][0]
    assert first['possession_start']=='2026-09-21T01:26:00+05:30'
    assert first['work_start']=='2026-09-21T01:36:00+05:30'
    assert first['costs']['forecast_exposure']==1200 # 2 expected trains * 600 track-seconds

def test_fractional_horizon_end_is_rounded_inward():
    from railsync.availability import compute_availability
    manifest={'horizon_start':START,'horizon_end':'2026-09-21T00:10:30+05:30','facts':{
        'network':[],'occupancy':[],'freight':[],'coa':[{'id':'c','external_id':'c','source_revision':1,
        'track_id':'AB','start_at':START,'end_at':END}]}}
    result=compute_availability(manifest,{'track_ids':['AB'],'minimum_useful_minutes':1,
        'clearance_before_minutes':0,'clearance_after_minutes':0,'protect_freight_envelope':True})
    assert result['windows'][0]['end_at']=='2026-09-21T00:10:00+05:30'
