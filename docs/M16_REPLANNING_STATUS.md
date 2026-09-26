# M16 - events, execution observations and freeze protection

M16 is **complete for the SIMULATED prototype**. Migration 016 adds immutable disruption records, snapshot invalidations and a scope-specific debounce generation. Migration 017 adds immutable execution observations and versioned freeze policy. Migration 018 captures execution and approval evidence for immutable replacement-planning snapshots. Migration 019 adds explicit remaining-work assessments and verified possession releases. Migrations 020–021 add immutable event-to-source reconciliation and one prepared proposal per source plan and event batch. The cumulative 162-test gate and actual backend example are in `evidence/M16-rolling.md`.

## Implemented

POST `/api/v1/disruption-events` accepts explicitly SIMULATED train delay, freight change, resource outage, urgent defect and restriction-change notifications with affected track/resource IDs, source identity/revision, occurrence time and evidence reference. Receipt time is server-generated. Identical redelivery returns the saved event; changed content under the same identity is rejected. Older unknown revisions and future occurrence times are rejected. Imported/operational event application is not enabled.

Intake holds the same scope lock as approval, then a publication lock shared with snapshot creation, planning-run queueing and result publication. Affected snapshots are invalidated; queued/running jobs become SUPERSEDED. A worker that finishes after invalidation cannot publish. Readable historical reports remain unchanged, but report usability and controller approval fail closed. The plan endpoint shows STALE_REQUIRES_ATTENTION with event evidence. Existing approved reservations remain recorded and active while the controller resolves the disruption.

Rapid events advance one scope generation and reset a five-second debounce deadline. GET `/api/v1/replanning-batches/SIMULATED` exposes DEBOUNCING or READY_FOR_NEW_SNAPSHOT. The status does not mean that a replacement was solved. Events do not silently edit occupancy or resource facts. Reissuing snapshot receipt metadata around unchanged invalidated facts is rejected; a genuine source update is required.

The scope-wide invalidation is deliberately conservative. Historical, non-scenario snapshots sharing the affected track/resource are invalidated. Finer temporal impact filtering and indexed retrieval should accompany later scaling work.

## Completed after the initial event-intake slice

- Continuation observations across approved replacements now preserve the request sequence and require exact unchanged assignment or captured release/assessment evidence. See M16_EXECUTION_CONTINUATION.md. Unreleased in-place resumption still cannot be planned or approved as replacement work.
- Source-event reconciliation now checks changed effective source facts for all five supported disruption kinds. A repeatable-read preparation transaction captures current commitments, saves a new snapshot, computes priority/availability/opportunities/coordination and queues baseline and CP-SAT together. Events still do not automatically patch source data; see `M16_ROLLING_REPLANNING_API.md`.
- Replacement revisions save unchanged/moved/removed/new/deferred plan differences and a defined change metric.
- Captured replacement approval has controlled lineage, a hashed per-request difference, atomic simulated-reservation supersession, and checked execution continuation. See M16_REPLACEMENT_APPROVAL.md and M16_EXECUTION_CONTINUATION.md. Frozen-work conflicts and infeasible replacements remain visible attention states.
- The 162-test cumulative gate covers repeated events, resource outages, overnight source occupancy, in-progress execution continuation, frozen-work conflicts, worker supersession, independent validation and controlled replacement approval. The M16 evidence records the actual backend output and limitations.

## Regression repairs included with this slice

M15 KPI version 2 corrects percent scaling and interval unions, adds coverage denominators, preserves no-solution nulls, strengthens input/configuration identity, and refreshes current comparison usability. M14 synthetic full-period inputs are now processed by the actual candidate and solver pipeline. These corrections were verified by the cumulative M15 corrective gate (100 tests) before M16 implementation began.
