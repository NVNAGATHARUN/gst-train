import uuid,math
from datetime import datetime,timedelta
from fastapi import APIRouter,Depends,HTTPException
from pydantic import AwareDatetime,Field
from sqlalchemy import select
from .auth import current_user,require
from .db import session_dependency
from .models import PlanningSnapshot,AvailabilityComputation,PriorityAssessment,OpportunityComputation
from .requests import StrictModel,digest,audit

router=APIRouter(prefix='/api/v1')

class OpportunityInput(StrictModel):
    snapshot_id:uuid.UUID
    availability_ids:list[uuid.UUID]=Field(min_length=1,max_length=100)
    assessed_at:AwareDatetime
    priority_policy_version:str='RULE_PRIORITY_V1'
    start_grid_minutes:int=Field(default=15,ge=1,le=120)
    max_candidates_per_request:int=Field(default=200,ge=1,le=5000)

def parse(value):return datetime.fromisoformat(value)
def grid_starts(first,last,step):
    if first>last:return []
    starts=[first];candidate=first+timedelta(minutes=step)
    while candidate<last:starts.append(candidate);candidate+=timedelta(minutes=step)
    if last!=starts[-1]:starts.append(last)
    return starts

def generate(snapshot,availability,assessments,config):
    by_footprint={tuple(sorted(x.policy['track_ids'])):x.result['windows'] for x in availability}
    scores={str(x.request_id):x for x in assessments};candidates=[];exclusions=[];before_cap=0
    captures=snapshot.manifest['facts'].get('replanning',[])
    cutoff=parse(captures[0]['payload']['captured_at']) if captures else None
    for request in snapshot.manifest['facts']['requests']:
        data=request['payload'];footprint=tuple(sorted(data['footprint']));windows=by_footprint.get(footprint)
        if windows is None:
            exclusions.append({'request_id':request['id'],'code':'CAPACITY_NOT_COMPUTED'});continue
        assessment=scores.get(request['id'])
        if not assessment:
            exclusions.append({'request_id':request['id'],'code':'PRIORITY_NOT_ASSESSED'});continue
        possession_minutes=data['setup_minutes']+data['work_minutes']+data['restore_minutes'];earliest=parse(data['earliest_at']);deadline=parse(data['deadline_at'])
        possible=[];saw_duration=False;saw_deadline=False
        for window in windows:
            wstart=parse(window['start_at']);wend=parse(window['end_at'])
            # earliest_at constrains work, so setup may begin before it.
            origin=parse(snapshot.manifest['horizon_start'])
            first=max(wstart,earliest-timedelta(minutes=data['setup_minutes']))
            if cutoff is not None:first=max(first,cutoff)
            first=origin+timedelta(minutes=math.ceil((first-origin).total_seconds()/60))
            last=wend-timedelta(minutes=possession_minutes)
            if first>last:continue
            saw_duration=True
            for start in grid_starts(first,last,config['start_grid_minutes']):
                work_start=start+timedelta(minutes=data['setup_minutes']);work_end=work_start+timedelta(minutes=data['work_minutes']);end=work_end+timedelta(minutes=data['restore_minutes'])
                deadline_point=end if data['deadline_kind']=='RESTORED_BY' else work_end
                if deadline_point>deadline:saw_deadline=True;continue
                from .availability import latest
                exposure=sum(max(0,int((min(end,parse(f['end_at']))-max(start,parse(f['start_at']))).total_seconds()))*f['expected_count'] for f in latest(snapshot.manifest['facts']['freight']) if f['track_id'] in footprint)
                raw={'request_id':request['id'],'request_revision':request['revision'],'window_id':window['id'],'track_ids':list(footprint),'possession_start':start.isoformat(),'work_start':work_start.isoformat(),'work_end':work_end.isoformat(),'possession_end':end.isoformat(),'resource_requirements':data['requirements'],'priority_basis_points':assessment.score_basis_points,'costs':{'reserved_track_minutes':possession_minutes*len(footprint),'forecast_exposure':exposure,'setup_minutes':data['setup_minutes'],'restoration_minutes':data['restore_minutes']},'forecast_exposure_unit':'expected_train_track_seconds'}
                possible.append({'id':digest(raw)[:24],**raw})
        before_cap+=len(possible)
        if not possible:
            exclusions.append({'request_id':request['id'],'code':'DEADLINE_EXCLUDED' if saw_duration and saw_deadline else 'WINDOW_TOO_SHORT'});continue
        possible.sort(key=lambda c:(c['possession_start'],c['id']))
        if len(possible)>config['max_candidates_per_request']:
            exclusions.append({'request_id':request['id'],'code':'SEARCH_LIMIT_REACHED','generated':len(possible),'retained':config['max_candidates_per_request']})
            possible=possible[:config['max_candidates_per_request']]
        candidates+=possible
    return {'candidates':candidates,'exclusions':exclusions,'search':{'grid_minutes':config['start_grid_minutes'],'max_candidates_per_request':config['max_candidates_per_request'],'before_cap':before_cap,'retained':len(candidates),'optimality_scope':'generated_candidate_set'},'counts':{'candidates':len(candidates),'excluded_requests':len({x['request_id'] for x in exclusions})}}

def serialize(row,duplicate=False):return {'id':str(row.id),'snapshot_id':str(row.snapshot_id),'input_hash':row.input_hash,'duplicate':duplicate,'result':row.result}

@router.post('/maintenance-opportunities',status_code=201)
def calculate(body:OpportunityInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    snapshot=db.get(PlanningSnapshot,body.snapshot_id)
    if not snapshot:raise HTTPException(422,'UNKNOWN_SNAPSHOT')
    availability=[]
    for id in body.availability_ids:
        row=db.get(AvailabilityComputation,id)
        if not row or row.snapshot_id!=snapshot.id:raise HTTPException(422,'AVAILABILITY_SNAPSHOT_MISMATCH')
        availability.append(row)
    assessments=db.scalars(select(PriorityAssessment).where(PriorityAssessment.snapshot_id==snapshot.id,PriorityAssessment.policy_version==body.priority_policy_version,PriorityAssessment.assessed_at==body.assessed_at)).all()
    config=body.model_dump(mode='json');input_hash=digest({'snapshot_hash':snapshot.content_hash,'availability_hashes':sorted(x.input_hash for x in availability),'config':config})
    existing=db.scalar(select(OpportunityComputation).where(OpportunityComputation.input_hash==input_hash))
    if existing:return serialize(existing,True)
    result=generate(snapshot,availability,assessments,config);row=OpportunityComputation(snapshot_id=snapshot.id,input_hash=input_hash,configuration=config,result=result);db.add(row);db.flush();audit(db,user,'OPPORTUNITIES_COMPUTED',row.id,result['counts']);db.commit();return serialize(row)

@router.get('/maintenance-opportunities/{id}')
def read(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(OpportunityComputation,id)
    if not row:raise HTTPException(404,'OPPORTUNITY_COMPUTATION_NOT_FOUND')
    return serialize(row)
