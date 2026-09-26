# M18 browser acceptance attempt — 2026-09-25

**Result:** Browser and wide-screen visual acceptance remain OPEN. This record does not claim 1440px or 1920px verification.

## Environment observations

- The in-app browser had no live RailSync tab. Opening `http://127.0.0.1:3000` returned `ERR_CONNECTION_REFUSED`; no frontend was listening.
- The existing development PostgreSQL cluster on port 55432 was interrupted during recovery. `scripts/local_db.py` timed out, and its log recorded `could not signal for checkpoint: Operation not permitted`. No recovery or data alteration was attempted.
- An isolated test PostgreSQL instance on port 55440 accepted connections. A separate FastAPI instance started successfully on port 8001 against its `railsync_test` database and was stopped after frontend startup failed. Port 8000 was already occupied by another process and was not changed.
- `npm run dev` for the existing Next.js frontend failed before serving with `spawn EPERM`. Attempts to start the built frontend were rejected by automatic execution review; the review required an approval category unavailable in this session. There was no browser page to inspect.

## Focused source/layout review

H1–H5 styles have explicit desktop-to-smaller-screen grid breakpoints and horizontally scrollable dense timeline primitives. Source review alone cannot prove width, clipping, focus, contrast, interaction or operational comprehension at the required viewport sizes.

One concrete issue was corrected in the shared `StatusBadge`: worker `RESPONSIVE` and active users now use the good state; overall `DEGRADED`, worker `ABSENT` and inactive users use the bad state. Previously those values fell through to the neutral information tone. `npx tsc --noEmit --incremental false` and targeted ESLint on the badge and System page passed.

## Next acceptance run

Use a host that can start the Next.js frontend and a healthy isolated simulated database. Review H1–H5 and supporting screens at 1440px and 1920px, with ADMIN/PLANNER/CONTROLLER/department roles, loading/empty/stale/failure states, keyboard focus and actual backend evidence. Save screenshots and interactions before checking any visual-acceptance box.
