# Changelog

## v0.8.1 - 2026-06-17

### Fixed

- Cleaned Browse detail citation display by removing PDB-derived wrapping semicolons, quotes, newlines, and zero-width artifacts while preserving meaningful internal punctuation.
- Cleaned Nonpoly entity name display with the same boundary-only normalization and improved long-name wrapping in the annotations table.

## v0.8.0 - 2026-06-17

### Changed

- Updated runtime/document version to `v0.8.0`.
- Refreshed the default deployment structure source to the 2026-06-17 PDB-derived `filtered_peppi_v4` snapshot.
- Updated the default PDB source snapshot date shown by the API and frontend to `2026-06-17`.
- Documented that structural data refreshes may be released before manual function and affinity annotations are complete for every newly added entry.

### Data

- Current deployment check: 16,642 synchronized entry directories, 14,746 SQLite entries, 22,339 peptide chains, 50,698 interface pairs, 28,207 peptide-protein (`PepPI`) interfaces, 2,935 clusters, 7,695 target cards, 14,305 peptide annotations, and 2,052 affinity annotation rows.
- Manual function and affinity annotations remain curated records; newly added structural entries can be present in search/download/AF3 workflows before annotation coverage catches up.

## v0.7.3 - 2026-06-09

### Changed

- Updated runtime/document version to `v0.7.3`.
- Reworked AF3 bond generation to use each entry's `<pdb_id>.json` `connect` records as the authoritative bond source.
- Added automatic CCD ligand/glycan entities for selected covalent bonds, including peptide linker bonds and optional protein/glycan bonds.
- Kept ordinary sequential peptide backbone `C-N` bonds filtered out while preserving non-sequential cyclic/linker bonds.

## v0.7.2 - 2026-06-09

### Changed

- Updated runtime/document version to `v0.7.2`.
- Updated AF3 input generation so ordinary sequential peptide backbone `C-N` bonds are not emitted as explicit `bondedAtomPairs`.
- Kept non-sequential peptide bonds, cyclic links, cross-links, and cross-chain peptide-related bonds available for AF3 input generation.
- Refined the About roadmap wording for the companion `afrun` local AFRun/MSA workflow.

## v0.7.1 - 2026-06-09

### Changed

- Updated runtime/document version to `v0.7.1`.
- Clarified that PepPCDB AF3 input generation is derived from the companion `afrun` project: https://github.com/zhaisilong/afrun.
- Updated README and About roadmap notes to mark AF3 config generation as available.
- Added a future-work note that direct prediction from precomputed MSA-enriched JSON remains under internal testing because MSA files can be large.

## v0.7.0 - 2026-06-09

### Added

- Added an `AF3 Input` detail tab for generating AlphaFold 3 JSON inputs from PepPCDB entry annotations.
- Added internal AF3 option/config endpoints for the Browse UI.
- Added `scripts/annotation_to_af3_input.py` for command-line AF3 input generation from local deployment data.
- Added the AlphaFold 3 input format note under `static/docs/input.md`.

### Changed

- Updated runtime/document version to `v0.7.0`.
- Documented AF3 input generation in the README.

## v0.6.3 - 2026-06-09

### Added

- Added Home hero CTA links for About and the GitHub repository.
- Added a live GitHub stars count beside the Home GitHub action.
- Added the PepPCDB banner image to the Home page before the feature overview.

### Changed

- Updated runtime/document version to `v0.6.3`.
- Refined Home banner sizing so the image fills the banner frame without cropping.
- Updated the About page development log with the latest Home navigation and local 3D display work.

### Fixed

- Increased the top navigation stacking layer and click target area so the upper-right links remain clickable.

## v0.6.2 - 2026-06-09

### Added

- Added a dedicated Browse page for search, filtering, entry details, interface views, downloads, and local 3D structure inspection.
- Added a dedicated Status page for dataset counts, annotation coverage, release metadata, and usage statistics.
- Added local Mol* viewer assets and interactive mmCIF rendering from PepPCDB-hosted structure files.

### Changed

- Updated runtime/document version to `v0.6.2`.
- Reworked the Home page into a database overview with feature descriptions and dataset snapshot cards instead of loading the full entry browser directly.
- Moved the feature overview from About to Home, kept About focused on legend rules, feedback, download API notes, roadmap, and development log.
- Moved Community Feedback after Legend Details and removed duplicate Usage Statistics from About.
- Extended internal `/api/stats` with target-card, peptide-annotation, and affinity-entry counts for Status/Home displays.

## v0.2.0 - 2026-06-01

### Changed

- Released the rebuilt deployment data after target-card review and peptide annotation updates.
- Updated runtime/document version to `v0.2.0`.
- Updated deployment documentation and About page wording to refer to the current `filtered_peppi` release instead of stale `filtered_peppi_v2` text.

### Data

- Current deployment check: 14,385 entries, 21,798 peptide chains, 48,916 interface pairs, 27,419 peptide-protein (`PepPI`) interfaces, 2,888 clusters, 7,628 target cards, 14,305 peptide annotations, and 2,052 affinity annotations.
- Confirmed repaired non-standard/cyclic peptide interface entries such as 7YV1 are searchable and expose function JSON downloads.

## v0.1.7 - 2026-05-29

### Fixed

- Refreshed the deployment data source to the `filtered_peppi_v3` release so peptide-protein interfaces recovered by the non-standard/cyclic peptide contact fix, including entries such as 7YV1, are available in the website search and API.

### Changed

- Updated runtime/document version to `v0.1.7`.
- Kept community feedback and copyright notes readable on the About page with explicit line breaks.

## v0.1.6 - 2026-05-29

### Added

- Added README and About page community feedback links for GitHub issues and direct email contact.

### Changed

- Updated runtime/document version to `v0.1.6`.

## v0.1.5 - 2026-05-28

### Changed

- Updated runtime/document version to `v0.1.5`.
- Added support for `cyclic.has_cyc_linker` in cyclic classification and cyclic type display.
- Added Details display for `modification.has_linker` and cyclic linker metadata.
- Updated the Home title to `PepPCDB: A PDB-wide Database of Peptide-Protein Complexes with Structural and Functional Annotations`.
- Updated the default release data source to `filtered_peppi_v2`.

## v0.1.4 - 2026-05-27

### Added

- Added daily unique Home visit and quick download statistics by hashed client IP.
- Added `GET /api/usage-stats` for aggregate usage counters.
- Added bottom-of-page About display for visit/download usage statistics.
- Added ignored persistent usage storage at `data/usage_stats.sqlite3`.

### Changed

- Updated runtime/document version to `v0.1.4`.
- Cleaned up function JSON download handling so rate limiting and usage counting happen once per successful request.
- Updated `run.sh` to create and reuse a local `.venv`, reinstalling dependencies only when `requirements.txt` changes.
- Updated `run.sh` to generate and reuse a private local usage salt when `PEPPCDB_USAGE_SALT` is not provided.
- Updated frontend API URL handling so deployments under a path prefix such as `/peppcdb/` can load data correctly.
- Updated default local port and documentation examples to `13008`.
- Updated API documentation to show hosted `/peppcdb/api/...` URLs while keeping FastAPI internal routes at `/api/...`.

## v0.1.3 - 2026-05-27

### Added

- Added generated function JSON to entry ZIP downloads.
- Added public download aliases using PDB-prefixed names for annotation, interface, and function files.
- Added a 2026-05-27 deployment update to the About page development log.

### Changed

- Updated runtime/document version to `v0.1.3`.
- Improved About page feature descriptions and moved Quick Download API after Legend Details.
- Reordered Roadmap / TODO before Development Log.
- Formatted displayed affinity values with thousands separators while preserving raw downloaded JSON values.
- Aligned Home hero and search panel widths and refined the search/filter row layout.

## v0.1.2 - 2026-05-27

### Changed

- Updated runtime/document version to `v0.1.2`.
- Refined the Home hero title and subtitle for the PepPCDB/NAR paper positioning.
- Changed the Home hero to a centered, narrower panel instead of a full-width block.
- Compressed Home stats card boxes and reordered them as Entries, Peptides, Clusters, Interfaces, Cyclic, Affinity.
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
