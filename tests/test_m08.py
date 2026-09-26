from conftest import auth
from test_m06 import prepare_baseline
from railsync.availability import compute_availability

def test_persisted_conservative_availability_and_exact_boundaries(client):
    run_id=prepare_baseline(client);h=auth()
    snapshot_id=client.get('/api/v1/planning-runs/'+run_id,headers=h).json()['snapshot_id']
    body={'snapshot_id':snapshot_id,'track_ids':['AB'],'clearance_before_minutes':5,'clearance_after_minutes':5,'minimum_useful_minutes':80,'protect_freight_envelope':True}
    first=client.post('/api/v1/corridor-availability',json=body,headers=h);assert first.status_code==201
    result=first.json()['result'];assert result['counts']['windows']==1
    window=result['windows'][0]
    assert window['start_at']=='2026-09-21T01:25:00+05:30' and window['end_at']=='2026-09-21T03:00:00+05:30' and window['usable_minutes']==95
    assert result['rounding']=={'allowed':'inward','blocked':'outward','intervals':'half-open'}
    assert result['source_conflicts'][0]['code']=='COA_OCCUPANCY_CONFLICT'
    assert client.post('/api/v1/corridor-availability',json=body,headers=h).json()['duplicate'] is True

def test_multi_track_intersection_rounding_restrictions_and_minimum():
    manifest={'horizon_start':'2026-09-21T00:00:00+05:30','horizon_end':'2026-09-21T04:00:00+05:30','facts':{
      'coa':[{'id':'ca','external_id':'CA','source_revision':1,'track_id':'A','start_at':'2026-09-21T00:00:10+05:30','end_at':'2026-09-21T04:00:50+05:30'},{'id':'cb','external_id':'CB','source_revision':1,'track_id':'B','start_at':'2026-09-21T00:00:00+05:30','end_at':'2026-09-21T04:00:00+05:30'}],
      'occupancy':[{'id':'oa','track_id':'A','enter_at':'2026-09-21T00:50:20+05:30','exit_at':'2026-09-21T01:10:20+05:30'},{'id':'ob','track_id':'B','enter_at':'2026-09-21T00:40:00+05:30','exit_at':'2026-09-21T00:50:00+05:30'}],
      'freight':[{'id':'fa','external_id':'FA','source_revision':1,'track_id':'A','start_at':'2026-09-21T02:00:20+05:30','end_at':'2026-09-21T02:10:20+05:30'}],
      'network':[{'id':'R','kind':'restriction','payload':{'footprint':['B'],'start':'2026-09-21T01:30:20+05:30','end':'2026-09-21T01:40:20+05:30'}}]}}
    policy={'snapshot_id':'00000000-0000-0000-0000-000000000000','track_ids':['A','B'],'clearance_before_minutes':5,'clearance_after_minutes':5,'minimum_useful_minutes':20,'protect_freight_envelope':True}
    result=compute_availability(manifest,policy)
    assert [(w['start_at'],w['end_at']) for w in result['windows']]==[('2026-09-21T00:01:00+05:30','2026-09-21T00:35:00+05:30'),('2026-09-21T02:11:00+05:30','2026-09-21T04:00:00+05:30')]
    assert any(x['code']=='BELOW_SHARED_MINIMUM_USEFUL_DURATION' for x in result['excluded'])
