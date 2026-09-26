# Implementation decisions

## ADR-001 — versioned network graph

Station, section, track, asset, isolation-zone and restriction identities share a typed entity table. Immutable revision rows preserve each validated payload. Current relationships are explicit NetworkLink rows with foreign keys. This replaces separate per-type identity tables in the draft schema while preserving typed API contracts, revision lineage and relational reference checks. Snapshots must materialize immutable payloads, never follow mutable current pointers.

## ADR-002 — evidence when Git is host-blocked

The host refuses `.git/index.lock` even after explicit filesystem grants. Gates preserve exact source SHA-256 manifests, test logs and JUnit results and state that no commit exists. The user's gate conditions (passing automated tests and correct backend output) still control milestone progression. Commit references must be populated once host Git writes work.

## ADR-003 — explicit M10 policy and resource units

Resource profiles and compatibility policies are immutable, typed revisions. Snapshots select one exact policy revision and capture the latest resource profiles in a PostgreSQL REPEATABLE READ transaction. Historical snapshots without these facts remain blocked for coordination. Rule provenance is SIMULATED or IMPORTED; neither label authenticates railway operating authority.

Each demand quantity becomes a named-unit slot. Qualifications must cover every reserved resource interval, including setup and restoration. A qualification omitted from a request requirement means its explicit issue_type is the required skill; there is no generic eligibility fallback. Multi-track work requires an explicit resource work location. OFF work expands the possession footprint to the entire declared electrical zone, and all those tracks need availability evidence.

Parallel bundles require explicit permission to share BOTH setup and restoration. Each crew remains reserved for the whole parallel possession, including waiting for shared restoration; this conservative capacity assumption is recorded in candidate output. Sequential work retains every task's setup/work/restoration and may reuse a named resource across adjacent stages. Partial parallel/sequential mixtures are excluded with a reason. Group permission must cover every subset of three or more tasks; pairs cannot authorize an unreviewed triple hazard.

Travel times are directed, resource-type-specific and must be supplied between distinct locations. Same location has zero movement. Rest is uninterrupted time additional to travel between separate duties. Adjacent work at the same location is one continuous duty; the rolling 24-hour duty limit still applies. The current limit measures reserved task-duty time; travel is enforced as a separation requirement, not included in that load. Domain-specific paid-duty accounting requires a new explicit policy version before operational use.

Pool membership supplements named-unit constraints. Capacity calendars and fixed duties produce event-segment coefficient rows. Rolling 24-hour limits also produce aggregate rows; pair incompatibilities cannot replace them. Missing pool coverage has capacity zero. Fixed duties and qualification history must cover the horizon plus 24 hours on either side. Search limits are recorded; no global optimization claim follows from finite candidate generation.

## ADR-004 — review remains blocked while source authority is unresolved

Existing M4/M8 synthetic COA inputs are broad corridor-access envelopes intersected with occupancy. Their overlap diagnostics are preserved and block operational review. An imported COA disagreement stops M10 generation. The organizer/domain owner's authoritative semantics, complete traffic coverage declarations and freshness policy remain prerequisites for approval; do not reinterpret synthetic fixtures as live source authority.

## ADR-005 — fixed-candidate CP-SAT and fair baseline

M11 uses OR-Tools CP-SAT 9.15.6755, locked in uv.lock. Each Boolean candidate variable carries concrete M10 times and resources. Coverage equals a Boolean request variable; mandatory obligations due by horizon end require coverage. Candidate conflicts, event-based pool capacity and rolling-duty rows, precedence, and frozen candidate facts are hard constraints. Frozen/commitment fact support is present in the model; operational commitment ingestion belongs to the later approval/replanning milestones and is not claimed here.

The objective minimizes weighted deferred priority basis points, reserved track-minutes, expected-train track-seconds of freight exposure, incremental directed travel minutes against fixed duties, and changed commitment count. These units are deliberately separate and each has an explicit nonnegative integer weight. Default weights are 100/1/0/1/100 respectively. Protected freight makes exposure zero only when backend intervals establish that fact. Travel cost is evaluated against fixed duties for each candidate; transitions between optional selected jobs are constrained for feasibility but their sequence-dependent travel cost is not optimized in this first fixed-cost model. Report that objective limitation.

Total objective magnitude is bounded to preserve exact integer reconciliation. Store actual solver status, objective terms, best bound, runtime, branches/conflicts, package version, model input hash, seed and worker count. A zero time budget is a supported test case producing the solver's UNKNOWN response without fabricated assignments. Optimality applies only to generated candidates, with pruning evidence retained.

The comparison baseline sees the same candidate universe, including bundles, and uses the same complete constraints. It considers mandatory work first, then deadlines and stable request IDs, choosing the first feasible candidate by start, track-minutes and candidate ID. It performs no objective search. The earlier basic baseline remains available for its historical fixtures but is labeled comparison-ineligible. Do not compare it against CP-SAT for KPI claims.

Worker leases expire after the configured solve budget plus five minutes for overhead. An expired job can be reclaimed. Publication locks the run and checks both lease token and expiry; an older worker cannot overwrite a newer attempt. No terminal solver outcome implies controller approval.

## ADR-006 — independent validation and explicit source declarations

The validator and its resource-check module do not import solver, opportunity, availability, bundling or resource-allocation predicates. They recompute feasibility from raw immutable facts and actual assignment intervals. Shared schema types are allowed; cached conflicts, counts, objectives and costs are not feasibility evidence. Validation does not certify those informational/optimization metrics; M15 must compute KPI values from saved intervals.

ValidationContext is part of a snapshot's content hash. It names the exact facts hash, received/expiry times, source coverage intervals, COA semantics, clearance margins, freight policy and commitment completeness. A source row's existence does not establish complete traffic coverage. Snapshot creation rejects a context tied to different facts. Occupancy capture includes up to 60 minutes on either side of the horizon so outside trains cannot escape a configured clearance check.

For the current prototype, PASS is available only for explicitly SIMULATED facts and rules with complete, current declarations. An access-envelope COA permits intersecting traffic to be subtracted; a TRAFFIC_FREE declaration contradicted by raw occupancy fails. Missing/unknown semantics, ambiguous source revisions, unauthenticated imported authority, unknown current state and absent profiles/coverage return blocking results. No live or operational certification is implied.

Reports are append-only, tied to exact run-plan and snapshot hashes, and timestamped by the server. Callers cannot choose checked_at. GET returns historical status plus current usability, which becomes false after source/plan changes or expiry. Exceptions, malformed inputs, unsupported shapes, exhausted check budgets and timeouts return ERROR; failures cannot become PASS. A five-second cooperative validation budget is a failure boundary, not a performance guarantee. Approval remains an M13 transaction and must revalidate/recheck atomically; GET usability alone cannot authorize a reservation.

Frozen-work checks require the full expected assignment content hash, not just a reusable candidate ID. Completed work cannot be rescheduled. The actual commitment/execution ingestion workflow remains a later milestone; unknown history stays blocked.

## Local database recovery during M12

On 16 September the existing project-local PostgreSQL cluster initially could not finish crash recovery: its startup process reported `could not signal for checkpoint: Operation not permitted`. Foreground retries also failed. A separately initialized PostgreSQL 17.11 test cluster at `.local/m12-test-pgdata`, port 55433, verified a fresh migration chain and the tests without modifying the original data files.

After confirming the original server was stopped, a PostgreSQL single-user session with no SQL input completed normal WAL recovery and a clean checkpoint. The original server then started successfully on port 55432. No data directory or WAL was reset or removed. Development migrations and the final cumulative gate use the original cluster; test logs identify the actual database port. Single-user recovery is a documented PostgreSQL mode: https://www.postgresql.org/docs/17/app-postgres.html#APP-POSTGRES-SINGLE-USER

## ADR-007 — immutable decisions and scope-separated reservations

A completed planning run is materialized as an immutable `PlanRevision` before controller review. Controller edits can select only real candidates from that run's coordination computation and create a child revision; they cannot change a parent or invent intervals/resources. Every child requires a new independent report bound to its own content hash.

Approval rechecks the exact plan hash, exact PASS report, report usability, current source hash and expected state revision inside one transaction. A scope-specific lock serializes competing controller decisions. Active reservations are checked using half-open intervals for shared tracks or named resources. Replacing an approved lineage requires an explicit superseded decision ID; old reservations remain active until that replacement commits.

Simulation state and reservations are isolated from OPERATIONAL state. The API explicitly returns `SOFTWARE_PROPOSAL_ONLY`; an approval is not a railway possession grant. Imported plans cannot pass the current validator until authority is authenticated, preventing this prototype from creating an operational reservation from unverified inputs.

Explanations cite persisted request priorities, candidates, resources, rules, exclusions and deferred reasons. Templates only verbalize those values. They do not use model attribution as scheduling causality and do not invent future windows.

## ADR-008 — calendar artifacts are views of canonical plans

Weekly and monthly reporting reuses a single immutable `PlanRevision`; it does not copy assignments into a new scheduling model. A weekly request expands to seven local calendar days and a monthly request to the actual calendar month. The artifact requires full snapshot horizon coverage, uses aware intervals and reports actual elapsed minutes across timezone changes.

The artifact records the plan/snapshot hashes, validation freshness, controller evidence, declared forecast-coverage limits and assignment-level firm/tentative state. A currently usable approved reservation makes a matching assignment `FIRM`; stale approved work is `REQUIRES_ATTENTION`. The scope is still an explicitly labeled software proposal.

Exports are generated deterministically from the immutable artifact and carry the same hashes and authority label. CSV formula prefixes are escaped. M14 does not decompose large monthly models or implement rolling replanning; those remain later scoped work rather than unqualified claims of monthly optimality.

## ADR-009 — approved M18 design and fair-baseline clarification

The user approved `M18_UX_DESIGN.md` version 1.1 with four targeted amendments: evidence-backed work readiness, explicit line/power/S&T access requirements, Wave-6 planned-versus-actual execution and user visual approval after each hero. H1 is the first major visual checkpoint. No high-level architecture change is authorized or needed.

The earlier Build Contract §6 baseline-without-bundling sentence is superseded for fair evaluation by the later user instruction, ADR-005 and implemented M11/M15 contract: both planners receive the same candidate universe, including bundles, with the same hard constraints and configuration. UI labels must preserve that comparison and never promise positive gains.

M18 foundation adds browser session credentials and a read-only snapshot projection without putting feasibility logic into the frontend. General planning requests are persisted idempotently and preparation commits both genuine planner jobs atomically. Scenario and rolling-replanning workflows retain their dedicated boundaries. See `M18_FOUNDATION_API.md`; the foundation does not constitute a complete M18 release.
