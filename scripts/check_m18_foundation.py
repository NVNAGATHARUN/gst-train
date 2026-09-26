"""Record the M18 foundation slice; this does NOT mark M18 or a hero complete."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
os.chdir(root)
evidence = root / 'docs/evidence'
port = int(os.environ.get('RAILSYNC_TEST_PORT', '55435'))
credential = json.loads((root / '.local/db.json').read_text())
env = {**os.environ, 'PYTHONPATH': 'backend',
    'RAILSYNC_DATABASE_URL': f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:{port}/railsync_test?connect_timeout=5",
    'RAILSYNC_M18_SESSION_EVIDENCE_OUTPUT': str(evidence / 'M18-session-example.json'),
    'RAILSYNC_M18_WORKSPACE_EVIDENCE_OUTPUT': str(evidence / 'M18-workspace-example.json'),
    'RAILSYNC_M18_PLANNING_EVIDENCE_OUTPUT': str(evidence / 'M18-planning-session-example.json')}
commands = [[sys.executable, '-m', 'alembic', 'upgrade', 'head'],
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        f'--junitxml={evidence}/M18-foundation.xml']]
outputs = []
for command in commands:
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    output = 'Command: ' + ' '.join(command) + '\n' + result.stdout + result.stderr
    outputs.append(output)
    print(output, flush=True)
    (evidence / 'M18-foundation-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
    if result.returncode: raise SystemExit(result.returncode)
cases = ET.parse(evidence / 'M18-foundation.xml').findall('.//testcase')
if len(cases) < 202 or any(c.find(t) is not None for c in cases for t in ('failure', 'error', 'skipped')):
    raise SystemExit('Incomplete cumulative M18 foundation gate')
session = json.loads((evidence / 'M18-session-example.json').read_text(encoding='utf-8'))
workspace = json.loads((evidence / 'M18-workspace-example.json').read_text(encoding='utf-8'))
planning = json.loads((evidence / 'M18-planning-session-example.json').read_text(encoding='utf-8'))
assert session['plaintext_session_stored'] is False and session['revoked_session_read_status'] == 401
assert session['csrf_denial']['detail'] == 'CSRF_TOKEN_INVALID'
assert workspace['workspace']['validation']['usable_for_review']
assert workspace['workspace']['validation']['status'] == 'PASS'
assert workspace['stale_blockers']
assert all(r['status'] != 'READY' for r in workspace['stale_readiness'])
assert planning['queued']['runs'] == []
assert planning['prepared']['status'] == 'QUEUED_SOLVE'
assert planning['completed']['status'] == 'COMPLETED'
assert planning['completed']['validation'] == 'SEPARATE_REQUIRED_STEP'
assert planning['optimized_result']['has_incumbent'] and planning['optimized_result']['assignments']
sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend', 'migrations', 'tests', 'scripts')
    for p in (root / folder).rglob('*.py')}
(evidence / 'M18-foundation-sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
print(f'{len(cases)} cumulative tests plus persisted M18 foundation examples verified. M18 remains in progress.')
