"""Durable, idempotent orchestration requests binding a pair of real planner runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '025'
down_revision = '024'
branch_labels = depends_on = None


def upgrade():
    op.create_table('planning_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('idempotency_key', UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('snapshot_id', UUID(as_uuid=True), sa.ForeignKey('planning_snapshots.id'), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('artifacts', JSONB(), nullable=False),
        sa.Column('error', JSONB(), nullable=True),
        sa.Column('baseline_run_id', UUID(as_uuid=True), sa.ForeignKey('planning_runs.id'), nullable=True),
        sa.Column('optimized_run_id', UUID(as_uuid=True), sa.ForeignKey('planning_runs.id'), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prepared_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_planning_sessions_status_created', 'planning_sessions', ['status', 'created_at'])
    op.execute('''CREATE FUNCTION protect_planning_session_request() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'IMMUTABLE_SESSION_REQUEST'; END IF;
      IF NEW.id IS DISTINCT FROM OLD.id OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
        OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id OR NEW.request_hash IS DISTINCT FROM OLD.request_hash
        OR NEW.payload IS DISTINCT FROM OLD.payload OR NEW.created_by IS DISTINCT FROM OLD.created_by
        OR NEW.created_at IS DISTINCT FROM OLD.created_at OR OLD.status <> 'QUEUED_PREPARATION'
      THEN RAISE EXCEPTION 'IMMUTABLE_SESSION_REQUEST'; END IF;
      RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER planning_session_request_immutable BEFORE UPDATE OR DELETE ON planning_sessions '
        'FOR EACH ROW EXECUTE FUNCTION protect_planning_session_request()')


def downgrade():
    op.drop_table('planning_sessions')
    op.execute('DROP FUNCTION protect_planning_session_request()')
