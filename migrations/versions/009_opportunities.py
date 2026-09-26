"""Persisted maintenance opportunity generation."""
from alembic import op
from railsync.models import OpportunityComputation
revision='009';down_revision='008';branch_labels=depends_on=None
def upgrade():
    OpportunityComputation.__table__.create(op.get_bind())
    op.execute("CREATE TRIGGER opportunity_immutable BEFORE UPDATE OR DELETE ON opportunity_computations FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():op.drop_table('opportunity_computations')
