"""Record actual replacement-approval backend output on the test database."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
os.chdir(root)
evidence=root/'docs/evidence'
port=int(os.environ.get('RAILSYNC_TEST_PORT','55432'))
credential=json.loads((root/'.local/db.json').read_text())
env={**os.environ,'PYTHONPATH':'backend','RAILSYNC_DATABASE_URL':
    f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:{port}/railsync_test",
    'RAILSYNC_M16_APPROVAL_EVIDENCE_OUTPUT':str(evidence/'M16-approval-backend-example.json')}
commands=[[sys.executable,'-m','alembic','upgrade','head'],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        f'--junitxml={evidence}/M16-approval.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    outputs.append('Command: '+' '.join(command)+'\n'+result.stdout+result.stderr)
    print(outputs[-1],flush=True)
    if result.returncode:raise SystemExit(result.returncode)
cases=ET.parse(evidence/'M16-approval.xml').findall('.//testcase')
if len(cases)<151 or any(c.find(t) is not None for c in cases for t in ('failure','error','skipped')):
    raise SystemExit('Incomplete approval test evidence')
example=json.loads((evidence/'M16-approval-backend-example.json').read_text(encoding='utf-8'))
assert example['differences']['payload']['counts']=={'NEWLY_SCHEDULED':1,'UNCHANGED':2}
assert example['validation']['status']=='PASS' and example['validation']['usable_for_review']
assert example['controller_decision']['scope']=='SIMULATED'
assert example['controller_decision']['result']['replacement']['difference_hash']==example['differences']['content_hash']
assert example['old_active_reservations']==0 and example['new_active_reservations']==2
assert example['operational_reservation_count']==0
assert example['controller_decision']['result']['operational_reservation_written'] is False
sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend','migrations','tests','scripts') for p in (root/folder).rglob('*.py')}
(evidence/'M16-approval-sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
(evidence/'M16-approval-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
print(f'{len(cases)} cumulative tests and replacement backend output verified; full M16 gate remains open.')
