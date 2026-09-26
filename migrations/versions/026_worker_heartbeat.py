"""Worker heartbeat evidence for truthful administration health."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision='026'
down_revision='025'
branch_labels=depends_on=None

def upgrade():
    op.create_table('worker_heartbeats',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('last_seen_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('stopped_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('ix_worker_heartbeats_last_seen_at','worker_heartbeats',['last_seen_at'])

def downgrade():
    op.drop_index('ix_worker_heartbeats_last_seen_at',table_name='worker_heartbeats')
    op.drop_table('worker_heartbeats')
