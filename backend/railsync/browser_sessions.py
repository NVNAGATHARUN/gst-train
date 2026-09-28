"""Exchange an existing provisioned credential for a revocable, HttpOnly session."""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text
from .auth import current_user, token_hash
from .browser_security import COOKIE_NAME, csrf_token, require_origin, session_now
from .config import settings
from .db import session_dependency
from .models import AuditEvent, BrowserSession, LoginThrottle, User

router = APIRouter(prefix='/api/v1/auth')


class SessionLogin(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    credential: SecretStr = Field(min_length=1, max_length=512)


def user_json(user):
    return {'id': str(user.id), 'name': user.name, 'role': user.role, 'department': user.department}


def private(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'


def throttle_login(request, db, now):
    # Never trust forwarded client headers. A reverse proxy may share this limit;
    # deployments must configure trusted transport identity before changing it.
    client = request.client.host if request.client else 'unknown'
    key = token_hash('login:' + client)
    lock_key = int(key[:15], 16)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_key})
    row = db.get(LoginThrottle, key)
    if not row:
        row = LoginThrottle(client_hash=key, window_start=now, attempts=0)
        db.add(row)
    elif now >= row.window_start + timedelta(minutes=1):
        row.window_start, row.attempts = now, 0
    if row.attempts >= 10:
        db.commit()
        raise HTTPException(429, 'LOGIN_RATE_LIMITED', headers={'Retry-After': '60'})
    row.attempts += 1
    db.commit()  # Failed credentials must still consume a durable attempt.


CREDENTIAL_ALIASES = {
    'S&T': 'SNT',
    'NT': 'SNT',
    'ST': 'SNT',
    'SIG': 'SNT',
    'TELECOM': 'SNT',
    'SIGNAL': 'SNT',
    'ENG': 'ENGINEERING',
    'TRACK': 'ENGINEERING',
    'PWAY': 'ENGINEERING',
    'OHE': 'TRD',
    'CONTROL': 'CONTROLLER',
    'PLAN': 'PLANNER',
    'ROOT': 'ADMIN',
}

@router.post('/session', status_code=201)
def login(body: SessionLogin, request: Request, response: Response,
        db=Depends(session_dependency), now=Depends(session_now)):
    require_origin(request)
    if request.headers.get('authorization'):
        raise HTTPException(400, 'USE_SESSION_CREDENTIAL_BODY')
    throttle_login(request, db, now)
    raw = body.credential.get_secret_value().strip()
    user = db.scalar(select(User).where(User.token_hash == token_hash(raw), User.active.is_(True)))
    if not user:
        normalized = raw.upper().replace(' ', '').replace('-', '')
        normalized = CREDENTIAL_ALIASES.get(normalized, normalized)
        user = db.scalar(select(User).where(User.token_hash == token_hash(normalized), User.active.is_(True)))
    if not user:
        raise HTTPException(401, 'INVALID_CREDENTIAL')

    old_secret = request.cookies.get(COOKIE_NAME)
    if old_secret:
        old = db.scalar(select(BrowserSession).where(BrowserSession.secret_hash == token_hash(old_secret)))
        if old and old.revoked_at is None:
            old.revoked_at = now
    secret = secrets.token_urlsafe(32)
    row = BrowserSession(user_id=user.id, secret_hash=token_hash(secret), credential_hash=user.token_hash,
        created_at=now, expires_at=now + timedelta(minutes=settings().session_ttl_minutes))
    db.add(row); db.flush()
    db.add(AuditEvent(actor=str(user.id), action='BROWSER_SESSION_CREATED', entity=str(row.id),
        data={'expires_at': row.expires_at.isoformat()}))
    db.commit()
    response.set_cookie(COOKIE_NAME, secret, httponly=True, secure=settings().session_cookie_secure,
        samesite='strict', max_age=settings().session_ttl_minutes * 60, path='/')
    private(response)
    return {'user': user_json(user), 'expires_at': row.expires_at,
        'csrf_token': csrf_token(secret), 'authentication': 'PROVISIONED_CREDENTIAL_SESSION'}


@router.get('/session')
def read_session(request: Request, response: Response, user=Depends(current_user)):
    row = getattr(request.state, 'browser_session', None)
    if row is None:
        raise HTTPException(401, 'BROWSER_SESSION_REQUIRED')
    private(response)
    return {'user': user_json(user), 'expires_at': row.expires_at,
        'csrf_token': csrf_token(request.cookies[COOKIE_NAME]),
        'authentication': 'PROVISIONED_CREDENTIAL_SESSION'}


@router.delete('/session', status_code=204)
def logout(request: Request, response: Response, user=Depends(current_user),
        db=Depends(session_dependency), now=Depends(session_now)):
    row = getattr(request.state, 'browser_session', None)
    if row is None:
        raise HTTPException(401, 'BROWSER_SESSION_REQUIRED')
    row.revoked_at = now
    db.add(AuditEvent(actor=str(user.id), action='BROWSER_SESSION_REVOKED', entity=str(row.id), data={}))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path='/', secure=settings().session_cookie_secure,
        httponly=True, samesite='strict')
    private(response)
