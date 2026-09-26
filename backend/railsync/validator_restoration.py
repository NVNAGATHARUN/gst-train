"""Validator-owned restoration, residual-demand and historical-duty checks."""
import copy
from .validator import instant,content_hash


def inspect_restoration(v,ledger,source):
    releases=ledger.get('releases',[])
    v.check(v.facts.get('released_possessions',[])==releases,'PROVENANCE','RELEASE_SNAPSHOT_MISMATCH')
    approvals={a['decision_id']:a for a in ledger['approvals']}
    execution={r['id']:r for r in ledger['execution']}
    reconciliations={r['id']:r for r in ledger.get('reconciliations',[])}
    latest_reconciliation={}
    for r in sorted(reconciliations.values(),key=lambda r:r['revision']):latest_reconciliation[r['execution_record_id']]=r['id']
    released={};duties={};residual_ids=set()
    for release in releases:
        v.tick();p=release['payload'];result=release['result'];key=(release['decision_id'],release['candidate_id'])
        if key in released:raise ValueError('DUPLICATE_POSSESSION_RELEASE')
        released[key]=release
        v.check(content_hash(p)==release['payload_hash'],'PROVENANCE','RELEASE_PAYLOAD_HASH_MISMATCH')
        v.check(p['decision_id']==key[0] and p['candidate_id']==key[1],'PROVENANCE','RELEASE_IDENTITY_MISMATCH')
        approval=approvals.get(key[0])
        original=next((a for a in approval['assignments'] if a['id']==key[1]),None) if approval else None
        if not original:raise ValueError('RELEASE_APPROVAL_UNKNOWN')
        v.check(result['assignment']==original and p['expected_assignment_hash']==content_hash(original)==result['assignment_hash'],
            'PROVENANCE','RELEASE_ASSIGNMENT_MISMATCH')
        v.check(all(p[k] is True for k in ('verified','track_restored','electrical_restored','signalling_restored','all_resources_clear')),
            'COMMITMENTS','RESTORATION_UNVERIFIED',error=True)
        start,restore,end=map(instant,(p['actual_possession_start'],p['restoration_started_at'],p['restored_at']))
        minimum=max((instant(t['restore_end'])-instant(t['restore_start'])).total_seconds() for t in original['tasks'])
        v.check(start<restore<=end<=instant(release['created_at'])<=v.checked_at and (end-restore).total_seconds()>=minimum,
            'TIMING','RESTORATION_TIMING_INVALID')
        v.check(set(p['expected_execution_ids'])==set(original['request_ids']) and p['expected_execution_ids']==result['execution_ids'],
            'COMMITMENTS','RELEASE_BUNDLE_EVIDENCE_INCOMPLETE')
        interrupted=set()
        for rid in original['request_ids']:
            observed=execution.get(p['expected_execution_ids'].get(rid))
            if observed is None:raise ValueError('RELEASE_EXECUTION_UNKNOWN')
            # Later approved replacement work may continue this request. Verify
            # the observation that was latest *when this release committed*.
            at_release=[r for r in ledger['execution'] if r['request_id']==rid and
                r['result']['operational_revision']<result['operational_revision'] and
                instant(r['received_at'])<=instant(release['created_at'])]
            latest_at_release=max(at_release,key=lambda r:r['sequence']) if at_release else None
            v.check(latest_at_release==observed and observed['decision_id']==key[0] and observed['candidate_id']==key[1]
                and observed['assignment_hash']==content_hash(original),'COMMITMENTS','RELEASE_EXECUTION_CHANGED')
            v.check(observed['status'] in ('COMPLETED','INTERRUPTED') and start<=instant(observed['observed_at'])<=restore,
                'COMMITMENTS','RELEASE_WHILE_WORK_ACTIVE_OR_UNKNOWN')
            v.check(all(start<=instant(r['observed_at']) for r in ledger['execution'] if r['request_id']==rid and r['decision_id']==key[0]),
                'TIMING','ACTUAL_POSSESSION_START_INVALID')
            if observed['status']=='COMPLETED':
                v.check(observed['payload']['remaining_work_minutes']==0,'COMMITMENTS','COMPLETION_REMAINING_WORK_NONZERO')
                continue
            interrupted.add(rid)
            reconciliation=reconciliations.get(p['reconciliation_ids'].get(rid))
            if reconciliation is None:raise ValueError('RELEASE_RECONCILIATION_UNKNOWN')
            rp=reconciliation['payload'];prior=reconciliation['result']['source_request']
            v.check(content_hash(rp)==reconciliation['payload_hash'] and reconciliation['execution_record_id']==observed['id']
                and latest_reconciliation[observed['id']]==reconciliation['id'],'PROVENANCE','RECONCILIATION_EVIDENCE_CHANGED')
            v.check(rp['verified'] is True and prior['id']==rid and rp['expected_request_revision']==prior['revision']
                and type(rp['remaining_work_minutes']) is int and 0<rp['remaining_work_minutes']<=prior['payload']['work_minutes'],
                'COMMITMENTS','REMAINING_WORK_UNVERIFIED_OR_INVALID')
            known=observed['payload']['remaining_work_minutes']
            v.check(known is None or known==rp['remaining_work_minutes'],'COMMITMENTS','OBSERVED_REMAINING_WORK_MISMATCH')
            v.check(instant(rp['earliest_restart_at'])>=instant(observed['observed_at']) and
                instant(observed['received_at'])<=instant(reconciliation['created_at'])<=instant(release['created_at']),
                'TIMING','RECONCILIATION_TIME_INVALID')
            if key[0]==source['decision_id']:
                residual_ids.add(rid);target=v.requests.get(rid)
                expected=copy.deepcopy(prior['payload'])
                expected.update(work_minutes=rp['remaining_work_minutes'],setup_minutes=rp['restart_setup_minutes'],
                    restore_minutes=rp['restart_restore_minutes'],earliest_at=max(instant(prior['payload']['earliest_at']),
                        instant(rp['earliest_restart_at']),end))
                valid=target is not None
                if target:
                    actual=copy.deepcopy(target['payload']);actual['earliest_at']=instant(actual['earliest_at'])
                    valid=(actual==expected and target.get('source_request')==prior and target['revision']==prior['revision']
                        and target.get('execution_basis')=={'reconciliation_id':reconciliation['id'],'release_id':release['id']})
                v.check(valid,'COMMITMENTS','RESIDUAL_REQUEST_DERIVATION_MISMATCH',{'request_id':rid})
        v.check(set(p['reconciliation_ids'])==interrupted,'COMMITMENTS','RECONCILIATION_COVERAGE_MISMATCH')
        expected_duties=[]
        for uid in sorted({a['resource_id'] for a in original['allocations']}):
            locations={a['track_id'] for a in original['allocations'] if a['resource_id']==uid}
            if len(locations)!=1:raise ValueError('ACTUAL_RESOURCE_LOCATION_UNKNOWN')
            duty={'resource_id':uid,'track_id':next(iter(locations)),'start_at':p['actual_possession_start'],'end_at':p['restored_at']}
            expected_duties.append(duty)
            duties.setdefault(uid,[]).append({k:value for k,value in duty.items() if k!='resource_id'})
        v.check(result['actual_resource_duties']==expected_duties,'RESOURCES','RELEASE_DUTY_ACCOUNTING_MISMATCH')
        v.check(not any(r['id']==release['reservation_id'] for r in approval['reservations']),
            'COMMITMENTS','RELEASED_RESERVATION_STILL_ACTIVE')
    for rid,r in v.requests.items():
        v.check(('execution_basis' in r)==(rid in residual_ids),'PROVENANCE','UNEXPLAINED_RESIDUAL_REQUEST',{'request_id':rid})
    for uid,unit in v.resources.items():
        additions=duties.get(uid,[])
        if additions and unit.get('profile'):
            original=unit.get('source_profile')
            if original is None:raise ValueError('SOURCE_RESOURCE_PROFILE_MISSING')
            expected=copy.deepcopy(original);expected['payload']['duties']+=additions
            v.check(unit['profile']==expected,'RESOURCES','EXECUTION_DUTY_HISTORY_MISMATCH',{'resource_id':uid})
    return released
