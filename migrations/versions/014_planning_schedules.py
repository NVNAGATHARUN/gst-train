"""M14 immutable weekly/monthly schedule artifacts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='014'
down_revision='013'
branch_labels=depends_on=None

def upgrade():
    op.create_table('planning_schedules',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('schedule_type',sa.String(16),nullable=False),sa.Column('timezone_name',sa.String(80),nullable=False),
        sa.Column('period_start',sa.DateTime(timezone=True),nullable=False),sa.Column('period_end',sa.DateTime(timezone=True),nullable=False),
        sa.Column('content_hash',sa.String(64),nullable=False,unique=True),sa.Column('content',JSONB(),nullable=False),
        sa.Column('created_by',sa.String(100),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.execute('CREATE TRIGGER planning_schedules_immutable BEFORE UPDATE OR DELETE ON planning_schedules FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():op.drop_table('planning_schedules')
