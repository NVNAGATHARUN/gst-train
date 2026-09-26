"""Finite, timed candidates; this module neither selects nor approves a schedule."""
from collections import defaultdict
from datetime import timedelta
from itertools import combinations, permutations, islice
import math
from pydantic import ValidationError
from .requests import digest
from .intervals import common_windows
from .opportunities import grid_starts
from .coordination_schema import CoordinationPolicy, ResourceProfile
from .resource_engine import (dt, period, overlap, allocate, resource_feasible,
                              pool_constraints, duty_constraints)

def signature(request):
    p=request['payload']
    return {'department':p['department'],'issue_type':p['issue_type'],
            'power_state':'OFF' if p['power_block_required'] else p.get('power_state','UNKNOWN'),
            'signalling_state':p.get('signalling_state','UNKNOWN')}

def relation(a,b):
    a,b=set(a),set(b)
    return 'SAME' if a==b else 'OVERLAP' if a&b else 'DISJOINT'

def compatibility(group, policy):
    if len(group)==1:return ['SINGLE'],[],None
    modes=[]
    references=[]
    shared=True
    for left,right in combinations(group,2):
        signatures=sorted([signature(left),signature(right)],key=digest)
        footprint_relation=relation(left['payload']['footprint'],right['payload']['footprint'])
        matches=[r for r in policy['pairs'] if r['footprint_relation']==footprint_relation and
                 sorted([r['left'],r['right']],key=digest)==signatures]
        if len(matches)!=1:return [],references,'COMPATIBILITY_UNKNOWN'
        rule=matches[0]
        if rule['mode'] in ['FORBID','UNKNOWN']:return [],[rule['id']],f"COMPATIBILITY_{rule['mode']}"
        modes.append(rule['mode'])
        references.append(rule['id'])
        shared &= rule['shared_setup'] and rule['shared_restoration']
    for size in range(3,len(group)+1):
        for subset in combinations(group,size):
            members=sorted([signature(r) for r in subset],key=digest)
            matches=[r for r in policy['groups'] if sorted(r['members'],key=digest)==members]
            if len(matches)!=1:return [],references,'GROUP_COMPATIBILITY_UNKNOWN'
            rule=matches[0]
            references.append(rule['id'])
            if rule['mode'] in ['FORBID','UNKNOWN']:return [],references,'GROUP_COMPATIBILITY_FORBIDDEN'
            modes.append(rule['mode'])
    # Mixed permissions cannot silently authorize an unmodeled partial-overlap schedule.
    if len(set(modes))!=1:return [],references,'MIXED_BUNDLE_MODE_UNSUPPORTED'
    mode=modes[0]
    if mode=='ALLOW_PARALLEL':
        if not shared:return [],references,'SHARED_OVERHEAD_NOT_AUTHORIZED'
        for left,right in combinations(group,2):
            a,b=signature(left),signature(right)
            if {a['power_state'],b['power_state']}=={'ON','OFF'}:
                return [],references,'CONTRADICTORY_POWER_STATES'
            if {a['signalling_state'],b['signalling_state']}=={'CONNECTED','DISCONNECTED'}:
                return [],references,'CONTRADICTORY_SIGNALLING_STATES'
    return [mode],references,None

def make_tasks(group,mode,start):
    tasks=[]
    shared_setup=max(r['payload']['setup_minutes'] for r in group)
    shared_restore=max(r['payload']['restore_minutes'] for r in group)
    if mode=='ALLOW_PARALLEL':
        end=start+timedelta(minutes=shared_setup+max(r['payload']['work_minutes'] for r in group)+shared_restore)
    else:
        end=start+timedelta(minutes=sum(sum(r['payload'][k] for k in ['setup_minutes','work_minutes','restore_minutes']) for r in group))
    cursor=start
    for request in group:
        p=request['payload']
        setup=shared_setup if mode=='ALLOW_PARALLEL' else p['setup_minutes']
        stage_start=start if mode=='ALLOW_PARALLEL' else cursor
        work_start=stage_start+timedelta(minutes=setup)
        work_end=work_start+timedelta(minutes=p['work_minutes'])
        stage_end=end if mode=='ALLOW_PARALLEL' else work_end+timedelta(minutes=p['restore_minutes'])
        restore_start=end-timedelta(minutes=shared_restore) if mode=='ALLOW_PARALLEL' else work_end
        tasks.append({'request_id':request['id'],'request_revision':request['revision'],
            'department':p['department'],'issue_type':p['issue_type'],'track_ids':p['footprint'],
            'resource_location':p.get('resource_location') or p['footprint'][0],
            'setup_start':stage_start.isoformat(),'setup_end':work_start.isoformat(),
            'work_start':work_start.isoformat(),'work_end':work_end.isoformat(),
            'restore_start':restore_start.isoformat(),'restore_end':stage_end.isoformat(),
            'resource_start':stage_start.isoformat(),'resource_end':stage_end.isoformat(),
            'requirements':p['requirements'],'power_state':signature(request)['power_state'],
            'signalling_state':signature(request)['signalling_state'],'isolation_zone':p['isolation_zone']})
        cursor=stage_end
    return tasks,end

def task_checks(tasks,requests,completed=None):
    completed=completed or {}
    by_id={t['request_id']:t for t in tasks}
    for t in tasks:
        p=requests[t['request_id']]['payload']
        if dt(t['work_start'])<dt(p['earliest_at']):return 'EARLIEST_WORK_VIOLATION'
        deadline_time=t['restore_end'] if p['deadline_kind']=='RESTORED_BY' else t['work_end']
        if dt(deadline_time)>dt(p['deadline_at']):return 'DEADLINE_EXCLUDED'
        for predecessor in p['predecessors']:
            if predecessor==t['request_id']:return 'SELF_PRECEDENCE'
            if predecessor not in requests:
                done=completed.get(predecessor)
                if not done or not done.get('restoration_verified'):return 'PREDECESSOR_STATE_UNKNOWN'
                if dt(done['restored_at'])>dt(t['setup_start']):return 'COMPLETED_PREDECESSOR_NOT_RESTORED'
            if predecessor in by_id and dt(by_id[predecessor]['restore_end'])>dt(t['setup_start']):
                return 'INTERNAL_PRECEDENCE_VIOLATION'
    return None

def candidate_conflicts(candidates, resources, policy, horizon, requests):
    units={r['id']:r for r in resources}
    conflicts=[]
    for a,b in combinations(candidates,2):
        reasons=set()
        if set(a['request_ids'])&set(b['request_ids']):reasons.add('DUPLICATE_REQUEST')
        if set(a['track_ids'])&set(b['track_ids']) and overlap(
                (dt(a['possession_start']),dt(a['possession_end'])),
                (dt(b['possession_start']),dt(b['possession_end']))):
            reasons.add('TRACK_POSSESSION_OVERLAP')
        left_units={x['resource_id'] for x in a['allocations']}
        right_units={x['resource_id'] for x in b['allocations']}
        for id in left_units&right_units:
            allocations=[x for c in [a,b] for x in c['allocations'] if x['resource_id']==id]
            valid,code,_=resource_feasible(units[id],allocations,policy,horizon)
            if not valid:reasons.add(code)
        tasks={t['request_id']:t for c in [a,b] for t in c['tasks']}
        for id,t in tasks.items():
            for predecessor in requests[id]['payload']['predecessors']:
                if predecessor in tasks and dt(tasks[predecessor]['restore_end'])>dt(t['setup_start']):
                    reasons.add('PRECEDENCE_VIOLATION')
        if reasons:conflicts.append({'left':a['id'],'right':b['id'],'reasons':sorted(reasons)})
    return conflicts

def coordinate(manifest, opportunities, availability, config):
    facts=manifest['facts']
    requests={r['id']:r for r in facts['requests']}
    resources=facts['resources']
    horizon=(dt(manifest['horizon_start']),dt(manifest['horizon_end']))
    excluded=[]
    pruned=[]
    for exclusion in opportunities['exclusions']:
        if exclusion['code']=='SEARCH_LIMIT_REACHED':
            pruned.append({'code':'UPSTREAM_OPPORTUNITY_PRUNING','evidence':exclusion})
    blockers=['INDEPENDENT_VALIDATION_NOT_YET_PERFORMED']
    result={'status':'DEVELOPMENT_ARTIFACT','candidates':[],'exclusions':excluded,
            'incompatibilities':[],'aggregate_constraints':[],'review_blockers':blockers,
            'search':{'optimality_scope':'generated_candidate_set','pruning':pruned,'configuration':config},
            'counts':{'candidates':0,'bundles':0,'incompatibilities':0}}
    captures=facts.get('replanning',[])
    cutoff=dt(captures[0]['payload']['captured_at']) if captures else None
    if captures and captures[0]['payload']['blockers']:
        result['status']='BLOCKED'
        blockers.extend(captures[0]['payload']['blockers'])
        return result
    records=facts.get('coordination_policies',[])
    if len(records)!=1:
        result['status']='BLOCKED'
        blockers.append('COORDINATION_POLICY_UNKNOWN')
        return result
    policy=records[0]['payload']
    try:
        CoordinationPolicy.model_validate(policy)
        for r in resources:
            if r.get('profile'):ResourceProfile.model_validate(r['profile']['payload'])
    except ValidationError:
        result['status']='BLOCKED'
        blockers.append('SNAPSHOT_RULE_SCHEMA_INVALID')
        return result
    result['policy_evidence']={'id':records[0]['id'],'revision':records[0]['revision'],'hash':digest(policy)}
    if policy['source_mode']=='SIMULATED':blockers.append('SIMULATED_RULES_NOT_OPERATIONAL_AUTHORITY')
    else:blockers.append('IMPORTED_RULES_REQUIRE_DOMAIN_AUTHENTICATION')
    windows_by_track=defaultdict(list)
    policy_by_footprint={}
    for row in availability:
        tracks=tuple(sorted(row['policy']['track_ids']))
        if tracks in policy_by_footprint:
            blockers.append('AMBIGUOUS_AVAILABILITY_POLICY')
            result['status']='BLOCKED'
            return result
        policy_by_footprint[tracks]=row['policy']
        if row['result']['source_conflicts']:
            blockers.append('UNRESOLVED_COA_SOURCE_CONFLICT')
            # Existing synthetic COA fixtures are broad access envelopes. Preserve
            # their diagnostics; imported authoritative disagreements stop generation.
            if any(c['source_mode']=='IMPORTED' for c in facts['coa']):
                result['status']='BLOCKED'
                return result
        for track in tracks:
            windows_by_track[track].append([period(w) for w in row['result']['windows']])
    windows_by_track={track:common_windows(values) for track,values in windows_by_track.items()}
    network={n['id']:n for n in facts['network']}
    scores={c['request_id']:c['priority_basis_points'] for c in opportunities['candidates']}
    eligible=[]
    footprints={}
    for request in sorted(requests.values(),key=lambda r:r['id']):
        p=request['payload']
        code=None
        if request['id'] not in scores:code='NO_TIMED_OPPORTUNITY'
        if 'UNKNOWN' in signature(request).values():code='WORK_STATE_UNKNOWN'
        if len(p['footprint'])>1 and not p.get('resource_location'):code='RESOURCE_LOCATION_UNKNOWN'
        footprint=set(p['footprint'])
        if signature(request)['power_state']=='OFF':
            zone=network.get(p.get('isolation_zone'))
            if not zone or zone['kind']!='isolation':code='ISOLATION_MAPPING_UNKNOWN'
            elif not footprint.issubset(zone['payload']['footprint']):code='ISOLATION_COVERAGE_INCOMPLETE'
            else:footprint.update(zone['payload']['footprint'])
        for track in footprint:
            if track not in network or network[track]['kind']!='track':code='TRACK_UNKNOWN'
            elif network[track]['payload']['status']!='OPEN':code='TRACK_CLOSED'
            if track not in windows_by_track:code='FOOTPRINT_AVAILABILITY_UNKNOWN'
        if code:
            excluded.append({'request_ids':[request['id']],'code':code})
        else:
            footprints[request['id']]=footprint
            eligible.append(request)
    group_count=0
    time_count=0
    candidates={}
    stop=False
    for size in range(1,config['max_bundle_size']+1):
        if size>len(eligible):break
        if size==config['max_bundle_size'] and size<len(eligible):
            pruned.append({'code':'BUNDLE_SIZE_LIMIT','retained_maximum':size})
        for group in combinations(eligible,size):
            if group_count>=config['max_groups']:
                pruned.append({'code':'GROUP_ENUMERATION_LIMIT','retained':group_count})
                stop=True
                break
            group_count+=1
            ids=sorted(r['id'] for r in group)
            modes,refs,code=compatibility(group,policy)
            if code:
                excluded.append({'request_ids':ids,'code':code,'rule_ids':refs})
                continue
            mode=modes[0]
            tracks=sorted(set().union(*(footprints[r['id']] for r in group)))
            windows=common_windows([windows_by_track[t] for t in tracks])
            orders=permutations(group) if mode=='ALLOW_SEQUENTIAL' else [group]
            generated=False
            failures=set()
            for ordered in orders:
                offsets,nominal_end=make_tasks(ordered,mode,horizon[0])
                duration=nominal_end-horizon[0]
                for wstart,wend in windows:
                    first=max(wstart,horizon[0])
                    if cutoff is not None:first=max(first,cutoff)
                    last=min(wend,horizon[1])-duration
                    for t in offsets:
                        p=requests[t['request_id']]['payload']
                        first=max(first,dt(p['earliest_at'])-(dt(t['work_start'])-horizon[0]))
                        endpoint=t['restore_end'] if p['deadline_kind']=='RESTORED_BY' else t['work_end']
                        last=min(last,dt(p['deadline_at'])-(dt(endpoint)-horizon[0]))
                    first=horizon[0]+timedelta(minutes=math.ceil((first-horizon[0]).total_seconds()/60))
                    last=horizon[0]+timedelta(minutes=math.floor((last-horizon[0]).total_seconds()/60))
                    for start in grid_starts(first,last,opportunities['search']['grid_minutes']):
                        if time_count>=config['max_time_plans'] or len(candidates)>=config['max_candidates']:
                            pruned.append({'code':'TIME_PLAN_OR_CANDIDATE_LIMIT','time_plans':time_count,'candidates':len(candidates)})
                            stop=True
                            break
                        time_count+=1
                        tasks,end=make_tasks(ordered,mode,start)
                        code=task_checks(tasks,requests,{c['request_id']:c for c in facts.get('completed_work',[])})
                        if code:
                            failures.add(code)
                            continue
                        alternatives,reasons,limited=allocate(tasks,resources,policy,horizon,config)
                        if limited:pruned.append({'code':'RESOURCE_ASSIGNMENT_SEARCH_LIMIT','request_ids':ids,'start_at':start.isoformat()})
                        failures.update(reasons)
                        for allocations in alternatives:
                            if len(candidates)>=config['max_candidates']:
                                pruned.append({'code':'CANDIDATE_LIMIT','retained':len(candidates)})
                                stop=True
                                break
                            exposure_seconds=0
                            # Forecast exposure is expected-train * track-seconds, not measured delay.
                            latest={}
                            for f in facts['freight']:
                                key=(f['external_id'],f['track_id'])
                                if key not in latest or latest[key]['source_revision']<f['source_revision']:latest[key]=f
                            for f in latest.values():
                                if f['track_id'] in tracks:
                                    exposure_seconds+=max(0,int((min(end,dt(f['end_at']))-max(start,dt(f['start_at']))).total_seconds()))*f['expected_count']
                            travel_delta=0
                            for resource in resources:
                                selected=[a for a in allocations if a['resource_id']==resource['id']]
                                if selected:
                                    travel_delta+=resource_feasible(resource,selected,policy,horizon)[2]-resource_feasible(resource,[],policy,horizon)[2]
                            raw={'request_ids':ids,'mode':mode,'track_ids':tracks,'possession_start':start.isoformat(),
                                'possession_end':end.isoformat(),'tasks':tasks,'allocations':sorted(allocations,key=digest),
                                'rule_ids':refs,'policy_revision_id':records[0]['id'],
                                'costs':{'reserved_track_minutes':int(duration.total_seconds()/60)*len(tracks),
                                    'forecast_exposure_train_track_seconds':exposure_seconds,
                                    'incremental_travel_minutes_against_fixed_duties':travel_delta},
                                'priority_by_request':{id:scores[id] for id in ids},
                                'resource_consumption':'SETUP_WORK_RESTORATION; parallel units reserved for whole possession'}
                            raw['id']=digest(raw)[:24]
                            candidates[raw['id']]=raw
                            generated=True
                        if stop:break
                    if stop:break
                if stop:break
            if not generated:excluded.append({'request_ids':ids,'code':'NO_ELIGIBLE_ASSIGNMENT_OR_WINDOW','details':sorted(failures)})
            if stop:break
        if stop:break
    if captures:
        from .replanning_candidates import preserve_candidates
        retained,failures=preserve_candidates(manifest,windows_by_track,policy,records[0]['id'],horizon)
        # Original approved assignments are evidence-backed alternatives, checked
        # against current facts. They are never used as timeout fallback output.
        for candidate in retained:candidates[candidate['id']]=candidate
        excluded.extend(failures)
        result['preserved_candidate_ids']=[c['id'] for c in retained]
        if len(candidates)>config['max_candidates']:
            pruned.append({'code':'APPROVED_COMMITMENTS_RETAINED_ABOVE_SEARCH_CAP','count':len(retained)})
    output=sorted(candidates.values(),key=lambda c:(c['possession_start'],c['id']))
    result['candidates']=output
    result['incompatibilities']=candidate_conflicts(output,resources,policy,horizon,requests)
    result['aggregate_constraints']=pool_constraints(output,resources,policy)+duty_constraints(output,resources)
    result['resource_policy_evidence']=[{'resource_id':r['id'],'profile_id':r['profile']['id'],
        'revision':r['profile']['revision'],'hash':digest(r['profile']['payload'])} for r in resources if r.get('profile')]
    result['precedence']=[{'request_id':r['id'],'predecessor_id':p} for r in facts['requests'] for p in r['payload']['predecessors']]
    result['review_blockers']=sorted(set(blockers))
    result['search'].update({'groups_evaluated':group_count,'time_plans_evaluated':time_count,
                            'complete_within_declared_search':not bool(pruned)})
    result['counts']={'candidates':len(output),'bundles':sum(len(c['request_ids'])>1 for c in output),
                      'incompatibilities':len(result['incompatibilities'])}
    return result
