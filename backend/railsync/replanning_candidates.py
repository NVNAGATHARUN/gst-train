"""Recheck saved approved alternatives against current candidate-engine facts."""
import copy
from .requests import digest
from .resource_engine import dt,resource_feasible
from .coordination_engine import compatibility,make_tasks,task_checks,signature


def preserve_candidates(manifest,windows,policy,policy_id,horizon):
    facts=manifest['facts'];requests={r['id']:r for r in facts['requests']}
    resources={r['id']:r for r in facts['resources']};network={r['id']:r for r in facts['network']}
    cutoff=dt(facts['replanning'][0]['payload']['captured_at'])
    retained=[];excluded=[]
    for commitment in facts['commitments']:
        candidate=commitment['assignment'];failures=[]
        if digest(candidate)!=commitment['assignment_hash'] or candidate['id']!=commitment['candidate_id']:
            failures.append('APPROVED_ASSIGNMENT_HASH_MISMATCH')
        start,end=dt(candidate['possession_start']),dt(candidate['possession_end'])
        if start<cutoff and not commitment['frozen']:failures.append('PAST_ASSIGNMENT_NOT_FROZEN')
        if not horizon[0]<=start<end<=horizon[1]:failures.append('APPROVED_ASSIGNMENT_OUTSIDE_HORIZON')
        if candidate['policy_revision_id']!=policy_id:failures.append('APPROVED_COORDINATION_POLICY_CHANGED')
        group=[requests[t['request_id']] for t in candidate['tasks'] if t['request_id'] in requests]
        if len(group)!=len(candidate['tasks']):failures.append('APPROVED_REQUEST_MISSING_OR_COMPLETED')
        else:
            modes,refs,code=compatibility(group,policy)
            if code or candidate['mode'] not in modes or refs!=candidate['rule_ids']:
                failures.append(code or 'APPROVED_COMPATIBILITY_CHANGED')
            tasks,expected_end=make_tasks(group,candidate['mode'],start)
            if tasks!=candidate['tasks'] or end!=expected_end:failures.append('APPROVED_TASK_FACTS_CHANGED')
            code=task_checks(tasks,requests,{c['request_id']:c for c in facts.get('completed_work',[])})
            if code:failures.append(code)
            footprint=set()
            for r in group:
                p=r['payload'];footprint.update(p['footprint'])
                if signature(r)['power_state']=='OFF':
                    zone=network.get(p['isolation_zone'])
                    if not zone:failures.append('ISOLATION_MAPPING_UNKNOWN')
                    else:footprint.update(zone['payload']['footprint'])
            if footprint!=set(candidate['track_ids']):failures.append('APPROVED_FOOTPRINT_CHANGED')
        for track in candidate['track_ids']:
            if not any(a<=start and end<=b for a,b in windows.get(track,[])):
                failures.append('APPROVED_WINDOW_NO_LONGER_AVAILABLE')
            if track not in network or network[track]['payload'].get('status')!='OPEN':failures.append('TRACK_CLOSED_OR_UNKNOWN')
        travel=0
        for resource_id in {a['resource_id'] for a in candidate['allocations']}:
            unit=resources.get(resource_id)
            if not unit:failures.append('APPROVED_RESOURCE_MISSING');continue
            allocations=[a for a in candidate['allocations'] if a['resource_id']==resource_id]
            valid,code,movement=resource_feasible(unit,allocations,policy,horizon)
            if not valid:failures.append(code)
            else:travel+=movement-resource_feasible(unit,[],policy,horizon)[2]
        exposure=sum(max(0,int((min(end,dt(f['end_at']))-max(start,dt(f['start_at']))).total_seconds()))*
            f['expected_count'] for f in facts['freight'] if f['track_id'] in candidate['track_ids'])
        costs={'reserved_track_minutes':int((end-start).total_seconds()/60)*len(candidate['track_ids']),
            'forecast_exposure_train_track_seconds':exposure,'incremental_travel_minutes_against_fixed_duties':travel}
        if costs!=candidate['costs']:failures.append('APPROVED_COST_FACTS_CHANGED')
        if failures:excluded.append({'request_ids':candidate['request_ids'],'candidate_id':candidate['id'],
            'code':'APPROVED_CANDIDATE_RECHECK_FAILED','details':sorted(set(failures)),'frozen':commitment['frozen']})
        else:retained.append(copy.deepcopy(candidate))
    return retained,excluded
