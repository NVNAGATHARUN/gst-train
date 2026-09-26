from conftest import auth
from test_m02 import request_data

def prepare_snapshot_facts(client):
    h=auth();department=auth('ENGINEERING')
    request=client.post('/api/v1/maintenance-requests',json=request_data(),headers=department).json()
    for action in ['VALIDATE','SUBMIT']:
        assert client.post(f"/api/v1/maintenance-requests/{request['id']}/transitions",json={'action':action,'expected_revision':1,'reason':'snapshot fixture'},headers=department).status_code==200
    run={'train_id':'P-01','train_name':'Fixture Passenger','train_type':'PASSENGER','service_date':'2026-09-21','source_mode':'SIMULATED','source_revision':1,'occupancies':[{'track_id':'AB','route_sequence':1,'enter_at':'2026-09-21T01:00:00+05:30','exit_at':'2026-09-21T01:20:00+05:30'}]}
    assert client.post('/api/v1/operations/train-runs',json=run,headers=h).status_code==201
    window={'external_id':'COA-SNAPSHOT','source_revision':1,'track_id':'AB','start_at':'2026-09-21T00:00:00+05:30','end_at':'2026-09-22T00:00:00+05:30','source_mode':'SIMULATED'}
    assert client.post('/api/v1/operations/coa-windows',json=window,headers=h).status_code==201
    forecast={**window,'external_id':'FF-SNAPSHOT','issued_at':'2026-09-20T12:00:00+05:30','expected_count':1,'confidence':0.6,'uncertainty_semantics':'synthetic scenario confidence'}
    assert client.post('/api/v1/operations/freight-forecasts',json=forecast,headers=h).status_code==201
    return request

def test_snapshot_hash_deduplication_and_immutability(client):
    request=prepare_snapshot_facts(client);h=auth()
    body={'horizon_start':'2026-09-21T00:00:00+05:30','horizon_end':'2026-09-22T00:00:00+05:30','track_ids':['AB']}
    first=client.post('/api/v1/snapshots',json=body,headers=h).json();assert first['counts']['requests']==1
    second=client.post('/api/v1/snapshots',json=body,headers=h).json();assert second['duplicate'] is True and second['content_hash']==first['content_hash']
    revised=request_data(work_minutes=99)
    assert client.patch('/api/v1/maintenance-requests/'+request['id'],json={'expected_revision':1,'data':revised},headers=auth('ENGINEERING')).status_code==200
    frozen=client.get('/api/v1/snapshots/'+first['id'],headers=h).json()
    assert frozen['content_hash']==first['content_hash']
    assert frozen['manifest']['facts']['requests'][0]['payload']['work_minutes']==60

def test_snapshot_fails_closed_on_missing_critical_coverage(client):
    h=auth();body={'horizon_start':'2026-09-21T00:00:00+05:30','horizon_end':'2026-09-22T00:00:00+05:30','track_ids':['AB']}
    response=client.post('/api/v1/snapshots',json=body,headers=h)
    assert response.status_code==422
    assert {g['source'] for g in response.json()['detail']['gaps']}=={'OCCUPANCY','COA','FREIGHT_FORECAST'}
