# M14 - weekly/monthly schedules and exports

M14 creates immutable reporting artifacts from a single canonical `PlanRevision`. It does not create a second scheduler or change assignments. The artifact copies the persisted selected candidates, task stages, resource allocations, deferred reasons, plan hash and snapshot hash.

## Calendar boundaries

`POST /api/v1/planning-schedules` accepts either:

- `WEEKLY` with `week_start` (`YYYY-MM-DD`), producing seven local-calendar days; or
- `MONTHLY` with `year` and `month`, producing the actual calendar month, including leap years.

The caller supplies an IANA timezone, defaulting to `Asia/Kolkata`. Local midnight boundaries are preserved and elapsed minutes account for timezone offset changes. The referenced snapshot must cover the entire requested period. A partial plan is rejected with `PLAN_HORIZON_DOES_NOT_COVER_PERIOD`, rather than presented as a weekly or monthly schedule.

## Status and uncertainty

Each schedule records the exact validator report and current usability at creation time. It labels assignments as `FIRM` only when a current approved reservation exactly matches the canonical possession, track footprint and resource allocation. Non-approved work is `TENTATIVE`; an approved plan with stale validation is `REQUIRES_ATTENTION` and the schedule status becomes `STALE_APPROVED_PROPOSAL`.

The schedule exposes `data_valid_until` and declared freight coverage end per track. It never translates missing forecast coverage into zero traffic. `APPROVED_PROPOSAL` is explicitly software-proposal status, never railway possession authority.

## Exports

`GET /api/v1/planning-schedules/{id}/export?format=json|csv` serves a deterministic export of the immutable artifact. JSON is canonical sorted JSON. CSV carries the plan/snapshot hashes, authority label, firm/tentative status, forecast coverage status, exact setup/work/restoration timestamps and deferred reasons. Cells beginning with spreadsheet formula prefixes are escaped. The response includes the persisted schedule content hash.

The M14 suite covers full-horizon rejection, seven-day and real-month boundaries, leap day and DST elapsed-minute calculations, current/stale firm status, immutable schedule records, deterministic exports, CSV formula safety, role checks and a persisted backend example.
