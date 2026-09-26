# M18 frontend redesign evidence — 25 September 2026

## Scope completed

Research-led planning desk shell and navigation; actual-data timeline with non-overlapping visual rows, date-aware axis, zoom and exact-time register; Planning work/evidence rail; Corridor derivation and selected-source details; linked comparison controls and labeled metric pairs; saved task-phase visualization; controller decision navigation; common supporting-screen visual system; sign-in redesign; contrast refinement.

Backend services, migrations and domain rules are unchanged. No runtime dependencies were added. Existing session, API, CSRF, hash and controller mutation contracts are preserved.

## Executed checks

| Command/check | Observed result |
| --- | --- |
| `npm run typecheck` | Exit 0 |
| `npm run lint` | Exit 0 |
| `node scripts/check-presentation.cjs` | Exit 0; 14 checks pass after the saved-comparison regression check |
| Static API call comparison against pre-edit source copy | 28 files, 95 API/fetch calls, zero changed call sites |
| SHA256 comparison of pre-edit backend/migration files | Zero changed hashes |
| Final `npm run build` | Source compilation succeeds in 2.0s; Next TypeScript subprocess fails with `spawn EPERM`; exit 1 |
| Automated headless Chrome launch | `spawn EPERM`; no screenshot claimed |
| Native Chrome via computer-use | Guest browser opens; local URL shows connection refused. Later inspection interrupted by minimized-window/user-input state. No application screenshot claimed. |
| Initial HTTP preview probe | Connection refused on 127.0.0.1:3000 before the user restarted Next.js |

## Continuation: saved comparison and repeatable browser review

H3 now locates persisted comparisons through the read-only report artifact index when session storage is empty. It accepts a comparison only if the saved snapshot ID and hash and both plan revision IDs match the selected runs. While lookup runs, the screen says it is finding saved comparisons. The two new backend calls are GETs; the original 95 API/fetch call sites remain unchanged.

The H3 comparison preparation button now checks the same three permitted roles as the backend (`ADMIN`, `PLANNER`, `CONTROLLER`). A read-only user can still inspect saved comparisons but cannot submit a preparation action. The browser harness also waits for the selected snapshot and saved-comparison lookup before capture, and flags missing saved metrics as incomplete review coverage.

H2's empty COA-context message now directs the user to inspect policy and source evidence instead of calling the saved calculation operationally authoritative. Targeted TypeScript and ESLint checks pass; this is a wording correction, not a recalculation.

The presentation suite now checks the matching function against a real archived **SIMULATED** backend comparison, including rejected hash and revision mismatches. `npx tsc --noEmit --incremental false`, `npm run lint` and all 14 presentation checks pass. The standard incremental typecheck cannot write its cache under current sandbox permissions; the non-incremental compiler completed successfully.

`web/scripts/review-heroes.mjs` is a read-only, current-backend browser capture harness with instructions in `docs/M18_BROWSER_REVIEW.md`. Its syntax and lint checks pass. Its localhost preflight returns `ECONNREFUSED`. An attempted `npm run dev` on this host fails at Next's child process with `spawn EPERM`, so no screenshots, browser interaction results or visual acceptance are claimed.

A production-server fallback was checked: `.next/BUILD_ID` does not exist, and `npm run start` reports that no production build is available. No listener was present on port 3000. The next visual gate requires a preview started in an environment that permits Next's worker process.

## Live isolated preview continuation

The user restarted Next.js in their own terminal. `/login` and the frontend proxy now return HTTP 200. The original local PostgreSQL cluster could not recover on this sandbox (`could not signal for checkpoint: Operation not permitted`), so a **fresh isolated** cluster was initialized on localhost port 55434; no original data was changed. Alembic migrations completed, then `tests/test_m15.py::test_same_snapshot_comparison_uses_persisted_intervals_and_honest_nulls` passed and saved a genuine **SIMULATED** first-feasible baseline, CP-SAT proposal, validation and comparison.

FastAPI is running against that isolated test database on localhost port 8000. The live authenticated `scripts/m18_frontend_smoke.py` check passes through the Next.js proxy: sign-in 201, session 200, three snapshots, one confirmed occupancy, two maintenance demands, 11 generated candidates, three capacity windows, an `OPTIMAL` CP-SAT result, a persisted `VALIDATED_COMPARISON`, and HTTP 200 for Planning, Corridor, Evaluation, Validation, Controller Review and Optimization. These are saved simulated backend outputs, not live railway data or current operating authorization. The smoke script was corrected to select a CP-SAT revision explicitly, rather than whichever proposal appeared first.

The browser review script preflight now passes. Chrome launch from this sandbox returns `spawn EPERM`; in-app browser kernel initialization also fails. Thus no screenshots, interaction results, 1440px/1920px visual judgment or accessibility acceptance are claimed. The user can run the read-only harness from their normal terminal while the isolated services remain available.

The earlier and final separate TypeScript checks pass. The production build is still not a passing gate. No database test, live API session, controller submission or current end-to-end workflow was run or claimed in this redesign slice.

## Saved artifacts

- `M18-redesign-presentation-checks.json`: named checks, archived SIMULATED fixture scope and browser-acceptance limitation.
- `M18-redesign-contract-audit.json`: static call-preservation counts.
- `M18-redesign-source-hashes.json`: final frontend source hashes for this slice.
- `../M18_FRONTEND_REDESIGN.md`: source citations, design decisions, implemented behavior and pending acceptance checklist.

Git status exposes the project as untracked. No commit was created; the source hashes identify the work. A local pre-edit frontend copy was retained in the Codex workspace.

## Next gate

Inspect the real five hero screens at 1440/1920, exercise their interactions and failure states, inspect all supporting pages, and complete responsive/keyboard/200%-zoom checks. The HTTP integration gate now passes on the isolated simulation; the production build and visual gates remain open. Do not mark M18 or the complete frontend redesign visually accepted yet.

## Five-hero browser capture and H1 correction — 26 September 2026

The user-run read-only harness produced `docs/evidence/browser-review/2026-09-25T18-34-36.495Z/`: 15 screenshots across Planning, Corridor, Evaluation, Validation and Controller Review at 1440/1920/390 pixels. It recorded successful timeline zoom, evidence-inspector selection, mobile navigation and saved comparison metrics, with no horizontal page overflow or blocked writes. The case is a stale **SIMULATED** snapshot viewed under a PLANNER role; current approval is blocked. The first run's `REVIEW_ISSUES_FOUND` status came from 12 canceled navigation GETs and three handled first-revision difference 404s. The script now reports those separately and continues to flag unhandled failures. A rerun of the changed script is still needed.

Screenshot inspection found the five hero layouts coherent at desktop and mobile, with source staleness and prototype authority visibly disclosed. It also found one genuine H1 data contradiction: the Planning session panel displayed “Not run” for baseline and CP-SAT despite saved results. H1 now displays saved run statuses from the selected snapshot/revision and explicitly distinguishes an unselected or unrecorded planning session. The updated harness asserts that recorded baseline and CP-SAT results are not hidden by “Not run” labels. The corrected screen has not yet been recaptured. Targeted TypeScript, ESLint, script syntax and all 14 presentation checks pass. This is a focused visual review of one historical fixture, not final visual acceptance across roles, failures, accessibility or 200% zoom.

The supplied 16-screen visual reference informed a narrow presentation update. Sign-in now has a dark railway-planning brand panel, an abstract non-data corridor motif, clearer credential form and mobile-first form order. The Overview has a distinct but restrained heading and stronger metric hierarchy. No API, authentication, snapshot, optimizer, validator or KPI behavior changed. The read-only capture harness now includes unauthenticated sign-in at 1440/390 and the selected-case Overview at 1440/1920/390, in addition to the five hero screens. Targeted TypeScript, ESLint, script syntax and all 14 presentation checks pass after this change. The new visual work still requires a browser capture before acceptance.

The user-run recapture at `docs/evidence/browser-review/2026-09-25T18-58-00.395Z/` produced 20 screenshots and `CAPTURED_REQUIRES_VISUAL_REVIEW`: zero page overflows, browser exceptions, HTTP errors and blocked writes; saved H3 metrics and Planning interactions are visible. H1 now displays baseline `COMPLETED` and CP-SAT `OPTIMAL` alongside “No session recorded.” Sign-in and Overview have the intended hierarchy at desktop/mobile. Screenshot review exposed an Overview CSS selector that styled every direct span as a numbered circle, collapsing workflow status badges. The selector now targets only the step number; this correction still needs a new capture. The login image also showed a Next.js development “1 Issue” indicator, so the harness now records console errors and development-indicator labels for diagnosis on the next run. No production behavior has been inferred from the development badge.

Capture `2026-09-26T02-45-40.893Z` confirms readable Overview workflow status badges and no page overflow in 20 views. Console diagnostics identify a login hydration mismatch involving `style={{caret-color: transparent}}` on the credential input. This matches Playwright screenshot caret hiding before hydration; all screenshots now preserve the initial caret to avoid that DOM mutation. The harness now treats non-resource console errors as review failures rather than silently accepting hydration warnings. Inspection also found a department-chart selector that clipped department badges to the bar height; it now targets only the second span (the actual bar). Script syntax, ESLint and workspace CSS parsing pass. Both latest changes require recapture; full M18 visual acceptance remains open.

Final refinement capture `2026-09-26T02-54-42.969Z` verifies these corrections. The report contains 20 views with no page overflow, browser exceptions, unhandled API errors or blocked writes, and saved comparison metrics remain visible. No hydration warning appears in console diagnostics; the login development indicator is only “Open Next.js Dev Tools.” Desktop/mobile Overview screenshots show full ENG/TRD/S&T labels and readable workflow status badges. H1 retains actual baseline COMPLETED and CP-SAT OPTIMAL statuses. The remaining resource-console messages correspond to unauthenticated session checks (401) and recorded absence of first-revision difference artifacts (404), already handled by the application. This closes the specific sign-in/Overview refinement bugs for the stale SIMULATED PLANNER fixture. It does not close broader roles, failures, keyboard, 200%-zoom, supporting-page or deployment acceptance.
