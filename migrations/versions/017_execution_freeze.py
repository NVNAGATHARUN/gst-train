"""M16 immutable execution observations and explicit versioned freeze policy."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision='017'
down_revision='016'
branch_labels=depends_on=None


def upgrade():
    op.create_table('freeze_policies',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('scope',sa.String(16),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('freeze_minutes',sa.Integer(),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),
        sa.Column('actor',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('scope','revision'),
        sa.CheckConstraint('freeze_minutes >= 0 AND freeze_minutes <= 10080'))
    op.create_table('execution_records',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('idempotency_key',UUID(as_uuid=True),nullable=False,unique=True),
        sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('decision_id',UUID(as_uuid=True),sa.ForeignKey('controller_decisions.id'),nullable=False),
        sa.Column('request_id',sa.String(100),nullable=False),
        sa.Column('candidate_id',sa.String(100),nullable=False),
        sa.Column('assignment_hash',sa.String(64),nullable=False),
        sa.Column('scope',sa.String(16),nullable=False),
        sa.Column('sequence',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),
        sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('received_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),sa.Column('result',JSONB(),nullable=False),
        sa.Column('actor',sa.String(100),nullable=False),
        sa.UniqueConstraint('request_id','sequence'),
        sa.CheckConstraint('sequence > 0'),
        sa.CheckConstraint("status IN ('STARTED','INTERRUPTED','RESUMED','COMPLETED')"))
    for table in ('freeze_policies','execution_records'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_mutation()')


def downgrade():
    op.drop_table('execution_records')
    op.drop_table('freeze_policies')
