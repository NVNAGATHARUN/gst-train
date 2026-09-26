# M18 H5 — Controller Review technical gate

Date: 2026-09-25. This is an M18 technical slice, not the complete M18 release gate.
Commit: none recorded; repository contents are currently untracked, so evidence is tied to the working tree.

## Backend-backed behavior

The Controller Review page assembles one saved plan revision, its snapshot/workspace evidence, the latest independent validation report, current freeze context and scope revision, saved explanations, replacement difference when present, and decision history. It shows exact possession, task setup/work/handback and named-resource intervals. Access requirements are displayed as requirements and `NOT_EVIDENCED` provision, not as grants.

CONTROLLER actions require a reason. Approval carries the exact plan hash, validation report ID, expected scope revision, idempotency key and prior lineage approval ID when applicable. The page fetches fresh revision/freeze/workspace context immediately before submission; a changed packet stops the write and preserves the reason. A network timeout or unknown response retains the exact request and key for saved-decision lookup or idempotent retry. A 409 marks the packet outdated and never automatically resubmits. Generated-candidate modifications create child proposals and require fresh validation. Replan calls the existing same-snapshot endpoint. The backend remains authoritative for all constraints, concurrency and reservations.

Isolated what-if revisions visibly disable controller writes and link to their actual source snapshot. The page says proposal approval does not grant railway operating authority.

## Verification

| Check | Result |
| --- | --- |
| `node node_modules/typescript/bin/tsc --noEmit --incremental false` | Passed after final H5 change. |
| `npm run lint` | Passed with no warnings after final H5 change. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1 npm run build` | Passed after separate TypeScript validation; `/review` included in production routes. |
| `scripts/test.ps1 -q -p no:cacheprovider tests/test_m13.py tests/test_m18_workspace.py` | 13 passed on isolated PostgreSQL port 55439; two upstream deprecation warnings. Includes backend concurrent approval, idempotency, role, modification and stale/hash boundary tests. |
| Focused M13 saved proposal test | 1 passed; left a labeled SIMULATED saved proposal, PASS-at-fixture-time report and explanations for browser review. |
| Focused M17 isolated train-delay scenario test | 1 passed; backend rejected scenario approval and left a saved scenario plan for browser review. |
| Browser flow through local production Next.js and FastAPI | CONTROLLER selected the saved revision; historical PASS was correctly BLOCKED on expired source facts; generated candidate picker showed the saved selection; simulated REJECT saved decision `4993b6bf-751b-4d87-9b6a-62948ca5ca66`, incremented SIMULATED scope revision 0→1, and remained visible after reload. Scenario proposal disabled all decision actions and the source-snapshot link selected the saved source snapshot. |

The simulated rejection wrote no approval or operational reservation. No browser approval was attempted on the expired fixture. The backend M13 tests exercise valid simulated approval and competing approvals; they do not establish external railway authority.

## Limits

Final user visual acceptance at 1440px/1920px, a current-data browser approval walk-through, and browser exercise of timeout/concurrent modification remain open. The backend covers the latter decision invariants in automated tests. Supporting Tier B/C screens, deployment, benchmark, backup/restore and the complete M18 release gate remain pending.
