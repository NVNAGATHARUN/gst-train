"""Explicit remaining-work assessments and simulated restoration observations."""
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import AwareDatetime,Field,model_validator
from sqlalchemy import select
from .auth import current_user,require
from .db import session_dependency
from .models import (WorkReconciliation,PossessionRelease,ExecutionRecord,PlanRevision,PlanningSnapshot,
    ControllerDecision,PlanReservation,PlanningRun,MaintenanceRequest,RequestRevision)
from .requests import StrictModel,digest,audit
from .decision_support import lock_state
from .staleness import lock_publication
from .freeze_state import execution_pending
from .validation import utc_now

router=APIRouter(prefix='/api/v1')


class ReconcileInput(StrictModel):
    idempotency_key:uuid.UUID
    execution_record_id:uuid.UUID
    expected_operational_revision:int=Field(ge=0)
    expected_revision:int=Field(ge=0)
    expected_request_revision:int=Field(ge=1)
    remaining_work_minutes:int=Field(ge=1,le=10080)
    restart_setup_minutes:int=Field(ge=0,le=1440)
    restart_restore_minutes:int=Field(ge=0,le=1440)
    earliest_restart_at:AwareDatetime
    verified:Literal[True]
    evidence_reference:str=Field(min_length=3,max_length=1000)


class ReleaseInput(StrictModel):
    idempotency_key:uuid.UUID
    decision_id:uuid.UUID
    candidate_id:str=Field(min_length=1,max_length=100)
    expected_assignment_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_operational_revision:int=Field(ge=0)
    expected_execution_ids:dict[str,uuid.UUID]
    reconciliation_ids:dict[str,uuid.UUID]=Field(default_factory=dict)
    actual_possession_start:AwareDatetime
    restoration_started_at:AwareDatetime
    restored_at:AwareDatetime
    verified:Literal[True]
    track_restored:Literal[True]
    electrical_restored:Literal[True]
    signalling_restored:Literal[True]
    all_resources_clear:Literal[True]
    evidence_reference:str=Field(min_length=3,max_length=1000)

    @model_validator(mode='after')
    def time_order(self):
        if not self.actual_possession_start<self.restoration_started_at<=self.restored_at:
            raise ValueError('ordered actual possession and restoration intervals required')
        return self


def serialize(row):
    return {'id':str(row.id),'payload_hash':row.payload_hash,'payload':row.payload,'result':row.result,
        'created_at':row.created_at.isoformat()}


def latest_execution(db,rid):
    return db.scalar(select(ExecutionRecord).where(ExecutionRecord.request_id==rid)
        .order_by(ExecutionRecord.sequence.desc()).limit(1))


def latest_reconciliation(db,eid):
    return db.scalar(select(WorkReconciliation).where(WorkReconciliation.execution_record_id==eid)
        .order_by(WorkReconciliation.revision.desc()).limit(1))


def saved_duplicate(db,model,key,payload,user):
    old=db.scalar(select(model).where(model.idempotency_key==key))
    if old and (old.payload_hash!=digest(payload) or old.actor!=str(user.id)):
        raise HTTPException(409,'IDEMPOTENCY_KEY_REUSED')
    return old


def current_request(db,rid,revision):
    request=db.get(MaintenanceRequest,uuid.UUID(rid))
    if not request or request.revision!=revision or request.status!='PENDING_PLANNING':
        raise HTTPException(409,'REQUEST_REVISION_OR_STATUS_CHANGED')
    original=db.scalar(select(RequestRevision).where(RequestRevision.request_id==request.id,RequestRevision.revision==revision))
    return {'id':rid,'revision':revision,'status':request.status,'payload':original.payload}


def supersede(db):
    for run in db.scalars(select(PlanningRun).where(PlanningRun.status.in_(['QUEUED','RUNNING']))
            .order_by(PlanningRun.id).with_for_update()):
        if execution_pending(db,db.get(PlanningSnapshot,run.snapshot_id)):run.status='SUPERSEDED'


@router.post('/work-reconciliations',status_code=201)
def reconcile(body:ReconcileInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    state=lock_state(db,'SIMULATED');lock_publication(db)
    payload=body.model_dump(mode='json');old=saved_duplicate(db,WorkReconciliation,body.idempotency_key,payload,user)
    if old:return serialize(old)
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    observed=db.get(ExecutionRecord,body.execution_record_id)
    if not observed or observed.scope!='SIMULATED' or observed.status!='INTERRUPTED':raise HTTPException(409,'INTERRUPTED_OBSERVATION_REQUIRED')
    if latest_execution(db,observed.request_id).id!=observed.id:raise HTTPException(409,'EXECUTION_OBSERVATION_SUPERSEDED')
    if not db.scalar(select(PlanReservation.id).where(PlanReservation.decision_id==observed.decision_id,
            PlanReservation.active.is_(True)).limit(1)):raise HTTPException(409,'ACTIVE_APPROVAL_REQUIRED')
    if db.scalar(select(PossessionRelease.id).where(PossessionRelease.decision_id==observed.decision_id,
            PossessionRelease.candidate_id==observed.candidate_id)):raise HTTPException(409,'POSSESSION_ALREADY_RELEASED')
    previous=latest_reconciliation(db,observed.id)
    if (previous.revision if previous else 0)!=body.expected_revision:raise HTTPException(409,'RECONCILIATION_REVISION_CONFLICT')
    revision=db.get(PlanRevision,observed.plan_revision_id)
    task=next(t for a in revision.content['assignments'] for t in a['tasks'] if t['request_id']==observed.request_id)
    if body.expected_request_revision!=task['request_revision']:raise HTTPException(409,'APPROVED_REQUEST_REVISION_CHANGED')
    source=current_request(db,observed.request_id,body.expected_request_revision)
    known=observed.payload['remaining_work_minutes']
    if known is not None and known!=body.remaining_work_minutes:raise HTTPException(409,'OBSERVED_REMAINING_WORK_MISMATCH')
    if body.remaining_work_minutes>source['payload']['work_minutes']:raise HTTPException(422,'ADDITIONAL_WORK_REQUIRES_REVISED_REQUEST')
    if observed.observed_at>now or body.earliest_restart_at<observed.observed_at:raise HTTPException(422,'RESTART_BEFORE_INTERRUPTION')
    row=WorkReconciliation(execution_record_id=observed.id,revision=body.expected_revision+1,
        idempotency_key=body.idempotency_key,payload=payload,payload_hash=digest(payload),actor=str(user.id),created_at=now,
        result={'source_request':source,'request_id':observed.request_id,'execution_sequence':observed.sequence,
            'restoration_required':True,'operational_revision':state.revision+1,'authority':'SIMULATED_ASSESSMENT_ONLY'})
    db.add(row);db.flush();state.revision+=1;state.updated_at=now;supersede(db)
    audit(db,user,'REMAINING_WORK_RECONCILED',row.id,{'request_id':observed.request_id,'revision':row.revision})
    db.commit();return serialize(row)


@router.post('/possession-releases',status_code=201)
def release(body:ReleaseInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    state=lock_state(db,'SIMULATED');lock_publication(db)
    payload=body.model_dump(mode='json');old=saved_duplicate(db,PossessionRelease,body.idempotency_key,payload,user)
    if old:return serialize(old)
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    decision=db.get(ControllerDecision,body.decision_id)
    if not decision or decision.scope!='SIMULATED' or decision.action!='APPROVE':raise HTTPException(409,'SIMULATED_APPROVAL_REQUIRED')
    revision=db.get(PlanRevision,decision.plan_revision_id);snapshot=db.get(PlanningSnapshot,revision.snapshot_id)
    if snapshot.scenario_id or digest(revision.content)!=revision.plan_hash:raise HTTPException(409,'SOURCE_PLAN_INVALID')
    assignment=next((a for a in revision.content['assignments'] if a['id']==body.candidate_id),None)
    if not assignment or digest(assignment)!=body.expected_assignment_hash:raise HTTPException(409,'ASSIGNMENT_HASH_MISMATCH')
    if db.scalar(select(PossessionRelease.id).where(PossessionRelease.decision_id==decision.id,
            PossessionRelease.candidate_id==body.candidate_id)):raise HTTPException(409,'POSSESSION_ALREADY_RELEASED')
    if body.restored_at>now:raise HTTPException(422,'RESTORATION_OBSERVATION_IN_FUTURE')
    minimum_restore=max((datetime.fromisoformat(t['restore_end'])-datetime.fromisoformat(t['restore_start'])).total_seconds()
        for t in assignment['tasks'])
    if (body.restored_at-body.restoration_started_at).total_seconds()<minimum_restore:
        raise HTTPException(422,'RESTORATION_DURATION_TOO_SHORT')
    if set(body.expected_execution_ids)!=set(assignment['request_ids']):raise HTTPException(422,'COMPLETE_BUNDLE_EVIDENCE_REQUIRED')
    interrupted=set();latest=[]
    for rid in assignment['request_ids']:
        record=latest_execution(db,rid)
        if not record or record.id!=body.expected_execution_ids[rid] or record.decision_id!=decision.id or record.assignment_hash!=digest(assignment):
            raise HTTPException(409,'EXECUTION_EVIDENCE_CHANGED')
        if record.status not in ('COMPLETED','INTERRUPTED'):raise HTTPException(409,'WORK_STILL_ACTIVE_OR_UNKNOWN')
        if not body.actual_possession_start<=record.observed_at<=body.restoration_started_at:
            raise HTTPException(422,'RESTORATION_PRECEDES_TERMINAL_OBSERVATION')
        observations=db.scalars(select(ExecutionRecord).where(ExecutionRecord.request_id==rid,ExecutionRecord.decision_id==decision.id)).all()
        if any(r.observed_at<body.actual_possession_start for r in observations):raise HTTPException(422,'ACTUAL_START_AFTER_EXECUTION')
        latest.append(record)
        if record.status=='INTERRUPTED':
            interrupted.add(rid);reconciliation=latest_reconciliation(db,record.id)
            if not reconciliation or body.reconciliation_ids.get(rid)!=reconciliation.id:raise HTTPException(409,'CURRENT_RECONCILIATION_REQUIRED')
            source=reconciliation.result['source_request']
            if current_request(db,rid,source['revision'])!=source:raise HTTPException(409,'RECONCILED_REQUEST_CHANGED')
    if set(body.reconciliation_ids)!=interrupted:raise HTTPException(422,'RECONCILIATION_COVERAGE_MISMATCH')
    units=sorted({a['resource_id'] for a in assignment['allocations']})
    reservations=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==decision.id,PlanReservation.active.is_(True))).all()
    matched=[r for r in reservations if set(r.track_ids)==set(assignment['track_ids']) and set(r.resource_ids)==set(units)
        and r.start_at==datetime.fromisoformat(assignment['possession_start']) and r.end_at==datetime.fromisoformat(assignment['possession_end'])]
    if len(matched)!=1:raise HTTPException(409,'ACTIVE_RESERVATION_MISSING_OR_AMBIGUOUS')
    duties=[]
    for uid in units:
        tracks={a['track_id'] for a in assignment['allocations'] if a['resource_id']==uid}
        if len(tracks)!=1:raise HTTPException(409,'ACTUAL_RESOURCE_LOCATION_REQUIRES_RECONCILIATION')
        duties.append({'resource_id':uid,'track_id':next(iter(tracks)),
            'start_at':payload['actual_possession_start'],'end_at':payload['restored_at']})
    result={'plan_revision_id':str(revision.id),'assignment':assignment,'assignment_hash':digest(assignment),
        'execution_ids':{r.request_id:str(r.id) for r in latest},'actual_resource_duties':duties,
        'resource_accounting_policy':'FULL_OBSERVED_POSSESSION_CONSERVATIVE',
        'reservation_released':True,'scope':'SIMULATED','operational_revision':state.revision+1,
        'authority':'SOFTWARE_OBSERVATION_ONLY','railway_control_issued':False}
    row=PossessionRelease(decision_id=decision.id,candidate_id=body.candidate_id,reservation_id=matched[0].id,
        idempotency_key=body.idempotency_key,payload=payload,payload_hash=digest(payload),result=result,actor=str(user.id),created_at=now)
    db.add(row);matched[0].active=False;state.revision+=1;state.updated_at=now;db.flush();supersede(db)
    audit(db,user,'POSSESSION_RESTORATION_RECORDED',row.id,{'reservation_id':str(matched[0].id),'scope':'SIMULATED'})
    db.commit();return serialize(row)


@router.get('/possession-releases/{id}')
def read_release(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(PossessionRelease,id)
    if not row:raise HTTPException(404,'RELEASE_NOT_FOUND')
    return serialize(row)


@router.get('/work-reconciliations/{id}')
def read_reconciliation(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(WorkReconciliation,id)
    if not row:raise HTTPException(404,'RECONCILIATION_NOT_FOUND')
    return serialize(row)
