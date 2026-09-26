import uuid,math
from datetime import datetime,timedelta
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select
from .auth import current_user,require
from .db import session_dependency
from .models import PlanningSnapshot,AvailabilityComputation
from .requests import StrictModel,digest,audit
from .intervals import merge,subtract,common_windows,intersect,minute

router=APIRouter(prefix='/api/v1')

class AvailabilityInput(StrictModel):
    snapshot_id:uuid.UUID
    track_ids:list[str]=Field(min_length=1,max_length=100)
    clearance_before_minutes:int=Field(default=5,ge=0,le=60)
    clearance_after_minutes:int=Field(default=5,ge=0,le=60)
    minimum_useful_minutes:int=Field(default=1,ge=1,le=10080)
    protect_freight_envelope:bool=True

def latest(records):
    chosen={}
    for row in records:
        key=(row['external_id'],row['track_id'])
        if key not in chosen or row['source_revision']>chosen[key]['source_revision']:chosen[key]=row
    return list(chosen.values())

def compute_availability(manifest,policy):
    facts=manifest['facts'];horizon_start=datetime.fromisoformat(manifest['horizon_start']);horizon_end=datetime.fromisoformat(manifest['horizon_end'])
    horizon_minutes=math.floor((horizon_end-horizon_start).total_seconds()/60)
    tracks=sorted(policy['track_ids']);windows_by_track=[];conflicts=[];excluded=[]
    current_coa=latest(facts['coa']);current_freight=latest(facts['freight'])
    restrictions=[n for n in facts['network'] if n['kind']=='restriction']
    for track in tracks:
        allowed=[]
        for window in current_coa:
            if window['track_id']!=track:continue
            start=max(0,minute(datetime.fromisoformat(window['start_at']),horizon_start,'ceil'))
            end=min(horizon_minutes,minute(datetime.fromisoformat(window['end_at']),horizon_start,'floor'))
            if start<end:allowed.append((start,end))
        blocked=[]
        for occupancy in facts['occupancy']:
            if occupancy['track_id']!=track:continue
            start=max(0,minute(datetime.fromisoformat(occupancy['enter_at']),horizon_start,'floor')-policy['clearance_before_minutes'])
            end=min(horizon_minutes,minute(datetime.fromisoformat(occupancy['exit_at']),horizon_start,'ceil')+policy['clearance_after_minutes'])
            if start<end:
                blocked.append((start,end,'CONFIRMED_OCCUPANCY',occupancy['id']))
                if any(intersect((start,end),window) for window in allowed):conflicts.append({'track_id':track,'code':'COA_OCCUPANCY_CONFLICT','evidence_id':occupancy['id']})
        if policy['protect_freight_envelope']:
            for forecast in current_freight:
                if forecast['track_id']!=track:continue
                start=max(0,minute(datetime.fromisoformat(forecast['start_at']),horizon_start,'floor'));end=min(horizon_minutes,minute(datetime.fromisoformat(forecast['end_at']),horizon_start,'ceil'))
                if start<end:blocked.append((start,end,'FREIGHT_ENVELOPE',forecast['id']))
        for restriction in restrictions:
            p=restriction['payload']
            if track not in p['footprint']:continue
            start=max(0,minute(datetime.fromisoformat(p['start']),horizon_start,'floor'));end=min(horizon_minutes,minute(datetime.fromisoformat(p['end']),horizon_start,'ceil'))
            if start<end:blocked.append((start,end,'RESTRICTION',restriction['id']))
        for release in facts.get('released_possessions',[]):
            if track not in release['result']['assignment']['track_ids']:continue
            p=release['payload']
            start=max(0,minute(datetime.fromisoformat(p['actual_possession_start']),horizon_start,'floor'))
            end=min(horizon_minutes,minute(datetime.fromisoformat(p['restored_at']),horizon_start,'ceil'))
            if start<end:blocked.append((start,end,'RECORDED_POSSESSION_HISTORY',release['id']))
        free=subtract(merge(allowed),[(x[0],x[1]) for x in blocked])
        kept=[]
        for start,end in free:
            if end-start<policy['minimum_useful_minutes']:excluded.append({'track_id':track,'start_minute':start,'end_minute':end,'code':'BELOW_MINIMUM_USEFUL_DURATION'})
            else:kept.append((start,end))
        windows_by_track.append(kept)
    shared=[]
    for start,end in common_windows(windows_by_track):
        if end-start<policy['minimum_useful_minutes']:excluded.append({'track_ids':tracks,'start_minute':start,'end_minute':end,'code':'BELOW_SHARED_MINIMUM_USEFUL_DURATION'})
        else:shared.append((start,end))
    output=[]
    for start,end in shared:
        start_at=horizon_start+timedelta(minutes=start);end_at=horizon_start+timedelta(minutes=end)
        raw={'track_ids':tracks,'start_at':start_at.isoformat(),'end_at':end_at.isoformat(),'usable_minutes':end-start}
        output.append({'id':digest(raw)[:24],**raw})
    return {'windows':output,'source_conflicts':conflicts,'excluded':excluded,'policy':policy,'rounding':{'allowed':'inward','blocked':'outward','intervals':'half-open'},'counts':{'windows':len(output),'conflicts':len(conflicts),'excluded':len(excluded)}}

def serialize(row,duplicate=False):return {'id':str(row.id),'snapshot_id':str(row.snapshot_id),'input_hash':row.input_hash,'duplicate':duplicate,'result':row.result}

@router.post('/corridor-availability',status_code=201)
def calculate(body:AvailabilityInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    snapshot=db.get(PlanningSnapshot,body.snapshot_id)
    if not snapshot:raise HTTPException(422,'UNKNOWN_SNAPSHOT')
    if not set(body.track_ids).issubset(snapshot.manifest['track_ids']):raise HTTPException(422,'TRACK_OUTSIDE_SNAPSHOT')
    policy=body.model_dump(mode='json');input_hash=digest({'snapshot_hash':snapshot.content_hash,'policy':policy})
    existing=db.scalar(select(AvailabilityComputation).where(AvailabilityComputation.input_hash==input_hash))
    if existing:return serialize(existing,True)
    result=compute_availability(snapshot.manifest,policy);row=AvailabilityComputation(snapshot_id=snapshot.id,input_hash=input_hash,policy=policy,result=result);db.add(row);db.flush();audit(db,user,'AVAILABILITY_COMPUTED',row.id,result['counts']);db.commit();return serialize(row)

@router.get('/corridor-availability/{id}')
def read(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(AvailabilityComputation,id)
    if not row:raise HTTPException(404,'AVAILABILITY_NOT_FOUND')
    return serialize(row)
