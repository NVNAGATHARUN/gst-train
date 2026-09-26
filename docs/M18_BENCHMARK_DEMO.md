# M18 benchmark and demonstration evidence

All data in this package is SIMULATED. Results measure the current software and generated candidate set only. They do not measure railway delay, asset reliability, field safety, live capacity or production infrastructure.

## Compatibility demonstration

The persisted backend fixture uses real request, timetable/occupancy, COA, priority, availability, opportunity, compatibility and resource-allocation code.

- With the explicit synthetic Engineering/TRD parallel-sharing rule, the engine generated a shared AB possession from 01:25 to 02:45 IST. Separate Engineering and TRD work stages and named resources remain visible.
- With the compatibility rule removed on otherwise equivalent fixture facts, the engine generated nine single-work candidates, zero bundles and an explicit COMPATIBILITY_UNKNOWN exclusion.
- Both variants retain review blockers, including simulated-rule and unresolved synthetic COA limitations. They are not controller-approved plans.

The saved artifacts are docs/evidence/M18-demo-bundle.json and docs/evidence/M18-demo-compatibility-disabled.json.

## Repeatable fixed-candidate benchmark

The benchmark uses seed 26027 and three generated alternatives for every request. Both planners receive identical requests, candidates, priorities and pool-capacity constraints. The baseline is the implemented fair deterministic first-feasible candidate planner; CP-SAT is the real OR-Tools model.

| Requests | Candidates | Baseline scheduled | CP-SAT scheduled | CP-SAT status | Solver wall time | Raw objective delta |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | 60 | 20 | 20 | OPTIMAL | 0.083659 s | -731 |
| 100 | 300 | 100 | 100 | OPTIMAL | 0.0440823 s | -2,992 |
| 300 | 900 | 289 | 300 | OPTIMAL | 0.1330268 s | -3,152,296 |

The raw objective delta is CP-SAT minus baseline under the configured integer objective. It is not a percentage and is not a train-delay or reliability improvement. Negative values happened in this recorded run; the harness does not require a positive gain. Exact input hashes, model hashes, best bounds, gaps, measured wrapper times, branches, conflicts and OR-Tools version are in docs/evidence/M18-benchmark-results.json.

## Reproduction

Start a clean isolated railsync_test PostgreSQL database, then run:

    RAILSYNC_TEST_PORT=55442
    .venv/Scripts/python.exe scripts/check_m18_benchmark.py

The gate runs two real compatibility variants and the 20/100/300 solver cases. The recorded run reported 3 passed in 4.04 seconds, plus two upstream TestClient deprecation warnings.

## Remaining integrated demo work

This closes the repeatable solver-scale benchmark and the core compatibility toggle evidence. It does not yet close the full A-B-C-D judge walkthrough. That final walkthrough must add the four-request corridor presentation, independent validation, baseline/CP-SAT plan materialization, a visible failure, stale/replan flow and frontend screenshots from the same saved case.
