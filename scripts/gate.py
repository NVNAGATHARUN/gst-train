"""Run the cumulative automated gate and record verifiable evidence; never mark on failure."""
from pathlib import Path
import sys,subprocess,os,json,hashlib,datetime,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
milestone=int(sys.argv[1]);description=sys.argv[2]
if not 1 <= milestone <= 19:raise SystemExit('Invalid milestone')
check=ROOT/'CHECKLIST.md'
check_text=check.read_text(encoding='utf-8')
if not (ROOT/f'tests/test_m{milestone:02}.py').exists():raise SystemExit('Milestone tests missing')
if milestone>1:
    if f'- [x] M{milestone-1} ' not in check_text or not (ROOT/f'docs/evidence/M{milestone-1:02}.md').exists():
        raise SystemExit('Previous milestone gate has not passed')
evidence=ROOT/'docs/evidence';evidence.mkdir(parents=True,exist_ok=True)
credential=json.loads((ROOT/'.local/db.json').read_text())
test_port=int(os.environ.get('RAILSYNC_TEST_PORT','55432'))
env={**os.environ,'PYTHONPATH':'backend','RAILSYNC_DATABASE_URL':f"postgresql+psycopg://railsync:{credential['password']}@127.0.0.1:{test_port}/railsync_test"}
if milestone==10:
    example=evidence/'M10-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_EVIDENCE_OUTPUT']=str(example)
if milestone==11:
    example=evidence/'M11-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_M11_EVIDENCE_OUTPUT']=str(example)
if milestone==12:
    example=evidence/'M12-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_M12_EVIDENCE_OUTPUT']=str(example)
if milestone==13:
    example=evidence/'M13-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_M13_EVIDENCE_OUTPUT']=str(example)
if milestone==14:
    example=evidence/'M14-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_M14_EVIDENCE_OUTPUT']=str(example)
if milestone==15:
    example=evidence/'M15-backend-example.json'
    example.unlink(missing_ok=True)
    env['RAILSYNC_M15_EVIDENCE_OUTPUT']=str(example)
commands=[[sys.executable,'-m','alembic','upgrade','head'],[sys.executable,'-m','pytest','-q','-p','no:cacheprovider',f'--junitxml={evidence}/M{milestone:02}.xml']]
outputs=[]
for command in commands:
    result=subprocess.run(command,env=env,capture_output=True,text=True);outputs.append(result.stdout+result.stderr)
    print(result.stdout,result.stderr)
    if result.returncode:
        (evidence/f'M{milestone:02}-failed-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
        raise SystemExit(result.returncode)
suite=ET.parse(evidence/f'M{milestone:02}.xml')
cases=suite.findall('.//testcase')
if not cases or any(c.find('failure') is not None or c.find('error') is not None or c.find('skipped') is not None for c in cases):
    raise SystemExit('Gate requires executed, passing tests; empty/skipped/error evidence is not accepted')
if milestone in [10,11,12,13,14,15] and not example.exists():raise SystemExit('Verified persisted backend example missing')
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['backend','tests','migrations','scripts'] for p in (ROOT/folder).rglob('*.py')}
for name in ['pyproject.toml','uv.lock','compose.yaml','alembic.ini','.github/workflows/test.yml']:
    manifest[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
source_hash=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
(evidence/f'M{milestone:02}-sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(evidence/f'M{milestone:02}-test-output.txt').write_text('\n'.join(outputs),encoding='utf-8')
commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True)
record=f'''# M{milestone:02} — automated and backend-output gate passed

Recorded: {datetime.datetime.now(datetime.timezone.utc).isoformat()}

{description}

Verification: real PostgreSQL on localhost:{test_port}, migrations, and cumulative pytest assertions (including persisted API values), as recorded in M{milestone:02}.xml and M{milestone:02}-test-output.txt. Tests failed earlier are corrected before this record is written.

Commands: `.venv/Scripts/python.exe -m alembic upgrade head`; `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --junitxml=docs/evidence/M{milestone:02}.xml` using the dedicated railsync_test database.

Source manifest SHA-256: {source_hash}

Commit: {commit.stdout.strip() if commit.returncode==0 else 'UNAVAILABLE — host denies .git writes despite approved filesystem grant. No commit claimed; source manifest preserves exact evidence.'}

Scope: prototype only. No live integration or operational certification. UI and later milestones are not implied by this gate.
'''
(evidence/f'M{milestone:02}.md').write_text(record,encoding='utf-8')
text=check.read_text(encoding='utf-8');import re
text=re.sub(r' \*\*\(in progress\)\*\*','',text)
text=re.sub(rf'- \[ \] M{milestone}\b',f'- [x] M{milestone}',text)
text=re.sub(r'Status: .*? A checkbox',f'Status: M1–M{milestone} backend gates passed; M{milestone+1} next. Git commits remain blocked by host permissions. A checkbox',text)
check.write_text(text,encoding='utf-8')
print(f'M{milestone:02} evidence saved; checklist updated.')
