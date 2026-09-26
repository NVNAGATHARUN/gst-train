"""Traceable rule priority and gated ML experiment metadata."""
from alembic import op
from railsync.models import PriorityAssessment,ModelExperiment
revision='007';down_revision='006';branch_labels=depends_on=None
def upgrade():
    PriorityAssessment.__table__.create(op.get_bind());ModelExperiment.__table__.create(op.get_bind())
    op.execute("CREATE TRIGGER assessment_immutable BEFORE UPDATE OR DELETE ON priority_assessments FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():
    op.drop_table('model_experiments');op.drop_table('priority_assessments')
