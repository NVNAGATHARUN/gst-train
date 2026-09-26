# M16 replacement lineage and controller approval — verified slice

Recorded: 2026-09-18 11:25:36 UTC.

**151 cumulative tests passed** against PostgreSQL `railsync_test` on `localhost:55433` with two upstream Starlette deprecation warnings. Set `RAILSYNC_TEST_PORT=55433`, then run `.venv/Scripts/python.exe scripts/check_m16_approval.py`. The script ran `alembic upgrade head` and `pytest -q -p no:cacheprovider --junitxml=docs/evidence/M16-approval.xml`; exact command output is in `M16-approval-test-output.txt`, test cases in `M16-approval.xml`, and source SHA256 values in `M16-approval-sources.json`. No Git commit is claimed because host permissions block `.git` writes.

Saved actual API/worker result: `M16-approval-backend-example.json`. The explicitly **SIMULATED** fixture has an approved shared ENG/TRD possession and a new urgent Engineering request. The real CP-SAT replacement and independent validator returned `PASS`. Materialization linked replacement revision `3d7ebf30-a221-4277-80fd-23465938e763` to source revision `d35b8b6a-e57c-4720-bab3-26ae5eeb6887` in the same lineage. Its persisted, hash-checked difference reports two `UNCHANGED` requests and one `NEWLY_SCHEDULED` request. Controller decision `3d46cd87-4209-4fb2-86a0-05dc6b70b20e` atomically left zero source active reservations and created two replacement **SIMULATED** reservations; operational reservation count stayed zero.

The tests also verify a previously released shared possession with verified completed TRD work and assessed residual ENG work, wrong source decision, stale operational revision, missing validation, execution changes after validation, concurrent identical idempotency keys, latest-lineage enforcement, and controller edits requiring fresh independent validation. Failed approvals preserve prior reservations.

M16 remains open: controlled execution continuation and source-event reconciliation/rolling-horizon orchestration have not passed their gates. M17 must not start.
