# M18 H3 — Baseline vs RailSync technical gate

Date: 2026-09-24. This is a technical slice of M18, not the complete M18 release gate.
Commit: none recorded; the current repository contents are untracked, so this evidence is tied to the working tree rather than a commit hash.

## Backend-backed behavior

The Comparison screen selects a completed planning session or a baseline and CP-SAT run pair from one snapshot. It reads both saved run results. On the explicit **Prepare comparison** action it materializes both proposals, runs independent validation for each, and calls the existing `/plan-comparisons` API. The backend rejects mismatched requirements, candidates, priorities, solver configuration or snapshot hashes. A comparison ID is retained in browser session storage; no credential or computed KPI is stored there.

The page renders the saved comparison's status, current validation states, signed KPI changes, units, denominator evidence and two timelines assembled from the same snapshot facts plus each saved plan. It presents zero-baseline percentages as N/A. Historical or failed validation blocks current benefit claims in the UI. Planned track availability is explicitly distinguished from asset reliability; forecast exposure is distinguished from measured delay. No KPI or proposal is hard-coded in the frontend.

## Verification

| Check | Result |
| --- | --- |
| `tsc --noEmit --incremental false` | Passed after final H3 changes. |
| `npm run lint` | Passed after final H3 changes. |
| `RAILSYNC_SKIP_NEXT_TYPECHECK=1 npm run build` | Passed after a separate TypeScript check; `/evaluation` included in production routes. |
| `scripts/test.ps1 -q -p no:cacheprovider tests/test_m15.py tests/test_m18_workspace.py tests/test_m18_planning_sessions.py` | 19 passed on isolated PostgreSQL port 55438; two upstream deprecation warnings. |
| `tests/test_m15.py::test_same_snapshot_comparison_uses_persisted_intervals_and_honest_nulls` | Passed; left a labeled simulated comparison for the browser check. |
| Browser flow through local production Next.js and FastAPI | Signed into isolated demo, selected saved baseline and CP-SAT, prepared comparison, reloaded and recovered comparison by ID. KPI method selection and denominator display worked. |

The observed **SIMULATED** fixture from 21 Sept 2026 had two scheduled requests in both plans. The baseline had two possessions and 120 reserved track minutes; CP-SAT had one integrated possession and 80 reserved track minutes. These are real saved results for that fixture, not a general performance claim. On 24 Sept the source declarations were expired: both new validation reports were FAIL, and the page displayed **Historical or unvalidated comparison** with current claims blocked. Mandatory coverage and measured delay correctly appeared as N/A. The displayed 40-minute favorable change is historical fixture arithmetic only.

## Remaining M18 work

Final H1–H3 visual approval at 1440px/1920px, H4 Validation Center, H5 Controller Review, supporting screens, deployment and benchmarks remain open.
