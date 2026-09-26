"""Versioned, interval-derived planning metrics. No cached optimizer costs are used."""
from collections import defaultdict
from datetime import timedelta
from .validator import instant

VERSION = 'INTERVAL_KPI_V2'


def union_seconds(intervals):
    end = None
    total = 0.0
    for left, right in sorted(intervals):
        if right <= left:
            raise ValueError('NON_POSITIVE_KPI_INTERVAL')
        begin = max(left, end) if end is not None else left
        if right > begin:
            total += (right - begin).total_seconds()
        end = max(end, right) if end is not None else right
    return total


def ratio(numerator, denominator, scale=10000):
    return None if denominator == 0 else numerator * scale / denominator


def metrics(plan, snapshot):
    manifest = snapshot.manifest
    start, end = instant(manifest['horizon_start']), instant(manifest['horizon_end'])
    facts = manifest['facts']
    requests = {r['id']: r['payload'] for r in facts['requests']}
    tracks = set(manifest['track_ids'])
    blocks = plan.get('assignments', [])
    result = {key: None for key in DEFINITIONS}
    result.update(planned_not_completed=True, denominators={}, outcome='NO_VALID_INCUMBENT')
    if plan.get('schedule_status') != 'DEVELOPMENT_ARTIFACT' or (
        plan.get('planner') == 'CP_SAT' and plan.get('solver_status') not in ('OPTIMAL', 'FEASIBLE')
    ):
        return result
    reserved = defaultdict(list)
    tasks = {}
    active_seconds = possession_seconds = task_work_seconds = 0
    for block in blocks:
        begin, finish = instant(block['possession_start']), instant(block['possession_end'])
        if not start <= begin < finish <= end or not set(block['track_ids']) <= tracks:
            raise ValueError('KPI_ASSIGNMENT_OUTSIDE_SCOPE')
        for track in block['track_ids']:
            reserved[track].append((begin, finish))
        possession_seconds += (finish - begin).total_seconds()
        active = []
        for task in block['tasks']:
            rid = task['request_id']
            if rid not in requests or rid in tasks:
                raise ValueError('UNKNOWN_OR_DUPLICATE_KPI_REQUEST')
            tasks[rid] = task
            left, right = instant(task['work_start']), instant(task['work_end'])
            if not begin <= left < right <= finish:
                raise ValueError('KPI_WORK_OUTSIDE_POSSESSION')
            active.append((left, right))
            task_work_seconds += (right - left).total_seconds()
        active_seconds += union_seconds(active)
    if len({b['id'] for b in blocks}) != len(blocks):
        raise ValueError('DUPLICATE_KPI_POSSESSION')
    due = {rid for rid, r in requests.items() if instant(r['deadline_at']) <= end}
    mandatory = {rid for rid in due if requests[rid]['mandatory']}
    on_time = {rid for rid in due & tasks.keys() if instant(tasks[rid][
        'restore_end' if requests[rid]['deadline_kind'] == 'RESTORED_BY' else 'work_end'
    ]) <= instant(requests[rid]['deadline_at'])}
    track_seconds = sum(union_seconds(values) for values in reserved.values())
    # Expected-count * overlap seconds is an exposure proxy, not a delay prediction.
    freight = 0.0
    identities = set()
    for forecast in facts['freight']:
        identity = (forecast['external_id'], forecast['track_id'])
        if identity in identities:
            raise ValueError('AMBIGUOUS_KPI_FORECAST_REVISION')
        identities.add(identity)
        a, b = instant(forecast['start_at']), instant(forecast['end_at'])
        overlap = [(max(a, c), min(b, d)) for c, d in reserved[forecast['track_id']] if c < b and a < d]
        freight += union_seconds(overlap) * forecast['expected_count']
    result.update(
        outcome='COMPUTED_FROM_SAVED_INTERVALS', requests_scheduled=len(tasks),
        critical_requests_scheduled=sum(requests[rid]['criticality'] >= 4 for rid in tasks),
        possession_count=len(blocks), reserved_track_minutes=track_seconds / 60,
        task_work_minutes=task_work_seconds / 60,
        block_utilization_basis_points=ratio(active_seconds, possession_seconds),
        mandatory_coverage_basis_points=ratio(len(mandatory & tasks.keys()), len(mandatory)),
        on_time_coverage_basis_points=ratio(len(on_time), len(due)),
        maintenance_track_availability_basis_points=10000 - ratio(track_seconds, (end-start).total_seconds()*len(tracks)),
        forecast_exposure_train_track_seconds=freight,
        multi_request_possessions=sum(len(b['request_ids']) > 1 for b in blocks),
        bundled_extra_tasks=sum(max(0, len(b['request_ids'])-1) for b in blocks),
        denominators={
            'block_utilization_basis_points': {'numerator': active_seconds/60, 'denominator': possession_seconds/60, 'unit': 'minutes'},
            'mandatory_coverage_basis_points': {'numerator': len(mandatory & tasks.keys()), 'denominator': len(mandatory), 'unit': 'requests'},
            'on_time_coverage_basis_points': {'numerator': len(on_time), 'denominator': len(due), 'unit': 'requests'},
            'maintenance_track_availability_basis_points': {'numerator': (end-start).total_seconds()*len(tracks)/60-track_seconds/60,
                'denominator': (end-start).total_seconds()*len(tracks)/60, 'unit': 'track_minutes'},
        },
    )
    result['solver_wall_time_seconds'] = plan.get('wall_time_seconds')
    return result


# name: (explicit unit, formula, preference). Counts of bundling are descriptive.
DEFINITIONS = {
    'requests_scheduled': ('requests', 'Distinct scheduled request IDs', 'HIGHER_IS_BETTER'),
    'critical_requests_scheduled': ('requests', 'Scheduled requests with criticality >= 4', 'HIGHER_IS_BETTER'),
    'possession_count': ('possessions', 'Distinct selected possession IDs', 'LOWER_IS_BETTER'),
    'reserved_track_minutes': ('track_minutes', 'Sum across tracks of union reserved interval duration', 'LOWER_IS_BETTER'),
    'task_work_minutes': ('task_minutes', 'Sum individual task work durations; parallel tasks may overlap', 'INFORMATIONAL'),
    'block_utilization_basis_points': ('basis_points', 'Union active work within each possession / total possession duration * 10000', 'HIGHER_IS_BETTER'),
    'mandatory_coverage_basis_points': ('basis_points', 'Scheduled mandatory due requests / all mandatory due requests * 10000', 'HIGHER_IS_BETTER'),
    'on_time_coverage_basis_points': ('basis_points', 'Scheduled on-time due requests / all requests due including deferred * 10000', 'HIGHER_IS_BETTER'),
    'maintenance_track_availability_basis_points': ('basis_points', '1 - union maintenance reservation duration / in-scope track-horizon duration; maintenance-only capacity proxy', 'HIGHER_IS_BETTER'),
    'forecast_exposure_train_track_seconds': ('expected_train_track_seconds', 'sum assignment/forecast interval overlap union seconds times expected train count; exposure proxy', 'LOWER_IS_BETTER'),
    'multi_request_possessions': ('possessions', 'Selected blocks with more than one request', 'INFORMATIONAL'),
    'bundled_extra_tasks': ('requests', 'Sum selected request count minus one per block', 'INFORMATIONAL'),
    'measured_train_delay_minutes': ('minutes', 'Unavailable: no actual execution delay feed', 'NOT_MEASURED'),
    'solver_wall_time_seconds': ('seconds', 'Actual solver runtime; no CP-SAT runtime for baseline', 'INFORMATIONAL'),
}


def comparison_metrics(baseline, railsync):
    result = {}
    for name, (unit, formula, direction) in DEFINITIONS.items():
        left, right = baseline[name], railsync[name]
        raw = None if left is None or right is None else right-left
        favorable = None if raw is None or direction in ('INFORMATIONAL', 'NOT_MEASURED') else raw if direction == 'HIGHER_IS_BETTER' else -raw
        result[name] = {
            'unit': unit, 'formula': formula, 'direction': direction,
            'baseline': left, 'railsync': right, 'raw_delta': raw, 'favorable_change': favorable,
            'percent_change': None if raw is None or left == 0 else raw/abs(left)*100,
            'improvement_percent': None if favorable is None or left == 0 else favorable/abs(left)*100,
            'percentage_unit': 'percent',
            'status': 'NOT_AVAILABLE' if raw is None else 'BASELINE_ZERO_PERCENT_NA' if left == 0 else 'AVAILABLE',
        }
    return result
