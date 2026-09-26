# RailSync AI — M18 UX Architecture and Design Proposal

**Status: approved with four required amendments; implementation authorized.**  
**Date:** 23 September 2026 · **Milestone:** M18 / P3 · **Version:** 1.1

This is the approved design specification, not evidence of implemented frontend behavior. The user approved implementation through the gates below. M18 remains incomplete. The design preserves the agreed backend architecture and human decision boundary.

## 1. Decision summary

Make RailSync a **corridor planning workbench**. Its central experience combines a track-and-time timeline, maintenance demand and linked evidence. A planner should be able to select a proposed block and understand its work, timing, resources, capacity context and validation state without opening five unrelated dashboards.

The five hero experiences are:

1. **Planning Workspace:** what can we coordinate, and what does the proposal contain?
2. **Corridor Availability:** where does usable capacity come from, and what limits it?
3. **Baseline vs RailSync:** what changed on identical facts, and how was it measured?
4. **Validation Center:** which configured checks passed or failed, with what evidence?
5. **Controller Review:** what exact revision am I reviewing, and what will this decision record?

Use restrained typography, a light operational canvas, compact information hierarchy and a consistent evidence inspector. Use the timeline as the primary visualization and a schematic corridor strip for orientation. Do not introduce a geographic map until coordinates and geographic provenance exist.

### Inspection findings and evidence

Inspected the detailed 43-page Build Contract, repository checklist and requirement traceability, decision records, M13–M17 API documentation, route/source contracts and the recorded M17 gate. References are collected in §15.

| Finding | Design consequence |
| --- | --- |
| Checklist records M1–M17 complete; M17 records 168 cumulative passing tests, migration 023 | Begin M18. These are historical test results, not a new test run or production-readiness claim. |
| Many immutable artifacts have GET-by-ID but no collection/search endpoint | Add bounded browse/read APIs before presenting navigable histories or review queues. |
| Requests, network, occupancy and coverage already have some collection reads | Reuse them; add pagination/scoping only where necessary. |
| Network contains topology and section distance, but no coordinates | Show ordered stations/sections/tracks; do not invent geography or continuous train trajectories. |
| Modification accepts existing candidate IDs | Use an alternatives picker; no free dragging that invents a new schedule. |
| Validation returns historical status plus current usability and blockers | Show both. A historical PASS can be unusable now. |
| Existing explanations contain priorities, rule references, resources and alternatives | Present those facts. Do not claim a causal optimality proof or precise binding constraint unless separately evidenced. |
| Current authentication is a bearer-token/role skeleton | Complete secure browser sessions and server-enforced scope checks in M18. Do not imply SSO exists. |
| Rules supply active priorities; no evaluated ML inference is deployed | Label scores “Rule priority”; do not present failure probabilities or SHAP results. |
| Availability has windows and selected exclusion/conflict evidence, but not a full boundary derivation graph | Add a provenance projection for explanatory layers; do not recalculate availability in React. |
| Existing freeze-context GET exposes the operational revision | Reuse this fact for review context; the approval transaction remains the authoritative concurrency check. |

**Document discrepancy:** Build Contract §6 describes a baseline without bundling. The later user instruction, ADR-005 and implemented M11/M15 comparison use the same candidate universe, including bundles, and complete constraints for both planners. Preserve that fair baseline. Record this clarification in project traceability when implementation is approved; do not weaken the baseline to produce a positive gain.

## 2. Product and authority boundaries

The visible workflow is:

```text
Department demand + operating facts
                |
       Frozen planning snapshot
                |
       Priority + capacity windows
                |
       Opportunities + coordination
                |
       Baseline / CP-SAT proposals
                |
       Independent validation
                |
       Controller proposal decision
                |
       Execution records / new planning state
```

The UI does not move any responsibility across these boundaries. It displays backend facts and sends explicit commands. The backend owns availability, candidate feasibility, optimization, validation, KPIs and authorization.

Always distinguish:

- **Source fact:** confirmed occupancy, an imported request, a recorded restriction.
- **Forecast:** a declared freight envelope, expected count and uncertainty semantics.
- **Computed proposal:** capacity windows, candidates, rule priority, selected blocks.
- **Validation evidence:** checks against configured prototype constraints.
- **Human record:** a controller decision or execution observation.

Use **“Approve proposal”**, never “Authorize train movement” or “Grant possession.” Show “Software proposal only; external railway authorization is separate” on review, approved-plan detail and exports. There is no invented external-authorization checkbox or integration.

An ordinary SIMULATED planning demonstration may record an isolated simulated controller approval. An isolated **what-if scenario** cannot record decisions or reservations. These are different scopes and must have different labels.

## 3. A — Information architecture and navigation

### Global shell

- Left navigation: compact RailSync wordmark, operational destinations, secondary records/admin links.
- Top context bar: selected corridor/track footprint, planning period, timezone, signed-in role and persistent source/simulation scope.
- Artifact header: proposal revision, snapshot reference, last successful refresh, freshness/review state. Show short IDs with full-copy action in provenance, rather than exposing long hashes throughout the workspace.
- Route and URL retain filters, selected revision and selected item. Refreshing the browser must recover the same saved artifact.
- Keep snapshot context fixed when reviewing a proposal. Current network/source changes appear as a distinct comparison or staleness notice, not silently mixed into historical facts.

### Primary destinations

```text
Planning                 default for planner
  Workspace · Opportunities · Coordination
Maintenance              default for department user
  Requirements · Import · Request history / priority
Corridor
  Availability · Operating facts · Data readiness
Validation
  Reports · Finding detail
Controller Review        default for controller
  Review queue · Revision review · Decision history
Evaluation
  Same-input comparison · Metric definitions
Schedules
  Weekly · Monthly · Exports
Changes & Scenarios
  Disruptions / replan · What-if · Revision differences
Records
  Snapshots / provenance · Execution / handback · Audit
Administration
  Network / assets · Resources / policies · Access / system health
```

No separate generic KPI home page is needed. Role-specific landing pages should surface work that needs attention, with links to the actual record. Counts must come from scoped backend queries.

## 4. B — User-role and workflow map

| User / question | Entry and workflow | Decision boundary |
| --- | --- | --- |
| Engineering, TRD, S&T: what work is required and ready? | Maintenance → create/revise requirement → prerequisites, footprint, deadline → lifecycle/import result → planning outcome | Department writes stay within backend permissions. No final block-time input. |
| Planner: where can work fit together? | Readiness → snapshot → corridor → opportunities → coordinated candidates → compute baseline and RailSync → inspect proposal → validate | Weights affect objective trade-offs, never hard feasibility rules. |
| Controller: what exactly am I deciding? | Review queue → exact revision → current report → resources/traffic/diff → reason → approve proposal, request a candidate change, reject or replan | Backend rechecks current hashes, scope, state revision and reservations atomically. |
| Execution recorder: what occurred and is the site restored? | Approved proposal → execution observations → interruption/remaining-work assessment → restoration evidence → release/continuation | Recorded completion is separate from planned work; release is a distinct verified action. |
| Management: what benefit is supported? | Evaluation → identical-input comparison → metric definitions → evidence export | Read-only presentation; no invented management role permissions. |
| Auditor: can I reconstruct this result? | Snapshot / provenance → run → revision → report → decision → execution / replacement lineage | Read-only history, scoped/redacted source details. Dedicated read-only permissions require explicit backend support. |
| Administrator: are sources and configuration usable? | Readiness, network/resources/policies, identity and worker health | ADMIN does not automatically substitute for CONTROLLER; enforce the actual route permissions. |

Management and auditor are product personas, not claims that new backend roles already exist. Existing verified roles include DEPARTMENT, PLANNER, CONTROLLER and ADMIN. Read-only access and corridor scope must be specified and tested before those personas receive access.

## 5. C — Design system specification

### Visual foundations

| Token / pattern | Proposed value and use |
| --- | --- |
| Canvas | `#F4F6F8`; quiet working surface |
| Surface | `#FFFFFF`; main workspace and inspectors |
| Primary text | `#172638`; headings and operational values |
| Secondary text | `#4B5B70`; captions and metadata |
| Structural border | `#D4DCE5`; grouping, not the only marker of interactive boundaries |
| Primary action | `#174E73` with white text; one dominant action per context |
| Focus | `#0067A6`, visible 2px outline with offset |
| Engineering | `#245CA6` + `ENG` label |
| TRD | `#815006` + `TRD` label |
| S&T | `#69489A` + `S&T` label |
| Passed check | `#176044` + PASS/check text |
| Failed check | `#A12632` + FAIL/error icon |
| Attention / stale | `#825000` + explicit state text |
| Typography | Self-hosted Source Sans 3 if packaging permits; system sans fallback. 14px body, 12px minimum supplementary text, 16px section titles, 24px page titles. Tabular numerals for times/metrics. |
| Spacing | 4/8/12/16/24/32px scale; 4–6px panel radius, minimal shadow |
| Density | 40px default table row; optional 32px compact desktop row. Comfortable touch controls on small screens. |

These are proposed tokens, not verified contrast results. Contrast-test actual foreground/background pairs before accepting components; do not use department color as the only carrier of meaning.

### Components and interaction conventions

- **ContextBar:** corridor, period, timezone, scope and artifact revision.
- **StateSummary:** job state, solution state, validation state and human decision shown separately.
- **CorridorTimeline:** shared time scale, lane groups, selection, focus, legends and accessible event list.
- **DemandList:** department, request, readiness, deadline, work duration, scheduling outcome.
- **EvidenceInspector:** Summary / Timing / Resources / Rules / Provenance; opens through the same selection model on all hero screens.
- **StageBar:** exact setup, work and restoration segments. Tiny stages retain accurate lengths; enlarge the hit target, not the visible duration.
- **FindingRow:** severity/status, rule, affected objects, exact interval and source links.
- **MetricRow:** unit, baseline, RailSync, signed delta, denominator/formula and claim state.
- **DecisionForm:** reason, expected revision and explicit outcome; no optimistic success state.
- **RevisionDiff:** preserved / moved / added / removed / residual work, with source and target times.
- **SourceBadge:** SIMULATED / IMPORTED / scenario, origin and revision accessible in details.

Forms retain user input after errors, associate messages with fields and focus the first invalid field. Drawers have labeled headings, Escape handling and return focus. Use a modal only for a decision that needs a bounded review step; extended investigation belongs in a panel or page.

### Accessibility and responsive behavior

Target WCAG 2.2 AA as a design/release criterion; compliance remains unverified until testing. Support keyboard-only selection and actions, visible focus, meaningful headings, labeled controls, screen-reader announcements for result changes and reduced motion. All charts/timelines have a synchronized accessible table with the same facts and selection.

Desktop ≥1280px: navigation + demand pane + timeline + optional inspector. At 1024–1279px: collapse navigation; inspector overlays on demand. Below 1024px: timeline/list tabs with full-width detail. At narrow phone widths, show a useful readable event list and complete decision details; do not squeeze four panes into miniature controls. Decision details must remain available before submission. Test zoom/reflow at 200% and keyboard operation, including dialogs.

## 6. Signature timeline specification

**Coordinate system:** time on the horizontal axis; ordered sections/tracks on vertical lanes. Section distance can appear as context, but no fabricated train interpolation between section entry/exit facts. This is a track occupancy timeline, not a signalling diagram.

Each expanded track group has aligned sublanes:

1. Confirmed train occupancy and configured clearance margins.
2. Freight forecast envelopes with pattern fill and issued/coverage metadata.
3. COA access context, restrictions and existing commitments.
4. Backend-computed capacity windows.
5. Proposed possessions; expanded child rows show department tasks and resources.

Do not place all layers on top of one another. Default to relevant operational layers and provide an explicit layer control. Hiding a layer changes presentation only; it never changes rules or computed capacity.

| Item | Representation |
| --- | --- |
| Confirmed occupancy | Solid dark neutral bar, train ID, entry/exit on focus |
| Clearance | Bordered/light shoulder around the occupancy bar; exact policy in evidence |
| Freight | Hatched envelope, `FORECAST` text; no invented precise arrival line |
| Restriction | Crosshatch with type and rule reference |
| COA | Thin labeled access band; semantics shown as ACCESS_ENVELOPE / TRAFFIC_FREE / UNKNOWN |
| Capacity window | Thin teal outline labeled `Computed window`; not “safe to work” |
| Unselected opportunity | Dashed outline in opportunity mode |
| Selected block proposal | Solid outline with PROPOSED label; individual work uses department labels |
| Approved software proposal | APPROVED PROPOSAL badge and decision reference; distinct from validation PASS |
| Frozen work | Lock marker and freeze evidence; never draggable |
| Validation finding | Local callout and linked finding; not inferred from overlap pixels |
| Replan difference | Before/after rows or ghost outline with explicit diff legend |

Use timezone-aware timestamps; default display Asia/Kolkata with the full date at midnight boundaries. Show the exclusive end boundary in interval details (`start inclusive, end exclusive`). The browser does not round work to a more convenient size. Display conservative rounding policy from the saved computation. Full-precision timestamps remain inspectable.

Support fit-to-horizon, day/6-hour/2-hour zoom, keyboard panning, “Go to selected block,” track filters and linked request highlighting. Selecting a bundle highlights every affected track and task. A resource subview uses named resource lanes with the same time scale. Weekly/monthly overview is an aggregation for navigation; selecting a day opens exact intervals.

## 7. D — Complete screen inventory and priority

Priorities below are **M18 internal build waves**, not replacements for completed P0–P3 milestones. H1–H5 identify the five heroes.

| Screen / proposed route | Main content / actions | Wave |
| --- | --- | --- |
| Secure sign-in / session (`/sign-in`) | Prototype identity, role, session expiry; no hardcoded privileged token | Foundation |
| H1 Planning (`/planning`) | Demand, track timeline, proposal, evidence, run/validate/review entry | 1 |
| Requirement register (`/maintenance`) | Department filters, readiness, lifecycle, persisted outcomes | 1 minimal; 6 full |
| Requirement detail/editor (`/maintenance/:id`) | Revisions, scope, stages, deadlines, resources, predecessors, rule priority | 1 minimal; 6 full |
| Source import (`/maintenance/import`) | CSV/JSON preview, row errors, source identity, explicit commit | 6 |
| H2 Corridor (`/corridor`) | Operating layers, capacity boundaries, multi-track intersection | 2 |
| Data readiness (`/corridor/readiness`) | Coverage, freshness, COA semantics, unknown/blocking declarations | Foundation + 2 |
| Operating source detail (`/corridor/sources/:type/:id`) | Dated occupancy, freight/COA provenance and revisions | 2 |
| Opportunity explorer (`/planning/opportunities`) | Timed candidates and exclusions linked to request/window | 2 |
| Coordination (`/planning/coordination`) | Bundle timing, explicit compatibility, named resources, excluded combinations | 2 |
| H3 Comparison (`/evaluation/:id`) | Same-input check, paired timelines, KPI definitions, solver evidence | 3 |
| H4 Validation (`/validation/:id`) | Historical report, current usability, categories, interval evidence | 4 |
| H5 Review queue/detail (`/review`, `/review/:id`) | Attention queue, decision packet, candidate modification, decision record | 5 |
| Weekly schedule (`/schedules/weekly/:id`) | Exact calendar period, firm/tentative/stale proposal status, exports | 6 |
| Monthly schedule (`/schedules/monthly/:id`) | Calendar overview, daily drilldown, coverage limits | 6 |
| Disruptions / rolling replan (`/changes`) | Events, source reconciliation, frozen work, new proposal job | 6 |
| Replacement differences (`/revisions/:id/diff`) | Old/new intervals, preserved work, residual stages, supersession evidence | 6 |
| What-if (`/scenarios/:id`) | Typed changes, real scenario run, isolated results; no decisions | 6 |
| Scenario impact (`/scenarios/:id/impact`) | Changed inputs and raw deltas; no optimizer-gain claim | 6 |
| Execution / handback (`/execution/:id`) | Observations, interruption, remaining work, verified restoration/release | 6 |
| Snapshot / run history (`/records`) | Searchable immutable artifacts and lineage | Foundation + 6 |
| Provenance (`/snapshots/:id`) | Source hashes, configuration, rules, code/model references when recorded | 6 |
| Audit explorer (`/audit`) | Actor/action/reason/related artifact, scoped export | 6 |
| Network/assets (`/admin/network`) | Topology, asset footprints, electrical zones, restrictions | 6 |
| Resources/policies (`/admin/resources`) | Named units, profiles, calendars, qualifications, compatibility revisions | 6 |
| Access/system (`/admin/system`) | Session/access administration and truthful API/DB/worker health | 6–7 |

The functional inventory remains in scope, with unequal visual effort:

- **Tier A — exceptional:** H1–H5; H1 receives disproportionate design/refinement effort.
- **Tier B — highly polished:** maintenance requirements, weekly/monthly schedules, replanning, what-if, revision differences and execution/handback.
- **Tier C — clean professional functional UI:** imports, provenance, audit, network administration, resources/policies and system health.

Do not expand the navigation, entity model or high-level architecture. No OpenRailwayMap, RailRadar, additional ML/ANN, chatbot, live train animation or decorative railway graphics during M18.

## 8. E — Data/API dependency map

Paths below are relative to `/api/v1`. Existing routes are source-inspected; proposed additions are clearly separate. All frontend requests must use typed, reviewed contracts.

| Experience | Existing contracts | Required additions or integration work |
| --- | --- | --- |
| Identity/shell | `GET /me`, `/health`, `/ready` | Secure browser-session adapter, CSRF protection for cookie writes, scoped access tests, explicit session expiration |
| Demand/import | GET/POST `/maintenance-requests`, GET/PATCH by ID, transitions, POST `/imports/preview`, `/imports/{id}/commit` | Bounded pagination/filtering as needed; persisted import-history retrieval |
| Corridor inputs | GET `/network`, `/assets`, `/operations/occupancy`, `/operations/coverage`; source write routes | Snapshot-bound projection; distinguish current source inspection from frozen planning facts |
| Snapshot/readiness | POST `/snapshots`, GET by ID | Browse/readiness projection with source completeness/authority blockers; unknown remains blocking |
| Priority/capacity/candidates | POST `/priority-assessments`; POST/GET availability, opportunities and coordinated candidates | Artifact relationship index and boundary provenance; preserve existing rule/calculation ownership |
| Compute proposal | POST/GET `/planning-runs`; internal proposal pipeline already reused by M16/M17 | General durable planning-session orchestration for the UI, shared candidate/config IDs for baseline and CP-SAT, idempotent resume after refresh/retry |
| Plan/explanations | POST/GET `/plan-revisions`; POST/GET explanations | Paginated plan/run/revision index and typed nested response contracts where currently loose |
| Validation | POST/GET `/validation-reports`; `usable_for_review`, `current_blockers` | Report index, source/finding labels and bounded evidence lookups; no frontend feasibility check |
| Review | POST decisions/modifications/replan; GET revision/decisions, freeze-context and differences | Consolidated review-context projection; use existing operational revision from freeze-context, bind to hashes and current report |
| Evaluation | POST/GET `/plan-comparisons`, GET export | Browse/selection of eligible comparisons; do not pick unrelated runs based on creation time |
| Calendar | POST/GET `/planning-schedules`, GET export JSON/CSV | Saved-artifact index; period selection with full-horizon guard |
| Changes/execution | Disruption, freeze-context, execution, captures, reconciliations, releases, rolling-replan routes | Discoverable event/history lists, typed form mapping and fresh review context |
| What-if | POST/GET scenarios; POST impacts and GET impact by ID | Browse scenarios/impacts, show linked job statuses and unchanged source scope |
| Audit/admin | Immutable events and source revisions exist in storage; several configuration write routes exist | Authorized audit/resource/policy/history read APIs; user management and worker health contracts where absent |

### Proposed contracts to settle before coding screens

These route names are proposals, not existing APIs:

- `GET /workspace-index`: bounded cursor pagination over visible artifacts, stable ordering, filters, scope and related IDs. May be split into ordinary resource collection routes during contract design.
- `POST /planning-sessions`, `GET /planning-sessions/{id}`: persist the requested pipeline and actual stage/run/artifact references. No fabricated percentage progress. Retry uses an idempotency key; restarting cannot fork silent duplicate runs.
- `GET /snapshots/{id}/workspace`: typed projection of snapshot facts plus referenced computations. It returns identifiers and display labels without re-solving or silently updating frozen facts.
- `GET /plan-revisions/{id}/review-context`: exact revision/hash, scope, current operational revision, report usability, blockers, decision history and permitted actions. Server still rechecks everything at write time.
- `GET /audit-events`: authorized, paginated immutable history with sensitive fields restricted.

Availability explanation evidence needs source IDs and the particular boundary/margin/rule used. Prefer a stored or hash-bound backend projection of existing computation inputs. It must not create a second interval algorithm in the UI. A COA/occupancy overlap is displayed as recorded source evidence; whether it is contradictory depends on declared COA semantics and validator findings.

### Frontend engineering shape after approval

Use the contracted Next.js/TypeScript frontend, separate from the modular FastAPI backend. Organize features by domain: planning, corridor, maintenance, validation, review, evaluation, schedules, changes and records. Shared components contain presentation behavior, not domain feasibility predicates.

Generate or check API types against FastAPI OpenAPI, adding typed response models where necessary. Keep URL state for selection/filter context and server-query state keyed by artifact ID/hash/scope. Do not cache across users or scopes. Poll real job state with backoff and cancellation; stop on terminal state. Do not invent completion percentages.

Use a same-origin server-side session/API boundary so service credentials do not enter browser storage or public bundles. Auth writes need CSRF protection, origin checks, expiry and server RBAC. Exact libraries and compatible versions will be resolved and locked during approved implementation; this design does not claim current library/version compatibility.

Render timeline geometry from actual intervals, initially with inspectable SVG/DOM and a synchronized event list. Introduce virtualization only after profiling shows a need, retaining keyboard selection and stable IDs. Do not adopt a heavy charting framework merely for decoration.

## 9. F — Five hero-screen specifications

### H1. Planning Workspace

**User question:** what maintenance can fit, which work can share a block, and what is being proposed?

```text
RailSync | Corridor / tracks | Period · Asia/Kolkata | SIMULATED | Role
Nav      | Proposal revision · snapshot · freshness · job / validation state
         |--------------------------------------------------------------
         | Maintenance demand | Track-and-time workspace | Evidence
         | ENG / TRD / S&T    | confirmed occupancy      | selected block
         | readiness/deadline | freight / restrictions   | task stages
         | scheduled/deferred| capacity / proposal       | resources/rules
         |                   |                          | alternatives
         |--------------------------------------------------------------
         | Selected-work details / deferred reasons / computation history
         | Configure run · Compute proposal · Validate · Open review
```

The center receives the most space. On a 1440px display, start with approximately 184px navigation, 264px demand and a 340px inspector opened only when selected; the timeline uses the remaining width. The inspector may collapse to keep the time context legible.

**Work Readiness:** Each requirement shows READY / CONDITIONAL / NOT READY only from a backend assessment tied to the selected snapshot/candidate context. Link prerequisite, named-resource and isolation/disconnection evidence. READY means ready within the stated planning context, not executable or externally authorized. Missing/unknown required evidence is never READY; show CONDITIONAL with the unresolved evidence, or NOT READY for a known blocking condition. A pending assessment is explicitly “Readiness not assessed.” Readiness, rule priority and scheduled/deferred outcome are separate fields. No second readiness algorithm belongs in the frontend.

**Railway access requirements:** On the integrated block and evidence inspector, explicitly show LINE/TRAFFIC BLOCK, POWER BLOCK / ELECTRICAL ISOLATION and S&T DISCONNECTION where supported by request/snapshot facts. Map `block_required`, `power_block_required`, `isolation_zone` and `signalling_state` through a typed backend projection. Display required / not required / unknown separately from verified provision. A requirement badge must never imply a grant, isolation completed or disconnection performed. Department identity alone does not establish access needs.

**Default information:** corridor, exact period, source scope, request count from the selected snapshot, data-readiness blockers, active artifact revision, actual job/solver/validation statuses. No giant promotional KPI cards.

**Interactions:** select a request to highlight its footprint, selected candidate and genuine alternatives; select an integrated block to expand department work and named resources. A deferred request opens recorded exclusions and any retained alternatives. Missing explanation is “Explanation not generated,” not a generated-looking narrative.

**Run action:** opens a short configuration sheet with horizon, required footprint and policy/configuration versions. Advanced objective weights have labels/units and never appear as safety sliders. The service persists one planning session referencing the same candidates/configuration for both planners. Job completion makes a proposal inspectable; validation and review remain separate explicit stages.

**Modification:** “Explore alternatives” selects existing candidates and previews exactly which requests/times/resources change. “Create revised proposal” persists a child revision; revalidation is required. Frozen work cannot be removed. Unsupported arbitrary time changes direct the user to new facts/configuration and recomputation.

**Acceptance:** selecting any visible block resolves to the saved assignment and exact task/resource intervals; refresh restores the artifact; no candidate means no invented bar; UNKNOWN/INFEASIBLE cannot display a successful proposal. Keyboard users reach the same detail through the event list.

### H2. Corridor Availability

**User question:** why is this window usable, and why does a request fail to fit?

Use a full-width layered timeline with a narrow footprint selector. The evidence inspector explains the selected boundary in ordinary language, alongside exact timestamps and references.

```text
Selected tracks and electrical footprint
COA context            [declared allowed intervals]
Confirmed occupancy    [trains plus margin shoulders]
Freight / restrictions [forecast envelopes and restrictions]
Computed capacity      [backend windows]
Request duration       [setup | work | restoration, exact candidate if present]
```

**Interactions:** select a window to inspect the COA context, nearest blocking records, margin policy, rounding and per-track intersection. Select multiple tracks to inspect backend-computed shared capacity. Toggle a visual layer without changing the computation. Policy changes require an explicit new computation with recorded configuration.

**Critical distinction:** a window alone does not establish resource or work compatibility. The label is “Capacity window”; task feasibility is shown only through candidate and validator evidence. A high priority cannot extend a window.

**States:** missing COA coverage remains unknown; forecast absence is not zero freight; restricted tracks retain clear labels. Overlapping source records are presented with the validator's interpretation, not silently called a conflict count or ignored.

**Acceptance:** a hand-checkable fixture explains an exact fit and oversized exclusion using actual stages and backend outputs. Midnight, multiple tracks and electrical-zone footprints remain intelligible. Every boundary explanation links to persisted evidence; no client-generated availability result.

### H3. Baseline vs RailSync

**User question:** what changed because of coordination/search on the same facts?

Top: comparison eligibility and snapshot/configuration identity. Middle: synchronized baseline and RailSync timelines with matching track order and horizontal scale. Bottom: compact metric table and request-level differences.

Columns: Metric | Definition/unit | Baseline | RailSync | Absolute change | Improvement, where meaningful. Open any row for numerator, denominator, formula, metric version and saved interval evidence.

**Primary measures:** scheduled requests, mandatory/on-time coverage, possession count, reserved track-minutes, temporal work utilization and freight exposure. Label counts as planned/scheduled, not completed. Measured train delay is unavailable unless measured evidence exists; maintenance-only track availability is not asset reliability.

**Honest comparison:** show zeros, nulls, negative gains and unchanged results. Baseline zero gives `N/A` percentage, with absolute delta still visible. A no-incumbent result gives unavailable metrics, not a fictitious efficient empty plan. Descriptive counts such as task work minutes or bundled tasks do not automatically get green “better” arrows.

**Solver panel:** actual status, objective, best bound, runtime and generated/pruned candidate scope. State “Optimal within generated candidates” when warranted. Rule references and objective terms are evidence, not proof of a unique causal explanation.

**States:** distinguish historical comparison eligibility from `current_claims_permitted`. Stale validation retains historical metrics with an explicit current-use block. Same-scenario comparisons carry isolated-simulation scope; source-versus-scenario impacts are a different view with changed-input warnings and raw deltas.

**Acceptance:** table values match saved M15 metric outputs exactly; mismatched inputs are blocked server-side; negative and zero-baseline cases are visibly tested. Shared bundles remain available to the legitimate first-feasible baseline.

### H4. Independent Validation Center

**User question:** which configured constraint failed, where, and what evidence supports that result?

Top banner has two fields: **Recorded result: PASS / FAIL / ERROR** and **Current review use: usable / blocked**. Include checked time, exact revision and current blockers. Keep “Configured prototype constraints; not railway safety certification” next to the result.

Left: categories (provenance, coverage, timing, infrastructure, traffic, compatibility, resources, commitments, data quality). Center: findings ordered by review impact, with rule code and affected items. Right/lower panel: interval or source evidence for the selected finding.

**Examples of presentation, conditional on actual findings:** train and possession rows at the same scale for overlap; named-resource demand rows for a crew conflict; requested versus declared isolation footprints; old versus current source reference for staleness. If a finding lacks an interval, show the missing declaration or record; never draw a plausible conflict.

**Actions:** open source/assignment, export available evidence, revalidate eligible revision, return to planning. No “ignore and approve” control. A missing report is “Not validated”; an exception is ERROR, not PASS with an empty findings list.

**Acceptance:** each deliberately corrupted plan in the test suite yields visible linked FAIL/ERROR evidence. Historical PASS with expired/source-changed data is blocked. Filtering findings must not change the overall result or hide the total/current blockers.

### H5. Controller Review

**User question:** what exact software proposal am I reviewing, what are its consequences, and is its evidence current?

Use a decision packet rather than a generic dashboard: block summary and compact timeline; affected requests/departments; named resources; validation evidence; current-state/freeze information; changes from previous revision; reasoned decision form.

The persistent decision strip names the exact revision, simulation scope and current usability. Actions: **Approve proposal**, **Modify proposal**, **Reject proposal**, **Replan**. A planner can inspect but cannot submit a controller-only decision. What-if scenarios show “Scenario results cannot be approved” with links back to source, not a disabled button that appears temporarily recoverable.

**Approval sequence:** fetch current review context → review the exact packet → enter reason → submit idempotency key, expected plan hash, expected operational revision and report ID → server transaction → show persisted decision ID and resulting state. A network timeout is “Decision result unconfirmed”; resolve using the same idempotency key or fetched record before allowing another logical submission.

**Concurrent change:** on a 409, retain the reason, mark the packet outdated and refresh the difference/context. Do not automatically resubmit an approval against a changed revision. Staleness while the page is open immediately removes the usable state when detected; the server remains authoritative even between refreshes.

**Modify/replan:** candidate changes create a child revision and require new validation. Same-snapshot rerun and changed-fact rolling replanning are separate options. Replacements show preserved/frozen work and the decision being superseded; source reservations remain until the replacement transaction succeeds.

**Acceptance:** two competing approvals result in at most one valid backend commit; stale/hash/report mismatches remain visible; API errors cannot show success. Approved software proposal is visually distinct from external railway authorization and actual execution.

## 10. State and failure design

| State | UI behavior |
| --- | --- |
| Loading | Skeleton structure with labels; no sample numbers or placeholder computed bars |
| Empty | State what is absent in the selected scope; provide the relevant permitted input action |
| Partial facts | Show available facts, identify missing sources/coverage, block dependent claims/actions |
| QUEUED/RUNNING | Actual job state and elapsed time; no invented progress percentage |
| COMPLETED | Worker finished; show solver, incumbent, validation and decision separately |
| UNKNOWN / no incumbent | No scheduled-plan claim; diagnostics and rerun configuration available |
| INFEASIBLE | Actual solver status, evidence and candidate-scope limits; no fabricated conflict explanation |
| FAILED / validator ERROR | Distinct computation/check failure, preserved artifact and recoverable action |
| Stale | Historical output remains inspectable; current review/claim use is blocked where backend says so |
| API/offline | Error with last-successful-refresh time; cached history clearly labeled; no writes or authority claims from cache |
| Forbidden | Clear role/scope explanation; backend remains authoritative on direct requests |
| Scope mismatch | Stop related data assembly; never combine records from different snapshots/scenarios |

Freshness is not inferred solely from client clock or absence of an invalidation event. Use server report usability/source checks. Display an unknown state when those cannot be obtained.

## 11. Numbered M18 implementation sequence and gates

**Design approval received. Begin step 1; preserve the per-hero approval gates.** At each step save source identity, exact commands/results, backend artifact IDs/hashes, representative screenshots and limitations. The next step starts only after its predecessor's automated checks and explicit expected-output review pass. Existing M1–M17 tests remain regression requirements.

1. **Contract and security preparation.** Record the baseline clarification; settle typed response/read projections, artifact browsing, planning-session orchestration and browser auth. Implement only required gaps, preserving existing algorithms. Gate: API authorization, scope/pagination, hash binding, idempotency, orchestration recovery and truthful stage output tested against PostgreSQL.
2. **Design foundation and global shell.** Implement tokens, navigation, context/state patterns, forms, focus behavior and typed API client. Gate: no public credentials; authenticated role/scoping behavior; session failure handling; keyboard/contrast checks; no fabricated data fallback.
3. **H1 Planning Workspace.** Build the track timeline, minimal real maintenance input/detail, request linkage, evidence inspector and real computation journey. Gate: saved values/timestamps match API artifacts; request selection, refresh, empty/error/no-incumbent states and timezone boundaries tested. Critically inspect hierarchy, density and domain language before continuing.
4. **H2 Corridor Availability and coordination detail.** Add explanatory layers, boundary provenance, opportunities, bundle/resource view and readiness. Gate: exact/oversized fit, multi-track, midnight, forecast/COA unknown and compatibility-disabled cases; verify displayed exclusions and resources against saved output. Perform visual/keyboard review.
5. **H3 Baseline comparison.** Implement paired timelines, metric definitions, signed changes and claim scope. Gate: same-input eligible case, mismatch rejection, zero/null/negative results, stale reports and isolated-scenario labels. Review whether changes are intelligible without marketing copy.
6. **H4 Validation Center.** Implement categories and linked evidence. Gate: real backend corrupted-plan tests, FAIL/ERROR/stale distinction and no-report state. Review whether a user can locate the actual cause without reading raw JSON.
7. **H5 Controller Review.** Implement decision packet, existing-candidate modification, concurrency/retry handling and replacement context. Gate: create → plan → validate → approve proposal → export on the real backend; duplicate/timeout/stale/concurrent approval and forbidden-scenario actions tested. Inspect clarity of human authority.
8. **Complete supporting workflows.** Full maintenance/import, schedules, changes/scenarios, differences, execution/handback, provenance/audit, network/resources and administration. Gate: end-to-end flows for each supported action, immutable period exports, preserved frozen work, scenario isolation and exact actual-versus-planned distinction.
9. **Deploy and rehearse.** Package Next.js, FastAPI, worker and PostgreSQL with migrations, secure configuration, reverse proxy/TLS, health checks and backup/restore procedure. Gate: clean install, worker interruption/recovery, backup restoration and complete local synthetic demonstration without remote dependencies.
10. **M18 release evidence.** Run cumulative tests, browser acceptance, accessibility checks and declared benchmarks. Record defects/limitations and evidence manifests; update checklist/traceability only after the full gate. M19 remains optional and does not delay the core release.

### Required visual-quality gate after each hero

After H1, H2, H3, H4 and H5, STOP implementation of the next hero. Capture representative **1440px and 1920px** screenshots, including important empty, failed and stale states. Inspect visual hierarchy, density, railway-domain credibility, usability, accessibility and generic-dashboard appearance. Record a UX critique, correct issues, rerun affected checks, and present screenshots and evidence for **user visual approval**. Only after functional tests and that approval may the next hero start. Automated tests alone do not satisfy visual acceptance. H1 is the first major acceptance checkpoint; do not build all five before showing the result.

### Wave-6 execution/handback amendment

Keep execution details out of H1. The existing execution screen must distinguish **planned block → recorded actual availed/granted block → actual work intervals → restoration/handback → completed / partial / not executed**. Present only supported observations, their source and scope. A software proposal approval is never an actual railway block grant. If actual-grant/availment or handback fields are unavailable, show “Not recorded / unsupported by current source” rather than infer them from planned intervals or controller decisions. Existing execution/reconciliation/release records remain authoritative; do not introduce a new large block-lifecycle subsystem.

Model allocation follows the requested workflow: Astra High for difficult timeline/interaction design and the first hero review; Sol High for feature integration and refinement; Luna Medium for bounded repetitive components, styling and straightforward tests after contracts are settled. This is a task-allocation recommendation, not a claim about account access or a model switch.

## 12. Verification and release acceptance

The SRS release criterion is broader than a working browser build. Retain AT-18 and NFR-01 through NFR-10 from the Build Contract. Unit/component mocks are permitted for isolated UI testing but never power acceptance or demonstration.

### Mandatory evidence

- Browser create → snapshot/plan → inspect → independently validate → controller proposal decision → export, with UI values checked against persisted backend artifacts.
- Contract tests for new read APIs, session/role/department/corridor scope, error envelopes, pagination and mixed-snapshot rejection.
- UI tests for half-open intervals, midnight, date/timezone display, tiny setup/restoration stages, frozen work, null metrics, negative gains and no-incumbent states.
- Real-backend tests for stale reports, wrong hashes, conflict responses, duplicate submissions, interrupted jobs and scenario isolation.
- Keyboard and screen-reader review of the five hero flows; automated accessibility checks and screenshots at desktop, tablet, narrow layout and 200% zoom.
- A source-to-screen evidence sample for each hero: source/snapshot ID, run/revision/report IDs, response values and matching screenshot/table values.
- Reproducible release manifest and backup/restore proof. If Git writes remain unavailable, record that explicitly and use source SHA256 manifests; do not claim a commit was created.

### Benchmarks — targets, not achieved results

Build Contract §30 specifies provisional CRUD p95 <500ms for 20 concurrent demo users; snapshot/window generation <5s for the declared weekly fixture; solver budgets 30s weekly and 120s monthly, returning honest status at the limit. Benchmark up to 300 requests with reported candidate caps, hardware, versions, repeated-run methodology and actual outcomes. These are not guarantees and are not measured in this design review.

Also measure timeline selection/filter/render behavior on those fixtures. Choose a frontend interaction threshold during step 2 based on declared test hardware; report actual measurements rather than assuming a chart library is fast enough.

### Usability release questions

Can a planner explain a selected block's footprint and setup/work/restoration? Can a controller identify the exact report and revision? Can users distinguish forecast from occupancy, planned from completed, and simulated proposal approval from external authorization? Can a failure be understood from evidence? Can Engineering/TRD/S&T see compatible co-work and why another request was deferred? Every answer needs observation or test evidence, not a design assertion.

## 13. Demonstration narrative

Use a **SIMULATED** A–B–C–D fixture with ENG-01, TRD-01, SNT-01 and a competing-resource task. The Build Contract's hand-checkable 80-minute window/shared-work example is a fixture expectation, not a hardcoded UI result. Compute every displayed window, bundle, selection, report and KPI through the real backend.

1. Show data scope/readiness and the department maintenance requirements.
2. Explain the capacity boundary on the corridor timeline.
3. Inspect allowed ENG/TRD coordination, stages and actual named resource allocation.
4. Run both planners on identical inputs and inspect genuine selections/deferrals. An equal result is acceptable.
5. Open rule priority contributions and scheduling evidence.
6. Validate; use a separate deliberately corrupted test artifact to show a real finding without changing the valid proposal.
7. Compare actual metrics, including unchanged or worse measures.
8. Record a simulated controller proposal decision; show its exact revision and authority boundary.
9. Demonstrate an **isolated what-if** change separately from a **SIMULATED source disruption** that stales the source plan and triggers frozen-work replanning. Do not imply that an isolated scenario modifies source state.
10. Export schedule, comparison and available evidence; rehearse worker recovery and truthful infeasibility.

Run a compatibility-disabled variant to verify the bundle disappears. Then scale labeled fixtures to 20, 100 and 300 requests with measured candidate counts. A positive optimizer improvement is not a condition of demo success; trustworthy coordination and evidence are.

## 14. Design-review checklist and approval scope

- [x] Inspect governing Build Contract and recorded milestone state.
- [x] Inspect backend routes, payload boundaries and relevant decision records.
- [x] Define information architecture and role workflows.
- [x] Specify design tokens, components, responsive behavior and accessibility targets.
- [x] Map complete screen inventory to implementation waves.
- [x] Map existing API contracts and identify necessary additions.
- [x] Specify all five hero experiences and failure behavior.
- [x] Define ordered implementation, evidence gates and release/demo criteria.
- [x] User approves the design direction with the four amendments recorded in version 1.1.
- [ ] H1 functional gate and user visual approval (1440px/1920px + failure states).
- [ ] H2–H5 each pass their own functional and user visual approval gate.
- [ ] Implementation steps 1–10 pass their gates.
- [ ] M18 complete.

**Approval recorded:** the user accepted the timeline-led workbench and implementation sequence with the four targeted amendments above. Start implementation; no further architecture approval is needed. User approval is still required at each completed hero visual checkpoint. M18 completion requires the full release gate.

No design decision requires a trained model, live railway connection, geographic map, quantum component or alternate high-level architecture. Questions about authentic operational rules remain fail-closed under the existing contract; synthetic fixtures must stay labeled.

## 15. Repository evidence and source references

Primary design source: `E:/sih_codex_train/RailSync_AI_Solution_SRS_Build_Contract.pdf`, especially §§6, 18–24, 28, 30–32, 35–36 and 39. User's latest M18 directive adds the design-first approval gate and five hero experiences. The earlier basic SRS does not override the detailed contract or later user instructions.

Read-only repository references used in this review:

- `E:/sih_codex_train/CHECKLIST.md`
- `E:/sih_codex_train/docs/REQUIREMENT_TRACEABILITY.md`
- `E:/sih_codex_train/docs/DECISIONS.md` (especially ADR-005 through ADR-008)
- `E:/sih_codex_train/docs/evidence/M17.md`
- `E:/sih_codex_train/docs/M13_DECISION_SUPPORT_API.md`
- `E:/sih_codex_train/docs/M14_SCHEDULES_API.md`
- `E:/sih_codex_train/docs/M15_EVALUATION_API.md`
- `E:/sih_codex_train/backend/railsync/main.py`, `auth.py`, `requests.py`, `network.py`, `operations.py`, `snapshots.py`
- `E:/sih_codex_train/backend/railsync/planning.py`, `availability.py`, `decision_support.py`, `validation.py`, `validation_schema.py`
- `E:/sih_codex_train/backend/railsync/execution.py`, `rolling_replans.py`, `what_if.py`

Version 1.0 was a read-only review. Version 1.1 records user approval and four targeted amendments, and is copied to `docs/M18_UX_DESIGN.md` in the project. Implementation evidence is recorded separately; this document itself makes no test-passing or production-readiness claim.
