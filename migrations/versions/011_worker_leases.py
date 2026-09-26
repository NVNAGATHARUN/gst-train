"""Recoverable durable planning work with fenced publication."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='011'
down_revision='010'
branch_labels=depends_on=None

def upgrade():
    op.create_table('worker_leases',
        sa.Column('run_id',UUID(as_uuid=True),sa.ForeignKey('planning_runs.id'),primary_key=True),
        sa.Column('token',UUID(as_uuid=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():op.drop_table('worker_leases')
