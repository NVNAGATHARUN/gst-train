# M16 execution-aware snapshot / replacement solver slice

Recorded: 2026-09-17T15:52:05.351890+00:00

**131 cumulative tests passed** against PostgreSQL railsync_test on port 55432.
Command: `.venv/Scripts/python.exe scripts/check_m16_replanning.py`.
Detailed commands/results: M16-replanning-test-output.txt and M16-replanning.xml.
Tested file SHA256 hashes: M16-replanning-sources.json. No Git commit is claimed.

Backend example: M16-replanning-backend-example.json. It uses synthetic source data and real API, candidate, baseline, solver and validator code.
Verified expected output: two ongoing ENG/TRD tasks preserved exactly in their original shared block, a third urgent request scheduled in a separate feasible 15-minute block; 3 scheduled requests for both planners; zero frozen-commitment changes; real incumbent and independent PASS. The evidence script checks these saved values. Approval of this replacement is blocked pending the controlled replacement transaction.

Also verified: updated restriction/resource conflict excludes the frozen candidate and returns actual INFEASIBLE with no assignments; completed requests are excluded from pending demand but restoration remains unresolved; interruptions and missing duration stay blocked; new observations invalidate captures; immutable provenance; scope/role/hash/revision guards; corruption of freeze derivation, execution evidence, candidate identity or commitment coverage cannot pass validation. Time passing does not manufacture completion.

Limitations: unchanged observed STARTED work is supported; actual deviation, interrupted/resumed remaining work and completed possession restoration require explicit reconciliation. Source events do not automatically update operational facts. Capture uses a conservative scope-wide state version; other overlapping approved lineages require reconciliation. Replacement plan diff/lineage, atomic supersede approval and restoration/remaining-work handling still precede the full M16 gate. M16 remains unchecked and M17 must not start.
