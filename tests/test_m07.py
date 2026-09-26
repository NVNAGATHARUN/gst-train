from conftest import auth
from test_m05 import prepare_snapshot_facts

def test_rule_priority_exact_contributions_and_idempotency(client):
    prepare_snapshot_facts(client);h=auth()
    snapshot=client.post('/api/v1/snapshots',json={'horizon_start':'2026-09-21T00:00:00+05:30','horizon_end':'2026-09-22T00:00:00+05:30','track_ids':['AB']},headers=h).json()
    body={'snapshot_id':snapshot['id'],'assessed_at':'2026-10-07T06:00:00+05:30'}
    first=client.post('/api/v1/priority-assessments',json=body,headers=h).json();second=client.post('/api/v1/priority-assessments',json=body,headers=h).json()
    item=first['items'][0]
    assert first['method']=='RULE' and first['policy_version']=='RULE_PRIORITY_V1'
    assert item['score']==56.25 and item['priority_band']=='MEDIUM'
    assert item['contributions']=={'severity':15.0,'urgency':18.75,'criticality':10.0,'overdue':7.5,'impact':5.0}
    assert second['items'][0]['id']==item['id']

def test_ml_experiment_stays_gated_without_defensible_evidence(client):
    body={'algorithm':'XGBOOST','target_definition':'Verified adverse asset event within seven days if unresolved','label_provenance':'SYNTHETIC','dataset_hash':'a'*64,'metrics':{'pr_auc':0.8},'temporal_holdout':True,'leakage_audit_passed':True,'domain_review_accepted':False,'beats_rule_baseline':True,'critical_recall':0.95}
    created=client.post('/api/v1/model-experiments',json=body,headers=auth()).json();assert created['status']=='EXPERIMENTAL'
    response=client.post('/api/v1/model-experiments/'+created['id']+'/activate',headers=auth('ADMIN'))
    assert response.status_code==422
    assert set(response.json()['detail']['reasons'])=={'LABEL_PROVENANCE_NOT_DEFENSIBLE','DOMAIN_REVIEW_REQUIRED'}

def test_ml_promotion_requires_predeclared_recall_threshold(client):
    body={'algorithm':'RANDOM_FOREST','target_definition':'Expert reviewed maintenance urgency classification for fixed assets','label_provenance':'EXPERT_REVIEWED','dataset_hash':'b'*64,'metrics':{'pr_auc':0.7},'temporal_holdout':True,'leakage_audit_passed':True,'domain_review_accepted':True,'beats_rule_baseline':True,'critical_recall':0.79}
    created=client.post('/api/v1/model-experiments',json=body,headers=auth()).json()
    result=client.post('/api/v1/model-experiments/'+created['id']+'/activate',headers=auth('ADMIN'))
    assert result.status_code==422 and result.json()['detail']['reasons']==['CRITICAL_RECALL_BELOW_0_80']
