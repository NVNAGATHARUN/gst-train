"""Persisted corridor availability computations."""
from alembic import op
from railsync.models import AvailabilityComputation
revision='008';down_revision='007';branch_labels=depends_on=None
def upgrade():
    AvailabilityComputation.__table__.create(op.get_bind())
    op.execute("CREATE TRIGGER availability_immutable BEFORE UPDATE OR DELETE ON availability_computations FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():op.drop_table('availability_computations')
