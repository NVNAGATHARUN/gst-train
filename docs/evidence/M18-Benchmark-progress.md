# M18 benchmark and demo — technical progress

**Date:** 2026-09-25  
**Scope:** SIMULATED software evidence only.

The real backend compatibility fixture produced a shared Engineering/TRD AB candidate with explicit timing and named allocations. Removing its explicit compatibility rule produced zero bundles and a COMPATIBILITY_UNKNOWN exclusion. No conflict or output was hardcoded.

The repeatable seed-26027 solver benchmark ran 20, 100 and 300 requests with 60, 300 and 900 generated candidates. CP-SAT returned OPTIMAL over each generated candidate set, with saved best bounds and zero relative gap. The benchmark preserves the actual baseline outcome, including only 289 of 300 requests selected in the largest first-feasible case. No positive percentage or operational outcome is inferred.

Command: .venv/Scripts/python.exe scripts/check_m18_benchmark.py with RAILSYNC_TEST_PORT=55442 on a fresh isolated PostgreSQL cluster.

Result: **3 passed**, two upstream deprecation warnings, in 4.04 seconds. Evidence: M18-demo-bundle.json, M18-demo-compatibility-disabled.json, M18-benchmark-results.json and M18-benchmark-test-output.txt.

The full four-request A-B-C-D controller walkthrough and frontend screenshots remain open.
