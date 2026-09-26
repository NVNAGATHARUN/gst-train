"""Create a local prototype user; token is displayed once. No default login tokens."""
import argparse,secrets,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'backend'))
from railsync.db import Session
from railsync.models import User
from railsync.auth import token_hash
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('role',choices=['ADMIN','PLANNER','CONTROLLER','AUDITOR','DEPARTMENT']);p.add_argument('--department',choices=['ENGINEERING','TRD','SNT']);a=p.parse_args()
if (a.role=='DEPARTMENT') != bool(a.department):p.error('Only DEPARTMENT users require a department')
token=secrets.token_urlsafe(32)
with Session.begin() as db:db.add(User(name=a.name,role=a.role,department=a.department,token_hash=token_hash(token),active=True))
print('Store this bearer token securely; it cannot be recovered: '+token)
