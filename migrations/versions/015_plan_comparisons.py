"""M15 immutable fair plan comparisons."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='015'
down_revision='014'
branch_labels=depends_on=None
def upgrade():
    op.create_table('plan_comparisons',sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('baseline_plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('railsync_plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False,unique=True),sa.Column('content',JSONB(),nullable=False),
        sa.Column('created_by',sa.String(100),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER plan_comparisons_immutable BEFORE UPDATE OR DELETE ON plan_comparisons FOR EACH ROW EXECUTE FUNCTION deny_mutation()')
def downgrade():op.drop_table('plan_comparisons')
