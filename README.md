# R-MAPS

**Railway Maintenance Allocation & Planning System**

Fixed-infrastructure maintenance decision-support prototype for SIH 2026 PS26027. Follow [CHECKLIST.md](CHECKLIST.md) for verified progress. The PDFs are reference material, not evidence that software has been implemented.

## Development foundation

- Python 3.12, FastAPI/Pydantic, PostgreSQL 17 and Alembic.
- `uv sync --locked` installs the versions in `uv.lock`.
- Copy `.env.example` to `.env` and configure a dedicated database, or use the project-local Windows database below.
- `uv run alembic upgrade head` applies migrations.
- `uv run uvicorn railsync.main:app --app-dir backend --host 127.0.0.1 --port 8000` starts the API.
- Open `/docs` for the API contract. `/api/v1/health` checks the service; `/api/v1/ready` checks PostgreSQL/migrations.

## Project-local Windows database

PostgreSQL's official Windows download page links EDB's binary archives. Development setup uses PostgreSQL 17.11 binaries under `.tools/pgsql` and an isolated cluster under `.local/pgdata`, listening only on localhost:55432. No Windows service is installed. Run `.venv/Scripts/python.exe scripts/local_db.py` to initialize/start it. Random local credentials are saved in ignored files; never commit them.

`powershell -File scripts/test.ps1 -q` migrates and tests against the separate `railsync_test` database. Tests refuse to clear any other database. CI uses an isolated PostgreSQL service; it does not require the Windows binary archive.

If Windows blocks the default port, choose an available localhost port with `RAILSYNC_LOCAL_DB_PORT`. This development session uses 55433:

```powershell
$env:RAILSYNC_LOCAL_DB_PORT='55433'
.venv/Scripts/python.exe scripts/local_db.py
$env:RAILSYNC_TEST_PORT='55433'
powershell -File scripts/test.ps1 -q
```

The launcher writes the development URL to the ignored `.env`. The latest complete gate is `.venv/Scripts/python.exe scripts/check_m17_what_if.py`, using `RAILSYNC_TEST_PORT`. See [the M17 scenario API](docs/M17_WHAT_IF_SCENARIOS.md) and [verified evidence](docs/evidence/M17.md). M16 rolling documentation remains at [M16_ROLLING_REPLANNING_API.md](docs/M16_ROLLING_REPLANNING_API.md).

## M18 frontend and decision-support workspace

The Next.js app is in `web/`. Start the API on localhost:8000, configure `RAILSYNC_BROWSER_ORIGINS=["http://127.0.0.1:3000"]` and `RAILSYNC_SESSION_COOKIE_SECURE=false` for loopback HTTP development, then run `npm ci` and `npm run dev` from `web/`. Sign in with a provisioned role credential. The frontend proxies `/api/v1/*` to `RAILSYNC_API_ORIGIN` (default localhost:8000), so credentials remain in an HttpOnly browser session rather than browser storage. Use HTTPS and secure cookies outside local development.

The current UI includes role-specific dashboards and 15 work areas covering maintenance intake, planning, capacity, solver state, fair comparison, validation, controller review, schedules, replanning, execution, reports, readiness and administration. Run `npm run typecheck`, `npm run lint`, and `npm run build` for frontend checks. The latest typecheck and lint pass. This managed Windows host still blocks the final Next.js build child process with `spawn EPERM`; rerun the production build on a normal host before release. Browser captures exist for the hero screens, responsive/reflow views and five role workspaces; the remaining M18 acceptance gates are listed in [CHECKLIST.md](CHECKLIST.md).

## Integrity commitments

Synthetic inputs must be labeled. No live railway integration, train control, fake scores, canned optimizer outputs or guaranteed KPI improvements. Review/approval requires independent validation and freshness/concurrency gates. ML promotion requires evaluated data; rules remain an honest fallback.

## Container deployment and recovery

The M18 deployment package now defines PostgreSQL, one-shot migrations, FastAPI, the durable worker and the Next.js standalone frontend. Copy deployment/.env.example to a protected environment file and follow docs/M18_DEPLOYMENT_RECOVERY.md. The web port binds to loopback by default; production requires an HTTPS reverse proxy and an exact secure browser origin.

scripts/backup.ps1 produces a custom PostgreSQL dump with a SHA-256 sidecar. scripts/restore_verify.ps1 restores only into the isolated recovery-profile database and refuses a checksum mismatch or non-empty target. Docker is unavailable on the current Windows host, so the package has automated/static evidence but no live container, backup or restore claim yet.

## Benchmark and demonstration evidence

Run scripts/check_m18_benchmark.py against a fresh isolated test database to reproduce the compatibility-on/off artifacts and 20/100/300-request fixed-candidate solver benchmarks. The exact results and limits are documented in docs/M18_BENCHMARK_DEMO.md. These SIMULATED results are software measurements, not railway delay, reliability or field-safety claims.

## Reference sources

- [R-MAPS Final SRS and Build Contract](docs/R-MAPS_FINAL_SRS_BUILD_CONTRACT.md) is the current implementation baseline. The repository also includes the matching DOCX and PDF editions.
- `RailSync_AI_Solution_SRS_Build_Contract.pdf` and `RailSync_AI_SRS.pdf` are superseded historical design references retained under their original filenames.
- [Official PostgreSQL Windows distribution information](https://www.postgresql.org/download/windows/).
