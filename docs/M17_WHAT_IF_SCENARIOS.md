# M17 isolated what-if scenarios

M17 provides immutable, explicitly **SIMULATED** alternatives. A scenario is derived from a current non-scenario snapshot, runs through the same priority, corridor availability, opportunity, coordination, first-feasible and CP-SAT code as ordinary planning, and can be independently validated. It cannot create source records, operational events, controller decisions or reservations.

## Supported changes

`POST /api/v1/what-if-scenarios` accepts one to twenty typed changes:

- `TRAIN_DELAY`: shift one saved occupancy by 1–240 minutes while preserving route order.
- `FREIGHT_COUNT`: change the expected count for one saved forecast.
- `RESOURCE_OUTAGE`: add a bounded duty to one saved resource profile.
- `RESTRICTION`: add a scenario-only restriction inside the source track/horizon scope.
- `ADD_REQUEST`: add a scenario-only maintenance request with a UUID, valid source asset/footprint and SIMULATED source mode.

The request binds an idempotency key, source snapshot ID/hash and scenario name. The source must be hash-valid, current, independently declared with a current SIMULATED validation context, free of unresolved execution state and not itself a scenario. Nested scenarios are rejected. The server deep-copies saved facts, applies the declared changes, binds a new facts hash and saves a scenario snapshot plus both queued planning runs in one repeatable-read transaction.

The response and `GET /api/v1/what-if-scenarios/{id}` expose real worker statuses. Source APIs continue to return the original train, request, restriction and resource records. If source facts change before a queued scenario run publishes, the worker marks the result `SUPERSEDED`. New planning jobs against that scenario are also rejected as stale.

## Validation and decisions

Scenario plan revisions can receive independent validation. Validation replays the saved changes from the current source snapshot and recomputes the scenario facts hash; a changed/stale source makes the report unusable. Controller approve, reject, replan and edit operations are forbidden for scenario revisions. This prevents SIMULATED scenario output from creating even a simulated reservation or being confused with an approved proposal.

A same-scenario baseline-versus-CP-SAT comparison uses the M15 KPI engine and carries `claim_scope: ISOLATED_SIMULATION_ONLY` plus `SCENARIO_RESULTS_CANNOT_AUTHORIZE_POSSESSIONS`.

`POST /api/v1/what-if-scenarios/{id}/impacts` accepts validated source and scenario CP-SAT plan revisions. It records a separate immutable source-versus-scenario impact artifact. Because those plans have different inputs, the artifact exposes raw metric differences and the exact changed inputs, sets `claims_permitted: false`, and includes `INPUTS_DIFFER_SO_DELTAS_ARE_NOT_OPTIMIZER_GAINS`. It never calls a difference an optimizer improvement.

## Limits

This is bounded prototype analysis over one saved source snapshot. It does not model probabilities, execute Monte Carlo simulation, authenticate live feeds, predict actual delay, authorize train movement, or write a possession. The fixed candidate set and declared operating policies still define the optimization scope. A source-versus-scenario difference is sensitivity evidence for the declared input change, not a causal railway performance claim.

Automated acceptance tests and an actual backend example are recorded in `docs/evidence/M17.md`.
