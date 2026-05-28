# PepPCDB Deployment Project

PepPCDB is a local deployment project for browsing and downloading a curated PDB-derived atlas of peptide-protein complexes. The portal links peptide chains, target proteins, interface records, functional annotations, and affinity values through a FastAPI backend and same-origin static frontend.

## Quick Start

Start the app from this directory:

```bash
./run.sh
```

`run.sh` creates a repo-local `.venv` on first run, installs `requirements.txt`, runs a fast release check, and starts the FastAPI app at `http://127.0.0.1:13008`. Later runs reuse `.venv`; dependencies are reinstalled only when `requirements.txt` changes.

Useful runtime overrides:

```bash
HOST=0.0.0.0 PORT=13008 ./run.sh
PYTHON=/path/to/python3 ./run.sh
PEPPCDB_VENV=/path/to/venv ./run.sh
```

To rebuild the Python environment, remove `.venv` and rerun `./run.sh`.

## Data Assets

This repository tracks code, scripts, static frontend files, and documentation only. Large generated or synchronized assets are intentionally excluded from git:

- `data/filtered_peppi/`
- `data/records/`
- `data/peppcdb.sqlite3`
- `data/usage_stats.sqlite3`
- `data/usage_salt`
- SQLite WAL/SHM files, caches, logs, and temporary files

Default runtime paths:

| Asset             | Default Path                                 | Override                                          |
| ----------------- | -------------------------------------------- | ------------------------------------------------- |
| SQLite index      | `data/peppcdb.sqlite3`                       | `PEPPCDB_DB`                                      |
| Structure dataset | `data/filtered_peppi`                        | `PEPPCDB_DATASET`                                 |
| Target cards      | `data/records/target_cards.jsonl`            | `PEPPCDB_TARGET_CARDS_JSONL`                      |
| Pep annotations   | `data/records/pep_annotations_patched.jsonl` | `PEPPCDB_PEP_ANNOTATIONS_JSONL`                   |
| Usage stats       | `data/usage_stats.sqlite3`                   | `PEPPCDB_USAGE_DB`                                |
| Usage salt        | `data/usage_salt`                            | `PEPPCDB_USAGE_SALT` or `PEPPCDB_USAGE_SALT_FILE` |

Current upstream sources:

- Structure dataset: `/home/silong/codex/peptarget/4.peptide/filtered_peppi_v2`
- Target cards: `/home/silong/codex/peptarget/function_mannual/records/target_cards.jsonl`
- Pep annotations with affinity patch: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.jsonl`
- Affinity patch report: `/home/silong/codex/peptarget/function_mannual/affinity/pep_annotations_patched.report.json`

The patched pep annotation JSONL is the preferred deployment source because it keeps the formal pep annotation schema while adding `has_affinity` and normalized `affinity_text` where safe.

## Release Data Refresh

When the upstream dataset or annotation records change, refresh the deployment copy:

```bash
./scripts/sync_release_data.sh
.venv/bin/python scripts/build_db.py
.venv/bin/python scripts/release_check.py
./run.sh
```

`sync_release_data.sh` uses `rsync --delete` for `filtered_peppi`, so the deployment copy exactly matches the upstream structure dataset. After refresh, record the dataset or annotation change in `CHANGELOG.md`.

## Public Quick Download API

The stable public API surface is limited to quick download endpoints. Browser search/detail APIs are used by the frontend and should be treated as internal. The hosted site uses the `/peppcdb` prefix; a root-path deployment uses the same paths without that prefix.

| Endpoint                                                          | Output                                                   |
| ----------------------------------------------------------------- | -------------------------------------------------------- |
| `GET /peppcdb/api/download/{entry_key}.zip`                       | Entry ZIP with source files plus generated function JSON |
| `GET /peppcdb/api/download/{entry_key}/{pdb_id}.cif`              | mmCIF coordinate file                                    |
| `GET /peppcdb/api/download/{entry_key}/{pdb_id}_annotations.json` | Peptide chain annotations                                |
| `GET /peppcdb/api/download/{entry_key}/{pdb_id}_interface.jsonl`  | Pair-level interface records                             |
| `GET /peppcdb/api/download/{entry_key}/{pdb_id}_function.json`    | Generated function, affinity, and target-card JSON       |
| `GET /peppcdb/api/download/{entry_key}/function.json`             | Compatibility alias for generated function JSON          |

Public download API requests are limited to 100 requests per client IP per hour by default. Override with `PEPPCDB_DOWNLOAD_RATE_LIMIT` when needed.

## Usage Statistics

PepPCDB records lightweight aggregate usage statistics in `data/usage_stats.sqlite3`. Home page visits and quick download API usage are counted as daily unique IP hashes, with one visit and one download counted per client IP per day.

Raw IP addresses are not stored. If `PEPPCDB_USAGE_SALT` is not set, `run.sh` creates a private local salt at `data/usage_salt` and exports it before starting the app. Keep this file stable across restarts to preserve daily unique counting continuity, and do not commit it. The About page displays aggregate visit/download totals from:

```text
GET /peppcdb/api/usage-stats
```

## Versioning

Version history starts at `v0.1.0`. The current document/runtime version is `v0.1.5`. This repository does not use git tags unless that release policy changes later.
