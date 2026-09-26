import argparse,time,uuid,threading
from datetime import datetime,timezone
from .db import Session
from .models import WorkerHeartbeat
from .planning import run_one
from .planning_sessions import prepare_one

def beat(worker_id,started_at,stopped=False):
    now=datetime.now(timezone.utc)
    with Session.begin() as db:
        row=db.get(WorkerHeartbeat,worker_id)
        if row is None:
            row=WorkerHeartbeat(id=worker_id,started_at=started_at,last_seen_at=now)
            db.add(row)
        else:row.last_seen_at=now
        if stopped:row.stopped_at=now

def keep_beating(worker_id,started_at,stop):
    while not stop.wait(5):
        try:beat(worker_id,started_at)
        except Exception:
            # A failed write makes the heartbeat stale; it never reports false health.
            pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    worker_id=uuid.uuid4();started_at=datetime.now(timezone.utc)
    beat(worker_id,started_at)
    stop=threading.Event()
    monitor=threading.Thread(target=keep_beating,args=(worker_id,started_at,stop),daemon=True)
    if not args.once:monitor.start()
    try:
        while True:
            prepared=prepare_one()
            found=run_one()
            if args.once:return 0
            if not found and not prepared:time.sleep(1)
    finally:
        stop.set()
        if monitor.is_alive():monitor.join(timeout=2)
        try:beat(worker_id,started_at,stopped=True)
        except Exception:pass
if __name__=='__main__':raise SystemExit(main())
