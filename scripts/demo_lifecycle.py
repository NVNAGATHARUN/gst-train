"""Isolated SIMULATED lifecycle replay. Never clears or changes the preview DB.
Uses explicit fixture-time dependency overrides; not current railway operations.
"""
import json, os, pathlib, subprocess, sys, uuid
from datetime import datetime, timezone, timedelta
import re
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]
import psycopg
from psycopg import sql
config=json.loads((ROOT/'.local/db.json').read_text())
name='railsync_demo_'+uuid.uuid4().hex[:12]
with psycopg.connect(host='127.0.0.1',port=55434,user='railsync',password=config['password'],dbname='postgres',autocommit=True,connect_timeout=5) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
os.environ['RAILSYNC_DATABASE_URL']='postgresql+psycopg://railsync:'+config['password']+'@127.0.0.1:55434/'+name
os.environ['RAILSYNC_BROWSER_ORIGINS']='["http://127.0.0.1:3000"]'
os.environ['RAILSYNC_SESSION_COOKIE_SECURE']='false'
subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT,check=True,capture_output=True,text=True)
from fastapi.testclient import TestClient
from sqlalchemy import select
from railsync.main import app
from railsync.db import Session
from railsync.models import User, PlanReservation, OperationalState
from railsync.auth import token_hash
from railsync.network import save_entity, EntityInput
from test_m16_restoration import released
current_date='--current-date' in sys.argv
reference=datetime.fromisoformat('2026-09-21T00:00:00+05:30')
base=datetime.now(timezone(timedelta(hours=5,minutes=30))).replace(microsecond=0)-timedelta(hours=3) if current_date else reference
delta=base-reference
def shift(value):
    if isinstance(value,dict):return {k:shift(v) for k,v in value.items()}
    if isinstance(value,list):return [shift(v) for v in value]
    if isinstance(value,str) and re.fullmatch(r'2026-09-(20|21|22)T[0-9:.]+(?:Z|[+-][0-9:]+)',value):
        return (datetime.fromisoformat(value.replace('Z','+00:00'))+delta).isoformat()
    if isinstance(value,str) and re.fullmatch(r'2026-09-(20|21|22)',value):
        return (datetime.fromisoformat(value)+delta).date().isoformat()
    return value
if current_date:
    for module_name,module in list(sys.modules.items()):
        if module_name.startswith('test_m'):
            if hasattr(module,'NOW'):module.NOW=base
            for attr in ['START','END']:
                if hasattr(module,attr):setattr(module,attr,shift(getattr(module,attr)))
            if hasattr(module,'HORIZON'):module.HORIZON=tuple(t+delta for t in module.HORIZON)

with Session.begin() as db:
    for role,dept in [('ADMIN',None),('PLANNER',None),('CONTROLLER',None),('AUDITOR',None),('DEPARTMENT','ENGINEERING'),('DEPARTMENT','TRD')]:
        token=dept or role
        db.add(User(name='SIMULATED '+token,role=role,department=dept,token_hash=token_hash(token),active=True))
    db.flush()
    admin=db.scalar(select(User).where(User.role=='ADMIN'))
    for kind,id,data in [('station','A',{'name':'A'}),('station','B',{'name':'B'}),('section','SEC-AB',{'from_station':'A','to_station':'B','distance_km':10}),('track','AB',{'section_id':'SEC-AB','electrified':True}),('asset','AS-1',{'department':'ENGINEERING','asset_type':'TRACK','footprint':['AB']})]:
        save_entity(db,kind,EntityInput(id=id,data=data),admin)
with Session() as db:
    initial_operational=db.get(OperationalState,'OPERATIONAL')
    initial_operational_revision=initial_operational.revision if initial_operational else None
transcript=[]
class RecordedClient:
    def __init__(self,client): self.client=client
    def __getattr__(self,method):
        def call(path,**kwargs):
            if current_date and 'json' in kwargs:kwargs['json']=shift(kwargs['json'])
            response=getattr(self.client,method)(path,**kwargs)
            try: output=response.json()
            except ValueError: output=response.text
            transcript.append({'method':method.upper(),'path':path,'actor':kwargs.get('headers',{}).get('Authorization','').removeprefix('Bearer '),'input':kwargs.get('json'),'status':response.status_code,'output':output})
            return response
        return call
folder=ROOT/'docs/evidence'/('lifecycle-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
folder.mkdir(parents=True,exist_ok=False)
result={'scope':'SIMULATED','clock':'Explicit SIMULATED replay clock; base '+base.isoformat()+'; dependency overrides apply only in TestClient; observations are synthetic','database':name,'transport':'in-process real FastAPI TestClient; not browser acceptance','status':'RUNNING','transcript':transcript}
try:
    with TestClient(app) as raw:
        manifest,revision,records,state,release=released(RecordedClient(raw),all_completed=True)
    assert records and all(r['status']=='COMPLETED' for r in records.values())
    assert release['result']['reservation_released'] is True,release
    assert release['result']['railway_control_issued'] is False,release
    with Session() as db:
        assert not any(r.active for r in db.scalars(select(PlanReservation)))
        operational=db.get(OperationalState,'OPERATIONAL')
        assert (operational.revision if operational else None)==initial_operational_revision
        assert not any(r.scope=='OPERATIONAL' for r in db.scalars(select(PlanReservation)))
    result.update(status='PASSED',plan_revision_id=revision['id'],solver_status=revision['content']['solver_status'],completed_requests=len(records),release=release,assertions=['Real request intake and transitions','Real candidate generation and CP-SAT','Independent validation and simulated controller approval','Explicit STARTED and COMPLETED records','Whole-possession restoration evidence','Simulated reservations released','OPERATIONAL revision unchanged; no operational reservations or railway control issued'])
    if current_date:
        with TestClient(app) as raw:
            response=raw.post('/api/v1/plan-revisions/'+revision['id']+'/explanations',headers={'Authorization':'Bearer PLANNER'},json={})
            assert response.status_code==201,response.text
        settings_file=ROOT/'.local/current-lifecycle-preview.json'
        settings_file.write_text(json.dumps({'database':name,'evidence':str(folder),'revision_id':revision['id'],'api_port':8001,'base':base.isoformat(),'scope':'SIMULATED'}),encoding='utf-8')
    print('SIMULATED lifecycle passed; requests completed:',len(records))
except Exception as error:
    result.update(status='FAILED',error=str(error));raise
finally:
    app.dependency_overrides.clear()
    (folder/'lifecycle.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('Evidence:',folder)
