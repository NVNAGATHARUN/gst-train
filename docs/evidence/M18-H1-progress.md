# M18 H1 implementation progress — 2026-09-23

Status: **in progress; H1 visual gate open**. All example railway data was created by the existing `SIMULATED` backend fixture. No live railway connection is claimed. No commit was created because this host's `.git` write access is restricted.

## Implemented

- Next.js 16/TypeScript/Tailwind frontend with a navy operational shell, protected routes, role-aware navigation, same-origin API proxy, HttpOnly browser session flow, and explicit unavailable/empty/stale states.
- Maintenance Intelligence register reads `/maintenance-requests`; department request form submits to that API with IST intervals and explicit access/resource requirements. Snapshot-specific priority and readiness come only from `/snapshots/{id}/workspace`.
- H1 reads saved snapshots, sessions, runs and the hash-bound workspace projection. It renders actual train occupancy, forecast envelope, COA, restrictions, derived windows, candidates and selected assignments on a track/time timeline. Demand cards and evidence inspector expose access, priority, setup/work/handback, resources, rules, deferrals and review blockers.
- Planning session action queues `/planning-sessions` and polls durable status. Save proposal uses the backend result hash in `/plan-revisions`. Independent validation calls `/validation-reports`; no UI PASS or score is synthesized.
- The backend run/session read models now expose the actual result hash needed to materialize a completed run; `tests/test_m18_planning_sessions.py` checks it.

## Executed checks

| Check | Result |
| --- | --- |
| `python -m pytest -q -p no:cacheprovider tests/test_m18_planning_sessions.py tests/test_m18_workspace.py tests/test_m18_sessions.py` | 34 passed, two upstream deprecation warnings. Separate PostgreSQL database on port 55436. |
| `npm run typecheck` | Passed. |
| `npm run lint` | Passed with zero errors; three non-blocking warnings were then removed. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1; npm run build` after a separate passing `npm run typecheck` | Passed, static `/login`, `/maintenance`, `/planning` routes built. Local Windows policy blocked Next's separate TypeScript child process; default production configuration still checks types unless the explicit flag is set. |
| `scripts/m18_frontend_smoke.py` through running production Next.js + FastAPI | Passed: login 201, session 200, 3 saved simulated snapshots, one confirmed occupancy, two demands, 11 backend-generated coordination candidates, saved proposal selected, planning route 200. |

## Visual review blocker and next gate

The local computer-use browser kernel failed to initialize (`failed to write kernel assets: The system cannot find the path specified`). Playwright and headless Edge/Chrome launches were also blocked by Windows process/IPC permissions (`spawn EPERM` / `Access is denied`). Thus no 1440px or 1920px screenshot was inspected, and browser interactions have not been asserted. H1 remains unchecked. The next task is to run `web/scripts/visual-check.mjs` on a host that permits browser launch (or use the user's browser), inspect both viewport screenshots and failure states, fix visible issues, and obtain H1 visual approval before H2.
