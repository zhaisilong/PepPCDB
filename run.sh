#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

export PEPPCDB_DB="${PEPPCDB_DB:-$ROOT_DIR/data/peppcdb.sqlite3}"
export PEPPCDB_DATASET="${PEPPCDB_DATASET:-$ROOT_DIR/data/filtered_peppi}"
export PEPPCDB_TARGET_CARDS_JSONL="${PEPPCDB_TARGET_CARDS_JSONL:-$ROOT_DIR/data/records/target_cards.jsonl}"
export PEPPCDB_PEP_ANNOTATIONS_JSONL="${PEPPCDB_PEP_ANNOTATIONS_JSONL:-$ROOT_DIR/data/records/pep_annotations_patched.jsonl}"

python3 "$ROOT_DIR/scripts/release_check.py" --fast

echo "Starting PepPCDB v0.1.4 at http://${HOST}:${PORT}"
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir "$ROOT_DIR"
