"""Deterministic, persisted explanation of a captured plan replacement.

The comparison is per request. A shared possession can change without hiding
which work moved, finished, or acquired an explicitly assessed residual scope.
"""
import uuid
from datetime import datetime
from fastapi import HTTPException
from .models import PlanRevision, ControllerDecision
from .requests import digest


def capture_source(db, snapshot):
    from .replanning_state import snapshot_capture_current
    captures=snapshot.manifest['facts'].get('replanning',[])
    if len(captures)!=1 or not snapshot_capture_current(db,snapshot):
        raise HTTPException(409,'REPLANNING_CAPTURE_STALE_OR_BLOCKED')
    captured=captures[0];payload=captured['payload']
    if captured['content_hash']!=digest(payload):raise HTTPException(409,'REPLANNING_CAPTURE_HASH_MISMATCH')
    source=db.get(PlanRevision,uuid.UUID(payload['source_plan_revision_id']))
    decision=db.get(ControllerDecision,uuid.UUID(payload['source_decision_id']))
    if (not source or not decision or decision.action!='APPROVE' or decision.scope!='SIMULATED'
            or decision.plan_revision_id!=source.id or source.plan_hash!=payload['source_plan_hash']
            or digest(source.content)!=source.plan_hash):
        raise HTTPException(409,'REPLANNING_SOURCE_APPROVAL_MISMATCH')
    return source,decision,captured


def _work(plan):
    result={}
    for assignment in plan.get('assignments',[]):
        for task in assignment.get('tasks',[]):
            rid=task['request_id']
            if rid in result:raise HTTPException(409,'DUPLICATE_PLAN_REQUEST')
            result[rid]={'candidate_id':assignment['id'],'assignment_hash':digest(assignment),
                'possession_start':assignment['possession_start'],'possession_end':assignment['possession_end'],
                'work_start':task['work_start'],'work_end':task['work_end'],
                'track_ids':assignment['track_ids'],
                'resource_ids':sorted({a['resource_id'] for a in assignment.get('allocations',[])})}
    return result


def difference(db,snapshot,replacement,replacement_hash):
    source,decision,captured=capture_source(db,snapshot)
    if digest(replacement)!=replacement_hash:raise HTTPException(409,'PLAN_HASH_MISMATCH')
    before=_work(source.content);after=_work(replacement)
    facts=snapshot.manifest['facts']
    completed={x['request_id'] for x in facts.get('completed_work',[])} & set(before)
    residual={x['id'] for x in facts['requests'] if x.get('execution_basis')}
    deferred={x['request_id']:x.get('reason') for x in replacement.get('deferred',[])}
    source_deferred={x['request_id']:x.get('reason') for x in source.content.get('deferred',[])}
    changes=[]
    for rid in sorted(set(before)|set(after)|completed|set(deferred)|set(source_deferred)):
        old=before.get(rid);new=after.get(rid)
        if rid in completed:
            if new:raise HTTPException(409,'COMPLETED_REQUEST_RESCHEDULED')
            kind='COMPLETED_VERIFIED'
        elif old and new:
            kind=('UNCHANGED' if old['assignment_hash']==new['assignment_hash']
                else 'REMAINING_WORK_RESCHEDULED' if rid in residual else 'CHANGED')
        elif old:kind='DEFERRED_FROM_SOURCE'
        elif new:kind='PREVIOUSLY_DEFERRED_NOW_SCHEDULED' if rid in source_deferred else 'NEWLY_SCHEDULED'
        elif rid in source_deferred and rid in deferred:
            kind='STILL_DEFERRED' if source_deferred[rid]==deferred[rid] else 'DEFERRED_REASON_CHANGED'
        elif rid in source_deferred:kind='NOT_IN_REPLACEMENT_SCOPE'
        else:kind='NEWLY_DEFERRED'
        shift=None
        if old and new:
            seconds=(datetime.fromisoformat(new['work_start'])-datetime.fromisoformat(old['work_start'])).total_seconds()
            shift=seconds/60
        changes.append({'request_id':rid,'change':kind,'before':old,'after':new,
            'work_start_shift_minutes':shift,'source_deferred_reason':source_deferred.get(rid),
            'replacement_deferred_reason':deferred.get(rid) if not new else None})
    counts={key:sum(x['change']==key for x in changes) for key in sorted({x['change'] for x in changes})}
    payload={'version':'REPLACEMENT_DIFFERENCE_V1','capture_id':captured['id'],
        'capture_hash':captured['content_hash'],'source_plan_revision_id':str(source.id),
        'source_decision_id':str(decision.id),'source_plan_hash':source.plan_hash,
        'replacement_snapshot_id':str(snapshot.id),'replacement_snapshot_hash':snapshot.content_hash,
        'replacement_plan_hash':replacement_hash,'changes':changes,'counts':counts,
        'authority':'SOFTWARE_PROPOSAL_ONLY'}
    return {'content_hash':digest(payload),'payload':payload}
