# RailSync M18 — Planning desk redesign

Date: 25 September 2026  
Status: implementation and source checks complete for the slice below; browser acceptance open.  
Authority: the user's frontend rebuild direction supersedes the earlier frozen visual layout. Backend architecture, contracts and domain rules remain protected.

## Product decision

RailSync should present a **planning desk**: inspect railway facts, understand usable capacity, coordinate maintenance, assess a proposal, then make a recorded human decision. The timeline is the primary working surface. Counts support that surface rather than displacing it.

The earlier implementation contained useful evidence but gave fifteen navigation destinations equal prominence, used many small status cards, compressed the timeline between two persistent sidebars and obscured overlapping intervals. Some clickable diagram evidence did not produce an obvious detail response. These are information architecture and interaction problems, not just color problems.

## Research and how it informed the implementation

These are design references, not a claim of railway certification, production readiness or feature parity.

| Primary source | Relevant observation | RailSync design decision |
| --- | --- | --- |
| [RMCon: construction management with RailSys](https://rmcon-int.de/wp-content/uploads/2024/07/Construction_Management_EN.pdf) | Describes restrictions in location/time, graphical timetable views, capacity gaps and coordination of construction work. | Keep track/time, restrictions and generated windows together. The corridor screen explains COA, protection policy and saved output in order. Do not introduce rerouting or calculate train delays the RailSync backend does not support. |
| [OpenTrack: railway simulation](https://www.opentrack.ch/mobile/opentrack_e/opentrack_e.html) | Presents timetable information graphically and in tables, including comparison with actual records. | Pair the diagram with an exact-time interval register. Link scale, horizontal position and track selection in baseline/RailSync views. Planned and observed execution remain distinct. |
| [IBM Carbon: data tables](https://carbondesignsystem.com/components/data-table/usage/) | Places search, filtering and actions near the data and supports progressive disclosure for detailed records. | Search/filter the work queue where it is used. Open evidence in a contextual side panel. Retain detailed tables for audit and exact values. |
| [W3C: use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html) | Meaning must not depend on color alone. | Named source/computed/proposal lanes, readable badges, hatching for forecasts/restrictions, textual statuses and a table alternative. |
| [W3C: minimum target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) | Small controls need adequate target size or an equivalent accessible control. | Increase diagram row/button height; expose exact selectable entries in the register when a short interval is too narrow. Keep its actual time width instead of stretching it. |

The design decisions are our interpretation of those sources. No external interface was copied wholesale. No new operational capability is inferred from a competitor's product.

## Information architecture

Four stable groups retain every existing route:

1. **Planning desk:** Overview, Block planning, Maintenance demand, Corridor & COA.
2. **Proposal & decision:** Planning sessions, Baseline comparison, Independent validation, Controller review.
3. **Delivery & records:** Weekly/monthly plan, Replan & what-if, Execution & handback, Reports & audit.
4. **Data & configuration:** Data readiness, Network & rules, System health (ADMIN).

The header identifies the current workspace and signed-in role. Account/sign-out remains accessible when the navigation collapses. A saved case is still bound to the original session-scoped snapshot/session/revision selection. The redesign does not infer a latest plan from unrelated runs.

## Visual and interaction system

- White utility header; dark, restrained navigation rail; neutral work surface; steel-blue primary actions.
- System Segoe UI/Arial typography. No remote font dependency, decorative illustration dependency or new runtime package.
- Page title 25–28px; panel title 13px; operational content 12–13px; compact metadata remains secondary. Tabular numbers and monospaced identifiers serve different purposes.
- ENG/TRD/S&T retain distinguishable labeled department treatments. Status color is always accompanied by text.
- Summary bands share a single container. Tables have consistent padding and separators. Selected work and evidence have a clear visual boundary.
- Desktop diagram + 310px work/evidence rail; wider rail on large displays. Below 850px the diagram comes first and the queue/inspector moves below. Below 600px navigation opens as a labeled menu.
- Skip link, visible focus, labeled icon navigation, keyboard-scrollable timeline and a selectable exact-time register. Reduced-motion preference is respected.
- Light-surface foreground colors were checked numerically and darkened where necessary. This is not a complete accessibility audit; browser keyboard, zoom and computed-style verification remain required.

## Implemented screen changes

### Block planning

The timeline owns the main column. A switchable Work queue / Evidence rail replaces the two permanently competing sidebars. The work queue filters by department, issue, request ID, asset and track. Selecting demand or a diagram interval opens its evidence. Mandatory and shown-request counts are calculated from the loaded demands, not illustrative constants.

Priority, access requirements, readiness, named resources, compatibility rules, source blockers and backend stage states remain visible. Setup/work/restoration are drawn from saved task subintervals on a common possession scale. Saving and validation actions still use the existing hashes and API bodies.

### Corridor & COA

The derivation strip shows the actual saved COA record count, clearance policy, freight protection state and returned window count. It does not claim a nearby fact caused a specific window boundary. Clicking a source interval now opens its actual track/start/end before the window derivation details. Unknown calculations and empty results remain distinct.

### Baseline vs RailSync

Metric pairs label each side separately and wrap long units. Negative favorable changes remain visible. Both diagrams use the same selected track, zoom and horizontal offset, with their original run assignments. Existing same-snapshot checks, validation semantics and KPI formulas are untouched.

### Independent validation

Constraint categories, findings and evidence have a more readable three-area layout, collapsing deliberately at narrower widths. Recorded result, current review use, source blockers and historical validation remain separate. All source data and report actions are unchanged.

### Controller review

Assignment cards reuse the actual task-phase visualization. A prominent “Review decision” anchor moves to the existing action form without submitting a decision. Permission, scenario isolation, frozen-work checks, reason entry, idempotent retries and revalidation logic are unchanged. Nothing in the design converts PASS into operational authority.

### Supporting screens and sign-in

All existing supporting pages inherit the new shell, readable controls, summary bands, tables and responsive treatments. Sign-in has a clearer access-credential explanation and a concise department/workflow introduction. No made-up railway map, occupancy graphic or performance result is shown at sign-in.

Supporting pages still require per-screen browser review; shared styling alone is not final acceptance of each screen.

## Diagram correctness

`timeline-layout.ts` is presentation logic only:

- Adjacent half-open intervals share a row; overlapping intervals occupy distinct rows.
- Clipping changes only drawing coordinates, never saved timestamps.
- Tick labels retain dates across midnight.
- Source, forecast, calculated and proposal records retain separate lanes.
- Empty source lanes explicitly do not imply complete source coverage or available capacity.
- Capacity/proposal artifacts are not inferred when missing.
- Fit/2×/4× zoom changes scale only. Track filtering and register selection are local view operations.

## Backend/API boundary and verification

No backend or migration file changed. A before/after static audit of 28 existing TypeScript files found **95 API/fetch calls, zero modified call sites**. Authentication, CSRF, request hashes and operational mutation bodies remain in their original code paths.

Automated presentation checks use an archived **SIMULATED** workspace already saved by backend tests. They exercise real component rendering, not generated replacements for backend results. They do not prove current HTTP integration or current approval eligibility.

Reproducible checks:

```text
cd E:\sih_codex_train\web
npm run typecheck
npm run lint
node scripts/check-presentation.cjs
npm run build
```

The production build compiled the frontend, then the host rejected Next's TypeScript child process with `spawn EPERM`. Separate TypeScript checking passes. The complete production build is not claimed as passing.

## Remaining acceptance gate

- [x] Obtain a reachable running preview: the user-started Next.js app and an isolated SIMULATED FastAPI/database fixture pass authenticated HTTP integration. Browser screenshot capture remains open because Chrome launch from this sandbox returns `spawn EPERM`.
- [ ] Sign in with a provisioned prototype role and inspect the current saved case.
- [ ] Review Planning, Corridor, Comparison, Validation and Controller Review at 1440px and 1920px.
- [ ] Check work search, department filter, evidence selection, overlapping intervals, layer toggles, zoom, linked comparison scroll and exact-time register with the mouse and keyboard.
- [ ] Inspect empty, blocked/stale, failed-validation, no-incumbent, API-error and permission-denied states with real or explicitly isolated fixture evidence.
- [ ] Review every supporting route, 390px responsive layout and 200% browser zoom. Check narrow navigation/account access and focus order.
- [ ] Confirm current API responses, role-based actions and browser console/network errors. Do not submit controller decisions merely for visual QA.
- [ ] Complete production build in an environment that permits the required Next child processes.

Do not mark the full frontend redesign, M18 or SIH demo as accepted until these gates have actual evidence. The archived fixture's PASS is historical; it is not evidence that a plan is currently approvable.
