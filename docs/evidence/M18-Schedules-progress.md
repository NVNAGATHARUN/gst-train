# M18 Weekly / Monthly Block Plan — technical gate

Date: 2026-09-25. This is one M18 frontend slice, not the full release gate.
Commit: none recorded; the repository contents remain untracked. Evidence refers to the current working tree.

## Result

The `/schedules` screen creates a weekly or monthly artifact only through the existing M14 backend endpoint and opens a persisted artifact by ID. The backend enforces complete local-calendar period coverage and rejects an assignment outside the selected period. The UI uses the saved period, assignments, request stages, named resources, deferred reasons, validation-at-generation status, controller decision and declared freight coverage. Monthly dates align to Monday–Sunday headings; selecting a day shows every saved possession intersecting that local day. FIRM, TENTATIVE and REQUIRES_ATTENTION remain software-proposal statuses, separate from execution or railway authority.

The screen makes historical versus selected snapshot/revision differences visible. A matching-snapshot action changes only the UI selection. JSON and CSV downloads use the M14 export endpoint; the UI checks the returned content-hash header against the displayed artifact before offering the blob. The backend independently checks its stored content hash and escapes CSV formula prefixes.

## Verification

| Check | Result |
| --- | --- |
| `npm run typecheck` | Passed after final UI change. |
| `npm run lint` | Passed with no warnings after final UI change. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1 npm run build` | Passed after separate TypeScript check; `/schedules` in production routes. Normal Next type subprocess hit Windows `spawn EPERM` twice, with source compilation successful; no type error was reported. |
| `RAILSYNC_TEST_PORT=55439 scripts/test.ps1 -q -p no:cacheprovider tests/test_m14.py tests/test_m18_workspace.py` | 12 passed, two upstream deprecation warnings. |
| Focused M14 monthly saved-artifact fixture | 1 passed; backend artifact `00bdfb7c-ba7d-4f02-910b-0d18d515423d` had one real computed integrated possession, two tasks, TENTATIVE status, no deferred work, 30 days and hash `9ba566d4...`. |
| Browser against local production Next.js and isolated FastAPI/PostgreSQL | Opened the saved SIMULATED monthly artifact by ID, selected 21 September and saw the computed 01:25–02:45 AB block, TRD + Engineering task stage times and named crew allocations. Selected matching snapshot, then created a second saved monthly artifact `fb43f0b0-22a2-446e-8912-7af19e83e69f` through the UI. Counts remained one possession, two tasks, zero firm, one tentative. |

The M14 suite also exercises weekly full-horizon rejection, monthly/leap/DST boundaries, approved/stale firm labeling, role controls, immutability, deterministic JSON/CSV export and CSV formula safety. A browser download event was not observable in the in-app browser; the UI showed no export error after the CSV action, but download-manager completion is not claimed.

## Remaining

Wide-screen visual acceptance at 1440px/1920px and browser download-manager confirmation remain open. Supporting replanning, scenario/difference, records, provenance and reports screens plus deployment/benchmarks/backup/demo acceptance are still part of M18. This SIMULATED fixture uses an old validation time; the UI correctly labels the proposal tentative and validation not run. It does not imply a current approved block.
