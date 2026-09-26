# M18 Data Import & System Readiness — progress evidence

Recorded: 2026-09-25. This is an M18 technical slice, not the complete release gate.

## Implemented

- Added `/data-readiness` to the operational navigation.
- Department users can submit TMS, TDMS or SMMS JSON/CSV data only for their mapped department. Preview performs backend schema/domain validation, returns exact row errors and persists a content hash without applying data.
- Commit uses the exact preview ID/hash, applies valid rows through the real maintenance-request path, records quarantined rows and preserves the existing idempotent revision behavior.
- Added role-scoped readback for persisted import outcomes and accepted source identities/revisions. Department users see only their own batches and department records; planner/controller/auditor/admin roles can inspect integrated provenance.
- Planner/admin users can submit dated train occupancy, COA and freight source revisions through their existing typed APIs. Controller scope remains limited to COA and freight. No operational values are prefilled.
- Staff readiness reads the immutable snapshot manifest, source validity interval, declared coverage/evidence references, COA semantics, clearance margins, freight policy, frozen fact counts, effective source revisions and current workspace blockers.
- The live coverage probe is labeled as occupancy/COA presence only. It is not presented as freight completeness, authenticated authority or a safety certificate.
- Missing declarations, missing source rows, stale validity and backend failures remain visible as unknown, incomplete or blocked states.

## Verification

- `npm run typecheck` — passed.
- `npm run lint` — passed with no diagnostics.
- `python -m compileall -q backend/railsync tests/test_m02.py` — passed.
- Targeted database command:

  `RAILSYNC_TEST_PORT=55440; powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1 -q tests/test_m02.py tests/test_m04.py tests/test_m05.py tests/test_m18_workspace.py`

- Result: **14 passed**. The run reported upstream Starlette/httpx deprecation warnings and a non-test-impacting pytest cache permission warning.
- `npm run build` compiled the optimized application successfully in 35.1 seconds. The Codex Windows host then rejected Next.js's post-compile TypeScript child process with `spawn EPERM`; a complete production-build pass is not claimed.

## Boundaries

- These adapters accept explicitly supplied prototype inputs. They do not claim authenticated TMS/SMMS/TDMS or live railway connectivity.
- An imported source mode does not by itself prove completeness, freshness or operational authority.
- Snapshot validation context remains the controlling completeness/freshness declaration. Presence checks cannot repair missing declarations.
- Browser interaction and final 1440px/1920px visual acceptance remain open because the host process/browser restriction persists.
