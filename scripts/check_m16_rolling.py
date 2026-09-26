"""Run and save the complete M16 PostgreSQL gate and an actual backend example."""
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
port = int(os.environ.get('RAILSYNC_TEST_PORT', '55432'))
credential = json.loads((root / '.local/db.json').read_text())
env = {**os.environ, 'PYTHONPATH': 'backend',
    'RAILSYNC_DATABASE_URL': f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:{port}/railsync_test",
    'RAILSYNC_M16_ROLLING_EVIDENCE_OUTPUT': str(evidence / 'M16-rolling-backend-example.json')}
commands = [[sys.executable, '-m', 'alembic', 'upgrade', 'head'],
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        f'--junitxml={evidence}/M16-rolling.xml']]
outputs = []
for command in commands:
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    output = 'Command: ' + ' '.join(command) + '\n' + result.stdout + result.stderr
    outputs.append(output)
    print(output, flush=True)
    if result.returncode:
        (evidence / 'M16-rolling-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
        raise SystemExit(result.returncode)
cases = ET.parse(evidence / 'M16-rolling.xml').findall('.//testcase')
if len(cases) < 162 or any(c.find(t) is not None for c in cases
        for t in ('failure', 'error', 'skipped')):
    raise SystemExit('Incomplete cumulative M16 gate')
example = json.loads((evidence / 'M16-rolling-backend-example.json').read_text(encoding='utf-8'))
assert example['preview']['status'] == 'READY'
assert example['preview']['events'][0]['status'] == 'RECONCILED'
assert example['reconciliation']['payload']['controller_approval'] == 'REQUIRED'
assert example['optimized_run']['result']['has_incumbent']
assert example['urgent_request_id'] in {request for assignment in
    example['optimized_run']['result']['assignments'] for request in assignment['request_ids']}
assert example['validation']['status'] == 'PASS'
assert example['replacement_decision']['action'] == 'APPROVE'
assert example['replacement_decision']['result']['operational_reservation_written'] is False
sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend', 'migrations', 'tests', 'scripts')
    for p in (root / folder).rglob('*.py')}
(evidence / 'M16-rolling-sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
(evidence / 'M16-rolling-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
print(f'{len(cases)} cumulative tests and actual rolling replacement output verified.')
