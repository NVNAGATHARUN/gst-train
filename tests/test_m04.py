from conftest import auth

def setup_second_section(client):
    h=auth()
    for kind,id,data in [('station','C',{'name':'C'}),('section','SEC-BC',{'from_station':'B','to_station':'C','distance_km':11}),('track','BC',{'section_id':'SEC-BC','direction':'BOTH','electrified':True})]:
        assert client.post('/api/v1/network/'+kind,json={'id':id,'data':data},headers=h).status_code==201

def test_dated_overnight_route_and_ordered_occupancy(client):
    setup_second_section(client);h=auth()
    body={'train_id':'F-01','train_name':'Fixture Freight','train_type':'FREIGHT','service_date':'2026-09-21','source_mode':'SIMULATED','source_revision':1,'occupancies':[
        {'track_id':'AB','route_sequence':1,'enter_at':'2026-09-21T23:50:00+05:30','exit_at':'2026-09-22T00:10:00+05:30'},
        {'track_id':'BC','route_sequence':2,'enter_at':'2026-09-22T00:15:00+05:30','exit_at':'2026-09-22T00:35:00+05:30'}]}
    r=client.post('/api/v1/operations/train-runs',json=body,headers=h);assert r.status_code==201 and r.json()['occupancy_count']==2
    assert client.post('/api/v1/operations/train-runs',json=body,headers=h).json()['duplicate'] is True
    items=client.get('/api/v1/operations/occupancy?start=2026-09-21T18:00:00Z&end=2026-09-22T20:00:00Z',headers=h).json()['items']
    assert [i['track_id'] for i in items]==['AB','BC'];assert all(i['source_mode']=='SIMULATED' for i in items)
    broken={**body,'train_id':'X','occupancies':[body['occupancies'][0],{**body['occupancies'][1],'route_sequence':3}]}
    assert client.post('/api/v1/operations/train-runs',json=broken,headers=h).status_code==422

def test_coa_freight_uncertainty_and_unknown_coverage(client):
    h=auth();base={'external_id':'COA-1','source_revision':1,'track_id':'AB','start_at':'2026-09-21T01:00:00+05:30','end_at':'2026-09-21T04:00:00+05:30','source_mode':'SIMULATED'}
    assert client.post('/api/v1/operations/coa-windows',json=base,headers=h).status_code==201
    assert client.post('/api/v1/operations/coa-windows',json=base,headers=h).json()['duplicate'] is True
    freight={**base,'external_id':'FF-1','issued_at':'2026-09-20T12:00:00+05:30','expected_count':2,'confidence':0.72,'uncertainty_semantics':'synthetic scenario confidence'}
    assert client.post('/api/v1/operations/freight-forecasts',json=freight,headers=h).status_code==201
    assert client.post('/api/v1/operations/freight-forecasts',json={**freight,'confidence':1.2},headers=h).status_code==422
    result=client.get('/api/v1/operations/coverage?start=2026-09-20T19:30:00Z&end=2026-09-20T22:30:00Z&track_id=AB',headers=h).json()
    assert result['complete'] is False and result['gaps']==[{'track_id':'AB','source':'OCCUPANCY','status':'UNKNOWN'}]
