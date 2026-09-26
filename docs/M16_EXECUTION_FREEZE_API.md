# M16 execution observations and freeze policy

This is a tested slice of M16, not the rolling-horizon milestone gate. The architecture is unchanged. The subsequent snapshot/solver slice now captures execution evidence; see M16_REPLANNING_SNAPSHOTS.md. Legacy execution-unaware snapshots remain blocked.

## API

All paths start with `/api/v1`. Authentication uses the existing prototype role checks.

| Endpoint | Role | Behavior |
| --- | --- | --- |
| `POST /freeze-policies` | ADMIN | Append a SIMULATED policy revision with expected current policy revision, freeze minutes (0–10080), and reason. Advances scoped operational revision. No implicit operating-rule default. |
| `GET /plan-revisions/{id}/freeze-context` | Authenticated | Assess active approvals in the lineage at server time. Returns policy version, exact assignment hashes, freeze reasons, blockers, and scoped state revision. |
| `POST /plan-revisions/{id}/execution-records` | CONTROLLER | Append a hash-bound observation for a request in an active, approved SIMULATED non-scenario assignment. |
| `GET /plan-revisions/{id}/execution-records` | Authenticated | Read immutable observations, ordered by request and sequence. |

### Observation contract

Required fields: `idempotency_key`, `decision_id`, `expected_plan_hash`, `candidate_id`, `expected_assignment_hash`, `request_id`, `expected_sequence`, `expected_operational_revision`, `status`, timezone-aware `observed_at`, `verified: true`, `evidence_reference`, and `note`. `remaining_work_minutes` is conditional as below. Receipt time and resulting state revision are assigned by the backend.

Allowed lifecycle:

```text
No observation -> STARTED -> COMPLETED
                      |
                      v
                  INTERRUPTED -> RESUMED -> COMPLETED
                                     |
                                     +-> INTERRUPTED ...
```

- STARTED does not assert remaining progress.
- INTERRUPTED accepts positive or unknown (`null`) remaining work. Unknown is retained visibly; reconciliation is required.
- RESUMED requires an explicit positive remaining-work duration. The observation alone does not grant permission or prove that a replacement schedule is feasible.
- COMPLETED requires explicit zero remaining work and a preceding STARTED/RESUMED observation. It is terminal for that request identity.
- Observation times must increase strictly per request and cannot be later than server receipt time. A factual deviation outside the planned work interval is retained and flagged, rather than quietly changing the plan.
- Equal redelivery by the same actor returns the saved record before checking now-stale sequence/state expectations. Different content under the same key fails. Concurrent delivery advances state once.
- Observations may report execution against a disrupted, still-active approval, because recording what happened is distinct from authorizing work. The stale-source flag remains visible.

The API never infers completed work from elapsed time, planned end, approval, or solver selection. `verified` is a controller attestation in this prototype, not independently authenticated field telemetry. Actual external verification remains a domain/integration requirement.

## Freeze semantics

The configured future freeze interval is `[now, now + freeze_minutes)`. An assignment exactly at the upper boundary is outside that interval. An assignment whose possession start has been reached is protected separately, including with zero freeze minutes. Missing execution observations after that point are an explicit `EXECUTION_STATE_UNKNOWN` blocker.

Any started, resumed, interrupted, or completed member protects its entire approved bundle. The shared possession is not automatically split. Interruptions require reconciliation; unknown remaining duration adds `REMAINING_WORK_UNKNOWN`. A missing policy conservatively protects all approved assignments and blocks replacement.

Protection compares the digest of the entire saved assignment: identity, tasks/stages, footprint, concrete resource allocations and other candidate content. Controller modifications and the approval transaction both recheck active frozen work. A proposal prepared before a freeze boundary cannot bypass that boundary when later approved. An unrelated plan lineage cannot reapprove the same already-committed requests.

Policy revisions are explicit, ADMIN-controlled, append-only and audited. A revised policy changes the future time interval; it never makes observed execution movable. Production domain owners must supply and approve actual freeze durations.

## Concurrency and failure behavior

Execution observations share approval's scope lock, then acquire the publication lock used by event intake, snapshot creation and worker publication. They advance scoped state and supersede affected queued/running work. Late worker output cannot overwrite the state. Controller edits and report usability reject execution-unaware snapshots.

The current fence is intentionally conservative: an observation blocks legacy snapshots sharing its request, track, or resource scope. A replacement snapshot must carry a current immutable capture with no unresolved execution blockers. Imported execution and scenario execution are not supported. This is not a completed replanning engine.

## Completion is not restoration

Completing a maintenance request does not verify restoration, hand back a possession, or release resources. All reservations stay active. Partial completion in a shared bundle remains visible and protected. A later execution-aware workflow must represent outstanding restoration, remaining work and resource duty history before producing a replacement.

## Evidence and remaining work

Migration: `017_execution_freeze.py`. Implementation: `execution.py`, `freeze_state.py`, approval/report/worker fences. Tests: `test_m16_execution.py`; cumulative evidence: `docs/evidence/M16-execution.md`.

Approved commitments, execution observations, completed-work exclusions and policy versions are captured in fresh immutable snapshots, with unchanged ongoing candidates rechecked for CP-SAT and independently validated. Subsequent M16 slices add remaining-work reconciliation, restoration, plan differences, controlled replacement approval and source-bound continuation; see M16_EXECUTION_CONTINUATION.md. Source-event reconciliation remains before the full M16 gate. M17 must wait.
