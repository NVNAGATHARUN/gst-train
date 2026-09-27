import sys, pathlib
from sqlalchemy import select

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend')]

from railsync.db import Session, engine
from railsync.models import User
from railsync.auth import token_hash
from railsync.network import save_entity, EntityInput

def seed():
    print(f"Connecting to database: {engine.url.render_as_string(hide_password=True)}")
    
    with Session.begin() as db:
        users = [
            ('ADMIN', None),
            ('PLANNER', None),
            ('CONTROLLER', None),
            ('AUDITOR', None),
            ('DEPARTMENT', 'ENGINEERING'),
            ('DEPARTMENT', 'TRD'),
            ('DEPARTMENT', 'SNT'),
        ]
        
        for role, dept in users:
            token = dept or role
            existing = db.scalar(select(User).where(User.token_hash == token_hash(token)))
            if not existing:
                db.add(User(name=token, role=role, department=dept, token_hash=token_hash(token), active=True))
                print(f"Provisioned user: {token} (role: {role})")
            else:
                print(f"User already exists: {token}")
        db.flush()

        admin = db.scalar(select(User).where(User.role == 'ADMIN'))
        
        # Core stations and track corridor: Ghaziabad to Aligarh
        entities = [
            ('station', 'GZB', {'name': 'Ghaziabad Junction'}),
            ('station', 'DER', {'name': 'Dadri'}),
            ('station', 'KRJ', {'name': 'Khurja Junction'}),
            ('station', 'ALJN', {'name': 'Aligarh Junction'}),
            ('section', 'SEC-GZB-DER', {'from_station': 'GZB', 'to_station': 'DER', 'distance_km': 19.5}),
            ('section', 'SEC-DER-KRJ', {'from_station': 'DER', 'to_station': 'KRJ', 'distance_km': 42.0}),
            ('section', 'SEC-KRJ-ALJN', {'from_station': 'KRJ', 'to_station': 'ALJN', 'distance_km': 21.0}),
            ('track', 'GZB-DER-UP', {'section_id': 'SEC-GZB-DER', 'direction': 'UP', 'electrified': True, 'status': 'OPEN'}),
            ('track', 'GZB-DER-DN', {'section_id': 'SEC-GZB-DER', 'direction': 'DOWN', 'electrified': True, 'status': 'OPEN'}),
            ('track', 'DER-KRJ-UP', {'section_id': 'SEC-DER-KRJ', 'direction': 'UP', 'electrified': True, 'status': 'OPEN'}),
            ('track', 'DER-KRJ-DN', {'section_id': 'SEC-DER-KRJ', 'direction': 'DOWN', 'electrified': True, 'status': 'OPEN'}),
            ('track', 'KRJ-ALJN-UP', {'section_id': 'SEC-KRJ-ALJN', 'direction': 'UP', 'electrified': True, 'status': 'OPEN'}),
            ('track', 'KRJ-ALJN-DN', {'section_id': 'SEC-KRJ-ALJN', 'direction': 'DOWN', 'electrified': True, 'status': 'OPEN'}),
            ('asset', 'AS-TRACK-DER-01', {'department': 'ENGINEERING', 'asset_type': 'TRACK', 'footprint': ['DER-KRJ-DN']}),
            ('asset', 'AS-OHE-KRJ-01', {'department': 'TRD', 'asset_type': 'OHE', 'footprint': ['DER-KRJ-DN']}),
            ('asset', 'AS-SIG-DER-01', {'department': 'SNT', 'asset_type': 'INTERLOCKING', 'footprint': ['DER-KRJ-DN']}),
            ('isolation', 'ISO-ZONE-KRJ-02', {'footprint': ['DER-KRJ-DN']}),
        ]

        for kind, eid, data in entities:
            try:
                save_entity(db, kind, EntityInput(id=eid, data=data), admin)
                print(f"Registered network entity: {kind} {eid}")
            except Exception as e:
                # Entity might already exist with expected revision
                pass

    print("Cloud database seeding complete!")

if __name__ == '__main__':
    seed()
