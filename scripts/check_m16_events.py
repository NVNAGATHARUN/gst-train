"""Run and record the M16 event slice without marking the whole milestone complete."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone

root=Path(__file__).resolve().parents[1]
os.chdir(root)
evidence=root/'docs/evidence'
credential=json.loads((root/'.local/db.json').read_text())
env={**os.environ,'PYTHONPATH':'backend','RAILSYNC_DATABASE_URL':
    f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:55432/railsync_test",
    'RAILSYNC_M14_EVIDENCE_OUTPUT':str(evidence/'M14-backend-example.json'),
    'RAILSYNC_M15_EVIDENCE_OUTPUT':str(evidence/'M15-backend-example.json'),
    'RAILSYNC_M16_EVENTS_EVIDENCE_OUTPUT':str(evidence/'M16-events-backend-example.json')}
commands=[[sys.executable,'-m','alembic','upgrade','head'],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={evidence}/M16-events.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    outputs.append(result.stdout+result.stderr)
    print(outputs[-1],flush=True)
    if result.returncode:
        (evidence/'M16-events-failed-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
        raise SystemExit(result.returncode)
import xml.etree.ElementTree as ET
cases=ET.parse(evidence/'M16-events.xml').findall('.//testcase')
if not cases or any(c.find(t) is not None for c in cases for t in ('failure','error','skipped')):
    raise SystemExit('Incomplete test evidence')
example=json.loads((evidence/'M16-events-backend-example.json').read_text(encoding='utf-8'))
assert example['plan_state']['status']=='STALE_REQUIRES_ATTENTION'
assert example['validation']['usable_for_review'] is False
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend','migrations','tests','scripts') for p in (root/folder).rglob('*.py')}
(evidence/'M16-events-sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(evidence/'M16-events-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
record=f'''# M16 event intake slice - verified, full milestone incomplete

Recorded: {datetime.now(timezone.utc).isoformat()}

Cumulative automated tests: {len(cases)} passed against PostgreSQL railsync_test on port 55432.
Command: `.venv/Scripts/python.exe scripts/check_m16_events.py`.
Exact source hashes: M16-events-sources.json. Test commands and results: M16-events-test-output.txt and M16-events.xml.
Backend evidence: M16-events-backend-example.json. M14 and M15 examples were refreshed from executed tests.

No source commit is claimed; this workspace has no recorded project commit. The source manifest identifies tested files.

Verified: event identity/immutability, concurrent duplicate delivery, debounce generations, old snapshot invalidation, approval blocking, reservation preservation and late-worker publication rejection. M15 percentage/union repairs and real M14 full-horizon solver tests are included.

M16 remains unchecked. Frozen/executed work, automatic fresh-state replanning, replacement diff and independent replacement validation/approval are still required. See M16_REPLANNING_STATUS.md.
'''
(evidence/'M16-events.md').write_text(record,encoding='utf-8')
print('Event slice verified; full M16 checklist intentionally remains incomplete.')
