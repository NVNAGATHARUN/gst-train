"""Versioned network graph and typed relational links."""
from alembic import op
from railsync.models import NetworkEntity,NetworkRevision,NetworkLink
revision='003'
down_revision='002'
branch_labels=depends_on=None
def upgrade():
    for table in [NetworkEntity.__table__,NetworkRevision.__table__,NetworkLink.__table__]:table.create(op.get_bind())
    op.execute("CREATE TRIGGER network_revision_immutable BEFORE UPDATE OR DELETE ON network_revisions FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():
    for name in ['network_links','network_revisions','network_entities']:op.drop_table(name)
