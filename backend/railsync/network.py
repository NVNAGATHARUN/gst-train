import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, AwareDatetime, model_validator
from sqlalchemy import select, delete
from .requests import StrictModel, audit
from .models import NetworkEntity, NetworkRevision, NetworkLink
from .auth import current_user, require
from .db import session_dependency

router=APIRouter(prefix='/api/v1')
class Station(StrictModel):
    name:str=Field(min_length=1,max_length=100)
class Section(StrictModel):
    from_station:str
    to_station:str
    distance_km:float=Field(gt=0)
class Track(StrictModel):
    section_id:str
    direction:Literal['UP','DOWN','BOTH']='BOTH'
    status:Literal['OPEN','CLOSED']='OPEN'
    electrified:bool=False
class Asset(StrictModel):
    department:Literal['ENGINEERING','TRD','SNT']
    asset_type:str
    footprint:list[str]=Field(min_length=1)
class Isolation(StrictModel):
    footprint:list[str]=Field(min_length=1)
class Restriction(StrictModel):
    footprint:list[str]=Field(min_length=1)
    start:AwareDatetime
    end:AwareDatetime
    rule_id:str=Field(min_length=1)
    type:Literal['CLOSURE','WORK_PROHIBITED','ISOLATION_UNAVAILABLE']
    @model_validator(mode='after')
    def times(self):
        if self.end<=self.start:raise ValueError('end must be after start')
        return self
SCHEMAS={'station':Station,'section':Section,'track':Track,'asset':Asset,'isolation':Isolation,'restriction':Restriction}
def network_records(db,kind=None):
    q=select(NetworkEntity,NetworkRevision).join(NetworkRevision,(NetworkEntity.id==NetworkRevision.entity_id)&(NetworkEntity.revision==NetworkRevision.revision))
    if kind:q=q.where(NetworkEntity.kind==kind)
    return [{'id':e.id,'kind':e.kind,'revision':e.revision,**r.payload} for e,r in db.execute(q).all()]
def require_entity(db,id,kind):
    entity=db.get(NetworkEntity,id)
    if not entity or entity.kind!=kind:raise HTTPException(422,{'code':'UNKNOWN_REFERENCE','id':id,'kind':kind})
    return entity
class EntityInput(StrictModel):
    id:str=Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    expected_revision:int=Field(default=0,ge=0)
    data:dict

def save_entity(db,kind,body,user):
    if kind not in SCHEMAS:raise HTTPException(422,'UNKNOWN_NETWORK_KIND')
    try:data=SCHEMAS[kind].model_validate(body.data).model_dump(mode='json')
    except ValueError as e:raise HTTPException(422,str(e))
    links=[]
    if kind=='section':
        if data['from_station']==data['to_station']:raise HTTPException(422,'SECTION_SELF_LOOP')
        links=[(data[k],'station',k) for k in ['from_station','to_station']]
    if kind=='track':links=[(data['section_id'],'section','section')]
    if 'footprint' in data:
        if len(set(data['footprint']))!=len(data['footprint']):raise HTTPException(422,'DUPLICATE_FOOTPRINT')
        links=[(id,'track','footprint') for id in data['footprint']]
    for id,target,_ in links:require_entity(db,id,target)
    entity=db.scalar(select(NetworkEntity).where(NetworkEntity.id==body.id).with_for_update())
    if entity:
        if entity.revision!=body.expected_revision or entity.kind!=kind:raise HTTPException(409,'STALE_ENTITY_REVISION')
        entity.revision+=1
        db.execute(delete(NetworkLink).where(NetworkLink.parent_id==body.id))
    else:
        if body.expected_revision!=0:raise HTTPException(409,'STALE_ENTITY_REVISION')
        entity=NetworkEntity(id=body.id,kind=kind,revision=1);db.add(entity);db.flush()
    db.add(NetworkRevision(entity_id=body.id,revision=entity.revision,payload=data))
    for id,_,relation in links:db.add(NetworkLink(parent_id=body.id,child_id=id,relation=relation))
    audit(db,user,'NETWORK_REVISED',body.id,{'kind':kind,'revision':entity.revision});db.flush()
    return {'id':body.id,'kind':kind,'revision':entity.revision,**data}

def validate_request_location(db,data):
    entity=require_entity(db,data.asset_id,'asset')
    revision=db.scalar(select(NetworkRevision).where(NetworkRevision.entity_id==entity.id,NetworkRevision.revision==entity.revision))
    asset=revision.payload
    if asset['department']!=data.department:raise HTTPException(422,'ASSET_DEPARTMENT_MISMATCH')
    if not set(asset['footprint']).issubset(data.footprint):raise HTTPException(422,'ASSET_FOOTPRINT_NOT_COVERED')
    for track in data.footprint:require_entity(db,track,'track')
    if data.power_block_required:
        zone=require_entity(db,data.isolation_zone,'isolation')
        z=db.scalar(select(NetworkRevision).where(NetworkRevision.entity_id==zone.id,NetworkRevision.revision==zone.revision))
        if not set(data.footprint).issubset(z.payload['footprint']):raise HTTPException(422,'ISOLATION_COVERAGE_MISSING')

@router.post('/network/{kind}',status_code=201)
def create_entity(kind:str,body:EntityInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    output=save_entity(db,kind,body,user);db.commit();return output
@router.get('/network')
def get_network(kind:str|None=None,user=Depends(current_user),db=Depends(session_dependency)):
    return {'items':network_records(db,kind)}
@router.get('/assets')
def get_assets(user=Depends(current_user),db=Depends(session_dependency)):
    items=network_records(db,'asset')
    return {'items':[a for a in items if user.role!='DEPARTMENT' or a['department']==user.department]}
