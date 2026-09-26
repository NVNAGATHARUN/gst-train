"""Immutable planning snapshots and materialized source facts."""
from alembic import op
from railsync.models import PlanningSnapshot,SnapshotItem
revision='005';down_revision='004';branch_labels=depends_on=None
def upgrade():
    for table in [PlanningSnapshot.__table__,SnapshotItem.__table__]:table.create(op.get_bind())
    op.execute("CREATE TRIGGER snapshot_immutable BEFORE UPDATE OR DELETE ON planning_snapshots FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
    op.execute("CREATE TRIGGER snapshot_item_immutable BEFORE UPDATE OR DELETE ON snapshot_items FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():
    op.drop_table('snapshot_items');op.drop_table('planning_snapshots')
