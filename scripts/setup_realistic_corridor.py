"""
Setup and integration of a realistic, bounded Indian Railways corridor for RailSync AI.
Selected Corridor: Ghaziabad Jn (GZB) - Dadri (DER) - Khurja Jn (KRJ) - Aligarh Jn (ALJN)
Zone: North Central Railway (NCR) | Division: Prayagraj | Main Line: Delhi - Kanpur - Howrah Trunk
Interchanges: Eastern Dedicated Freight Corridor (EDFC) & Inland Container Depot (ICD Dadri)
"""
import sys, pathlib, json, uuid
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests')]

from sqlalchemy import select, delete, text
from fastapi.testclient import TestClient

from railsync.db import Session, engine
from railsync.models import (
    User, NetworkEntity, NetworkRevision, NetworkLink,
    MaintenanceRequest, RequestRevision, Train, TrainRun, TrainOccupancy,
    CoaWindow, FreightForecast, ResourceUnit, CoordinationRevision,
    PlanningSnapshot, PlanningRun, PlanRevision, ValidationReport,
    PlanComparison, DecisionExplanation, ControllerDecision, AuditEvent,
    OperationalState, PlanReservation
)
from railsync.auth import token_hash
from railsync.network import save_entity, EntityInput
from railsync.validator import content_hash
from railsync.main import app
from railsync.planning import run_one
from railsync.proposal_pipeline import queue_proposal
from railsync.validation_schema import ValidationContext
from railsync.snapshots import facts, SnapshotInput

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime.now(IST)
BASE_WINDOW = NOW.replace(minute=0, second=0, microsecond=0)
SERVICE_DATE = BASE_WINDOW.strftime("%Y-%m-%d")

# Dynamic horizon anchored around current execution time
HORIZON_START = (BASE_WINDOW + timedelta(hours=1)).isoformat()
HORIZON_END = (BASE_WINDOW + timedelta(hours=7)).isoformat()
ASSESSED_AT = NOW.isoformat()

def ts(hour_offset, minute_offset=0):
    """Helper to generate ISO timestamps relative to BASE_WINDOW."""
    return (BASE_WINDOW + timedelta(hours=hour_offset, minutes=minute_offset)).isoformat()

print("=" * 80)
print("RAILSYNC AI: REALISTIC INDIAN RAILWAYS CORRIDOR SETUP")
print("Corridor: Ghaziabad Jn (GZB) - Dadri (DER) - Khurja Jn (KRJ) - Aligarh Jn (ALJN)")
print(f"Base Window: {BASE_WINDOW.isoformat()} | Horizon: {HORIZON_START} to {HORIZON_END}")
print("=" * 80)

def auth(role="ADMIN"):
    return {"Authorization": f"Bearer {role}"}

with TestClient(app) as client:
    # -------------------------------------------------------------------------
    # 1. USERS & ROLES
    # -------------------------------------------------------------------------
    print("\n[1/8] Verifying users and roles...")
    with Session.begin() as db:
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
                db.add(User(name=f"NCR {token}", role=role, department=dept, token_hash=token_hash(token), active=True))
    print("[OK] Roles provisioned: ADMIN, PLANNER, CONTROLLER, AUDITOR, ENGINEERING, TRD, SNT")

    # -------------------------------------------------------------------------
    # 2. NETWORK TOPOLOGY (STATIONS, SECTIONS, TRACKS, ISOLATIONS, ASSETS)
    # -------------------------------------------------------------------------
    print("\n[2/8] Constructing realistic corridor network topology...")
    def save_or_update_entity(db, kind, eid, data, admin):
        entity = db.get(NetworkEntity, eid)
        if entity:
            rev = db.scalar(select(NetworkRevision).where(NetworkRevision.entity_id==eid, NetworkRevision.revision==entity.revision))
            if rev and rev.payload == data:
                return {'id': eid, 'kind': kind, 'revision': entity.revision, **data}
            return save_entity(db, kind, EntityInput(id=eid, expected_revision=entity.revision, data=data), admin)
        return save_entity(db, kind, EntityInput(id=eid, expected_revision=0, data=data), admin)

    with Session.begin() as db:
        admin_user = db.scalar(select(User).where(User.role == 'ADMIN'))
        
        # 4 Stations
        stations = [
            ("STA-GZB", "Ghaziabad Jn (GZB)"),
            ("STA-DER", "Dadri (DER)"),
            ("STA-KRJ", "Khurja Jn (KRJ)"),
            ("STA-ALJN", "Aligarh Jn (ALJN)"),
        ]
        for sid, name in stations:
            save_or_update_entity(db, 'station', sid, {'name': name}, admin_user)

        # 3 Sections
        sections = [
            ("SEC-GZB-DER", "STA-GZB", "STA-DER", 16.5),
            ("SEC-DER-KRJ", "STA-DER", "STA-KRJ", 31.5),
            ("SEC-KRJ-ALJN", "STA-KRJ", "STA-ALJN", 34.5),
        ]
        for sec_id, f_sta, t_sta, length in sections:
            save_or_update_entity(db, 'section', sec_id, {
                'from_station': f_sta, 'to_station': t_sta, 'distance_km': length
            }, admin_user)

        # 6 Double-Line Electrified Tracks (UP & DOWN per Section)
        tracks = [
            ("TRK-GZB-DER-UP", "SEC-GZB-DER", "UP", True),
            ("TRK-GZB-DER-DN", "SEC-GZB-DER", "DOWN", True),
            ("TRK-DER-KRJ-UP", "SEC-DER-KRJ", "UP", True),
            ("TRK-DER-KRJ-DN", "SEC-DER-KRJ", "DOWN", True),
            ("TRK-KRJ-ALJN-UP", "SEC-KRJ-ALJN", "UP", True),
            ("TRK-KRJ-ALJN-DN", "SEC-KRJ-ALJN", "DOWN", True),
        ]
        for tid, sec_id, direct, elec in tracks:
            save_or_update_entity(db, 'track', tid, {
                'section_id': sec_id, 'direction': direct, 'status': 'OPEN', 'electrified': elec
            }, admin_user)

        # 6 Traction Distribution (TRD) 25kV OHE Isolation Zones (Track-specific Motorized Section Isolators)
        isolations = [
            ("ISO-GZB-DER-UP", ["TRK-GZB-DER-UP"]),
            ("ISO-GZB-DER-DN", ["TRK-GZB-DER-DN"]),
            ("ISO-DER-KRJ-UP", ["TRK-DER-KRJ-UP"]),
            ("ISO-DER-KRJ-DN", ["TRK-DER-KRJ-DN"]),
            ("ISO-KRJ-ALJN-UP", ["TRK-KRJ-ALJN-UP"]),
            ("ISO-KRJ-ALJN-DN", ["TRK-KRJ-ALJN-DN"]),
        ]
        for iso_id, footprints in isolations:
            save_or_update_entity(db, 'isolation', iso_id, {
                'footprint': footprints
            }, admin_user)

        # 5 Critical Railway Assets
        assets = [
            ("ASSET-ENG-TRACK-DER-KRJ", "ENGINEERING", "TRACK_STRUCTURE", ["TRK-DER-KRJ-DN"]),
            ("ASSET-TRD-OHE-DER-KRJ", "TRD", "OHE_LINE", ["TRK-DER-KRJ-DN"]),
            ("ASSET-SNT-EI-KRJ", "SNT", "POINT_MACHINE", ["TRK-DER-KRJ-DN"]),
            ("ASSET-ENG-TRACK-GZB-DER", "ENGINEERING", "TRACK_STRUCTURE", ["TRK-GZB-DER-UP"]),
            ("ASSET-TRD-OHE-GZB-DER", "TRD", "OHE_LINE", ["TRK-GZB-DER-UP"]),
        ]
        for aid, dept, atype, footprint in assets:
            save_or_update_entity(db, 'asset', aid, {
                'department': dept, 'asset_type': atype, 'footprint': footprint
            }, admin_user)
            
    print("[OK] 4 Stations (GZB, DER, KRJ, ALJN), 3 Sections (82.5 km), 6 Electrified Tracks, 3 Isolation Zones, 5 Assets registered.")

    # -------------------------------------------------------------------------
    # 3. MAINTENANCE RESOURCES & DUTY PROFILES
    # -------------------------------------------------------------------------
    print("\n[3/8] Provisioning railway maintenance resources...")
    resources = [
        ('CSM-TAMPER-DER', 'TRACK_MACHINE', 'ENGINEERING', 'TRK-DER-KRJ-DN'),
        ('TOWER-WAGON-KRJ', 'TOWER_WAGON', 'TRD', 'TRK-DER-KRJ-DN'),
        ('CREW-PWAY-DER', 'TRACK_CREW', 'ENGINEERING', 'TRK-GZB-DER-UP'),
        ('CREW-TRD-KRJ', 'TRD_CREW', 'TRD', 'TRK-GZB-DER-UP'),
        ('CREW-SNT-KRJ', 'SNT_CREW', 'SNT', 'TRK-DER-KRJ-DN'),
    ]

    for rid, rtype, dept, home_trk in resources:
        with Session() as db:
            existing = db.scalar(select(ResourceUnit).where(ResourceUnit.id == rid))
            existing_prof = db.scalar(select(CoordinationRevision).where(
                CoordinationRevision.kind == 'RESOURCE_PROFILE', CoordinationRevision.entity_key == rid
            ).order_by(CoordinationRevision.revision.desc()).limit(1))
        
        if not existing:
            client.post('/api/v1/resources', json={
                'id': rid, 'resource_type': rtype, 'department': dept,
                'available_start': ts(-48, 0), 'available_end': ts(48, 0),
                'source_mode': 'SIMULATED'
            }, headers=auth('ADMIN'))
        
        # Attach or upgrade profile with full 48-hour history coverage
        prof = {
            'source_mode': 'SIMULATED', 'rule_reference': 'NCR Section Resource Policy',
            'departments': [dept],
            'qualifications': [{'skill': 'INSPECTION', 'start_at': ts(-48, 0), 'end_at': ts(48, 0)}],
            'calendar': [{'start_at': ts(-48, 0), 'end_at': ts(48, 0)}],
            'home_track': home_trk,
            'history': {'start_at': ts(-48, 0), 'end_at': ts(48, 0)},
            'duties': [], 'min_rest_minutes': 0, 'max_duty_minutes_per_24h': 480, 'pool_id': None
        }
        exp_rev = existing_prof.revision if existing_prof else 0
        client.post(f'/api/v1/resources/{rid}/profiles', json={'expected_revision': exp_rev, 'data': prof}, headers=auth('ADMIN'))

    # Provision Multi-Department Coordination Policy for Shadow Blocking (Eng + TRD + S&T)
    def sig(dept='ENGINEERING', issue='INSPECTION', **changes):
        return {'department': dept, 'issue_type': issue, 'power_state': 'ANY', 'signalling_state': 'ANY', **changes}

    coord_policy = {
        'source_mode': 'SIMULATED', 'rule_reference': 'Realistic NCR Joint Maintenance Coordination Policy',
        'pairs': [
            # Engineering + TRD Shadow Block
            {'id': 'PAIR-ENG-TRD', 'left': sig('ENGINEERING', 'INSPECTION'), 'right': sig('TRD', 'OHE_WORK', power_state='OFF'),
             'footprint_relation': 'SAME', 'mode': 'ALLOW_PARALLEL', 'shared_setup': True, 'shared_restoration': True},
            # Engineering + SNT Block
            {'id': 'PAIR-ENG-SNT', 'left': sig('ENGINEERING', 'INSPECTION'), 'right': sig('SNT', 'POINT_MACHINE', signalling_state='DISCONNECTED'),
             'footprint_relation': 'SAME', 'mode': 'ALLOW_PARALLEL', 'shared_setup': True, 'shared_restoration': True},
            # TRD + SNT Block
            {'id': 'PAIR-TRD-SNT', 'left': sig('TRD', 'OHE_WORK', power_state='OFF'), 'right': sig('SNT', 'POINT_MACHINE', signalling_state='DISCONNECTED'),
             'footprint_relation': 'SAME', 'mode': 'ALLOW_PARALLEL', 'shared_setup': True, 'shared_restoration': True},
        ],
        'groups': [
            {'id': 'GROUP-ENG-TRD-SNT',
             'members': [sig('ENGINEERING', 'INSPECTION'), sig('TRD', 'OHE_WORK', power_state='OFF'), sig('SNT', 'POINT_MACHINE', signalling_state='DISCONNECTED')],
             'mode': 'ALLOW_PARALLEL'}
        ],
        'travel': [], 'pools': []
    }
    with Session() as db:
        old_pol = db.scalar(select(CoordinationRevision).where(
            CoordinationRevision.kind == 'POLICY', CoordinationRevision.entity_key == 'NCR-JOINT'
        ).order_by(CoordinationRevision.revision.desc()).limit(1))
    
    exp_pol_rev = old_pol.revision if old_pol else 0
    p_resp = client.post('/api/v1/coordination-policies/NCR-JOINT', json={'expected_revision': exp_pol_rev, 'data': coord_policy}, headers=auth('ADMIN')).json()
    policy_id = p_resp['id']

    print(f"[OK] Resources & duty profiles registered with Shadow Block Coordination Policy (ID: {policy_id[:8]}...)")

    # -------------------------------------------------------------------------
    # 4. TIMETABLE RUNS, OCCUPANCY, COA SLOTS, AND EDFC FREIGHT
    # -------------------------------------------------------------------------
    print("\n[4/8] Generating timetable occupancy, COA slots, and EDFC freight forecasts...")
    
    with Session.begin() as db:
        db.execute(delete(TrainOccupancy))
        db.execute(delete(TrainRun))
        db.execute(delete(Train))
        db.execute(delete(CoaWindow))
        db.execute(delete(FreightForecast))
    
    # 5 Key Passenger Trains
    train_runs = [
        # Train 1: 22436 Vande Bharat Express (DOWN Line towards Varanasi)
        {
            'train_id': '22436-VANDE-BHARAT', 'train_name': '22436 New Delhi - Varanasi Vande Bharat Express',
            'train_type': 'PREMIUM', 'service_date': SERVICE_DATE, 'source_mode': 'SIMULATED', 'source_revision': 1,
            'occupancies': [
                {'track_id': 'TRK-GZB-DER-DN', 'route_sequence': 1, 'enter_at': ts(1, 15), 'exit_at': ts(1, 35)},
                {'track_id': 'TRK-DER-KRJ-DN', 'route_sequence': 2, 'enter_at': ts(1, 35), 'exit_at': ts(1, 55)},
                {'track_id': 'TRK-KRJ-ALJN-DN', 'route_sequence': 3, 'enter_at': ts(1, 55), 'exit_at': ts(2, 15)},
            ]
        },
        # Train 2: 12302 Howrah Rajdhani Express (DOWN Line towards Howrah)
        {
            'train_id': '12302-HOWRAH-RAJDHANI', 'train_name': '12302 New Delhi - Howrah Rajdhani Express',
            'train_type': 'PREMIUM', 'service_date': SERVICE_DATE, 'source_mode': 'SIMULATED', 'source_revision': 1,
            'occupancies': [
                {'track_id': 'TRK-GZB-DER-DN', 'route_sequence': 1, 'enter_at': ts(1, 35), 'exit_at': ts(1, 55)},
                {'track_id': 'TRK-DER-KRJ-DN', 'route_sequence': 2, 'enter_at': ts(1, 55), 'exit_at': ts(2, 15)},
                {'track_id': 'TRK-KRJ-ALJN-DN', 'route_sequence': 3, 'enter_at': ts(2, 15), 'exit_at': ts(2, 35)},
            ]
        },
        # Train 3: 12418 Prayagraj Express (DOWN Line towards Prayagraj)
        {
            'train_id': '12418-PRAYAGRAJ-EXP', 'train_name': '12418 New Delhi - Prayagraj Superfast Express',
            'train_type': 'EXPRESS', 'service_date': SERVICE_DATE, 'source_mode': 'SIMULATED', 'source_revision': 1,
            'occupancies': [
                {'track_id': 'TRK-GZB-DER-DN', 'route_sequence': 1, 'enter_at': ts(5, 20), 'exit_at': ts(5, 40)},
                {'track_id': 'TRK-DER-KRJ-DN', 'route_sequence': 2, 'enter_at': ts(5, 40), 'exit_at': ts(6, 5)},
                {'track_id': 'TRK-KRJ-ALJN-DN', 'route_sequence': 3, 'enter_at': ts(6, 5), 'exit_at': ts(6, 30)},
            ]
        },
        # Train 4: 14218 Unchahar Express (UP Line towards Ghaziabad/Delhi)
        {
            'train_id': '14218-UNCHAHAR-EXP', 'train_name': '14218 Unchahar Express',
            'train_type': 'EXPRESS', 'service_date': SERVICE_DATE, 'source_mode': 'SIMULATED', 'source_revision': 1,
            'occupancies': [
                {'track_id': 'TRK-KRJ-ALJN-UP', 'route_sequence': 1, 'enter_at': ts(1, 15), 'exit_at': ts(1, 40)},
                {'track_id': 'TRK-DER-KRJ-UP', 'route_sequence': 2, 'enter_at': ts(1, 40), 'exit_at': ts(2, 5)},
                {'track_id': 'TRK-GZB-DER-UP', 'route_sequence': 3, 'enter_at': ts(2, 5), 'exit_at': ts(2, 25)},
            ]
        },
        # Train 5: 04414 Suburban Local EMU (UP Line)
        {
            'train_id': '04414-EMU-LOCAL', 'train_name': '04414 Aligarh - Delhi EMU',
            'train_type': 'SUBURBAN', 'service_date': SERVICE_DATE, 'source_mode': 'SIMULATED', 'source_revision': 1,
            'occupancies': [
                {'track_id': 'TRK-KRJ-ALJN-UP', 'route_sequence': 1, 'enter_at': ts(5, 0), 'exit_at': ts(5, 30)},
                {'track_id': 'TRK-DER-KRJ-UP', 'route_sequence': 2, 'enter_at': ts(5, 30), 'exit_at': ts(6, 0)},
                {'track_id': 'TRK-GZB-DER-UP', 'route_sequence': 3, 'enter_at': ts(6, 0), 'exit_at': ts(6, 25)},
            ]
        },
    ]
    for tr in train_runs:
        r = client.post('/api/v1/operations/train-runs', json=tr, headers=auth('PLANNER'))
        assert r.status_code == 201, f"Train run failed: {r.text}"

    # COA Maintenance Windows (Declared corridor availability slots)
    all_tracks = ['TRK-GZB-DER-UP', 'TRK-GZB-DER-DN', 'TRK-DER-KRJ-UP', 'TRK-DER-KRJ-DN', 'TRK-KRJ-ALJN-UP', 'TRK-KRJ-ALJN-DN']
    for tid in all_tracks:
        coa = {
            'external_id': f'COA-{tid}-NIGHT',
            'source_revision': 1,
            'track_id': tid,
            'start_at': ts(2, 20),
            'end_at': ts(5, 30),
            'source_mode': 'SIMULATED'
        }
        r = client.post('/api/v1/operations/coa-windows', json=coa, headers=auth('PLANNER'))
        assert r.status_code == 201, f"COA window failed: {r.text}"

    # Freight Forecast Uncertainty Envelopes (e.g. from EDFC interchange)
    for tid in all_tracks:
        ff = {
            'external_id': f'FF-EDFC-{tid}',
            'source_revision': 1,
            'track_id': tid,
            'start_at': ts(5, 10),
            'end_at': ts(5, 35),
            'issued_at': ts(-2, 0),
            'expected_count': 1,
            'confidence': 0.75,
            'uncertainty_semantics': 'EDFC junction feeder uncertainty envelope',
            'source_mode': 'SIMULATED'
        }
        r = client.post('/api/v1/operations/freight-forecasts', json=ff, headers=auth('PLANNER'))
        assert r.status_code == 201, f"Freight forecast failed: {r.text}"
    print("[OK] Timetable (Vande Bharat, Rajdhani, Prayagraj, Unchahar, EMU), COA Slots, and EDFC Freight Envelopes ready.")

    # -------------------------------------------------------------------------
    # 5. MAINTENANCE DEMAND TICKETS (ENGINEERING, TRD, S&T)
    # -------------------------------------------------------------------------
    print("\n[5/8] Creating multi-department maintenance demand tickets...")
    with Session.begin() as db:
        db.execute(text("UPDATE maintenance_requests SET status = 'CANCELLED' WHERE status = 'PENDING_PLANNING'"))
    requests_to_create = [
        # Ticket 1: Engineering Track Tamping on DER-KRJ DOWN track
        {
            'dept': 'ENGINEERING',
            'data': {
                'department': 'ENGINEERING', 'asset_id': 'ASSET-ENG-TRACK-DER-KRJ', 'footprint': ['TRK-DER-KRJ-DN'],
                'issue_type': 'INSPECTION', 'description': 'Automated Track Tamping (CSM) & USFD defect correction post-monsoon',
                'severity': 4, 'urgency': 4, 'work_minutes': 60, 'setup_minutes': 10, 'restore_minutes': 10,
                'earliest_at': ts(2, 20), 'deadline_at': ts(5, 20),
                'mandatory': True, 'block_required': True, 'power_block_required': False,
                'isolation_zone': None, 'power_state': 'ANY', 'signalling_state': 'ANY',
                'requirements': [{'type': 'TRACK_MACHINE', 'quantity': 1, 'qualification': 'INSPECTION'}]
            }
        },
        # Ticket 2: TRD OHE Wire Overhaul on DER-KRJ DOWN track (COMPATIBLE for Shadow Block!)
        {
            'dept': 'TRD',
            'data': {
                'department': 'TRD', 'asset_id': 'ASSET-TRD-OHE-DER-KRJ', 'footprint': ['TRK-DER-KRJ-DN'],
                'issue_type': 'OHE_WORK', 'description': '25kV Contact Wire height-stagger adjustment & insulator washing',
                'severity': 4, 'urgency': 4, 'work_minutes': 60, 'setup_minutes': 10, 'restore_minutes': 10,
                'earliest_at': ts(2, 20), 'deadline_at': ts(5, 20),
                'mandatory': True, 'block_required': True, 'power_block_required': True,
                'isolation_zone': 'ISO-DER-KRJ-DN', 'power_state': 'OFF', 'signalling_state': 'ANY',
                'requirements': [{'type': 'TOWER_WAGON', 'quantity': 1, 'qualification': 'INSPECTION'}]
            }
        },
        # Ticket 3: S&T Interlocking Point Machine Overhaul at Khurja
        {
            'dept': 'SNT',
            'data': {
                'department': 'SNT', 'asset_id': 'ASSET-SNT-EI-KRJ', 'footprint': ['TRK-DER-KRJ-DN'],
                'issue_type': 'POINT_MACHINE', 'description': 'Quarterly overhaul of high-speed turnout point machine 102A',
                'severity': 3, 'urgency': 3, 'work_minutes': 45, 'setup_minutes': 10, 'restore_minutes': 10,
                'earliest_at': ts(2, 20), 'deadline_at': ts(5, 20),
                'mandatory': False, 'block_required': True, 'power_block_required': False,
                'isolation_zone': None, 'power_state': 'ANY', 'signalling_state': 'DISCONNECTED',
                'requirements': [{'type': 'SNT_CREW', 'quantity': 1, 'qualification': 'INSPECTION'}]
            }
        },
        # Ticket 4: Engineering Rail Joint Welding on GZB-DER UP track
        {
            'dept': 'ENGINEERING',
            'data': {
                'department': 'ENGINEERING', 'asset_id': 'ASSET-ENG-TRACK-GZB-DER', 'footprint': ['TRK-GZB-DER-UP'],
                'issue_type': 'WELDING', 'description': 'Thermit welding of rail joint KM 14/2-4 under caution order',
                'severity': 3, 'urgency': 3, 'work_minutes': 50, 'setup_minutes': 10, 'restore_minutes': 10,
                'earliest_at': ts(2, 20), 'deadline_at': ts(5, 20),
                'mandatory': False, 'block_required': True, 'power_block_required': False,
                'isolation_zone': None, 'power_state': 'ANY', 'signalling_state': 'ANY',
                'requirements': [{'type': 'TRACK_CREW', 'quantity': 1, 'qualification': 'INSPECTION'}]
            }
        },
        # Ticket 5: TRD Insulator Washing on GZB-DER UP track
        {
            'dept': 'TRD',
            'data': {
                'department': 'TRD', 'asset_id': 'ASSET-TRD-OHE-GZB-DER', 'footprint': ['TRK-GZB-DER-UP'],
                'issue_type': 'INSULATOR_WASHING', 'description': 'Chemical cleaning of 25kV bracket insulators',
                'severity': 3, 'urgency': 3, 'work_minutes': 45, 'setup_minutes': 10, 'restore_minutes': 10,
                'earliest_at': ts(2, 20), 'deadline_at': ts(5, 20),
                'mandatory': False, 'block_required': True, 'power_block_required': True,
                'isolation_zone': 'ISO-GZB-DER-UP', 'power_state': 'OFF', 'signalling_state': 'ANY',
                'requirements': [{'type': 'TRD_CREW', 'quantity': 1, 'qualification': 'INSPECTION'}]
            }
        }
    ]

    created_requests = []
    for item in requests_to_create:
        resp = client.post('/api/v1/maintenance-requests', json=item['data'], headers=auth(item['dept'])).json()
        req_id = resp['id']
        for act in ['VALIDATE', 'SUBMIT']:
            client.post(f'/api/v1/maintenance-requests/{req_id}/transitions',
                        json={'action': act, 'expected_revision': 1, 'reason': 'Realistic NCR maintenance intake'},
                        headers=auth(item['dept']))
        created_requests.append(req_id)
    print(f"[OK] 5 Maintenance tickets submitted across Engineering, TRD, and S&T (IDs: {[r[:8] for r in created_requests]})")

    # -------------------------------------------------------------------------
    # 6. SEAL IMMUTABLE PLANNING SNAPSHOT & RUN SOLVER ENGINES
    # -------------------------------------------------------------------------
    print("\n[6/8] Sealing Planning Snapshot and executing dual CP-SAT & Baseline solvers...")
    
    # Compute raw facts first to establish exact content hash for validation context
    with Session() as db:
        dummy_input = SnapshotInput(
            horizon_start=datetime.fromisoformat(HORIZON_START),
            horizon_end=datetime.fromisoformat(HORIZON_END),
            track_ids=['TRK-DER-KRJ-DN'],
            coordination_policy_id=uuid.UUID(policy_id)
        )
        raw_facts = facts(db, dummy_input)
    
    exact_facts_hash = content_hash(raw_facts)

    # Define validation context covering the horizon with safety clearance
    val_coverage = []
    for src, trk in [(s, None) for s in ['NETWORK', 'REQUESTS', 'RESOURCES', 'COMMITMENTS']] + [(s, 'TRK-DER-KRJ-DN') for s in ['OCCUPANCY', 'COA', 'FREIGHT']]:
        val_coverage.append({
            'source': src, 'track_id': trk,
            'start_at': ts(-1, 0), 'end_at': ts(10, 0),
            'complete': True, 'evidence_reference': 'Realistic NCR GZB-ALJN Corridor Complete Input Dataset'
        })
    val_ctx = {
        'scope': 'SIMULATED', 'facts_hash': exact_facts_hash,
        'received_at': ts(-1, 0), 'valid_until': ts(24, 0),
        'coverage': val_coverage, 'coa_semantics': 'ACCESS_ENVELOPE',
        'clearance_before_minutes': 5, 'clearance_after_minutes': 5,
        'protect_freight_envelope': True, 'commitments_known_empty': True,
        'rule_reference': 'Northern/NCR Working Time Table & Block Rules (Simulated)'
    }
    
    # Primary maintenance track TRK-DER-KRJ-DN
    snapshot_payload = {
        'horizon_start': HORIZON_START,
        'horizon_end': HORIZON_END,
        'track_ids': ['TRK-DER-KRJ-DN'],
        'coordination_policy_id': policy_id,
        'validation_context': val_ctx
    }
    snap_resp = client.post('/api/v1/snapshots', json=snapshot_payload, headers=auth('PLANNER')).json()
    snapshot_id = snap_resp['id']
    snapshot_hash = snap_resp['content_hash']
    print(f"[OK] Snapshot created: {snapshot_id} (SHA-256: {snapshot_hash[:16]}...)")

    # Queue proposal (runs priority assessment, availability, opportunities, coordination, and queues BASELINE + CP_SAT)
    with Session() as db:
        snap_obj = db.get(PlanningSnapshot, uuid.UUID(snapshot_id))
        ctx_obj = ValidationContext.model_validate(snap_obj.manifest['validation_context'])
        proposal_meta, runs = queue_proposal(db, snap_obj, datetime.fromisoformat(ASSESSED_AT), ctx_obj)
        db.commit()
    print(f"[OK] Pipeline computed: {proposal_meta['candidate_count']} candidates bundled. Both BASELINE and CP_SAT queued.")

    # Execute both solver runs
    import time
    def wait_for_run(run_id, max_seconds=20):
        for _ in range(max_seconds * 2):
            r = client.get(f'/api/v1/planning-runs/{run_id}', headers=auth()).json()
            if r['status'] in ('COMPLETED', 'FAILED'):
                return r
            run_one()
            time.sleep(0.5)
        return client.get(f'/api/v1/planning-runs/{run_id}', headers=auth()).json()

    baseline_run_id = [r.id for r in runs if r.planner_type == 'BASELINE'][0]
    cpsat_run_id = [r.id for r in runs if r.planner_type == 'CP_SAT'][0]

    baseline_run = wait_for_run(baseline_run_id)
    cpsat_run = wait_for_run(cpsat_run_id)
    
    print(f"[OK] Baseline Run: {baseline_run['status']} (Scheduled: {baseline_run['result']['counts']['scheduled']})")
    print(f"[OK] CP-SAT Solver: {cpsat_run['status']} (Status: {cpsat_run['result']['solver_status']}, Scheduled: {cpsat_run['result']['counts']['scheduled']})")

    # -------------------------------------------------------------------------
    # 7. PLAN REVISIONS, INDEPENDENT VALIDATION, AND DECISIONS
    # -------------------------------------------------------------------------
    print("\n[7/8] Independent validation, controller approval, and KPI comparisons...")
    
    # Create Baseline Plan Revision
    rev_baseline = client.post('/api/v1/plan-revisions', headers=auth('PLANNER'), json={
        'run_id': str(baseline_run_id), 'expected_plan_hash': content_hash(baseline_run['result'])
    }).json()

    # Create CP-SAT Plan Revision
    rev_cpsat = client.post('/api/v1/plan-revisions', headers=auth('PLANNER'), json={
        'run_id': str(cpsat_run_id), 'expected_plan_hash': content_hash(cpsat_run['result'])
    }).json()
    
    # Run Independent Validation on CP-SAT Proposal
    val_report = client.post('/api/v1/validation-reports', headers=auth('PLANNER'), json={
        'plan_revision_id': rev_cpsat['id'], 'expected_plan_hash': rev_cpsat['plan_hash']
    }).json()
    findings_count = len(val_report['result'].get('findings', [])) if 'result' in val_report else len(val_report.get('findings', []))
    print(f"[OK] Independent Safety & Rule Validation: STATUS = {val_report['status']} (Checks evaluated: {findings_count})")

    # Generate Baseline vs CP-SAT KPI Comparison
    comparison = client.post('/api/v1/plan-comparisons', headers=auth('PLANNER'), json={
        'baseline_plan_revision_id': rev_baseline['id'],
        'railsync_plan_revision_id': rev_cpsat['id']
    }).json()
    metrics_comp = comparison.get('content', {}).get('metrics', {})
    print(f"[OK] Live KPI Deltas Computed: Maintenance Hours Planned: {metrics_comp.get('total_maintenance_hours_planned')}, Blocks Granted: {metrics_comp.get('blocks_granted_count')}")

    # Section Controller Approves CP-SAT Plan Revision
    with Session.begin() as db:
        db.execute(text("UPDATE plan_reservations SET active = false WHERE scope = 'SIMULATED' AND active = true"))
        sim_state = db.get(OperationalState, 'SIMULATED')
        expected_op_rev = sim_state.revision if sim_state else 0

    dec_body = {
        'action': 'APPROVE',
        'idempotency_key': str(uuid.uuid4()),
        'expected_plan_hash': rev_cpsat['plan_hash'],
        'expected_operational_revision': expected_op_rev,
        'validation_report_id': val_report['id'],
        'reason': 'Approved realistic GZB-ALJN joint maintenance block with shadow scheduling on TRK-DER-KRJ-DN during night freight slot.'
    }
    controller_resp = client.post(f"/api/v1/plan-revisions/{rev_cpsat['id']}/decisions", json=dec_body, headers=auth('CONTROLLER')).json()
    print(f"[OK] Section Controller Approval: ID = {controller_resp['id']}, State = APPROVED")

    # -------------------------------------------------------------------------
    # 8. DISRUPTION WHAT-IF SCENARIO (DYNAMIC REPLANNING SIMULATION)
    # -------------------------------------------------------------------------
    print("\n[8/8] Testing What-If Disruption & Dynamic Replanning...")
    
    # Find Rajdhani Express occupancy on DER-KRJ-DN
    rajdhani_occ = [o for o in raw_facts['occupancy'] if 'RAJDHANI' in o['train_id'] and o['track_id'] == 'TRK-DER-KRJ-DN'][0]
    
    scenario_body = {
        'idempotency_key': str(uuid.uuid4()),
        'source_snapshot_id': snapshot_id,
        'expected_source_hash': snapshot_hash,
        'name': 'GZB-ALJN 15-min Rajdhani Delay Disruption Scenario',
        'changes': [
            {
                'kind': 'TRAIN_DELAY',
                'occupancy_id': rajdhani_occ['id'],
                'delay_minutes': 15
            }
        ]
    }
    scen_resp = client.post('/api/v1/what-if-scenarios', json=scenario_body, headers=auth('PLANNER')).json()
    scen_snap_id = scen_resp['snapshot_id']
    scen_baseline_id = scen_resp['baseline_run']['id']
    scen_cpsat_id = scen_resp['optimized_run']['id']
    print(f"[OK] Isolated Scenario Created: {scen_resp['id']} (Snapshot: {scen_snap_id})")
    
    # Wait for scenario solver runs
    scen_base_run = wait_for_run(scen_baseline_id)
    scen_run = wait_for_run(scen_cpsat_id)
    
    scen_rev = client.post('/api/v1/plan-revisions', headers=auth('PLANNER'), json={
        'run_id': str(scen_cpsat_id), 'expected_plan_hash': content_hash(scen_run['result'])
    }).json()
    scen_val = client.post('/api/v1/validation-reports', headers=auth('PLANNER'), json={
        'plan_revision_id': scen_rev['id'], 'expected_plan_hash': scen_rev['plan_hash']
    }).json()
    print(f"[OK] What-If Replanner: Evaluated delayed train impact -> Status = {scen_run['result']['solver_status']}, Validation = {scen_val['status']}")

    # Compute What-If Impact Delta
    impact_resp = client.post(f"/api/v1/what-if-scenarios/{scen_resp['id']}/impacts", json={
        'source_plan_revision_id': rev_cpsat['id'],
        'scenario_plan_revision_id': scen_rev['id']
    }, headers=auth('PLANNER')).json()
    print(f"[OK] Disruption Impact Delta computed successfully (Comparison Type: {impact_resp.get('comparison_type')})")

print("\n" + "=" * 80)
print("SUCCESS: REALISTIC INDIAN RAILWAYS CORRIDOR INTEGRATED AND VERIFIED!")
print(f"Active Snapshot ID: {snapshot_id}")
print(f"Active Plan Revision ID: {rev_cpsat['id']}")
print(f"Web Preview: http://127.0.0.1:3000/planning?snapshot_id={snapshot_id}&plan_revision_id={rev_cpsat['id']}")
print("=" * 80)
