"""Immutable resource/policy revisions and concrete candidate computations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '010'
down_revision = '009'
branch_labels = depends_on = None

def upgrade():
    op.create_table('coordination_revisions',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('kind', sa.String(30), nullable=False),
        sa.Column('entity_key', sa.String(100), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('payload', pg.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('kind', 'entity_key', 'revision'))
    op.create_table('coordination_computations',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('snapshot_id', pg.UUID(as_uuid=True), sa.ForeignKey('planning_snapshots.id'), nullable=False),
        sa.Column('opportunity_id', pg.UUID(as_uuid=True), sa.ForeignKey('opportunity_computations.id'), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('configuration', pg.JSONB(), nullable=False),
        sa.Column('result', pg.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    for table in ['coordination_revisions', 'coordination_computations']:
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} '
                   'FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():
    op.drop_table('coordination_computations')
    op.drop_table('coordination_revisions')
