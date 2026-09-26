"""Foundation tables; immutable audit log."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = "001"
down_revision = None
branch_labels = depends_on = None
def upgrade():
    op.create_table("users",sa.Column("id",pg.UUID(),primary_key=True),sa.Column("name",sa.String(100),nullable=False),sa.Column("role",sa.String(24),nullable=False),sa.Column("department",sa.String(24)),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("active",sa.Boolean(),nullable=False))
    op.create_table("audit_events",sa.Column("id",pg.UUID(),primary_key=True),sa.Column("actor",sa.String(100),nullable=False),sa.Column("action",sa.String(100),nullable=False),sa.Column("entity",sa.String(100),nullable=False),sa.Column("data",pg.JSONB(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.execute("CREATE FUNCTION deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'IMMUTABLE_RECORD'; END $$")
    op.execute("CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION deny_mutation()")
def downgrade():
    op.drop_table("audit_events")
    op.drop_table("users")
    op.execute("DROP FUNCTION deny_mutation()")
