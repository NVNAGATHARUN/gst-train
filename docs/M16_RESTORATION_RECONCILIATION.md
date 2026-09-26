# M16 — remaining work and verified restoration

This slice supports an interrupted task after the original shared possession is explicitly restored and released. It also handles a completed bundle without scheduling its completed requests again. All observations and releases are **SIMULATED, software-only**; no railway control command or operational reservation is issued or released.

## Explicit workflow

1. Record STARTED followed by INTERRUPTED or COMPLETED observations through the existing execution API. Elapsed time never supplies completion or remaining work.
2. For each interrupted request, a controller calls `POST /api/v1/work-reconciliations`. Supply the exact latest interruption ID, expected scoped state/request/assessment revisions, explicit remaining work minutes, restart setup and restoration minutes, earliest restart work time, verification and evidence reference.
3. The assessment is append-only and versioned. Unknown remaining work can be supplied explicitly. If the interruption already declared a known remaining amount, conflicting assessment values are rejected. More work than the source request permits needs a revised request. Restart setup/restoration values are explicit synthetic domain inputs, not inferred savings. Deadlines, mandatory status, footprint, resource requirements and predecessor relationships are preserved.
4. After every member of the bundle is COMPLETED or INTERRUPTED with a current assessment, the controller calls `POST /api/v1/possession-releases`. Supply exact approval/assignment hashes, all current execution IDs, all required assessment IDs, observed possession start, restoration start/end, and explicit track/electrical/signalling/resource-clear attestations.
5. The backend verifies the entire bundle. Restoration cannot precede the terminal observations, be in the future, or be shorter than the largest configured restoration stage in that assignment. The actual possession start must cover recorded execution. The observed times may differ from planned times; they remain explicit history.
6. The release record, scoped state increment, audit record and deactivation of the **single exactly matched reservation** commit together. A repeated identical release returns the saved record; concurrent deliveries release once. Other reservations remain unchanged. A new assessment or execution observation cannot modify that closed possession.
7. Create a new replanning capture and snapshot. Released assignments become history rather than frozen candidates. Completed requests leave pending demand. Interrupted requests become derived residual requirements, retaining their original request and assessment/release provenance. Their future work starts no earlier than the latest of the original earliest-work constraint, assessed restart time and verified restoration.
8. Generate availability/opportunities/candidates and run baseline or CP-SAT normally. The independent validator recomputes release evidence and residual requirements. Captured replacement approval uses the controlled-supersession workflow in M16_REPLACEMENT_APPROVAL.md; observations under the new approval use the source-bound handoff in M16_EXECUTION_CONTINUATION.md.

Read saved evidence with `GET /api/v1/work-reconciliations/{id}` and `GET /api/v1/possession-releases/{id}`. Mutation endpoints require CONTROLLER; authenticated auditors can read. Migration 019 protects both evidence tables from update/delete.

## Resource and track history

Release does not erase consumed time. Recorded possession intervals block track availability for that historical period. Every assigned named unit is conservatively charged for the full observed possession at its recorded location. This is labeled `FULL_OBSERVED_POSSESSION_CONSERVATIVE`; it does not claim per-worker telemetry or precisely measured activity.

Snapshots keep the unchanged source resource profile alongside the effective profile augmented with release duty history. Existing qualification, availability, travel, rest, pools and rolling 24-hour duty calculations operate on that effective history. The independent validator derives the same expected history from raw release facts using its own checks. Overlapping/contradictory source duty records remain fail-closed and require reconciliation, rather than silently deduplicating unproven records.

Restored and verified completed tasks may satisfy predecessor constraints. A completion with no verified restoration cannot satisfy that dependency or free a shared block.

## Evidence and supported limits

The hand-checkable fixture records completed TRD work, interrupted ENG work, explicit 40-minute ENG remaining work with five-minute restart setup/restoration, and a ten-minute restoration of the original shared possession. Actual baseline and CP-SAT pipelines each schedule one residual request, with independent PASS. Other tests verify resource rest/rolling-duty effects, obsolete assessments, missing/active bundle members, UTC timestamps, immutable evidence, concurrent duplicate release, and corrupted facts failing validation.

Verification command: set `RAILSYNC_TEST_PORT` to the running local test database port, then run `.venv/Scripts/python.exe scripts/check_m16_restoration.py`. Evidence is in `docs/evidence/M16-restoration.md` and its related JSON/XML files.

This slice does **not** authorize resuming work within an unreleased possession or moving a still-frozen task. RESUMED observations without a subsequent interruption/completion and verified closure remain blocked for replanning. The subsequent M16 slices add captured replacement differences, atomic simulated approval and source-bound continuation; see M16_REPLACEMENT_APPROVAL.md and M16_EXECUTION_CONTINUATION.md. Source-event reconciliation remains pending. M17 cannot start until the complete milestone gate passes.

## Local PostgreSQL port

The project-local launcher now accepts `RAILSYNC_LOCAL_DB_PORT` (default 55432). On this Windows session, 55432 could not be bound, so development and tests used 55433. Set `RAILSYNC_TEST_PORT=55433` for `scripts/test.ps1` and the restoration evidence script. The ignored `.env` points to the running development instance. No Windows networking settings were changed.
