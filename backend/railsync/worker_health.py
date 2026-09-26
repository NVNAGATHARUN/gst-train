"""Container health probe for the durable planning worker."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from .db import Session
from .models import WorkerHeartbeat

MAX_AGE_SECONDS = 15


def healthy(now=None):
    now = now or datetime.now(timezone.utc)
    with Session() as db:
        latest = db.scalars(select(WorkerHeartbeat).where(
            WorkerHeartbeat.stopped_at.is_(None)).order_by(
            WorkerHeartbeat.last_seen_at.desc()).limit(1)).first()
        return bool(latest and latest.last_seen_at >= now - timedelta(seconds=MAX_AGE_SECONDS))


if __name__ == "__main__":
    raise SystemExit(0 if healthy() else 1)
