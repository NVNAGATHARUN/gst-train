"""Shared persistence guard, independent of scheduling and feasibility logic."""
from sqlalchemy import select, text
from .models import SnapshotInvalidation,PlanningSnapshot


def lock_publication(db):
    # Event intake, run queueing and result publication use the same lock order.
    db.execute(text('SELECT pg_advisory_xact_lock(2602716)'))


def invalidation_ids(db, snapshot_id):
    return [str(id) for id in db.scalars(select(SnapshotInvalidation.event_id)
        .where(SnapshotInvalidation.snapshot_id == snapshot_id).order_by(SnapshotInvalidation.event_id))]


def invalidated_facts(db, facts):
    return db.scalar(select(SnapshotInvalidation.event_id).join(PlanningSnapshot,
        PlanningSnapshot.id==SnapshotInvalidation.snapshot_id)
        .where(PlanningSnapshot.manifest['facts']==facts).limit(1)) is not None
