# RailSync AI Implementation Status and Remaining Work

**SIH 2026 PS26027**  
**Status date:** 25 September 2026  
**Project stage:** M18 in progress  
**Audience:** RailSync team, mentors and reviewers

## Executive status

RailSync AI has passed the recorded M1 through M17 milestone gates for a **SIMULATED railway maintenance planning prototype**. Its backend accepts Engineering, TRD and S&T maintenance demand and railway operating facts, freezes them in an immutable planning snapshot, derives corridor capacity and timed work opportunities, coordinates compatible work and named resources, runs a fair first-feasible baseline and a real OR-Tools CP-SAT optimizer, independently validates proposals, and supports controller decisions, reports, replanning and isolated what-if analysis.

The M18 Next.js product is substantially implemented. Its five hero screens and supporting operational screens, including Access and System Health Administration, have technical evidence. **M18 is not complete.** Remaining work includes full browser and visual acceptance, deployment and backup/restore verification, repeatable benchmarks, an integrated SIH demonstration, and a fresh cumulative release gate.

The latest complete cumulative test gate is **M17 with 168 passing tests**. Later M18 slices have separate targeted test runs. Those counts overlap and must not be added together or presented as a new cumulative pass. Recent Next.js builds compiled source successfully, then this Windows host rejected a post-compile child process with `spawn EPERM`; those attempts do not count as complete production builds.

## Scope and rules

RailSync is a fixed-infrastructure maintenance **decision-support** prototype. It proposes and checks maintenance blocks; it does not control trains or grant railway operating authority. The detailed `RailSync_AI_Solution_SRS_Build_Contract.pdf`, approved `docs/M18_UX_DESIGN.md`, `CHECKLIST.md`, and `docs/REQUIREMENT_TRACEABILITY.md` govern this status. The earlier basic SRS is superseded where less specific.

Synthetic inputs and examples must be labeled **SIMULATED**. An IMPORTED flag records provenance, but does not authenticate a live railway interface, complete traffic coverage or a railway operating rule. Unknown critical facts block review or approval. No AI score, conflict, optimizer result or KPI improvement may be invented for a screen or demonstration.

## Implemented architecture

1. Engineering, TRD and S&T requests; simulated/imported TMS, SMMS and TDMS records; network and assets; dated train occupancy; COA; freight forecasts; restrictions, resources and commitments.
2. Schema and reference validation, source revisions, idempotent imports, completeness/freshness declarations and provenance.
3. Immutable Integrated Railway Planning State as a content-hashed snapshot.
4. Transparent rule priority and a separate Corridor Availability Engine.
5. Timed opportunities, evidence-backed exclusions, explicit work compatibility and concrete resource allocation.
6. Deterministic first-feasible baseline and real fixed-candidate CP-SAT selection over the same facts and alternatives.
7. Canonical plan revisions and an independent fail-closed validator that recomputes constraints from raw snapshot facts.
8. Structured explanations, current validation status, controller approve/modify/reject/replan decisions, audit and software reservations.
9. Weekly/monthly artifacts, same-input KPI comparisons, execution observations, rolling replanning and isolated what-if scenarios.

The backend uses Python, FastAPI/Pydantic, PostgreSQL with Alembic migrations, a durable planning worker and OR-Tools CP-SAT. The frontend uses Next.js and TypeScript. Docker Compose currently defines a PostgreSQL development service; verified production packaging of the whole application is pending.

**AI, ML and safety boundary:** The active maintenance priority is deterministic and explainable. An evaluated, versioned ML experiment interface exists, but no promoted Random Forest/XGBoost model or demonstrated SHAP inference is claimed. CP-SAT is the implemented scheduling intelligence. The independent validator and human controller are separate decision layers. ANN forecasting is optional M19 work and is not in the current core path.

## Completed milestones

| Milestone | Priority | Implemented result | Gate |
| --- | --- | --- | --- |
| M1 | P0 | Repository, PostgreSQL, migrations, configuration, authentication skeleton and test harness | Complete |
| M2 | P0 | Maintenance requests, revisions, lifecycle and idempotent TMS/SMMS/TDMS imports | Complete |
| M3 | P0 | Stations, sections, tracks, assets, footprints, isolation zones and restrictions | Complete |
| M4 | P0 | Timetable, dated train-section occupancy, COA inputs and freight uncertainty | Complete |
| M5 | P0 | Immutable content-hashed snapshots and provenance | Complete |
| M6 | P0 | Deterministic first-feasible baseline | Complete |
| M7 | P1 | Rule priority and gated ML experiment interface | Complete; no promoted ML model |
| M8 | P1 | Conservative corridor availability | Complete |
| M9 | P1 | Timed opportunities and explicit exclusion evidence | Complete |
| M10 | P1 | Pair/group compatibility, timing, named resources, pools, travel, rest and duty limits | Complete |
| M11 | P1 | Genuine CP-SAT selection, weighted objectives, solver status/diagnostics and fair updated baseline | Complete |
| M12 | P1 | Independent fail-closed validation, freshness checks and corruption tests | Complete |
| M13 | P2 | Explanations, plan revisions, controller decisions, concurrency and audit | Complete |
| M14 | P2 | Weekly/monthly saved schedule artifacts and exact JSON/CSV exports | Complete |
| M15 | P2 | Same-snapshot baseline comparison with declared KPI units and denominators | Complete |
| M16 | P3 | Disruptions, frozen/interrupted work, execution observations and rolling replanning | Complete for SIMULATED prototype |
| M17 | P3 | Isolated what-if scenarios through the real pipeline with approval/reservation boundaries | Complete for SIMULATED prototype |

For saved comparisons, the M11 baseline uses the same generated alternatives and constraint model as CP-SAT. The early M6 baseline alone is not eligible. CP-SAT optimality, when reported, applies only to the generated candidate set. Initial train times are fixed and planning/validation use half-open timezone-aware intervals.

M16 recorded **162 cumulative tests** and a simulated source-event replacement scenario. M17 recorded **168 cumulative tests** and a ten-minute train-delay scenario. In the saved M17 example, both real planners ran, CP-SAT returned `OPTIMAL` within its candidate set, independent validation passed while the source was current, and controller approval of the isolated scenario was refused. These are historical test results, not a production benchmark.

## M18 frontend technical implementation

Each item below is implemented technically. The full M18 release gate remains open.

| Screen or workflow | Current behavior | Open acceptance |
| --- | --- | --- |
| Global shell and browser session | Role-aware navigation, HttpOnly browser session, explicit snapshot/session/revision context and API error states | Final cross-role browser review |
| H1 Planning Workspace | Demand, time-track timeline, selected proposal, task stages, resources, readiness and planning actions | 1440px/1920px visual approval |
| H2 Corridor and COA | Occupancy, freight, COA, restrictions, commitments, capacity windows and boundary/exclusion evidence | Wide-screen visual approval |
| Optimization State | Durable preparation stages and actual baseline/CP-SAT statuses and diagnostics | Final browser review |
| H3 Baseline versus RailSync | Same-snapshot run pairing, saved validation, backend KPIs with signed/N/A outcomes and two plan timelines | Wide-screen visual approval |
| H4 Validation Center | Saved PASS/FAIL/ERROR, current usability, findings, source-linked evidence, revalidation and export | Wide-screen visual approval; interval-linked conflict exercise |
| H5 Controller Review | Exact packet, validation/freeze context, generated-candidate modification, reasoned decisions, idempotent retry and history | Current-data browser approval and visual approval |
| Weekly and Monthly | Immutable period generation, calendar drilldown, status limits, tasks/resources and hash-checked exports | Wide-screen review; download confirmation |
| Replanning and What-if | Isolated scenarios, real worker state, raw impact deltas, simulated disruptions and rolling replacement preparation | Full browser interaction and visual review |
| Revision Differences and Execution | Stored before/after changes, execution ledger, interrupted-work assessment, restoration attestations and software release evidence | Browser interaction and visual review |
| Reports, Analytics and Audit | Saved artifacts, KPI semantics, hashes, exports and append-only audit views | Browser interaction and visual review |
| Operational Dashboard | Explicit case selection, demand/coverage/readiness, blockers, corridor timeline and planned-versus-observed distinction | Browser interaction and visual review |
| Data Import and System Readiness | Department preview/commit, source lineage, operational intake and snapshot coverage/freshness/COA evidence | Browser interaction and visual review |
| Network, Resource and Policy Administration | Current network register, named units, profile revisions and policy history with server role/revision checks | Browser interaction and visual review |
| Access and System Health Administration | ADMIN-only current API/database/worker heartbeat state, queue counts, provisioned role roster and session facts | Browser interaction and visual review |

Operational results on these screens come from backend APIs or saved artifacts. Empty, infeasible, unknown, stale and error states remain visible. A validator PASS means compliance with configured prototype constraints; it does not certify a railway operation.

## Verification position

M1-M17 have recorded milestone gates, ending with the **168-test M17 cumulative run** through migration 023. M18 has targeted tests, separate TypeScript/lint checks, source compilation and selected local browser/proxy exercises. Examples include **45 H4 validator/workspace tests**, **42 execution/workspace tests**, **20 reports tests**, **14 data-readiness tests**, and **18 administration tests**. These suites overlap and were run at different points.

Selected browser exercises verified H1/H2 interaction at an available viewport, a simulated H3 comparison, a H4 stale-data finding, a simulated H5 controller rejection, and weekly/monthly day drilldown. They do not close the required wide-screen acceptance. The latest administration build compiled its optimized source in **18.1 seconds**, then failed with `spawn EPERM` during a later Next.js child step. Separate `npm run typecheck` and `npm run lint` passed. A full production-build pass is not recorded for that slice.

The Access and System Health slice added migration 026 and an observed worker heartbeat. On 25 September, **30 focused backend tests passed** against isolated PostgreSQL, including ADMIN browser-session access, role denial, absent/responsive/stale/stopped worker states and credential exclusion. `npx tsc --noEmit --incremental false` and `npm run lint` passed. These are targeted results, not a new cumulative gate or browser visual sign-off.

The repository has no recorded Git commit for M18 because host permissions blocked `.git` writes. Some earlier milestone gates use source-hash manifests instead. The release gate should capture a reproducible source revision or hash manifest with the final test outputs.

## Remaining work and completion criteria

### Access and System Health Administration

The technical slice is complete. The ADMIN-only page reports observed API and PostgreSQL state, migration revision, worker heartbeat and queued work; stale/absent workers degrade the overall status. It shows a read-only provisioned roster and the current authentication mode without credentials or hashes. Browser interaction and wide-screen visual acceptance remain open. Credential provisioning remains outside this UI.

### Browser and visual acceptance

Review all M18 screens at **1440px and 1920px**, including loading, empty, blocked, stale, validation failure, infeasible and API-error states. Exercise keyboard access, focus, labels, dense timeline usability, responsive layout and source-to-screen evidence. Obtain user-required visual approval for H1-H5. Close current-data controller approval, timeout/concurrent-edit presentation, schedule download confirmation and later supporting-screen flows.

### Deployment and recovery

Package API, durable worker, Next.js frontend and PostgreSQL with locked dependencies and explicit configuration. Run migrations and readiness checks on a clean deployment. Verify HTTPS and secure cookies outside loopback development. Test PostgreSQL backup and restore to a separate target; prove restored snapshots, plan revisions, decisions, audit events and exports are readable. Record commands, versions and outcomes. Current `compose.yaml` covers only PostgreSQL development.

### Benchmarks and SIH demonstration

Run the real backend on a labeled, hand-checkable A-B-C-D **SIMULATED** case with Engineering, TRD, S&T and a competing resource task. Verify compatible Engineering/TRD sharing and a variant that disables compatibility. Then run larger 20, 100 and, if feasible, 300-plus request cases with fixed seeds/input manifests. Save candidate counts, pruning, solver status, runtime, best bound, validation and baseline comparisons. Do not force improvement; show negative and N/A results when produced. Build a judge walkthrough from persisted outputs, including a constraint failure and stale/replan case.

### Final M18 release gate

Run a fresh cumulative backend suite and complete frontend typecheck, lint and production build on a host that permits the required child processes. Add end-to-end browser acceptance for role scope, import, planning, comparison, validation, controller decision and exports. Record source revision/hash, migration head, exact commands and outputs, screenshots, backend examples, benchmark definitions and known limits in one M18 evidence package. Update the checklist and traceability only after this gate passes.

### Domain review and optional M19

A domain owner must confirm imported COA semantics, source coverage/freshness, electrical isolation and work-access rules before any operational-readiness claim. Imported data remains fail-closed until authority and completeness are established. M19 forecasting is optional; it needs suitable history, a defined prediction target and a versioned evaluation. It does not delay the core M18 prototype.

## Recommended completion sequence

1. Restore a working browser/build environment and close outstanding screen interaction and visual gates, fixing findings.
2. Complete clean deployment, startup, backup and restore verification.
3. Run repeatable benchmarks and the integrated simulated demonstration.
4. Execute the cumulative M18 release gate and mark M18 complete only when it passes.
5. Consider M19 separately if suitable forecasting data exists.

The milestone rule still applies: record automated tests and correct backend output for each new slice before the next. A technically implemented screen is not an accepted M18 release.

## Source and evidence map

| Record | Purpose |
| --- | --- |
| `CHECKLIST.md` | Current milestone and M18 checkbox state |
| `docs/REQUIREMENT_TRACEABILITY.md` | Contract-to-code and evidence map |
| `docs/M18_UX_DESIGN.md` | Approved frontend design and visual gates |
| `docs/evidence/M17.md` | Latest complete cumulative gate and 168-test result |
| `docs/evidence/M18-H1-progress.md` through `M18-H5-progress.md` | Five hero experiences and acceptance gaps |
| `docs/evidence/M18-Schedules-progress.md` | Weekly/monthly UI and exports |
| `docs/evidence/M18-Changes-progress.md` | Replanning and what-if UI |
| `docs/evidence/M18-Execution-progress.md` | Difference, execution and handback UI |
| `docs/evidence/M18-Reports-progress.md` | Reports, KPI and audit UI |
| `docs/evidence/M18-Dashboard-progress.md` | Operational dashboard |
| `docs/evidence/M18-Data-Readiness-progress.md` | Import and readiness center |
| `docs/evidence/M18-Administration-progress.md` | Network, resource and policy administration |
| `docs/evidence/M18-System-progress.md` | Access and System Health Administration; 30 focused backend tests |
| `backend/railsync/`, `web/src/`, `tests/`, `migrations/` | Application, tests and schema history |

**Status statement:** RailSync has a tested simulated planning backend and a broad, technically implemented M18 frontend. It remains in M18 until browser, deployment, recovery, benchmark and cumulative evidence gates are complete.
