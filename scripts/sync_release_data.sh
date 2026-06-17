#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${SOURCE_ROOT:-/home/silong/codex/peptarget}"

SOURCE_DATASET="${SOURCE_DATASET:-$SOURCE_ROOT/4.peptide/filtered_peppi_v4}"
SOURCE_TARGET_CARDS="${SOURCE_TARGET_CARDS:-$SOURCE_ROOT/function_mannual/records/target_cards.jsonl}"
SOURCE_PEP_ANNOTATIONS="${SOURCE_PEP_ANNOTATIONS:-$SOURCE_ROOT/function_mannual/affinity/pep_annotations_patched.jsonl}"
SOURCE_PATCH_REPORT="${SOURCE_PATCH_REPORT:-$SOURCE_ROOT/function_mannual/affinity/pep_annotations_patched.report.json}"

DEST_DATASET="${DEST_DATASET:-$ROOT_DIR/data/filtered_peppi}"
DEST_RECORDS="$ROOT_DIR/data/records"

mkdir -p "$DEST_DATASET" "$DEST_RECORDS"

echo "[1/4] Syncing filtered_peppi"
rsync -a --delete --info=stats2,progress2 "$SOURCE_DATASET"/ "$DEST_DATASET"/

echo "[2/4] Copying target cards"
cp "$SOURCE_TARGET_CARDS" "$DEST_RECORDS/target_cards.jsonl"

echo "[3/4] Copying patched pep annotations"
cp "$SOURCE_PEP_ANNOTATIONS" "$DEST_RECORDS/pep_annotations_patched.jsonl"

echo "[4/4] Copying affinity patch report"
cp "$SOURCE_PATCH_REPORT" "$DEST_RECORDS/pep_annotations_patched.report.json"

echo "Data sync complete."
