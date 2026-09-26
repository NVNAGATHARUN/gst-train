"""Immutable, source-bound what-if scenarios with isolated planning runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '022'
down_revision = '021'
branch_labels = depends_on = None


def upgrade():
    op.create_table('what_if_scenarios',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('idempotency_key', UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('source_snapshot_id', UUID(as_uuid=True), sa.ForeignKey('planning_snapshots.id'), nullable=False),
        sa.Column('snapshot_id', UUID(as_uuid=True), sa.ForeignKey('planning_snapshots.id'), nullable=False, unique=True),
        sa.Column('baseline_run_id', UUID(as_uuid=True), sa.ForeignKey('planning_runs.id'), nullable=False),
        sa.Column('optimized_run_id', UUID(as_uuid=True), sa.ForeignKey('planning_runs.id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.execute('CREATE TRIGGER what_if_scenarios_immutable BEFORE UPDATE OR DELETE ON what_if_scenarios FOR EACH ROW EXECUTE FUNCTION deny_mutation()')


def downgrade():
    op.drop_table('what_if_scenarios')
