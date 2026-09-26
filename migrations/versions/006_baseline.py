"""Basic resources and durable planning-run records."""
from alembic import op
from railsync.models import ResourceUnit,PlanningRun
revision='006';down_revision='005';branch_labels=depends_on=None
def upgrade():
    ResourceUnit.__table__.create(op.get_bind());PlanningRun.__table__.create(op.get_bind())
def downgrade():
    op.drop_table('planning_runs');op.drop_table('resource_units')
