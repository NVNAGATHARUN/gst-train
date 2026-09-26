from conftest import auth
from test_m02 import request_data
from railsync.planning import run_one

def prepare_baseline(client,work_minutes=60,mandatory=False):
    h=auth();department=auth('ENGINEERING')
    resource={'id':'CREW-1','resource_type':'TRACK_CREW','department':'ENGINEERING','available_start':'2026-09-21T00:00:00+05:30','available_end':'2026-09-22T00:00:00+05:30','source_mode':'SIMULATED'}
    assert client.post('/api/v1/resources',json=resource,headers=h).status_code==201
    request=client.post('/api/v1/maintenance-requests',json=request_data(work_minutes=work_minutes,mandatory=mandatory),headers=department).json()
    for action in ['VALIDATE','SUBMIT']:assert client.post(f"/api/v1/maintenance-requests/{request['id']}/transitions",json={'action':action,'expected_revision':1,'reason':'baseline fixture'},headers=department).status_code==200
    train={'train_id':'P-BASE','train_name':'Baseline Passenger','train_type':'PASSENGER','service_date':'2026-09-21','source_mode':'SIMULATED','source_revision':1,'occupancies':[{'track_id':'AB','route_sequence':1,'enter_at':'2026-09-21T01:00:00+05:30','exit_at':'2026-09-21T01:20:00+05:30'}]}
    assert client.post('/api/v1/operations/train-runs',json=train,headers=h).status_code==201
    coa={'external_id':'COA-BASE','source_revision':1,'track_id':'AB','start_at':'2026-09-21T00:00:00+05:30','end_at':'2026-09-21T04:00:00+05:30','source_mode':'SIMULATED'}
    assert client.post('/api/v1/operations/coa-windows',json=coa,headers=h).status_code==201
    freight={**coa,'external_id':'FF-BASE','start_at':'2026-09-21T03:00:00+05:30','end_at':'2026-09-21T03:30:00+05:30','issued_at':'2026-09-20T12:00:00+05:30','expected_count':1,'confidence':0.6,'uncertainty_semantics':'protected synthetic envelope'}
    assert client.post('/api/v1/operations/freight-forecasts',json=freight,headers=h).status_code==201
    snapshot=client.post('/api/v1/snapshots',json={'horizon_start':'2026-09-21T00:00:00+05:30','horizon_end':'2026-09-21T04:00:00+05:30','track_ids':['AB']},headers=h).json()
    queued=client.post('/api/v1/planning-runs',json={'snapshot_id':snapshot['id'],'planner_type':'BASELINE','clearance_minutes':5},headers=h).json()
    return queued['id']

def test_first_feasible_exact_output_and_persistence(client):
    run_id=prepare_baseline(client);assert run_one() is not None
    output=client.get('/api/v1/planning-runs/'+run_id,headers=auth()).json()
    assert output['status']=='COMPLETED' and output['result']['counts']=={'scheduled':1,'deferred':0}
    assignment=output['result']['assignments'][0]
    assert assignment['possession_start']=='2026-09-21T01:25:00+05:30'
    assert assignment['possession_end']=='2026-09-21T02:45:00+05:30'
    assert assignment['resource_ids']==['CREW-1']
    assert output['result']['policy']=={'fixed_trains':True,'freight_envelope_protected':True,'clearance_minutes':5,'bundling':False}

def test_mandatory_unscheduled_is_non_approvable(client):
    run_id=prepare_baseline(client,work_minutes=240,mandatory=True);run_one()
    result=client.get('/api/v1/planning-runs/'+run_id,headers=auth()).json()['result']
    assert result['schedule_status']=='NON_APPROVABLE'
    assert result['assignments']==[] and result['deferred'][0]['reason']=='NO_FEASIBLE_WINDOW_OR_RESOURCE'
