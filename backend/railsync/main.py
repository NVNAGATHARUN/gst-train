from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from sqlalchemy import text
from .db import session_dependency
from .auth import current_user, require

app = FastAPI(title="RailSync AI", version="0.1.0", description="SIMULATED/IMPORTED decision support. No railway control.")
from .browser_sessions import router as browser_session_router
app.include_router(browser_session_router)

@app.exception_handler(RequestValidationError)
async def validation_errors(request, exc):
    if request.url.path == '/api/v1/auth/session':
        # Never echo a submitted credential, including invalid input or extra keys.
        return JSONResponse(status_code=422, content={'detail': [
            {'type': error['type'], 'loc': error['loc'], 'msg': error['msg']}
            for error in exc.errors()]})
    return await request_validation_exception_handler(request, exc)

@app.middleware('http')
async def private_api_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
    return response
from .requests import router as request_router
app.include_router(request_router)
from .network import router as network_router
app.include_router(network_router)
from .operations import router as operations_router
app.include_router(operations_router)
from .snapshots import router as snapshot_router
app.include_router(snapshot_router)
from .planning import router as planning_router
app.include_router(planning_router)
from .priority import router as priority_router
app.include_router(priority_router)
from .availability import router as availability_router
app.include_router(availability_router)
from .opportunities import router as opportunity_router
app.include_router(opportunity_router)
from .coordination import router as coordination_router
app.include_router(coordination_router)
from .validation import router as validation_router
app.include_router(validation_router)
from .decision_support import router as decision_support_router
app.include_router(decision_support_router)
from .schedules import router as schedules_router
app.include_router(schedules_router)
from .evaluation import router as evaluation_router
app.include_router(evaluation_router)
from .disruptions import router as disruption_router
app.include_router(disruption_router)
from .execution import router as execution_router
app.include_router(execution_router)
from .replanning import router as replanning_router
app.include_router(replanning_router)
from .restoration import router as restoration_router
app.include_router(restoration_router)
from .rolling_replans import router as rolling_replans_router
app.include_router(rolling_replans_router)
from .what_if import router as what_if_router
app.include_router(what_if_router)
from .workspace import router as workspace_router
app.include_router(workspace_router)
from .planning_sessions import router as planning_session_router
app.include_router(planning_session_router)
from .system_admin import router as system_admin_router
app.include_router(system_admin_router)

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "railsync", "railway_control": False}

@app.get("/api/v1/ready")
def ready(db=Depends(session_dependency)):
    try:
        db.execute(text("SELECT 1 FROM alembic_version"))
    except Exception:
        raise HTTPException(503, "DATABASE_NOT_READY")
    return {"status": "ready", "database": "postgresql"}

@app.get("/api/v1/me")
def me(user=Depends(current_user)):
    return {"id": str(user.id), "name": user.name, "role": user.role, "department": user.department}

@app.get("/api/v1/admin/check")
def admin_check(user=Depends(require("ADMIN"))):
    return {"authorized": True}
