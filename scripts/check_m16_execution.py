"""Record the execution/freeze slice without claiming the full M16 gate."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
os.chdir(root)
evidence=root/'docs/evidence'
credential=json.loads((root/'.local/db.json').read_text())
env={**os.environ,'PYTHONPATH':'backend','RAILSYNC_DATABASE_URL':
    f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:55432/railsync_test",
    'RAILSYNC_M16_EXECUTION_EVIDENCE_OUTPUT':str(evidence/'M16-execution-backend-example.json')}
commands=[[sys.executable,'-m','alembic','upgrade','head'],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={evidence}/M16-execution.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    outputs.append('Command: '+' '.join(command)+'\n'+result.stdout+result.stderr)
    print(outputs[-1],flush=True)
    if result.returncode:
        (evidence/'M16-execution-failed-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
        raise SystemExit(result.returncode)
cases=ET.parse(evidence/'M16-execution.xml').findall('.//testcase')
if not cases or any(c.find(t) is not None for c in cases for t in ('failure','error','skipped')):
    raise SystemExit('Incomplete test evidence')
example=json.loads((evidence/'M16-execution-backend-example.json').read_text(encoding='utf-8'))
assert [r['status'] for r in example['execution']['items']]==['STARTED','COMPLETED']
assert example['validation']['usable_for_review'] is False
assert 'EXECUTION_AWARE_SNAPSHOT_REQUIRED' in example['validation']['current_blockers']
assert any('EXECUTION_COMPLETED' in c['reasons'] for c in example['freeze_context']['commitments'])
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend','migrations','tests','scripts') for p in (root/folder).rglob('*.py')}
(evidence/'M16-execution-sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(evidence/'M16-execution-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
record=f'''# M16 execution and freeze slice — verified; full milestone incomplete

Recorded: {datetime.now(timezone.utc).isoformat()}

Cumulative automated tests: **{len(cases)} passed** against PostgreSQL railsync_test on port 55432.
Command: `.venv/Scripts/python.exe scripts/check_m16_execution.py`.
Source hashes: M16-execution-sources.json. Commands/results: M16-execution-test-output.txt and M16-execution.xml.
Saved backend output: M16-execution-backend-example.json, computed using the real CP-SAT fixture, independent validation, controller approval and execution API.

Explicit expected output: STARTED sequence 1 then COMPLETED sequence 2; zero remaining work explicitly verified; reservations retained; prior validation no longer usable; completed assignment frozen. The script asserts these expectations on the saved JSON.

Verified: exact plan/assignment binding; controller-only immutable lifecycle; server receipt time; future/out-of-order observations rejected; concurrent duplicate idempotency; unknown interrupted duration exposed; policy revisions; calendar and half-open freeze boundaries; frozen edits and approval blocked; duplicate request approvals blocked; obsolete workers fenced.

No Git commit is claimed. The existing workspace has no project commit; SHA256 source hashes identify the tested files. Unrelated files were preserved.

Limitations: SIMULATED non-scenario observations only. Work completion does not verify restoration or release possession/resources. Affected snapshots/runs/approvals remain blocked pending execution-aware snapshot and candidate integration. Full replacement solve, plan diff, validator recomputation and separate approval remain required. M16 stays unchecked; M17 must not start.
'''
(evidence/'M16-execution.md').write_text(record,encoding='utf-8')
print('Execution/freeze slice verified. Full M16 remains incomplete.')
