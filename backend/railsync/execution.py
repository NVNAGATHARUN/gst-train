"""Controller observations of simulated execution, never commands to railway staff."""
import uuid
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select
from .auth import current_user, require
from .db import session_dependency
from .models import ExecutionRecord, FreezePolicy, PlanRevision, ControllerDecision, PlanReservation, PlanningRun, PlanningSnapshot, PossessionRelease
from .requests import StrictModel, audit, digest
from .decision_support import lock_state, scope_for
from .staleness import lock_publication, invalidation_ids
from .freeze_state import latest_policy, freeze_context, execution_pending
from .validation import utc_now
from .execution_continuation import continuation

router=APIRouter(prefix='/api/v1')


class PolicyInput(StrictModel):
    scope: Literal['SIMULATED']='SIMULATED'
    expected_revision: int=Field(ge=0)
    freeze_minutes: int=Field(ge=0,le=10080)
    reason: str=Field(min_length=3,max_length=1000)


class ExecutionInput(StrictModel):
    idempotency_key: uuid.UUID
    decision_id: uuid.UUID
    expected_plan_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id: str=Field(min_length=1,max_length=100)
    expected_assignment_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    request_id: uuid.UUID
    expected_sequence: int=Field(ge=0)
    expected_operational_revision: int=Field(ge=0)
    status: Literal['STARTED','INTERRUPTED','RESUMED','COMPLETED']
    observed_at: AwareDatetime
    remaining_work_minutes: int|None=Field(default=None,ge=0,le=10080)
    verified: Literal[True]
    evidence_reference: str=Field(min_length=3,max_length=1000)
    note: str=Field(min_length=3,max_length=1000)

    @model_validator(mode='after')
    def remaining(self):
        if self.status=='COMPLETED' and self.remaining_work_minutes!=0:
            raise ValueError('Completion requires explicit zero remaining work')
        if self.status=='STARTED' and self.remaining_work_minutes is not None:
            raise ValueError('STARTED does not assert remaining progress')
        if self.status=='RESUMED' and not self.remaining_work_minutes:
            raise ValueError('RESUMED requires explicit positive remaining work')
        if self.status=='INTERRUPTED' and self.remaining_work_minutes==0:
            raise ValueError('Interrupted work must have positive or unknown remaining work')
        return self


def record_json(row,duplicate=False):
    return {'id':str(row.id),'plan_revision_id':str(row.plan_revision_id),'decision_id':str(row.decision_id),
        'request_id':row.request_id,'candidate_id':row.candidate_id,'assignment_hash':row.assignment_hash,
        'scope':row.scope,'sequence':row.sequence,'status':row.status,'observed_at':row.observed_at.isoformat(),
        'received_at':row.received_at.isoformat(),'payload':row.payload,'result':row.result,'duplicate':duplicate}


@router.post('/freeze-policies',status_code=201)
def configure(body:PolicyInput,user=Depends(require('ADMIN')),now=Depends(utc_now),db=Depends(session_dependency)):
    state=lock_state(db,body.scope)
    old=latest_policy(db,body.scope)
    if (old.revision if old else 0)!=body.expected_revision:raise HTTPException(409,'FREEZE_POLICY_REVISION_CONFLICT')
    row=FreezePolicy(scope=body.scope,revision=body.expected_revision+1,freeze_minutes=body.freeze_minutes,
        reason=body.reason,actor=str(user.id),created_at=now)
    db.add(row);db.flush();state.revision+=1;state.updated_at=now
    audit(db,user,'FREEZE_POLICY_CONFIGURED',row.id,{'revision':row.revision,'freeze_minutes':row.freeze_minutes})
    db.commit()
    return {'id':str(row.id),'scope':row.scope,'revision':row.revision,'freeze_minutes':row.freeze_minutes,
        'resulting_operational_revision':state.revision,'authority':'SOFTWARE_PROPOSAL_ONLY'}


@router.get('/plan-revisions/{id}/freeze-context')
def read_freeze(id:uuid.UUID,user=Depends(current_user),now=Depends(utc_now),db=Depends(session_dependency)):
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id)
    scope=scope_for(snapshot)
    state=lock_state(db,scope)
    result=freeze_context(db,scope,now,revision.lineage_id)
    result['operational_revision']=state.revision
    return result


@router.post('/plan-revisions/{id}/execution-records',status_code=201)
def observe(id:uuid.UUID,body:ExecutionInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id)
    if snapshot.scenario_id or scope_for(snapshot)!='SIMULATED':raise HTTPException(409,'SIMULATED_NON_SCENARIO_EXECUTION_ONLY')
    state=lock_state(db,'SIMULATED')
    lock_publication(db)
    payload=body.model_dump(mode='json');fingerprint=digest(payload)
    duplicate=db.scalar(select(ExecutionRecord).where(ExecutionRecord.idempotency_key==body.idempotency_key))
    if duplicate:
        if duplicate.plan_revision_id!=id or duplicate.payload_hash!=fingerprint or duplicate.actor!=str(user.id):
            raise HTTPException(409,'EXECUTION_IDEMPOTENCY_KEY_REUSED')
        return record_json(duplicate,True)
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    if revision.plan_hash!=body.expected_plan_hash or digest(revision.content)!=body.expected_plan_hash:
        raise HTTPException(409,'PLAN_HASH_MISMATCH')
    approved=db.get(ControllerDecision,body.decision_id)
    if not approved or approved.plan_revision_id!=id or approved.action!='APPROVE' or approved.scope!='SIMULATED':
        raise HTTPException(409,'APPROVED_DECISION_REQUIRED')
    active=db.scalar(select(PlanReservation.id).where(PlanReservation.decision_id==approved.id,PlanReservation.active.is_(True)).limit(1))
    if not active:raise HTTPException(409,'APPROVAL_NO_LONGER_ACTIVE')
    if db.scalar(select(PossessionRelease.id).where(PossessionRelease.decision_id==approved.id,
            PossessionRelease.candidate_id==body.candidate_id)):raise HTTPException(409,'POSSESSION_ALREADY_RELEASED')
    assignment=next((a for a in revision.content['assignments'] if a['id']==body.candidate_id),None)
    rid=str(body.request_id)
    if not assignment or rid not in assignment['request_ids']:raise HTTPException(422,'REQUEST_NOT_IN_APPROVED_ASSIGNMENT')
    if digest(assignment)!=body.expected_assignment_hash:raise HTTPException(409,'ASSIGNMENT_HASH_MISMATCH')
    if body.observed_at>now:raise HTTPException(422,'EXECUTION_OBSERVATION_IN_FUTURE')
    task=next(t for t in assignment['tasks'] if t['request_id']==rid)
    previous=db.scalar(select(ExecutionRecord).where(ExecutionRecord.request_id==rid)
        .order_by(ExecutionRecord.sequence.desc()).limit(1))
    if (previous.sequence if previous else 0)!=body.expected_sequence:raise HTTPException(409,'EXECUTION_SEQUENCE_CONFLICT')
    allowed={None:{'STARTED'},'STARTED':{'INTERRUPTED','COMPLETED'},'INTERRUPTED':{'RESUMED'},
        'RESUMED':{'INTERRUPTED','COMPLETED'},'COMPLETED':set()}
    if body.status not in allowed[previous.status if previous else None]:raise HTTPException(409,'INVALID_EXECUTION_TRANSITION')
    continuation_evidence=None
    if previous:
        if body.observed_at<=previous.observed_at:raise HTTPException(409,'EXECUTION_OBSERVATION_OUT_OF_ORDER')
        if previous.decision_id!=approved.id:
            continuation_evidence=continuation(db,revision,approved,snapshot,previous,assignment,task,body)
        elif previous.assignment_hash!=body.expected_assignment_hash:
            raise HTTPException(409,'EXECUTION_ASSIGNMENT_CHANGED')
    work_start=datetime.fromisoformat(task['work_start']);work_end=datetime.fromisoformat(task['work_end'])
    outside=not (work_start<=body.observed_at<work_end or
        (body.status=='COMPLETED' and body.observed_at==work_end))
    result={'authority':'SOFTWARE_OBSERVATION_ONLY','execution_authorized':False,'reservations_released':False,
        'source_plan_stale':bool(invalidation_ids(db,snapshot.id)) or execution_pending(db,snapshot),
        'outside_planned_work_interval':outside,'remaining_work_known':body.remaining_work_minutes is not None,
        'requires_execution_aware_replan':True,'operational_revision':state.revision+1,
        'track_ids':assignment['track_ids'],
        'resource_ids':sorted({a['resource_id'] for a in assignment['allocations']})}
    if continuation_evidence:result['continuation']=continuation_evidence
    row=ExecutionRecord(idempotency_key=body.idempotency_key,plan_revision_id=id,decision_id=approved.id,
        request_id=rid,candidate_id=body.candidate_id,assignment_hash=body.expected_assignment_hash,scope='SIMULATED',
        sequence=body.expected_sequence+1,status=body.status,observed_at=body.observed_at,received_at=now,
        payload_hash=fingerprint,payload=payload,result=result,actor=str(user.id))
    db.add(row);db.flush()
    superseded=[]
    for run in db.scalars(select(PlanningRun).where(PlanningRun.status.in_(['QUEUED','RUNNING']))
            .order_by(PlanningRun.id).with_for_update()):
        if execution_pending(db,db.get(PlanningSnapshot,run.snapshot_id)):
            run.status='SUPERSEDED';superseded.append(str(run.id))
    state.revision+=1;state.updated_at=now
    audit(db,user,'EXECUTION_OBSERVED',row.id,{'status':body.status,'request_id':rid,'superseded_run_ids':superseded})
    db.commit()
    return record_json(row)


@router.get('/plan-revisions/{id}/execution-records')
def read_records(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    if not db.get(PlanRevision,id):raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    rows=db.scalars(select(ExecutionRecord).where(ExecutionRecord.plan_revision_id==id)
        .order_by(ExecutionRecord.request_id,ExecutionRecord.sequence)).all()
    return {'plan_revision_id':str(id),'items':[record_json(r) for r in rows]}
