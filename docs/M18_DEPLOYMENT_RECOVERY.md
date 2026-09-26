# M18 deployment and recovery

This package runs the RailSync decision-support prototype as one Docker Compose application. It does not provide railway operating authority and must not be presented as a live train-control deployment.

## Services and startup order

1. The db service starts PostgreSQL 17 with a persistent volume and no published database port.
2. The migration service waits for PostgreSQL, runs Alembic upgrade head, and must finish successfully.
3. API and worker start from the same locked Python image only after migration succeeds.
4. Web starts only after the API readiness check succeeds. It is published on loopback by default for a host TLS reverse proxy.
5. Restore-db exists only under the recovery profile and uses a separate user, database and volume.

The API and worker containers use a read-only root filesystem, tmpfs scratch space, a non-root user and no-new-privileges. The frontend uses a non-root Next.js standalone image. The internal Compose network prevents direct external access to PostgreSQL, API and worker.

## Configuration and startup

Docker and Compose are prerequisites. Copy deployment/.env.example to a secure file outside source control, replace both database secrets, and set RAILSYNC_BROWSER_ORIGINS to the exact public HTTPS origin.

Run from the repository root:

    docker compose --env-file deployment/.env.production config
    docker compose --env-file deployment/.env.production build
    docker compose --env-file deployment/.env.production up -d
    docker compose --env-file deployment/.env.production ps

Keep RAILSYNC_PUBLIC_BIND set to 127.0.0.1. Terminate TLS in a host reverse proxy and forward to that loopback port. Production configuration rejects HTTP origins and insecure session cookies. If the API container address changes, rebuild the web image because its same-origin API rewrite is part of the standalone build.

Readiness signals are intentionally distinct:

- API health: process response only.
- API ready: PostgreSQL and migration-table access.
- Worker health: a current persisted heartbeat; stale or absent heartbeat fails.
- ADMIN System Health: API/database/worker/queue evidence for operators.

## Backup

The backup helper creates a PostgreSQL custom-format dump and a SHA-256 sidecar without writing database credentials to the command line:

    powershell -File scripts/backup.ps1 -DestinationDirectory D:\RailSyncBackups

Store the dump, checksum and protected deployment secrets in access-controlled storage. A backup has not been proven until its checksum is verified and it restores successfully.

## Isolated restore verification

Set a separate RESTORE_POSTGRES_PASSWORD in the environment file, then run:

    powershell -File scripts/restore_verify.ps1 -BackupFile D:\RailSyncBackups\railsync-YYYYMMDDTHHMMSSZ.dump

The helper verifies the SHA-256 file, starts the recovery profile, refuses a non-empty target, restores only into railsync_restore on the separate railsync_restore_pg volume, and reads the restored Alembic revision and table count. It never targets the operational railsync database and does not use a destructive clean restore.

For a repeat exercise, use a new recovery volume through an explicit, reviewed operational procedure. Do not delete or replace the operational volume as part of a restore test.

## Acceptance boundary

Before the deployment checkbox can be closed:

- run Compose configuration validation, build and startup on a host with Docker;
- verify every health state and the browser session through HTTPS;
- create a backup and complete an isolated restore;
- inspect restored snapshots, revisions, validation reports, controller decisions, execution/audit records and exports;
- save exact image identifiers, source hash, commands, outputs and known limits.

This repository currently has static and automated configuration evidence. The present Windows host has no Docker installation, so no container build, startup, backup or restore success is claimed.
