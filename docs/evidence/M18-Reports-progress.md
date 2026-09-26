# M18 Reports, Analytics, Audit and Provenance — progress evidence

Recorded: 2026-09-25. This is an M18 technical slice, not the complete M18 gate.

## Implemented

- Added `/reports` and enabled **Reports & Audit** in the application shell.
- Added a read-only, hash-checked report-artifact index for one exact plan revision. It discovers saved validation reports, weekly/monthly schedules, baseline comparisons, controller decisions and execution observations without combining snapshots.
- Added authenticated append-only audit reads with exact action/entity/actor filters, bounded pages and query-bound cursors. Department-only roles cannot read the cross-department audit projection.
- The UI shows the snapshot → run → revision provenance chain, full plan/snapshot hashes, saved validation and human-decision evidence, publication artifacts and execution observations.
- KPI tables use saved backend metrics, formulas, signs and units. Current comparison claim eligibility is reread from the comparison endpoint rather than copied from historical content.
- JSON/CSV schedule exports and exact comparison JSON exports use the existing hash-checked backend endpoints.
- Empty, stale, missing, N/A and blocked-claim states remain visible. The page does not calculate or invent optimizer improvement.

## Verification

- `npm run typecheck` — passed.
- `npm run lint` — passed with no warnings.
- Focused report API tests — 2 passed.
- Regression command against isolated PostgreSQL `railsync_test` on port 55439:

  `RAILSYNC_TEST_PORT=55439; powershell -ExecutionPolicy Bypass -File scripts/test.ps1 -q -p no:cacheprovider tests/test_m14.py tests/test_m15.py tests/test_m18_workspace.py tests/test_m18_reports.py`

- Result: **20 passed**, with two upstream Starlette deprecation warnings.
- `npm run build` compiled the application successfully. The Codex Windows host then rejected Next.js's post-compile child process with `spawn EPERM`; therefore no complete production-build pass is claimed.

## Boundaries

- A saved KPI comparison describes proposed plans over the same saved inputs. It does not establish actual asset reliability, completed maintenance or measured train delay.
- Audit rows identify software actors and actions in this prototype. They do not authenticate external railway-system users or constitute railway authorization.
- The report index is read-only and does not replace the independent validator or controller workflow.
- Browser interaction and 1440px/1920px visual acceptance remain open due the host process/browser restriction.
