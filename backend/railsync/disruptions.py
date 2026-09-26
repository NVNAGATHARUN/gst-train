"""M16 event intake. Records invalidate plans; they do not silently patch source facts."""
import uuid
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select
from .auth import current_user, require
from .db import session_dependency
from .models import DisruptionEvent, SnapshotInvalidation, ReplanningBatch, PlanningSnapshot, PlanningRun, ResourceUnit
from .network import require_entity
from .requests import StrictModel, audit, digest
from .decision_support import lock_state
from .staleness import lock_publication
from .validation import utc_now

router = APIRouter(prefix='/api/v1')
DEBOUNCE_SECONDS = 5


class EventInput(StrictModel):
    source: str = Field(min_length=1,max_length=80)
    external_id: str = Field(min_length=1,max_length=100)
    source_revision: int = Field(ge=1)
    scope: Literal['SIMULATED'] = 'SIMULATED'
    kind: Literal['TRAIN_DELAY','FREIGHT_CHANGE','RESOURCE_OUTAGE','URGENT_DEFECT','RESTRICTION_CHANGE']
    occurred_at: AwareDatetime
    track_ids: list[str] = Field(default_factory=list,max_length=100)
    resource_ids: list[str] = Field(default_factory=list,max_length=100)
    evidence_reference: str = Field(min_length=3,max_length=1000)
    description: str = Field(min_length=3,max_length=2000)

    @model_validator(mode='after')
    def footprint(self):
        if not self.track_ids and not self.resource_ids:
            raise ValueError('Explicit affected tracks or resources required')
        if len(set(self.track_ids)) != len(self.track_ids) or len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError('Duplicate impact identity')
        return self


def event_json(row, duplicate=False):
    return {'id':str(row.id),'scope':row.scope,'kind':row.kind,'payload':row.payload,'payload_hash':row.payload_hash,
        'occurred_at':row.occurred_at.isoformat(),'received_at':row.received_at.isoformat(),
        'result':row.result,'duplicate':duplicate}


@router.post('/disruption-events',status_code=201)
def ingest(body:EventInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    # Share approval's scope lock before acquiring the publication lock.
    state=lock_state(db,body.scope)
    lock_publication(db)
    payload=body.model_dump(mode='json')
    payload['track_ids']=sorted(payload['track_ids'])
    payload['resource_ids']=sorted(payload['resource_ids'])
    fingerprint=digest(payload)
    existing=db.scalar(select(DisruptionEvent).where(DisruptionEvent.source==body.source,
        DisruptionEvent.external_id==body.external_id,DisruptionEvent.source_revision==body.source_revision))
    if existing:
        if existing.payload_hash!=fingerprint:raise HTTPException(409,'EVENT_REVISION_CONFLICT')
        return event_json(existing,True)
    latest=db.scalar(select(DisruptionEvent).where(DisruptionEvent.source==body.source,
        DisruptionEvent.external_id==body.external_id).order_by(DisruptionEvent.source_revision.desc()).limit(1))
    if latest and latest.source_revision>=body.source_revision:raise HTTPException(409,'EVENT_REVISION_OUT_OF_ORDER')
    if body.occurred_at>now:raise HTTPException(422,'EVENT_OCCURRENCE_IN_FUTURE')
    for track in body.track_ids:require_entity(db,track,'track')
    for resource in body.resource_ids:
        if not db.get(ResourceUnit,resource):raise HTTPException(422,'UNKNOWN_RESOURCE')
    affected=[]
    for snapshot in db.scalars(select(PlanningSnapshot).where(PlanningSnapshot.scenario_id.is_(None))):
        context=snapshot.manifest.get('validation_context') or {}
        if context.get('scope')!='SIMULATED':continue
        resources={r['id'] for r in snapshot.manifest['facts']['resources']}
        if set(body.track_ids)&set(snapshot.manifest['track_ids']) or set(body.resource_ids)&resources:
            affected.append(snapshot.id)
    batch=db.get(ReplanningBatch,body.scope)
    generation=(batch.generation if batch else 0)+1
    ready_at=now+timedelta(seconds=DEBOUNCE_SECONDS)
    superseded=[]
    if affected:
        for run in db.scalars(select(PlanningRun).where(PlanningRun.snapshot_id.in_(affected),
            PlanningRun.status.in_(['QUEUED','RUNNING'])).order_by(PlanningRun.id).with_for_update()):
            run.status='SUPERSEDED'
            superseded.append(str(run.id))
    result={'status':'NEW_SNAPSHOT_REQUIRED','batch_generation':generation,'ready_at':ready_at.isoformat(),
        'invalidated_snapshot_ids':sorted(str(id) for id in affected),'superseded_run_ids':superseded,
        'operational_revision':state.revision+1,'source_facts_applied':False,
        'authority':'SOFTWARE_PROPOSAL_ONLY'}
    row=DisruptionEvent(source=body.source,external_id=body.external_id,source_revision=body.source_revision,
        scope=body.scope,kind=body.kind,occurred_at=body.occurred_at,received_at=now,
        payload_hash=fingerprint,payload=payload,result=result,actor=str(user.id))
    db.add(row);db.flush()
    db.add_all(SnapshotInvalidation(snapshot_id=id,event_id=row.id) for id in affected)
    if batch:
        batch.generation=generation;batch.ready_at=ready_at;batch.latest_event_id=row.id
    else:db.add(ReplanningBatch(scope=body.scope,generation=generation,ready_at=ready_at,latest_event_id=row.id))
    state.revision+=1;state.updated_at=now
    audit(db,user,'DISRUPTION_RECORDED',row.id,result)
    db.commit()
    return event_json(row)


@router.get('/disruption-events/{id}')
def read(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(DisruptionEvent,id)
    if not row:raise HTTPException(404,'DISRUPTION_EVENT_NOT_FOUND')
    return event_json(row)


@router.get('/replanning-batches/{scope}')
def batch_status(scope:Literal['SIMULATED'],user=Depends(current_user),now=Depends(utc_now),db=Depends(session_dependency)):
    batch=db.get(ReplanningBatch,scope)
    if not batch:return {'scope':scope,'generation':0,'status':'NO_EVENTS'}
    return {'scope':scope,'generation':batch.generation,'ready_at':batch.ready_at.isoformat(),
        'latest_event_id':str(batch.latest_event_id),
        'status':'DEBOUNCING' if now<batch.ready_at else 'READY_FOR_NEW_SNAPSHOT'}
