from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select
from .auth import current_user, require
from .db import session_dependency
from .models import Train, TrainRun, TrainOccupancy, CoaWindow, FreightForecast, NetworkEntity, NetworkRevision
from .network import require_entity
from .requests import StrictModel, audit, digest
from .source_versions import effective_versions

router=APIRouter(prefix='/api/v1')

class OccupancyInput(StrictModel):
    track_id:str
    route_sequence:int=Field(ge=1)
    enter_at:AwareDatetime
    exit_at:AwareDatetime
    timing_source:Literal['TIMETABLE','CONFIRMED','SIMULATED']='SIMULATED'
    @model_validator(mode='after')
    def time_order(self):
        if self.exit_at<=self.enter_at:raise ValueError('exit_at must be after enter_at')
        return self

class TrainRunInput(StrictModel):
    train_id:str=Field(min_length=1,max_length=100)
    train_name:str=Field(min_length=1,max_length=120)
    train_type:Literal['PREMIUM','EXPRESS','PASSENGER','SUBURBAN','FREIGHT','SPECIAL']
    service_date:date
    source_mode:Literal['SIMULATED','IMPORTED']='SIMULATED'
    source_revision:int=Field(ge=1)
    occupancies:list[OccupancyInput]=Field(min_length=1,max_length=500)

class WindowInput(StrictModel):
    external_id:str=Field(min_length=1,max_length=100)
    source_revision:int=Field(ge=1)
    track_id:str
    start_at:AwareDatetime
    end_at:AwareDatetime
    source_mode:Literal['SIMULATED','IMPORTED']='SIMULATED'
    @model_validator(mode='after')
    def time_order(self):
        if self.end_at<=self.start_at:raise ValueError('end_at must be after start_at')
        return self

class FreightInput(WindowInput):
    issued_at:AwareDatetime
    expected_count:int=Field(ge=0,le=1000)
    confidence:float=Field(ge=0,le=1)
    uncertainty_semantics:str=Field(min_length=1,max_length=80)

def current_payload(db,entity):
    return db.scalar(select(NetworkRevision).where(NetworkRevision.entity_id==entity.id,NetworkRevision.revision==entity.revision)).payload

def track_section(db,track_id):
    track=require_entity(db,track_id,'track')
    section=require_entity(db,current_payload(db,track)['section_id'],'section')
    return current_payload(db,section)

def endpoints(section):return {section['from_station'],section['to_station']}

@router.post('/operations/train-runs',status_code=201)
def create_run(body:TrainRunInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    rows=sorted(body.occupancies,key=lambda x:x.route_sequence)
    if [o.route_sequence for o in rows] != list(range(1,len(rows)+1)):raise HTTPException(422,'ROUTE_SEQUENCE_GAP')
    service_start=datetime.combine(body.service_date,time.min,tzinfo=ZoneInfo('Asia/Kolkata'))
    sections=[]
    for index,o in enumerate(rows):
        sections.append(track_section(db,o.track_id))
        if o.enter_at<service_start:raise HTTPException(422,'OCCUPANCY_BEFORE_SERVICE_DATE')
        if index and rows[index-1].exit_at>o.enter_at:raise HTTPException(422,'RUN_TEMPORAL_OVERLAP')
        if index and not endpoints(sections[index-1]).intersection(endpoints(sections[index])):raise HTTPException(422,'DISCONNECTED_ROUTE')
    raw=body.model_dump(mode='json');payload_hash=digest(raw)
    train=db.get(Train,body.train_id)
    if train and (train.name!=body.train_name or train.train_type!=body.train_type):raise HTTPException(409,'TRAIN_IDENTITY_CONFLICT')
    if not train:db.add(Train(id=body.train_id,name=body.train_name,train_type=body.train_type))
    existing=db.scalar(select(TrainRun).where(TrainRun.train_id==body.train_id,TrainRun.service_date==service_start,TrainRun.source_revision==body.source_revision))
    if existing:
        if existing.payload_hash==payload_hash:return {'id':str(existing.id),'duplicate':True,'occupancy_count':len(rows)}
        raise HTTPException(409,'RUN_REVISION_CONFLICT')
    previous=db.scalar(select(TrainRun).where(TrainRun.train_id==body.train_id,TrainRun.service_date==service_start)
        .order_by(TrainRun.source_revision.desc()).limit(1))
    if previous and (previous.source_revision>=body.source_revision or previous.source_mode!=body.source_mode):
        raise HTTPException(409,'RUN_SOURCE_REVISION_CONFLICT')
    run=TrainRun(train_id=body.train_id,service_date=service_start,source_mode=body.source_mode,source_revision=body.source_revision,payload_hash=payload_hash);db.add(run);db.flush()
    for o in rows:db.add(TrainOccupancy(run_id=run.id,track_id=o.track_id,route_sequence=o.route_sequence,enter_at=o.enter_at,exit_at=o.exit_at,timing_source=o.timing_source))
    audit(db,user,'TRAIN_RUN_CREATED',run.id,{'source_mode':body.source_mode,'source_revision':body.source_revision});db.commit()
    return {'id':str(run.id),'duplicate':False,'occupancy_count':len(rows)}

def save_window(db,model,body,user,action,extra=None):
    require_entity(db,body.track_id,'track');payload=body.model_dump(mode='json');h=digest(payload)
    previous=db.scalar(select(model).where(model.external_id==body.external_id).order_by(model.source_revision.desc()).limit(1))
    if previous and previous.source_revision>=body.source_revision:
        if previous.source_revision==body.source_revision and previous.payload_hash==h:return {'id':str(previous.id),'duplicate':True}
        raise HTTPException(409,'SOURCE_REVISION_CONFLICT')
    if previous and previous.source_mode!=body.source_mode:raise HTTPException(409,'SOURCE_MODE_CHANGED')
    common=dict(external_id=body.external_id,source_revision=body.source_revision,track_id=body.track_id,start_at=body.start_at,end_at=body.end_at,source_mode=body.source_mode,payload_hash=h)
    if extra:common.update(extra)
    row=model(**common);db.add(row);db.flush();audit(db,user,action,row.id,{'source_mode':body.source_mode});db.commit();return {'id':str(row.id),'duplicate':False}

@router.post('/operations/coa-windows',status_code=201)
def create_coa(body:WindowInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),db=Depends(session_dependency)):
    return save_window(db,CoaWindow,body,user,'COA_WINDOW_CREATED')

@router.post('/operations/freight-forecasts',status_code=201)
def create_freight(body:FreightInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),db=Depends(session_dependency)):
    extra={'issued_at':body.issued_at,'expected_count':body.expected_count,'confidence_basis_points':round(body.confidence*10000),'uncertainty_semantics':body.uncertainty_semantics}
    return save_window(db,FreightForecast,body,user,'FREIGHT_FORECAST_CREATED',extra)

@router.get('/operations/occupancy')
def occupancy(start:AwareDatetime,end:AwareDatetime,track_id:str|None=None,user=Depends(current_user),db=Depends(session_dependency)):
    if end<=start:raise HTTPException(422,'INVALID_HORIZON')
    runs=effective_versions(db.scalars(select(TrainRun)),lambda r:(r.train_id,r.service_date))
    q=select(TrainOccupancy,TrainRun,Train).join(TrainRun,TrainRun.id==TrainOccupancy.run_id).join(Train,Train.id==TrainRun.train_id).where(TrainOccupancy.run_id.in_([r.id for r in runs]),TrainOccupancy.exit_at>start,TrainOccupancy.enter_at<end).order_by(TrainOccupancy.enter_at,TrainOccupancy.route_sequence)
    if track_id:q=q.where(TrainOccupancy.track_id==track_id)
    items=[]
    for o,r,t in db.execute(q):items.append({'run_id':str(r.id),'train_id':t.id,'train_type':t.train_type,'track_id':o.track_id,'route_sequence':o.route_sequence,'enter_at':o.enter_at.isoformat(),'exit_at':o.exit_at.isoformat(),'source_mode':r.source_mode,'source_revision':r.source_revision,'timing_source':o.timing_source})
    return {'items':items}

@router.get('/operations/coverage')
def coverage(start:AwareDatetime,end:AwareDatetime,track_id:list[str]=Query(),user=Depends(current_user),db=Depends(session_dependency)):
    if end<=start or not track_id:raise HTTPException(422,'INVALID_COVERAGE_REQUEST')
    gaps=[]
    runs=effective_versions(db.scalars(select(TrainRun)),lambda r:(r.train_id,r.service_date))
    windows=effective_versions(db.scalars(select(CoaWindow)),lambda w:w.external_id)
    for track in track_id:
        require_entity(db,track,'track')
        occupancy_exists=db.scalar(select(TrainOccupancy.id).where(TrainOccupancy.run_id.in_([r.id for r in runs]),
            TrainOccupancy.track_id==track,TrainOccupancy.exit_at>start,TrainOccupancy.enter_at<end).limit(1))
        coa_exists=any(w.track_id==track and w.end_at>start and w.start_at<end for w in windows)
        if not occupancy_exists:gaps.append({'track_id':track,'source':'OCCUPANCY','status':'UNKNOWN'})
        if not coa_exists:gaps.append({'track_id':track,'source':'COA','status':'UNKNOWN'})
    return {'complete':not gaps,'gaps':gaps}
