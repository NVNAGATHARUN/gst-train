# M12 — independent validation

## API

`POST /api/v1/validation-reports` (PLANNER, CONTROLLER or ADMIN)

```json
{"run_id":"<completed planning run UUID>","expected_plan_hash":"<SHA-256 of saved run.result>"}
```

The server reads the saved run and snapshot, recomputes constraints, and persists a new immutable report. Wrong expected hashes return 409. A run that has not completed cannot be validated. Validations returning FAIL or ERROR are saved as evidence rather than discarded.

`GET /api/v1/validation-reports/{id}` returns the historical report and `usable_for_review` / `current_blockers`. A historical PASS does not remain usable after facts change or expire. Every report contains category results and evidence references. There is no controller approval endpoint in M12.

## Snapshot declaration

`POST /api/v1/snapshots` accepts optional `validation_context`. Without it the snapshot can support historical planning experiments, but independent validation returns ERROR. The declaration must contain:

- `scope`: SIMULATED for current prototype PASS eligibility; imported authority is unverified.
- `facts_hash`: SHA-256 of the exact snapshot facts object, using sorted JSON keys and compact separators.
- `received_at` / `valid_until`: aware timestamps, checked against the server clock.
- `coverage`: complete intervals with evidence references for NETWORK, REQUESTS, RESOURCES and COMMITMENTS; plus OCCUPANCY, COA and FREIGHT per track. Occupancy coverage includes clearance beyond both horizon boundaries.
- `coa_semantics`: ACCESS_ENVELOPE or TRAFFIC_FREE. UNKNOWN blocks validation.
- Both clearance margins, explicit freight protection policy, a rule reference, and whether commitments are known empty.

Declarations are labeled input evidence, not automatically inferred operating truth. Do not manufacture complete coverage for an unknown operational feed. In tests, all declarations explicitly describe controlled synthetic fixtures.

## Verification and reproduction

The standard gate uses the original project-local PostgreSQL cluster on port 55432, recovered successfully during M12. Run `scripts/test.ps1 -q -p no:cacheprovider` for the cumulative suite. Fresh-install verification also used a separate test cluster:

1. Start `.venv/Scripts/python.exe scripts/isolated_test_db.py --serve` in a terminal; leave it running.
2. In another terminal, run `.venv/Scripts/python.exe scripts/isolated_test_db.py` to ensure the test database exists.
3. Set `RAILSYNC_TEST_PORT=55433`, then run `scripts/test.ps1 -q -p no:cacheprovider`.

The helper stores no credentials in committed files. All tests require a database named railsync_test before clearing tables. Do not substitute a development database. The final gate record and saved backend example are in docs/evidence/M12.*. See DECISIONS.md for the recovered host startup issue and the exact separation of the two clusters.

The suite covers deliberate duration, traffic, crew, identity, footprint, deadline, capacity, compatibility, source-freshness and provenance corruption; frozen content, completed work, travel/rest, group hazards, exceptions, timeout and API authorization. An import-boundary check and poisoned scheduler predicates verify that validation does not call scheduling feasibility code.
