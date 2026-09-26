"""Independent M16 checks from captured approval and execution evidence.

Do not import freeze, opportunity, coordination, resource or optimizer helpers.
"""
from collections import defaultdict
from datetime import timedelta
from .validator import content_hash,instant


def inspect_handoff(v,ledger,approvals,previous,record):
    """Independently reconstruct a transition across two approved decisions."""
    source=approvals.get(previous['decision_id']);target=approvals.get(record['decision_id'])
    if not source or not target:raise ValueError('CONTINUATION_APPROVAL_UNKNOWN')
    stored=target.get('replacement');decision=target.get('approval_replacement')
    if not stored or not decision:raise ValueError('CONTINUATION_REPLACEMENT_PROVENANCE_MISSING')
    p=stored.get('payload') or {}
    v.check(content_hash(p)==stored.get('content_hash') and
        p.get('source_decision_id')==previous['decision_id'] and
        p.get('source_plan_revision_id')==source['plan_revision_id'] and
        p.get('source_plan_hash')==source['plan_hash']==source['actual_plan_hash'] and
        p.get('replacement_plan_hash')==target['plan_hash']==target['actual_plan_hash'] and
        source['lineage_id']==target['lineage_id'] and
        p.get('capture_id')==decision.get('capture_id') and
        p.get('source_decision_id')==decision.get('source_decision_id') and
        p.get('source_plan_revision_id')==decision.get('source_plan_revision_id') and
        stored.get('content_hash')==decision.get('difference_hash'),
        'PROVENANCE','CONTINUATION_REPLACEMENT_MISMATCH')
    changes=[x for x in p.get('changes',[]) if x.get('request_id')==record['request_id']]
    old=next((a for a in source['assignments'] if a['id']==previous['candidate_id']),None)
    new=next((a for a in target['assignments'] if a['id']==record['candidate_id']),None)
    if len(changes)!=1 or not old or not new:raise ValueError('CONTINUATION_ASSIGNMENT_UNKNOWN')
    change=changes[0];before=change.get('before');after=change.get('after')
    v.check(before is not None and after is not None and
        before['candidate_id']==previous['candidate_id'] and
        before['assignment_hash']==previous['assignment_hash']==content_hash(old) and
        after['candidate_id']==record['candidate_id'] and
        after['assignment_hash']==record['assignment_hash']==content_hash(new),
        'PROVENANCE','CONTINUATION_DIFFERENCE_MISMATCH')
    info=record.get('result',{}).get('continuation') or {}
    v.check(info.get('source_decision_id')==previous['decision_id'] and
        info.get('source_execution_record_id')==previous['id'] and
        info.get('source_assignment_hash')==previous['assignment_hash'],
        'PROVENANCE','CONTINUATION_RECORD_LINK_MISMATCH')
    if change.get('change')=='UNCHANGED':
        released=any(r['decision_id']==previous['decision_id'] and r['candidate_id']==previous['candidate_id']
            for r in ledger.get('releases',[]))
        v.check(not released and previous['status']=='STARTED' and
            previous['assignment_hash']==record['assignment_hash'] and
            info.get('kind')=='PRESERVED_ASSIGNMENT' and
            info.get('release_id') is None and info.get('reconciliation_id') is None,
            'COMMITMENTS','PRESERVED_CONTINUATION_INVALID')
        return
    if change.get('change')!='REMAINING_WORK_RESCHEDULED':
        v.check(False,'COMMITMENTS','CONTINUATION_WITHOUT_RELEASED_REMAINING_WORK')
        return
    release=next((r for r in ledger.get('releases',[]) if r['decision_id']==previous['decision_id']
        and r['candidate_id']==previous['candidate_id']),None)
    if not release:raise ValueError('CONTINUATION_RELEASE_UNKNOWN')
    assessment_id=release['payload']['reconciliation_ids'].get(record['request_id'])
    assessment=next((r for r in ledger.get('reconciliations',[]) if r['id']==assessment_id),None)
    if not assessment:raise ValueError('CONTINUATION_ASSESSMENT_UNKNOWN')
    rp=assessment['payload']
    task=next((t for t in new['tasks'] if t['request_id']==record['request_id']),None)
    if not task:raise ValueError('CONTINUATION_TASK_UNKNOWN')
    v.check(previous['status']=='INTERRUPTED' and record['status']=='RESUMED' and
        assessment['execution_record_id']==previous['id'] and
        rp['verified'] is True and release['payload']['verified'] is True and
        rp['remaining_work_minutes']==record['payload']['remaining_work_minutes'] and
        (instant(task['work_end'])-instant(task['work_start'])).total_seconds()==60*rp['remaining_work_minutes'] and
        info.get('kind')=='VERIFIED_RESIDUAL_RESTART' and
        info.get('release_id')==release['id'] and info.get('reconciliation_id')==assessment['id'] and
        instant(record['observed_at'])>=instant(release['payload']['restored_at']) and
        instant(record['observed_at'])>=instant(rp['earliest_restart_at']),
        'COMMITMENTS','RESIDUAL_CONTINUATION_INVALID')


def inspect_replanning(inspector):
    v=inspector
    captures=v.facts.get('replanning',[])
    if not captures:return
    if len(captures)!=1:raise ValueError('AMBIGUOUS_REPLANNING_CAPTURE')
    evidence=captures[0];capture=evidence['payload'];ledger=capture['ledger']
    v.check(content_hash(capture)==evidence['content_hash'],'PROVENANCE','REPLANNING_CAPTURE_HASH_MISMATCH')
    v.check(content_hash(ledger)==capture['ledger_hash'],'PROVENANCE','REPLANNING_LEDGER_HASH_MISMATCH')
    v.check(ledger['scope']=='SIMULATED' and v.manifest['scenario_id'] is None,
        'COMMITMENTS','REPLANNING_SCOPE_UNSUPPORTED',error=True)
    at=instant(capture['captured_at'])
    v.check(v.start<=at<v.end and at<=v.checked_at,'TIMING','REPLANNING_CAPTURE_TIME_INVALID')
    policy=ledger['policy']
    if not policy or type(policy['freeze_minutes'])!=int or not 0<=policy['freeze_minutes']<=10080:
        raise ValueError('FREEZE_POLICY_UNKNOWN_OR_INVALID')
    cutoff=at+timedelta(minutes=policy['freeze_minutes'])
    approvals=[a for a in ledger['approvals'] if a['decision_id']==capture['source_decision_id']]
    if len(approvals)!=1:raise ValueError('SOURCE_APPROVAL_UNKNOWN')
    source=approvals[0]
    v.check(source['plan_revision_id']==capture['source_plan_revision_id'] and
        source['plan_hash']==source['actual_plan_hash']==capture['source_plan_hash'],
        'PROVENANCE','SOURCE_APPROVAL_IDENTITY_MISMATCH')
    originals={a['id']:a for a in source['assignments']}
    if len(originals)!=len(source['assignments']):raise ValueError('DUPLICATE_APPROVED_ASSIGNMENT')
    released_keys={(r['decision_id'],r['candidate_id']) for r in ledger.get('releases',[])}
    for other in ledger['approvals']:
        if other['decision_id']==source['decision_id']:continue
        if not other['reservations']:continue
        overlaps_scope=any(set(v.manifest['track_ids']).intersection(a['track_ids']) or
            set(v.resources).intersection(x['resource_id'] for x in a['allocations']) for a in other['assignments']
            if (other['decision_id'],a['id']) not in released_keys)
        v.check(not overlaps_scope,'COMMITMENTS','OTHER_APPROVED_COMMITMENT_REQUIRES_RECONCILIATION',error=True)
    grouped=defaultdict(list)
    approval_by_id={a['decision_id']:a for a in ledger['approvals']}
    if len(approval_by_id)!=len(ledger['approvals']):raise ValueError('DUPLICATE_APPROVAL_EVIDENCE')
    for record in ledger['execution']:
        v.tick()
        v.check(content_hash(record['payload'])==record['payload_hash'],'PROVENANCE','EXECUTION_PAYLOAD_HASH_MISMATCH')
        owning=approval_by_id.get(record['decision_id'])
        if not owning:raise ValueError('EXECUTION_APPROVAL_UNKNOWN')
        original=next((a for a in owning['assignments'] if a['id']==record['candidate_id']),None)
        v.check(original is not None and content_hash(original)==record['assignment_hash'],
            'PROVENANCE','EXECUTION_APPROVED_ASSIGNMENT_MISMATCH')
        v.check(record['payload']['verified'] is True and instant(record['observed_at'])<=instant(record['received_at'])<=at,
            'COMMITMENTS','EXECUTION_OBSERVATION_UNVERIFIED_OR_FUTURE')
        v.check(record['payload']['status']==record['status'] and record['payload']['request_id']==record['request_id']
            and instant(record['payload']['observed_at'])==instant(record['observed_at'])
            and record['payload']['decision_id']==record['decision_id']
            and record['payload']['candidate_id']==record['candidate_id']
            and record['payload']['expected_assignment_hash']==record['assignment_hash'],
            'PROVENANCE','EXECUTION_OBSERVATION_IDENTITY_MISMATCH')
        grouped[record['request_id']].append(record)
    latest={}
    transitions={None:{'STARTED'},'STARTED':{'COMPLETED','INTERRUPTED'},'INTERRUPTED':{'RESUMED'},
        'RESUMED':{'COMPLETED','INTERRUPTED'},'COMPLETED':set()}
    for rid,records in grouped.items():
        previous=None
        for index,record in enumerate(sorted(records,key=lambda r:r['sequence']),1):
            prior=previous['status'] if previous else None
            v.check(record['sequence']==index and record['status'] in transitions.get(prior,set()),
                'COMMITMENTS','EXECUTION_LIFECYCLE_INVALID',{'request_id':rid})
            if previous:
                v.check(instant(previous['observed_at'])<instant(record['observed_at']),
                    'COMMITMENTS','EXECUTION_OBSERVATION_ORDER_INVALID')
                if previous['decision_id']!=record['decision_id']:
                    inspect_handoff(v,ledger,approval_by_id,previous,record)
            previous=record
        latest[rid]=previous
    commitments={c['candidate_id']:c for c in v.facts.get('commitments',[])}
    from .validator_restoration import inspect_restoration
    released=inspect_restoration(v,ledger,source)
    outstanding={cid for cid in originals if (source['decision_id'],cid) not in released}
    v.check(len(commitments)==len(v.facts.get('commitments',[])) and set(commitments)==outstanding,
        'COMMITMENTS','APPROVED_COMMITMENT_COVERAGE_MISMATCH')
    v.check(v.facts.get('execution')==ledger['execution'],'PROVENANCE','EXECUTION_SNAPSHOT_EVIDENCE_MISMATCH')
    v.check(v.facts.get('commitments')==capture['commitments'],'PROVENANCE','COMMITMENT_CAPTURE_MISMATCH')
    for cid,original in originals.items():
        if cid not in outstanding:continue
        observations=[latest[r] for r in original['request_ids'] if r in latest]
        start=instant(original['possession_start'])
        frozen=bool(observations) or start<=at or start<cutoff
        c=commitments.get(cid)
        v.check(c is not None and c['frozen'] is frozen and c.get('assignment_hash')==content_hash(original)
            and c.get('assignment')==original,'COMMITMENTS','FROZEN_DERIVATION_MISMATCH',{'candidate_id':cid})
        if start<=v.checked_at:
            v.check(all(r in latest for r in original['request_ids']),'COMMITMENTS','EXECUTION_STATE_UNKNOWN',error=True)
        for task in original['tasks']:
            record=latest.get(task['request_id'])
            if not record:continue
            # Only unchanged, verified ongoing work is representable in this slice.
            # Completed work still needs restoration; interruptions need a new
            # remaining-work specification. Neither is silently rescheduled.
            v.check(record['status']=='STARTED','COMMITMENTS','EXECUTION_RECONCILIATION_REQUIRED',error=True)
            if record['status']=='STARTED':
                v.check(instant(record['observed_at'])==instant(task['work_start']) and v.checked_at<instant(task['work_end']),
                    'COMMITMENTS','EXECUTION_TIMING_RECONCILIATION_REQUIRED',error=True)
        currently_frozen=bool(observations) or start<=v.checked_at or start<v.checked_at+timedelta(minutes=policy['freeze_minutes'])
        if currently_frozen:
            actual=next((b for b in v.blocks if b['id']==cid),None)
            v.check(actual is not None and content_hash(actual)==content_hash(original),
                'COMMITMENTS','FROZEN_WORK_CHANGED',{'candidate_id':cid})
    for block in v.blocks:
        c=commitments.get(block['id'])
        v.check(instant(block['possession_start'])>=v.checked_at or bool(c and c['frozen'] and
            c.get('assignment_hash')==content_hash(block)),'TIMING','NEW_WORK_BEFORE_REPLANNING_TIME',{'candidate_id':block['id']})
    all_latest={r['request_id']:r for r in sorted(ledger['execution'],key=lambda r:r['sequence'])}
    completed={rid for rid,r in all_latest.items() if r['status']=='COMPLETED' and
        (r['decision_id']==source['decision_id'] or (r['decision_id'],r['candidate_id']) in released)}
    v.check({c['request_id'] for c in v.facts.get('completed_work',[])}==completed,
        'COMMITMENTS','COMPLETED_WORK_EVIDENCE_MISMATCH')
    v.check(not completed.intersection(v.requests),'COVERAGE','COMPLETED_WORK_IN_PENDING_DEMAND')
    for c in v.facts.get('completed_work',[]):
        r=all_latest.get(c['request_id'])
        release=released.get((r['decision_id'],r['candidate_id'])) if r else None
        v.check(c['restoration_verified']==bool(release) and (not release or
            instant(c['restored_at'])==instant(release['payload']['restored_at'])),
            'COMMITMENTS','COMPLETED_RESTORATION_EVIDENCE_MISMATCH')
    v.check(not capture['blockers'],'COMMITMENTS','CAPTURE_REQUIRES_ATTENTION',{'blockers':capture['blockers']},error=True)
