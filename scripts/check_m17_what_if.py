"""Record the M17 what-if acceptance output and cumulative PostgreSQL gate."""
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
    'RAILSYNC_M17_EVIDENCE_OUTPUT': str(evidence / 'M17-backend-example.json')}
commands = [[sys.executable, '-m', 'alembic', 'upgrade', 'head'],
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
        f'--junitxml={evidence}/M17.xml']]
outputs = []
for command in commands:
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    output = 'Command: ' + ' '.join(command) + '\n' + result.stdout + result.stderr
    outputs.append(output)
    print(output, flush=True)
    if result.returncode:
        (evidence / 'M17-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
        raise SystemExit(result.returncode)
cases = ET.parse(evidence / 'M17.xml').findall('.//testcase')
if len(cases) < 168 or any(c.find(t) is not None for c in cases
        for t in ('failure', 'error', 'skipped')):
    raise SystemExit('Incomplete cumulative M17 gate')
example = json.loads((evidence / 'M17-backend-example.json').read_text(encoding='utf-8'))
assert example['scenario']['approval_permitted'] is False
assert example['scenario']['baseline_run']['status'] == 'COMPLETED'
assert example['scenario']['optimized_run']['status'] == 'COMPLETED'
assert example['optimized_run']['result']['has_incumbent']
assert example['validation']['status'] == 'PASS'
assert example['comparison']['content']['claim_scope'] == 'ISOLATED_SIMULATION_ONLY'
assert example['impact']['content']['comparison_type'] == 'INPUT_CHANGED_SCENARIO_IMPACT'
assert example['impact']['content']['claims_permitted'] is False
assert 'INPUTS_DIFFER_SO_DELTAS_ARE_NOT_OPTIMIZER_GAINS' in example['impact']['content']['limits']
assert example['approval_blocked']['detail'] == 'SCENARIO_DECISION_FORBIDDEN'
assert example['source_occupancy']['enter_at'] != example['scenario_occupancy']['enter_at']
sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend', 'migrations', 'tests', 'scripts')
    for p in (root / folder).rglob('*.py')}
(evidence / 'M17-sources.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
(evidence / 'M17-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
print(f'{len(cases)} cumulative tests and actual isolated scenario output verified.')
