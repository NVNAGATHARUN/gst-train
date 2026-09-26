"""One prepared replacement per source plan and disruption generation."""
from alembic import op

revision = '021'
down_revision = '020'
branch_labels = depends_on = None


def upgrade():
    op.create_unique_constraint('uq_replan_source_generation', 'event_reconciliations',
        ['source_plan_revision_id', 'batch_generation'])


def downgrade():
    op.drop_constraint('uq_replan_source_generation', 'event_reconciliations', type_='unique')
