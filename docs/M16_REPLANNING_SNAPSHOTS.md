# M16: execution-aware snapshots and replacement scheduling

This slice connects immutable execution/approval evidence to the existing pipeline. It supports keeping unchanged, explicitly observed ongoing work while scheduling eligible future requests. The subsequent restoration/reconciliation slice also supports residual work after verified possession release; see M16_RESTORATION_RECONCILIATION.md. Captured replacement approval is described in M16_REPLACEMENT_APPROVAL.md.

## Workflow and endpoints

1. The controller calls `POST /api/v1/plan-revisions/{id}/replanning-captures` with `expected_plan_hash` and `expected_operational_revision`. The source must have an active SIMULATED non-scenario approval. Server time is used; callers cannot submit a replanning clock.
2. The backend saves an append-only capture containing the original assignments and hashes, approval/reservation identities, execution observations, policy version, disruption references, scoped state revision, derived commitments, completed-work evidence and explicit blockers. Repeated identical captures deduplicate by content hash. Read it with `GET /api/v1/replanning-captures/{id}`.
3. The planner creates a snapshot through the existing `POST /api/v1/snapshots`, adding `replanning_capture_id`. Current network, request, traffic, freight, restriction, resource and coordination facts are loaded normally. The capture and execution/commitment evidence become part of the immutable snapshot hash and item records.
4. Use the saved draft facts hash in the normal validation-context declaration; create the final snapshot with that context and the same capture ID. `commitments_known_empty` must be false. These source-completeness declarations remain explicitly synthetic prototype evidence, not authenticated railway authority.
5. Run priority, corridor availability, opportunities, coordination and CP-SAT through the existing APIs. Baseline planning uses the same snapshot, alternatives and constraints.
6. Materialize the actual worker output and request independent validation. A new source observation/policy/approval/event makes an earlier capture obsolete. Current fact comparison also detects changed network, maintenance and operational inputs.

Migration 018 protects captures against updates/deletes. No new service or alternative planning architecture is introduced.

## Frozen work and future candidates

Fresh opportunities and fresh candidate starts cannot precede the captured replanning time. The existing original horizon is retained where needed to represent ongoing setup/work/restoration and resource duty history; cropping an ongoing possession is rejected.

An approved assignment is considered as an alternative only after checking current availability, task/revision/stage identity, compatibility, footprint, policy revision, named resources, calendar, qualifications, travel/rest and cost inputs. This is evidence from a saved actual approved plan, not a canned or fallback schedule. Candidates excluded by the recheck carry explicit reasons. Pool and rolling-duty constraints and candidate incompatibilities are recomputed with the retained alternatives.

The fixed-candidate CP-SAT model now accepts assignment hashes and source assignments in commitment facts. It rejects identity substitution. Missing frozen candidates create genuine infeasibility; the worker does not move work or invent an incumbent. Any optimum remains qualified to the generated candidate set, including preserved approved alternatives. The baseline obeys the same commitments.

## Independent validation

Validator V2 reads raw capture evidence without importing freeze, opportunity, candidate-generation, resource-engine or solver predicates. It independently checks:

- Capture and execution hashes, observation identity, source approval identity and observation sequence.
- Freeze obligations derived from policy, captured time and execution status; complete original commitment coverage.
- Exact frozen assignment content, no new work in the past, and current time crossing a possession/work boundary.
- Completed-work exclusions and unresolved execution/restoration states.
- The original validator's traffic, infrastructure, task, compatibility, resource, precedence and mandatory-coverage checks against the new snapshot.

Validation does not infer completion as time passes. A STARTED record whose planned work end is reached without a new observation requires attention. A future capture cannot retain its earlier assumptions once possession start is reached without execution evidence. Validator version changes require new reports; historical reports are preserved.

## Explicit supported boundary

Supported: approved future commitments and unchanged ongoing tasks with explicit STARTED observations matching their planned starts. The tested scenario preserves the exact ENG/TRD shared block and schedules a new mandatory five-minute work task with five-minute setup and restoration in a separate feasible 15-minute block. Both planners process real inputs and return three scheduled requests; the independent validator passes the optimized result.

Still blocked:

- INTERRUPTED/RESUMED work without a current remaining-work assessment and verified possession release. In-place resumption is not authorized by reconciliation.
- Completed work whose possession restoration/release has not been verified. Once restoration is verified, completed work is excluded and possession/resource history is retained.
- Unknown/mismatched execution time, missing observations, stale captures or unknown policy.
- Changed footprints or a horizon that omits a frozen possession.
- Other overlapping approved lineages requiring commitment reconciliation.
- Imported execution and scenario replanning.

Events remain notifications; they do not automatically update source records. Wrapping unchanged invalidated source facts in new capture metadata is rejected. Captures use a conservative scope-wide version rather than optimized per-corridor invalidation.

## Approval remains closed

A replacement can be computed, independently reviewed and approved through a source-bound, atomic simulated-reservation supersession. The source plan and target difference remain immutable. See M16_REPLACEMENT_APPROVAL.md for the exact controller inputs and remaining continuation limits.

## Evidence

Tests: `tests/test_m16_replanning.py`. Cumulative test command: `.venv/Scripts/python.exe scripts/check_m16_replanning.py`. Saved evidence, source hashes and backend output are under `docs/evidence/M16-replanning*`. The script checks expected preserved assignments, three scheduled requests, real solver status, zero frozen-commitment changes and independent PASS. The full M16 checkbox remains open until all acceptance work is complete.
