"""M13 immutable plan revisions, explanations and controller decisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID,JSONB
revision='013'
down_revision='012'
branch_labels=depends_on=None

def upgrade():
    op.create_table('plan_revisions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('lineage_id',UUID(as_uuid=True),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('run_id',UUID(as_uuid=True),sa.ForeignKey('planning_runs.id'),nullable=False),
        sa.Column('snapshot_id',UUID(as_uuid=True),sa.ForeignKey('planning_snapshots.id'),nullable=False),
        sa.Column('parent_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=True),
        sa.Column('plan_hash',sa.String(64),nullable=False),
        sa.Column('snapshot_hash',sa.String(64),nullable=False),
        sa.Column('edit',JSONB(),nullable=False),sa.Column('content',JSONB(),nullable=False),
        sa.Column('created_by',sa.String(100),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('lineage_id','revision'),sa.UniqueConstraint('run_id','revision'))
    op.create_table('decision_explanations',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),
        sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('request_id',sa.String(100),nullable=False),sa.Column('outcome',sa.String(24),nullable=False),
        sa.Column('payload',JSONB(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('plan_revision_id','request_id'))
    op.create_table('operational_states',sa.Column('scope',sa.String(16),primary_key=True),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.execute("INSERT INTO operational_states(scope,revision,updated_at) VALUES ('SIMULATED',0,now()),('OPERATIONAL',0,now())")
    op.create_table('controller_decisions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),sa.Column('idempotency_key',UUID(as_uuid=True),nullable=False,unique=True),
        sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('validation_report_id',UUID(as_uuid=True),sa.ForeignKey('validation_reports.id'),nullable=True),
        sa.Column('action',sa.String(24),nullable=False),sa.Column('scope',sa.String(16),nullable=False),
        sa.Column('expected_operational_revision',sa.Integer(),nullable=False),sa.Column('resulting_operational_revision',sa.Integer(),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),sa.Column('actor',sa.String(100),nullable=False),
        sa.Column('result',JSONB(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('plan_reservations',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),sa.Column('plan_revision_id',UUID(as_uuid=True),sa.ForeignKey('plan_revisions.id'),nullable=False),
        sa.Column('decision_id',UUID(as_uuid=True),sa.ForeignKey('controller_decisions.id'),nullable=False),
        sa.Column('scope',sa.String(16),nullable=False),sa.Column('track_ids',JSONB(),nullable=False),sa.Column('resource_ids',JSONB(),nullable=False),
        sa.Column('start_at',sa.DateTime(timezone=True),nullable=False),sa.Column('end_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('active',sa.Boolean(),nullable=False))
    op.add_column('validation_reports',sa.Column('plan_revision_id',UUID(as_uuid=True),nullable=True))
    op.create_foreign_key('fk_validation_plan_revision','validation_reports','plan_revisions',['plan_revision_id'],['id'])
    for table in ['plan_revisions','decision_explanations','controller_decisions']:
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION deny_mutation()')

def downgrade():
    op.drop_constraint('fk_validation_plan_revision','validation_reports',type_='foreignkey')
    op.drop_column('validation_reports','plan_revision_id')
    for table in ['plan_reservations','controller_decisions','operational_states','decision_explanations','plan_revisions']:
        op.drop_table(table)
