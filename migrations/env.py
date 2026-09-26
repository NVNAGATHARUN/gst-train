from alembic import context
from sqlalchemy import create_engine
from railsync.config import settings
from railsync.db import Base
from railsync import models

with create_engine(settings().database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
