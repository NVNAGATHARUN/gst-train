"""Server-side browser sessions and durable bounded login attempts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '024'
down_revision = '023'
branch_labels = depends_on = None


def upgrade():
    op.create_table('browser_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('secret_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('credential_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('expires_at > created_at', name='ck_browser_session_expiry'))
    op.create_index('ix_browser_sessions_user_id', 'browser_sessions', ['user_id'])
    op.create_table('login_throttles',
        sa.Column('client_hash', sa.String(64), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('login_throttles')
    op.drop_table('browser_sessions')
