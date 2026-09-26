# M18 deployment and recovery — technical progress

**Date:** 2026-09-25  
**Status:** package implemented and statically tested; live container/recovery gate OPEN.

## Implemented

- Locked, pinned multi-stage backend image for FastAPI, Alembic and the durable worker.
- Locked, pinned Next.js standalone image with non-root runtime.
- Full Compose stack: PostgreSQL, one-shot migration, API, worker and web.
- Health ordering: database to migration to API/worker to web.
- Internal service network; PostgreSQL/API/worker are not published. The frontend binds to loopback by default for external TLS termination.
- Read-only application filesystems, tmpfs scratch space and no-new-privileges.
- Persisted worker-heartbeat container probe.
- Custom-format PostgreSQL backup with SHA-256 sidecar.
- Recovery profile with a separate database identity and volume; restore refuses checksum mismatch and non-empty targets.

## Automated evidence

On a fresh isolated PostgreSQL cluster at port 55441:

    RAILSYNC_TEST_PORT=55441; scripts/test.ps1 -q -p no:cacheprovider tests/test_m18_deployment.py tests/test_m18_system.py

Result: **8 passed**, with two upstream TestClient deprecation warnings, in 3.14 seconds. The tests cover production HTTPS/cookie validation, fresh/stale worker probes, complete service/startup declarations, database isolation, pinned non-root images, locked installs, standalone frontend output and checksum-bound isolated restore semantics.

Both PowerShell operational scripts parsed successfully with the PowerShell language parser. Frontend TypeScript and targeted ESLint were already passing after the preceding status-semantic fix.

## Unverified boundary

Docker is not installed on this host. Therefore image builds, Compose configuration, container health, HTTPS behavior, backup creation and isolated restore have not been run. These boxes stay open until executed on a Docker-capable host. The existing local Next.js spawn restriction also leaves browser acceptance open.
