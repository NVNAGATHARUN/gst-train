import uuid
from datetime import datetime,timedelta,timezone
from conftest import auth
from railsync.db import Session
from railsync.models import WorkerHeartbeat
from railsync.worker import beat
from fastapi.testclient import TestClient
from railsync.main import app

ORIGIN = 'https://localhost:3000'


def test_admin_system_reports_absent_responsive_and_stale_worker(client):
    assert client.get('/api/v1/admin/system',headers=auth('PLANNER')).status_code==403
    absent=client.get('/api/v1/admin/system',headers=auth('ADMIN'))
    assert absent.status_code==200
    first=absent.json()
    assert first['status']=='DEGRADED'
    assert first['api']['status']=='RESPONSIVE'
    assert first['database']['status']=='READY'
    assert first['database']['migration_revision']=='026'
    assert first['worker']['status']=='ABSENT'
    assert first['queue']=={'preparation':0,'queued_runs':0,'running_runs':0}
    assert len(first['access']['users'])==6
    assert all('token_hash' not in row and 'credential' not in row for row in first['access']['users'])

    worker_id=uuid.uuid4();started=datetime.now(timezone.utc)
    beat(worker_id,started)
    responsive=client.get('/api/v1/admin/system',headers=auth('ADMIN')).json()
    assert responsive['status']=='READY'
    assert responsive['worker']['status']=='RESPONSIVE'
    assert responsive['worker']['responsive_instances']==1

    with Session.begin() as db:
        db.get(WorkerHeartbeat,worker_id).last_seen_at=started-timedelta(minutes=1)
    stale=client.get('/api/v1/admin/system',headers=auth('ADMIN')).json()
    assert stale['status']=='DEGRADED'
    assert stale['worker']['status']=='STALE'
    assert stale['worker']['responsive_instances']==0


def test_stopped_worker_is_not_reported_responsive(client):
    worker_id=uuid.uuid4();started=datetime.now(timezone.utc)
    beat(worker_id,started,stopped=True)
    result=client.get('/api/v1/admin/system',headers=auth('ADMIN')).json()
    assert result['worker']['status']=='ABSENT'
    assert result['status']=='DEGRADED'


def test_system_health_uses_browser_session_and_keeps_credentials_out():
    with TestClient(app, base_url=ORIGIN) as browser:
        signed_in = browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
            json={'credential': 'ADMIN'})
        assert signed_in.status_code == 201
        status = browser.get('/api/v1/admin/system')
        assert status.status_code == 200
        data = status.json()
        assert data['session']['kind'] == 'BROWSER_SESSION'
        assert data['session']['expires_at'] is not None
        assert data['access']['provisioning'] == 'EXTERNAL_TO_THIS_UI'
        assert 'token_hash' not in str(data)
        assert 'csrf_token' not in str(data)
