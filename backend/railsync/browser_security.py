"""Browser-only session security. Does not grant application roles or railway authority."""
import hashlib
import hmac
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from sqlalchemy import select
from .config import settings
from .models import BrowserSession, User

COOKIE_NAME = 'railsync_session'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}


def session_now():
    return datetime.now(timezone.utc)


def hash_secret(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(secret):
    return hmac.new(secret.encode(), b'railsync-browser-csrf-v1', hashlib.sha256).hexdigest()


def require_origin(request: Request):
    if request.headers.get('origin') not in settings().browser_origins:
        raise HTTPException(403, 'BROWSER_ORIGIN_FORBIDDEN')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'CROSS_SITE_REQUEST_FORBIDDEN')


def browser_identity(request: Request, db, now):
    secret = request.cookies.get(COOKIE_NAME)
    if not secret or len(secret) > 128:
        raise HTTPException(401, 'SESSION_REQUIRED')
    row = db.scalar(select(BrowserSession).where(BrowserSession.secret_hash == hash_secret(secret)))
    if not row or row.revoked_at is not None or now >= row.expires_at:
        raise HTTPException(401, 'SESSION_EXPIRED_OR_REVOKED')
    user = db.get(User, row.user_id)
    if not user or not user.active or not hmac.compare_digest(row.credential_hash, user.token_hash):
        raise HTTPException(401, 'SESSION_EXPIRED_OR_REVOKED')
    if request.method not in SAFE_METHODS:
        require_origin(request)
        supplied = request.headers.get('x-csrf-token', '')
        if not hmac.compare_digest(supplied.encode(), csrf_token(secret).encode()):
            raise HTTPException(403, 'CSRF_TOKEN_INVALID')
    request.state.browser_session = row
    return user
