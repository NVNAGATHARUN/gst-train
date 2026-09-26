"""M16 foundation: immutable disruptions, invalidations and debounce generation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='016'
down_revision='015'
branch_labels=depends_on=None

def upgrade():
    op.create_table('disruption_events',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('source',sa.String(80),nullable=False),sa.Column('external_id',sa.String(100),nullable=False),
        sa.Column('source_revision',sa.Integer(),nullable=False),sa.Column('scope',sa.String(16),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('received_at',sa.DateTime(timezone=True),nullable=False),sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),sa.Column('result',JSONB(),nullable=False),sa.Column('actor',sa.String(100),nullable=False),
        sa.UniqueConstraint('source','external_id','source_revision'))
    op.create_table('snapshot_invalidations',
        sa.Column('snapshot_id',UUID(as_uuid=True),sa.ForeignKey('planning_snapshots.id'),primary_key=True),
        sa.Column('event_id',UUID(as_uuid=True),sa.ForeignKey('disruption_events.id'),primary_key=True))
    op.create_table('replanning_batches',sa.Column('scope',sa.String(16),primary_key=True),
        sa.Column('generation',sa.Integer(),nullable=False),sa.Column('ready_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('latest_event_id',UUID(as_uuid=True),sa.ForeignKey('disruption_events.id'),nullable=False))
    for table in ('disruption_events','snapshot_invalidations'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():
    for table in ('replanning_batches','snapshot_invalidations','disruption_events'):op.drop_table(table)
