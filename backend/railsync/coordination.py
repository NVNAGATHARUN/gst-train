"""Persistence boundary for explicit resource rules and candidate coordination."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, text
from .auth import current_user, require
from .db import session_dependency
from .models import (CoordinationRevision, CoordinationComputation, ResourceUnit,
                     PlanningSnapshot, OpportunityComputation, AvailabilityComputation)
from .requests import StrictModel, audit, digest
from .network import require_entity
from .coordination_schema import CoordinationPolicy, ResourceProfile
from .coordination_engine import coordinate

router = APIRouter(prefix='/api/v1')
ENGINE_VERSION = 'COORDINATION_V1'

class ProfileWrite(StrictModel):
    expected_revision: int = Field(ge=0)
    data: ResourceProfile

class PolicyWrite(StrictModel):
    expected_revision: int = Field(ge=0)
    data: CoordinationPolicy

class CoordinationInput(StrictModel):
    opportunity_id: uuid.UUID
    max_bundle_size: int = Field(default=3, ge=1, le=4)
    max_groups: int = Field(default=500, ge=1, le=5000)
    max_time_plans: int = Field(default=5000, ge=1, le=20000)
    max_assignments_per_plan: int = Field(default=20, ge=1, le=1000)
    max_assignment_nodes_per_plan: int = Field(default=10000, ge=1, le=100000)
    max_resource_slots_per_plan: int = Field(default=100, ge=1, le=500)
    max_candidates: int = Field(default=1000, ge=1, le=3000)

def revision_json(row):
    return {'id': str(row.id), 'kind': row.kind, 'key': row.entity_key,
            'revision': row.revision, 'data': row.payload}

def save_revision(db, user, kind, key, expected, payload):
    if not key or len(key)>100:raise HTTPException(422, 'INVALID_KEY')
    db.execute(text('SELECT pg_advisory_xact_lock(2602710)'))
    latest = db.scalar(select(CoordinationRevision).where(
        CoordinationRevision.kind==kind, CoordinationRevision.entity_key==key
    ).order_by(CoordinationRevision.revision.desc()).limit(1))
    if expected != (latest.revision if latest else 0):
        raise HTTPException(409, 'REVISION_CONFLICT')
    row = CoordinationRevision(kind=kind, entity_key=key, revision=expected+1, payload=payload)
    db.add(row)
    db.flush()
    audit(db, user, 'COORDINATION_RULE_REVISED', row.id, {'kind': kind, 'key': key, 'revision': row.revision})
    db.commit()
    return revision_json(row)

@router.post('/resources/{id}/profiles', status_code=201)
def write_profile(id: str, body: ProfileWrite, user=Depends(require('ADMIN','PLANNER')), db=Depends(session_dependency)):
    unit=db.get(ResourceUnit,id)
    if not unit:raise HTTPException(422, 'UNKNOWN_RESOURCE')
    if body.data.source_mode!=unit.source_mode:raise HTTPException(422,'SOURCE_MODE_MISMATCH')
    for track in {body.data.home_track, *(d.track_id for d in body.data.duties)}:
        require_entity(db, track, 'track')
    return save_revision(db, user, 'RESOURCE_PROFILE', id, body.expected_revision, body.data.model_dump(mode='json'))

@router.post('/coordination-policies/{key}', status_code=201)
def write_policy(key: str, body: PolicyWrite, user=Depends(require('ADMIN','PLANNER')), db=Depends(session_dependency)):
    for rule in body.data.travel:
        require_entity(db, rule.from_track, 'track')
        require_entity(db, rule.to_track, 'track')
    return save_revision(db, user, 'POLICY', key, body.expected_revision, body.data.model_dump(mode='json'))

@router.get('/coordination-rules')
def list_revisions(kind: str | None = Query(default=None,pattern='^(RESOURCE_PROFILE|POLICY)$'),
        key: str | None = Query(default=None,max_length=100),limit: int = Query(100,ge=1,le=200),
        offset: int = Query(0,ge=0),user=Depends(require('ADMIN','PLANNER','CONTROLLER','AUDITOR')),
        db=Depends(session_dependency)):
    query=select(CoordinationRevision)
    if kind:query=query.where(CoordinationRevision.kind==kind)
    if key:query=query.where(CoordinationRevision.entity_key==key)
    rows=db.scalars(query.order_by(CoordinationRevision.kind,CoordinationRevision.entity_key,
        CoordinationRevision.revision.desc()).offset(offset).limit(limit)).all()
    return {'items':[revision_json(row) for row in rows],
        'next_offset':offset+limit if len(rows)==limit else None}

@router.get('/coordination-rules/{id}')
def read_revision(id: uuid.UUID, user=Depends(current_user), db=Depends(session_dependency)):
    row=db.get(CoordinationRevision,id)
    if not row:raise HTTPException(404,'RULE_NOT_FOUND')
    return revision_json(row)

def serialize(row, duplicate=False):
    return {'id':str(row.id),'snapshot_id':str(row.snapshot_id),'opportunity_id':str(row.opportunity_id),
            'input_hash':row.input_hash,'duplicate':duplicate,'result':row.result}

@router.post('/coordinated-candidates', status_code=201)
def calculate(body: CoordinationInput, user=Depends(require('ADMIN','PLANNER')), db=Depends(session_dependency)):
    opportunity=db.get(OpportunityComputation,body.opportunity_id)
    if not opportunity:raise HTTPException(422,'UNKNOWN_OPPORTUNITIES')
    snapshot=db.get(PlanningSnapshot,opportunity.snapshot_id)
    if digest(snapshot.manifest)!=snapshot.content_hash:raise HTTPException(409,'SNAPSHOT_HASH_MISMATCH')
    availability=[]
    for id in opportunity.configuration['availability_ids']:
        row=db.get(AvailabilityComputation,uuid.UUID(id))
        if not row or row.snapshot_id!=snapshot.id:raise HTTPException(422,'AVAILABILITY_SNAPSHOT_MISMATCH')
        availability.append({'policy':row.policy,'result':row.result,'input_hash':row.input_hash})
    config=body.model_dump(mode='json')
    input_hash=digest({'snapshot_hash':snapshot.content_hash,'opportunity_hash':opportunity.input_hash,
                       'engine_version':ENGINE_VERSION,'config':config})
    db.execute(text('SELECT pg_advisory_xact_lock(2602711)'))
    existing=db.scalar(select(CoordinationComputation).where(CoordinationComputation.input_hash==input_hash))
    if existing:return serialize(existing,True)
    result=coordinate(snapshot.manifest,opportunity.result,availability,config)
    result['engine_version']=ENGINE_VERSION
    result['snapshot_hash']=snapshot.content_hash
    row=CoordinationComputation(snapshot_id=snapshot.id,opportunity_id=opportunity.id,input_hash=input_hash,
                                configuration=config,result=result)
    db.add(row)
    db.flush()
    audit(db,user,'CANDIDATES_COORDINATED',row.id,result['counts'])
    db.commit()
    return serialize(row)

@router.get('/coordinated-candidates/{id}')
def read(id: uuid.UUID, user=Depends(current_user), db=Depends(session_dependency)):
    row=db.get(CoordinationComputation,id)
    if not row:raise HTTPException(404,'COORDINATION_NOT_FOUND')
    return serialize(row)
