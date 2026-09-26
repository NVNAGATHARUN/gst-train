# M18 foundation — browser sessions and planning workspace contracts

Design: [approved M18 UX specification](M18_UX_DESIGN.md), version 1.1. This is a foundation slice, not M18 completion or hero-screen acceptance.

## Browser sessions

`POST /api/v1/auth/session` accepts `{ "credential": "<provisioned personal credential>" }`. The existing bearer credential is exchanged for a random server-side session. This is prototype credential provisioning, not password authentication, SSO or a new identity provider. Never put credentials into a public frontend bundle, URL, localStorage or screenshot. The sign-in form must clear the entered credential after the exchange.

The response returns user identity, expiry and a session-bound CSRF token. It sets the host-only `railsync_session` cookie with HttpOnly, Secure, SameSite=Strict and Path=/. PostgreSQL stores only the session secret hash. Sessions have a fixed configurable lifetime (default eight hours), become invalid on logout, user deactivation or credential rotation, and rotate on another login. Identity/role checks are repeated on each API request.

`GET /api/v1/auth/session` restores identity/expiry/CSRF state after a browser refresh. `DELETE /api/v1/auth/session` revokes the current session and clears the cookie. Cookie-authenticated writes require an exact configured Origin and `X-CSRF-Token`; login itself requires the trusted Origin. Cross-site fetch metadata is rejected. Mixed cookie/bearer authentication is rejected rather than silently choosing a different identity. Bearer-only clients remain supported for CLI/test integrations.

All API responses are `Cache-Control: no-store`. Authentication input errors omit submitted input values. Audit records contain session IDs and lifecycle events, never cookie/credential/CSRF secrets. Login attempts are durably limited to ten per minute per transport client address, including failed credentials; forwarded headers are not trusted.

Configuration:

- `RAILSYNC_BROWSER_ORIGINS`: JSON array of exact origins, e.g. `["https://localhost:3000"]`.
- `RAILSYNC_SESSION_COOKIE_SECURE=true` by default.
- `RAILSYNC_SESSION_TTL_MINUTES=480` (5–1440).
- Local HTTP requires explicit `environment=development|test`, an exclusively loopback origin and `secure=false`. Production rejects insecure cookie configuration. Origins cannot contain wildcards, paths, query strings or embedded credentials.

Deployment still needs TLS/reverse-proxy setup and a secure credential-provisioning procedure. The proxy may cause many clients to share the transport-level login limit; trusted proxy identity configuration must be reviewed before external deployment. The UI must distinguish failed login, expired session and forbidden role. No frontend session integration or production deployment has been verified by this backend slice.

## Browsing artifacts

`GET /api/v1/workspace/snapshots?scenario=SOURCE|SCENARIO|ANY&track_id=...&limit=25&cursor=...`

Returns a typed page of snapshot summaries: IDs/hashes, exact horizon, footprint, creation time, scenario and declared source scope. The default excludes isolated scenarios. Unknown scope remains UNKNOWN. It does not infer live data authority.

`GET /api/v1/workspace/runs?snapshot_id=...&limit=25&cursor=...`

Returns job state, solver state, incumbent presence and linked saved revision IDs as separate fields. COMPLETED is not validation or approval. Both APIs use stable descending creation-time/UUID keyset pagination, maximum page size 100, and query-bound opaque cursors. Invalid or cross-filter cursors return 422. Filters are presentation filters, not corridor authorization grants.

These cross-department aggregate reads are restricted to existing ADMIN/PLANNER/CONTROLLER/AUDITOR roles. DEPARTMENT users continue using scoped maintenance/assets APIs; they cannot use the new workspace aggregate routes. Existing prototype staff access covers the declared network; per-corridor entitlement management and a complete legacy-route authorization audit remain release work. This slice does not claim production corridor isolation.

## Snapshot-bound workspace

`GET /api/v1/snapshots/{id}/workspace?run_id=...&plan_revision_id=...`

Selection is explicit. Omitting both IDs returns frozen facts/demand with NOT_ASSESSED readiness and no selected plan, candidate bars or priority fallback. Supplying unrelated snapshot/run/revision references returns 409. Snapshot and selected revision hashes are checked. The result includes:

- Frozen source facts and snapshot summary.
- Actual selected run/revision and its referenced opportunity/coordination/availability artifacts.
- Exact priority policy/assessment instant used by the opportunity; later assessments cannot overwrite that context.
- Latest independent report for the selected revision, current usability and blockers.
- Request payloads, selected/deferred outcome, resource/rule/predecessor evidence and access requirements.
- Stored explanations, if generated; an absent explanation stays absent.

This projection does not recalculate availability or validate feasibility. It does not promise atomic future approval. The controller write transaction still rechecks state, hashes, reservations and exact validation evidence.

### Readiness and access semantics

Readiness is scoped to **SELECTED_PROPOSAL_CONTEXT**, not field execution. READY requires an actual selected assignment and current usable independent PASS. A selected unvalidated proposal or unresolved evidence remains CONDITIONAL. Known current blockers can yield NOT_READY; missing/unknown context never yields READY. Without a selected plan it is NOT_ASSESSED. Every result includes reasons and `execution_authorized: false`.

LINE BLOCK comes from `block_required`; POWER BLOCK from `power_block_required`; isolation zone and signalling requirements retain their explicit facts. S&T DISCONNECTION is required only for DISCONNECTED. Missing values stay UNKNOWN; department alone is not an access requirement. `provision_status: NOT_EVIDENCED` prevents a requirement badge being mistaken for an actual block grant, completed isolation or performed disconnection.

No-forecast data is not converted to zero traffic, and missing resources are not generated by this API. A report becoming stale changes readiness/current usability while preserving the historical plan.

## Durable planning sessions

`POST /api/v1/planning-sessions` (ADMIN/PLANNER) accepts an idempotency key, snapshot ID, expected snapshot hash and typed solver options. It records one immutable request and returns 202 with `QUEUED_PREPARATION`. The same actor/key/body returns the same session; reuse with changed input is rejected. Missing, stale, incomplete or unknown declared source context is rejected. Scenario and execution-aware replanning snapshots use their existing dedicated workflows.

`GET /api/v1/planning-sessions/{id}` restores the session after refresh. `GET /api/v1/workspace/planning-sessions?snapshot_id=...` browses saved requests with bounded keyset pagination.

The existing worker first prepares one queued session, then processes the existing leased planning jobs. Preparation is a transaction protected with row locks and source-publication serialization. It commits priority, availability, opportunities, coordination and the paired jobs together. A worker interruption rolls back to QUEUED_PREPARATION; a recoverable blocked/error result is saved without invented runs. A fresh worker can take an interrupted queued request. Existing immutable computation artifacts may be reused by content identity; each explicitly new planning request still queues real new baseline/CP-SAT jobs.

Both planners reference the same snapshot, coordination candidates, traffic policy, priority context and solver configuration. Solver weights are recorded. A repeated session is not an excuse to degrade the baseline or return a saved schedule as newly computed output.

Preparation state and actual worker/solver states remain separate. COMPLETE means both jobs finished, not that a feasible incumbent exists. Materialization, independent validation and controller review are separate API actions. UNKNOWN/INFEASIBLE/FAILED stay visible; there is no generated percentage-progress indicator or timeout fallback schedule.

Asymmetric clearance remains unsupported by the current run contract; the session returns an explicit blocker rather than silently normalizing it. Candidate generation remains bounded by the existing engine configuration; configurable search controls and detailed boundary provenance are later H1/H2 integration work. Worker lock timeouts may require a worker restart; queued preparation stays durable.

## Remaining M18 work

Secure frontend integration; read/authorization completion for review/audit/supporting flows; boundary derivation evidence; global shell; H1 implementation and visual acceptance; the remaining heroes; support screens; deployment; benchmarks; recovery/backup checks and the full release gate.

Each hero must stop for functional evidence plus screenshots at 1440px/1920px and failure/empty/stale states, critique, correction and user visual approval. The foundation tests do not satisfy any hero's visual acceptance.
