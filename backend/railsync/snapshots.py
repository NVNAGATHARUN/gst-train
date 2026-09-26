import uuid
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import current_user, require
from .db import session_dependency, engine, Session
from .models import CoordinationRevision
from .models import PlanningSnapshot,SnapshotItem,NetworkEntity,NetworkRevision,MaintenanceRequest,RequestRevision,Train,TrainRun,TrainOccupancy,CoaWindow,FreightForecast,ResourceUnit
from .network import require_entity
from .requests import StrictModel,digest,audit
from .validation_schema import ValidationContext
from .staleness import lock_publication,invalidated_facts
from .source_versions import effective_versions

router=APIRouter(prefix='/api/v1')

class SnapshotInput(StrictModel):
    horizon_start:AwareDatetime
    horizon_end:AwareDatetime
    track_ids:list[str]=Field(min_length=1,max_length=100)
    scenario_id:str|None=Field(default=None,max_length=100)
    require_freight_forecast:bool=True
    coordination_policy_id:uuid.UUID|None=None
    validation_context:ValidationContext|None=None
    replanning_capture_id:uuid.UUID|None=None
    @model_validator(mode='after')
    def validate_input(self):
        if self.horizon_end<=self.horizon_start:raise ValueError('invalid horizon')
        if len(set(self.track_ids))!=len(self.track_ids):raise ValueError('duplicate track')
        return self

def iso(value):return value.isoformat()

def facts(db,body):
    for track in body.track_ids:require_entity(db,track,'track')
    network=[]
    for entity,revision in db.execute(select(NetworkEntity,NetworkRevision).join(NetworkRevision,(NetworkEntity.id==NetworkRevision.entity_id)&(NetworkEntity.revision==NetworkRevision.revision)).order_by(NetworkEntity.kind,NetworkEntity.id)):
        network.append({'id':entity.id,'kind':entity.kind,'revision':entity.revision,'payload':revision.payload})
    requests=[]
    q=select(MaintenanceRequest,RequestRevision).join(RequestRevision,(MaintenanceRequest.id==RequestRevision.request_id)&(MaintenanceRequest.revision==RequestRevision.revision)).where(MaintenanceRequest.status=='PENDING_PLANNING').order_by(MaintenanceRequest.id)
    for request,revision in db.execute(q):
        if set(revision.payload['footprint']).intersection(body.track_ids):requests.append({'id':str(request.id),'revision':request.revision,'status':request.status,'payload':revision.payload})
    occupancy=[]
    effective_runs=effective_versions(db.scalars(select(TrainRun)),lambda r:(r.train_id,r.service_date))
    run_ids={r.id for r in effective_runs}
    # Capture adjacent movements as well: a train outside the horizon can still
    # impose clearance inside it. Sixty minutes is the maximum accepted policy margin.
    q=select(TrainOccupancy,TrainRun,Train).join(TrainRun,TrainRun.id==TrainOccupancy.run_id).join(Train,Train.id==TrainRun.train_id).where(TrainOccupancy.run_id.in_(run_ids),TrainOccupancy.track_id.in_(body.track_ids),TrainOccupancy.exit_at>body.horizon_start-timedelta(minutes=60),TrainOccupancy.enter_at<body.horizon_end+timedelta(minutes=60)).order_by(TrainOccupancy.track_id,TrainOccupancy.enter_at,TrainOccupancy.route_sequence)
    for o,r,t in db.execute(q):occupancy.append({'id':str(o.id),'run_id':str(r.id),'train_id':t.id,'service_date':iso(r.service_date),'track_id':o.track_id,'sequence':o.route_sequence,'enter_at':iso(o.enter_at),'exit_at':iso(o.exit_at),'timing_source':o.timing_source,'source_mode':r.source_mode,'source_revision':r.source_revision})
    coa=[]
    windows=effective_versions(db.scalars(select(CoaWindow)),lambda w:w.external_id)
    for w in sorted(windows,key=lambda w:(w.track_id,w.start_at,w.external_id)):
        if w.track_id not in body.track_ids or w.end_at<=body.horizon_start or w.start_at>=body.horizon_end:continue
        coa.append({'id':str(w.id),'external_id':w.external_id,'source_revision':w.source_revision,'track_id':w.track_id,'start_at':iso(w.start_at),'end_at':iso(w.end_at),'source_mode':w.source_mode,'payload_hash':w.payload_hash})
    freight=[]
    forecasts=effective_versions(db.scalars(select(FreightForecast)),lambda f:f.external_id)
    for f in sorted(forecasts,key=lambda f:(f.track_id,f.start_at,f.external_id)):
        if f.track_id not in body.track_ids or f.end_at<=body.horizon_start or f.start_at>=body.horizon_end:continue
        freight.append({'id':str(f.id),'external_id':f.external_id,'source_revision':f.source_revision,'track_id':f.track_id,'start_at':iso(f.start_at),'end_at':iso(f.end_at),'issued_at':iso(f.issued_at),'expected_count':f.expected_count,'confidence_basis_points':f.confidence_basis_points,'uncertainty_semantics':f.uncertainty_semantics,'source_mode':f.source_mode,'payload_hash':f.payload_hash})
    resources=[]
    profiles={}
    for profile in db.scalars(select(CoordinationRevision).where(CoordinationRevision.kind=='RESOURCE_PROFILE').order_by(CoordinationRevision.revision)):
        profiles[profile.entity_key]={'id':str(profile.id),'revision':profile.revision,'payload':profile.payload}
    for r in db.scalars(select(ResourceUnit).where(ResourceUnit.available_end>body.horizon_start,ResourceUnit.available_start<body.horizon_end).order_by(ResourceUnit.id)):
        resources.append({'id':r.id,'resource_type':r.resource_type,'department':r.department,'available_start':iso(r.available_start),'available_end':iso(r.available_end),'source_mode':r.source_mode})
        resources[-1]['profile']=profiles.get(r.id)
    policies=[]
    if body.coordination_policy_id:
        policy=db.get(CoordinationRevision,body.coordination_policy_id)
        if not policy or policy.kind!='POLICY':raise HTTPException(422,'UNKNOWN_COORDINATION_POLICY')
        policies.append({'id':str(policy.id),'key':policy.entity_key,'revision':policy.revision,'payload':policy.payload})
    missing=[]
    for track in body.track_ids:
        if not any(x['track_id']==track for x in occupancy):missing.append({'track_id':track,'source':'OCCUPANCY'})
        if not any(x['track_id']==track for x in coa):missing.append({'track_id':track,'source':'COA'})
        if body.require_freight_forecast and not any(x['track_id']==track for x in freight):missing.append({'track_id':track,'source':'FREIGHT_FORECAST'})
    if missing:raise HTTPException(422,{'code':'CRITICAL_COVERAGE_UNKNOWN','gaps':missing})
    result={'network':network,'requests':requests,'occupancy':occupancy,'coa':coa,'freight':freight,'resources':resources,'coordination_policies':policies}
    if body.replanning_capture_id:
        # Governance metadata alone cannot repair a disrupted operating dataset.
        if invalidated_facts(db,result):raise HTTPException(409,'INVALIDATED_SOURCE_FACTS_REQUIRE_UPDATE')
        from .replanning_state import attach_capture
        return attach_capture(db,body,result)
    return result

@router.post('/snapshots',status_code=201)
def create_snapshot(body:SnapshotInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    # Authentication has already read from its session. Start a distinct, consistent
    # transaction before the first fact read rather than changing isolation mid-transaction.
    # Acquire the fence before opening the repeatable-read view. Acquiring it
    # inside that view could wait on an event yet retain a pre-event MVCC snapshot.
    lock_publication(db)
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as consistent_db:
            return persist_snapshot(body,user,consistent_db)

def persist_snapshot(body,user,db,commit=True):
    payload=facts(db,body)
    if body.scenario_id is None and invalidated_facts(db,payload):
        raise HTTPException(409,'INVALIDATED_SOURCE_FACTS_REQUIRE_UPDATE')
    if body.validation_context and body.validation_context.facts_hash!=digest(payload):
        raise HTTPException(409,'VALIDATION_CONTEXT_FACTS_CHANGED')
    manifest={'schema_version':1,'horizon_start':iso(body.horizon_start),'horizon_end':iso(body.horizon_end),'track_ids':sorted(body.track_ids),'scenario_id':body.scenario_id,'require_freight_forecast':body.require_freight_forecast,'facts':payload,'counts':{k:len(v) for k,v in payload.items()}}
    if body.validation_context:manifest['validation_context']=body.validation_context.model_dump(mode='json')
    content_hash=digest(manifest)
    existing=db.scalar(select(PlanningSnapshot).where(PlanningSnapshot.content_hash==content_hash))
    if existing:return {'id':str(existing.id),'content_hash':content_hash,'duplicate':True,'counts':existing.manifest['counts']}
    snapshot=PlanningSnapshot(content_hash=content_hash,horizon_start=body.horizon_start,horizon_end=body.horizon_end,scenario_id=body.scenario_id,manifest=manifest);db.add(snapshot);db.flush()
    for kind,values in payload.items():
        for value in values:
            key=value.get('id') or value.get('external_id') or digest(value)
            db.add(SnapshotItem(snapshot_id=snapshot.id,kind=kind,item_key=str(key),payload=value))
    audit(db,user,'SNAPSHOT_CREATED',snapshot.id,{'content_hash':content_hash,'counts':manifest['counts']})
    if commit:db.commit()
    return {'id':str(snapshot.id),'content_hash':content_hash,'duplicate':False,'counts':manifest['counts']}

@router.get('/snapshots/{id}')
def read_snapshot(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    snapshot=db.get(PlanningSnapshot,id)
    if not snapshot:raise HTTPException(404,'SNAPSHOT_NOT_FOUND')
    return {'id':str(snapshot.id),'content_hash':snapshot.content_hash,'created_at':iso(snapshot.created_at),'facts_hash':digest(snapshot.manifest['facts']),'manifest':snapshot.manifest}
