#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "peppcdb.sqlite3"
DEFAULT_DATASET = ROOT / "data" / "filtered_peppi"
DEFAULT_TARGETS = ROOT / "data" / "records" / "target_cards.jsonl"
DEFAULT_PEPS = ROOT / "data" / "records" / "pep_annotations_patched.jsonl"
DEFAULT_REPORT = ROOT / "data" / "records" / "pep_annotations_patched.report.json"


def jsonl_stats(path: Path) -> dict[str, Any]:
    rows = 0
    affinity_rows = 0
    errors: list[str] = []
    if not path.exists():
        return {"exists": False, "rows": 0, "affinity_rows": 0, "errors": [f"missing: {path}"]}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"{line_no}: {exc}")
            continue
        rows += 1
        if obj.get("has_affinity") is True and str(obj.get("affinity_text", "")).strip():
            affinity_rows += 1
    return {"exists": True, "rows": rows, "affinity_rows": affinity_rows, "errors": errors[:20]}


def db_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "error": f"missing: {path}"}
    conn = sqlite3.connect(path)
    try:
        return {
            "exists": True,
            "entries": conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0],
            "peptide_chains": conn.execute("SELECT COUNT(*) FROM peptide_chains").fetchone()[0],
            "interface_pairs": conn.execute("SELECT COUNT(*) FROM interface_pairs").fetchone()[0],
            "clusters": conn.execute("SELECT COUNT(DISTINCT cluster_id) FROM entry_clusters").fetchone()[0],
        }
    finally:
        conn.close()


def dataset_stats(path: Path, fast: bool) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "entry_dirs": 0, "error": f"missing: {path}"}
    if fast:
        return {"exists": True, "entry_dirs": None, "mode": "fast"}
    count = 0
    for cluster_dir in path.iterdir():
        if not cluster_dir.is_dir():
            continue
        count += sum(1 for entry_dir in cluster_dir.iterdir() if entry_dir.is_dir())
    return {"exists": True, "entry_dirs": count, "mode": "full"}


def main() -> None:
    parser = argparse.ArgumentParser(description="PepPCDB deployment release checks")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("PEPPCDB_DB", DEFAULT_DB)))
    parser.add_argument("--dataset", type=Path, default=Path(os.environ.get("PEPPCDB_DATASET", DEFAULT_DATASET)))
    parser.add_argument("--target-cards", type=Path, default=Path(os.environ.get("PEPPCDB_TARGET_CARDS_JSONL", DEFAULT_TARGETS)))
    parser.add_argument("--pep-annotations", type=Path, default=Path(os.environ.get("PEPPCDB_PEP_ANNOTATIONS_JSONL", DEFAULT_PEPS)))
    parser.add_argument("--patch-report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fast", action="store_true", help="Skip full dataset directory counting")
    args = parser.parse_args()

    payload = {
        "dataset": dataset_stats(args.dataset, args.fast),
        "database": db_stats(args.db),
        "target_cards": jsonl_stats(args.target_cards),
        "pep_annotations": jsonl_stats(args.pep_annotations),
        "patch_report_exists": args.patch_report.exists(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    errors = []
    if not payload["dataset"]["exists"]:
        errors.append("dataset missing")
    if not payload["database"]["exists"]:
        errors.append("database missing")
    if not payload["target_cards"]["exists"]:
        errors.append("target cards missing")
    if not payload["pep_annotations"]["exists"]:
        errors.append("pep annotations missing")
    if payload["pep_annotations"].get("errors"):
        errors.append("pep annotations have JSONL errors")
    if errors:
        raise SystemExit("; ".join(errors))


if __name__ == "__main__":
    main()

