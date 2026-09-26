# M13 — plan revisions and controller decisions

M13 adds the decision boundary after independent validation. `APPROVED` means approval of a RailSync software proposal only. It is not a railway possession, signalling or train-control authority.

## Workflow

1. `POST /api/v1/plan-revisions` materializes a completed run as immutable revision 1 and binds it to exact plan and snapshot hashes.
2. `POST /api/v1/plan-revisions/{id}/explanations` persists one structured explanation per request from actual priority assessments, selected candidates, resource assignments, rule references and recorded exclusions.
3. `POST /api/v1/validation-reports` with `plan_revision_id` independently validates that exact revision. An edited child cannot reuse its parent's report.
4. `POST /api/v1/plan-revisions/{id}/decisions` accepts `APPROVE` or `REJECT` from the CONTROLLER role. Approval requires the exact current plan hash, an exact usable PASS report, an expected state revision and a reason.
5. `POST /api/v1/plan-revisions/{id}/modifications` creates an immutable child from existing generated candidates. It never edits a parent and always requires a fresh validation report.
6. `POST /api/v1/plan-revisions/{id}/replan` queues the same planner against the unchanged current snapshot. If facts changed, it returns `CURRENT_STATE_REQUIRES_NEW_SNAPSHOT`; rolling-horizon snapshot creation is M16.

## Concurrency and reservations

Controller decisions acquire a transaction-level scope lock and lock the `operational_states` revision. Two requests carrying the same expected revision cannot both commit. Before approval, active track and named-resource reservations are checked with half-open intervals. Superseding an existing approved lineage requires the prior decision ID and atomically deactivates its reservations while creating the replacement.

SIMULATED snapshots use a separate state and reservation scope. They never write an OPERATIONAL reservation or increment OPERATIONAL state. Imported facts remain unable to pass M12 validation until authority and completeness are authenticated, so this prototype cannot silently cross into operational approval.

All plan revisions, explanations and controller decisions are append-only at the database layer. Reservation activity may change only in the same controlled supersede transaction. Every action also writes an `audit_events` entry.

## Evidence

`tests/test_m13.py` verifies exact revision validation, evidence-backed explanations, controller-only access, plan/report/hash binding, idempotency, real simultaneous approval serialization, simulated-scope isolation, immutable evidence, child revisions, fresh validation after edits, rejection and replan audit events. The cumulative M13 gate stores JUnit results, command output, source hashes and a persisted API example under `docs/evidence/M13*`.
