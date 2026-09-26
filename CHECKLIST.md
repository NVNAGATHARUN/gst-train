# RailSync AI — implementation checklist

Status: M1–M17 gates passed; M18 is in progress; design approved with four amendments. Git commits remain blocked by host permissions. A checkbox means automated tests passed and backend output was verified; implementation alone is not completion.

- [x] M1 · P0 — Repository, PostgreSQL, migrations, configuration, auth skeleton and test harness (3 tests; evidence in docs/evidence/M01.md)
- [x] M2 · P0 — Maintenance requests, revisions, lifecycle and idempotent imports
- [x] M3 · P0 — Network, tracks, assets, footprints, isolation and restrictions
- [x] M4 · P0 — Timetable, dated occupancy, COA and freight uncertainty
- [x] M5 · P0 — Immutable snapshots and provenance
- [x] M6 · P0 — Deterministic first-feasible baseline
- [x] M7 · P1 — Rule priority and gated ML experiment interface
- [x] M8 · P1 — Conservative corridor availability
- [x] M9 · P1 — Timed opportunities and exclusion evidence
- [x] M10 · P1 — Compatibility, bundling and resource constraints
- [x] M11 · P1 — Genuine CP-SAT selection and diagnostics
- [x] M12 · P1 — Independent fail-closed validator and mutation tests
- [x] M13 · P2 — Explanations, controller decisions, concurrency and audit
- [x] M14 · P2 — Weekly/monthly orchestration and exports
- [x] M15 · P2 — Same-snapshot baseline/KPI comparison
- [x] M16 · P3 — Rolling-horizon replanning, frozen work and staleness
- [x] M17 · P3 — Isolated what-if scenarios
- [ ] M18 · P3 — Complete frontend, deployment, benchmark and demo evidence
- [ ] M19 · P3 optional — Forecasting, only with suitable data and evaluation

## M16 progress (complete SIMULATED prototype gate)

- [x] Immutable simulated disruption events, occurrence/receipt times and source revision checks.
- [x] Concurrent duplicate handling and debounce generations.
- [x] Snapshot invalidation, stale approval blocking and reservation preservation.
- [x] Supersede obsolete jobs and reject late worker publication.
- [x] Reject new receipt metadata around unchanged invalidated facts.
- [x] Immutable execution records, explicit lifecycle, concurrent idempotency and configurable freeze-policy revisions.
- [x] Exact frozen-assignment protection on controller edits and approval; execution-aware snapshot requirement and stale worker fencing.
- [x] Immutable replanning capture: source approval, execution ledger, policy versions, reservations and event references.
- [x] Fresh snapshots include execution/commitment evidence and completed-request exclusions; stale captures are rejected.
- [x] Recheck approved candidates against current facts; solve with exact frozen commitments using real CP-SAT and the same-input baseline.
- [x] Independent replacement validation recomputes freeze obligations, execution provenance and time boundaries; corruption tests pass.
- [x] Versioned remaining-work assessments for interrupted tasks, preserving source requirements and explicit restart stages.
- [x] Verified whole-possession restoration and atomic release of the matched SIMULATED reservation; duplicate/stale/active-work guards.
- [x] Residual-work planning after release, completed-work exclusion, restored predecessor handling and conservative resource/track history.
- [x] Independent release/residual/history validation and corruption tests; UTC timestamps and concurrent duplicate release verified.
- [x] Execution continuation against controlled replacement approvals, with verified preserved or residual handoff and independently checked history; unreleased in-place resumption cannot become an approved replacement.
- [x] Source-event reconciliation and rolling-horizon orchestration across supported disruption cases.
- [x] Replacement differences/lineage and atomic controlled-supersede controller approval for captured SIMULATED plans.
- [x] Complete M16 acceptance scenario and milestone gate.

Latest evidence: `docs/evidence/M16-rolling.md` — **162 cumulative tests passed** against PostgreSQL on localhost:55433 through migration 021. Recorded urgent-defect source reconciliation produced real candidates, baseline/CP-SAT runs, independent PASS validation and controlled controller replacement approval. Train delay, freight change, resource outage and restriction changes each reconcile to revised source facts; a delayed train that conflicts with frozen work remains visibly infeasible. The older continuation evidence and tests remain part of the cumulative gate. Use `RAILSYNC_TEST_PORT=55433` with `scripts/check_m16_rolling.py`.

Unknown remaining work and unverified restoration remain blocked; verified release and controlled supersession are separate reservation transitions. **M16 is complete for the SIMULATED prototype.**

## M17 progress (complete SIMULATED prototype gate)

- [x] Immutable scenarios derived from a hash-bound, current non-scenario snapshot.
- [x] Typed train-delay, freight-count, resource-outage, restriction and added-request overlays.
- [x] Source records, snapshots, decisions and reservations remain unchanged by scenario creation.
- [x] Real rule-priority, availability, opportunity, coordination, baseline and CP-SAT pipeline.
- [x] Independent scenario validation replays changes from the current source and becomes stale when that source changes.
- [x] Scenario plan approve/reject/replan/edit boundaries fail closed; queued and new jobs are fenced after source changes.
- [x] Same-scenario baseline comparison is labeled isolated simulation only.
- [x] Immutable source-versus-scenario impact records expose changed inputs and raw deltas without claiming optimizer gains.
- [x] Complete M17 acceptance scenario and cumulative milestone gate.

Latest evidence: `docs/evidence/M17.md` — **168 cumulative tests passed** through migration 023. The saved ten-minute train-delay scenario completed actual baseline and CP-SAT work, passed independent validation, produced isolated comparison/impact artifacts and was refused controller approval. The source occupancy and reservation state remained unchanged. **M17 is complete; M18 is the next milestone.**

## Gate requirements

Milestone N+1 must not start until N has passing automated tests and correct backend output checked against explicit expected results. Evidence belongs in `docs/evidence/Mxx.md` with source commit, commands, results, persisted examples and limitations. Never fabricate scores, assignments, conflicts or improvements. Unknown operational rules remain fail-closed.

## Source precedence

The user's implementation request and detailed Build Contract govern. The earlier one-page SRS and pasted discussions provide context. All demonstration data must be labeled SIMULATED. No live railway interface is claimed.

## M18 progress (in progress; no completion gate claimed)

- [x] UX architecture approved; Work Readiness, access requirements, planned/actual and per-hero visual gates incorporated in `docs/M18_UX_DESIGN.md`.
- [x] Step 1: API/session prerequisites with automated tests and saved backend output (`docs/M18_FOUNDATION_API.md`, 34 targeted tests rechecked on 2026-09-23).
- [x] Step 2: frontend foundation and global shell (Next.js production compile, separate TypeScript and lint checks, live proxy/session smoke).
- [x] H1 technical implementation: Planning Workspace, backend-bound timeline, saved session/proposal/validation actions, focused source/layout review and passing targeted checks. Corrected restriction `start`/`end` mapping.
- [x] H2 technical implementation: Corridor & COA Availability, real capacity/policy/exclusion/boundary evidence, shared timeline, focused source/layout review and passing targeted checks.
- [x] Optimization State: actual durable session stages and saved baseline/CP-SAT metrics; no inferred progress or solver results.
- [x] H1/H2 browser interaction review at the available viewport: request/train inspectors, historical capacity run selection, actual calculated windows and stale-source blockers verified on 2026-09-24.
- [ ] H1/H2 final visual acceptance at 1440px/1920px.
- [x] H3 technical implementation: Baseline vs RailSync comparison, same-snapshot run pairing, independent validation, versioned KPI evidence, responsive timelines and browser integration verified with a labeled simulated fixture.
- [ ] H3 final user visual approval at 1440px/1920px.
- [x] H4 technical implementation: Validation Center, saved PASS/FAIL/ERROR reports, current review blockers, source-linked findings, explicit revalidation and JSON export; TypeScript, lint, build, targeted backend tests and local browser flow verified.
- [ ] H4 final user visual approval at 1440px/1920px.
- [x] H5 technical implementation: exact revision packet, current validation/freeze context, generated-candidate modification, controller approve/reject/replan forms, idempotent retry resolution, decision history and scenario boundary; targeted checks and isolated browser flow verified.
- [ ] H5 final user visual approval at 1440px/1920px and a current-data browser approval demonstration.
- [x] Weekly / Monthly Block Plan technical implementation: backend-generated immutable period artifacts, calendar day drilldown, exact setup/work/restoration and resource details, status/coverage limits, and hash-checked JSON/CSV exports. M14/workspace tests and isolated browser flow verified.
- [ ] Weekly / Monthly final wide-screen visual acceptance and browser download-manager confirmation.
- [x] Replanning & What-if technical implementation: isolated typed scenario changes, actual worker status, source-versus-scenario raw impact deltas, immutable disruption intake, changed-source reconciliation preview, controller-only rolling replacement preparation and idempotent uncertain-result recovery. M16/M17/workspace tests and live proxy/API fixture verified.
- [ ] Replanning & What-if final browser interaction and wide-screen visual acceptance; local browser launch is currently blocked by the host runtime (`kernel assets` / `spawn EPERM`).
- [x] Revision Differences and Execution / Handback technical implementation: stored source-to-replacement classifications, active approval/freeze context, immutable execution ledger, guarded lifecycle writes, versioned interrupted-work reconciliation, whole-bundle restoration attestations, software reservation release, evidence reopening and idempotent uncertain-result retry. TypeScript/lint pass and 42 focused M16/workspace tests pass.
- [ ] Revision Differences and Execution / Handback final browser interaction and wide-screen visual acceptance; the Next.js compiler currently reaches successful compilation but the host rejects its child process with `spawn EPERM`.
- [x] Reports, Analytics, Audit and Provenance technical implementation: exact revision report index, saved validation/schedule/comparison/decision/execution discovery, backend KPI semantics, reproducible export links, hash provenance and authenticated query-bound audit pagination. TypeScript/lint pass and 20 M14/M15/workspace/report tests pass.
- [ ] Reports, Analytics, Audit and Provenance final browser interaction and wide-screen visual acceptance; Next.js source compilation succeeds before the same host `spawn EPERM` restriction.
- [x] Operational Dashboard technical implementation: default signed-in landing page, explicit case selection, source/validation/decision boundary, backend-derived demand/coverage/readiness/capacity summaries, corridor timeline, department demand, blockers, proposed blocks and observed-execution separation. TypeScript/lint pass and 9 workspace/report tests pass on a fresh isolated database.
- [ ] Operational Dashboard final browser interaction and 1440px/1920px visual acceptance; Next.js source compilation succeeds before the host `spawn EPERM` restriction.
- [x] Data Import & System Readiness technical implementation: department-scoped TMS/TDMS/SMMS JSON/CSV preview and hash-bound commit, persisted import outcomes, source-revision lineage, role-checked operational train/COA/freight intake, immutable snapshot coverage/freshness/COA-policy evidence and explicit unknown/blocking states. TypeScript/lint pass and 14 M2/M4/M5/workspace tests pass.
- [ ] Data Import & System Readiness final browser interaction and wide-screen visual acceptance; Next.js source compilation succeeds before the host `spawn EPERM` restriction.
- [x] Network, Resource & Policy Administration technical implementation: current network register and revision editor, named resource register, versioned profile editor, policy revision history, backend role/revision checks and explicit configuration boundaries. TypeScript/lint pass and 18 focused M3/M10/admin tests pass.
- [ ] Network, Resource & Policy Administration browser interaction and wide-screen visual acceptance; full Next.js build still stops at the host `spawn EPERM` restriction after source compilation.
- [x] Access & System Health Administration technical implementation: ADMIN-only current API/database state, migration revision, observed worker heartbeat, queue counts, read-only user roster and session facts. Migration 026; 30 focused backend tests, TypeScript and lint pass.
- [ ] Access & System Health Administration browser interaction and wide-screen visual acceptance.
- [x] Focused 2026-09-25 source/layout audit found and corrected health-badge semantics: `RESPONSIVE`/`ACTIVE` good, `DEGRADED`/`ABSENT`/`INACTIVE` bad. Targeted TypeScript and ESLint checks pass.
- [ ] M18 browser acceptance at 1440px/1920px remains open: the user-run read-only harness captured all five hero screens at 1440/1920/390 on a stale SIMULATED case. Its old report included expected navigation cancellations and handled difference 404s; the corrected H1 status and harness need a new capture. Role/failure/accessibility and supporting-screen review remain open.
- [ ] Supporting Tier B/C experiences, deployment, benchmark, backup/restore and complete M18 gate.
- [x] Deployment/recovery package technical implementation: pinned non-root backend and Next.js standalone images; PostgreSQL/migration/API/worker/web Compose stack; internal network and health ordering; worker heartbeat probe; checksum-bound backup; isolated non-empty-target-safe restore profile. Eight focused tests pass.
- [ ] Live deployment and recovery acceptance: Docker is unavailable on this host, so image build/start, HTTPS browser session, container health, actual backup and isolated restore remain unverified.
- [x] Repeatable M18 benchmark harness: real fair baseline and OR-Tools CP-SAT on identical seed-26027 candidate sets for 20/100/300 requests; actual statuses, bounds, gaps, runtimes, input/model hashes and negative/raw deltas persisted. Three focused tests pass.
- [x] Core compatibility demonstration evidence: explicit synthetic ENG/TRD rule creates a real shared AB candidate; removing the rule produces zero bundles and an evidence-backed COMPATIBILITY_UNKNOWN exclusion.
- [ ] Complete integrated A-B-C-D judge walkthrough: four requests including S&T and a competing resource, plan materialization, independent validation, visible failure, stale/replan flow and frontend screenshots.

Visual effort: Tier A H1–H5 exceptional; Tier B maintenance/schedules/replanning/scenarios/diffs/execution highly polished; Tier C import/audit/provenance/admin professional functional UI. Browser visual acceptance remains part of final M18 quality review. The user explicitly authorized source/layout review and continuation through H2 and Optimization State while browser tooling is unavailable.

H1/H2/Optimization implementation evidence (2026-09-23): `docs/evidence/M18-H1-progress.md` and `docs/evidence/M18-H2-Optimization-progress.md`. H3 evidence (2026-09-24): `docs/evidence/M18-H3-progress.md`. H4 evidence (2026-09-24): `docs/evidence/M18-H4-progress.md`. H5 evidence (2026-09-25): `docs/evidence/M18-H5-progress.md`. Weekly / Monthly evidence (2026-09-25): `docs/evidence/M18-Schedules-progress.md`. Replanning & What-if evidence (2026-09-25): `docs/evidence/M18-Changes-progress.md`. Revision Differences and Execution / Handback evidence (2026-09-25): `docs/evidence/M18-Execution-progress.md`. Reports/Audit evidence (2026-09-25): `docs/evidence/M18-Reports-progress.md`. Dashboard evidence (2026-09-25): `docs/evidence/M18-Dashboard-progress.md`. Data Import & System Readiness evidence (2026-09-25): `docs/evidence/M18-Data-Readiness-progress.md`. Network/Resource/Policy Administration evidence (2026-09-25): `docs/evidence/M18-Administration-progress.md`. Access/System evidence (2026-09-25): `docs/evidence/M18-System-progress.md`. M18 as a whole remains incomplete.

## Frontend rebuild — 25 September 2026

The user authorized a new visual/UX direction while protecting the existing backend. See `docs/M18_FRONTEND_REDESIGN.md` for research, decisions, scope and the remaining browser gate.

- [x] Research primary railway planning and enterprise/accessibility sources; identify the current layout and interaction weaknesses.
- [x] Implement grouped navigation, a compact role/context header, accessible account actions and responsive navigation.
- [x] Rebuild the shared timeline with overlap stacking, dated ticks, Fit/2x/4x scaling, visible missing-evidence states and an exact-time interval register.
- [x] Restructure Planning around a wide diagram and a searchable department work queue / contextual evidence rail.
- [x] Add the saved Corridor derivation sequence and direct source-interval inspection.
- [x] Link comparison diagram track/scale/horizontal position; preserve genuine KPI signs, units and same-snapshot checks.
- [x] Add saved setup/work/restoration diagrams and direct navigation to the existing controller decision form.
- [x] Apply the common visual system across supporting screens and rebuild the sign-in experience.
- [x] Verify backend/migration hashes unchanged and all 95 existing API/fetch call sites preserved.
- [x] TypeScript, ESLint and 14 production-component/presentation checks pass. Presentation fixtures come from archived SIMULATED backend evidence.
- [ ] Final browser interaction/visual acceptance: 15 real-backend hero screenshots have been inspected from `docs/evidence/browser-review/2026-09-25T18-34-36.495Z/`. One real H1 status contradiction was corrected; the post-fix capture and broader state/role/accessibility checks remain open.
- [ ] Full production build: source compilation passes; the host still rejects the Next TypeScript child process with `spawn EPERM`.
- [ ] Per-screen 1440px/1920px review, 390px navigation and 200% zoom; one stale SIMULATED PLANNER case has 15 captures, no page overflow, working timeline/evidence/mobile navigation and saved H3 metrics. Post-fix recapture, error/failure states, other roles and zoom remain open.

This rebuild is not yet visually accepted. M18 and the integrated SIH judge demonstration remain open.

### Five-hero visual review continuation

- [x] Add `web/scripts/review-heroes.mjs`: read-only real-backend screenshots at 1440/1920/390, timeline/evidence and mobile-navigation checks, overflow/browser/API error reporting, and blocked planning/controller writes.
- [x] Browser review harness syntax and ESLint checks pass; secure local-run instructions added in `docs/M18_BROWSER_REVIEW.md`.
- [x] H3 fresh-session comparison lookup now reads saved backend artifact indices and verifies the exact snapshot hash and both plan revisions; archived-backend regression check passes. The 95 original API/fetch call sites remain preserved; this fix adds read-only comparison/index GETs.
- [x] H3 preparation action now follows backend permissions: ADMIN/PLANNER/CONTROLLER can prepare; read-only roles see a disabled action. TypeScript, targeted ESLint and all 14 presentation checks pass.
- [x] H2 COA context wording clarified: a saved capacity calculation is not described as operational authority when no individual COA record intersects a window. Targeted TypeScript and ESLint pass.
- [x] Reachable user-started Next.js preview and fresh isolated PostgreSQL/FastAPI test service. The original local cluster remained untouched after recovery failed with a checkpoint-permission error.
- [x] Live authenticated proxy smoke: login/session, saved SIMULATED snapshot and CP-SAT proposal, occupancy, demand, 11 candidates, 3 capacity windows, `OPTIMAL` solver status, persisted `VALIDATED_COMPARISON`, and all H1–H5 routes returned HTTP 200. The smoke selector was corrected to choose a CP-SAT revision explicitly.
- [x] Run the read-only hero browser capture from normal PowerShell and inspect 15 screenshots for the five hero screens at 1440/1920/390; identify and fix the H1 saved-run status contradiction.
- [x] Focused visual polish based on the supplied reference: branded sign-in corridor motif and clearer first-screen hierarchy; distinct overview header and metric hierarchy. No operational values or API calls changed. Targeted TypeScript, ESLint and 14 presentation checks pass.
- [x] Post-H1 and branded sign-in/Overview capture: 20 read-only views, saved comparison metrics, timeline/evidence and mobile navigation; no page overflow, browser/API errors or blocked writes. H1 now shows recorded baseline COMPLETED and CP-SAT OPTIMAL.
- [x] Capture `2026-09-26T02-45-40.893Z`: 20 views with no page overflow; Overview workflow badges verified. Login hydration diagnostic identifies screenshot caret hiding (`caret-color: transparent`), now disabled in the harness. Console hydration errors now fail review status.
- [x] Capture `2026-09-26T02-54-42.969Z`: sign-in hydration warning absent; department labels and workflow badges readable on desktop/mobile. All 20 views have zero page overflow, browser exceptions, unhandled API errors and blocked writes. Saved H3 metrics remain visible.
- [ ] Finish role, failure, keyboard and 200%-zoom review, supporting-screen acceptance and production/deployment gates before M18 completion.

- [x] Focused H1 keyboard evidence: skip link, timeline scale and actual interval selection passed in `2026-09-26T03-05-31.928Z`.
- [x] H1–H5 720 CSS-pixel reflow proxy: all five screenshots inspected from `2026-09-26T03-09-17.603Z`; readable stacked layouts and no page overflow. Native 200% browser zoom remains a separate open manual gate.

- [ ] H1–H5 fresh-load API connection failure/recovery: `--failure-states` read-only harness implemented; browser execution and screenshot review pending.

- [x] Separate-database backend lifecycle replay: real intake/transitions, CP-SAT, validator, simulated approval, two completed requests and verified software handback; evidence `lifecycle-20260926T072523Z`. Explicit controlled fixture clock; preview unchanged.
- [ ] Current-date browser lifecycle and complete A–B–C–D judge demo remain open; backend replay does not satisfy those gates.

- [x] Current-date isolated SIMULATED backend replay and external API readiness: `lifecycle-20260926T072807Z`, API port 8001. Real inputs/solver/validator/approval/execution/handback; synthetic replay observations explicitly labeled.
- [ ] Current-date browser walkthrough on separate port 3001: frontend launch and inspection pending.

- [x] Role workspaces implemented: department-scoped dashboard and 3-page navigation; admin configuration dashboard; planner/controller/auditor primary actions; UI direct-route guard denies unsupported/unknown roles. Backend authorization unchanged. TypeScript and five-role boundary checks passed.
- [ ] Browser review of each role dashboard/navigation and direct-page denial remains open. This is UI workflow restriction, not a replacement for backend authorization.

- [ ] Five-role browser harness `review-roles.mjs --isolated-demo`: verifies login destination, dashboard heading, navigation, mobile primary action, direct-page denial and read-only behavior. Execution/visual inspection pending.

- [x] Five-role navigation/mobile/direct-route denial verified in `role-review/2026-09-26T08-10-41.965Z`: no exceptions, writes or page overflow.
- [ ] Role visual acceptance: visible punctuation corrected; planner/controller/auditor populated-case capture added. Updated browser capture remains pending.

- [x] Maintenance submission UI: department Validate/Submit controls use revision-checked backend lifecycle APIs.
- [x] Planning live intake: current request register, 30-second/focus/manual refresh, explicit unsubmitted and uncaptured states; saved snapshot demand remains separate. TypeScript and targeted ESLint passed.
- [x] Synthetic backend intake verification: RAISED → VALIDATED → PENDING_PLANNING; live register includes request; existing snapshot hash/content unchanged. Evidence `M18-live-intake-verification.json`.
- [ ] Browser acceptance of new intake/submission controls and planner snapshot-preparation UI remain open. New submitted requests are not automatically scheduled.

- [x] Planner snapshot preparation UI: explicit horizon/tracks, optional policy/replanning capture, draft facts inspection, manually reviewed source-declaration JSON, server-bound facts hash and new snapshot selection. TypeScript/targeted ESLint passed.
- [x] Isolated API verification: submitted request included in new draft; backend facts hash matches; altered declaration hash rejected; undeclared draft not CURRENT; existing execution lineage rejects ordinary session with USE_ROLLING_REPLAN_WORKFLOW. Evidence `M18-snapshot-preparation.json`.
- [ ] Browser acceptance of snapshot form and execution-aware replacement snapshot workflow remain open. No source completeness is inferred.

- [x] UI capture handoff: controller execution-capture action in Replan & what-if, planner link carries capture ID, snapshot form checks current/CAPTURED status before saving; rolling-replan path retained. TypeScript and targeted ESLint passed before notice-reset refinement.
- [x] Live boundary verification: planner capture denied 403; expired source horizon rejects controller capture 409 REPLANNING_TIME_OUTSIDE_HORIZON. No bypass. Evidence `M18-execution-capture-handoff.json`.
- [ ] Successful current-time capture/snapshot handoff and browser acceptance remain pending; demo source horizon expired.
