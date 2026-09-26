"""Persist a real candidate pipeline and queue both planners in one transaction."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from .models import (AvailabilityComputation, CoordinationComputation,
    OpportunityComputation, PlanningRun, PriorityAssessment)
from .requests import digest
from .priority import POLICY_VERSION, classify, rule_assessment
from .availability import AvailabilityInput, compute_availability
from .opportunities import OpportunityInput, generate
from .coordination import CoordinationInput, ENGINE_VERSION
from .coordination_engine import coordinate
from .planning import RunInput


def queue_proposal(db, snapshot, assessed_at, context, solver_options=None):
    facts = snapshot.manifest['facts']
    assessments = []
    for request in facts['requests']:
        existing = db.scalar(select(PriorityAssessment).where(PriorityAssessment.snapshot_id == snapshot.id,
            PriorityAssessment.request_id == uuid.UUID(request['id']), PriorityAssessment.policy_version == POLICY_VERSION,
            PriorityAssessment.assessed_at == assessed_at))
        if existing:
            assessments.append(existing)
            continue
        features, contributions, score = rule_assessment(request['payload'], assessed_at)
        row = PriorityAssessment(snapshot_id=snapshot.id, request_id=uuid.UUID(request['id']),
            policy_version=POLICY_VERSION, method='RULE', score_basis_points=score,
            priority_band=classify(score/100), features=features,
            contributions=contributions, assessed_at=assessed_at)
        db.add(row); assessments.append(row)
    db.flush()
    available = []
    footprints = {tuple(sorted(r['payload']['footprint'])) for r in facts['requests']}
    if not footprints: footprints = {tuple(sorted(snapshot.manifest['track_ids']))}
    for footprint in sorted(footprints):
        policy = AvailabilityInput(snapshot_id=snapshot.id, track_ids=list(footprint),
            clearance_before_minutes=context.clearance_before_minutes,
            clearance_after_minutes=context.clearance_after_minutes,
            protect_freight_envelope=context.protect_freight_envelope).model_dump(mode='json')
        input_hash = digest({'snapshot_hash': snapshot.content_hash, 'policy': policy})
        row = db.scalar(select(AvailabilityComputation).where(AvailabilityComputation.input_hash == input_hash))
        if row is None:
            row = AvailabilityComputation(snapshot_id=snapshot.id, input_hash=input_hash,
                policy=policy, result=compute_availability(snapshot.manifest, policy))
            db.add(row)
        available.append(row)
    db.flush()
    opportunity_config = OpportunityInput(snapshot_id=snapshot.id,
        availability_ids=[r.id for r in available], assessed_at=assessed_at).model_dump(mode='json')
    opportunity_hash = digest({'snapshot_hash': snapshot.content_hash,
        'availability_hashes': sorted(r.input_hash for r in available),
        'config': opportunity_config})
    opportunity = db.scalar(select(OpportunityComputation).where(OpportunityComputation.input_hash == opportunity_hash))
    if opportunity is None:
        opportunity = OpportunityComputation(snapshot_id=snapshot.id, input_hash=opportunity_hash,
            configuration=opportunity_config,
            result=generate(snapshot, available, assessments, opportunity_config))
        db.add(opportunity); db.flush()
    coordinate_config = CoordinationInput(opportunity_id=opportunity.id).model_dump(mode='json')
    coordinate_hash = digest({'snapshot_hash': snapshot.content_hash,
        'opportunity_hash': opportunity.input_hash, 'engine_version': ENGINE_VERSION,
        'config': coordinate_config})
    coordination = db.scalar(select(CoordinationComputation).where(CoordinationComputation.input_hash == coordinate_hash))
    coordinated = coordination.result if coordination else coordinate(snapshot.manifest, opportunity.result,
        [{'policy': r.policy, 'result': r.result, 'input_hash': r.input_hash}
            for r in available], coordinate_config)
    if coordination is None:
        coordinated['engine_version'] = ENGINE_VERSION
        coordinated['snapshot_hash'] = snapshot.content_hash
    if coordinated['status'] == 'BLOCKED':
        raise HTTPException(409, {'code': 'COORDINATION_BLOCKED',
            'exclusions': coordinated.get('exclusions', [])})
    if coordination is None:
        coordination = CoordinationComputation(snapshot_id=snapshot.id,
            opportunity_id=opportunity.id, input_hash=coordinate_hash,
            configuration=coordinate_config, result=coordinated)
        db.add(coordination); db.flush()
    runs = []
    for planner in ('BASELINE', 'CP_SAT'):
        config = RunInput(snapshot_id=snapshot.id, planner_type=planner,
            coordination_id=coordination.id,
            clearance_minutes=context.clearance_before_minutes,
            protect_freight_envelope=context.protect_freight_envelope,
            **({'solver_options': solver_options} if solver_options is not None else {})).model_dump(mode='json')
        run = PlanningRun(snapshot_id=snapshot.id, planner_type=planner,
            status='QUEUED', config=config)
        db.add(run); runs.append(run)
    db.flush()
    return {'priority_count': len(assessments),
        'availability_ids': [str(r.id) for r in available],
        'opportunity_id': str(opportunity.id), 'coordination_id': str(coordination.id),
        'candidate_count': coordinated['counts']}, runs
