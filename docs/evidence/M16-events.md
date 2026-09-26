# M16 event intake slice - verified, full milestone incomplete

Recorded: 2026-09-16T02:46:56.788657+00:00

Cumulative automated tests: 106 passed against PostgreSQL railsync_test on port 55432.
Command: `.venv/Scripts/python.exe scripts/check_m16_events.py`.
Exact source hashes: M16-events-sources.json. Test commands and results: M16-events-test-output.txt and M16-events.xml.
Backend evidence: M16-events-backend-example.json. M14 and M15 examples were refreshed from executed tests.

No source commit is claimed; this workspace has no recorded project commit. The source manifest identifies tested files.

Verified: event identity/immutability, concurrent duplicate delivery, debounce generations, old snapshot invalidation, approval blocking, reservation preservation and late-worker publication rejection. M15 percentage/union repairs and real M14 full-horizon solver tests are included.

M16 remains unchecked. Frozen/executed work, automatic fresh-state replanning, replacement diff and independent replacement validation/approval are still required. See M16_REPLANNING_STATUS.md.
