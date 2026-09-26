# M18 Network, Resource & Policy Administration — progress evidence

Recorded: 2026-09-25. This is one M18 technical slice, not the complete M18 gate.

## Implemented

- Added `/admin` for the current network register: station, section, track, asset, isolation and restriction records. Selecting an entity shows its real saved data and current revision. A save sends that revision to the existing backend validator; stale edits fail with a conflict.
- Added a named resource register and resource creation form. Source mode, department and full timezone-aware availability interval are explicit. A resource without a saved profile remains visibly incomplete.
- Added a resource profile editor tied to a named unit. The editor loads the actual latest profile revision and saves the next revision through the existing profile schema and track reference checks.
- Added policy selection, saved revision history and an editor for explicit pair/group compatibility, travel and pool rules. Historical revisions can be inspected; editing requires the latest loaded revision. No allow rules, resource qualifications or railway policies are prefilled.
- Added read-only collection endpoints for resources and saved coordination-rule revisions. The server limits them to ADMIN, PLANNER, CONTROLLER and AUDITOR; write routes remain ADMIN/PLANNER only.
- Department users receive an access boundary instead of cross-department configuration views.

## Verified backend output

- A saved resource is returned from `GET /resources` with its exact ID, type, department, availability interval and source mode.
- A saved profile is returned from `GET /coordination-rules?kind=RESOURCE_PROFILE` with its exact key, revision and payload.
- A revised policy is returned with revisions `[2, 1]` in descending order for that key; read-only staff can inspect the history while department roles receive HTTP 403.

## Verification

- `npm run typecheck` — passed.
- `npm run lint` — passed with no diagnostics after cleanup.
- Targeted PostgreSQL command:

  `RAILSYNC_TEST_PORT=55440; powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1 -q -p no:cacheprovider tests/test_m18_admin.py tests/test_m03.py tests/test_m10.py`

- Result: **18 passed**, with two upstream Starlette/httpx deprecation warnings.
- `npm run build` compiled the optimized application successfully in 18.1 seconds. The host then refused Next.js's post-compile child process with `spawn EPERM`; a complete build pass is not claimed.

## Remaining gate

- Browser interaction and 1440px/1920px visual acceptance remain open.
- Worker/system health, deployment, backup/restore, benchmarks and complete M18 release evidence remain pending.
- SIMULATED policy and resource declarations still need the domain owner's review before operational use.
