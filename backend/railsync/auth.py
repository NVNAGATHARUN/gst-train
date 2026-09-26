import hashlib
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from .db import session_dependency
from .models import User
from .browser_security import COOKIE_NAME, browser_identity, session_now

bearer = HTTPBearer(auto_error=False)

def token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        db=Depends(session_dependency), now=Depends(session_now)):
    if COOKIE_NAME in request.cookies:
        if request.headers.get('authorization'):
            raise HTTPException(400, 'AMBIGUOUS_AUTHENTICATION')
        return browser_identity(request, db, now)
    if not credentials:
        raise HTTPException(401, "AUTH_REQUIRED")
    user = db.scalar(select(User).where(User.token_hash == token_hash(credentials.credentials), User.active.is_(True)))
    if not user:
        raise HTTPException(401, "INVALID_TOKEN")
    return user

def require(*roles):
    def dependency(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "ROLE_FORBIDDEN")
        return user
    return dependency
