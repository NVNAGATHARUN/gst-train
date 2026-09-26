"""Real OR-Tools calls, with exhaustive small-instance reference solutions."""
import copy
import itertools
import json
import os
import random
import uuid
from pathlib import Path
from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from conftest import auth
from test_m10 import coordinated_pipeline,START,END
from railsync.solver import solve,first_feasible,SolverOptions
from railsync.planning import run_one,claim_run,publish_run
from railsync.db import Session
from railsync.models import PlanningRun,WorkerLease

def fixture(count=3):
    requests=[{'id':str(i),'revision':1,'payload':{'mandatory':False,'predecessors':[],
                'deadline_at':END}} for i in range(count)]
    candidates=[{'id':'c'+str(i),'request_ids':[str(i)],'tasks':[{'request_id':str(i),
        'setup_start':'2026-09-21T01:00:00+05:30','restore_end':'2026-09-21T02:00:00+05:30'}],
        'possession_start':'2026-09-21T01:00:00+05:30','costs':{'reserved_track_minutes':60,
        'forecast_exposure_train_track_seconds':0,'incremental_travel_minutes_against_fixed_duties':0}} for i in range(count)]
    manifest={'horizon_start':START,'horizon_end':END,'facts':{'requests':requests,'commitments':[]}}
    coordination={'candidates':candidates,'incompatibilities':[],'aggregate_constraints':[],
        'exclusions':[],'search':{'fixture':'SIMULATED','optimality_scope':'generated_candidate_set'},
        'review_blockers':['INDEPENDENT_VALIDATION_NOT_YET_PERFORMED']}
    priorities={str(i):(i+1)*1000 for i in range(count)}
    return manifest,coordination,priorities

def test_cp_sat_selects_real_bundle_and_same_input_baseline(client):
    coordination,_,_=coordinated_pipeline(client)
    body={'snapshot_id':coordination['snapshot_id'],'coordination_id':coordination['id']}
    ids={}
    for planner in ['CP_SAT','BASELINE']:
        response=client.post('/api/v1/planning-runs',json={**body,'planner_type':planner},headers=auth())
        assert response.status_code==202,response.text
        ids[planner]=response.json()['id']
    # The fixture also queued an earlier legacy baseline; durable processing handles it.
    for _ in range(3):assert run_one() is not None
    cp=client.get('/api/v1/planning-runs/'+ids['CP_SAT'],headers=auth()).json()
    base=client.get('/api/v1/planning-runs/'+ids['BASELINE'],headers=auth()).json()
    assert cp['status']=='COMPLETED',cp
    result=cp['result']
    assert result['solver_status']=='OPTIMAL'
    assert result['counts']['scheduled']==2 and len(result['assignments'])==1
    assert result['objective_value']==80 and result['best_bound']==80 and result['relative_gap']==0
    assert result['objective_terms']['deferred_utility']['raw']==0
    assert result['ortools_version'] and result['wall_time_seconds']>=0
    assert result['diagnostics']['model_validation']==''
    assert result['snapshot_hash']==base['result']['snapshot_hash']
    assert result['coordination_hash']==base['result']['coordination_hash']
    assert result['requirements_hash']==base['result']['requirements_hash']
    assert result['objective_value']<=base['result']['objective_value']
    assert base['result']['solver_status'] is None and base['result']['comparison_eligible']
    if path:=os.environ.get('RAILSYNC_M11_EVIDENCE_OUTPUT'):
        Path(path).write_text(json.dumps({'fixture':'SIMULATED; real CP-SAT and same-input baseline',
            'cp_sat':cp,'baseline':base},indent=2),encoding='utf-8')

def test_mandatory_without_candidate_and_frozen_missing_are_real_infeasible():
    manifest,coord,priorities=fixture(1)
    manifest['facts']['requests'][0]['payload']['mandatory']=True
    coord['candidates']=[]
    result=solve(manifest,coord,priorities,{})
    assert result['solver_status']=='INFEASIBLE' and result['assignments']==[]
    assert result['objective_value'] is None and result['objective_terms'] is None
    assert result['diagnostics']['mandatory_without_candidates']==['0']
    manifest,coord,priorities=fixture(1)
    manifest['facts']['commitments']=[{'id':'f','candidate_id':'missing','frozen':True}]
    result=solve(manifest,coord,priorities,{})
    assert result['solver_status']=='INFEASIBLE'
    assert result['diagnostics']['missing_frozen_candidates']==['f']

def test_pool_capacity_prevents_three_individually_feasible_candidates():
    manifest,coord,priorities=fixture()
    coord['aggregate_constraints']=[{'kind':'POOL_CAPACITY','capacity':2,'coefficients':{'c0':1,'c1':1,'c2':1}}]
    result=solve(manifest,coord,priorities,{})
    assert result['solver_status']=='OPTIMAL' and result['selected_candidate_ids']==['c1','c2']
    assert result['objective_value']==100120 # deferred utility 1000*100 + 2*60 track-minutes

def test_duplicate_coverage_conflicts_and_deadline_mandatory_are_hard():
    manifest,coord,priorities=fixture(2)
    duplicate=copy.deepcopy(coord['candidates'][0])
    duplicate['id']='alternative'
    duplicate['costs']['reserved_track_minutes']=1
    coord['candidates'].append(duplicate)
    result=solve(manifest,coord,priorities,{})
    assert 'alternative' in result['selected_candidate_ids'] and 'c0' not in result['selected_candidate_ids']
    coord['incompatibilities']=[{'left':'alternative','right':'c1'},{'left':'c0','right':'c1'}]
    for r in manifest['facts']['requests']:r['payload']['mandatory']=True
    assert solve(manifest,coord,priorities,{'weights':{'deferred_utility':0,'possession':0}})['solver_status']=='INFEASIBLE'

def test_precedence_internal_and_external_and_frozen_selection():
    manifest,coord,priorities=fixture(2)
    manifest['facts']['requests'][1]['payload']['predecessors']=['0']
    result=solve(manifest,coord,priorities,{})
    assert result['selected_candidate_ids']==['c0'] # same-time predecessor/successor cannot both run
    coord['candidates'][1]['tasks'][0]['setup_start']='2026-09-21T02:00:00+05:30'
    coord['candidates'][1]['possession_start']='2026-09-21T02:00:00+05:30'
    manifest['facts']['commitments']=[{'id':'f','candidate_id':'c1','frozen':True}]
    assert solve(manifest,coord,priorities,{})['selected_candidate_ids']==['c0','c1']
    assert first_feasible(manifest,coord,priorities,{})['counts']['scheduled']==2
    # A candidate containing both tasks with reversed order is disabled, not exempted.
    coord['candidates'][0]['request_ids']=['0','1']
    coord['candidates'][0]['tasks'].append({'request_id':'1','setup_start':START,'restore_end':END})
    manifest['facts']['commitments']=[]
    assert 'c0' not in solve(manifest,coord,priorities,{})['selected_candidate_ids']

def test_zero_solver_budget_returns_unknown_without_fallback():
    manifest,coord,priorities=fixture(30)
    priorities={id:1000 for id in priorities}
    result=solve(manifest,coord,priorities,{'max_time_seconds':0})
    assert result['solver_status']=='UNKNOWN' and result['assignments']==[]
    assert not result['has_incumbent'] and result['objective_terms'] is None
    assert len(result['unresolved_request_ids'])==30 and result['deferred']==[]

def test_empty_optional_solution_and_weight_sensitivity_are_explicit():
    manifest,coord,priorities=fixture(1)
    low=solve(manifest,coord,priorities,{'weights':{'deferred_utility':0}})
    assert low['solver_status']=='OPTIMAL' and low['selection_state']=='EMPTY_OPTIONAL_SOLUTION'
    assert low['objective_value']==0 and low['counts']['deferred']==1
    high=solve(manifest,coord,priorities,{'weights':{'deferred_utility':100}})
    assert high['selected_candidate_ids']==['c0']
    manifest['facts']['commitments']=[{'id':'accepted','candidate_id':'c0','frozen':False}]
    commitment=solve(manifest,coord,priorities,{'weights':{'deferred_utility':0,'commitment_change':100}})
    assert commitment['selected_candidate_ids']==['c0'] and commitment['objective_terms']['commitment_change']['raw']==0

def test_solver_matches_exhaustive_reference_on_seeded_small_instances():
    rng=random.Random(26027)
    for _ in range(12):
        manifest,coord,priorities=fixture(5)
        ids=[c['id'] for c in coord['candidates']]
        edges=[(a,b) for a,b in itertools.combinations(ids,2) if rng.random()<.3]
        coord['incompatibilities']=[{'left':a,'right':b} for a,b in edges]
        capacity=rng.randint(1,5)
        coord['aggregate_constraints']=[{'kind':'POOL_CAPACITY','capacity':capacity,'coefficients':{id:1 for id in ids}}]
        required={str(i) for i in range(5) if rng.random()<.2}
        for r in manifest['facts']['requests']:r['payload']['mandatory']=r['id'] in required
        values=[]
        for bits in itertools.product([0,1],repeat=5):
            chosen={ids[i] for i,b in enumerate(bits) if b}
            if len(chosen)>capacity or any(a in chosen and b in chosen for a,b in edges):continue
            if not {'c'+id for id in required}.issubset(chosen):continue
            # Independent arithmetic: simple per-request penalty plus actual selected cost.
            values.append(sum(priorities[str(i)]*100 for i,b in enumerate(bits) if not b)+60*len(chosen))
        result=solve(manifest,coord,priorities,{})
        if not values:assert result['solver_status']=='INFEASIBLE'
        else:
            assert result['solver_status']=='OPTIMAL'
            assert result['objective_value']==min(values)

def test_worker_expired_lease_recovery_and_stale_publication_fencing(client):
    from test_m06 import prepare_baseline
    id=uuid.UUID(prepare_baseline(client))
    first=claim_run()
    assert first[0]==id and claim_run() is None
    with Session.begin() as db:
        db.get(WorkerLease,id).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    second=claim_run()
    assert second[0]==id and second[1]!=first[1]
    assert not publish_run(id,first[1],{'schedule_status':'SHOULD_NOT_PUBLISH'})
    # Publish only a failure diagnostic here: never fabricate a computed plan in a test.
    assert publish_run(id,second[1],{'schedule_status':'ERROR','error':'SYNTHETIC_WORKER_INTERRUPTION'},error=True)
    output=client.get('/api/v1/planning-runs/'+str(id),headers=auth()).json()
    assert output['status']=='FAILED' and output['result']['error']=='SYNTHETIC_WORKER_INTERRUPTION'

def test_queue_rejects_mismatched_facts_and_unsafe_parameters(client):
    coordination,_,_=coordinated_pipeline(client)
    body={'snapshot_id':coordination['snapshot_id'],'coordination_id':coordination['id'],'planner_type':'CP_SAT'}
    assert client.post('/api/v1/planning-runs',headers=auth(),json={**body,'clearance_minutes':0}).status_code==422
    assert client.post('/api/v1/planning-runs',headers=auth(),json={**body,'solver_options':{'weights':{'possession':-1}}}).status_code==422
    assert client.post('/api/v1/planning-runs',headers=auth(),json={**body,'coordination_id':str(uuid.uuid4())}).status_code==422
