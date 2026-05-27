# PepPCDB Deployment Project

Document version: `v0.1.4`

This directory is the new local deployment project for PepPCDB. It contains a FastAPI backend, same-origin static frontend assets, release scripts, and documentation for the peptide-protein complex database portal.

## Versioning

Version history starts at `v0.1.0` in the documentation. The current document/runtime version is `v0.1.4`. This local repository does not use git tags unless that policy changes later.

## Git Policy

This repository tracks code, scripts, static frontend files, and documentation only. Large or generated data assets are intentionally excluded from git:

- `data/filtered_peppi/`
- `data/records/`
- SQLite database snapshots
- Usage statistics database (`data/usage_stats.sqlite3`)
- SQLite WAL/SHM files
- caches, logs, and temporary files

The deployable data should be synchronized or rebuilt as part of the release preparation workflow rather than committed.

## Run

Install dependencies in your preferred Python environment:

```bash
pip install -r requirements.txt
```

Start the deployment app:

```bash
./run.sh
```

Defaults:

- URL: `http://127.0.0.1:8000`
- Database: `data/peppcdb.sqlite3`
- Structure dataset: `data/filtered_peppi`
- Target cards: `data/records/target_cards.jsonl`
- Pep annotations: `data/records/pep_annotations_patched.jsonl`
- Usage stats: `data/usage_stats.sqlite3`

The app serves both the API and frontend from the same port.

## Data Sources

The current upstream source of truth remains outside this deployment project:

- Structure dataset: `/home/silong/codex/peptarget/4.peptide/filtered_peppi`
- Target cards: `/home/silong/codex/peptarget/function_mannual/records/target_cards.jsonl`
- Pep annotations with affinity patch: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.jsonl`
- Affinity patch report: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.report.json`

The patched pep annotation file should be treated as the preferred deployment annotation source because it preserves the formal pep annotation schema while adding `has_affinity` and normalized `affinity_text` where safe.

## Release Data Refresh

When the upstream structural dataset is updated, prepare this deployment project with the following workflow:

1. Synchronize the updated `filtered_peppi` dataset and JSONL records:

```bash
./scripts/sync_release_data.sh
```

2. Rebuild the deployment SQLite database from the synchronized dataset and patched annotations:

```bash
python3 scripts/build_db.py
```

3. Run release checks:

```bash
python3 scripts/release_check.py
```

4. Start the app and run page/API smoke checks before publishing:

```bash
./run.sh
```

5. Record the dataset and annotation refresh in `CHANGELOG.md`.

Use `rsync --delete` for structure data refreshes so the deployment copy exactly matches the current source dataset.

## Public Quick Download API

- `GET /api/download/{entry_key}.zip`
- `GET /api/download/{entry_key}/{filename}`
- `GET /api/download/{entry_key}/function.json`

The browser uses additional internal `/api/*` endpoints for search and entry rendering. The stable public API surface is limited to the quick download endpoints above. Public download API requests are limited to 100 requests per client IP per hour.

## Usage Statistics

PepPCDB records lightweight aggregate usage statistics in `data/usage_stats.sqlite3`. Home page visits and quick download API usage are counted as daily unique IP hashes, with one visit and one download counted per client IP per day. Raw IP addresses are not stored; set `PEPPCDB_USAGE_SALT` in deployment to control the hash salt. The About page displays aggregate visit/download totals from `GET /api/usage-stats`.
