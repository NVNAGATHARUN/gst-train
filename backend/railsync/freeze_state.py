"""Execution/freeze persistence boundary; no scheduling or validator algorithms.

Legacy snapshots with affected execution stay blocked. Captured replanning facts
must match the current ledger and have no unresolved execution blockers.
An execution observation never implicitly releases a possession or its resources.
"""
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from .models import FreezePolicy, ExecutionRecord, ControllerDecision, PlanRevision, PlanReservation, PossessionRelease
from .requests import digest


def latest_policy(db, scope):
    return db.scalar(select(FreezePolicy).where(FreezePolicy.scope==scope)
        .order_by(FreezePolicy.revision.desc()).limit(1))


def active_approvals(db, scope, lineage_id=None):
    query=select(ControllerDecision,PlanRevision).join(PlanRevision,
        PlanRevision.id==ControllerDecision.plan_revision_id).where(
        ControllerDecision.scope==scope,ControllerDecision.action=='APPROVE',
        select(PlanReservation.id).where(PlanReservation.decision_id==ControllerDecision.id,
            PlanReservation.active.is_(True)).exists())
    if lineage_id is not None:query=query.where(PlanRevision.lineage_id==lineage_id)
    return db.execute(query.order_by(ControllerDecision.id)).all()


def execution_pending(db, snapshot):
    """Fence execution-unaware, obsolete, or unreconciled snapshot evidence."""
    facts=snapshot.manifest['facts']
    if facts.get('replanning'):
        from .replanning_state import snapshot_capture_current
        return not snapshot_capture_current(db,snapshot)
    requests={r['id'] for r in facts['requests']}
    tracks=set(snapshot.manifest['track_ids'])
    resources={r['id'] for r in facts['resources']}
    scope='OPERATIONAL' if (snapshot.manifest.get('validation_context') or {}).get('scope')=='IMPORTED' else 'SIMULATED'
    for record in db.scalars(select(ExecutionRecord).where(ExecutionRecord.scope==scope)):
        if (record.request_id in requests or tracks.intersection(record.result['track_ids'])
                or resources.intersection(record.result['resource_ids'])):
            return True
    return False


def assess_freeze(assignments, records, freeze_minutes, now):
    """Half-open freeze interval [now, cutoff); overdue unobserved work is unknown."""
    latest={}
    for record in sorted(records,key=lambda r:r['sequence']):latest[record['request_id']]=record
    cutoff=now+timedelta(minutes=freeze_minutes) if freeze_minutes is not None else None
    result=[]
    for assignment in assignments:
        reasons=[];blockers=[]
        start=datetime.fromisoformat(assignment['possession_start'])
        observed=[latest[r] for r in assignment['request_ids'] if r in latest]
        for record in observed:
            reasons.append('EXECUTION_'+record['status'])
            if record['status']=='INTERRUPTED':
                blockers.append('INTERRUPTED_WORK_REQUIRES_RECONCILIATION')
                if record['remaining_work_minutes'] is None:blockers.append('REMAINING_WORK_UNKNOWN')
        if start<=now:
            reasons.append('POSSESSION_START_REACHED')
            if any(r not in latest for r in assignment['request_ids']):blockers.append('EXECUTION_STATE_UNKNOWN')
        elif cutoff is not None and start<cutoff:reasons.append('APPROVED_WITHIN_FREEZE_INTERVAL')
        if freeze_minutes is None:
            blockers.append('FREEZE_POLICY_UNKNOWN')
            reasons.append('CONSERVATIVE_POLICY_UNKNOWN')
        result.append({'candidate_id':assignment['id'],'assignment_hash':digest(assignment),
            'request_ids':assignment['request_ids'],'frozen':bool(reasons),
            'reasons':sorted(set(reasons)),'blockers':sorted(set(blockers))})
    return result


def freeze_context(db, scope, now, lineage_id=None):
    policy=latest_policy(db,scope)
    commitments=[]
    for decision,revision in active_approvals(db,scope,lineage_id):
        if digest(revision.content)!=revision.plan_hash:raise HTTPException(409,'APPROVED_PLAN_HASH_MISMATCH')
        records=[{'request_id':r.request_id,'sequence':r.sequence,'status':r.status,
            'remaining_work_minutes':r.payload.get('remaining_work_minutes')}
            for r in db.scalars(select(ExecutionRecord).where(ExecutionRecord.decision_id==decision.id))]
        released=set(db.scalars(select(PossessionRelease.candidate_id).where(PossessionRelease.decision_id==decision.id)))
        for entry in assess_freeze([a for a in revision.content['assignments'] if a['id'] not in released],records,
                policy.freeze_minutes if policy else None,now):
            commitments.append({**entry,'plan_revision_id':str(revision.id),'decision_id':str(decision.id)})
    return {'scope':scope,'checked_at':now.isoformat(),
        'policy':None if not policy else {'id':str(policy.id),'revision':policy.revision,
            'freeze_minutes':policy.freeze_minutes},'commitments':commitments,
        'status':'REQUIRES_ATTENTION' if any(c['blockers'] for c in commitments) else 'ASSESSED',
        'authority':'SOFTWARE_PROPOSAL_ONLY'}


def enforce_replacement(db, scope, lineage_id, proposed, now):
    context=freeze_context(db,scope,now,lineage_id)
    blockers=sorted({b for c in context['commitments'] for b in c['blockers']})
    if blockers:raise HTTPException(409,{'code':'FROZEN_WORK_REQUIRES_ATTENTION','blockers':blockers})
    hashes={digest(a) for a in proposed}
    changed=[c['candidate_id'] for c in context['commitments'] if c['frozen'] and c['assignment_hash'] not in hashes]
    if changed:raise HTTPException(409,{'code':'FROZEN_WORK_CHANGED','candidate_ids':changed})


def enforce_no_duplicate_approved_requests(db, scope, lineage_id, proposed):
    requests={r for a in proposed for r in a['request_ids']}
    for _,revision in active_approvals(db,scope):
        if revision.lineage_id==lineage_id:continue
        overlap=requests.intersection(r for a in revision.content['assignments'] for r in a['request_ids'])
        if overlap:raise HTTPException(409,{'code':'REQUEST_ALREADY_APPROVED','request_ids':sorted(overlap)})
