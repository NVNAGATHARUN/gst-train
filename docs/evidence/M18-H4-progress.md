# M18 H4 — Independent Validation Center technical gate

Date: 2026-09-24. This is an M18 technical slice, not the complete M18 release gate.
Commit: none recorded; repository contents are currently untracked, so evidence is tied to the working tree.

## Backend-backed behavior

The Validation Center selects an immutable planning snapshot and saved plan revision, then reads the latest independent validation report through the workspace API. It displays the recorded PASS, FAIL or ERROR separately from the backend's **current review usability**. It shows current source/hash/freshness blockers, configured category results, findings, exact recorded fields and matched snapshot facts. The shared timeline uses saved occupancy, forecast, COA, restriction, commitment and proposal intervals. A finding's referenced train, forecast or assignment is highlighted when present; missing evidence does not produce an invented interval.

An explicit action creates a new independent report with the expected plan hash, then refreshes the workspace. Report export serializes the actual retrieved JSON. The page does not grant approval or imply railway safety certification.

## Verification

| Check | Result |
| --- | --- |
| `npx tsc --noEmit --incremental false` | Passed after final H4 change. |
| `npm run lint` | Passed after final H4 change. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1 npm run build` | Passed after separate TypeScript validation; `/validation` included in production routes. |
| `scripts/test.ps1 -q -p no:cacheprovider tests/test_m12.py tests/test_m18_workspace.py` | 45 passed on fresh isolated PostgreSQL port 55439; two upstream deprecation warnings. |
| `tests/test_m15.py::test_same_snapshot_comparison_uses_persisted_intervals_and_honest_nulls` | Passed; left a labeled SIMULATED saved snapshot, CP-SAT proposal and validation report for browser review. |
| Local production Next.js + FastAPI browser flow | Signed into isolated PLANNER fixture; selected CP-SAT revision; saw recorded PASS but current BLOCKED; revalidated to recorded FAIL; inspected data-quality finding, category filter and proposal timeline. |

The saved simulated report was PASS at its fixture check time on 21 September 2026, but review use was BLOCKED on 24 September because source declarations had expired. Revalidation returned FAIL with `DATA_STALE_OR_FUTURE_RECEIPT`; the UI showed no source interval for that interval-free finding. No operational approval or current benefit claim was made.

## Limits

The browser review used the available approximately 1000-pixel viewport and a stale-data finding. Final H4 visual acceptance at 1440px/1920px and a browser exercise of an interval-linked conflict remain open. H5 Controller Review and remaining M18 deployment/demo work are not complete.
