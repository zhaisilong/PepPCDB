#!/usr/bin/env python3
"""Build SQLite database for PepPCDB from filtered_peppi dataset."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def to_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_optional_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    raw = str(value).strip().lower()
    if raw in {"", "none", "null", "-"}:
        return None
    if raw in {"true", "1", "yes", "y"}:
        return 1
    if raw in {"false", "0", "no", "n"}:
        return 0
    return None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical_entry_key(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "__" in raw:
        raw = raw.rsplit("__", 1)[-1].strip()
    return raw


def _load_jsonl_objects(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    out: list[dict[str, Any]] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(obj, dict):
            skipped += 1
            continue
        out.append(obj)
    return out, skipped


def load_target_card_records(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    rows, skipped = _load_jsonl_objects(path)
    best: dict[str, dict[str, Any]] = {}
    for obj in rows:
        target_id = str(obj.get("target_id", "")).strip()
        entry_key = canonical_entry_key(obj.get("entry_key", ""))
        if not target_id:
            skipped += 1
            continue
        status = str(obj.get("status", "draft")).strip().lower()
        updated_at = str(obj.get("updated_at", "")).strip()
        key = f"{entry_key}::{target_id}"
        prev = best.get(key)
        if prev and str(prev.get("updated_at", "")) > updated_at:
            continue
        best[key] = {
            "target_id": target_id,
            "entry_key": entry_key,
            "target_name": str(obj.get("target_name", "")).strip(),
            "mechanism_text": str(obj.get("mechanism_text", "")).strip(),
            "opentarget_url": str(obj.get("opentarget_url", "")).strip(),
            "notes": str(obj.get("notes", "")).strip(),
            "status": status if status in {"draft", "published"} else "draft",
            "annotator": str(obj.get("annotator", "")).strip(),
            "updated_at": updated_at,
        }
    return best, skipped


def load_pair_annotation_records(path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    rows, skipped = _load_jsonl_objects(path)
    best: dict[str, dict[str, Any]] = {}
    for obj in rows:
        entry_key = canonical_entry_key(obj.get("entry_key", ""))
        pair_id = str(obj.get("pair_id", "")).strip()
        if not entry_key or not pair_id:
            skipped += 1
            continue
        status = str(obj.get("status", "draft")).strip().lower()
        updated_at = str(obj.get("updated_at", "")).strip()
        key = f"{entry_key}::{pair_id}"
        prev = best.get(key)
        if prev and str(prev.get("updated_at", "")) > updated_at:
            continue
        evidence = obj.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        aff_history = obj.get("affinity_history", [])
        if not isinstance(aff_history, list):
            aff_history = []
        aff_current = obj.get("affinity_current")
        current_index = obj.get("affinity_current_index")
        try:
            current_index_i = int(current_index) if current_index is not None else -1
        except (TypeError, ValueError):
            current_index_i = -1
        best[key] = {
            "entry_key": entry_key,
            "cluster_id": str(obj.get("cluster_id", "")).strip(),
            "pair_id": pair_id,
            "interface_kind": str(obj.get("interface_kind", "")).strip(),
            "function_text": str(obj.get("function_text", "")).strip(),
            "affinity_text": str(obj.get("affinity_text", "")).strip(),
            "target_tags_json": json.dumps([str(x).strip() for x in obj.get("target_tags", []) if str(x).strip()], ensure_ascii=True),
            "evidence_json": json.dumps([str(x).strip() for x in evidence if str(x).strip()], ensure_ascii=True),
            "confidence": str(obj.get("confidence", "")).strip().lower(),
            "notes": str(obj.get("notes", "")).strip(),
            "status": status if status in {"draft", "published"} else "draft",
            "annotator": str(obj.get("annotator", "")).strip(),
            "has_affinity": to_optional_bool_int(obj.get("has_affinity")),
            "affinity_history_json": json.dumps(aff_history, ensure_ascii=True),
            "affinity_current_json": json.dumps(aff_current, ensure_ascii=True) if aff_current is not None else None,
            "affinity_current_index": current_index_i,
            "updated_at": updated_at,
        }
    return best, skipped


def iter_entry_dirs(dataset_root: Path) -> Iterable[tuple[str, str, Path]]:
    for hash_dir in sorted(dataset_root.iterdir()):
        if not hash_dir.is_dir():
            continue
        for pdb_dir in sorted(hash_dir.iterdir()):
            if pdb_dir.is_dir():
                yield hash_dir.name, pdb_dir.name.lower(), pdb_dir


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        DROP TABLE IF EXISTS entry_files;
        DROP TABLE IF EXISTS entry_clusters;
        DROP TABLE IF EXISTS db_meta;
        DROP TABLE IF EXISTS interface_details;
        DROP TABLE IF EXISTS interface_pairs;
        DROP TABLE IF EXISTS entry_connect;
        DROP TABLE IF EXISTS entry_nonpoly;
        DROP TABLE IF EXISTS peptide_chains;
        DROP TABLE IF EXISTS pair_annotations;
        DROP TABLE IF EXISTS target_cards;
        DROP TABLE IF EXISTS entry_functions;
        DROP TABLE IF EXISTS citations;
        DROP TABLE IF EXISTS entries;

        CREATE TABLE entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_key TEXT NOT NULL UNIQUE,
            pdb_id TEXT NOT NULL UNIQUE,
            source_hash TEXT NOT NULL,
            entry_id TEXT,
            exptl_method TEXT,
            deposition_date TEXT,
            d_res_high REAL,
            d_res_low REAL,
            r_work REAL,
            r_free REAL,
            chain_count INTEGER DEFAULT 0,
            peptide_chain_count INTEGER DEFAULT 0,
            has_nonstd INTEGER DEFAULT 0,
            nonstd_chain_count INTEGER DEFAULT 0,
            nonstd_mod_count INTEGER DEFAULT 0,
            is_cyclic INTEGER DEFAULT 0,
            cyclic_chain_count INTEGER DEFAULT 0,
            cyclic_types_json TEXT DEFAULT '[]',
            interface_pair_count INTEGER DEFAULT 0
        );

        CREATE TABLE citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            citation_key TEXT,
            title TEXT,
            journal TEXT,
            year TEXT,
            doi TEXT,
            pubmed TEXT,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE peptide_chains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            chain_id TEXT NOT NULL,
            chain_type TEXT,
            length INTEGER,
            sequence TEXT,
            has_nonstd INTEGER DEFAULT 0,
            mod_positions_json TEXT,
            mod_types_json TEXT,
            cyclic_head2tail INTEGER,
            cyclic_head2side INTEGER,
            cyclic_side2tail INTEGER,
            cyclic_side2side INTEGER,
            n_ss INTEGER,
            n_nc INTEGER,
            n_cyclic INTEGER,
            n_cyclic_nonstd INTEGER,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE entry_nonpoly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            entity_id TEXT,
            comp_id TEXT,
            name TEXT,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE entry_connect (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            connect_id TEXT,
            connect_type TEXT,
            leaving_atom TEXT,
            ptnr1_chain TEXT,
            ptnr1_comp TEXT,
            ptnr1_seq INTEGER,
            ptnr1_atom TEXT,
            ptnr2_chain TEXT,
            ptnr2_comp TEXT,
            ptnr2_seq INTEGER,
            ptnr2_atom TEXT,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE interface_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            pair_id TEXT,
            chain1_id TEXT,
            chain2_id TEXT,
            interface_kind TEXT,
            chain1_len INTEGER,
            chain2_len INTEGER,
            interface_residues1 INTEGER,
            interface_residues2 INTEGER,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE interface_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            pair_id TEXT NOT NULL,
            chain1_id TEXT,
            chain2_id TEXT,
            chain1_sequence TEXT,
            chain2_sequence TEXT,
            interface_mask1_sequence TEXT,
            interface_mask2_sequence TEXT,
            ss1 TEXT,
            ss2 TEXT,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE entry_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE entry_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            cluster_id TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE,
            UNIQUE(entry_id, cluster_id)
        );

        CREATE TABLE db_meta (
            meta_key TEXT PRIMARY KEY,
            meta_value TEXT
        );

        CREATE TABLE target_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_key TEXT NOT NULL,
            target_id TEXT NOT NULL,
            target_name TEXT,
            mechanism_text TEXT,
            opentarget_url TEXT,
            notes TEXT,
            status TEXT NOT NULL,
            annotator TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(entry_key, target_id)
        );

        CREATE TABLE pair_annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            entry_key TEXT NOT NULL,
            cluster_id TEXT,
            pair_id TEXT NOT NULL,
            interface_kind TEXT,
            function_text TEXT,
            affinity_text TEXT,
            target_tags_json TEXT DEFAULT '[]',
            evidence_json TEXT DEFAULT '[]',
            confidence TEXT,
            notes TEXT,
            status TEXT NOT NULL,
            annotator TEXT,
            has_affinity INTEGER,
            affinity_history_json TEXT DEFAULT '[]',
            affinity_current_json TEXT,
            affinity_current_index INTEGER DEFAULT -1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE TABLE entry_functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            entry_key TEXT NOT NULL,
            cluster_id TEXT NOT NULL,
            function_text TEXT NOT NULL,
            evidence_json TEXT DEFAULT '[]',
            confidence TEXT,
            annotator TEXT,
            source TEXT,
            notes TEXT,
            ligand_chain_id TEXT,
            bioactivity_value TEXT,
            bioactivity_unit TEXT,
            bioactivity_method TEXT,
            affinity_citation TEXT,
            has_affinity INTEGER,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );

        CREATE INDEX idx_entries_key ON entries(entry_key);
        CREATE INDEX idx_entries_pdb_id ON entries(pdb_id);
        CREATE INDEX idx_entries_source_hash ON entries(source_hash);
        CREATE INDEX idx_entries_method ON entries(exptl_method);
        CREATE INDEX idx_entries_date ON entries(deposition_date);
        CREATE INDEX idx_chains_entry_chain ON peptide_chains(entry_id, chain_id);
        CREATE INDEX idx_chains_sequence ON peptide_chains(sequence);
        CREATE INDEX idx_nonpoly_entry ON entry_nonpoly(entry_id);
        CREATE INDEX idx_connect_entry ON entry_connect(entry_id);
        CREATE INDEX idx_target_cards_target_id ON target_cards(target_id);
        CREATE INDEX idx_pair_annotations_entry_key ON pair_annotations(entry_key);
        CREATE INDEX idx_pair_annotations_entry ON pair_annotations(entry_id);
        CREATE INDEX idx_pair_annotations_pair ON pair_annotations(pair_id);
        CREATE INDEX idx_functions_entry ON entry_functions(entry_id);
        CREATE INDEX idx_functions_key ON entry_functions(entry_key);
        CREATE INDEX idx_pairs_entry ON interface_pairs(entry_id);
        CREATE INDEX idx_pairs_kind ON interface_pairs(interface_kind);
        CREATE INDEX idx_iface_details_entry_pair ON interface_details(entry_id, pair_id);
        CREATE INDEX idx_files_entry ON entry_files(entry_id);
        CREATE INDEX idx_entry_clusters_cluster ON entry_clusters(cluster_id);
        CREATE INDEX idx_entry_clusters_entry ON entry_clusters(entry_id);
        """
    )


def build_database(dataset_root: Path, db_path: Path, target_cards_jsonl: Path, pair_annotations_jsonl: Path) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    create_schema(conn)

    entry_count = 0
    chain_count = 0
    nonpoly_count = 0
    connect_count = 0
    pair_count = 0
    iface_detail_count = 0
    file_count = 0
    latest_file_mtime = 0.0

    entry_id_by_pdb: dict[str, int] = {}
    for source_hash, pdb_id, entry_dir in iter_entry_dirs(dataset_root):
        meta_path = entry_dir / f"{pdb_id}.json"
        ann_path = entry_dir / "annotations.json"
        iface_path = entry_dir / "interface.jsonl"

        existing_entry_id = entry_id_by_pdb.get(pdb_id)
        if existing_entry_id is not None:
            conn.execute(
                "INSERT OR IGNORE INTO entry_clusters (entry_id, cluster_id) VALUES (?, ?)",
                (existing_entry_id, source_hash),
            )
            for file_path in sorted(entry_dir.iterdir()):
                if not file_path.is_file():
                    continue
                stat = file_path.stat()
                if stat.st_mtime > latest_file_mtime:
                    latest_file_mtime = stat.st_mtime
            continue

        if not meta_path.exists() or not ann_path.exists():
            continue

        meta = load_json(meta_path)
        annotations = load_json(ann_path)

        polymer = meta.get("polymer", [])
        chain_total = len(polymer)
        entry_key = pdb_id

        cur = conn.execute(
            """
            INSERT INTO entries (
                entry_key, pdb_id, source_hash, entry_id, exptl_method, deposition_date,
                d_res_high, d_res_low, r_work, r_free,
                chain_count, has_nonstd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                entry_key,
                pdb_id,
                source_hash,
                meta.get("entry_id"),
                meta.get("exptl_method"),
                meta.get("deposition_date"),
                to_float(meta.get("d_res_high")),
                to_float(meta.get("d_res_low")),
                to_float(meta.get("R_work")),
                to_float(meta.get("R_free")),
                chain_total,
            ),
        )
        entry_id = cur.lastrowid
        entry_id_by_pdb[pdb_id] = entry_id
        entry_count += 1
        conn.execute(
            "INSERT OR IGNORE INTO entry_clusters (entry_id, cluster_id) VALUES (?, ?)",
            (entry_id, source_hash),
        )

        for item in meta.get("citation", []):
            conn.execute(
                """
                INSERT INTO citations (entry_id, citation_key, title, journal, year, doi, pubmed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    item.get("id"),
                    item.get("title"),
                    item.get("journal"),
                    item.get("year"),
                    item.get("doi"),
                    item.get("pubmed"),
                ),
            )

        peptide_chain_ids = set()
        nonstd_chain_count = 0
        nonstd_mod_count = 0
        cyclic_chain_count = 0
        cyclic_types: set[str] = set()
        for item in annotations:
            chain_id = item.get("chain_id")
            peptide_chain_ids.add(chain_id)
            modification = item.get("modification", {})
            cyclic = item.get("cyclic", {})
            mod_positions = modification.get("positions", []) or []
            if modification.get("has_nonstd"):
                nonstd_chain_count += 1
            nonstd_mod_count += len(mod_positions)

            n_cyclic = int(cyclic.get("n_cyclic") or 0)
            chain_cyclic_types: list[str] = []
            if n_cyclic > 0 and cyclic.get("head2tail"):
                chain_cyclic_types.append("Head-to-Tail")
            if n_cyclic > 0 and cyclic.get("head2side"):
                chain_cyclic_types.append("Head-to-Side")
            if n_cyclic > 0 and cyclic.get("side2tail"):
                chain_cyclic_types.append("Side-to-Tail")
            if n_cyclic > 0 and cyclic.get("side2side"):
                chain_cyclic_types.append("Side-to-Side")
            if n_cyclic > 0:
                cyclic_chain_count += 1
            cyclic_types.update(chain_cyclic_types)

            conn.execute(
                """
                INSERT INTO peptide_chains (
                    entry_id, chain_id, chain_type, length, sequence,
                    has_nonstd, mod_positions_json, mod_types_json,
                    cyclic_head2tail, cyclic_head2side, cyclic_side2tail, cyclic_side2side,
                    n_ss, n_nc, n_cyclic, n_cyclic_nonstd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    chain_id,
                    "peptide",
                    item.get("length"),
                    item.get("sequence"),
                    1 if modification.get("has_nonstd") else 0,
                    json.dumps(mod_positions, ensure_ascii=True),
                    json.dumps(modification.get("types", []), ensure_ascii=True),
                    1 if cyclic.get("head2tail") else 0,
                    1 if cyclic.get("head2side") else 0,
                    1 if cyclic.get("side2tail") else 0,
                    1 if cyclic.get("side2side") else 0,
                    int(cyclic.get("n_ss") or 0),
                    int(cyclic.get("n_nc") or 0),
                    int(cyclic.get("n_cyclic") or 0),
                    int(cyclic.get("n_cyclic_nonstd") or 0),
                ),
            )
            chain_count += 1

        for item in meta.get("nonpoly", []):
            conn.execute(
                """
                INSERT INTO entry_nonpoly (entry_id, entity_id, comp_id, name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    entry_id,
                    item.get("entity_id"),
                    item.get("comp_id"),
                    item.get("name"),
                ),
            )
            nonpoly_count += 1

        for item in meta.get("connect", []):
            ptnr1 = item.get("ptnr1", {}) or {}
            ptnr2 = item.get("ptnr2", {}) or {}
            conn.execute(
                """
                INSERT INTO entry_connect (
                    entry_id, connect_id, connect_type, leaving_atom,
                    ptnr1_chain, ptnr1_comp, ptnr1_seq, ptnr1_atom,
                    ptnr2_chain, ptnr2_comp, ptnr2_seq, ptnr2_atom
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    item.get("id"),
                    item.get("type"),
                    item.get("leaving_atom"),
                    ptnr1.get("chain"),
                    ptnr1.get("comp_id"),
                    to_int(ptnr1.get("seq_id")),
                    ptnr1.get("atom"),
                    ptnr2.get("chain"),
                    ptnr2.get("comp_id"),
                    to_int(ptnr2.get("seq_id")),
                    ptnr2.get("atom"),
                ),
            )
            connect_count += 1

        if iface_path.exists():
            with iface_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    mask1 = obj.get("interface_mask1_sequence", "")
                    mask2 = obj.get("interface_mask2_sequence", "")
                    pair_id = obj.get("pair_id")
                    chain1_id = obj.get("chain1_id")
                    chain2_id = obj.get("chain2_id")
                    c1_pep = chain1_id in peptide_chain_ids
                    c2_pep = chain2_id in peptide_chain_ids
                    if c1_pep ^ c2_pep:
                        interface_kind = "PepPI"
                    elif (not c1_pep) and (not c2_pep):
                        interface_kind = "PPI"
                    else:
                        interface_kind = "other"
                    chain1_seq = obj.get("chain1_sequence", "")
                    chain2_seq = obj.get("chain2_sequence", "")
                    ss1 = obj.get("ss1", "")
                    ss2 = obj.get("ss2", "")

                    conn.execute(
                        """
                        INSERT INTO interface_pairs (
                            entry_id, pair_id, chain1_id, chain2_id, interface_kind,
                            chain1_len, chain2_len,
                            interface_residues1, interface_residues2
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry_id,
                            pair_id,
                            chain1_id,
                            chain2_id,
                            interface_kind,
                            len(chain1_seq),
                            len(chain2_seq),
                            mask1.count("-"),
                            mask2.count("-"),
                        ),
                    )

                    conn.execute(
                        """
                        INSERT INTO interface_details (
                            entry_id, pair_id, chain1_id, chain2_id,
                            chain1_sequence, chain2_sequence,
                            interface_mask1_sequence, interface_mask2_sequence,
                            ss1, ss2
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry_id,
                            pair_id,
                            chain1_id,
                            chain2_id,
                            chain1_seq,
                            chain2_seq,
                            mask1,
                            mask2,
                            ss1,
                            ss2,
                        ),
                    )
                    pair_count += 1
                    iface_detail_count += 1

        for file_path in sorted(entry_dir.iterdir()):
            if not file_path.is_file():
                continue
            stat = file_path.stat()
            if stat.st_mtime > latest_file_mtime:
                latest_file_mtime = stat.st_mtime
            suffix = file_path.suffix.lower()
            if suffix == ".cif":
                file_type = "cif"
            elif suffix == ".jsonl":
                file_type = "jsonl"
            elif suffix == ".json":
                file_type = "json"
            else:
                file_type = suffix.lstrip(".")

            rel_path = file_path.relative_to(dataset_root).as_posix()
            conn.execute(
                """
                INSERT INTO entry_files (entry_id, file_name, rel_path, file_type, size_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry_id, file_path.name, rel_path, file_type, stat.st_size),
            )
            file_count += 1

        conn.execute(
            """
            UPDATE entries
            SET peptide_chain_count = ?,
                has_nonstd = ?,
                nonstd_chain_count = ?,
                nonstd_mod_count = ?,
                is_cyclic = ?,
                cyclic_chain_count = ?,
                cyclic_types_json = ?,
                interface_pair_count = ?
            WHERE id = ?
            """,
            (
                len(peptide_chain_ids),
                1 if nonstd_chain_count > 0 else 0,
                nonstd_chain_count,
                nonstd_mod_count,
                1 if cyclic_chain_count > 0 else 0,
                cyclic_chain_count,
                json.dumps(sorted(cyclic_types), ensure_ascii=True),
                conn.execute(
                    "SELECT COUNT(*) FROM interface_pairs WHERE entry_id = ?",
                    (entry_id,),
                ).fetchone()[0],
                entry_id,
            ),
        )

        if entry_count % 500 == 0:
            conn.commit()

    if latest_file_mtime > 0:
        dataset_update_date = datetime.fromtimestamp(latest_file_mtime).strftime("%Y-%m-%d")
        conn.execute(
            "INSERT OR REPLACE INTO db_meta (meta_key, meta_value) VALUES (?, ?)",
            ("dataset_update_date", dataset_update_date),
        )

    target_cards, target_cards_skipped_invalid = load_target_card_records(target_cards_jsonl)
    pair_records, pair_skipped_invalid = load_pair_annotation_records(pair_annotations_jsonl)
    target_cards_merged = 0
    pair_records_merged = 0
    pair_skipped_unknown_entry = 0
    pair_skipped_missing_target = 0

    for _, rec in target_cards.items():
        conn.execute(
            """
            INSERT INTO target_cards (
                entry_key, target_id, target_name, mechanism_text, opentarget_url, notes,
                status, annotator, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec["entry_key"],
                rec["target_id"],
                rec["target_name"],
                rec["mechanism_text"],
                rec["opentarget_url"],
                rec["notes"],
                rec["status"],
                rec["annotator"],
                rec["updated_at"],
            ),
        )
        target_cards_merged += 1

    for _, rec in pair_records.items():
        entry_key = rec["entry_key"]
        row = conn.execute(
            "SELECT id, lower(pdb_id) AS pdb_key FROM entries WHERE lower(pdb_id) = ? OR entry_key = ? LIMIT 1",
            (entry_key, entry_key),
        ).fetchone()
        if not row:
            pair_skipped_unknown_entry += 1
            continue
        conn.execute(
            """
            INSERT INTO pair_annotations (
                entry_id, entry_key, cluster_id, pair_id, interface_kind,
                function_text, affinity_text, target_tags_json, evidence_json, confidence, notes, status, annotator,
                has_affinity, affinity_history_json, affinity_current_json, affinity_current_index, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["pdb_key"],
                rec["cluster_id"],
                rec["pair_id"],
                rec["interface_kind"],
                rec["function_text"],
                rec["affinity_text"],
                rec["target_tags_json"],
                rec["evidence_json"],
                rec["confidence"],
                rec["notes"],
                rec["status"],
                rec["annotator"],
                rec["has_affinity"],
                rec["affinity_history_json"],
                rec["affinity_current_json"],
                rec["affinity_current_index"],
                rec["updated_at"],
            ),
        )
        pair_records_merged += 1

    conn.commit()
    cluster_count = conn.execute("SELECT COUNT(DISTINCT cluster_id) FROM entry_clusters").fetchone()[0]
    conn.close()
    return {
        "entries": entry_count,
        "clusters": cluster_count,
        "peptide_chains": chain_count,
        "nonpoly": nonpoly_count,
        "connect": connect_count,
        "interface_pairs": pair_count,
        "interface_details": iface_detail_count,
        "files": file_count,
        "target_cards_merged": target_cards_merged,
        "target_cards_skipped_invalid": target_cards_skipped_invalid,
        "pair_records_merged": pair_records_merged,
        "pair_records_skipped_invalid": pair_skipped_invalid,
        "pair_records_skipped_unknown_entry": pair_skipped_unknown_entry,
        "pair_records_skipped_missing_target": pair_skipped_missing_target,
        "db_path": str(db_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PepPCDB SQLite database")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "filtered_peppi",
        help="Path to filtered_peppi dataset root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "peppcdb.sqlite3",
        help="Output sqlite database path",
    )
    parser.add_argument(
        "--target-cards-jsonl",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "records" / "target_cards.jsonl",
        help="Path to target cards jsonl",
    )
    parser.add_argument(
        "--pair-annotations-jsonl",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "records" / "pep_annotations_patched.jsonl",
        help="Path to peptide ligand annotations jsonl",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dataset.exists():
        raise SystemExit(f"Dataset path does not exist: {args.dataset}")

    result = build_database(args.dataset, args.output, args.target_cards_jsonl, args.pair_annotations_jsonl)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
