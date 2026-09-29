# M18 R-MAPS contract and integrity update

**Date:** 29 September 2026

**Scope:** product-name consistency, final SRS/build contract, browser-security correction and removal of illustrative frontend claims.

## Changes

- Established R-MAPS — Railway Maintenance Allocation & Planning System — as the current product name in the application metadata, active documentation and final contract.
- Added `docs/R-MAPS_FINAL_SRS_BUILD_CONTRACT.md` and matching DOCX/PDF editions. The contract distinguishes completed M1–M17 gates, substantially implemented M18 scope, open acceptance gates and optional M19.
- Restored exact configured-Origin enforcement. Missing, suffix-matching, unconfigured local and cross-site origins are rejected; cookie-authenticated writes still require CSRF.
- Replaced hard-coded comparison gains, train impacts, corridor values, chainage, validation claims and fallback block data in the Planning workspace with values derived from the selected saved plan, snapshot, availability and validation artifacts.
- Removed a hard-coded notice count and fixed corridor/date from the global shell. The header now shows only the selected snapshot identity.

## Verification

| Check | Result |
| --- | --- |
| Complete PostgreSQL backend suite | 215 passed, 2 upstream deprecation warnings |
| Focused M18 session and system tests after origin correction | 24 passed |
| Frontend TypeScript | Passed |
| Frontend ESLint | Passed with two existing `snapshot-preparation.tsx` hook warnings and no errors |
| Contract PDF render | 22 pages rendered and visually inspected; no clipping, overlap or broken tables found |
| DOCX structure | Generated from the same canonical Markdown source; title, headings, tables, diagrams, headers, footers and page-number fields validated through OOXML inspection |

## Remaining limits

- The managed host has no LibreOffice installation, and Word COM conversion did not complete. The required DOCX renderer could not produce PNGs; the matching PDF edition was rendered and inspected page by page instead.
- M18 remains open for the integrated current-date judge walkthrough, fresh API failure/recovery, native 200% zoom/supporting-screen acceptance, a normal-host production Next.js build and live Docker/HTTPS/backup/restore verification.
- Internal API/database field names containing `railsync` are retained for compatibility. User-visible product labels and exports use R-MAPS.
