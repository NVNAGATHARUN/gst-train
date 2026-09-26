# M18 Replanning & What-if — technical gate

Date: 2026-09-25. This is an M18 frontend technical slice, not the complete M18 release gate.
Commit: none recorded; the repository contents are currently untracked, so this evidence is tied to the working tree.

## Implemented behavior

The `/changes` workspace presents two deliberately separate workflows.

**Isolated what-if** builds one to twenty typed changes against a selected current, non-scenario snapshot. Train-delay and freight changes select exact saved facts; resource outages and restrictions require concrete tracks and intervals; an added request passes a complete JSON payload to backend validation. The page submits the source snapshot hash and an idempotency key, shows real baseline and CP-SAT run statuses, lists the immutable changed inputs and makes `APPROVAL_FORBIDDEN` prominent. It can save a source-versus-scenario impact from validated CP-SAT revisions and labels every value as a raw input-changed delta, with no optimizer-gain claim.

**Source disruption & replacement** records an immutable SIMULATED event with source identity, revision, time, footprint and evidence. The page states that this makes affected plans stale but does not modify source facts. A rolling-replan preview shows batch generation, base-facts hash, each event's reconciliation status, matched changed source records and blockers. Only a CONTROLLER can submit a reviewed validation-context declaration after a fresh preview/hash/revision check. The server binds the new facts hash, captures frozen/execution evidence and queues actual baseline and CP-SAT work. Independent validation and controller review remain later gates.

Scenario, event and rolling-replan writes retain their exact request for idempotent retry when a response is uncertain. Known 401/403/409/422 responses clear that pending retry and display the backend blocker. The UI never fabricates progress, impact metrics, source reconciliation or an approved replacement.

## Verification

| Check | Result |
| --- | --- |
| `npm run typecheck` | Passed after the final `/changes` implementation. |
| `npm run lint` | Passed with no warnings after dependency corrections. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1 npm run build` | Passed after the separate TypeScript check; `/changes` is present in the production route list. |
| `RAILSYNC_TEST_PORT=55439 scripts/test.ps1 -q -p no:cacheprovider tests/test_m16_rolling.py tests/test_m17_what_if.py tests/test_m18_workspace.py` | 20 passed; two upstream deprecation warnings. |
| Focused M17 saved fixture | 1 passed on a fresh isolated PostgreSQL cluster. Saved scenario `77118198-df2b-4368-b863-19d0eace2f71` applied one ten-minute TRAIN_DELAY through the real pipeline; baseline and CP-SAT both completed. Saved impact `81514d6c-0d86-46fb-9445-65262a17ba58` has `INPUT_CHANGED_SCENARIO_IMPACT`, `claims_permitted=false`, and isolated-simulation authority. |
| Live Next.js proxy/session/API smoke | A PLANNER browser session read the same saved scenario and impact through `127.0.0.1:3000/api/v1`. Returned authority was `ISOLATED_SIMULATION_ONLY`, approval was false, both run statuses were `COMPLETED`, and impact claims were false. |

The M16/M17 suites cover all five disruption kinds, all five scenario change kinds, real solver publication, stale/hash/idempotency boundaries, changed-source reconciliation, rolling-horizon retention, independent validation, scenario decision refusal and source/reservation isolation.

## Visual verification limitation

The in-app browser could not initialize its kernel assets after its prior tab closed. The installed Playwright/Chrome fallback also failed at process launch with Windows `spawn EPERM`. I did not weaken process security or claim a screenshot result. Source/layout review, production compilation and live authenticated proxy/API checks passed. Final browser interaction and 1440px/1920px visual acceptance remain open.

## Remaining M18 work

Revision-difference and execution/handback views, reports/provenance/audit screens, final wide-screen review, deployment/backup checks, benchmarks and the full demonstration gate remain. The M16 rolling-replan form intentionally requires a fresh reviewed validation-context declaration; the UI does not infer operational completeness from old snapshot facts.
