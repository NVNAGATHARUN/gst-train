"""Record actual M16 continuation output and the cumulative PostgreSQL gate."""
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
    'RAILSYNC_M16_CONTINUATION_EVIDENCE_OUTPUT':str(evidence/'M16-continuation-preserved.json'),
    'RAILSYNC_M16_CONTINUATION_RESIDUAL_EVIDENCE_OUTPUT':str(evidence/'M16-continuation-residual.json')}
commands=[[sys.executable,'-m','alembic','upgrade','head'],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
        f'--junitxml={evidence}/M16-continuation.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    outputs.append('Command: '+' '.join(command)+'\n'+result.stdout+result.stderr)
    print(outputs[-1],flush=True)
    if result.returncode:raise SystemExit(result.returncode)
cases=ET.parse(evidence/'M16-continuation.xml').findall('.//testcase')
if len(cases)<155 or any(c.find(t) is not None for c in cases for t in ('failure','error','skipped')):
    raise SystemExit('Incomplete continuation test evidence')
preserved=json.loads((evidence/'M16-continuation-preserved.json').read_text(encoding='utf-8'))
residual=json.loads((evidence/'M16-continuation-residual.json').read_text(encoding='utf-8'))
assert preserved['observation']['status']=='COMPLETED'
assert preserved['observation']['result']['continuation']['kind']=='PRESERVED_ASSIGNMENT'
assert preserved['observation']['result']['continuation']['source_decision_id']==preserved['captured_source_decision_id']
assert preserved['observation']['result']['execution_authorized'] is False
assert residual['resumed_observation']['status']=='RESUMED'
assert residual['resumed_observation']['payload']['remaining_work_minutes']==40
assert residual['resumed_observation']['result']['continuation']['kind']=='VERIFIED_RESIDUAL_RESTART'
assert residual['completed_observation']['status']=='COMPLETED'
assert residual['restoration_release']['result']['reservation_released'] is True
assert residual['restoration_release']['result']['scope']=='SIMULATED'
sources={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend','migrations','tests','scripts') for p in (root/folder).rglob('*.py')}
(evidence/'M16-continuation-sources.json').write_text(json.dumps(sources,indent=2),encoding='utf-8')
(evidence/'M16-continuation-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
print(f'{len(cases)} cumulative tests and both continuation outputs verified; full M16 gate remains open.')
