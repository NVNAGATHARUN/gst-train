import uuid
from datetime import datetime,timezone,timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import AwareDatetime,Field,model_validator
from sqlalchemy import select,or_,and_
from .auth import current_user,require
from .db import session_dependency,Session
from .models import ResourceUnit,PlanningRun,PlanningSnapshot,AuditEvent
from .requests import StrictModel,audit
from .requests import digest
from .models import CoordinationComputation,OpportunityComputation,PriorityAssessment,WorkerLease,AvailabilityComputation
from .solver import SolverOptions,solve,first_feasible
from .intervals import intersect,merge,subtract,common_windows
from .staleness import lock_publication,invalidation_ids
from .freeze_state import execution_pending

router=APIRouter(prefix='/api/v1')

class ResourceInput(StrictModel):
    id:str=Field(min_length=1,max_length=100)
    resource_type:str=Field(min_length=1,max_length=60)
    department:Literal['ENGINEERING','TRD','SNT']|None=None
    available_start:AwareDatetime
    available_end:AwareDatetime
    source_mode:Literal['SIMULATED','IMPORTED']='SIMULATED'
    @model_validator(mode='after')
    def times(self):
        if self.available_end<=self.available_start:raise ValueError('invalid availability')
        return self

@router.post('/resources',status_code=201)
def create_resource(body:ResourceInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    if db.get(ResourceUnit,body.id):raise HTTPException(409,'RESOURCE_EXISTS')
    row=ResourceUnit(**body.model_dump());db.add(row);audit(db,user,'RESOURCE_CREATED',row.id,{'source_mode':body.source_mode});db.commit()
    return body.model_dump(mode='json')

@router.get('/resources')
def list_resources(limit:int=Query(100,ge=1,le=200),offset:int=Query(0,ge=0),
        user=Depends(require('ADMIN','PLANNER','CONTROLLER','AUDITOR')),db=Depends(session_dependency)):
    rows=db.scalars(select(ResourceUnit).order_by(ResourceUnit.id).offset(offset).limit(limit)).all()
    return {'items':[{'id':row.id,'resource_type':row.resource_type,'department':row.department,
        'available_start':row.available_start.isoformat(),'available_end':row.available_end.isoformat(),
        'source_mode':row.source_mode} for row in rows],
        'next_offset':offset+limit if len(rows)==limit else None}

class RunInput(StrictModel):
    snapshot_id:uuid.UUID
    planner_type:Literal['BASELINE','CP_SAT']='BASELINE'
    coordination_id:uuid.UUID|None=None
    solver_options:SolverOptions=Field(default_factory=SolverOptions)
    clearance_minutes:int=Field(default=5,ge=0,le=60)
    protect_freight_envelope:bool=True
    @model_validator(mode='after')
    def coordinated_solver(self):
        if self.planner_type=='CP_SAT' and not self.coordination_id:raise ValueError('CP_SAT requires coordinated candidates')
        return self

@router.post('/planning-runs',status_code=202)
def create_run(body:RunInput,user=Depends(require('ADMIN','PLANNER')),db=Depends(session_dependency)):
    lock_publication(db)
    snapshot=db.get(PlanningSnapshot,body.snapshot_id)
    if not snapshot:raise HTTPException(422,'UNKNOWN_SNAPSHOT')
    if invalidation_ids(db,body.snapshot_id):raise HTTPException(409,'SNAPSHOT_INVALIDATED_BY_EVENT')
    if execution_pending(db,snapshot):raise HTTPException(409,'EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    if not scenario_current(db,snapshot):raise HTTPException(409,'SCENARIO_SOURCE_STALE')
    if body.coordination_id:
        coordination=db.get(CoordinationComputation,body.coordination_id)
        if not coordination or coordination.snapshot_id!=body.snapshot_id:raise HTTPException(422,'COORDINATION_SNAPSHOT_MISMATCH')
        if coordination.result['status']=='BLOCKED':raise HTTPException(409,'COORDINATION_BLOCKED')
        opportunity=db.get(OpportunityComputation,coordination.opportunity_id)
        for id in opportunity.configuration['availability_ids']:
            policy=db.get(AvailabilityComputation,uuid.UUID(id)).policy
            if policy['clearance_before_minutes']!=body.clearance_minutes or policy['clearance_after_minutes']!=body.clearance_minutes or policy['protect_freight_envelope']!=body.protect_freight_envelope:
                raise HTTPException(422,'TRAFFIC_POLICY_MISMATCH')
    row=PlanningRun(snapshot_id=body.snapshot_id,planner_type=body.planner_type,status='QUEUED',config=body.model_dump(mode='json'));db.add(row);db.flush();audit(db,user,'PLANNING_RUN_QUEUED',row.id);db.commit()
    return {'id':str(row.id),'status':'QUEUED'}

@router.get('/planning-runs/{id}')
def read_run(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(PlanningRun,id)
    if not row:raise HTTPException(404,'RUN_NOT_FOUND')
    return {'id':str(row.id),'snapshot_id':str(row.snapshot_id),'planner_type':row.planner_type,'status':row.status,'config':row.config,
        'result':row.result,'result_hash':digest(row.result) if row.result is not None else None}

def parse(value):return datetime.fromisoformat(value)
def scenario_current(db,snapshot):
    if not snapshot.scenario_id:return True
    from .validation import current_hash
    return current_hash(db,snapshot)==digest(snapshot.manifest['facts'])
def baseline(snapshot,config,resources):
    manifest=snapshot.manifest;facts=manifest['facts'];clearance=timedelta(minutes=config['clearance_minutes'])
    horizon=(parse(manifest['horizon_start']),parse(manifest['horizon_end']))
    requests=sorted(facts['requests'],key=lambda r:(not r['payload']['mandatory'],parse(r['payload']['deadline_at']),r['id']))
    selected=[];deferred=[];track_bookings={};resource_bookings={r['id']:[] for r in resources}
    for request in requests:
        data=request['payload'];duration=timedelta(minutes=data['setup_minutes']+data['work_minutes']+data['restore_minutes'])
        windows_by_track=[]
        for track in data['footprint']:
            allowed=[]
            for w in facts['coa']:
                if w['track_id']==track:
                    x=intersect((parse(w['start_at']),parse(w['end_at'])),horizon)
                    if x:allowed.append(x)
            blocked=[(parse(o['enter_at'])-clearance,parse(o['exit_at'])+clearance) for o in facts['occupancy'] if o['track_id']==track]
            if config['protect_freight_envelope']:blocked += [(parse(f['start_at']),parse(f['end_at'])) for f in facts['freight'] if f['track_id']==track]
            blocked += track_bookings.get(track,[])
            windows_by_track.append(subtract(merge(allowed),blocked))
        windows=common_windows(windows_by_track) if windows_by_track else []
        earliest=parse(data['earliest_at']);deadline=parse(data['deadline_at']);chosen=None
        for start,end in windows:
            start=max(start,earliest);finish=start+duration
            deadline_finish=finish if data['deadline_kind']=='RESTORED_BY' else start+timedelta(minutes=data['setup_minutes']+data['work_minutes'])
            if finish>end or deadline_finish>deadline:continue
            assignments=[];unavailable=False
            for requirement in data['requirements']:
                eligible=[]
                for resource in resources:
                    if resource['resource_type']!=requirement['type'] or resource['department'] not in (None,data['department']):continue
                    if parse(resource['available_start'])>start or parse(resource['available_end'])<finish:continue
                    if any(intersect((start,finish),x) for x in resource_bookings[resource['id']]):continue
                    eligible.append(resource['id'])
                if len(eligible)<requirement['quantity']:unavailable=True;break
                assignments += eligible[:requirement['quantity']]
            if not unavailable:chosen=(start,finish,assignments);break
        if not chosen:
            deferred.append({'request_id':request['id'],'reason':'NO_FEASIBLE_WINDOW_OR_RESOURCE','mandatory':data['mandatory']});continue
        start,finish,assignments=chosen
        for track in data['footprint']:track_bookings.setdefault(track,[]).append((start,finish))
        for resource in assignments:resource_bookings[resource].append((start,finish))
        selected.append({'request_id':request['id'],'request_revision':request['revision'],'possession_start':start.isoformat(),'work_start':(start+timedelta(minutes=data['setup_minutes'])).isoformat(),'work_end':(start+timedelta(minutes=data['setup_minutes']+data['work_minutes'])).isoformat(),'possession_end':finish.isoformat(),'track_ids':data['footprint'],'resource_ids':assignments})
    mandatory_failed=any(x['mandatory'] for x in deferred)
    return {'planner':'FIRST_FEASIBLE_BASELINE','snapshot_hash':snapshot.content_hash,'schedule_status':'NON_APPROVABLE' if mandatory_failed else 'DEVELOPMENT_ARTIFACT','assignments':selected,'deferred':deferred,'counts':{'scheduled':len(selected),'deferred':len(deferred)},'policy':{'fixed_trains':True,'freight_envelope_protected':config['protect_freight_envelope'],'clearance_minutes':config['clearance_minutes'],'bundling':False}}

def claim_run():
    with Session.begin() as db:
        now=datetime.now(timezone.utc)
        row=db.scalar(select(PlanningRun).outerjoin(WorkerLease,WorkerLease.run_id==PlanningRun.id).where(
            or_(PlanningRun.status=='QUEUED',and_(PlanningRun.status=='RUNNING',or_(WorkerLease.run_id==None,WorkerLease.expires_at<=now)))
        ).order_by(PlanningRun.created_at).with_for_update(skip_locked=True,of=PlanningRun).limit(1))
        if not row:return None
        row.status='RUNNING'
        token=uuid.uuid4()
        lease=db.get(WorkerLease,row.id)
        duration=row.config.get('solver_options',{}).get('max_time_seconds',10)+300
        if lease:lease.token=token;lease.expires_at=now+timedelta(seconds=duration)
        else:db.add(WorkerLease(run_id=row.id,token=token,expires_at=now+timedelta(seconds=duration)))
        return row.id,token

def publish_run(run_id,token,result,error=False):
    with Session.begin() as db:
        lock_publication(db)
        row=db.scalar(select(PlanningRun).where(PlanningRun.id==run_id).with_for_update())
        lease=db.get(WorkerLease,run_id)
        if not row or row.status!='RUNNING' or not lease or lease.token!=token or lease.expires_at<=datetime.now(timezone.utc):return False
        snapshot=db.get(PlanningSnapshot,row.snapshot_id)
        if invalidation_ids(db,row.snapshot_id) or execution_pending(db,snapshot) or not scenario_current(db,snapshot):
            row.status='SUPERSEDED'
            return False
        row.result=result
        row.status='FAILED' if error else 'COMPLETED'
        row.completed_at=datetime.now(timezone.utc)
        db.add(AuditEvent(actor='WORKER',action='PLANNING_RUN_'+row.status,entity=str(row.id),
                         data={'status':result.get('schedule_status'),'counts':result.get('counts',{})}))
        return True

def execute_run(run_id):
    # Read frozen inputs, then release the DB transaction before expensive solving.
    with Session() as db:
        row=db.get(PlanningRun,run_id)
        if invalidation_ids(db,row.snapshot_id):raise ValueError('SNAPSHOT_INVALIDATED_BY_EVENT')
        snapshot=db.get(PlanningSnapshot,row.snapshot_id)
        if execution_pending(db,snapshot):raise ValueError('EXECUTION_AWARE_SNAPSHOT_REQUIRED')
        if not scenario_current(db,snapshot):raise ValueError('SCENARIO_SOURCE_STALE')
        if digest(snapshot.manifest)!=snapshot.content_hash:raise ValueError('SNAPSHOT_HASH_MISMATCH')
        config=row.config
        if not config.get('coordination_id'):
            result=baseline(snapshot,config,snapshot.manifest['facts'].get('resources',[]))
            result['comparison_eligible']=False
            result['limitation']='LEGACY_BASIC_BASELINE; use coordinated candidates for fair complete-constraint comparison'
            return result
        coordination=db.get(CoordinationComputation,uuid.UUID(config['coordination_id']))
        if not coordination or coordination.snapshot_id!=snapshot.id:raise ValueError('COORDINATION_SNAPSHOT_MISMATCH')
        if coordination.result['snapshot_hash']!=snapshot.content_hash:raise ValueError('COORDINATION_HASH_MISMATCH')
        opportunity=db.get(OpportunityComputation,coordination.opportunity_id)
        priorities={str(p.request_id):p.score_basis_points for p in db.scalars(select(PriorityAssessment).where(
            PriorityAssessment.snapshot_id==snapshot.id,
            PriorityAssessment.policy_version==opportunity.configuration['priority_policy_version'],
            PriorityAssessment.assessed_at==parse(opportunity.configuration['assessed_at'])))}
        manifest=snapshot.manifest
        coordinated=coordination.result
        planner=row.planner_type
        coordination_hash=coordination.input_hash
        snapshot_hash=snapshot.content_hash
    function=solve if planner=='CP_SAT' else first_feasible
    result=function(manifest,coordinated,priorities,config['solver_options'])
    result.update({'snapshot_hash':snapshot_hash,'coordination_hash':coordination_hash,'comparison_eligible':True,
                   'requirements_hash':digest(manifest['facts']['requests']),'priorities_hash':digest(priorities)})
    return result

def run_one():
    claimed=claim_run()
    if not claimed:return None
    run_id,token=claimed
    try:
        result=execute_run(run_id)
        publish_run(run_id,token,result)
        return run_id
    except Exception as error:
        publish_run(run_id,token,{'schedule_status':'ERROR','solver_status':None,'error':type(error).__name__,
            'detail':str(error) if isinstance(error,ValueError) else 'Worker failed; inspect server logs',
            'assignments':[],'review_blockers':['WORKER_ERROR']},error=True)
        return run_id
