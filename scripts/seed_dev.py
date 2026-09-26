import sys, pathlib, json
from datetime import datetime, timezone, timedelta
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests')]

from sqlalchemy import select
from railsync.db import Session, engine
from railsync.models import User, OperationalState, PlanReservation
from railsync.auth import token_hash
from railsync.network import save_entity, EntityInput
from railsync.main import app
from fastapi.testclient import TestClient
from test_m13 import prepare
from test_m12 import NOW

print("Connecting to database:", engine.url)

with Session.begin() as db:
    # Seed users if not existing
    for role, dept in [
        ('ADMIN', None),
        ('PLANNER', None),
        ('CONTROLLER', None),
        ('AUDITOR', None),
        ('DEPARTMENT', 'ENGINEERING'),
        ('DEPARTMENT', 'TRD'),
        ('DEPARTMENT', 'SNT'),
    ]:
        token = dept or role
        existing = db.scalar(select(User).where(User.token_hash == token_hash(token)))
        if not existing:
            db.add(User(name=token, role=role, department=dept, token_hash=token_hash(token), active=True))
    db.flush()

    admin = db.scalar(select(User).where(User.role == 'ADMIN'))
    for kind, eid, data in [
        ('station', 'A', {'name': 'A'}),
        ('station', 'B', {'name': 'B'}),
        ('section', 'SEC-AB', {'from_station': 'A', 'to_station': 'B', 'distance_km': 10}),
        ('track', 'AB', {'section_id': 'SEC-AB', 'electrified': True}),
        ('asset', 'AS-1', {'department': 'ENGINEERING', 'asset_type': 'TRACK', 'footprint': ['AB']}),
    ]:
        try:
            save_entity(db, kind, EntityInput(id=eid, data=data), admin)
        except Exception as e:
            print(f"Entity {kind} {eid} note:", e)

print("Users and network entities ready.")

with TestClient(app) as client:
    manifest, revision, report = prepare(client)
    print(f"Seeded snapshot: {revision['snapshot_id']}")
    print(f"Seeded plan revision: {revision['id']} (solver_status: {revision['content']['solver_status']})")
    print(f"Validation report: {report['status']}")
    
    # Materialize explanations
    exp_resp = client.post(f"/api/v1/plan-revisions/{revision['id']}/explanations", headers={"Authorization": "Bearer PLANNER"}, json={})
    print("Explanations status:", exp_resp.status_code)

print("Prototype database seeding complete!")
