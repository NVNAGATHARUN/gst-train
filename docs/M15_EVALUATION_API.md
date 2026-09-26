# M15 evaluation contract - interval KPI version 2

POST `/api/v1/plan-comparisons` takes baseline and RailSync plan revision IDs. Both must refer to completed, hash-matching runs from the same snapshot, requirements, priority assessments, coordination computation, clearance/freight policy and solver configuration. A manual plan edit cannot masquerade as solver output. GET returns the immutable historical comparison and separately computed current report usability. Historical records using an older metric version cannot authorize current claims.

Reserved track-minutes use interval union on each track. Temporal utilization unions concurrent active work within each possession, then divides total active minutes by total possession minutes. It does not divide summed parallel task-minutes by track-minutes. Mandatory and on-time coverage expose numerators and denominators, including deferred requests due within the horizon. The maintenance-only track availability metric explicitly measures the maintenance footprint; it is not total traffic capacity or observed asset reliability. Measured delay remains unavailable.

Percent change is `(RailSync - baseline) / abs(baseline) * 100`. Improvement percent reverses the sign for lower-is-better measures. Zero denominators return null percentages alongside absolute deltas. Negative improvements remain negative. UNKNOWN, INFEASIBLE and other outcomes without a valid incumbent return unavailable metrics instead of a fictitious zero-possession success. All metrics have explicit units, version and formula; task work and bundle counts are descriptive rather than automatic quality claims.

GET `/api/v1/plan-comparisons/{id}/export` returns the saved evidence as reproducible JSON with its content hash and current-claims header. Validation status, findings, horizon, solver status, objective, bound, gap and candidate-search evidence accompany the metrics.

## Correctness follow-up

The original two-test M15 gate did not cover percentage scaling or parallel-work double counting. Those errors were corrected in version 2 with hand-calculated regression fixtures, denominator and negative-gain tests, configuration mismatch rejection, persisted-run integrity checks and stale-export checks. Old evidence remains historical; use the current source-manifest gate. M14 calendar evidence now comes from real full-horizon candidate generation and CP-SAT execution, not copied short-horizon outputs.
