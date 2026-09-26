"""Record compatibility demo variants and repeatable solver benchmarks."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
evidence = root / 'docs/evidence'
credential = json.loads((root / '.local/db.json').read_text())
port = int(os.environ.get('RAILSYNC_TEST_PORT', '55432'))
env = {**os.environ, 'PYTHONPATH': 'backend',
    'RAILSYNC_DATABASE_URL': f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:{port}/railsync_test",
    'RAILSYNC_M18_DEMO_BUNDLE_OUTPUT': str(evidence / 'M18-demo-bundle.json'),
    'RAILSYNC_M18_DEMO_DISABLED_OUTPUT': str(evidence / 'M18-demo-compatibility-disabled.json'),
    'RAILSYNC_M18_BENCHMARK_OUTPUT': str(evidence / 'M18-benchmark-results.json')}
commands = [
    [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
    [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
     'tests/test_m10.py::test_parallel_exact_backend_output_persistence_and_snapshot_isolation',
     'tests/test_m10.py::test_unknown_compatibility_keeps_singles_and_rejects_bundle',
     'tests/test_m18_benchmark.py']]
outputs = []
for command in commands:
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    outputs.append('Command: ' + ' '.join(command) + '\n' + result.stdout + result.stderr)
    if result.returncode:
        (evidence / 'M18-benchmark-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
        raise SystemExit(result.returncode)
bundle = json.loads((evidence / 'M18-demo-bundle.json').read_text())
disabled = json.loads((evidence / 'M18-demo-compatibility-disabled.json').read_text())
benchmarks = json.loads((evidence / 'M18-benchmark-results.json').read_text())
candidate = bundle['verified_candidate']
assert len(candidate['request_ids']) == 2
assert disabled['bundle_count'] == 0
assert [row['request_count'] for row in benchmarks['results']] == [20, 100, 300]
assert all(row['cp_sat']['status'] in ('OPTIMAL', 'FEASIBLE') for row in benchmarks['results'])
(evidence / 'M18-benchmark-test-output.txt').write_text('\n'.join(outputs), encoding='utf-8')
print('Verified real compatibility variants and 20/100/300-request solver benchmarks.')
