"""M14 immutable weekly/monthly views and reproducible exports."""
import csv
import io
import json
import uuid
from datetime import date,datetime,time,timedelta,timezone
from typing import Literal
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from pydantic import Field,model_validator
from sqlalchemy import select
from .auth import current_user,require
from .db import session_dependency
from .models import (PlanningSchedule,PlanRevision,PlanningSnapshot,ValidationReport,
    ControllerDecision,PlanReservation)
from .requests import StrictModel,audit,digest
from .validation import usability,utc_now

router=APIRouter(prefix='/api/v1')
AUTHORITY='SOFTWARE_PROPOSAL_ONLY'

class ScheduleInput(StrictModel):
    plan_revision_id:uuid.UUID
    schedule_type:Literal['WEEKLY','MONTHLY']
    timezone_name:str=Field(default='Asia/Kolkata',min_length=1,max_length=80)
    week_start:date|None=None
    year:int|None=Field(default=None,ge=2000,le=2200)
    month:int|None=Field(default=None,ge=1,le=12)
    @model_validator(mode='after')
    def period_fields(self):
        if self.schedule_type=='WEEKLY' and (not self.week_start or self.year is not None or self.month is not None):
            raise ValueError('WEEKLY requires only week_start')
        if self.schedule_type=='MONTHLY' and (self.week_start or self.year is None or self.month is None):
            raise ValueError('MONTHLY requires only year and month')
        return self

def local_period(schedule_type,timezone_name,week_start=None,year=None,month=None):
    try:zone=ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:raise HTTPException(422,'UNKNOWN_TIMEZONE')
    if schedule_type=='WEEKLY':
        start_date=week_start;end_date=week_start+timedelta(days=7)
    else:
        start_date=date(year,month,1)
        end_date=date(year+1,1,1) if month==12 else date(year,month+1,1)
    start=datetime.combine(start_date,time.min,zone);end=datetime.combine(end_date,time.min,zone)
    return start,end,start_date,end_date

def iso(value):return value.isoformat()

def merged_coverage(rows):
    rows=sorted((datetime.fromisoformat(x['start_at']),datetime.fromisoformat(x['end_at'])) for x in rows if x.get('complete'))
    merged=[]
    for begin,end in rows:
        if not merged or begin>merged[-1][1]:merged.append([begin,end])
        else:merged[-1][1]=max(merged[-1][1],end)
    return merged

def covers(rows,start,end):return any(a<=start and end<=b for a,b in merged_coverage(rows))

def status_context(db,revision,snapshot,now):
    reports=db.scalars(select(ValidationReport).where(ValidationReport.plan_revision_id==revision.id)
        .order_by(ValidationReport.checked_at.desc())).all()
    report=reports[0] if reports else None
    usable,blockers=usability(db,report,now) if report else (False,['VALIDATION_REPORT_MISSING'])
    decisions=db.scalars(select(ControllerDecision).where(ControllerDecision.plan_revision_id==revision.id)
        .order_by(ControllerDecision.created_at.desc())).all()
    decision=decisions[0] if decisions else None
    active=[]
    if decision and decision.action=='APPROVE':
        active=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==decision.id,PlanReservation.active.is_(True))).all()
    assignments=revision.content.get('assignments',[])
    if decision and decision.action=='REJECT':status='REJECTED_PROPOSAL'
    elif decision and decision.action=='APPROVE' and assignments and not active:status='SUPERSEDED_PROPOSAL'
    elif decision and decision.action=='APPROVE' and usable:status='APPROVED_PROPOSAL'
    elif decision and decision.action=='APPROVE':status='STALE_APPROVED_PROPOSAL'
    elif report and report.status=='PASS' and usable:status='VALIDATED_TENTATIVE_PROPOSAL'
    elif report and report.status!='PASS':status='INVALID_PROPOSAL'
    else:status='TENTATIVE_PROPOSAL'
    return report,decision,active,usable,blockers,status

def reservation_matches(block,row):
    resources=sorted({a['resource_id'] for a in block.get('allocations',[])})
    return (datetime.fromisoformat(block['possession_start'])==row.start_at and
        datetime.fromisoformat(block['possession_end'])==row.end_at and
        sorted(block['track_ids'])==sorted(row.track_ids) and resources==sorted(row.resource_ids))

def schedule_content(db,revision,snapshot,schedule_type,timezone_name,start,end,start_date,end_date,now):
    if digest(revision.content)!=revision.plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    if digest(snapshot.manifest)!=snapshot.content_hash or revision.snapshot_hash!=snapshot.content_hash:
        raise HTTPException(409,'SNAPSHOT_HASH_MISMATCH')
    if snapshot.horizon_start>start or snapshot.horizon_end<end:raise HTTPException(409,'PLAN_HORIZON_DOES_NOT_COVER_PERIOD')
    report,decision,reservations,usable,blockers,status=status_context(db,revision,snapshot,now)
    context=snapshot.manifest.get('validation_context') or {}
    declarations=context.get('coverage',[])
    assignments=[]
    for block in revision.content.get('assignments',[]):
        begin=datetime.fromisoformat(block['possession_start']);finish=datetime.fromisoformat(block['possession_end'])
        if not start<=begin<finish<=end:raise HTTPException(409,'ASSIGNMENT_OUTSIDE_SCHEDULE_PERIOD')
        firm=next((r for r in reservations if reservation_matches(block,r)),None)
        forecast_rows=[x for x in declarations if x.get('source')=='FREIGHT' and x.get('track_id') in block['track_ids']]
        forecast_complete=all(covers([x for x in forecast_rows if x.get('track_id')==track],begin,finish) for track in block['track_ids'])
        assignments.append({**block,
            'commitment_status':('FIRM' if firm and usable else 'REQUIRES_ATTENTION' if firm else 'TENTATIVE'),
            'reservation_scope':firm.scope if firm else None,
            'forecast_coverage_status':'DECLARED_COMPLETE' if forecast_complete else 'UNKNOWN_OR_INCOMPLETE'})
    valid_until=context.get('valid_until')
    payload={'schema_version':1,'schedule_type':schedule_type,'timezone':timezone_name,
        'period':{'local_start':start_date.isoformat(),'local_end_exclusive':end_date.isoformat(),
            'start_at':iso(start),'end_at':iso(end),
            'duration_minutes':int((end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds()/60),
            'calendar_days':(end_date-start_date).days},
        'status':status,'authority':AUTHORITY,'plan_revision':{'id':str(revision.id),'revision':revision.revision,
            'plan_hash':revision.plan_hash,'snapshot_hash':revision.snapshot_hash},
        'validation':{'report_id':str(report.id) if report else None,'status':report.status if report else 'NOT_RUN',
            'currently_usable':usable,'blockers':blockers},
        'controller_decision':{'id':str(decision.id),'action':decision.action,'scope':decision.scope} if decision else None,
        'uncertainty':{'data_valid_until':valid_until,'freight_coverage_declared_until_by_track':{
            track:max((x['end_at'] for x in declarations if x.get('source')=='FREIGHT' and x.get('track_id')==track and x.get('complete')),default=None)
            for track in snapshot.manifest['track_ids']}},
        'assignments':assignments,'deferred':copy_json(revision.content.get('deferred',[])),
        'planner_evidence':{'planner':revision.content.get('planner'),'solver_status':revision.content.get('solver_status'),
            'optimality_scope':revision.content.get('optimality_scope'),'candidate_search':revision.content.get('candidate_search')},
        'counts':{'assignments':len(assignments),'tasks':sum(len(x.get('tasks',[])) for x in assignments),
            'firm':sum(x['commitment_status']=='FIRM' for x in assignments),
            'tentative':sum(x['commitment_status']=='TENTATIVE' for x in assignments),
            'requires_attention':sum(x['commitment_status']=='REQUIRES_ATTENTION' for x in assignments),
            'deferred':len(revision.content.get('deferred',[]))},
        'generated_at':iso(now),'planning_method':'SINGLE_CANONICAL_PLAN'}
    return payload

def copy_json(value):return json.loads(json.dumps(value))

def schedule_json(row,duplicate=False):
    return {'id':str(row.id),'plan_revision_id':str(row.plan_revision_id),'schedule_type':row.schedule_type,
        'timezone':row.timezone_name,'period_start':iso(row.period_start),'period_end':iso(row.period_end),
        'content_hash':row.content_hash,'content':row.content,'created_at':iso(row.created_at),'duplicate':duplicate}

@router.post('/planning-schedules',status_code=201)
def create_schedule(body:ScheduleInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    revision=db.get(PlanRevision,body.plan_revision_id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id)
    start,end,start_date,end_date=local_period(body.schedule_type,body.timezone_name,body.week_start,body.year,body.month)
    payload=schedule_content(db,revision,snapshot,body.schedule_type,body.timezone_name,start,end,start_date,end_date,now)
    content_hash=digest(payload)
    existing=db.scalar(select(PlanningSchedule).where(PlanningSchedule.content_hash==content_hash))
    if existing:return schedule_json(existing,True)
    row=PlanningSchedule(plan_revision_id=revision.id,schedule_type=body.schedule_type,timezone_name=body.timezone_name,
        period_start=start,period_end=end,content_hash=content_hash,content=payload,created_by=str(user.id),created_at=now)
    db.add(row);db.flush();audit(db,user,'PLANNING_SCHEDULE_CREATED',row.id,{'type':body.schedule_type,
        'content_hash':content_hash,'plan_hash':revision.plan_hash,'status':payload['status']});db.commit()
    return schedule_json(row)

@router.get('/planning-schedules/{id}')
def read_schedule(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(PlanningSchedule,id)
    if not row:raise HTTPException(404,'PLANNING_SCHEDULE_NOT_FOUND')
    return schedule_json(row)

def safe_cell(value):
    text_value='' if value is None else str(value)
    return "'"+text_value if text_value.startswith(('=','+','-','@')) else text_value

def csv_export(content):
    columns=['record_type','schedule_type','schedule_status','plan_revision_id','plan_hash','snapshot_hash',
        'candidate_id','request_id','department','issue_type','possession_start','setup_start','work_start','work_end',
        'restore_end','possession_end','track_ids','resource_ids','commitment_status','reservation_scope',
        'forecast_coverage_status','deferred_reason','authority']
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=columns,lineterminator='\n');writer.writeheader()
    common={'schedule_type':content['schedule_type'],'schedule_status':content['status'],
        'plan_revision_id':content['plan_revision']['id'],'plan_hash':content['plan_revision']['plan_hash'],
        'snapshot_hash':content['plan_revision']['snapshot_hash'],'authority':content['authority']}
    for block in sorted(content['assignments'],key=lambda x:(x['possession_start'],x['id'])):
        for task in sorted(block['tasks'],key=lambda x:(x['setup_start'],x['request_id'])):
            resources=sorted(a['resource_id'] for a in block.get('allocations',[]) if a['request_id']==task['request_id'])
            row={**common,'record_type':'ASSIGNMENT','candidate_id':block['id'],'request_id':task['request_id'],
                'department':task['department'],'issue_type':task['issue_type'],'possession_start':block['possession_start'],
                'setup_start':task['setup_start'],'work_start':task['work_start'],'work_end':task['work_end'],
                'restore_end':task['restore_end'],'possession_end':block['possession_end'],
                'track_ids':'|'.join(sorted(block['track_ids'])),'resource_ids':'|'.join(resources),
                'commitment_status':block['commitment_status'],'reservation_scope':block['reservation_scope'],
                'forecast_coverage_status':block['forecast_coverage_status'],'deferred_reason':''}
            writer.writerow({key:safe_cell(row.get(key)) for key in columns})
    for item in sorted(content['deferred'],key=lambda x:x['request_id']):
        row={**common,'record_type':'DEFERRED','request_id':item['request_id'],'deferred_reason':item['reason'],
            'commitment_status':'TENTATIVE'}
        writer.writerow({key:safe_cell(row.get(key)) for key in columns})
    return output.getvalue()

@router.get('/planning-schedules/{id}/export')
def export_schedule(id:uuid.UUID,format:Literal['json','csv']=Query('json'),user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(PlanningSchedule,id)
    if not row:raise HTTPException(404,'PLANNING_SCHEDULE_NOT_FOUND')
    if digest(row.content)!=row.content_hash:raise HTTPException(409,'SCHEDULE_HASH_MISMATCH')
    if format=='json':
        data=json.dumps(row.content,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        media='application/json';suffix='json'
    else:
        data=csv_export(row.content).encode('utf-8-sig');media='text/csv; charset=utf-8';suffix='csv'
    filename=f"rmaps-{row.schedule_type.lower()}-{row.id}.{suffix}"
    return Response(data,media_type=media,headers={'Content-Disposition':f'attachment; filename="{filename}"',
        'X-RMAPS-Content-Hash':row.content_hash,'X-RMAPS-Authority':AUTHORITY})
