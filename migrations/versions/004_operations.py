"""Dated train occupancy, COA windows and freight uncertainty."""
from alembic import op
from railsync.models import Train,TrainRun,TrainOccupancy,CoaWindow,FreightForecast
revision='004';down_revision='003';branch_labels=depends_on=None
def upgrade():
    for table in [Train.__table__,TrainRun.__table__,TrainOccupancy.__table__,CoaWindow.__table__,FreightForecast.__table__]:table.create(op.get_bind())
def downgrade():
    for name in ['freight_forecasts','coa_windows','train_occupancies','train_runs','trains']:op.drop_table(name)
