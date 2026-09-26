"""Named-unit allocation plus explicit pool/rolling-duty constraints for selection."""
from collections import defaultdict
from datetime import datetime, timedelta
import math

DAY = timedelta(days=1)

def dt(value):
    return datetime.fromisoformat(value)

def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]

def travel_minutes(policy, resource_type, origin, destination):
    # No movement within one explicit location. Different locations need a rule.
    if origin == destination:
        return 0
    for rule in policy['travel']:
        if (rule['resource_type'], rule['from_track'], rule['to_track']) == (resource_type, origin, destination):
            return rule['minutes']
    return None

def period(value):
    return dt(value['start_at']), dt(value['end_at'])

def rolling_load(duties, end):
    start=end-DAY
    return sum(max(0, (min(b,end)-max(a,start)).total_seconds()) for a,b,_ in duties)

def resource_feasible(unit, allocations, policy, horizon):
    profile_record=unit.get('profile')
    if not profile_record:
        return False, 'QUALIFICATION_AND_DUTY_PROFILE_UNKNOWN', 0
    p=profile_record['payload']
    hstart,hend=horizon
    if dt(p['history']['start_at']) > hstart-DAY or dt(p['history']['end_at']) < hend+DAY:
        return False, 'DUTY_HISTORY_COVERAGE_UNKNOWN', 0
    start_available,end_available=dt(unit['available_start']),dt(unit['available_end'])
    duties=[(*period(d),d['track_id']) for d in p['duties']]
    assigned=[]
    for allocation in allocations:
        a,b=period(allocation)
        if not (start_available<=a<b<=end_available):return False,'RESOURCE_UNAVAILABLE',0
        if not any(dt(c['start_at'])<=a and b<=dt(c['end_at']) for c in p['calendar']):
            return False,'RESOURCE_CALENDAR_GAP',0
        if allocation['department'] not in p['departments'] or unit['department'] not in [None,allocation['department']]:
            return False,'DEPARTMENT_NOT_PERMITTED',0
        if not any(q['skill']==allocation['qualification'] and dt(q['start_at'])<=a and b<=dt(q['end_at']) for q in p['qualifications']):
            return False,'QUALIFICATION_MISSING_OR_EXPIRED',0
        assigned.append((a,b,allocation['track_id']))
    all_duties=sorted(duties+assigned)
    if any(overlap((a,b),(c,d)) for (a,b,_),(c,d,_) in zip(all_duties,all_duties[1:])):
        return False,'NAMED_RESOURCE_OVERLAP',0
    # Adjacent stages at one location form continuous duty (including across midnight).
    merged=[]
    for a,b,track in all_duties:
        if merged and merged[-1][1]==a and merged[-1][2]==track:
            merged[-1]=(merged[-1][0],b,track)
        else:
            merged.append((a,b,track))
    movement=0
    for left,right in zip(merged,merged[1:]):
        minutes=travel_minutes(policy,unit['resource_type'],left[2],right[2])
        if minutes is None:return False,'TRAVEL_TIME_UNKNOWN',0
        # Conservative policy: travel is additional to uninterrupted rest.
        if (right[0]-left[1]).total_seconds() < 60*(minutes+p['min_rest_minutes']):
            return False,'TRAVEL_OR_REST_SHORTFALL',0
        movement+=minutes
    # The last known duty establishes location; otherwise use the declared home at availability start.
    for a,b,track in assigned:
        previous=[d for d in all_duties if d[1]<=a]
        if not previous:
            minutes=travel_minutes(policy,unit['resource_type'],p['home_track'],track)
            if minutes is None:return False,'TRAVEL_TIME_UNKNOWN',0
            if a < start_available+timedelta(minutes=minutes):return False,'HOME_TRAVEL_SHORTFALL',0
            movement+=minutes
    endpoints={t for a,b,_ in merged for t in [a,b,a+DAY,b+DAY]}
    if any(rolling_load(merged,t)>60*p['max_duty_minutes_per_24h'] for t in endpoints):
        return False,'ROLLING_24H_DUTY_LIMIT',0
    return True,None,movement

def pool_constraints(candidates, resources, policy):
    """Event segments preserve aggregate conflicts that no pairwise test can detect."""
    units={r['id']:r for r in resources}
    constraints=[]
    known={p['id']:p for p in policy['pools']}
    members=defaultdict(list)
    for c in candidates:
        for a in c['allocations']:
            unit=units[a['resource_id']]
            pool=unit['profile']['payload'].get('pool_id')
            if pool:
                members[pool].append((c['id'],a))
    for pool_id,entries in sorted(members.items()):
        pool=known.get(pool_id)
        calendar=pool['calendar'] if pool else []
        # Existing duties also consume pooled capacity.
        fixed=[d for r in resources if r.get('profile') and r['profile']['payload'].get('pool_id')==pool_id
               for d in r['profile']['payload']['duties']]
        edges=sorted({t for _,a in entries for t in period(a)} |
                     {t for p in calendar+fixed for t in period(p)})
        for left,right in zip(edges,edges[1:]):
            coefficients=defaultdict(int)
            for cid,a in entries:
                if overlap((left,right),period(a)):coefficients[cid]+=1
            if not coefficients:continue
            covering=[p for p in calendar if dt(p['start_at'])<=left and right<=dt(p['end_at'])]
            capacity=covering[0]['capacity'] if len(covering)==1 else 0
            capacity-=sum(overlap((left,right),period(d)) for d in fixed)
            constraints.append({'kind':'POOL_CAPACITY','pool_id':pool_id,'start_at':left.isoformat(),
                                'end_at':right.isoformat(),'capacity':capacity,'coefficients':dict(coefficients),
                                'coverage_known':len(covering)==1})
    return constraints

def duty_constraints(candidates, resources):
    constraints=[]
    for r in resources:
        if not r.get('profile'):continue
        entries=[(c['id'],a) for c in candidates for a in c['allocations'] if a['resource_id']==r['id']]
        if not entries:continue
        p=r['profile']['payload']
        fixed=[(*period(d),d['track_id']) for d in p['duties']]
        edges={t for _,a in entries for a0,b0 in [period(a)] for t in [a0,b0,a0+DAY,b0+DAY]}
        edges.update(t for a,b,_ in fixed for t in [a,b,a+DAY,b+DAY])
        for end in sorted(edges):
            coefficients=defaultdict(int)
            for cid,a in entries:
                seconds=max(0,(min(dt(a['end_at']),end)-max(dt(a['start_at']),end-DAY)).total_seconds())
                if seconds:coefficients[cid]+=math.ceil(seconds)
            if coefficients:
                constraints.append({'kind':'ROLLING_DUTY_SECONDS','resource_id':r['id'],
                    'start_at':(end-DAY).isoformat(),'end_at':end.isoformat(),
                    'capacity':60*p['max_duty_minutes_per_24h']-math.ceil(rolling_load(fixed,end)),
                    'coefficients':dict(coefficients)})
    return constraints

def allocate(tasks, resources, policy, horizon, config):
    """Backtracking assigns every demand slot, with bounded work and explicit pruning."""
    if sum(r['quantity'] for t in tasks for r in t['requirements']) > config['max_resource_slots_per_plan']:
        return [],['RESOURCE_DEMAND_SEARCH_LIMIT'],True
    demands=[]
    for task in tasks:
        for requirement in task['requirements']:
            for _ in range(requirement['quantity']):
                demands.append({'request_id':task['request_id'],'resource_type':requirement['type'],
                    'qualification':requirement.get('qualification') or task['issue_type'],
                    'department':task['department'],'track_id':task['resource_location'],
                    'start_at':task['resource_start'],'end_at':task['resource_end']})
    # Every repeated quantity/requirement becomes a separate demand slot.
    choices=[]
    rejected=set()
    units={r['id']:r for r in resources}
    pools={p['id']:p for p in policy['pools']}
    for demand in demands:
        eligible=[]
        for resource in sorted(resources,key=lambda r:r['id']):
            if resource['resource_type']!=demand['resource_type']:continue
            ok,reason,_=resource_feasible(resource,[demand],policy,horizon)
            pool_id=resource['profile']['payload'].get('pool_id') if resource.get('profile') else None
            if ok and pool_id and (pool_id not in pools or pools[pool_id]['resource_type']!=resource['resource_type']):
                ok,reason=False,'RESOURCE_POOL_UNKNOWN_OR_TYPE_MISMATCH'
            if ok:eligible.append(resource['id'])
            else:rejected.add(reason)
        if not eligible:return [],sorted(rejected or {'NO_RESOURCE_OF_REQUIRED_TYPE'}),False
        choices.append(eligible)
    order=sorted(range(len(demands)),key=lambda i:(len(choices[i]),i))
    results=[]
    nodes=0
    pruned=False

    def visit(index,selected):
        nonlocal nodes,pruned
        if nodes>=config['max_assignment_nodes_per_plan'] or len(results)>=config['max_assignments_per_plan']:
            pruned=True
            return
        nodes+=1
        if index==len(order):
            cs=pool_constraints([{'id':'current','allocations':selected}],resources,policy)
            if any(c['coefficients']['current']>c['capacity'] for c in cs):
                rejected.add('POOL_CAPACITY_OR_COVERAGE')
            else:
                results.append(list(selected))
            return
        slot=order[index]
        for id in choices[slot]:
            allocation={**demands[slot],'resource_id':id}
            same=[a for a in selected if a['resource_id']==id]+[allocation]
            ok,reason,_=resource_feasible(units[id],same,policy,horizon)
            if ok:visit(index+1,selected+[allocation])
            else:rejected.add(reason)
            if pruned:return
    visit(0,[])
    return results,sorted(rejected),pruned
