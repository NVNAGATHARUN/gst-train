"""M13 plan revision, explanation and controller decision boundary.

APPROVED means a software proposal decision. It is never a railway possession grant.
"""
import copy
import uuid
from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field
from sqlalchemy import select,text
from .auth import current_user,require
from .db import session_dependency
from .models import (PlanningRun,PlanningSnapshot,PlanRevision,DecisionExplanation,
    ControllerDecision,PlanReservation,OperationalState,ValidationReport,
    CoordinationComputation,PriorityAssessment)
from .planning import parse
from .requests import StrictModel,audit,digest
from .validation import usability,current_hash,utc_now
from .staleness import invalidation_ids,lock_publication
from .freeze_state import enforce_replacement,enforce_no_duplicate_approved_requests,execution_pending
from .replacement_diff import capture_source,difference

router=APIRouter(prefix='/api/v1')
AUTHORITY='SOFTWARE_PROPOSAL_ONLY'

class MaterializeInput(StrictModel):
    run_id:uuid.UUID
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')

class ModifyInput(StrictModel):
    expected_revision:int=Field(ge=1)
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    selected_candidate_ids:list[str]=Field(max_length=3000)
    reason:str=Field(min_length=3,max_length=1000)

class DecisionInput(StrictModel):
    action:Literal['APPROVE','REJECT']
    idempotency_key:uuid.UUID
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_operational_revision:int=Field(ge=0)
    validation_report_id:uuid.UUID|None=None
    reason:str=Field(min_length=3,max_length=1000)
    supersedes_decision_id:uuid.UUID|None=None

class ReplanInput(StrictModel):
    idempotency_key:uuid.UUID
    expected_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_operational_revision:int=Field(ge=0)
    reason:str=Field(min_length=3,max_length=1000)

def revision_json(row):
    return {'id':str(row.id),'lineage_id':str(row.lineage_id),'revision':row.revision,
        'run_id':str(row.run_id),'snapshot_id':str(row.snapshot_id),'parent_id':str(row.parent_id) if row.parent_id else None,
        'plan_hash':row.plan_hash,'snapshot_hash':row.snapshot_hash,'edit':row.edit,'content':row.content,
        'created_by':row.created_by,'created_at':row.created_at.isoformat(),'authority':AUTHORITY}

def decision_json(row,reservations=None):
    return {'id':str(row.id),'idempotency_key':str(row.idempotency_key),'plan_revision_id':str(row.plan_revision_id),
        'validation_report_id':str(row.validation_report_id) if row.validation_report_id else None,
        'action':row.action,'scope':row.scope,'expected_operational_revision':row.expected_operational_revision,
        'resulting_operational_revision':row.resulting_operational_revision,'reason':row.reason,'result':row.result,
        'created_at':row.created_at.isoformat(),'authority':AUTHORITY,
        'reservations':reservations if reservations is not None else []}

def decision_fingerprint(body):
    return digest(body.model_dump(mode='json'))

def scope_for(snapshot):
    context=snapshot.manifest.get('validation_context') or {}
    return 'SIMULATED' if snapshot.scenario_id or context.get('scope')!='IMPORTED' else 'OPERATIONAL'

def lock_state(db,scope):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':26027130 if scope=='SIMULATED' else 26027131})
    state=db.scalar(select(OperationalState).where(OperationalState.scope==scope).with_for_update())
    if not state:
        state=OperationalState(scope=scope,revision=0,updated_at=datetime.now(timezone.utc));db.add(state);db.flush()
    return state

@router.post('/plan-revisions',status_code=201)
def materialize(body:MaterializeInput,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),db=Depends(session_dependency)):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':26027132})
    run=db.scalar(select(PlanningRun).where(PlanningRun.id==body.run_id).with_for_update())
    if not run:raise HTTPException(404,'RUN_NOT_FOUND')
    if run.status!='COMPLETED':raise HTTPException(409,'RUN_NOT_COMPLETED')
    if digest(run.result)!=body.expected_plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    existing=db.scalar(select(PlanRevision).where(PlanRevision.run_id==run.id).order_by(PlanRevision.revision.desc()).limit(1))
    if existing:
        if existing.plan_hash!=body.expected_plan_hash:raise HTTPException(409,'RUN_ALREADY_MATERIALIZED')
        return revision_json(existing)
    snapshot=db.get(PlanningSnapshot,run.snapshot_id)
    lineage=uuid.uuid4();number=1;parent_id=None;edit={'kind':'SOLVER_RESULT'}
    if snapshot.manifest['facts'].get('replanning'):
        if snapshot.scenario_id or scope_for(snapshot)!='SIMULATED':
            raise HTTPException(409,'SIMULATED_REPLACEMENT_ONLY')
        lock_state(db,'SIMULATED');lock_publication(db)
        source,_,_=capture_source(db,snapshot)
        latest=db.scalar(select(PlanRevision).where(PlanRevision.lineage_id==source.lineage_id)
            .order_by(PlanRevision.revision.desc()).limit(1))
        if latest.id!=source.id and latest.snapshot_id!=snapshot.id:
            raise HTTPException(409,'SOURCE_LINEAGE_ADVANCED')
        lineage=source.lineage_id;number=latest.revision+1;parent_id=latest.id
        edit['replacement']=difference(db,snapshot,run.result,body.expected_plan_hash)
    row=PlanRevision(lineage_id=lineage,revision=number,run_id=run.id,snapshot_id=snapshot.id,parent_id=parent_id,
        plan_hash=body.expected_plan_hash,snapshot_hash=snapshot.content_hash,edit=edit,
        content=copy.deepcopy(run.result),created_by=str(user.id))
    db.add(row);db.flush();audit(db,user,'PLAN_REVISION_CREATED',row.id,{'revision':number,'plan_hash':row.plan_hash,
        'source_plan_revision_id':edit.get('replacement',{}).get('payload',{}).get('source_plan_revision_id')});db.commit()
    return revision_json(row)

def coordination_for(db,run):
    raw=run.config.get('coordination_id')
    if not raw:raise HTTPException(409,'PLAN_HAS_NO_COORDINATED_CANDIDATES')
    coordination=db.get(CoordinationComputation,uuid.UUID(raw))
    if not coordination:raise HTTPException(409,'COORDINATION_NOT_FOUND')
    return coordination

@router.post('/plan-revisions/{id}/modifications',status_code=201)
def modify(id:uuid.UUID,body:ModifyInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':26027132})
    parent=db.get(PlanRevision,id)
    if not parent:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    snapshot=db.get(PlanningSnapshot,parent.snapshot_id)
    if snapshot.scenario_id:raise HTTPException(409,'SCENARIO_EDIT_REQUIRES_NEW_SCENARIO')
    scope=scope_for(snapshot);lock_state(db,scope)
    if execution_pending(db,snapshot):raise HTTPException(409,'EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    if parent.revision!=body.expected_revision or parent.plan_hash!=body.expected_plan_hash:raise HTTPException(409,'PLAN_REVISION_CONFLICT')
    latest=db.scalar(select(PlanRevision).where(PlanRevision.lineage_id==parent.lineage_id).order_by(PlanRevision.revision.desc()).limit(1))
    if latest.id!=parent.id:raise HTTPException(409,'PLAN_REVISION_NOT_LATEST')
    run=db.get(PlanningRun,parent.run_id);coordination=coordination_for(db,run)
    candidates={c['id']:c for c in coordination.result['candidates']}
    selected=body.selected_candidate_ids
    if len(selected)!=len(set(selected)):raise HTTPException(422,'DUPLICATE_CANDIDATE_SELECTION')
    unknown=sorted(set(selected)-set(candidates))
    if unknown:raise HTTPException(422,{'code':'UNKNOWN_CANDIDATE','ids':unknown})
    enforce_replacement(db,scope,parent.lineage_id,[candidates[cid] for cid in selected],now)
    covered={request for cid in selected for request in candidates[cid]['request_ids']}
    requests={r['id'] for r in db.get(PlanningSnapshot,parent.snapshot_id).manifest['facts']['requests']}
    content=copy.deepcopy(parent.content)
    content.update({'planner':'CONTROLLER_EDIT','solver_status':None,'has_incumbent':None,
        'schedule_status':'DEVELOPMENT_ARTIFACT','assignments':[candidates[cid] for cid in selected],
        'selected_candidate_ids':selected,'deferred':[{'request_id':rid,'reason':'CONTROLLER_EXCLUDED_OR_REPLACED'} for rid in sorted(requests-covered)],
        'counts':{'scheduled':len(covered),'deferred':len(requests-covered),'unresolved':0,'candidates':len(candidates)},
        'objective_value':None,'objective_terms':None,'best_bound':None,'relative_gap':None,
        'review_blockers':['FRESH_VALIDATION_REQUIRED_AFTER_CONTROLLER_EDIT']})
    plan_hash=digest(content)
    edit={'kind':'CANDIDATE_SELECTION','selected_candidate_ids':selected,'reason':body.reason}
    if snapshot.manifest['facts'].get('replanning'):
        edit['replacement']=difference(db,snapshot,content,plan_hash)
    row=PlanRevision(lineage_id=parent.lineage_id,revision=parent.revision+1,run_id=parent.run_id,
        snapshot_id=parent.snapshot_id,parent_id=parent.id,plan_hash=plan_hash,snapshot_hash=parent.snapshot_hash,
        edit=edit,
        content=content,created_by=str(user.id))
    db.add(row);db.flush();audit(db,user,'PLAN_MODIFIED',row.id,{'parent_id':str(parent.id),'revision':row.revision,'plan_hash':plan_hash});db.commit()
    return revision_json(row)

def priority_map(db,snapshot_id):
    rows=db.scalars(select(PriorityAssessment).where(PriorityAssessment.snapshot_id==snapshot_id)
        .order_by(PriorityAssessment.request_id,PriorityAssessment.assessed_at.desc())).all()
    result={}
    for row in rows:
        result.setdefault(str(row.request_id),row)
    return result

def explanation_payload(request,plan,coordination,assessment):
    rid=request['id']
    selected=next((c for c in plan.get('assignments',[]) if rid in c.get('request_ids',[])),None)
    alternatives=[c for c in coordination.result['candidates'] if rid in c['request_ids']]
    exclusions=[e for e in coordination.result.get('exclusions',[]) if rid in e.get('request_ids',[])]
    priority=None if not assessment else {'method':assessment.method,'score_basis_points':assessment.score_basis_points,
        'priority_band':assessment.priority_band,'contributions':assessment.contributions,'policy_version':assessment.policy_version}
    if selected:
        co_work=sorted(set(selected['request_ids'])-{rid})
        payload={'request_id':rid,'outcome':'SCHEDULED','priority':priority,'selected_candidate_id':selected['id'],
            'selected_window':{'possession_start':selected['possession_start'],'possession_end':selected['possession_end'],
                'track_ids':selected['track_ids']},'compatible_co_work':co_work,
            'resource_assignments':selected.get('allocations',[]),'binding_rule_evidence':selected.get('rule_ids',[]),
            'alternative_candidate_count':len(alternatives),'objective_evidence':plan.get('objective_terms'),
            'narrative':f"Request {rid} is scheduled in generated candidate {selected['id']} from {selected['possession_start']} to {selected['possession_end']}."}
    else:
        deferred=next((x for x in plan.get('deferred',[]) if x.get('request_id')==rid),{'reason':'UNRESOLVED'})
        earliest=min(alternatives,key=lambda c:(c['possession_start'],c['id'])) if alternatives else None
        payload={'request_id':rid,'outcome':'DEFERRED','priority':priority,'deferred_reason':deferred['reason'],
            'evidence_backed_exclusions':exclusions,'alternative_candidate_count':len(alternatives),
            'earliest_verified_candidate':({'candidate_id':earliest['id'],'possession_start':earliest['possession_start'],
                'possession_end':earliest['possession_end']} if earliest else None),
            'narrative':f"Request {rid} is deferred with recorded reason {deferred['reason']}."}
    return payload

@router.post('/plan-revisions/{id}/explanations',status_code=201)
def explain(id:uuid.UUID,user=Depends(require('ADMIN','PLANNER','CONTROLLER')),db=Depends(session_dependency)):
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    existing=db.scalars(select(DecisionExplanation).where(DecisionExplanation.plan_revision_id==id).order_by(DecisionExplanation.request_id)).all()
    if existing:return {'plan_revision_id':str(id),'items':[x.payload for x in existing],'duplicate':True}
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id);run=db.get(PlanningRun,revision.run_id)
    coordination=coordination_for(db,run);priorities=priority_map(db,snapshot.id)
    rows=[]
    for request in snapshot.manifest['facts']['requests']:
        payload=explanation_payload(request,revision.content,coordination,priorities.get(request['id']))
        rows.append(DecisionExplanation(plan_revision_id=id,request_id=request['id'],outcome=payload['outcome'],payload=payload))
    db.add_all(rows);db.flush();audit(db,user,'PLAN_EXPLAINED',id,{'request_count':len(rows),'plan_hash':revision.plan_hash});db.commit()
    return {'plan_revision_id':str(id),'items':[x.payload for x in sorted(rows,key=lambda x:x.request_id)],'duplicate':False}

@router.get('/plan-revisions/{id}')
def read_revision(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    row=db.get(PlanRevision,id)
    if not row:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    result=revision_json(row)
    events=invalidation_ids(db,row.snapshot_id)
    result['current_state']={'status':'STALE_REQUIRES_ATTENTION' if events else 'NO_EVENT_INVALIDATION',
        'disruption_event_ids':events}
    if execution_pending(db,db.get(PlanningSnapshot,row.snapshot_id)):
        result['current_state'].update(status='STALE_REQUIRES_ATTENTION',execution_blocker='EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    decisions=db.scalars(select(ControllerDecision).where(ControllerDecision.plan_revision_id==id).order_by(ControllerDecision.created_at)).all()
    result['decisions']=[decision_json(x) for x in decisions]
    return result

@router.get('/plan-revisions/{id}/explanations')
def read_explanations(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    if not db.get(PlanRevision,id):raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    rows=db.scalars(select(DecisionExplanation).where(DecisionExplanation.plan_revision_id==id).order_by(DecisionExplanation.request_id)).all()
    return {'plan_revision_id':str(id),'items':[x.payload for x in rows]}

@router.get('/plan-revisions/{id}/differences')
def read_differences(id:uuid.UUID,user=Depends(current_user),db=Depends(session_dependency)):
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    stored=revision.edit.get('replacement')
    if not stored:raise HTTPException(404,'REPLACEMENT_DIFFERENCES_NOT_FOUND')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id)
    # The record remains readable after approval changes the live ledger.
    if (digest(stored['payload'])!=stored['content_hash'] or
            stored['payload']['replacement_plan_hash']!=revision.plan_hash or
            digest(revision.content)!=revision.plan_hash or
            stored['payload']['replacement_snapshot_hash']!=snapshot.content_hash):
        raise HTTPException(409,'REPLACEMENT_DIFFERENCE_HASH_MISMATCH')
    return {'plan_revision_id':str(id),**stored}

def overlaps(left,right):
    return left.start_at<right['end'] and right['start']<left.end_at

def reservation_json(row):
    return {'id':str(row.id),'scope':row.scope,'track_ids':row.track_ids,'resource_ids':row.resource_ids,
        'start_at':row.start_at.isoformat(),'end_at':row.end_at.isoformat(),'active':row.active}

@router.post('/plan-revisions/{id}/decisions',status_code=201)
def decide(id:uuid.UUID,body:DecisionInput,user=Depends(require('CONTROLLER')),now=Depends(utc_now),db=Depends(session_dependency)):
    duplicate=db.scalar(select(ControllerDecision).where(ControllerDecision.idempotency_key==body.idempotency_key))
    if duplicate:
        if duplicate.plan_revision_id!=id or duplicate.action!=body.action or duplicate.result.get('request_fingerprint')!=decision_fingerprint(body):
            raise HTTPException(409,'IDEMPOTENCY_KEY_REUSED')
        reservations=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==duplicate.id)).all()
        return decision_json(duplicate,[reservation_json(x) for x in reservations])
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    if revision.plan_hash!=body.expected_plan_hash or digest(revision.content)!=body.expected_plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id);scope=scope_for(snapshot);state=lock_state(db,scope)
    if snapshot.scenario_id:raise HTTPException(409,'SCENARIO_DECISION_FORBIDDEN')
    # A concurrent request with the same key may have committed while this one
    # waited for the scope lock. Retry must return that exact decision.
    duplicate=db.scalar(select(ControllerDecision).where(ControllerDecision.idempotency_key==body.idempotency_key))
    if duplicate:
        if duplicate.plan_revision_id!=id or duplicate.action!=body.action or duplicate.result.get('request_fingerprint')!=decision_fingerprint(body):
            raise HTTPException(409,'IDEMPOTENCY_KEY_REUSED')
        reservations=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==duplicate.id)).all()
        return decision_json(duplicate,[reservation_json(x) for x in reservations])
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    if body.action=='APPROVE':lock_publication(db)
    validation=None
    if body.action=='APPROVE':
        if snapshot.manifest['facts'].get('replanning'):
            if snapshot.scenario_id or scope!='SIMULATED':raise HTTPException(409,'SIMULATED_REPLACEMENT_ONLY')
            source,source_decision,_=capture_source(db,snapshot)
            if body.supersedes_decision_id!=source_decision.id:
                raise HTTPException(409,'REPLACEMENT_SOURCE_SUPERSEDE_REQUIRED')
            stored=revision.edit.get('replacement')
            if not stored or stored!=difference(db,snapshot,revision.content,revision.plan_hash):
                raise HTTPException(409,'REPLACEMENT_DIFFERENCE_MISMATCH')
            if revision.lineage_id!=source.lineage_id or revision.id==source.id:
                raise HTTPException(409,'REPLACEMENT_LINEAGE_MISMATCH')
            latest=db.scalar(select(PlanRevision).where(PlanRevision.lineage_id==source.lineage_id)
                .order_by(PlanRevision.revision.desc()).limit(1))
            if latest.id!=revision.id:raise HTTPException(409,'PLAN_REVISION_NOT_LATEST')
        if not body.validation_report_id:raise HTTPException(422,'VALIDATION_REPORT_REQUIRED')
        validation=db.get(ValidationReport,body.validation_report_id)
        if not validation or validation.plan_revision_id!=revision.id or validation.plan_hash!=revision.plan_hash:
            raise HTTPException(409,'VALIDATION_REPORT_MISMATCH')
        usable,blockers=usability(db,validation,now)
        if not usable:raise HTTPException(409,{'code':'VALIDATION_NOT_USABLE','blockers':blockers})
    active_approval=db.scalar(select(ControllerDecision).join(PlanRevision,PlanRevision.id==ControllerDecision.plan_revision_id)
        .where(PlanRevision.lineage_id==revision.lineage_id,ControllerDecision.action=='APPROVE')
        .order_by(ControllerDecision.created_at.desc()).limit(1))
    active_old=[]
    if active_approval:
        active_old=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==active_approval.id,PlanReservation.active.is_(True))).all()
        if active_old and body.action=='REJECT':raise HTTPException(409,'APPROVED_PLAN_REQUIRES_CONTROLLED_SUPERSEDE')
        if active_old and (body.action=='APPROVE'):
            if active_approval.plan_revision_id==revision.id:raise HTTPException(409,'PLAN_ALREADY_APPROVED')
            if body.supersedes_decision_id!=active_approval.id:raise HTTPException(409,'EXISTING_APPROVAL_REQUIRES_SUPERSEDE')
    if body.action=='APPROVE' and snapshot.manifest['facts'].get('replanning'):
        if not active_approval or active_approval.id!=source_decision.id:
            raise HTTPException(409,'REPLACEMENT_SOURCE_NOT_CURRENT')
    proposed=[]
    if body.action=='APPROVE':
        enforce_replacement(db,scope,revision.lineage_id,revision.content.get('assignments',[]),now)
        enforce_no_duplicate_approved_requests(db,scope,revision.lineage_id,revision.content.get('assignments',[]))
        for block in revision.content.get('assignments',[]):
            resources=sorted({a['resource_id'] for a in block.get('allocations',[])})
            proposed.append({'start':parse(block['possession_start']),'end':parse(block['possession_end']),
                'tracks':sorted(block['track_ids']),'resources':resources})
        active=db.scalars(select(PlanReservation).where(PlanReservation.scope==scope,PlanReservation.active.is_(True))).all()
        ignored={x.id for x in active_old} if body.supersedes_decision_id else set()
        for old in active:
            if old.id in ignored:continue
            for new in proposed:
                if overlaps(old,new) and (set(old.track_ids)&set(new['tracks']) or set(old.resource_ids)&set(new['resources'])):
                    raise HTTPException(409,{'code':'RESERVATION_CONFLICT','reservation_id':str(old.id)})
    next_revision=state.revision+1
    result={'authority':AUTHORITY,'reservation_scope':scope,
        'operational_reservation_written':scope=='OPERATIONAL' and body.action=='APPROVE',
        'simulation_isolated':scope=='SIMULATED','request_fingerprint':decision_fingerprint(body)}
    if body.action=='APPROVE' and snapshot.manifest['facts'].get('replanning'):
        result['replacement']={'source_decision_id':str(source_decision.id),'source_plan_revision_id':str(source.id),
            'difference_hash':stored['content_hash'],'capture_id':stored['payload']['capture_id']}
    decision=ControllerDecision(idempotency_key=body.idempotency_key,plan_revision_id=id,
        validation_report_id=validation.id if validation else None,action=body.action,scope=scope,
        expected_operational_revision=state.revision,resulting_operational_revision=next_revision,
        reason=body.reason,actor=str(user.id),result=result)
    db.add(decision);db.flush()
    if body.action=='APPROVE':
        if body.supersedes_decision_id:
            for old in active_old:old.active=False
        for proposed_row in proposed:
            db.add(PlanReservation(plan_revision_id=id,decision_id=decision.id,scope=scope,
                track_ids=proposed_row['tracks'],resource_ids=proposed_row['resources'],
                start_at=proposed_row['start'],end_at=proposed_row['end'],active=True))
    state.revision=next_revision;state.updated_at=now
    audit(db,user,'CONTROLLER_'+body.action,id,{'decision_id':str(decision.id),'scope':scope,'authority':AUTHORITY})
    db.commit()
    reservations=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==decision.id)).all()
    return decision_json(decision,[reservation_json(x) for x in reservations])

@router.post('/plan-revisions/{id}/replan',status_code=202)
def replan(id:uuid.UUID,body:ReplanInput,user=Depends(require('CONTROLLER')),db=Depends(session_dependency)):
    duplicate=db.scalar(select(ControllerDecision).where(ControllerDecision.idempotency_key==body.idempotency_key))
    if duplicate:
        if duplicate.plan_revision_id!=id or duplicate.action!='REPLAN' or duplicate.result.get('request_fingerprint')!=decision_fingerprint(body):
            raise HTTPException(409,'IDEMPOTENCY_KEY_REUSED')
        return decision_json(duplicate)
    revision=db.get(PlanRevision,id)
    if not revision:raise HTTPException(404,'PLAN_REVISION_NOT_FOUND')
    if revision.plan_hash!=body.expected_plan_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    snapshot=db.get(PlanningSnapshot,revision.snapshot_id);scope=scope_for(snapshot);state=lock_state(db,scope)
    if snapshot.scenario_id:raise HTTPException(409,'SCENARIO_DECISION_FORBIDDEN')
    if state.revision!=body.expected_operational_revision:raise HTTPException(409,'OPERATIONAL_REVISION_CONFLICT')
    if current_hash(db,snapshot)!=digest(snapshot.manifest['facts']):raise HTTPException(409,'CURRENT_STATE_REQUIRES_NEW_SNAPSHOT')
    lock_publication(db)
    if invalidation_ids(db,snapshot.id):raise HTTPException(409,'SNAPSHOT_INVALIDATED_BY_EVENT')
    if execution_pending(db,snapshot):raise HTTPException(409,'EXECUTION_AWARE_SNAPSHOT_REQUIRED')
    source=db.get(PlanningRun,revision.run_id)
    run=PlanningRun(snapshot_id=snapshot.id,planner_type=source.planner_type,status='QUEUED',
        config={**source.config,'replan_of_plan_revision_id':str(id),'replan_reason':body.reason})
    db.add(run);db.flush();next_revision=state.revision+1
    decision=ControllerDecision(idempotency_key=body.idempotency_key,plan_revision_id=id,validation_report_id=None,
        action='REPLAN',scope=scope,expected_operational_revision=state.revision,resulting_operational_revision=next_revision,
        reason=body.reason,actor=str(user.id),result={'authority':AUTHORITY,'planning_run_id':str(run.id),'status':'QUEUED',
            'request_fingerprint':decision_fingerprint(body)})
    db.add(decision);state.revision=next_revision;state.updated_at=datetime.now(timezone.utc)
    audit(db,user,'CONTROLLER_REPLAN',id,{'decision_id':str(decision.id),'planning_run_id':str(run.id)});db.commit()
    return decision_json(decision)
