"""Append-only remaining-work reconciliation and verified possession release."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB

revision='019'
down_revision='018'
branch_labels=depends_on=None


def common():
    return [sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('idempotency_key',UUID(as_uuid=True),nullable=False,unique=True),
        sa.Column('payload_hash',sa.String(64),nullable=False),sa.Column('payload',JSONB(),nullable=False),
        sa.Column('result',JSONB(),nullable=False),sa.Column('actor',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False)]


def upgrade():
    op.create_table('work_reconciliations',*common(),
        sa.Column('execution_record_id',UUID(as_uuid=True),sa.ForeignKey('execution_records.id'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.UniqueConstraint('execution_record_id','revision'))
    op.create_table('possession_releases',*common(),
        sa.Column('decision_id',UUID(as_uuid=True),sa.ForeignKey('controller_decisions.id'),nullable=False),
        sa.Column('candidate_id',sa.String(100),nullable=False),
        sa.Column('reservation_id',UUID(as_uuid=True),sa.ForeignKey('plan_reservations.id'),nullable=False,unique=True),
        sa.UniqueConstraint('decision_id','candidate_id'))
    for table in ('work_reconciliations','possession_releases'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_mutation()')


def downgrade():
    op.drop_table('possession_releases')
    op.drop_table('work_reconciliations')
