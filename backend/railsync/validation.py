"""Append-only validation reports. Controller decisions are a later milestone."""
import uuid
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,model_validator
from sqlalchemy import select
from .auth import current_user,require
from .db import Session,engine,session_dependency
from .models import PlanningRun,PlanningSnapshot,ValidationReport,CoordinationRevision,PlanRevision,WhatIfScenario
from .requests import StrictModel,audit
from .snapshots import SnapshotInput,facts
from .validator import validate,content_hash,instant,VERSION
from .staleness import invalidation_ids
from .freeze_state import execution_pending

router=APIRouter(prefix='/api/v1')

def utc_now():return datetime.now(timezone.utc)

class ValidationInput(StrictModel):
    run_id:uuid.UUID|None=None
    plan_revision_id:uuid.UUID|None=None
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    @model_validator(mode='after')
    def one_target(self):
        if (self.run_id is None)==(self.plan_revision_id is None):raise ValueError('provide exactly one validation target')
        return self

def current_hash(db,snapshot):
    m=snapshot.manifest
    if snapshot.scenario_id:
        row=db.scalar(select(WhatIfScenario).where(WhatIfScenario.snapshot_id==snapshot.id))
        if not row or str(row.id)!=snapshot.scenario_id or content_hash(row.payload)!=row.content_hash:
            return None
        source=db.get(PlanningSnapshot,row.source_snapshot_id)
        scenario=m.get('scenario') or {}
        if (not source or source.scenario_id or source.content_hash!=row.payload['source_snapshot_hash']
                or content_hash(source.manifest)!=source.content_hash
                or scenario.get('source_snapshot_id')!=str(source.id)
                or scenario.get('source_snapshot_hash')!=source.content_hash
                or scenario.get('changes_hash')!=content_hash(row.payload['changes'])
                or invalidation_ids(db,source.id)
                or current_hash(db,source)!=content_hash(source.manifest['facts'])):
            return None
        from .what_if import apply_changes
        try:return content_hash(apply_changes(source.manifest,row.payload['changes'],row.id))
        except (HTTPException,ValueError,KeyError,TypeError):return None
    policies=m['facts']['coordination_policies']
    policy_id=None
    if policies:
        latest=db.scalar(select(CoordinationRevision).where(CoordinationRevision.kind=='POLICY',
            CoordinationRevision.entity_key==policies[0]['key']).order_by(CoordinationRevision.revision.desc()).limit(1))
        if not latest:return None
        policy_id=latest.id
    body=SnapshotInput(horizon_start=m['horizon_start'],horizon_end=m['horizon_end'],track_ids=m['track_ids'],
        scenario_id=m['scenario_id'],require_freight_forecast=m['require_freight_forecast'],coordination_policy_id=policy_id,
        replanning_capture_id=(m['facts'].get('replanning') or [{}])[0].get('id'))
    try:return content_hash(facts(db,body))
    except HTTPException:return None

def report_json(row,usable,reasons):
    return {'id':str(row.id),'run_id':str(row.run_id),'plan_revision_id':str(row.plan_revision_id) if row.plan_revision_id else None,'snapshot_id':str(row.snapshot_id),
            'status':row.status,'plan_hash':row.plan_hash,'snapshot_hash':row.snapshot_hash,
            'checked_at':row.checked_at.astimezone(timezone.utc).isoformat(),'result':row.result,
            'usable_for_review':usable,'current_blockers':reasons}

def usability(db,row,now):
    blockers=[]
    if invalidation_ids(db,row.snapshot_id):blockers.append('SNAPSHOT_INVALIDATED_BY_EVENT')
    if row.status!='PASS':blockers.append('VALIDATION_NOT_PASS')
    if row.validator_version!=VERSION:blockers.append('VALIDATOR_VERSION_CHANGED')
    run=db.get(PlanningRun,row.run_id)
    snapshot=db.get(PlanningSnapshot,row.snapshot_id)
    if snapshot and execution_pending(db,snapshot):blockers.append('EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    revision=db.get(PlanRevision,row.plan_revision_id) if row.plan_revision_id else None
    if revision:
        if content_hash(revision.content)!=row.plan_hash or revision.plan_hash!=row.plan_hash:blockers.append('PLAN_CHANGED')
    elif not run or run.status!='COMPLETED' or content_hash(run.result)!=row.plan_hash:blockers.append('PLAN_CHANGED')
    if not snapshot or content_hash(snapshot.manifest)!=row.snapshot_hash:blockers.append('SNAPSHOT_CHANGED')
    elif current_hash(db,snapshot)!=content_hash(snapshot.manifest['facts']):blockers.append('OPERATIONAL_STATE_CHANGED')
    context=snapshot.manifest.get('validation_context') if snapshot else None
    if not context or not instant(context['received_at'])<=now<instant(context['valid_until']):blockers.append('DATA_STALE_OR_UNKNOWN')
    return not blockers,blockers

@router.post('/validation-reports',status_code=201)
def create_report(body:ValidationInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),now=Depends(utc_now)):
    # Consistent view of current facts; approval must perform its own atomic recheck.
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as db:
            revision=db.get(PlanRevision,body.plan_revision_id) if body.plan_revision_id else None
            run=db.get(PlanningRun,revision.run_id if revision else body.run_id)
            if body.plan_revision_id and not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
            if not run:raise HTTPException(404,'RUN_NOT_FOUND')
            if run.status!='COMPLETED':raise HTTPException(409,'RUN_NOT_COMPLETED')
            plan=revision.content if revision else run.result
            if content_hash(plan)!=body.expected_plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
            snapshot=db.get(PlanningSnapshot,run.snapshot_id)
            if revision and (revision.snapshot_id!=snapshot.id or revision.snapshot_hash!=snapshot.content_hash):raise HTTPException(409,'PLAN_REVISION_SNAPSHOT_MISMATCH')
            result=validate(snapshot.manifest,snapshot.content_hash,plan,body.expected_plan_hash,now,current_hash(db,snapshot))
            row=ValidationReport(run_id=run.id,snapshot_id=snapshot.id,plan_hash=body.expected_plan_hash,
                snapshot_hash=snapshot.content_hash,validator_version=VERSION,status=result['status'],checked_at=now,result=result,
                plan_revision_id=revision.id if revision else None)
            db.add(row);db.flush()
            audit(db,user,'PLAN_VALIDATED',row.id,{'status':row.status,'run_id':str(run.id),'plan_hash':row.plan_hash})
            usable,reasons=usability(db,row,now)
            db.commit()
            return report_json(row,usable,reasons)

@router.get('/validation-reports/{id}')
def read_report(id:uuid.UUID,user=Depends(current_user),now=Depends(utc_now),db=Depends(session_dependency)):
    row=db.get(ValidationReport,id)
    if not row:raise HTTPException(404,'VALIDATION_REPORT_NOT_FOUND')
    usable,reasons=usability(db,row,now)
    return report_json(row,usable,reasons)
