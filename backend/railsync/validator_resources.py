"""Validator-owned resource arithmetic, separate from resource_engine allocation."""
from collections import defaultdict
from datetime import timedelta
from .coordination_schema import ResourceProfile
from .validator import instant,intersects

def movement(v,unit,left,right):
    if left==right:return 0
    matches=[r['minutes'] for r in v.policy['travel'] if (r['resource_type'],r['from_track'],r['to_track'])==(unit['resource_type'],left,right)]
    v.check(len(matches)==1,'RESOURCES','TRAVEL_TIME_UNKNOWN',{'resource_id':unit['id'],'from':left,'to':right},error=True)
    return matches[0] if len(matches)==1 else 0

def inspect_resources(v):
    by_unit=defaultdict(list)
    pool_duties=defaultdict(list)
    pools={p['id']:p for p in v.policy['pools']}
    for a in v.assignments:
        v.check(a['resource_id'] in v.resources,'RESOURCES','RESOURCE_UNKNOWN',{'resource_id':a['resource_id']},error=True)
        if a['resource_id'] in v.resources:by_unit[a['resource_id']].append(a)
    for id,unit in v.resources.items():
        v.tick()
        record=unit.get('profile')
        if not record:
            if by_unit[id]:v.check(False,'RESOURCES','RESOURCE_PROFILE_UNKNOWN',{'resource_id':id},error=True)
            continue
        p=ResourceProfile.model_validate(record['payload']).model_dump(mode='json')
        v.check(p['source_mode']=='SIMULATED','DATA_QUALITY','RESOURCE_AUTHORITY_UNVERIFIED',{'resource_id':id},error=True)
        pool=p['pool_id']
        if pool:v.check(pool in pools and pools[pool]['resource_type']==unit['resource_type'],'RESOURCES','POOL_UNKNOWN_OR_TYPE_MISMATCH',{'pool_id':pool},error=True)
        duties=[(instant(d['start_at']),instant(d['end_at']),d['track_id']) for d in p['duties']]
        if pool:pool_duties[pool].extend(duties)
        selected=[]
        for a in by_unit[id]:
            ev={'resource_id':id,'request_id':a['request_id']}
            start,end=instant(a['start_at']),instant(a['end_at'])
            v.check(unit['resource_type']==a['resource_type'],'RESOURCES','RESOURCE_TYPE_MISMATCH',ev)
            v.check(a['department'] in p['departments'] and unit['department'] in [None,a['department']],'RESOURCES','RESOURCE_DEPARTMENT_FORBIDDEN',ev)
            v.check(instant(unit['available_start'])<=start<end<=instant(unit['available_end']),'RESOURCES','RESOURCE_UNAVAILABLE',ev)
            v.check(any(instant(w['start_at'])<=start and end<=instant(w['end_at']) for w in p['calendar']),'RESOURCES','RESOURCE_CALENDAR_GAP',ev)
            v.check(any(q['skill']==a['qualification'] and instant(q['start_at'])<=start and end<=instant(q['end_at']) for q in p['qualifications']),
                    'RESOURCES','QUALIFICATION_MISSING_OR_EXPIRED',ev)
            selected.append((start,end,a['track_id']))
        if not selected:continue
        v.check(instant(p['history']['start_at'])<=v.start-timedelta(days=1) and instant(p['history']['end_at'])>=v.end+timedelta(days=1),
                'RESOURCES','DUTY_HISTORY_UNKNOWN',{'resource_id':id},error=True)
        if pool:pool_duties[pool].extend(selected)
        ordered=sorted(duties+selected)
        merged=[]
        for duty in ordered:
            if merged:v.check(merged[-1][1]<=duty[0],'RESOURCES','RESOURCE_OVERLAP',{'resource_id':id})
            if merged and duty[0]==merged[-1][1] and duty[2]==merged[-1][2]:merged[-1]=(merged[-1][0],duty[1],duty[2])
            else:merged.append(duty)
        for left,right in zip(merged,merged[1:]):
            travel=movement(v,unit,left[2],right[2])
            v.check((right[0]-left[1]).total_seconds()>=60*(travel+p['min_rest_minutes']),'RESOURCES','TRAVEL_OR_REST_VIOLATION',{'resource_id':id})
        for start,end,track in selected:
            if not any(d[1]<=start for d in duties+selected):
                travel=movement(v,unit,p['home_track'],track)
                v.check((start-instant(unit['available_start'])).total_seconds()>=travel*60,'RESOURCES','HOME_TRAVEL_VIOLATION',{'resource_id':id})
        endpoints={t for a,b,_ in ordered for t in [a,b,a+timedelta(days=1),b+timedelta(days=1)]}
        for end in endpoints:
            v.tick()
            load=sum(max(0,(min(b,end)-max(a,end-timedelta(days=1))).total_seconds()) for a,b,_ in ordered)
            v.check(load<=p['max_duty_minutes_per_24h']*60,'RESOURCES','ROLLING_DUTY_LIMIT',{'resource_id':id,'duty_seconds':load})
    for id,duties in pool_duties.items():
        if id not in pools:continue
        windows=pools[id]['calendar']
        edges={v.start,v.end}|{t for a,b,_ in duties for t in [a,b] if v.start<t<v.end}
        edges.update(t for w in windows for t in [instant(w['start_at']),instant(w['end_at'])] if v.start<t<v.end)
        edges=sorted(edges)
        for start,end in zip(edges,edges[1:]):
            demand=sum(intersects(start,end,a,b) for a,b,_ in duties)
            if not demand:continue
            active=[w for w in windows if instant(w['start_at'])<=start and end<=instant(w['end_at'])]
            v.check(len(active)==1,'RESOURCES','POOL_CALENDAR_UNKNOWN',{'pool_id':id},error=True)
            if len(active)==1:v.check(demand<=active[0]['capacity'],'RESOURCES','POOL_CAPACITY_EXCEEDED',{'pool_id':id,'demand':demand,'capacity':active[0]['capacity']})
