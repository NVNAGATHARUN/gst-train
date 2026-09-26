"""Execute cumulative tests and record this M16 slice; never check the full gate."""
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
    'RAILSYNC_M16_REPLANNING_EVIDENCE_OUTPUT':str(evidence/'M16-replanning-backend-example.json')}
commands=[[sys.executable,'-m','alembic','upgrade','head'],
    [sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={evidence}/M16-replanning.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True)
    outputs.append('Command: '+' '.join(command)+'\n'+result.stdout+result.stderr)
    print(outputs[-1],flush=True)
    if result.returncode:
        (evidence/'M16-replanning-failed-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
        raise SystemExit(result.returncode)
cases=ET.parse(evidence/'M16-replanning.xml').findall('.//testcase')
if not cases or any(c.find(t) is not None for c in cases for t in ('failure','error','skipped')):
    raise SystemExit('Incomplete test evidence')
example=json.loads((evidence/'M16-replanning-backend-example.json').read_text(encoding='utf-8'))
plan=example['optimized']['result'];baseline=example['baseline']['result']
assert plan['solver_status'] in ('OPTIMAL','FEASIBLE') and plan['has_incumbent']
assert plan['counts']['scheduled']==baseline['counts']['scheduled']==3
assert plan['objective_terms']['commitment_change']['raw']==0
assert example['validation']['status']=='PASS' and example['validation']['usable_for_review']
assert example['replacement_approval_blocked'] is True
by_id={a['id']:a for a in plan['assignments']}
for commitment in example['capture']['payload']['commitments']:
    assert commitment['frozen'] and by_id[commitment['candidate_id']]==commitment['assignment']
manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('backend','migrations','tests','scripts') for p in (root/folder).rglob('*.py')}
(evidence/'M16-replanning-sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(evidence/'M16-replanning-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
record=f'''# M16 execution-aware snapshot / replacement solver slice

Recorded: {datetime.now(timezone.utc).isoformat()}

**{len(cases)} cumulative tests passed** against PostgreSQL railsync_test on port 55432.
Command: `.venv/Scripts/python.exe scripts/check_m16_replanning.py`.
Detailed commands/results: M16-replanning-test-output.txt and M16-replanning.xml.
Tested file SHA256 hashes: M16-replanning-sources.json. No Git commit is claimed.

Backend example: M16-replanning-backend-example.json. It uses synthetic source data and real API, candidate, baseline, solver and validator code.
Verified expected output: two ongoing ENG/TRD tasks preserved exactly in their original shared block, a third urgent request scheduled in a separate feasible 15-minute block; 3 scheduled requests for both planners; zero frozen-commitment changes; real incumbent and independent PASS. The evidence script checks these saved values. Approval of this replacement is blocked pending the controlled replacement transaction.

Also verified: updated restriction/resource conflict excludes the frozen candidate and returns actual INFEASIBLE with no assignments; completed requests are excluded from pending demand but restoration remains unresolved; interruptions and missing duration stay blocked; new observations invalidate captures; immutable provenance; scope/role/hash/revision guards; corruption of freeze derivation, execution evidence, candidate identity or commitment coverage cannot pass validation. Time passing does not manufacture completion.

Limitations: unchanged observed STARTED work is supported; actual deviation, interrupted/resumed remaining work and completed possession restoration require explicit reconciliation. Source events do not automatically update operational facts. Capture uses a conservative scope-wide state version; other overlapping approved lineages require reconciliation. Replacement plan diff/lineage, atomic supersede approval and restoration/remaining-work handling still precede the full M16 gate. M16 remains unchecked and M17 must not start.
'''
(evidence/'M16-replanning.md').write_text(record,encoding='utf-8')
print('M16 snapshot/solver slice verified; full milestone remains incomplete.')
