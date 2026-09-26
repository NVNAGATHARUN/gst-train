"""Verify an execution observation crossing one approved replacement boundary.

This is observation provenance, not permission to operate a railway possession.
The old and new decisions must be joined by the immutable captured snapshot.
"""
import uuid
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from .models import PlanRevision, PossessionRelease, WorkReconciliation
from .requests import digest


def continuation(db,revision,approval,snapshot,previous,assignment,task,body):
    stored=revision.edit.get('replacement')
    captures=snapshot.manifest['facts'].get('replanning',[])
    if not stored or len(captures)!=1:
        raise HTTPException(409,'EXECUTION_ASSIGNMENT_CHANGED')
    evidence=stored.get('payload') or {};captured=captures[0]
    result=approval.result.get('replacement') or {}
    if (stored.get('content_hash')!=digest(evidence) or
            evidence.get('replacement_plan_hash')!=revision.plan_hash or
            evidence.get('replacement_snapshot_id')!=str(snapshot.id) or
            evidence.get('replacement_snapshot_hash')!=snapshot.content_hash or
            evidence.get('capture_id')!=captured['id'] or
            evidence.get('capture_hash')!=captured['content_hash'] or
            captured['content_hash']!=digest(captured['payload']) or
            evidence.get('source_decision_id')!=str(previous.decision_id) or
            evidence.get('source_plan_revision_id')!=str(previous.plan_revision_id) or
            result.get('source_decision_id')!=str(previous.decision_id) or
            result.get('source_plan_revision_id')!=str(previous.plan_revision_id) or
            result.get('capture_id')!=captured['id'] or
            result.get('difference_hash')!=stored['content_hash'] or
            captured['payload']['source_decision_id']!=str(previous.decision_id) or
            captured['payload']['source_plan_revision_id']!=str(previous.plan_revision_id)):
        raise HTTPException(409,'CONTINUATION_SOURCE_MISMATCH')
    source=db.get(PlanRevision,previous.plan_revision_id)
    if (not source or source.lineage_id!=revision.lineage_id or
            source.plan_hash!=evidence.get('source_plan_hash') or digest(source.content)!=source.plan_hash):
        raise HTTPException(409,'CONTINUATION_SOURCE_PLAN_MISMATCH')
    prior=next((r for r in captured['payload']['ledger']['execution'] if r['id']==str(previous.id)),None)
    if (not prior or prior['decision_id']!=str(previous.decision_id) or
            prior['plan_revision_id']!=str(previous.plan_revision_id) or
            prior['request_id']!=previous.request_id or prior['sequence']!=previous.sequence or
            prior['status']!=previous.status or prior['candidate_id']!=previous.candidate_id or
            prior['assignment_hash']!=previous.assignment_hash or
            prior['payload_hash']!=previous.payload_hash or prior['payload']!=previous.payload or
            datetime.fromisoformat(prior['observed_at'])!=previous.observed_at):
        raise HTTPException(409,'CONTINUATION_PRIOR_OBSERVATION_NOT_CAPTURED')
    changes=[x for x in evidence.get('changes',[]) if x['request_id']==previous.request_id]
    if len(changes)!=1:raise HTTPException(409,'CONTINUATION_DIFFERENCE_MISSING')
    change=changes[0];before=change['before'];after=change['after']
    if (not before or not after or before['candidate_id']!=previous.candidate_id or
            before['assignment_hash']!=previous.assignment_hash or
            after['candidate_id']!=assignment['id'] or after['assignment_hash']!=digest(assignment)):
        raise HTTPException(409,'CONTINUATION_DIFFERENCE_MISMATCH')
    if change['change']=='UNCHANGED':
        if (previous.status!='STARTED' or previous.assignment_hash!=digest(assignment) or
                db.scalar(select(PossessionRelease.id).where(PossessionRelease.decision_id==previous.decision_id,
                    PossessionRelease.candidate_id==previous.candidate_id))):
            raise HTTPException(409,'UNCHANGED_CONTINUATION_NOT_ELIGIBLE')
        return {'kind':'PRESERVED_ASSIGNMENT','source_decision_id':str(previous.decision_id),
            'source_execution_record_id':str(previous.id),'source_assignment_hash':previous.assignment_hash,
            'release_id':None,'reconciliation_id':None}
    if change['change']!='REMAINING_WORK_RESCHEDULED' or previous.status!='INTERRUPTED' or body.status!='RESUMED':
        raise HTTPException(409,'RELEASED_REMAINING_WORK_REQUIRED')
    request=next((r for r in snapshot.manifest['facts']['requests'] if r['id']==previous.request_id),None)
    basis=request.get('execution_basis') if request else None
    if not basis:raise HTTPException(409,'RESIDUAL_EXECUTION_BASIS_MISSING')
    release=db.get(PossessionRelease,uuid.UUID(basis['release_id']))
    assessment=db.get(WorkReconciliation,uuid.UUID(basis['reconciliation_id']))
    if (not release or not assessment or release.decision_id!=previous.decision_id or
            release.candidate_id!=previous.candidate_id or
            release.payload_hash!=digest(release.payload) or
            assessment.payload_hash!=digest(assessment.payload) or
            assessment.execution_record_id!=previous.id or
            release.payload['reconciliation_ids'].get(previous.request_id)!=str(assessment.id) or
            not all(release.payload.get(k) is True for k in
                ('verified','track_restored','electrical_restored','signalling_restored','all_resources_clear')) or
            assessment.payload.get('verified') is not True or
            request['payload']['work_minutes']!=assessment.payload['remaining_work_minutes'] or
            body.remaining_work_minutes!=assessment.payload['remaining_work_minutes'] or
            task['request_revision']!=request['revision'] or
            datetime.fromisoformat(release.payload['restored_at'])>body.observed_at or
            datetime.fromisoformat(assessment.payload['earliest_restart_at'])>body.observed_at):
        raise HTTPException(409,'RESIDUAL_CONTINUATION_EVIDENCE_MISMATCH')
    captured_release=next((r for r in captured['payload']['ledger']['releases'] if r['id']==str(release.id)),None)
    captured_assessment=next((r for r in captured['payload']['ledger']['reconciliations'] if r['id']==str(assessment.id)),None)
    if (not captured_release or captured_release['payload_hash']!=release.payload_hash or
            captured_release['payload']!=release.payload or not captured_assessment or
            captured_assessment['payload_hash']!=assessment.payload_hash or
            captured_assessment['payload']!=assessment.payload):
        raise HTTPException(409,'RESIDUAL_EVIDENCE_NOT_CAPTURED')
    return {'kind':'VERIFIED_RESIDUAL_RESTART','source_decision_id':str(previous.decision_id),
        'source_execution_record_id':str(previous.id),'source_assignment_hash':previous.assignment_hash,
        'release_id':str(release.id),'reconciliation_id':str(assessment.id)}
