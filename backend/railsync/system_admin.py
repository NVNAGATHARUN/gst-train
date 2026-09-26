"""Read-only administrative health with an observed worker heartbeat."""
from datetime import datetime,timedelta,timezone
from fastapi import APIRouter,Depends,Request
from sqlalchemy import func,select,text
from .auth import require
from .db import session_dependency
from .models import BrowserSession,PlanningRun,PlanningSession,User,WorkerHeartbeat

router=APIRouter(prefix='/api/v1')
HEARTBEAT_MAX_AGE_SECONDS=15

@router.get('/admin/system')
def system_status(request:Request,user=Depends(require('ADMIN')),db=Depends(session_dependency)):
    now=datetime.now(timezone.utc)
    migration=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
    workers=db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.stopped_at.is_(None))
        .order_by(WorkerHeartbeat.last_seen_at.desc())).all()
    responsive=[row for row in workers if row.last_seen_at>=now-timedelta(seconds=HEARTBEAT_MAX_AGE_SECONDS)]
    latest=workers[0] if workers else None
    worker_status='RESPONSIVE' if responsive else 'STALE' if latest else 'ABSENT'
    queue={
        'preparation':db.scalar(select(func.count()).select_from(PlanningSession).where(
            PlanningSession.status=='QUEUED_PREPARATION')),
        'queued_runs':db.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.status=='QUEUED')),
        'running_runs':db.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.status=='RUNNING')),
    }
    users=db.scalars(select(User).order_by(User.role,User.department,User.name,User.id)).all()
    session=getattr(request.state,'browser_session',None)
    return {
        'status':'READY' if responsive else 'DEGRADED',
        'checked_at':now.isoformat(),
        'api':{'status':'RESPONSIVE'},
        'database':{'status':'READY','engine':'PostgreSQL','migration_revision':migration},
        'worker':{'status':worker_status,'responsive_instances':len(responsive),
                  'last_seen_at':latest.last_seen_at.isoformat() if latest else None,
                  'max_age_seconds':HEARTBEAT_MAX_AGE_SECONDS},
        'queue':queue,
        'access':{'users':[{'id':str(row.id),'name':row.name,'role':row.role,
                            'department':row.department,'active':row.active} for row in users],
                  'provisioning':'EXTERNAL_TO_THIS_UI'},
        'session':{'kind':'BROWSER_SESSION' if isinstance(session,BrowserSession) else 'BEARER',
                   'expires_at':session.expires_at.isoformat() if isinstance(session,BrowserSession) else None,
                   'user_id':str(user.id)},
        'railway_control':False,
    }
