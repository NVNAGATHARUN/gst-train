from sqlalchemy import text
from railsync.db import engine
from conftest import auth
import pytest
from sqlalchemy.exc import DBAPIError
from railsync.db import Session
from railsync.models import AuditEvent

def test_real_postgres_and_readiness(client):
    with engine.connect() as c: assert "PostgreSQL" in c.scalar(text("SELECT version()"))
    assert client.get('/api/v1/health').json()['railway_control'] is False
    assert client.get('/api/v1/ready').json()=={'status':'ready','database':'postgresql'}

def test_auth_is_enforced(client):
    assert client.get('/api/v1/me').status_code==401
    assert client.get('/api/v1/me',headers=auth('bad')).status_code==401
    assert client.get('/api/v1/me',headers=auth('ENGINEERING')).json()['department']=='ENGINEERING'
    assert client.get('/api/v1/admin/check',headers=auth()).status_code==403
    assert client.get('/api/v1/admin/check',headers=auth('ADMIN')).status_code==200

def test_audit_is_append_only():
    with Session.begin() as db: db.add(AuditEvent(actor='test',action='created',entity='foundation',data={'verified':True}))
    with pytest.raises(DBAPIError,match='IMMUTABLE_RECORD'):
        with engine.begin() as c:c.execute(text("UPDATE audit_events SET action='altered'"))
    with engine.connect() as c:assert c.scalar(text("SELECT action FROM audit_events WHERE actor='test'"))=='created'
