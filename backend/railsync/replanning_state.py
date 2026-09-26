"""Snapshot provenance for approved commitments and explicit execution observations."""
import copy
import uuid
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select,or_
from .models import (ExecutionRecord,OperationalState,PlanReservation,ReplanningCapture,
    PlanningSnapshot,PlanRevision,DisruptionEvent,ControllerDecision,WorkReconciliation,PossessionRelease)
from .freeze_state import active_approvals,latest_policy,freeze_context
from .requests import digest

BASE_FACT_KEYS=('network','requests','occupancy','coa','freight','resources','coordination_policies')


def ledger(db):
    """Conservative scope-wide ledger: every mutation forces a new capture."""
    policy=latest_policy(db,'SIMULATED')
    state=db.get(OperationalState,'SIMULATED')
    approvals=[]
    source_approvals=db.execute(select(ControllerDecision,PlanRevision).join(PlanRevision,PlanRevision.id==ControllerDecision.plan_revision_id)
        .where(ControllerDecision.scope=='SIMULATED',ControllerDecision.action=='APPROVE',or_(
            select(PlanReservation.id).where(PlanReservation.decision_id==ControllerDecision.id,PlanReservation.active.is_(True)).exists(),
            select(PossessionRelease.id).where(PossessionRelease.decision_id==ControllerDecision.id).exists(),
            select(ExecutionRecord.id).where(ExecutionRecord.decision_id==ControllerDecision.id).exists()))
        .order_by(ControllerDecision.id)).all()
    for decision,revision in source_approvals:
        reservations=db.scalars(select(PlanReservation).where(PlanReservation.decision_id==decision.id,
            PlanReservation.active.is_(True)).order_by(PlanReservation.id)).all()
        approvals.append({'decision_id':str(decision.id),'plan_revision_id':str(revision.id),
            'lineage_id':str(revision.lineage_id),'plan_hash':revision.plan_hash,
            'actual_plan_hash':digest(revision.content),'assignments':copy.deepcopy(revision.content['assignments']),
            'replacement':copy.deepcopy(revision.edit.get('replacement')),
            'approval_replacement':copy.deepcopy(decision.result.get('replacement')),
            'reservations':[{'id':str(r.id),'track_ids':r.track_ids,'resource_ids':r.resource_ids,
                'start_at':r.start_at.isoformat(),'end_at':r.end_at.isoformat()} for r in reservations]})
    observations=[{'id':str(r.id),'plan_revision_id':str(r.plan_revision_id),'decision_id':str(r.decision_id),
        'request_id':r.request_id,'sequence':r.sequence,'candidate_id':r.candidate_id,
        'assignment_hash':r.assignment_hash,'status':r.status,'observed_at':r.observed_at.isoformat(),
        'received_at':r.received_at.isoformat(),'payload_hash':r.payload_hash,'payload':r.payload,'result':r.result}
        for r in db.scalars(select(ExecutionRecord).where(ExecutionRecord.scope=='SIMULATED')
            .order_by(ExecutionRecord.request_id,ExecutionRecord.sequence))]
    events=[{'id':str(e.id),'payload_hash':e.payload_hash} for e in db.scalars(select(DisruptionEvent)
        .where(DisruptionEvent.scope=='SIMULATED').order_by(DisruptionEvent.id))]
    reconciliations=[{'id':str(r.id),'execution_record_id':str(r.execution_record_id),'revision':r.revision,
        'payload_hash':r.payload_hash,'payload':r.payload,'result':r.result,'created_at':r.created_at.isoformat()}
        for r in db.scalars(select(WorkReconciliation).order_by(WorkReconciliation.execution_record_id,WorkReconciliation.revision))]
    releases=[{'id':str(r.id),'decision_id':str(r.decision_id),'candidate_id':r.candidate_id,
        'reservation_id':str(r.reservation_id),'payload_hash':r.payload_hash,'payload':r.payload,'result':r.result,
        'created_at':r.created_at.isoformat()} for r in db.scalars(select(PossessionRelease).order_by(PossessionRelease.id))]
    return {'scope':'SIMULATED','operational_revision':state.revision if state else 0,
        'policy':None if not policy else {'id':str(policy.id),'revision':policy.revision,
            'freeze_minutes':policy.freeze_minutes,'reason':policy.reason},
        'approvals':approvals,'execution':observations,'events':events,'reconciliations':reconciliations,'releases':releases}


def capture_payload(db,parent,now):
    raw=ledger(db)
    current=db.scalar(select(ControllerDecision).join(PlanRevision,
        PlanRevision.id==ControllerDecision.plan_revision_id).where(
        PlanRevision.lineage_id==parent.lineage_id,ControllerDecision.scope=='SIMULATED',
        ControllerDecision.action=='APPROVE').order_by(
        ControllerDecision.resulting_operational_revision.desc()).limit(1))
    if current and current.plan_revision_id!=parent.id:
        raise HTTPException(409,'SOURCE_APPROVAL_SUPERSEDED')
    source=next((a for a in raw['approvals'] if current and a['decision_id']==str(current.id)),None)
    if not source:raise HTTPException(409,'ACTIVE_SOURCE_APPROVAL_REQUIRED')
    if source['plan_hash']!=source['actual_plan_hash']:raise HTTPException(409,'SOURCE_PLAN_HASH_MISMATCH')
    snapshot=db.get(PlanningSnapshot,parent.snapshot_id)
    if snapshot.scenario_id or (snapshot.manifest.get('validation_context') or {}).get('scope')!='SIMULATED':
        raise HTTPException(409,'SIMULATED_NON_SCENARIO_REPLANNING_ONLY')
    freeze=freeze_context(db,'SIMULATED',now,parent.lineage_id)
    commitments=[];blockers={b for c in freeze['commitments'] for b in c['blockers']}
    if raw['policy'] is None:blockers.add('FREEZE_POLICY_UNKNOWN')
    tracks=set(snapshot.manifest['track_ids'])
    resources={r['id'] for r in snapshot.manifest['facts']['resources']}
    released={(r['decision_id'],r['candidate_id']):r for r in raw['releases']}
    for other in raw['approvals']:
        if other['decision_id']==source['decision_id']:continue
        if not other['reservations']:continue
        if any(tracks.intersection(a['track_ids']) or resources.intersection(x['resource_id'] for x in a['allocations'])
                for a in other['assignments'] if (other['decision_id'],a['id']) not in released):blockers.add('OTHER_APPROVED_COMMITMENT_REQUIRES_RECONCILIATION')
    latest={r['request_id']:r for r in raw['execution'] if r['decision_id']==source['decision_id']}
    by_id={a['id']:a for a in source['assignments']}
    for frozen in freeze['commitments']:
        assignment=by_id[frozen['candidate_id']]
        commitments.append({'id':source['decision_id']+':'+assignment['id'],'candidate_id':assignment['id'],
            'frozen':frozen['frozen'],'assignment_hash':digest(assignment),'assignment':assignment})
        for task in assignment['tasks']:
            observed=latest.get(task['request_id'])
            if not observed:continue
            if observed['status']=='COMPLETED':blockers.add('COMPLETED_WORK_RESTORATION_UNVERIFIED')
            elif observed['status'] in ('INTERRUPTED','RESUMED'):
                blockers.add('REMAINING_WORK_RECONCILIATION_REQUIRED')
            elif (datetime.fromisoformat(observed['observed_at'])!=datetime.fromisoformat(task['work_start'])
                    or now>=datetime.fromisoformat(task['work_end'])):
                blockers.add('EXECUTION_TIMING_RECONCILIATION_REQUIRED')
    completed=[]
    for r in {r['request_id']:r for r in raw['execution']}.values():
        if r['status']!='COMPLETED':continue
        release=released.get((r['decision_id'],r['candidate_id']))
        if r['decision_id']!=source['decision_id'] and release is None:continue
        completed.append({'id':r['id'],'request_id':r['request_id'],'verified':True,'completed_at':r['observed_at'],
            'restoration_verified':release is not None,'restored_at':release['payload']['restored_at'] if release else None})
    return {'version':'REPLANNING_CAPTURE_V1','captured_at':now.isoformat(),
        'source_plan_revision_id':str(parent.id),'source_snapshot_id':str(parent.snapshot_id),
        'source_decision_id':source['decision_id'],'source_plan_hash':parent.plan_hash,
        'ledger':raw,'ledger_hash':digest(raw),'commitments':commitments,'completed_work':completed,
        'released_possessions':raw['releases'],
        'blockers':sorted(blockers),'authority':'SOFTWARE_PROPOSAL_ONLY'}


def current_capture(db,row):
    return digest(row.payload)==row.content_hash and digest(ledger(db))==row.payload['ledger_hash']


def attach_capture(db,body,base):
    row=db.get(ReplanningCapture,body.replanning_capture_id)
    if not row:raise HTTPException(422,'REPLANNING_CAPTURE_NOT_FOUND')
    if body.scenario_id:raise HTTPException(422,'REPLANNING_SCENARIO_NOT_SUPPORTED')
    if not current_capture(db,row):raise HTTPException(409,'REPLANNING_CAPTURE_STALE')
    source=db.get(PlanningSnapshot,uuid.UUID(row.payload['source_snapshot_id']))
    if set(body.track_ids)!=set(source.manifest['track_ids']):raise HTTPException(422,'REPLANNING_TRACK_SCOPE_CHANGED')
    # Keep original stage/resource history within the horizon. Truncating ongoing
    # possession stages is not a valid way to account for executed work.
    for c in row.payload['commitments']:
        a=c['assignment']
        if c['frozen'] and not (body.horizon_start<=datetime.fromisoformat(a['possession_start'])
                and datetime.fromisoformat(a['possession_end'])<=body.horizon_end):
            raise HTTPException(422,'FROZEN_POSSESSION_OUTSIDE_REPLANNING_HORIZON')
    if not body.horizon_start<=datetime.fromisoformat(row.payload['captured_at'])<body.horizon_end:
        raise HTTPException(422,'REPLANNING_TIME_OUTSIDE_HORIZON')
    completed={c['request_id'] for c in row.payload['completed_work']}
    requests=copy.deepcopy([r for r in base['requests'] if r['id'] not in completed])
    resources=copy.deepcopy(base['resources'])
    reconciliations={r['id']:r for r in row.payload['ledger'].get('reconciliations',[])}
    for release in row.payload.get('released_possessions',[]):
        if release['decision_id']==row.payload['source_decision_id']:
            for rid,reconciliation_id in release['payload']['reconciliation_ids'].items():
                reconciliation=reconciliations[reconciliation_id];p=reconciliation['payload']
                target=next((r for r in requests if r['id']==rid),None)
                if target!=reconciliation['result']['source_request']:raise HTTPException(409,'RECONCILED_REQUEST_CHANGED')
                target['source_request']=copy.deepcopy(target)
                target['execution_basis']={'reconciliation_id':reconciliation_id,'release_id':release['id']}
                target['payload'].update(work_minutes=p['remaining_work_minutes'],setup_minutes=p['restart_setup_minutes'],
                    restore_minutes=p['restart_restore_minutes'],earliest_at=max(datetime.fromisoformat(p['earliest_restart_at']),
                        datetime.fromisoformat(release['payload']['restored_at']),datetime.fromisoformat(target['payload']['earliest_at'])).isoformat())
        for duty in release['result']['actual_resource_duties']:
            resource=next((r for r in resources if r['id']==duty['resource_id']),None)
            if resource and resource.get('profile'):
                resource.setdefault('source_profile',copy.deepcopy(resource['profile']))
                resource['profile']['payload']['duties'].append({k:v for k,v in duty.items() if k!='resource_id'})
    return {**base,'requests':requests,'resources':resources,
        'replanning':[{'id':str(row.id),'content_hash':row.content_hash,'payload':row.payload}],
        'commitments':row.payload['commitments'],'completed_work':row.payload['completed_work'],
        'execution':row.payload['ledger']['execution'],'released_possessions':row.payload.get('released_possessions',[])}


def snapshot_capture_current(db,snapshot):
    captures=snapshot.manifest['facts'].get('replanning',[])
    if len(captures)!=1:return False
    evidence=captures[0]
    row=db.get(ReplanningCapture,uuid.UUID(evidence['id']))
    return bool(row and evidence['content_hash']==row.content_hash and evidence['payload']==row.payload
        and not row.payload['blockers'] and current_capture(db,row))
