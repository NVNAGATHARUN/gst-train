"""Immutable event-to-source reconciliation and queued rolling-horizon proposal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB

revision='020'
down_revision='019'
branch_labels=depends_on=None

def upgrade():
    op.create_table('event_reconciliations',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('idempotency_key',UUID(as_uuid=True),nullable=False,unique=True),
        sa.Column('source_plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('batch_generation',sa.Integer(),nullable=False),
        sa.Column('source_snapshot_id',UUID(as_uuid=True),sa.ForeignKey('planning_snapshots.id'),nullable=False),
        sa.Column('capture_id',UUID(as_uuid=True),sa.ForeignKey('replanning_captures.id'),nullable=False),
        sa.Column('snapshot_id',UUID(as_uuid=True),sa.ForeignKey('planning_snapshots.id'),nullable=False),
        sa.Column('baseline_run_id',UUID(as_uuid=True),sa.ForeignKey('planning_runs.id'),nullable=False),
        sa.Column('optimized_run_id',UUID(as_uuid=True),sa.ForeignKey('planning_runs.id'),nullable=False),
        sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),
        sa.Column('created_by',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER event_reconciliations_immutable BEFORE UPDATE OR DELETE ON event_reconciliations FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():
    op.drop_table('event_reconciliations')
