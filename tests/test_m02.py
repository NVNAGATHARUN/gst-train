from conftest import auth

def request_data(**changes):
    return {'department':'ENGINEERING','asset_id':'AS-1','footprint':['AB'],'issue_type':'INSPECTION','severity':3,'urgency':4,'work_minutes':60,'setup_minutes':10,'restore_minutes':10,'earliest_at':'2026-09-21T00:00:00+05:30','deadline_at':'2026-09-22T06:00:00+05:30','requirements':[{'type':'TRACK_CREW','quantity':1}],**changes}

def test_request_validation_ownership_revision_and_lifecycle(client):
    h=auth('ENGINEERING');r=client.post('/api/v1/maintenance-requests',json=request_data(),headers=h)
    assert r.status_code==201;r=r.json();id=r['id']
    assert client.post('/api/v1/maintenance-requests',json=request_data(work_minutes=0),headers=h).status_code==422
    assert client.post('/api/v1/maintenance-requests',json=request_data(earliest_at='2026-09-21T00:00:00'),headers=h).status_code==422
    assert client.get('/api/v1/maintenance-requests/'+id,headers=auth('TRD')).status_code==403
    for action,status in [('VALIDATE','VALIDATED'),('SUBMIT','PENDING_PLANNING')]:
        t=client.post(f'/api/v1/maintenance-requests/{id}/transitions',json={'action':action,'expected_revision':1,'reason':'verified fixture'},headers=h);assert t.json()['status']==status
    b={'expected_revision':1,'data':request_data(work_minutes=61)}
    assert client.patch('/api/v1/maintenance-requests/'+id,json=b,headers=h).json()['revision']==2
    assert client.patch('/api/v1/maintenance-requests/'+id,json=b,headers=h).status_code==409
    assert client.get('/api/v1/maintenance-requests',headers=h).json()['items'][0]['data']['work_minutes']==61

def test_import_quarantine_idempotency_and_source_conflict(client):
    h=auth('ENGINEERING');row={**request_data(),'external_id':'TMS-1','source_revision':1}
    def preview(rows):return client.post('/api/v1/imports/preview',json={'source':'TMS','rows':rows},headers=h).json()
    def commit(p):return client.post('/api/v1/imports/'+p['id']+'/commit',json={'expected_hash':p['hash']},headers=h)
    p=preview([row,{**row,'external_id':'bad','work_minutes':-1}]);assert len(p['errors'])==1
    result=commit(p);assert result.json()['applied']==1;assert result.json()['quarantined']==1
    assert commit(p).json()==result.json()
    assert commit(preview([row])).json()['duplicates']==1
    assert len(client.get('/api/v1/maintenance-requests',headers=h).json()['items'])==1
    assert commit(preview([{**row,'work_minutes':90}])).status_code==409
    updated=commit(preview([{**row,'source_revision':2,'work_minutes':90}])).json()
    assert updated['applied']==1
    assert len(client.get('/api/v1/maintenance-requests',headers=h).json()['items'])==1

def test_import_history_and_source_revision_lineage_are_role_scoped(client):
    h=auth('ENGINEERING');row={**request_data(),'external_id':'TMS-LINEAGE-1','source_revision':1}
    preview=client.post('/api/v1/imports/preview',json={'source':'TMS','rows':[row]},headers=h).json()
    committed=client.post('/api/v1/imports/'+preview['id']+'/commit',json={'expected_hash':preview['hash']},headers=h)
    assert committed.status_code==200

    own=client.get('/api/v1/imports',headers=h).json()['items']
    assert own==[{'id':preview['id'],'source':'TMS','hash':preview['hash'],'state':'COMMITTED',
        'valid_count':1,'error_count':0,'result':committed.json()}]
    lineage=client.get('/api/v1/source-records?source=TMS',headers=h).json()['items']
    assert len(lineage)==1
    assert lineage[0]['external_id']=='TMS-LINEAGE-1'
    assert lineage[0]['source_revision']==1
    assert lineage[0]['department']=='ENGINEERING'
    assert lineage[0]['request_id']==committed.json()['request_ids'][0]
    assert len(lineage[0]['payload_hash'])==64

    assert client.get('/api/v1/imports',headers=auth('TRD')).json()['items']==[]
    assert client.get('/api/v1/source-records',headers=auth('TRD')).json()['items']==[]
    assert client.get('/api/v1/imports',headers=auth('AUDITOR')).json()['items']==own
    assert client.get('/api/v1/source-records',headers=auth('PLANNER')).json()['items']==lineage
