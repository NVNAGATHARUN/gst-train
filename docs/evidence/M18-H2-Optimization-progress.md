# M18 H2 and Optimization State — technical progress (2026-09-23)

Status: technical implementation passed targeted checks; browser visual acceptance remains open. The source is an isolated `SIMULATED` PostgreSQL fixture, processed by the real backend. No live railway connection or operating authorization is claimed. No commit was created because `.git` write access remains restricted.

## Implemented and reviewed

- H1 source/layout review: corrected the real backend restriction interval fields (`start`/`end`), kept the 1440px three-column width above the timeline's 550px minimum, and checked the responsive two/one-column breakpoints in source. Browser screenshot tooling had already failed in this host, so no visual screenshot was claimed.
- Extracted the shared time/track timeline data and component. Confirmed trains, freight envelopes, COA, restrictions, approved commitments, recorded possession history, capacity windows, candidates and proposed blocks remain distinct layers.
- H2 reads `/workspace/snapshots`, `/workspace/runs`, `/snapshots/{id}/workspace` and the selected calculation's saved policy/result. It shows derived windows, minimum-duration exclusions, COA/source conflicts, freight protection policy, clearance and rounding. Nearby facts are identified by temporal proximity and explicitly **not** claimed as the proven cause of a boundary. Commitments are shown separately from availability.
- Optimization State reads durable `/workspace/planning-sessions`, polls `/planning-sessions/{id}` only while active, and can queue `/planning-sessions`. It displays actual preparation artifacts, baseline and CP-SAT run states, objective/best-bound/runtime/branches/conflicts, objective terms and review blockers when recorded. No percentage completion or fabricated fallback schedule appears.

## Executed checks

| Check | Result |
| --- | --- |
| `tsc --noEmit --incremental false` | Passed on final source. |
| `npm run lint` | Passed, zero warnings. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1; npm run build` after separate TypeScript check | Passed; `/planning`, `/corridor`, `/optimization` all generated. The explicit flag bypasses only the host-blocked Next child-process check. |
| `python -m pytest -q -p no:cacheprovider tests/test_m08.py tests/test_m18_workspace.py tests/test_m18_planning_sessions.py` | 15 passed, two upstream deprecation warnings, isolated PostgreSQL 55437. |
| `scripts/m18_frontend_smoke.py` through production Next.js + FastAPI | Passed: login 201, session 200, three simulated snapshots, one confirmed occupancy, two demands, 11 generated candidates, saved proposal, all three routes 200, real `OPTIMAL` solver status and three backend-computed capacity windows. |

## Remaining acceptance

The browser could not launch on this Windows host in the previous run (`spawn EPERM` and computer-use kernel failure). Under the latest user instruction, a focused source/layout review substituted for the immediate visual pass so implementation could continue. Real 1440px/1920px screenshots and H1/H2 interaction/failure-state review remain necessary before final M18 acceptance. H3–H5, supporting screens, deployment and benchmarks remain out of this run's scope.
