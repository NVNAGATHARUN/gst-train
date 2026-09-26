# M16 approved replacement execution continuation — verified slice

Recorded: 2026-09-18 11:56:14 UTC.

**155 cumulative tests passed** against PostgreSQL `railsync_test` on `localhost:55433`, with two upstream Starlette deprecation warnings. Set `RAILSYNC_TEST_PORT=55433`, then run `.venv/Scripts/python.exe scripts/check_m16_continuation.py`. The script ran Alembic `upgrade head` and the full `pytest -q -p no:cacheprovider` suite. Exact commands/results are in `M16-continuation-test-output.txt`; test cases are in `M16-continuation.xml`; Python source SHA256 values are in `M16-continuation-sources.json`. No Git commit is claimed because host permissions block `.git` writes.

Saved backend examples come from explicitly **SIMULATED** fixtures and actual API/worker/validator code:

- `M16-continuation-preserved.json`: source revision `cafbdb17-3765-4279-8dd5-6bc31ea6cc3c` and approved replacement revision `7b53e867-9b86-47fc-9143-1ecbaeeec0b6` retain the exact shared ENG/TRD assignment. Controller observation `062ff272-dd03-44ad-ad46-30738989dac3` continues a previously `STARTED` request to `COMPLETED`, with `PRESERVED_ASSIGNMENT` provenance. It does not authorize execution or release a reservation. A further observation or capture against the superseded source approval is rejected.
- `M16-continuation-residual.json`: verified restoration and 40-minute remaining-work assessment lead to a new approved assignment. Observation `5b025546-c86d-4b9f-ad6b-f456099711d2` is `RESUMED` with exactly 40 minutes and `VERIFIED_RESIDUAL_RESTART` evidence; observation `c763cca8-26b4-473f-923d-0ab8cfb062c5` completes it. Verified release `337850f0-05ca-4172-b8a7-ece9cff23ed9` closes the replacement possession and its simulated reservation.

Tests reject incorrect residual minutes and restart before restoration without writing an observation. Concurrent identical delivery advances the sequence once. After the residual release, a second capture retains both historical approvals and all execution evidence; a fresh snapshot has zero pending requests, the real planning pipeline produces zero scheduled work, and independent validation returns `PASS`. Deliberately corrupting the captured cross-approval link makes that validator block review.

M16 remains incomplete. Source-event reconciliation and rolling-horizon orchestration across supported disruptions remain pending; M17 has not started.
