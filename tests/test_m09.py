from conftest import auth
from test_m06 import prepare_baseline

def pipeline(client,max_candidates=200):
    h=auth();run_id=prepare_baseline(client);snapshot_id=client.get('/api/v1/planning-runs/'+run_id,headers=h).json()['snapshot_id']
    assessed_at='2026-09-21T00:00:00+05:30'
    assert client.post('/api/v1/priority-assessments',json={'snapshot_id':snapshot_id,'assessed_at':assessed_at},headers=h).status_code==201
    availability=client.post('/api/v1/corridor-availability',json={'snapshot_id':snapshot_id,'track_ids':['AB'],'minimum_useful_minutes':1},headers=h).json()
    body={'snapshot_id':snapshot_id,'availability_ids':[availability['id']],'assessed_at':assessed_at,'start_grid_minutes':15,'max_candidates_per_request':max_candidates}
    return body,client.post('/api/v1/maintenance-opportunities',json=body,headers=h)

def test_timed_candidates_preserve_setup_work_restore_and_costs(client):
    body,response=pipeline(client);assert response.status_code==201
    result=response.json()['result'];assert result['counts']=={'candidates':2,'excluded_requests':0}
    first,last=result['candidates'];assert first['possession_start']=='2026-09-21T01:25:00+05:30'
    assert first['work_start']=='2026-09-21T01:35:00+05:30' and first['work_end']=='2026-09-21T02:35:00+05:30' and first['possession_end']=='2026-09-21T02:45:00+05:30'
    assert first['costs']=={'reserved_track_minutes':80,'forecast_exposure':0,'setup_minutes':10,'restoration_minutes':10}
    assert last['possession_start']=='2026-09-21T01:40:00+05:30' and last['possession_end']=='2026-09-21T03:00:00+05:30'
    assert response.json()['result']['search']['optimality_scope']=='generated_candidate_set'
    assert client.post('/api/v1/maintenance-opportunities',json=body,headers=auth()).json()['duplicate'] is True

def test_search_cap_is_explicit_not_silent(client):
    _,response=pipeline(client,max_candidates=1);result=response.json()['result']
    assert result['counts']['candidates']==1 and result['search']['before_cap']==2
    assert result['exclusions']==[{'request_id':result['candidates'][0]['request_id'],'code':'SEARCH_LIMIT_REACHED','generated':2,'retained':1}]
