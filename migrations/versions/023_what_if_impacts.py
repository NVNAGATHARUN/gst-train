"""Immutable validated source-versus-scenario impact records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '023'
down_revision = '022'
branch_labels = depends_on = None


def upgrade():
    op.create_table('what_if_impacts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('scenario_id', UUID(as_uuid=True), sa.ForeignKey('what_if_scenarios.id'), nullable=False),
        sa.Column('source_plan_revision_id', UUID(as_uuid=True), sa.ForeignKey('plan_revisions.id'), nullable=False),
        sa.Column('scenario_plan_revision_id', UUID(as_uuid=True), sa.ForeignKey('plan_revisions.id'), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('content', JSONB(), nullable=False),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('scenario_id', 'source_plan_revision_id', 'scenario_plan_revision_id',
            name='uq_what_if_impact_plans'))
    op.execute('CREATE TRIGGER what_if_impacts_immutable BEFORE UPDATE OR DELETE ON what_if_impacts FOR EACH ROW EXECUTE FUNCTION deny_mutation()')


def downgrade():
    op.drop_table('what_if_impacts')
