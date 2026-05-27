#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
BOOTSTRAP_PYTHON="${PYTHON:-python3}"
VENV_DIR="${PEPPCDB_VENV:-$ROOT_DIR/.venv}"
VENV_PYTHON="$VENV_DIR/bin/python"
REQUIREMENTS_FILE="$ROOT_DIR/requirements.txt"
REQUIREMENTS_STAMP="$VENV_DIR/.requirements.sha256"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Creating Python virtual environment at $VENV_DIR"
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

REQUIREMENTS_HASH="$("$VENV_PYTHON" - "$REQUIREMENTS_FILE" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"

INSTALLED_HASH=""
if [[ -f "$REQUIREMENTS_STAMP" ]]; then
  INSTALLED_HASH="$(cat "$REQUIREMENTS_STAMP")"
fi

if [[ "$INSTALLED_HASH" != "$REQUIREMENTS_HASH" ]]; then
  echo "Installing Python dependencies from requirements.txt"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
  printf "%s\n" "$REQUIREMENTS_HASH" > "$REQUIREMENTS_STAMP"
fi

export PEPPCDB_DB="${PEPPCDB_DB:-$ROOT_DIR/data/peppcdb.sqlite3}"
export PEPPCDB_DATASET="${PEPPCDB_DATASET:-$ROOT_DIR/data/filtered_peppi}"
export PEPPCDB_TARGET_CARDS_JSONL="${PEPPCDB_TARGET_CARDS_JSONL:-$ROOT_DIR/data/records/target_cards.jsonl}"
export PEPPCDB_PEP_ANNOTATIONS_JSONL="${PEPPCDB_PEP_ANNOTATIONS_JSONL:-$ROOT_DIR/data/records/pep_annotations_patched.jsonl}"

"$VENV_PYTHON" "$ROOT_DIR/scripts/release_check.py" --fast

echo "Starting PepPCDB v0.1.4 at http://${HOST}:${PORT}"
exec "$VENV_PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir "$ROOT_DIR"
