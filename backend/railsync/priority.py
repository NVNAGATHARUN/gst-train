import uuid
from typing import Literal
from datetime import datetime
from pydantic import AwareDatetime,Field
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .auth import current_user,require
from .db import session_dependency
from .models import PlanningSnapshot,PriorityAssessment,ModelExperiment
from .requests import StrictModel,audit,digest

router=APIRouter(prefix='/api/v1')
POLICY_VERSION='RULE_PRIORITY_V1'
WEIGHTS={'severity':3000,'urgency':2500,'criticality':2000,'overdue':1500,'impact':1000}

class AssessInput(StrictModel):
    snapshot_id:uuid.UUID
    assessed_at:AwareDatetime

def normalize_ordinal(value):return (value-1)/4
def classify(score):
    if score>=80:return 'CRITICAL'
    if score>=60:return 'HIGH'
    if score>=40:return 'MEDIUM'
    return 'LOW'
def rule_assessment(payload,assessed_at):
    deadline=datetime.fromisoformat(payload['deadline_at'])
    overdue=max(0,min(1,(assessed_at-deadline).total_seconds()/86400/30))
    features={'severity':normalize_ordinal(payload['severity']),'urgency':normalize_ordinal(payload['urgency']),'criticality':normalize_ordinal(payload['criticality']),'overdue':overdue,'impact':normalize_ordinal(payload['impact'])}
    contributions={key:round(features[key]*WEIGHTS[key]) for key in WEIGHTS}
    score_bp=sum(contributions.values());return features,contributions,score_bp

@router.post('/priority-assessments',status_code=201)
def assess(body:AssessInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    snapshot=db.get(PlanningSnapshot,body.snapshot_id)
    if not snapshot:raise HTTPException(422,'UNKNOWN_SNAPSHOT')
    output=[]
    for request in snapshot.manifest['facts']['requests']:
        existing=db.scalar(select(PriorityAssessment).where(PriorityAssessment.snapshot_id==snapshot.id,PriorityAssessment.request_id==uuid.UUID(request['id']),PriorityAssessment.policy_version==POLICY_VERSION,PriorityAssessment.assessed_at==body.assessed_at))
        if existing:
            output.append(serialize(existing));continue
        features,contributions,score=rule_assessment(request['payload'],body.assessed_at)
        row=PriorityAssessment(snapshot_id=snapshot.id,request_id=uuid.UUID(request['id']),policy_version=POLICY_VERSION,method='RULE',score_basis_points=score,priority_band=classify(score/100),features=features,contributions=contributions,assessed_at=body.assessed_at);db.add(row);db.flush();output.append(serialize(row))
    audit(db,user,'PRIORITY_ASSESSED',snapshot.id,{'method':'RULE','policy_version':POLICY_VERSION,'count':len(output)});db.commit()
    return {'snapshot_id':str(snapshot.id),'method':'RULE','policy_version':POLICY_VERSION,'items':output}
def serialize(row):return {'id':str(row.id),'request_id':str(row.request_id),'method':row.method,'policy_version':row.policy_version,'score':row.score_basis_points/100,'priority_band':row.priority_band,'features':row.features,'contributions':{k:v/100 for k,v in row.contributions.items()},'assessed_at':row.assessed_at.isoformat()}

class ExperimentInput(StrictModel):
    algorithm:Literal['RANDOM_FOREST','XGBOOST']
    target_definition:str=Field(min_length=20,max_length=500)
    label_provenance:Literal['SYNTHETIC','RULE_GENERATED','EXPERT_REVIEWED','OBSERVED_OUTCOME']
    dataset_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    metrics:dict
    temporal_holdout:bool
    leakage_audit_passed:bool
    domain_review_accepted:bool=False
    beats_rule_baseline:bool=False
    critical_recall:float|None=Field(default=None,ge=0,le=1)

@router.post('/model-experiments',status_code=201)
def create_experiment(body:ExperimentInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    evaluation={'temporal_holdout':body.temporal_holdout,'leakage_audit_passed':body.leakage_audit_passed,'domain_review_accepted':body.domain_review_accepted,'beats_rule_baseline':body.beats_rule_baseline,'critical_recall':body.critical_recall}
    row=ModelExperiment(algorithm=body.algorithm,target_definition=body.target_definition,label_provenance=body.label_provenance,dataset_hash=body.dataset_hash,metrics=body.metrics,evaluation=evaluation,status='EXPERIMENTAL');db.add(row);db.flush();audit(db,user,'MODEL_EXPERIMENT_REGISTERED',row.id,{'status':'EXPERIMENTAL'});db.commit();return {'id':str(row.id),'status':'EXPERIMENTAL'}

@router.post('/model-experiments/{id}/activate')
def activate(id:uuid.UUID,user=Depends(require('ADMIN')),db=Depends(session_dependency)):
    row=db.scalar(select(ModelExperiment).where(ModelExperiment.id==id).with_for_update())
    if not row:raise HTTPException(404,'EXPERIMENT_NOT_FOUND')
    e=row.evaluation;reasons=[]
    if row.label_provenance not in ['EXPERT_REVIEWED','OBSERVED_OUTCOME']:reasons.append('LABEL_PROVENANCE_NOT_DEFENSIBLE')
    if not e['temporal_holdout']:reasons.append('TEMPORAL_HOLDOUT_REQUIRED')
    if not e['leakage_audit_passed']:reasons.append('LEAKAGE_AUDIT_REQUIRED')
    if not e['beats_rule_baseline']:reasons.append('RULE_BASELINE_NOT_BEATEN')
    if not e['domain_review_accepted']:reasons.append('DOMAIN_REVIEW_REQUIRED')
    if e['critical_recall'] is None:reasons.append('CRITICAL_RECALL_MISSING')
    elif e['critical_recall']<0.80:reasons.append('CRITICAL_RECALL_BELOW_0_80')
    if reasons:raise HTTPException(422,{'code':'MODEL_PROMOTION_BLOCKED','reasons':reasons})
    row.status='ACTIVE';audit(db,user,'MODEL_ACTIVATED',row.id,{'evaluation':e});db.commit();return {'id':str(row.id),'status':'ACTIVE'}
