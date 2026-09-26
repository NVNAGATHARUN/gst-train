# M18 Access & System Health Administration — technical progress

**Date:** 2026-09-25  
**Scope:** SIMULATED RailSync prototype; M18 release gate remains open.

## Implemented

- Migration 026 persists worker start, last-seen and stopped timestamps. The durable planning worker writes a separate five-second heartbeat while processing jobs. A failed database write cannot create a false healthy status.
- `GET /api/v1/admin/system` requires ADMIN. It reports API/database response, migration head, observed active worker age and count, real preparation/run queue counts, a read-only role roster without credentials or hashes, and the current authentication mode/expiry.
- An active heartbeat older than 15 seconds is STALE; no active heartbeat is ABSENT. Either case degrades overall status even when API and PostgreSQL respond. This is process reachability evidence, not a guarantee of job completion or railway authority.
- The `/system` page uses the existing shell and browser API client. It renders actual returned values, loading/API-error states and an administrator boundary. Navigation is shown only to ADMIN. Credential provisioning remains external.

## Automated evidence

Command: `RAILSYNC_TEST_PORT=55440; powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1 -q -p no:cacheprovider tests/test_m18_system.py tests/test_m18_sessions.py tests/test_m18_planning_sessions.py`  
Result: **30 passed, 2 upstream deprecation warnings**, in 11.55 seconds against isolated PostgreSQL with migration 026.

Assertions cover role denial, ADMIN bearer and browser-session access, absent/responsive/stale/stopped worker states, migration revision 026, queue fields and exclusion of credentials, hashes and CSRF secrets. Expected backend examples: absent worker -> `status=DEGRADED`, `worker.status=ABSENT`; fresh heartbeat -> `status=READY`, `worker.status=RESPONSIVE`; stale heartbeat -> `status=DEGRADED`, `worker.status=STALE`.

Frontend: `npx tsc --noEmit --incremental false` passed; `npm run lint` passed. The nonincremental TypeScript command avoids this host's existing `tsconfig.tsbuildinfo` write restriction. A new production build and browser visual sign-off were not completed for this slice; prior M18 builds reached successful source compilation and then failed on this host at `spawn EPERM`.

## Remaining gate

Review the `/system` page in a working browser at 1440px and 1920px, including ADMIN and non-ADMIN roles and a stopped worker. Then complete M18-wide browser, deployment/recovery, benchmark and cumulative evidence gates. Do not mark M18 complete from these focused results.
