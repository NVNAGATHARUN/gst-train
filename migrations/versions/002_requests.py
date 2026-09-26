"""Maintenance request revisions and source import lineage."""
from alembic import op
from railsync.models import MaintenanceRequest, RequestRevision, ImportBatch, SourceRecord
revision='002'
down_revision='001'
branch_labels=depends_on=None
def upgrade():
    for table in [MaintenanceRequest.__table__,RequestRevision.__table__,ImportBatch.__table__,SourceRecord.__table__]:table.create(op.get_bind())
    op.execute("CREATE TRIGGER request_revision_immutable BEFORE UPDATE OR DELETE ON request_revisions FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():
    for name in ['source_records','import_batches','request_revisions','maintenance_requests']:op.drop_table(name)
