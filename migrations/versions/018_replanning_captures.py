"""Immutable M16 operational/execution capture, bound to an approved revision."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB

revision='018'
down_revision='017'
branch_labels=depends_on=None


def upgrade():
    op.create_table('replanning_captures',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('payload',JSONB(),nullable=False),sa.Column('created_by',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER replanning_captures_immutable BEFORE UPDATE OR DELETE ON replanning_captures FOR EACH ROW EXECUTE FUNCTION deny_mutation()')


def downgrade():
    op.drop_table('replanning_captures')
