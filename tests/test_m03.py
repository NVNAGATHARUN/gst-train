from conftest import auth
from test_m02 import request_data

def test_graph_references_and_department_location(client):
    h=auth();post=lambda kind,id,data:client.post('/api/v1/network/'+kind,json={'id':id,'data':data},headers=h)
    assert post('track','BAD',{'section_id':'missing'}).status_code==422
    assert post('track','AB-DOWN',{'section_id':'SEC-AB','direction':'DOWN','electrified':True}).status_code==201
    assert post('isolation','ZONE-1',{'footprint':['AB','AB-DOWN']}).status_code==201
    assert client.post('/api/v1/maintenance-requests',json=request_data(asset_id='missing'),headers=auth('ENGINEERING')).status_code==422
    assert client.post('/api/v1/maintenance-requests',json=request_data(department='TRD'),headers=auth('TRD')).status_code==422
    assert client.post('/api/v1/maintenance-requests',json=request_data(power_block_required=True,isolation_zone='missing'),headers=auth('ENGINEERING')).status_code==422
    r=client.post('/api/v1/maintenance-requests',json=request_data(power_block_required=True,isolation_zone='ZONE-1'),headers=auth('ENGINEERING'))
    assert r.status_code==201
    tracks=client.get('/api/v1/network?kind=track',headers=h).json()['items'];assert len(tracks)==2

def test_network_revision_and_restriction_validation(client):
    h=auth();body={'id':'AB','expected_revision':1,'data':{'section_id':'SEC-AB','status':'CLOSED'}}
    assert client.post('/api/v1/network/track',json=body,headers=h).json()['revision']==2
    assert client.post('/api/v1/network/track',json=body,headers=h).status_code==409
    assert client.post('/api/v1/network/restriction',json={'id':'X','data':{'footprint':['AB'],'start':'2026-09-21T03:00:00Z','end':'2026-09-21T02:00:00Z','type':'CLOSURE','rule_id':'synthetic-v1'}},headers=h).status_code==422
