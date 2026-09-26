# M16: execution observations across approved replacement plans

This slice records what a controller observed under a **SIMULATED** replacement proposal. It issues no possession grant, train-control command, or permission to resume railway work.

The existing `POST /api/v1/plan-revisions/{id}/execution-records` endpoint keeps one increasing sequence per request across plan revisions. A different decision/assignment is accepted only when the new decision is an active, approved replacement linked to the immediately preceding observation's source decision in the immutable planning capture. The endpoint checks the persisted replacement difference, source/target plan hashes, capture and approval identities, the captured prior observation, and the normal lifecycle/timestamp rules under the simulated-state lock.

Two handoffs are supported:

1. **Preserved ongoing assignment:** the candidate and full assignment hash are unchanged, the source observation is `STARTED`, and the source possession has not been released. The next observation can be `INTERRUPTED` or `COMPLETED` according to the normal lifecycle. The new record includes `result.continuation.kind=PRESERVED_ASSIGNMENT` and the prior record/decision IDs.
2. **Verified residual restart:** the source observation is `INTERRUPTED`, a verified whole-possession release and current remaining-work assessment are captured, and the new assignment is labeled `REMAINING_WORK_RESCHEDULED`. The controller records `RESUMED` with exactly the assessed remaining work minutes, no earlier than the restoration and assessed restart times. The new record includes `result.continuation.kind=VERIFIED_RESIDUAL_RESTART`, plus release and assessment IDs. Later completion and restoration use the replacement approval's records and reservation.

Old approvals cannot accept new observations once their reservations are superseded. A wrong source, changed assignment without residual evidence, wrong remaining duration, early restart, stale sequence, or reused key with changed payload fails without advancing the state. Equal concurrent redelivery advances it once. A factual observation outside the planned work interval remains visibly flagged, as in the original execution API; recording that fact does not validate an unsafe schedule.

Completing work does not release a reservation. The controller still needs verified whole-possession restoration. In-place `RESUMED` observations against an unreleased original approval remain factual records under the existing API, but they cannot create an approved replacement or bypass reconciliation/restoration. The replacement snapshot is no longer reusable for *new* planning once approval or later observations advance the ledger; a future replan needs fresh capture and validation.

A later capture retains superseded approvals that have execution history, even when their reservations are inactive. The independent validator checks the global request sequence and each cross-approval handoff from those raw facts. It checks a historical restoration against the records that existed when that release committed, then evaluates any later continuation separately. The tested two-approval residual sequence ends with both original requests completed; a third snapshot has no pending demand and independently validates an empty plan. A corrupted continuation link fails validation.

Historical approval rows remain available for that validation, but a superseded source decision cannot be captured as the basis for a new plan. Capture checks that its source is the latest approved decision in its lineage; the test confirms a request to recapture the original plan fails after supersession.

Saved backend results and the cumulative gate are in [M16 continuation evidence](evidence/M16-continuation.md). Source-event reconciliation and rolling-horizon orchestration remain pending before the full M16 gate.
