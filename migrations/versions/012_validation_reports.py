"""Append-only independent validation reports bound to exact plan/snapshot hashes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='012'
down_revision='011'
branch_labels=depends_on=None

def upgrade():
    op.create_table('validation_reports',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('run_id',UUID(as_uuid=True),sa.ForeignKey('planning_runs.id'),nullable=False),
        sa.Column('snapshot_id',UUID(as_uuid=True),sa.ForeignKey('planning_snapshots.id'),nullable=False),
        sa.Column('plan_hash',sa.String(64),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('validator_version',sa.String(80),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('checked_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('result',JSONB(),nullable=False))
    op.execute('CREATE TRIGGER validation_report_immutable BEFORE UPDATE OR DELETE ON validation_reports '
               'FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():op.drop_table('validation_reports')
