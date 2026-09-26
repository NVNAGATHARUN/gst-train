# M16: captured replacement lineage and controller approval

This slice remains limited to **SIMULATED, non-scenario** decision support. An `APPROVE` response means approval of a software proposal, never a railway possession grant.

## Backend flow

1. The controller captures the approved source plan's current simulated ledger. The planner creates a fresh immutable snapshot, generates candidates, and runs the baseline and CP-SAT on those facts.
2. `POST /api/v1/plan-revisions` materializes a completed replacement run. It joins the source plan's lineage, increments the lineage revision, and binds the immutable revision to the captured source decision, source/target hashes, and a deterministic per-request difference. Repeating materialization for the same run returns the same revision.
3. `GET /api/v1/plan-revisions/{id}/differences` returns that stored, hash-checked difference. It distinguishes unchanged work, changed work, explicitly assessed residual work, verified completion, newly scheduled work and deferred work. The comparison reports original and replacement possession/work times, footprints/resources, assignment hashes, and work-start shift minutes. This is descriptive evidence, not a claimed KPI improvement.
4. Independent `POST /api/v1/validation-reports` must return `PASS` and remain usable. The controller calls the existing `POST /api/v1/plan-revisions/{id}/decisions` with `action=APPROVE`, the current `expected_operational_revision`, exact plan hash, report ID, and `supersedes_decision_id` equal to the source approval in the capture.
5. Under the simulated-state and publication locks, approval rechecks the capture/ledger, source decision, latest lineage revision, persisted difference, report usability, frozen work, duplicate request coverage, and cross-lineage track/resource conflicts. One database transaction deactivates only the source approval's still-active reservations, creates replacement **SIMULATED** reservations, advances the state revision, and records the decision/audit. A released source possession already has no active reservation to deactivate. Failed checks leave the source reservations intact.

The captured snapshot becomes stale for *new* planning after approval advances the ledger. The historical PASS report and difference remain readable, but a later decision requires fresh facts and validation. Duplicate delivery of the same decision idempotency key returns the saved decision, including when concurrent requests wait on the state lock.

## Deliberate limits before the full M16 gate

- Source-bound execution continuation is supported for exact preserved assignments and verified residual restart. See M16_EXECUTION_CONTINUATION.md. A new approval cannot silently resume interrupted work without assessed remaining demand and verified release.
- Disruption events do not apply source facts. Event reconciliation and automatic rolling-horizon orchestration remain pending.
- Unknown execution, stale captures, invalidated source facts, failed validation, and incompatible frozen commitments remain blocked. No operational reservation or train-control action is issued.

Tests and saved API output: [M16-approval evidence](evidence/M16-approval.md). The full M16 gate remains open.
