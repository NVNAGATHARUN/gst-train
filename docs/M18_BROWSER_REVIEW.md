# M18 five-screen browser review

The capture harness reads the current local backend. It never substitutes mocked API responses or creates planning/validation/comparison artifacts. It creates and revokes its own authenticated browser session. Other browser API writes are blocked.

## Prerequisites

- FastAPI and the Next.js preview running with a working proxy.
- A provisioned PLANNER, CONTROLLER, AUDITOR or ADMIN credential able to read planning evidence.
- At least one saved CP-SAT proposal. A saved paired session/comparison is needed for a populated comparison view; absent evidence stays absent.
- Installed Chrome or Edge; optional `RAILSYNC_REVIEW_BROWSER` points to another installed Chromium executable.

From PowerShell:

```powershell
cd E:\sih_codex_train\web
node scripts/review-heroes.mjs --preflight
$env:RAILSYNC_VISUAL_CREDENTIAL = [System.Net.NetworkCredential]::new('', (Read-Host 'Prototype credential' -AsSecureString)).Password
node scripts/review-heroes.mjs
Remove-Item Env:\RAILSYNC_VISUAL_CREDENTIAL
```

Do not paste the credential into chat. The script redacts it from errors and does not save browser storage or an authenticated trace.

## What the harness checks

- Actual sign-in, saved snapshot/proposal selection and optional paired-session selection.
- Saved baseline and CP-SAT status labels must agree with the persisted runs selected for review.
- Diagram scale controls and selection opening the evidence inspector.
- Screenshots of Planning, Corridor, Comparison, Validation, Controller Review and the saved-case Overview at 1440, 1920 and 390 pixels; unauthenticated sign-in at 1440 and 390 pixels.
- Horizontal page overflow, JavaScript exceptions, failed API reads and mobile navigation.
- Existing empty/error/blocking states are recorded, not replaced by success data.

Screenshots and `review.json` are saved in `docs/evidence/browser-review/<timestamp>/`. Inspect them locally: they can contain the selected planning case. No data is uploaded.

`CAPTURED_REQUIRES_VISUAL_REVIEW` means capture completed without the automated issues listed above. It does **not** mean visual acceptance. `REVIEW_ISSUES_FOUND`, `INCOMPLETE_EVIDENCE` and `BLOCKED` return exit code 1. A comparison without saved metrics is reported as incomplete review coverage even if screenshots are captured successfully.

## Human review still required

- Judge hierarchy, information density and readable evidence at both desktop sizes.
- Verify the exact reasons behind selections and failed validation using recorded backend facts.
- Confirm actual comparison metrics, linked scrolling and boundary labels.
- Keyboard navigation, focus order, 200% zoom and color/contrast across all real states.
- Role-specific controller behavior in an isolated test workflow; this harness intentionally submits no decisions.

## Current execution status

Script syntax, ESLint, TypeScript and 14 presentation checks pass. The user-started Next.js preview, isolated simulated FastAPI service and authenticated proxy smoke are reachable. Chrome launch remains blocked inside the Codex sandbox (`spawn EPERM`), but the user ran the harness from normal PowerShell. It captured 15 real-backend screenshots in `docs/evidence/browser-review/2026-09-25T18-34-36.495Z/`: five hero screens at 1440, 1920 and 390 pixels. Timeline zoom, interval inspection, mobile navigation, saved comparison metrics and no horizontal page overflow were recorded. The evidence is an old, stale **SIMULATED** snapshot viewed as PLANNER; it is not a current operating approval case.

That run reported `REVIEW_ISSUES_FOUND` because it counted 12 canceled GET requests during page navigation and three handled 404 responses for a first revision with no difference artifact. The harness now records these separately as `expected_navigation_cancellations` and `expected_absences`; real HTTP/browser failures still fail the run. It also exposed an actual H1 contradiction: the selected saved CP-SAT and baseline results existed while the session panel said “Not run.” H1 now reads persisted run summaries and distinguishes an unselected or unrecorded session. A focused brand pass also changed sign-in and overview presentation, without changing API or operational data. **A post-fix browser capture has not run yet.** Visual acceptance, accessibility and broader role/state coverage remain open.

The later run at `docs/evidence/browser-review/2026-09-25T18-58-00.395Z/` captured 20 views, including sign-in and Overview. It recorded no page overflow, browser exceptions, HTTP errors or blocked writes. Saved H3 comparison metrics and the corrected H1 baseline/CP-SAT statuses are visible. Visual inspection found a separate Overview badge-selector bug, now corrected in CSS but not yet recaptured. The login screenshot also contains a Next.js development “1 Issue” badge; the harness now records console errors and development-indicator labels on the next run so its cause can be assessed before the demo. This is still one stale SIMULATED PLANNER case, not final role/state/accessibility acceptance.

The final refinement capture `2026-09-26T02-54-42.969Z` verifies readable department labels and workflow badges on desktop/mobile, and no sign-in hydration warning. Preserving the screenshot caret removed the DOM mutation that triggered the warning. All 20 captured views have zero page overflow, browser exceptions, unhandled API errors and blocked writes; saved comparison metrics are visible. These specific fixes are verified. Broader role/failure/accessibility and supporting-page review remains open.


## Focused keyboard and enlarged-layout review

Add `--accessibility` to the existing command to verify keyboard activation of the skip link, timeline scale and a real interval, and capture five additional hero views with CSS zoom set to 200%. This is a labeled CSS reflow check, not native browser zoom or a complete accessibility audit. All operational data still comes from saved backend results. These added checks await execution in normal PowerShell. Failure-state and role coverage remain open. H3 now displays an unavailable state instead of indefinite loading after a failed saved-run request.


### 2026-09-26 keyboard review result and method correction

Run `2026-09-26T03-05-31.928Z` verified skip-link focus, Enter activation of timeline scale with pressed state, and keyboard selection of a real interval with evidence inspector. All 20 standard views had no page overflow, browser exceptions, unexpected HTTP errors or writes. The five CSS-zoom captures failed: CSS zoom left viewport media queries at desktop width and compressed desktop grids. They are not accepted. The original report is preserved. The harness now captures 720 CSS-pixel viewport layouts, the reflow width corresponding to 1440 / 2, explicitly labeled as a viewport proxy. Native browser zoom, full focus-order/contrast, role and failure-state gates remain open.


### Corrected reflow evidence inspected

Run `2026-09-26T03-09-17.603Z` completed 25 real-backend captures with no page overflow, browser exceptions, unexpected HTTP errors or blocked writes. H1–H5 720 CSS-pixel screenshots were visually inspected: contextual selectors, status summaries, proposal/constraint evidence and controller actions stack without the narrow columns seen in CSS zoom. Timeline diagrams retain their internal horizontal scrolling. The current stale SIMULATED case remains visibly blocked despite historical validator PASS; missing explanations remain explicit and PLANNER cannot submit controller decisions. Focused skip-link, timeline-scale and interval-selection keyboard assertions passed again. This accepts the narrow reflow proxy gate only. Native browser zoom, comprehensive keyboard/contrast, actual FAIL/ERROR/API failure states, controller-role workflows, supporting screens and production/deployment remain open.


## Read-only failure and recovery review (execution pending)

Run the existing script with `--failure-states` to abort domain GET requests on fresh H1–H5 page loads. Authentication remains real and no fabricated domain response is supplied. Assertions require visible connection errors, loading termination, absence of timeline/comparison results, and absent/disabled approval. Restoring access and reloading must restore saved timeline evidence; H3 must restore saved comparison metrics. Ten additional fault/recovery screenshots are recorded separately from normal operational captures. This covers initial-load connection failures only; in-session stale results, HTTP-specific failures, validator FAIL/ERROR and actual controller-role decisions remain separate gates.
