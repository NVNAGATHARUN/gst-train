"""Repeatable generated-candidate solver benchmarks; no operational-performance claim."""
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

from railsync.requests import digest
from railsync.solver import first_feasible, solve

START = datetime.fromisoformat('2026-09-21T00:00:00+05:30')
END = datetime.fromisoformat('2026-09-22T00:00:00+05:30')


def generated_case(request_count):
    requests = []
    candidates = []
    slot_coefficients = {slot: {} for slot in range(24)}
    priorities = {}
    for index in range(request_count):
        request_id = f'R{index:04d}'
        requests.append({'id': request_id, 'revision': 1, 'payload': {
            'mandatory': False, 'predecessors': [], 'deadline_at': END.isoformat()}})
        priorities[request_id] = 1000 + (index % 9) * 500
        for alternative in range(3):
            slot = (index * 7 + alternative * 5) % 24
            begin = START + timedelta(minutes=slot * 30)
            finish = begin + timedelta(minutes=20 + alternative * 5)
            candidate_id = f'C{index:04d}-{alternative}'
            candidates.append({
                'id': candidate_id, 'request_ids': [request_id],
                'tasks': [{'request_id': request_id, 'setup_start': begin.isoformat(),
                           'restore_end': finish.isoformat()}],
                'possession_start': begin.isoformat(),
                'costs': {'reserved_track_minutes': 20 + alternative * 5,
                          'forecast_exposure_train_track_seconds': (slot % 4) * 60,
                          'incremental_travel_minutes_against_fixed_duties': alternative * 2}})
            slot_coefficients[slot][candidate_id] = 1
    capacity = math.ceil(request_count / 24) + 1
    coordination = {
        'candidates': candidates, 'incompatibilities': [],
        'aggregate_constraints': [{'kind': 'POOL_CAPACITY', 'capacity': capacity,
            'coefficients': coefficients} for coefficients in slot_coefficients.values()],
        'exclusions': [], 'search': {'fixture': 'SIMULATED', 'seed': 26027,
            'alternatives_per_request': 3, 'optimality_scope': 'generated_candidate_set'},
        'review_blockers': ['SIMULATED_BENCHMARK_NOT_OPERATIONAL_AUTHORITY',
                            'INDEPENDENT_VALIDATION_NOT_RUN_IN_SOLVER_BENCHMARK']}
    manifest = {'horizon_start': START.isoformat(), 'horizon_end': END.isoformat(),
                'facts': {'requests': requests, 'commitments': []}}
    return manifest, coordination, priorities


def test_repeatable_20_100_300_request_solver_benchmarks():
    results = []
    for count in (20, 100, 300):
        manifest, coordination, priorities = generated_case(count)
        options = {'random_seed': 26027, 'workers': 1, 'max_time_seconds': 10,
                   'weights': {'deferred_utility': 100, 'possession': 1,
                               'freight': 1, 'travel': 1, 'commitment_change': 100}}
        baseline_started = perf_counter()
        baseline = first_feasible(manifest, coordination, priorities, options)
        baseline_elapsed = perf_counter() - baseline_started
        optimized_started = perf_counter()
        optimized = solve(manifest, coordination, priorities, options)
        optimized_elapsed = perf_counter() - optimized_started
        assert baseline['counts']['candidates'] == count * 3
        assert optimized['counts']['candidates'] == count * 3
        assert optimized['solver_status'] in ('OPTIMAL', 'FEASIBLE')
        assert optimized['has_incumbent']
        assert optimized['objective_value'] <= baseline['objective_value']
        results.append({
            'scope': 'SIMULATED fixed-candidate solver benchmark; not end-to-end or live railway',
            'request_count': count, 'candidate_count': count * 3,
            'input_hash': digest({'manifest': manifest, 'coordination': coordination,
                                  'priorities': priorities, 'options': options}),
            'baseline': {'scheduled': baseline['counts']['scheduled'],
                         'objective_value': baseline['objective_value'],
                         'measured_elapsed_seconds': baseline_elapsed},
            'cp_sat': {'status': optimized['solver_status'],
                       'scheduled': optimized['counts']['scheduled'],
                       'objective_value': optimized['objective_value'],
                       'best_bound': optimized['best_bound'],
                       'relative_gap': optimized['relative_gap'],
                       'solver_wall_time_seconds': optimized['wall_time_seconds'],
                       'measured_elapsed_seconds': optimized_elapsed,
                       'branches': optimized['branches'], 'conflicts': optimized['conflicts'],
                       'ortools_version': optimized['ortools_version'],
                       'model_hash': optimized['model_hash']},
            'raw_objective_delta_cp_sat_minus_baseline':
                optimized['objective_value'] - baseline['objective_value'],
            'limits': ['OPTIMALITY_ONLY_OVER_GENERATED_CANDIDATE_SET',
                       'NO_TRAIN_DELAY_OR_ASSET_RELIABILITY_CLAIM',
                       'NO_INDEPENDENT_VALIDATION_IN_THIS_SOLVER_BENCHMARK']
        })
    if path := os.environ.get('RAILSYNC_M18_BENCHMARK_OUTPUT'):
        Path(path).write_text(json.dumps({'seed':26027, 'results':results}, indent=2),
                              encoding='utf-8')
