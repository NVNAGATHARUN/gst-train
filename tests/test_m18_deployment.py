from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

from pydantic import ValidationError
import pytest

from railsync.config import Settings
from railsync.worker import beat
from railsync.worker_health import healthy

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_production_browser_configuration_requires_https_and_secure_cookie():
    valid = Settings(_env_file=None, environment='production', session_cookie_secure=True,
        browser_origins=['https://railsync.example'])
    assert valid.session_cookie_secure is True
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='production', session_cookie_secure=False,
            browser_origins=['https://railsync.example'])
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment='production', session_cookie_secure=True,
            browser_origins=['http://railsync.example'])


def test_worker_container_probe_uses_persisted_recent_heartbeat():
    worker_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    assert healthy(now) is False
    beat(worker_id, now)
    assert healthy(now + timedelta(seconds=14)) is True
    assert healthy(now + timedelta(seconds=16)) is False


def test_compose_declares_complete_isolated_stack_and_gates_startup():
    compose = source('compose.yaml')
    for service in ('db:', 'migration:', 'api:', 'worker:', 'web:', 'restore-db:'):
        assert service in compose
    assert 'condition: service_completed_successfully' in compose
    assert 'condition: service_healthy' in compose
    assert 'RAILSYNC_BROWSER_ORIGINS: ${RAILSYNC_BROWSER_ORIGINS:?' in compose
    assert 'RAILSYNC_SESSION_COOKIE_SECURE: ${RAILSYNC_SESSION_COOKIE_SECURE:-true}' in compose
    assert 'internal: true' in compose
    db_block = compose.split('  db:', 1)[1].split('  migration:', 1)[0]
    assert 'ports:' not in db_block
    assert 'profiles: [recovery]' in compose
    assert 'railsync_restore_pg:' in compose


def test_images_are_pinned_non_root_and_build_from_locks():
    backend = source('Dockerfile')
    frontend = source('web/Dockerfile')
    assert 'python:3.12.11-slim-bookworm' in backend
    assert 'uv sync --frozen --no-dev' in backend
    assert 'USER railsync' in backend
    assert 'node:22.19.0-alpine3.22' in frontend
    assert 'RUN npm ci' in frontend
    assert 'USER railsync' in frontend
    assert 'output: "standalone"' in source('web/next.config.ts')


def test_backup_and_restore_are_checksum_bound_and_restore_is_isolated():
    backup = source('scripts/backup.ps1')
    restore = source('scripts/restore_verify.ps1')
    assert 'pg_dump' in backup and 'Get-FileHash' in backup and '.sha256' in backup
    assert 'SHA256 mismatch; restore refused' in restore
    assert '--profile recovery' in restore and 'restore-db' in restore
    assert 'Restore target is not empty; refusing to overwrite it' in restore
    assert 'pg_restore' in restore and 'alembic_version' in restore
    assert '--clean' not in restore and 'railsync_pg' not in restore
