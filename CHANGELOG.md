# Changelog

## v0.1.2 - 2026-05-27

### Changed

- Updated runtime/document version to `v0.1.2`.
- Refined the Home hero title and subtitle for the PepPCDB/NAR paper positioning.
- Compressed Home stats labels and card spacing to reduce wrapping in the first viewport.
- Split the search panel into a main search row and a secondary filter row.

## v0.1.1 - 2026-05-27

### Added

- Added affinity-aware browsing with a table Affinity column and an All / With Affinity / Without Affinity filter.
- Added `Affinity Annotations` to the Home stats summary.
- Added `GET /api/download/{entry_key}/function.json` for merged peptide function, affinity, and linked target-card annotations.
- Added lightweight rate limiting for public quick download API endpoints: 100 requests per client IP per hour.
- Added public quick download API documentation to the About page.

### Changed

- Updated runtime/document version to `v0.1.1`.
- Simplified the `pep nonstd` badge and non-standard filter labels to `nonstd` wording.
- Renamed the overview function section to `Function Annotation & Affinity`.
- Added target-card status and update time to function annotation display.
- Updated the GitHub header link to `https://github.com/zhaisilong/PepPCDB`.
- Scoped public API documentation to quick download endpoints only; browser search/detail APIs remain internal.

## v0.1.0 - 2026-05-27

### Added

- Initialized `peppcdb` as a standalone local deployment project.
- Started project version records at document version `v0.1.0`.
- Added git ignore rules so code and documentation are versioned while large synchronized data assets are excluded.
- Documented the planned deployment data sources and refresh workflow.
- Added a FastAPI single-port deployment app serving both API endpoints and static frontend files.
- Added release sync/check scripts for refreshing structure data, copied records, and release statistics.
- Migrated the existing static frontend into the deployment project and switched API calls to same-origin paths.

### Data Policy

- `filtered_peppi`, SQLite snapshots, SQLite WAL/SHM files, logs, caches, and temporary outputs are not tracked in git.
- `data/records` is not tracked in git; JSONL records are copied during release preparation.
- Deployment data should be copied or rebuilt during release preparation.
- The preferred pep annotation source for deployment is `function_mannual/affinity/pep_annotations_patched.jsonl`.

### Notes

- The affinity patched annotation file keeps the formal pep annotation row count stable at 13,886 rows.
- The current affinity patch adds `has_affinity=true` and normalized nM `affinity_text` to 1,944 pep annotation rows.
- Patch report issue counts to preserve for review: ambiguous 3, chain unmatched 10, conflicting values 8, entry missing 348, malformed value 1, sequence problem 2.
- Current deployment data check after sync: 2,797 cluster directories, 15,731 entry directories, 13,967 SQLite entries, 21,155 peptide chains, and 46,909 interface pairs.
