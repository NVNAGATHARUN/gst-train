"""Start a project-local PostgreSQL instance; no system service or existing DB changes."""
import os, subprocess, pathlib, secrets, json, sys, time
import psycopg
ROOT=pathlib.Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local';LOCAL.mkdir(exist_ok=True)
BIN=ROOT/'.tools/pgsql/bin';DATA=LOCAL/'pgdata'
PORT=int(os.environ.get('RAILSYNC_LOCAL_DB_PORT','55432'))
if not 1024<=PORT<=65535:raise ValueError('Invalid local PostgreSQL port')
credentials=LOCAL/'db.json'
if credentials.exists():password=json.loads(credentials.read_text())['password']
else:
    password=secrets.token_urlsafe(32)
    credentials.write_text(json.dumps({'password':password}))
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
def run(name,*args,check=True):
    return subprocess.run([str(BIN/name),*map(str,args)],check=check,creationflags=flags,capture_output=True,text=True)
if not (DATA/'PG_VERSION').exists():
    pw=LOCAL/'init-password';pw.write_text(password)
    try:
        r=run('initdb.exe','-D',DATA,'-U','railsync','--pwfile',pw,'--auth=scram-sha-256','--encoding=UTF8','--locale=C')
        print(r.stdout)
    except subprocess.CalledProcessError as e:
        print(e.stdout,e.stderr);raise
    finally:pw.unlink(missing_ok=True)
def connect():
    return psycopg.connect(host='127.0.0.1',port=PORT,user='railsync',password=password,dbname='postgres',autocommit=True,connect_timeout=2)
try:
    connect().close()
except psycopg.OperationalError as initial_error:
    if 'password authentication failed' in str(initial_error):raise
    # A recovering server must not trigger a second postmaster on the same cluster.
    readiness=run('pg_isready.exe','-h','127.0.0.1','-p',str(PORT),check=False)
    process=None
    if readiness.returncode==2:
        log=(LOCAL/'postgres.log').open('ab')
        process=subprocess.Popen([str(BIN/'postgres.exe'),'-D',str(DATA),'-p',str(PORT),'-h','127.0.0.1'],stdout=log,stderr=log,creationflags=flags)
    elif readiness.returncode not in [0,1]:raise RuntimeError('PostgreSQL readiness probe failed')
    for attempt in range(120):
        time.sleep(.5)
        try:connect().close();break
        except psycopg.OperationalError:
            if process is not None and process.poll() is not None:raise RuntimeError('PostgreSQL exited; inspect .local/postgres.log')
    else:raise RuntimeError('PostgreSQL did not become ready')
with psycopg.connect(host='127.0.0.1',port=PORT,user='railsync',password=password,dbname='postgres',autocommit=True) as conn:
    for name in ['railsync','railsync_test']:
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():conn.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
    print(conn.execute('SELECT version()').fetchone()[0])
(ROOT/'.env').write_text(f'RAILSYNC_DATABASE_URL=postgresql+psycopg://railsync:{password}@127.0.0.1:{PORT}/railsync\n')
print(f'Development and test databases ready on localhost:{PORT}. Credentials kept in ignored local files.')
