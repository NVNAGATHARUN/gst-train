import csv, io, json, hashlib, uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator, ValidationError
from sqlalchemy import select, text
from .db import session_dependency
from .models import MaintenanceRequest, RequestRevision, AuditEvent, ImportBatch, SourceRecord
from .auth import current_user, require

router=APIRouter(prefix='/api/v1')
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Requirement(StrictModel):
    type: str = Field(min_length=1,max_length=60)
    quantity: int = Field(gt=0,le=100)
    qualification: str | None = Field(default=None,max_length=60)

class RequestInput(StrictModel):
    department: Literal['ENGINEERING','TRD','SNT']
    asset_id: str = Field(min_length=1,max_length=100)
    footprint: list[str] = Field(min_length=1,max_length=50)
    issue_type: str = Field(min_length=1,max_length=60)
    description: str = Field(default='',max_length=4000)
    severity: int = Field(ge=1,le=5)
    urgency: int = Field(ge=1,le=5)
    criticality: int = Field(default=3,ge=1,le=5)
    impact: int = Field(default=3,ge=1,le=5)
    work_minutes: int = Field(gt=0,le=10080)
    setup_minutes: int = Field(default=0,ge=0,le=1440)
    restore_minutes: int = Field(default=0,ge=0,le=1440)
    earliest_at: AwareDatetime
    deadline_at: AwareDatetime
    deadline_kind: Literal['RESTORED_BY','WORK_COMPLETE_BY']='RESTORED_BY'
    mandatory: bool=False
    block_required: bool=True
    power_block_required: bool=False
    isolation_zone: str | None=None
    power_state: Literal['ANY','ON','OFF','UNKNOWN']='UNKNOWN'
    signalling_state: Literal['ANY','CONNECTED','DISCONNECTED','UNKNOWN']='UNKNOWN'
    resource_location: str | None = None
    requirements: list[Requirement] = Field(default_factory=list,max_length=20)
    predecessors: list[str] = Field(default_factory=list,max_length=50)
    source_mode: Literal['SIMULATED','IMPORTED']='SIMULATED'

    @model_validator(mode='after')
    def intervals(self):
        if self.earliest_at>=self.deadline_at:raise ValueError('earliest_at must precede deadline_at')
        if len(set(self.footprint))!=len(self.footprint):raise ValueError('duplicate footprint')
        if self.power_block_required and not self.isolation_zone:raise ValueError('isolation_zone required')
        if self.power_block_required and self.power_state=='ON':raise ValueError('power block contradicts ON state')
        if self.resource_location and self.resource_location not in self.footprint:raise ValueError('resource location outside work footprint')
        return self

def scoped(user,department,write=False):
    if user.role=='DEPARTMENT' and user.department==department:return
    if not write and user.role in ['PLANNER','CONTROLLER','AUDITOR','ADMIN']:return
    raise HTTPException(403,'DEPARTMENT_FORBIDDEN')

def audit(db,user,action,entity,data=None):
    db.add(AuditEvent(actor=str(user.id),action=action,entity=str(entity),data=data or {}))

def get_request(db,id,user,lock=False):
    query=select(MaintenanceRequest).where(MaintenanceRequest.id==id)
    if lock:query=query.with_for_update()
    request=db.scalar(query)
    if not request:raise HTTPException(404,'REQUEST_NOT_FOUND')
    scoped(user,request.department)
    return request

def serialize(db,r):
    rev=db.scalar(select(RequestRevision).where(RequestRevision.request_id==r.id,RequestRevision.revision==r.revision))
    return {'id':str(r.id),'revision':r.revision,'status':r.status,'created_at':r.created_at.isoformat(),'data':rev.payload}

def create(db,data,user):
    scoped(user,data.department,True)
    from .network import validate_request_location
    validate_request_location(db,data)
    r=MaintenanceRequest(department=data.department);db.add(r);db.flush()
    db.add(RequestRevision(request_id=r.id,revision=1,payload=data.model_dump(mode='json')));db.flush()
    audit(db,user,'REQUEST_CREATED',r.id,{'revision':1})
    return r

@router.post('/maintenance-requests',status_code=201)
def create_request(data:RequestInput,user=Depends(current_user),db=Depends(session_dependency)):
    r=create(db,data,user);db.commit();return serialize(db,r)

@router.get('/maintenance-requests')
def list_requests(department:str|None=None,status:str|None=None,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0),user=Depends(current_user),db=Depends(session_dependency)):
    query=select(MaintenanceRequest).order_by(MaintenanceRequest.created_at,MaintenanceRequest.id)
    if user.role=='DEPARTMENT':query=query.where(MaintenanceRequest.department==user.department)
    if department:query=query.where(MaintenanceRequest.department==department)
    if status:query=query.where(MaintenanceRequest.status==status)
    rows=db.scalars(query.offset(offset).limit(limit)).all()
    return {'items':[serialize(db,r) for r in rows],'next_offset':offset+limit if len(rows)==limit else None}

@router.get('/maintenance-requests/{id}')
def read_request(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    return serialize(db,get_request(db,id,user))

class RevisionInput(StrictModel):
    expected_revision:int
    data:RequestInput

@router.patch('/maintenance-requests/{id}')
def revise_request(id:uuid.UUID,body:RevisionInput,user=Depends(current_user),db=Depends(session_dependency)):
    r=get_request(db,id,user,True);scoped(user,r.department,True)
    if r.revision!=body.expected_revision:raise HTTPException(409,'STALE_REVISION')
    if r.status not in ['RAISED','VALIDATED','PENDING_PLANNING','DEFERRED']:raise HTTPException(409,'REQUEST_NOT_EDITABLE')
    if body.data.department!=r.department:raise HTTPException(422,'DEPARTMENT_IMMUTABLE')
    from .network import validate_request_location
    validate_request_location(db,body.data)
    r.revision+=1;r.status='RAISED'
    db.add(RequestRevision(request_id=r.id,revision=r.revision,payload=body.data.model_dump(mode='json')))
    audit(db,user,'REQUEST_REVISED',r.id,{'revision':r.revision});db.commit();return serialize(db,r)

class Transition(StrictModel):
    action:Literal['VALIDATE','SUBMIT','DEFER','CANCEL']
    expected_revision:int
    reason:str=Field(min_length=1,max_length=1000)

@router.post('/maintenance-requests/{id}/transitions')
def transition(id:uuid.UUID,body:Transition,user=Depends(current_user),db=Depends(session_dependency)):
    r=get_request(db,id,user,True);scoped(user,r.department,True)
    if body.expected_revision!=r.revision:raise HTTPException(409,'STALE_REVISION')
    allowed={'VALIDATE':({'RAISED'},'VALIDATED'),'SUBMIT':({'VALIDATED'},'PENDING_PLANNING'),'DEFER':({'PENDING_PLANNING'},'DEFERRED'),'CANCEL':({'RAISED','VALIDATED','PENDING_PLANNING','DEFERRED'},'CANCELLED')}
    before,after=allowed[body.action]
    if r.status not in before:raise HTTPException(409,'INVALID_TRANSITION')
    r.status=after;audit(db,user,body.action,r.id,{'reason':body.reason});db.commit();return serialize(db,r)

class ImportInput(StrictModel):
    source:Literal['TMS','SMMS','TDMS']
    rows:list[dict]=Field(default_factory=list,max_length=1000)
    csv_text:str|None=Field(default=None,max_length=1000000)

@router.post('/imports/preview',status_code=201)
def preview(body:ImportInput,user=Depends(require('DEPARTMENT')),db=Depends(session_dependency)):
    expected={'TMS':'ENGINEERING','TDMS':'TRD','SMMS':'SNT'}[body.source];scoped(user,expected,True)
    if body.csv_text and body.rows:raise HTTPException(422,'ONE_IMPORT_FORMAT_REQUIRED')
    rows=list(csv.DictReader(io.StringIO(body.csv_text))) if body.csv_text else body.rows
    if len(rows)>1000:raise HTTPException(422,'IMPORT_TOO_LARGE')
    valid=[];errors=[]
    for index,row in enumerate(rows,1):
        try:
            row=dict(row);external=str(row.pop('external_id'));revision=int(row.pop('source_revision'))
            if not external or len(external)>100 or revision<1:raise ValueError('Invalid source identity')
            for key in ['footprint','requirements','predecessors']:
                if isinstance(row.get(key),str):row[key]=json.loads(row[key])
            row['source_mode']='IMPORTED';data=RequestInput.model_validate(row)
            if data.department!=expected:raise ValueError('Source department mismatch')
            valid.append({'external_id':external,'source_revision':revision,'data':data.model_dump(mode='json')})
        except (ValueError,KeyError,TypeError) as e:
            errors.append({'row':index,'code':'INVALID_ROW','message':str(e)[:1000]})
    payload={'valid':valid,'errors':errors};batch=ImportBatch(actor=str(user.id),source=body.source,payload=payload,content_hash=digest(payload))
    db.add(batch);db.commit();return {'id':str(batch.id),'hash':batch.content_hash,**payload}

class ImportCommit(StrictModel):
    expected_hash:str

@router.get('/imports')
def list_imports(source:Literal['TMS','SMMS','TDMS']|None=None,limit:int=Query(50,ge=1,le=200),
    offset:int=Query(0,ge=0),user=Depends(current_user),db=Depends(session_dependency)):
    query=select(ImportBatch).order_by(ImportBatch.source,ImportBatch.id)
    if user.role=='DEPARTMENT':query=query.where(ImportBatch.actor==str(user.id))
    elif user.role not in ['PLANNER','CONTROLLER','AUDITOR','ADMIN']:raise HTTPException(403,'ROLE_FORBIDDEN')
    if source:query=query.where(ImportBatch.source==source)
    rows=db.scalars(query.offset(offset).limit(limit)).all()
    return {'items':[{'id':str(row.id),'source':row.source,'hash':row.content_hash,
        'state':'COMMITTED' if row.result is not None else 'PREVIEWED',
        'valid_count':len(row.payload.get('valid',[])),'error_count':len(row.payload.get('errors',[])),
        'result':row.result} for row in rows],
        'next_offset':offset+limit if len(rows)==limit else None}

@router.get('/source-records')
def list_source_records(source:Literal['TMS','SMMS','TDMS']|None=None,limit:int=Query(50,ge=1,le=200),
    offset:int=Query(0,ge=0),user=Depends(current_user),db=Depends(session_dependency)):
    query=select(SourceRecord,MaintenanceRequest).join(MaintenanceRequest,MaintenanceRequest.id==SourceRecord.request_id)
    if user.role=='DEPARTMENT':query=query.where(MaintenanceRequest.department==user.department)
    elif user.role not in ['PLANNER','CONTROLLER','AUDITOR','ADMIN']:raise HTTPException(403,'ROLE_FORBIDDEN')
    if source:query=query.where(SourceRecord.source==source)
    rows=db.execute(query.order_by(SourceRecord.source,SourceRecord.external_id,SourceRecord.source_revision.desc())
        .offset(offset).limit(limit)).all()
    return {'items':[{'id':str(record.id),'source':record.source,'external_id':record.external_id,
        'source_revision':record.source_revision,'payload_hash':record.payload_hash,
        'request_id':str(record.request_id),'department':request.department} for record,request in rows],
        'next_offset':offset+limit if len(rows)==limit else None}

@router.post('/imports/{id}/commit')
def commit_import(id:uuid.UUID,body:ImportCommit,user=Depends(require('DEPARTMENT')),db=Depends(session_dependency)):
    batch=db.scalar(select(ImportBatch).where(ImportBatch.id==id).with_for_update())
    if not batch:raise HTTPException(404,'BATCH_NOT_FOUND')
    if batch.actor!=str(user.id):raise HTTPException(403,'BATCH_OWNER_REQUIRED')
    if batch.content_hash!=body.expected_hash:raise HTTPException(409,'PREVIEW_CHANGED')
    if batch.result is not None:return batch.result
    db.execute(text('SELECT pg_advisory_xact_lock(2602702)'))
    created=[];skipped=0
    for row in batch.payload['valid']:
        q=select(SourceRecord).where(SourceRecord.source==batch.source,SourceRecord.external_id==row['external_id'])
        previous=db.scalar(q.order_by(SourceRecord.source_revision.desc()).limit(1))
        payload_hash=digest(row['data'])
        if previous and previous.source_revision>=row['source_revision']:
            if previous.source_revision==row['source_revision'] and previous.payload_hash==payload_hash:skipped+=1;continue
            raise HTTPException(409,'SOURCE_REVISION_CONFLICT')
        data=RequestInput.model_validate(row['data'])
        from .network import validate_request_location
        validate_request_location(db,data)
        if previous:
            r=get_request(db,previous.request_id,user,True)
            if r.status not in ['RAISED','VALIDATED','PENDING_PLANNING','DEFERRED']:raise HTTPException(409,'REQUEST_NOT_EDITABLE')
            r.revision+=1;r.status='RAISED';db.add(RequestRevision(request_id=r.id,revision=r.revision,payload=row['data']))
        else:r=create(db,data,user)
        db.add(SourceRecord(source=batch.source,external_id=row['external_id'],source_revision=row['source_revision'],payload_hash=payload_hash,request_id=r.id));db.flush();created.append(str(r.id))
    batch.result={'request_ids':created,'applied':len(created),'duplicates':skipped,'quarantined':len(batch.payload['errors'])}
    audit(db,user,'IMPORT_COMMITTED',batch.id,batch.result);db.commit();return batch.result
