"""Capture facts for replacement planning; approval remains a separate boundary."""
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import require,current_user
from .db import session_dependency
from .models import PlanRevision,ReplanningCapture
from .requests import StrictModel,digest,audit
from .decision_support import lock_state
from .staleness import lock_publication
from .validation import utc_now
from .replanning_state import capture_payload,current_capture

router=APIRouter(prefix='/api/v1')


class CaptureInput(StrictModel):
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_operational_revision:int=Field(ge=0)


def serialize(db,row):
    return {'id':str(row.id),'plan_revision_id':str(row.plan_revision_id),'content_hash':row.content_hash,
        'payload':row.payload,'current':current_capture(db,row),
        'status':'BLOCKED' if row.payload['blockers'] else 'CAPTURED'}


@router.post('/plan-revisions/{id}/replanning-captures',status_code=201)
def capture(id:uuid.UUID,body:CaptureInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    state=lock_state(db,'SIMULATED');lock_publication(db)
    parent=db.get(PlanRevision,id)
    if not parent:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    if parent.plan_hash!=body.expected_plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    payload=capture_payload(db,parent,now);content_hash=digest(payload)
    row=db.scalar(select(ReplanningCapture).where(ReplanningCapture.content_hash==content_hash))
    if not row:
        row=ReplanningCapture(plan_revision_id=id,content_hash=content_hash,payload=payload,created_by=str(user.id),created_at=now)
        db.add(row);db.flush();audit(db,user,'REPLANNING_CAPTURED',row.id,{'blockers':payload['blockers'],'content_hash':content_hash})
    result=serialize(db,row);db.commit();return result


@router.get('/replanning-captures/{id}')
def read(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(ReplanningCapture,id)
    if not row:raise HTTPException(404,'REPLANNING_CAPTURE_NOT_FOUND')
    return serialize(db,row)
