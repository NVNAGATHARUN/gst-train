"""Raw-fact validation. No scheduling engine or cached feasibility predicate is used."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from itertools import combinations
import hashlib
import json
import time
from pydantic import ValidationError
from .validation_schema import ValidationContext
from .coordination_schema import CoordinationPolicy

VERSION='INDEPENDENT_VALIDATOR_V3'
CATEGORIES=('PROVENANCE','COVERAGE','TIMING','INFRASTRUCTURE','TRAFFIC','COMPATIBILITY','RESOURCES','COMMITMENTS','DATA_QUALITY')

def content_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def instant(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:raise ValueError('NAIVE_TIMESTAMP')
    return result.astimezone(timezone.utc)

def intersects(a,b,c,d):return a<d and c<b

def covers(intervals,start,end):
    cursor=start
    for left,right in sorted(intervals):
        if left>cursor:return False
        cursor=max(cursor,right)
        if cursor>=end:return True
    return cursor>=end

def unique(rows,key):
    result={row[key]:row for row in rows}
    if len(result)!=len(rows):raise ValueError('DUPLICATE_FACT_ID')
    return result

class ValidationBudgetExceeded(Exception):pass

class Inspector:
    def __init__(self,manifest,snapshot_hash,plan,plan_hash,checked_at,current_facts_hash,max_seconds,max_checks):
        self.manifest,self.snapshot_hash,self.plan,self.plan_hash=manifest,snapshot_hash,plan,plan_hash
        self.checked_at,self.current_facts_hash=checked_at,current_facts_hash
        self.deadline=time.monotonic()+max_seconds
        self.max_checks,self.operations=max_checks,0
        self.findings=[]
        self.completed=set()
        self.scope='UNKNOWN'
        self.facts=manifest['facts']

    def tick(self):
        self.operations+=1
        if self.operations>self.max_checks or time.monotonic()>=self.deadline:raise ValidationBudgetExceeded()

    def check(self,condition,category,code,evidence=None,error=False):
        self.tick()
        if not condition:self.findings.append({'category':category,'status':'ERROR' if error else 'FAIL','code':code,'evidence':evidence or {}})

    def run(self):
        self.check(content_hash(self.manifest)==self.snapshot_hash,'PROVENANCE','SNAPSHOT_HASH_MISMATCH')
        self.check(content_hash(self.plan)==self.plan_hash,'PROVENANCE','PLAN_HASH_MISMATCH')
        self.check(self.plan['snapshot_hash']==self.snapshot_hash,'PROVENANCE','PLAN_SNAPSHOT_MISMATCH')
        self.check(self.plan.get('solver_status') in ['OPTIMAL','FEASIBLE',None] and self.plan.get('schedule_status')=='DEVELOPMENT_ARTIFACT',
                   'PROVENANCE','PLAN_HAS_NO_VALID_INCUMBENT')
        self.completed.add('PROVENANCE')
        self.start,self.end=instant(self.manifest['horizon_start']),instant(self.manifest['horizon_end'])
        if self.start>=self.end:raise ValueError('INVALID_HORIZON')
        self.requests=unique(self.facts['requests'],'id')
        for request in self.requests.values():
            p=request['payload']
            if p['deadline_kind'] not in ['RESTORED_BY','WORK_COMPLETE_BY'] or type(p['mandatory'])!=bool:
                raise ValueError('UNSUPPORTED_REQUEST_RULE')
            if any(type(p[k])!=int or p[k]<0 for k in ['setup_minutes','restore_minutes']) or type(p['work_minutes'])!=int or p['work_minutes']<=0:
                raise ValueError('INVALID_REQUIRED_DURATION')
        self.network=unique(self.facts['network'],'id')
        self.resources=unique(self.facts['resources'],'id')
        self.blocks=self.plan['assignments']
        if len(self.blocks)>3000:raise ValidationBudgetExceeded()
        self.tasks,self.reservations,self.assignments={},[],[]
        policies=self.facts['coordination_policies']
        if len(policies)!=1:raise ValueError('POLICY_MISSING_OR_AMBIGUOUS')
        self.policy_record=policies[0]
        self.policy=CoordinationPolicy.model_validate(policies[0]['payload']).model_dump(mode='json')
        context=self.manifest.get('validation_context')
        self.context=ValidationContext.model_validate(context).model_dump(mode='json') if context else None
        self.data_quality()
        for block in self.blocks:self.inspect_block(block)
        for id,r in self.requests.items():
            p=r['payload']
            if p['mandatory'] and instant(p['deadline_at'])<=self.end:
                self.check(id in self.tasks,'COVERAGE','MANDATORY_UNSCHEDULED',{'request_id':id})
            if id in self.tasks:
                for predecessor in p['predecessors']:
                    completed=next((c for c in self.facts.get('completed_work',[]) if c['request_id']==predecessor
                        and c.get('verified') is True and c.get('restoration_verified') is True),None)
                    if completed and predecessor not in self.requests:
                        self.check(instant(completed['restored_at'])<=instant(self.tasks[id]['setup_start']),
                            'TIMING','COMPLETED_PREDECESSOR_NOT_RESTORED',{'request_id':id,'predecessor':predecessor})
                        continue
                    self.check(predecessor in self.tasks,'COVERAGE','PREDECESSOR_NOT_SCHEDULED',{'request_id':id,'predecessor':predecessor})
                    if predecessor in self.tasks:self.check(instant(self.tasks[predecessor]['restore_end'])<=instant(self.tasks[id]['setup_start']),
                        'TIMING','PRECEDENCE_VIOLATION',{'request_id':id,'predecessor':predecessor})
        for a,b in combinations(self.reservations,2):
            self.check(not(set(a['tracks'])&set(b['tracks']) and intersects(a['start'],a['end'],b['start'],b['end'])),
                       'INFRASTRUCTURE','TRACK_POSSESSION_OVERLAP',{'left':a['id'],'right':b['id']})
        from .validator_resources import inspect_resources
        inspect_resources(self)
        self.inspect_commitments()
        from .validator_replanning import inspect_replanning
        inspect_replanning(self)
        self.completed.update(CATEGORIES)
        if not self.context:self.completed.discard('TRAFFIC')

    def data_quality(self):
        if not self.context:
            self.check(False,'DATA_QUALITY','COVERAGE_DECLARATION_MISSING',error=True)
            return
        c=self.context
        self.scope=c['scope']
        self.check(c['facts_hash']==content_hash(self.facts),'DATA_QUALITY','COVERAGE_FACTS_HASH_MISMATCH')
        self.check(self.current_facts_hash is not None,'DATA_QUALITY','CURRENT_STATE_UNKNOWN',error=True)
        if self.current_facts_hash is not None:self.check(self.current_facts_hash==content_hash(self.facts),'DATA_QUALITY','OPERATIONAL_STATE_CHANGED')
        self.check(instant(c['received_at'])<=self.checked_at<instant(c['valid_until']),'DATA_QUALITY','DATA_STALE_OR_FUTURE_RECEIPT')
        self.check(c['coa_semantics']!='UNKNOWN','DATA_QUALITY','COA_SEMANTICS_UNKNOWN',error=True)
        self.check(c['scope']=='SIMULATED','DATA_QUALITY','IMPORTED_AUTHORITY_UNVERIFIED',error=True)
        imported=[r.get('id') for values in self.facts.values() if isinstance(values,list) for r in values if isinstance(r,dict) and r.get('source_mode')=='IMPORTED']
        self.check(not imported and self.policy['source_mode']=='SIMULATED','DATA_QUALITY','SOURCE_SCOPE_MISMATCH',{'records':imported},error=True)
        required=[(source,None) for source in ['NETWORK','REQUESTS','RESOURCES','COMMITMENTS']]
        required += [(source,track) for track in self.manifest['track_ids'] for source in ['OCCUPANCY','COA','FREIGHT']]
        for source,track in required:
            declarations=[d for d in c['coverage'] if (d['source'],d['track_id'])==(source,track) and d['complete']]
            begin=self.start-timedelta(minutes=c['clearance_before_minutes']) if source=='OCCUPANCY' else self.start
            end=self.end+timedelta(minutes=c['clearance_after_minutes']) if source=='OCCUPANCY' else self.end
            self.check(covers([(instant(d['start_at']),instant(d['end_at'])) for d in declarations],begin,end),
                       'DATA_QUALITY','CRITICAL_COVERAGE_GAP',{'source':source,'track_id':track},error=True)
        for f in self.facts['freight']:self.check(instant(f['issued_at'])<=instant(c['received_at']),
            'DATA_QUALITY','FORECAST_ISSUED_AFTER_RECEIPT',{'forecast_id':f['id']})
        for kind in ['coa','freight']:
            identities=Counter(r['external_id'] for r in self.facts[kind])
            for id,count in identities.items():self.check(count==1,'DATA_QUALITY','SOURCE_REVISION_AMBIGUOUS',{'source':kind,'external_id':id},error=True)
        runs=defaultdict(set)
        for row in self.facts['occupancy']:
            runs[(row['train_id'],row.get('service_date','UNKNOWN'))].add(row['run_id'])
        for key,values in runs.items():self.check(len(values)==1,'DATA_QUALITY','DATED_TRAIN_RUN_AMBIGUOUS',{'train_id':key[0],'service_date':key[1]},error=True)
        if c['coa_semantics']=='TRAFFIC_FREE':
            for w in self.facts['coa']:
                for o in self.facts['occupancy']:
                    self.check(not(w['track_id']==o['track_id'] and intersects(instant(w['start_at']),instant(w['end_at']),instant(o['enter_at']),instant(o['exit_at']))),
                               'DATA_QUALITY','COA_SOURCE_CONFLICT',{'coa_id':w['id'],'occupancy_id':o['id']})
        self.completed.add('DATA_QUALITY')

    def signature(self,p):
        return {'department':p['department'],'issue_type':p['issue_type'],
                'power_state':'OFF' if p['power_block_required'] else p['power_state'],'signalling_state':p['signalling_state']}

    def inspect_block(self,b):
        self.tick()
        start,end=instant(b['possession_start']),instant(b['possession_end'])
        ev={'candidate_id':b['id']}
        self.check(self.start<=start<end<=self.end,'TIMING','POSSESSION_OUTSIDE_HORIZON',ev)
        self.check(b['policy_revision_id']==self.policy_record['id'],'PROVENANCE','POLICY_REVISION_MISMATCH',ev)
        ids=[t['request_id'] for t in b['tasks']]
        if len(ids)>4:raise ValueError('UNSUPPORTED_BUNDLE_SIZE')
        self.check(Counter(ids)==Counter(b['request_ids']) and len(set(ids))==len(ids),'COVERAGE','BLOCK_COVERAGE_MISMATCH',ev)
        self.check(len(b['track_ids'])==len(set(b['track_ids'])),'INFRASTRUCTURE','DUPLICATE_TRACK',ev)
        if not ids or any(id not in self.requests for id in ids):raise ValueError('EMPTY_OR_UNKNOWN_REQUEST')
        mode=b['mode']
        if mode not in ['SINGLE','ALLOW_PARALLEL','ALLOW_SEQUENTIAL']:raise ValueError('UNSUPPORTED_BUNDLE_MODE')
        self.check((mode=='SINGLE')==(len(ids)==1),'COMPATIBILITY','BUNDLE_MODE_MISMATCH',ev)
        payloads=[self.requests[id]['payload'] for id in ids]
        setups,works,restores=([p[k] for p in payloads] for k in ['setup_minutes','work_minutes','restore_minutes'])
        parallel=mode=='ALLOW_PARALLEL'
        duration=max(setups)+max(works)+max(restores) if parallel else sum(setups+works+restores)
        self.check((end-start).total_seconds()==duration*60,'TIMING','POSSESSION_DURATION_MISMATCH',ev)
        cursor=start
        footprint=set()
        for t in b['tasks']:
            id=t['request_id'];r=self.requests[id];p=r['payload'];e={**ev,'request_id':id}
            self.check(id not in self.tasks,'COVERAGE','DUPLICATE_TASK',e)
            self.tasks[id]=t
            self.check(t['request_revision']==r['revision'],'PROVENANCE','REQUEST_REVISION_MISMATCH',e)
            self.check(t['department']==p['department'] and t['issue_type']==p['issue_type'],'PROVENANCE','TASK_IDENTITY_MISMATCH',e)
            signature=self.signature(p)
            self.check('UNKNOWN' not in signature.values(),'COMPATIBILITY','WORK_STATE_UNKNOWN',e,error=True)
            self.check(t['power_state']==signature['power_state'] and t['signalling_state']==signature['signalling_state'] and t['isolation_zone']==p['isolation_zone'],
                       'COMPATIBILITY','TASK_STATE_MISMATCH',e)
            ss=start if parallel else cursor
            ws=ss+timedelta(minutes=max(setups) if parallel else p['setup_minutes'])
            we=ws+timedelta(minutes=p['work_minutes'])
            rs=end-timedelta(minutes=max(restores)) if parallel else we
            re=end if parallel else rs+timedelta(minutes=p['restore_minutes'])
            expected={'setup_start':ss,'setup_end':ws,'work_start':ws,'work_end':we,'restore_start':rs,'restore_end':re,'resource_start':ss,'resource_end':re}
            for name,value in expected.items():self.check(instant(t[name])==value,'TIMING','TASK_STAGE_MISMATCH',{**e,'stage':name})
            self.check(instant(t['work_start'])>=instant(p['earliest_at']),'TIMING','EARLIEST_VIOLATION',e)
            deadline=t['restore_end'] if p['deadline_kind']=='RESTORED_BY' else t['work_end']
            self.check(instant(deadline)<=instant(p['deadline_at']),'TIMING','DEADLINE_VIOLATION',e)
            cursor=re
            tracks=set(p['footprint'])
            self.check(set(t['track_ids'])==tracks,'INFRASTRUCTURE','TASK_FOOTPRINT_MISMATCH',e)
            asset=self.network.get(p['asset_id'])
            self.check(bool(asset and asset['kind']=='asset'),'INFRASTRUCTURE','ASSET_UNKNOWN',e,error=True)
            if asset:self.check(asset['payload']['department']==p['department'] and set(asset['payload']['footprint'])<=tracks,'INFRASTRUCTURE','ASSET_FOOTPRINT_MISMATCH',e)
            footprint.update(tracks)
            if signature['power_state']=='OFF':
                zone=self.network.get(p['isolation_zone'])
                self.check(bool(zone and zone['kind']=='isolation'),'INFRASTRUCTURE','ISOLATION_MISSING',e,error=True)
                if zone:
                    footprint.update(zone['payload']['footprint'])
                    self.check(tracks<=set(zone['payload']['footprint']),'INFRASTRUCTURE','ISOLATION_COVERAGE_INCOMPLETE',e)
            location=p.get('resource_location') or (p['footprint'][0] if len(p['footprint'])==1 else None)
            self.check(location is not None and t['resource_location']==location,'RESOURCES','RESOURCE_LOCATION_UNKNOWN_OR_CHANGED',e,error=location is None)
            demand=Counter()
            for req in p['requirements']:demand[(req['type'],req.get('qualification') or p['issue_type'])]+=req['quantity']
            actual=Counter()
            for a in b['allocations']:
                if a['request_id']!=id:continue
                actual[(a['resource_type'],a['qualification'])]+=1
                self.check(a['department']==p['department'] and a['track_id']==location and instant(a['start_at'])==ss and instant(a['end_at'])==re,
                           'RESOURCES','RESOURCE_DUTY_MISMATCH',e)
                self.assignments.append(a)
            self.check(demand==actual,'RESOURCES','RESOURCE_REQUIREMENTS_NOT_MET',e)
        self.check(all(a['request_id'] in ids for a in b['allocations']),'RESOURCES','ORPHAN_ALLOCATION',ev)
        self.check(set(b['track_ids'])==footprint,'INFRASTRUCTURE','POSSESSION_FOOTPRINT_MISMATCH',ev)
        self.check(footprint<=set(self.manifest['track_ids']),'INFRASTRUCTURE','FOOTPRINT_OUTSIDE_SNAPSHOT',ev,error=True)
        for track in footprint:
            n=self.network.get(track)
            self.check(bool(n and n['kind']=='track'),'INFRASTRUCTURE','TRACK_UNKNOWN',{'track_id':track},error=True)
            if n:self.check(n['payload']['status']=='OPEN','INFRASTRUCTURE','TRACK_CLOSED',{'track_id':track})
        self.inspect_compatibility(b,payloads)
        self.inspect_traffic(start,end,footprint,ev)
        self.reservations.append({'id':b['id'],'start':start,'end':end,'tracks':footprint})

    def inspect_compatibility(self,b,payloads):
        refs=[]
        for left,right in combinations(payloads,2):
            self.tick()
            a,c=set(left['footprint']),set(right['footprint'])
            relation='SAME' if a==c else 'OVERLAP' if a&c else 'DISJOINT'
            signatures=sorted([self.signature(left),self.signature(right)],key=content_hash)
            matches=[r for r in self.policy['pairs'] if r['footprint_relation']==relation and sorted([r['left'],r['right']],key=content_hash)==signatures]
            self.check(len(matches)==1,'COMPATIBILITY','COMPATIBILITY_RULE_UNKNOWN',{'candidate_id':b['id']},error=True)
            if len(matches)!=1:continue
            rule=matches[0];refs.append(rule['id'])
            self.check(rule['mode']==b['mode'],'COMPATIBILITY','WORK_INCOMPATIBLE',{'rule_id':rule['id']})
            if b['mode']=='ALLOW_PARALLEL':
                self.check(rule['shared_setup'] and rule['shared_restoration'],'COMPATIBILITY','SHARED_OVERHEAD_FORBIDDEN',{'rule_id':rule['id']})
                self.check({s['power_state'] for s in signatures}!={'ON','OFF'},'COMPATIBILITY','ELECTRICAL_CONFLICT')
                self.check({s['signalling_state'] for s in signatures}!={'CONNECTED','DISCONNECTED'},'COMPATIBILITY','SIGNALLING_CONFLICT')
        for size in range(3,len(payloads)+1):
            for subset in combinations(payloads,size):
                self.tick()
                signatures=sorted([self.signature(p) for p in subset],key=content_hash)
                matches=[r for r in self.policy['groups'] if sorted(r['members'],key=content_hash)==signatures]
                self.check(len(matches)==1,'COMPATIBILITY','GROUP_RULE_UNKNOWN',error=True)
                if len(matches)==1:
                    refs.append(matches[0]['id'])
                    self.check(matches[0]['mode']==b['mode'],'COMPATIBILITY','GROUP_WORK_INCOMPATIBLE',{'rule_id':matches[0]['id']})
        self.check(Counter(refs)==Counter(b['rule_ids']),'PROVENANCE','RULE_EVIDENCE_MISMATCH',{'candidate_id':b['id']})

    def inspect_traffic(self,start,end,tracks,evidence):
        for release in self.facts.get('released_possessions',[]):
            p=release['payload'];original=release['result']['assignment']
            self.check(not(set(original['track_ids'])&tracks and intersects(start,end,
                instant(p['actual_possession_start']),instant(p['restored_at']))),
                'INFRASTRUCTURE','RECORDED_POSSESSION_OVERLAP',{**evidence,'release_id':release['id']})
        for r in self.facts['network']:
            if r['kind']!='restriction':continue
            p=r['payload']
            if p['type'] not in ['CLOSURE','WORK_PROHIBITED','ISOLATION_UNAVAILABLE']:raise ValueError('UNSUPPORTED_RESTRICTION')
            self.check(not(set(p['footprint'])&tracks and intersects(start,end,instant(p['start']),instant(p['end']))),
                       'INFRASTRUCTURE','RESTRICTION_OVERLAP',{**evidence,'restriction_id':r['id']})
        if not self.context:return
        c=self.context
        for track in tracks:
            allowed=[(instant(w['start_at']),instant(w['end_at'])) for w in self.facts['coa'] if w['track_id']==track]
            self.check(covers(allowed,start,end),'TRAFFIC','OUTSIDE_COA_WINDOW',{**evidence,'track_id':track})
        for train in self.facts['occupancy']:
            before=instant(train['enter_at'])-timedelta(minutes=c['clearance_before_minutes'])
            after=instant(train['exit_at'])+timedelta(minutes=c['clearance_after_minutes'])
            self.check(not(train['track_id'] in tracks and intersects(start,end,before,after)),
                       'TRAFFIC','TRAIN_CLEARANCE_VIOLATION',{**evidence,'occupancy_id':train['id']})
        if c['protect_freight_envelope']:
            for f in self.facts['freight']:self.check(not(f['track_id'] in tracks and intersects(start,end,instant(f['start_at']),instant(f['end_at']))),
                'TRAFFIC','FREIGHT_ENVELOPE_OVERLAP',{**evidence,'forecast_id':f['id']})

    def inspect_commitments(self):
        commitments=self.facts.get('commitments',[])
        if not commitments:self.check(bool(self.context and self.context['commitments_known_empty']),'COMMITMENTS','COMMITMENT_STATE_UNKNOWN',error=True)
        else:self.check(not(self.context and self.context['commitments_known_empty']),'COMMITMENTS','CONTRADICTORY_COMMITMENT_DECLARATION')
        selected={b['id']:b for b in self.blocks}
        for c in commitments:
            self.tick()
            if not {'id','candidate_id','frozen'}<=set(c) or type(c['frozen'])!=bool:raise ValueError('UNSUPPORTED_COMMITMENT_FACT')
            if not c.get('frozen'):continue
            expected=c.get('assignment_hash')
            self.check(expected is not None,'COMMITMENTS','FROZEN_CONTENT_UNKNOWN',{'commitment_id':c['id']},error=True)
            actual=selected.get(c['candidate_id'])
            self.check(actual is not None and content_hash(actual)==expected,'COMMITMENTS','FROZEN_WORK_CHANGED',{'commitment_id':c['id']})
        for c in self.facts.get('completed_work',[]):
            self.check(c.get('verified') is True,'COMMITMENTS','COMPLETION_UNVERIFIED',error=True)
            self.check(c['request_id'] not in self.tasks,'COMMITMENTS','COMPLETED_WORK_RESCHEDULED',{'request_id':c['request_id']})

    def result(self):
        checks=[]
        for category in CATEGORIES:
            findings=[f for f in self.findings if f['category']==category]
            status='ERROR' if any(f['status']=='ERROR' for f in findings) else 'FAIL' if findings else 'PASS' if category in self.completed else 'NOT_RUN'
            checks.append({'category':category,'status':status,'findings':findings})
        status='ERROR' if any(c['status'] in ['ERROR','NOT_RUN'] for c in checks) else 'FAIL' if self.findings else 'PASS'
        return {'status':status,'validator_version':VERSION,'plan_hash':self.plan_hash,'snapshot_hash':self.snapshot_hash,
                'checked_at':self.checked_at.isoformat(),'scope':self.scope,'checks':checks,'checks_performed':self.operations,
                'current_facts_hash':self.current_facts_hash,'approval_blocked':status!='PASS','authority':'CONFIGURED_PROTOTYPE_CONSTRAINTS_ONLY'}

def validate(manifest,snapshot_hash,plan,plan_hash,checked_at,current_facts_hash=None,*,max_seconds=5,max_checks=500000):
    inspector=None
    try:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:raise ValueError('NAIVE_CHECK_TIME')
        inspector=Inspector(manifest,snapshot_hash,plan,plan_hash,checked_at,current_facts_hash,max_seconds,max_checks)
        inspector.run()
    except Exception as error:
        code=('VALIDATION_BUDGET_EXCEEDED' if isinstance(error,ValidationBudgetExceeded) else 'FACT_SCHEMA_INVALID' if isinstance(error,ValidationError) else
              'MALFORMED_OR_UNSUPPORTED_INPUT' if isinstance(error,(ValueError,KeyError,TypeError)) else 'VALIDATOR_EXCEPTION')
        finding={'category':'PROVENANCE','status':'ERROR','code':code,'evidence':{'error_type':type(error).__name__}}
        if inspector:inspector.findings.append(finding)
        else:return {'status':'ERROR','validator_version':VERSION,'plan_hash':plan_hash,'snapshot_hash':snapshot_hash,'checked_at':checked_at.isoformat() if isinstance(checked_at,datetime) else None,
                     'scope':'UNKNOWN','checks':[{'category':'PROVENANCE','status':'ERROR','findings':[finding]}],'approval_blocked':True,
                     'authority':'CONFIGURED_PROTOTYPE_CONSTRAINTS_ONLY'}
    return inspector.result()
