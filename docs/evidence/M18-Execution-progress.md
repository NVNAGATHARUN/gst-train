# M18 Revision Differences and Execution / Handback — progress evidence

Recorded: 2026-09-25. This is an M18 technical slice, not the complete M18 gate and not an operational railway authorization claim.

## Implemented

- Added `/execution` to the application shell and built a backend-bound execution workspace.
- Reads the exact saved plan revision, active freeze/approval commitments, scoped operational revision, immutable execution records and stored replacement difference.
- Shows request-level source/replacement classifications with saved before/after possession, work, track and resource evidence. The screen explicitly labels this as descriptive evidence rather than a KPI improvement.
- Separates the planned setup/work/restoration interval from observed STARTED, INTERRUPTED, RESUMED and COMPLETED records.
- Constrains lifecycle choices from the latest saved state and preflights current commitment, assignment hash, sequence and operational revision before writes.
- Records interrupted-work assessments with request revision, remaining work, restart setup/restoration and evidence reference.
- Requires terminal evidence for every member of a shared assignment, a current assessment for every interrupted member, ordered timestamps and explicit track/electrical/signalling/resource-clear attestations before a software handback request can be sent.
- Supports opening immutable reconciliation or release evidence by recorded ID. Scenario and non-controller writes remain disabled.
- Preserves an exact idempotent request after an uncertain network result so retry does not create a second action.

## Verification

- `npm run typecheck` — passed.
- `npm run lint` — passed with no warnings.
- Focused backend regression command using the isolated `railsync_test` database on port 55439:

  `RAILSYNC_TEST_PORT=55439; powershell -ExecutionPolicy Bypass -File scripts/test.ps1 -q -p no:cacheprovider tests/test_m16_execution.py tests/test_m16_restoration.py tests/test_m16_continuation.py tests/test_m16_approval.py tests/test_m18_workspace.py`

- Result: **42 passed**, with two upstream Starlette deprecation warnings.
- `npm run build` and the webpack build both reached successful source compilation. The current Codex Windows host then rejected the Next.js child process with `spawn EPERM` during the post-compile phase. This is recorded as an unresolved environment limitation; no production-build pass is claimed for this slice.

## Boundaries

- The page records verified software observations. It does not command field work, certify safety, grant a line/power block or issue railway control.
- Completion of a maintenance task does not release a shared possession. Release remains a separate atomic backend transition after full-bundle evidence and restoration attestations.
- There is no release-list endpoint. The screen retains a newly returned release in the current view and can reopen older immutable evidence by ID; it does not invent a release state when no artifact is loaded.
- Final browser interaction and 1440px/1920px visual acceptance remain open because the host cannot currently launch the Next.js compiler child process or browser automation runtime.
