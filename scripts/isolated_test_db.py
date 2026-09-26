"""Fresh, separate PostgreSQL test cluster. Never edits the existing development data."""
import json,os,pathlib,subprocess,sys,time
import psycopg

ROOT=pathlib.Path(__file__).resolve().parents[1]
BIN=ROOT/'.tools/pgsql/bin'
DATA=ROOT/os.environ.get('RAILSYNC_TEST_DATA','.local/m12-test-pgdata')
PORT=int(os.environ.get('RAILSYNC_TEST_PORT','55433'))
password=json.loads((ROOT/'.local/db.json').read_text())['password']
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
if not (DATA/'PG_VERSION').exists():
    pw=ROOT/'.local/m12-init-password'
    pw.write_text(password)
    try:
        result=subprocess.run([str(BIN/'initdb.exe'),'-D',str(DATA),'-U','railsync','--pwfile',str(pw),
            '--auth=scram-sha-256','--encoding=UTF8','--locale=C'],capture_output=True,text=True,creationflags=flags)
        if result.returncode:
            print(result.stdout,result.stderr)
            raise SystemExit(result.returncode)
    finally:pw.unlink(missing_ok=True)
    print('Initialized separate PostgreSQL test cluster.')
if '--serve' in sys.argv:
    raise SystemExit(subprocess.call([str(BIN/'postgres.exe'),'-D',str(DATA),'-p',str(PORT),'-h','127.0.0.1']))
with psycopg.connect(host='127.0.0.1',port=PORT,user='railsync',password=password,dbname='postgres',autocommit=True,connect_timeout=5) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname='railsync_test'").fetchone():
        conn.execute('CREATE DATABASE railsync_test')
print(f'Isolated railsync_test database ready on port {PORT}.')
