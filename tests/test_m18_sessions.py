"""Real PostgreSQL session, CSRF, role and credential-lifecycle boundaries."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from railsync.auth import token_hash
from railsync.browser_security import COOKIE_NAME, session_now
from railsync.config import Settings, settings
from railsync.db import Session
from railsync.main import app
from railsync.models import AuditEvent, BrowserSession, User

ORIGIN = 'https://localhost:3000'
NOW = datetime(2026, 9, 23, 6, tzinfo=timezone.utc)


@pytest.fixture
def browser():
    app.dependency_overrides[session_now] = lambda: NOW
    with TestClient(app, base_url=ORIGIN) as client:
        yield client
    app.dependency_overrides.clear()


def login(browser, credential='PLANNER'):
    response = browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
        json={'credential': credential})
    assert response.status_code == 201, response.text
    return response


def write_headers(response):
    return {'Origin': ORIGIN, 'X-CSRF-Token': response.json()['csrf_token']}


def station(browser, headers):
    return browser.post('/api/v1/network/station', headers=headers,
        json={'id': 'M18-C', 'data': {'name': 'C'}})


def test_browser_session_cookie_hashed_storage_csrf_rbac_and_logout(browser):
    created = login(browser)
    raw_cookie = browser.cookies.get(COOKIE_NAME)
    cookie_header = created.headers['set-cookie']
    for flag in ('HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'):
        assert flag in cookie_header
    assert 'Domain=' not in cookie_header
    assert created.headers['cache-control'] == 'no-store'
    assert created.json()['user']['role'] == 'PLANNER'
    assert 'credential' not in created.json()
    with Session() as db:
        saved = db.scalar(select(BrowserSession))
        assert saved.secret_hash == token_hash(raw_cookie)
        assert saved.secret_hash != raw_cookie
        assert saved.expires_at == NOW + timedelta(minutes=settings().session_ttl_minutes)
        assert raw_cookie not in str(db.scalars(select(AuditEvent.data)).all())
    me = browser.get('/api/v1/me')
    assert me.status_code == 200 and me.json()['role'] == 'PLANNER'
    read = browser.get('/api/v1/auth/session')
    assert read.json()['csrf_token'] == created.json()['csrf_token']
    role_denied = browser.get('/api/v1/admin/check')
    assert role_denied.status_code == 403
    missing_csrf = station(browser, {'Origin': ORIGIN})
    assert missing_csrf.status_code == 403 and missing_csrf.json()['detail'] == 'CSRF_TOKEN_INVALID'
    write = station(browser, write_headers(created))
    assert write.status_code == 201
    signed_out = browser.delete('/api/v1/auth/session', headers=write_headers(created))
    assert signed_out.status_code == 204 and 'Max-Age=0' in signed_out.headers['set-cookie']
    browser.cookies.set(COOKIE_NAME, raw_cookie)
    assert browser.get('/api/v1/me').status_code == 401
    if output := os.environ.get('RAILSYNC_M18_SESSION_EVIDENCE_OUTPUT'):
        Path(output).write_text(json.dumps({
            'scope': 'SIMULATED test identity; no railway authority',
            'user': me.json(), 'session_flags': ['HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'],
            'plaintext_session_stored': False, 'cache_control': created.headers['cache-control'],
            'role_denial': role_denied.json(), 'csrf_denial': missing_csrf.json(),
            'persisted_station': write.json(), 'logout_status': signed_out.status_code,
            'revoked_session_read_status': 401}, indent=2), encoding='utf-8')


@pytest.mark.parametrize('headers', [
    {}, {'Origin': 'https://evil.example'}, {'Origin': 'null'},
    {'Origin': ORIGIN + '.evil.example'}, {'Origin': ORIGIN, 'Sec-Fetch-Site': 'cross-site'}])
def test_login_requires_exact_trusted_origin(browser, headers):
    response = browser.post('/api/v1/auth/session', headers=headers, json={'credential': 'PLANNER'})
    assert response.status_code == 403
    with Session() as db:
        assert not db.scalars(select(BrowserSession)).all()


@pytest.mark.parametrize('mutation', ['missing_origin', 'wrong_origin', 'wrong_csrf', 'cross_site'])
def test_cookie_writes_reject_csrf_even_with_authenticated_session(browser, mutation):
    result = login(browser)
    headers = write_headers(result)
    if mutation == 'missing_origin': headers.pop('Origin')
    if mutation == 'wrong_origin': headers['Origin'] = 'https://evil.example'
    if mutation == 'wrong_csrf': headers['X-CSRF-Token'] = 'wrong'
    if mutation == 'cross_site': headers['Sec-Fetch-Site'] = 'cross-site'
    assert station(browser, headers).status_code == 403


def test_sessions_expire_exactly_and_credentials_or_users_revoke_them(browser):
    created = login(browser)
    app.dependency_overrides[session_now] = lambda: NOW + timedelta(minutes=settings().session_ttl_minutes)
    assert browser.get('/api/v1/me').status_code == 401
    app.dependency_overrides[session_now] = lambda: NOW
    assert browser.get('/api/v1/me').status_code == 200
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == 'PLANNER'))
        user.token_hash = token_hash('rotated')
    assert browser.get('/api/v1/me').status_code == 401
    login(browser, 'rotated')
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == 'PLANNER'))
        user.active = False
    assert browser.get('/api/v1/me').status_code == 401
    assert browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
        json={'credential': 'rotated'}).status_code == 401


def test_login_rotates_session_and_no_cookie_bearer_ambiguity(browser):
    login(browser)
    original = browser.cookies.get(COOKIE_NAME)
    login(browser, 'CONTROLLER')
    assert browser.cookies.get(COOKIE_NAME) != original
    assert browser.get('/api/v1/me').json()['role'] == 'CONTROLLER'
    assert browser.get('/api/v1/me', headers={'Authorization': 'Bearer ADMIN'}).status_code == 400
    browser.cookies.clear()
    browser.cookies.set(COOKIE_NAME, original)
    assert browser.get('/api/v1/me').status_code == 401
    browser.cookies.clear()
    assert browser.get('/api/v1/me', headers={'Authorization': 'Bearer ADMIN'}).status_code == 200


def test_login_failure_is_durable_rate_limited_and_does_not_echo_secrets(browser):
    for _ in range(10):
        response = browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
            json={'credential': 'incorrect-sensitive-value'})
        assert response.status_code == 401 and 'sensitive' not in response.text
    limited = browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
        json={'credential': 'PLANNER'})
    assert limited.status_code == 429 and limited.headers['retry-after'] == '60'
    app.dependency_overrides[session_now] = lambda: NOW + timedelta(minutes=1)
    assert login(browser).status_code == 201
    invalid = browser.post('/api/v1/auth/session', headers={'Origin': ORIGIN},
        json={'credential': 's' * 513, 'unexpected': 'private-value'})
    assert invalid.status_code == 422
    assert 's' * 513 not in invalid.text and 'private-value' not in invalid.text
    assert all('input' not in error for error in invalid.json()['detail'])


@pytest.mark.parametrize('values', [
    {'environment': 'production', 'session_cookie_secure': False},
    {'browser_origins': ['https://localhost:3000/']},
    {'browser_origins': ['https://localhost:3000?x=1']},
    {'browser_origins': ['*']},
    {'browser_origins': []},
    {'browser_origins': ['http://localhost:3000']},
    {'browser_origins': ['http://example.com'], 'session_cookie_secure': False},
])
def test_unsafe_browser_configuration_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_explicit_loopback_development_and_secure_production_settings():
    assert Settings(_env_file=None, environment='development', session_cookie_secure=False,
        browser_origins=['http://localhost:3000']).session_cookie_secure is False
    assert Settings(_env_file=None, environment='production',
        browser_origins=['https://railsync.example']).session_cookie_secure is True
