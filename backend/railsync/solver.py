"""Fixed-candidate CP-SAT selection under SRS section 18.

Only actual solver incumbents become assignments. This is not the independent validator.
"""
from datetime import datetime
from typing import Literal
from pydantic import Field
from ortools.sat.python import cp_model
import ortools
from .requests import StrictModel, digest

MODEL_VERSION='FIXED_CANDIDATE_CP_SAT_V2'
COST_FIELDS={'possession':'reserved_track_minutes','freight':'forecast_exposure_train_track_seconds',
             'travel':'incremental_travel_minutes_against_fixed_duties'}

class ObjectiveWeights(StrictModel):
    deferred_utility:int=Field(default=100,ge=0,le=1000000)
    possession:int=Field(default=1,ge=0,le=1000000)
    freight:int=Field(default=0,ge=0,le=1000000)
    travel:int=Field(default=1,ge=0,le=1000000)
    commitment_change:int=Field(default=100,ge=0,le=1000000)

class SolverOptions(StrictModel):
    weights:ObjectiveWeights=Field(default_factory=ObjectiveWeights)
    max_time_seconds:float=Field(default=10,ge=0,le=300,allow_inf_nan=False)
    random_seed:int=Field(default=26027,ge=0,le=2147483647)
    workers:int=Field(default=1,ge=1,le=8)

def parse(value):return datetime.fromisoformat(value)

def instance(manifest,coordination,priorities):
    requests={r['id']:r for r in manifest['facts']['requests']}
    candidates={c['id']:c for c in coordination['candidates']}
    if len(candidates)!=len(coordination['candidates']):raise ValueError('DUPLICATE_CANDIDATE_ID')
    if set(requests)-set(priorities):raise ValueError('PRIORITY_FACTS_MISSING')
    for id,value in priorities.items():
        if type(value)!=int or not 0<=value<=10000:raise ValueError('INVALID_PRIORITY_SCALE')
    coverage={id:[] for id in requests}
    for id,c in candidates.items():
        if not c['request_ids'] or len(set(c['request_ids']))!=len(c['request_ids']):raise ValueError('INVALID_CANDIDATE_COVERAGE')
        if set(c['request_ids'])!={t['request_id'] for t in c['tasks']}:raise ValueError('TASK_COVERAGE_MISMATCH')
        if len(c['tasks'])!=len(c['request_ids']):raise ValueError('DUPLICATE_CANDIDATE_TASK')
        for request in c['request_ids']:
            if request not in coverage:raise ValueError('UNKNOWN_CANDIDATE_REQUEST')
            coverage[request].append(id)
        for field in COST_FIELDS.values():
            if type(c['costs'][field])!=int:raise ValueError('NON_INTEGER_COST')
    conflicts={tuple(sorted([e['left'],e['right']])) for e in coordination['incompatibilities']}
    if any(a==b or a not in candidates or b not in candidates for a,b in conflicts):raise ValueError('INVALID_CONFLICT_REFERENCE')
    for row in coordination['aggregate_constraints']:
        if row['kind'] not in ['POOL_CAPACITY','ROLLING_DUTY_SECONDS']:raise ValueError('UNSUPPORTED_CAPACITY_CONSTRAINT')
        if type(row['capacity'])!=int or any(id not in candidates or type(v)!=int or v<0 for id,v in row['coefficients'].items()):
            raise ValueError('INVALID_CAPACITY_COEFFICIENT')
    # Precedence is encoded directly as well as retained in M10 conflict evidence.
    dependencies=[]
    completed={c['request_id']:c for c in manifest['facts'].get('completed_work',[]) if c.get('verified') and c.get('restoration_verified')}
    for id,r in requests.items():
        for predecessor in r['payload']['predecessors']:
            if predecessor in completed and predecessor not in requests:
                for cid in coverage[id]:
                    task=next(t for t in candidates[cid]['tasks'] if t['request_id']==id)
                    if parse(completed[predecessor]['restored_at'])>parse(task['setup_start']):conflicts.add((cid,cid))
                continue
            dependencies.append((id,predecessor))
            if predecessor not in requests:continue
            for left in coverage[id]:
                for right in coverage[predecessor]:
                    a=next(t for t in candidates[left]['tasks'] if t['request_id']==id)
                    b=next(t for t in candidates[right]['tasks'] if t['request_id']==predecessor)
                    if parse(b['restore_end'])>parse(a['setup_start']):conflicts.add(tuple(sorted([left,right])))
    commitments=manifest['facts'].get('commitments',[])
    if any(not {'id','candidate_id','frozen'}<=set(c) or
           set(c)-{'id','candidate_id','frozen','assignment_hash','assignment'} or type(c['frozen'])!=bool for c in commitments):
        raise ValueError('UNSUPPORTED_COMMITMENT_FACT')
    for commitment in commitments:
        cid=commitment['candidate_id'];expected=commitment.get('assignment_hash')
        if expected is not None and cid in candidates and digest(candidates[cid])!=expected:
            raise ValueError('COMMITMENT_CANDIDATE_HASH_MISMATCH')
        if 'assignment' in commitment and digest(commitment['assignment'])!=expected:
            raise ValueError('COMMITMENT_SOURCE_HASH_MISMATCH')
    if len({c['id'] for c in commitments})!=len(commitments):raise ValueError('DUPLICATE_COMMITMENT')
    mandatory={id for id,r in requests.items() if r['payload']['mandatory'] and
               parse(r['payload']['deadline_at'])<=parse(manifest['horizon_end'])}
    return requests,candidates,coverage,conflicts,dependencies,commitments,mandatory

def objective_terms(selected,requests,candidates,priorities,commitments,weights):
    covered={id for cid in selected for id in candidates[cid]['request_ids']}
    raw={'deferred_utility':sum(priorities[id] for id in requests if id not in covered),
         **{term:sum(candidates[id]['costs'][field] for id in selected) for term,field in COST_FIELDS.items()},
         'commitment_change':sum(c['candidate_id'] not in selected for c in commitments)}
    return {key:{'raw':value,'weight':weights[key],'weighted':value*weights[key]} for key,value in raw.items()}

def solve(manifest,coordination,priorities,options):
    options=SolverOptions.model_validate(options).model_dump()
    weights=options['weights']
    requests,candidates,coverage,conflicts,dependencies,commitments,mandatory=instance(manifest,coordination,priorities)
    model=cp_model.CpModel()
    x={id:model.new_bool_var('candidate_'+id) for id in candidates}
    y={id:model.new_bool_var('covered_'+id) for id in requests}
    for id in requests:
        model.add(sum(x[c] for c in coverage[id])==y[id])
        if id in mandatory:model.add(y[id]==1)
    for a,b in conflicts:model.add(x[a]+x[b]<=1)
    for row in coordination['aggregate_constraints']:
        model.add(sum(coefficient*x[id] for id,coefficient in row['coefficients'].items())<=row['capacity'])
    for id,predecessor in dependencies:
        model.add(y[id] <= y[predecessor] if predecessor in y else y[id]==0)
    for commitment in commitments:
        if commitment['frozen']:
            model.add(x[commitment['candidate_id']]==1 if commitment['candidate_id'] in x else False)
    objective=sum(weights['deferred_utility']*priorities[id]*(1-y[id]) for id in requests)
    coefficients={id:sum(weights[term]*c['costs'][field] for term,field in COST_FIELDS.items()) for id,c in candidates.items()}
    # Keep integer arithmetic exact in both solver bounds and returned JSON numbers.
    magnitude=sum(abs(v) for v in coefficients.values())+sum(priorities.values())*weights['deferred_utility']+len(commitments)*weights['commitment_change']
    if magnitude>2**50:raise ValueError('OBJECTIVE_SCALE_EXCEEDS_EXACT_REPORTING_LIMIT')
    objective+=sum(coefficients[id]*x[id] for id in candidates)
    objective+=sum(weights['commitment_change']*(1-x[c['candidate_id']] if c['candidate_id'] in x else 1) for c in commitments)
    model.minimize(objective)
    validation=model.validate()
    model_hash=digest({'version':MODEL_VERSION,'snapshot':manifest,'coordination':coordination,'priorities':priorities,'options':options})
    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=options['max_time_seconds']
    solver.parameters.random_seed=options['random_seed']
    solver.parameters.num_search_workers=options['workers']
    status=solver.solve(model)
    status_name=solver.status_name(status)
    incumbent=status in [cp_model.OPTIMAL,cp_model.FEASIBLE]
    selected=sorted([id for id in candidates if solver.value(x[id])]) if incumbent else []
    covered={id for cid in selected for id in candidates[cid]['request_ids']}
    terms=objective_terms(selected,requests,candidates,priorities,commitments,weights) if incumbent else None
    objective_value=sum(t['weighted'] for t in terms.values()) if incumbent else None
    if incumbent and abs(solver.objective_value-objective_value)>0.5:raise RuntimeError('OBJECTIVE_RECONCILIATION_FAILED')
    diagnostics={'mandatory_without_candidates':sorted(id for id in mandatory if not coverage[id]),
                 'missing_frozen_candidates':[c['id'] for c in commitments if c['frozen'] and c['candidate_id'] not in candidates],
                 'candidate_exclusions':coordination['exclusions'],'model_validation':validation,
                 'infeasibility_explanation':'NO_MINIMAL_CONFLICT_SET_CLAIMED'}
    return {'planner':'CP_SAT','model_version':MODEL_VERSION,'model_hash':model_hash,
            'ortools_version':ortools.__version__,'solver_status':status_name,'has_incumbent':incumbent,
            'schedule_status':'DEVELOPMENT_ARTIFACT' if incumbent else status_name,
            'selection_state':('WORK_SELECTED' if selected else 'EMPTY_OPTIONAL_SOLUTION') if incumbent else 'NO_INCUMBENT',
            'assignments':[candidates[id] for id in selected],'selected_candidate_ids':selected,
            'deferred':[{'request_id':id,'reason':('NO_GENERATED_CANDIDATE' if not coverage[id] else 'NOT_SELECTED_UNDER_OBJECTIVE')}
                        for id in sorted(requests) if incumbent and id not in covered],
            'unresolved_request_ids':sorted(requests) if not incumbent else [],
            'objective_value':objective_value,'objective_terms':terms,
            'best_bound':solver.best_objective_bound if status!=cp_model.MODEL_INVALID else None,
            'relative_gap':abs(objective_value-solver.best_objective_bound)/max(1,abs(objective_value)) if incumbent else None,
            'wall_time_seconds':solver.wall_time,'branches':solver.num_branches,'conflicts':solver.num_conflicts,
            'solver_response_stats':solver.response_stats(),'options':options,
            'optimality_scope':'generated_candidate_set','candidate_search':coordination['search'],
            'review_blockers':coordination['review_blockers'],
            'counts':{'scheduled':len(covered),'deferred':len(requests)-len(covered) if incumbent else 0,
                      'unresolved':len(requests) if not incumbent else 0,'candidates':len(candidates)},
            'diagnostics':diagnostics}

def first_feasible(manifest,coordination,priorities,options):
    """Fair deterministic baseline on identical candidates/constraints, no objective search."""
    options=SolverOptions.model_validate(options).model_dump()
    requests,candidates,coverage,conflicts,dependencies,commitments,mandatory=instance(manifest,coordination,priorities)
    selected=[]
    covered=set()
    # Include the same bundle alternatives; do not sabotage the baseline's choices.
    pending=set(requests)
    def fits(candidate_id):
        if any(tuple(sorted([candidate_id,id])) in conflicts for id in selected):return False
        if (candidate_id,candidate_id) in conflicts:return False
        if covered.intersection(candidates[candidate_id]['request_ids']):return False
        trial=selected+[candidate_id]
        if any(sum(row['coefficients'].get(id,0) for id in trial)>row['capacity'] for row in coordination['aggregate_constraints']):return False
        prospective=covered|set(candidates[candidate_id]['request_ids'])
        if any(id in prospective and p not in prospective for id,p in dependencies):return False
        return True
    fixed={c['candidate_id'] for c in commitments if c['frozen']}
    missing_fixed=[c['id'] for c in commitments if c['frozen'] and c['candidate_id'] not in candidates]
    fixed=fixed.intersection(candidates)
    fixed_covered=[id for c in fixed for id in candidates[c]['request_ids']]
    fixed_invalid=(len(fixed_covered)!=len(set(fixed_covered)) or
        any(a in fixed and b in fixed for a,b in conflicts) or
        any(sum(row['coefficients'].get(id,0) for id in fixed)>row['capacity'] for row in coordination['aggregate_constraints']))
    if fixed_invalid:missing_fixed+=[c['id'] for c in commitments if c['frozen']]
    else:
        selected=sorted(fixed)
        covered=set(fixed_covered)
    while pending:
        progress=False
        for id in sorted(pending,key=lambda id:(id not in mandatory,parse(requests[id]['payload']['deadline_at']),id)):
            if id in covered:
                pending.remove(id)
                progress=True
                continue
            # Defer dependent work until its predecessor has been considered.
            if any(r==id and p in pending and p!=id for r,p in dependencies):continue
            ordered=sorted(coverage[id],key=lambda c:(parse(candidates[c]['possession_start']),candidates[c]['costs']['reserved_track_minutes'],c))
            for candidate_id in ordered:
                if fits(candidate_id):
                    selected.append(candidate_id)
                    covered.update(candidates[candidate_id]['request_ids'])
                    break
            pending.remove(id)
            progress=True
        if not progress:break
    mandatory_failed=bool(mandatory-covered or missing_fixed or any(id in covered and p not in covered for id,p in dependencies))
    terms=objective_terms(selected,requests,candidates,priorities,commitments,options['weights'])
    return {'planner':'FIRST_FEASIBLE_CANDIDATE_BASELINE','solver_status':None,
        'schedule_status':'NON_APPROVABLE' if mandatory_failed else 'DEVELOPMENT_ARTIFACT',
        'assignments':[candidates[id] for id in selected],'selected_candidate_ids':selected,
        'deferred':[{'request_id':id,'reason':'NO_FIRST_FEASIBLE_SELECTION'} for id in sorted(set(requests)-covered)],
        'counts':{'scheduled':len(covered),'deferred':len(requests)-len(covered),'unresolved':0,'candidates':len(candidates)},
        'objective_terms':terms,'objective_value':sum(t['weighted'] for t in terms.values()),
        'review_blockers':coordination['review_blockers'],'candidate_search':coordination['search'],
        'baseline_policy':'mandatory then deadline then request ID; first feasible start, track-minutes, candidate ID; same bundles and constraints',
        'missing_frozen_commitments':missing_fixed,'optimality_claim':False}
