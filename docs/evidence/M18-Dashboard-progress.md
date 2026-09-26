# M18 Operational Dashboard — progress evidence

Recorded: 2026-09-25. This is an M18 technical slice, not the complete M18 gate.

## Implemented

- Added `/dashboard` as the default signed-in landing page and placed Dashboard first in the operational navigation.
- Requires explicit immutable snapshot and proposal-revision selection; it never combines unrelated latest records.
- Shows source currency, independent validation, controller decision and software-authority boundaries separately.
- Summarizes maintenance demand, mandatory and high/critical demand, proposal coverage, selected-context readiness, saved capacity windows and actual execution-observation counts from backend projections.
- Reuses the time-track corridor visualization for confirmed trains, freight, restrictions, commitments, released possessions, derived capacity and proposed blocks.
- Shows department request distribution, current blockers, proposed block intervals and the five-stage evidence workflow.
- Planned assignments and observed execution remain separate. Missing report evidence displays loading/N/A rather than fabricated zero counts or a false no-decision state.
- Department users receive a bounded route to their maintenance workspace instead of cross-department planning evidence.

## Verification

- `npm run typecheck` — passed.
- `npm run lint` — passed with no warnings.
- A fresh isolated PostgreSQL cluster and `railsync_test` database were created on port 55440 after the prior temporary test process ended.
- Regression command:

  `RAILSYNC_TEST_PORT=55440; powershell -ExecutionPolicy Bypass -File scripts/test.ps1 -q -p no:cacheprovider tests/test_m18_workspace.py tests/test_m18_reports.py`

- Result: **9 passed**, with two upstream Starlette deprecation warnings.
- `npm run build` compiled the application successfully. The Codex Windows host then rejected Next.js's post-compile child process with `spawn EPERM`; no complete production-build pass is claimed.

## Boundaries

- Dashboard figures summarize saved planning evidence. They do not represent completed maintenance, actual train delay, asset reliability or railway authorization.
- Work readiness is scoped to the selected proposal and current independent evidence.
- Capacity is displayed as saved windows and computation counts; the UI does not invent a network-wide capacity percentage.
- Final browser interaction and 1440px/1920px visual acceptance remain open due the host process/browser restriction.
