import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from railsync.db import engine, Session
from railsync.models import User
from railsync.auth import token_hash
from railsync.main import app
from railsync.network import save_entity, EntityInput

@pytest.fixture(autouse=True)
def clean_database():
    assert engine.url.database == "railsync_test", "Tests require a dedicated railsync_test database"
    with engine.begin() as c:
        names=c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'")).scalars().all()
        if names:c.execute(text('TRUNCATE '+','.join('"'+n+'"' for n in names)+' CASCADE'))
    with Session.begin() as db:
        for role,dept in [("ADMIN",None),("PLANNER",None),("CONTROLLER",None),("AUDITOR",None),("DEPARTMENT","ENGINEERING"),("DEPARTMENT","TRD")]:
            token=dept or role
            db.add(User(name=token,role=role,department=dept,token_hash=token_hash(token),active=True))
        db.flush()
        from sqlalchemy import select
        admin=db.scalar(select(User).where(User.role=='ADMIN'))
        for kind,id,data in [('station','A',{'name':'A'}),('station','B',{'name':'B'}),('section','SEC-AB',{'from_station':'A','to_station':'B','distance_km':10}),('track','AB',{'section_id':'SEC-AB','electrified':True}),('asset','AS-1',{'department':'ENGINEERING','asset_type':'TRACK','footprint':['AB']})]:
            save_entity(db,kind,EntityInput(id=id,data=data),admin)

@pytest.fixture
def client():
    try:
        with TestClient(app) as c:yield c
    finally:
        app.dependency_overrides.clear()

def auth(role="PLANNER"):
    return {"Authorization":"Bearer "+role}
