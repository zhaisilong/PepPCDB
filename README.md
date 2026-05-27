# PepPCDB Deployment Project

Document version: `v0.1.0`

This directory is the new local deployment project for PepPCDB. It is intended to contain the deployable application code, static frontend assets, release scripts, and documentation for the peptide-protein complex database portal.

## Versioning

Version history starts at `v0.1.0` in the documentation. This local repository does not use git tags for the initial version unless that policy changes later.

## Git Policy

This repository tracks code, scripts, and documentation only. Large or generated data assets are intentionally excluded from git:

- `data/filtered_peppi/`
- SQLite database snapshots
- SQLite WAL/SHM files
- caches, logs, and temporary files

The deployable data should be synchronized or rebuilt as part of the release preparation workflow rather than committed.

## Data Sources

The current deployment source of truth remains outside this new project until the migration is implemented:

- Structure dataset: `/home/silong/codex/peptarget/4.peptide/filtered_peppi`
- Target cards: `/home/silong/codex/peptarget/function_mannual/records/target_cards.jsonl`
- Pep annotations with affinity patch: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.jsonl`
- Affinity patch report: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.report.json`

The patched pep annotation file should be treated as the preferred deployment annotation source because it preserves the formal pep annotation schema while adding `has_affinity` and normalized `affinity_text` where safe.

## Release Data Refresh

When the upstream structural dataset is updated, prepare this deployment project with the following workflow:

1. Synchronize the updated `filtered_peppi` dataset into `data/filtered_peppi/`.
2. Copy the latest target card JSONL into `data/records/target_cards.jsonl`.
3. Copy `pep_annotations_patched.jsonl` into `data/records/pep_annotations_patched.jsonl`.
4. Copy `pep_annotations_patched.report.json` into `data/records/pep_annotations_patched.report.json`.
5. Rebuild the deployment SQLite database from the synchronized dataset and patched annotations.
6. Run API and page smoke checks before publishing.
7. Record the dataset and annotation refresh in `CHANGELOG.md`.

Use `rsync --delete` for structure data refreshes so the deployment copy exactly matches the current source dataset.
