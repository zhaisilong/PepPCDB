from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_SEEDS = [42]
AF3_VERSION = 4

STANDARD_THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

# Lightweight subset of the CCD-to-one-letter map used by afrun. Unknown
# modified residues intentionally fall back to X while the original CCD code is
# preserved in the AF3 modification record.
CCD_NAME_TO_ONE_LETTER = {
    **STANDARD_THREE_TO_ONE,
    "ASX": "B",
    "GLX": "Z",
    "SEC": "U",
    "PYL": "O",
    "UNK": "X",
    "MSE": "M",
    "SEP": "S",
    "TPO": "T",
    "PTR": "Y",
    "CSO": "C",
    "CME": "C",
    "MLY": "K",
    "KCX": "K",
    "M3L": "K",
    "MLE": "L",
    "MAA": "A",
    "SAR": "G",
    "7VU": "F",
    "7W2": "F",
    "7VN": "A",
    "HYP": "P",
    "DPR": "P",
    "DAL": "A",
    "DAR": "R",
    "DSG": "N",
    "DSP": "D",
    "DCY": "C",
    "DGN": "Q",
    "DGL": "E",
    "DHI": "H",
    "DIL": "I",
    "DLE": "L",
    "DLY": "K",
    "MED": "M",
    "DPN": "F",
    "DPR": "P",
    "DSN": "S",
    "DTH": "T",
    "DTR": "W",
    "DTY": "Y",
    "DVA": "V",
    "AIB": "A",
    "ABA": "A",
    "ORN": "K",
    "NLE": "L",
    "NVA": "V",
}

PEPTIDE_BOND_TYPES = {"covale", "disulf"}
PROTEIN_BOND_TYPES = {"covale", "disulf"}


class AF3InputError(ValueError):
    pass


def canonical_entry(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if "__" in raw:
        raw = raw.rsplit("__", 1)[-1].strip()
    return raw


def parse_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows(rows_: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows_]


def one_letter_for(code: Any) -> str:
    raw = str(code or "").strip().upper()
    if len(raw) == 1 and raw in "ARNDCQEGHILKMFPSTWYVXOUBZ":
        return raw
    return CCD_NAME_TO_ONE_LETTER.get(raw, "X")


def unique_ordered(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        out.append(item)
        seen.add(item)
    return out


def normalize_seeds(raw: Any) -> list[int]:
    if raw is None or raw == "":
        return list(DEFAULT_SEEDS)
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace(";", ",").split(",")]
    elif isinstance(raw, list):
        parts = raw
    else:
        raise AF3InputError("Seeds must be an integer, comma-separated string, or list of integers")

    seeds: list[int] = []
    for part in parts:
        if part in ("", None):
            continue
        try:
            seeds.append(int(part))
        except (TypeError, ValueError) as exc:
            raise AF3InputError(f"Invalid seed: {part}") from exc
    if not seeds:
        raise AF3InputError("At least one seed is required")
    return seeds


def safe_job_id(raw: Any, default: str) -> str:
    value = str(raw or "").strip() or default
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned or default


def connect_db(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise AF3InputError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_entry_json_path(conn: sqlite3.Connection, dataset_root: Path, entry: sqlite3.Row) -> Path:
    pdb_id = str(entry["pdb_id"]).lower()
    row = conn.execute(
        "SELECT rel_path FROM entry_files WHERE entry_id = ? AND file_name = ? LIMIT 1",
        (entry["id"], f"{pdb_id}.json"),
    ).fetchone()
    if not row:
        raise AF3InputError(f"Entry metadata JSON not found for {pdb_id}")
    resolved = (dataset_root / row["rel_path"]).resolve()
    root = dataset_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise AF3InputError("Entry metadata path escaped dataset root")
    if not resolved.is_file():
        raise AF3InputError(f"Entry metadata JSON missing: {resolved}")
    return resolved


def load_entry_context(db_path: Path, dataset_root: Path, entry_key: str) -> dict[str, Any]:
    ref = canonical_entry(entry_key)
    if not ref:
        raise AF3InputError("Entry key is required")
    with connect_db(db_path) as conn:
        entry = conn.execute(
            """
            SELECT id, entry_key, pdb_id
            FROM entries
            WHERE lower(pdb_id) = ? OR entry_key = ?
            ORDER BY CASE WHEN lower(pdb_id) = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (ref, ref, ref),
        ).fetchone()
        if not entry:
            raise AF3InputError(f"Entry not found: {entry_key}")

        metadata_path = resolve_entry_json_path(conn, dataset_root, entry)
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        pairs = conn.execute(
            """
            SELECT pair_id, chain1_id, chain2_id, chain1_len, chain2_len,
                   interface_kind, interface_residues1, interface_residues2
            FROM interface_pairs
            WHERE entry_id = ?
            ORDER BY pair_id
            """,
            (entry["id"],),
        ).fetchall()
        peptide_rows = conn.execute(
            """
            SELECT
                chain_id, length, sequence, has_nonstd, mod_has_linker,
                mod_positions_json, mod_types_json,
                cyclic_head2tail, cyclic_head2side, cyclic_side2tail, cyclic_side2side,
                cyclic_has_cyc_linker, n_cyclic
            FROM peptide_chains
            WHERE entry_id = ?
            ORDER BY chain_id
            """,
            (entry["id"],),
        ).fetchall()

    peptide_info: dict[str, dict[str, Any]] = {}
    for row in rows(peptide_rows):
        chain_id = str(row.get("chain_id") or "")
        row["mod_positions"] = parse_json_list(row.pop("mod_positions_json", "[]"))
        row["mod_types"] = parse_json_list(row.pop("mod_types_json", "[]"))
        peptide_info[chain_id] = row

    polymer = [x for x in meta.get("polymer", []) if isinstance(x, dict) and x.get("id")]
    return {
        "entry": row_dict(entry),
        "pdb_id": str(entry["pdb_id"]).lower(),
        "metadata_path": metadata_path,
        "meta": meta,
        "polymer": polymer,
        "pairs": rows(pairs),
        "peptide_info": peptide_info,
        "peptide_chain_ids": set(peptide_info),
    }


def pair_default_chain_ids(pair: dict[str, Any], peptide_chain_ids: set[str]) -> list[str]:
    chains = [str(pair.get("chain1_id") or ""), str(pair.get("chain2_id") or "")]
    peptide = [x for x in chains if x in peptide_chain_ids]
    protein = [x for x in chains if x and x not in peptide_chain_ids]
    return unique_ordered([*peptide, *protein])


def default_pair(context: dict[str, Any]) -> dict[str, Any] | None:
    peppi = [p for p in context["pairs"] if p.get("interface_kind") == "PepPI"]
    return peppi[0] if peppi else (context["pairs"][0] if context["pairs"] else None)


def chain_summary(chain: dict[str, Any], peptide_info: dict[str, dict[str, Any]]) -> dict[str, Any]:
    chain_id = str(chain.get("id") or "")
    pep = peptide_info.get(chain_id, {})
    is_peptide = chain_id in peptide_info
    mod_positions = chain.get("positions") or pep.get("mod_positions") or []
    mod_types = chain.get("types") or pep.get("mod_types") or []
    n_cyclic = int(pep.get("n_cyclic") or 0) if pep else 0
    cyclic_flags = [
        pep.get("cyclic_head2tail"),
        pep.get("cyclic_head2side"),
        pep.get("cyclic_side2tail"),
        pep.get("cyclic_side2side"),
        pep.get("cyclic_has_cyc_linker"),
        n_cyclic > 0,
    ]
    return {
        "chain_id": chain_id,
        "role": "peptide" if is_peptide else "protein",
        "polymer_type": chain.get("type") or "-",
        "length": chain.get("length") or len(str(chain.get("sequence") or "")),
        "sequence": chain.get("sequence") or "",
        "has_nonstd": bool(chain.get("has_nonstd") or pep.get("has_nonstd")),
        "mod_positions": mod_positions,
        "mod_types": mod_types,
        "mod_has_linker": bool(pep.get("mod_has_linker")),
        "is_cyclic": any(bool(x) for x in cyclic_flags),
        "cyclic_has_cyc_linker": bool(pep.get("cyclic_has_cyc_linker")),
    }


def build_af3_options(db_path: Path, dataset_root: Path, entry_key: str) -> dict[str, Any]:
    context = load_entry_context(db_path, dataset_root, entry_key)
    pep_ids = context["peptide_chain_ids"]
    pair = default_pair(context)
    selectable_pairs = [p for p in context["pairs"] if p.get("interface_kind") == "PepPI"] or context["pairs"]
    pairs = []
    for item in selectable_pairs:
        chain_ids = [str(item.get("chain1_id") or ""), str(item.get("chain2_id") or "")]
        peptide_ids = [x for x in chain_ids if x in pep_ids]
        protein_ids = [x for x in chain_ids if x and x not in pep_ids]
        pairs.append(
            {
                **item,
                "peptide_chain_ids": peptide_ids,
                "protein_chain_ids": protein_ids,
                "default_chain_ids": pair_default_chain_ids(item, pep_ids),
            }
        )

    default_pair_id = str(pair.get("pair_id") or "") if pair else ""
    default_chains = pair_default_chain_ids(pair, pep_ids) if pair else []
    return {
        "entry_key": context["pdb_id"],
        "pdb_id": context["pdb_id"],
        "defaults": {
            "pair_id": default_pair_id,
            "chain_ids": default_chains,
            "seeds": list(DEFAULT_SEEDS),
            "job_id": context["pdb_id"],
            "include_peptide_bonds": True,
            "include_protein_bonds": False,
        },
        "pairs": pairs,
        "chains": [chain_summary(chain, context["peptide_info"]) for chain in context["polymer"]],
        "bond_types": {
            "peptide_default": sorted(PEPTIDE_BOND_TYPES),
            "protein_optional": sorted(PROTEIN_BOND_TYPES),
        },
    }


def normalize_chain_sequence(chain: dict[str, Any], warnings: list[str]) -> tuple[str, list[dict[str, Any]]]:
    sequence = list(str(chain.get("sequence") or ""))
    positions = chain.get("positions") or []
    types = chain.get("types") or []
    modifications: list[dict[str, Any]] = []
    for pos_raw, code_raw in zip(positions, types):
        try:
            pos = int(pos_raw)
        except (TypeError, ValueError):
            warnings.append(f"Skipped invalid modification position {pos_raw} on chain {chain.get('id')}")
            continue
        code = str(code_raw or "").strip().upper()
        if not code:
            continue
        if 1 <= pos <= len(sequence):
            sequence[pos - 1] = one_letter_for(code)
            modifications.append({"ptmType": code, "ptmPosition": pos})
        else:
            warnings.append(f"Skipped out-of-range modification {code}@{pos} on chain {chain.get('id')}")
    cleaned = "".join(x if x and x != "?" else "X" for x in sequence)
    return cleaned, modifications


def sequence_entry(
    chain: dict[str, Any],
    pdb_id: str,
    peptide_chain_ids: set[str],
    warnings: list[str],
) -> dict[str, Any]:
    chain_id = str(chain.get("id") or "")
    sequence, modifications = normalize_chain_sequence(chain, warnings)
    role = "peptide" if chain_id in peptide_chain_ids else "protein"
    protein = {
        "id": chain_id,
        "sequence": sequence,
        "description": f"PepPCDB {role} chain {chain_id} from PDB {pdb_id.upper()}",
    }
    if modifications:
        protein["modifications"] = modifications
    return {"protein": protein}


def connect_to_bond(row: dict[str, Any]) -> list[Any] | None:
    required = [
        row.get("ptnr1_chain"),
        row.get("ptnr1_seq"),
        row.get("ptnr1_atom"),
        row.get("ptnr2_chain"),
        row.get("ptnr2_seq"),
        row.get("ptnr2_atom"),
    ]
    if any(x in (None, "") for x in required):
        return None
    return [
        [str(row["ptnr1_chain"]), int(row["ptnr1_seq"]), str(row["ptnr1_atom"])],
        [str(row["ptnr2_chain"]), int(row["ptnr2_seq"]), str(row["ptnr2_atom"])],
    ]


def normalize_connect(row: dict[str, Any]) -> dict[str, Any]:
    if "ptnr1" not in row and "ptnr2" not in row:
        return row
    ptnr1 = row.get("ptnr1") or {}
    ptnr2 = row.get("ptnr2") or {}
    return {
        "connect_id": row.get("id"),
        "connect_type": row.get("type"),
        "leaving_atom": row.get("leaving_atom"),
        "ptnr1_chain": ptnr1.get("chain"),
        "ptnr1_comp": ptnr1.get("comp_id"),
        "ptnr1_seq": ptnr1.get("seq_id"),
        "ptnr1_atom": ptnr1.get("atom"),
        "ptnr2_chain": ptnr2.get("chain"),
        "ptnr2_comp": ptnr2.get("comp_id"),
        "ptnr2_seq": ptnr2.get("seq_id"),
        "ptnr2_atom": ptnr2.get("atom"),
    }


def bonded_atom_pairs(
    connect_rows: list[dict[str, Any]],
    selected_chain_ids: set[str],
    peptide_chain_ids: set[str],
    include_peptide_bonds: bool,
    include_protein_bonds: bool,
    warnings: list[str],
) -> list[list[Any]]:
    out: list[list[Any]] = []
    seen: set[tuple[Any, ...]] = set()
    skipped_incomplete = 0
    for row in connect_rows:
        row = normalize_connect(row)
        c1 = str(row.get("ptnr1_chain") or "")
        c2 = str(row.get("ptnr2_chain") or "")
        if c1 not in selected_chain_ids or c2 not in selected_chain_ids:
            continue
        ctype = str(row.get("type") or row.get("connect_type") or "").strip().lower()
        peptide_related = c1 in peptide_chain_ids or c2 in peptide_chain_ids
        if peptide_related:
            if not include_peptide_bonds or ctype not in PEPTIDE_BOND_TYPES:
                continue
        elif not include_protein_bonds or ctype not in PROTEIN_BOND_TYPES:
            continue
        bond = connect_to_bond(row)
        if not bond:
            skipped_incomplete += 1
            continue
        key = tuple(tuple(x) for x in bond)
        if key in seen:
            continue
        seen.add(key)
        out.append(bond)
    if skipped_incomplete:
        warnings.append(f"Skipped {skipped_incomplete} connect records without residue-level atom pairs")
    return out


def build_af3_input(
    db_path: Path,
    dataset_root: Path,
    entry_key: str,
    *,
    pair_id: str | None = None,
    chain_ids: list[Any] | None = None,
    seeds: Any = None,
    job_id: str | None = None,
    include_peptide_bonds: bool = True,
    include_protein_bonds: bool = False,
) -> dict[str, Any]:
    context = load_entry_context(db_path, dataset_root, entry_key)
    pdb_id = context["pdb_id"]
    warnings: list[str] = []
    pair_by_id = {str(x.get("pair_id") or ""): x for x in context["pairs"]}
    selected_pair = pair_by_id.get(str(pair_id or "")) if pair_id else default_pair(context)
    if pair_id and not selected_pair:
        raise AF3InputError(f"Interface pair not found: {pair_id}")
    selected_pair_id = str(selected_pair.get("pair_id") or "") if selected_pair else ""

    chain_by_id = {str(x.get("id") or ""): x for x in context["polymer"]}
    if chain_ids:
        selected_chain_ids = unique_ordered(chain_ids)
    elif selected_pair:
        selected_chain_ids = pair_default_chain_ids(selected_pair, context["peptide_chain_ids"])
    else:
        selected_chain_ids = unique_ordered(list(chain_by_id))
    if not selected_chain_ids:
        raise AF3InputError("At least one chain is required")

    missing = [x for x in selected_chain_ids if x not in chain_by_id]
    if missing:
        raise AF3InputError(f"Unknown chain id(s): {', '.join(missing)}")

    sequences = [
        sequence_entry(chain_by_id[chain_id], pdb_id, context["peptide_chain_ids"], warnings)
        for chain_id in selected_chain_ids
    ]
    bonds = bonded_atom_pairs(
        context["meta"].get("connect", []) or [],
        set(selected_chain_ids),
        context["peptide_chain_ids"],
        include_peptide_bonds,
        include_protein_bonds,
        warnings,
    )

    config: dict[str, Any] = {
        "name": safe_job_id(job_id, pdb_id),
        "modelSeeds": normalize_seeds(seeds),
        "sequences": sequences,
        "dialect": "alphafold3",
        "version": AF3_VERSION,
    }
    if bonds:
        config["bondedAtomPairs"] = bonds

    modifications_count = sum(len(item["protein"].get("modifications", [])) for item in sequences)
    return {
        "entry_key": pdb_id,
        "pdb_id": pdb_id,
        "config": config,
        "summary": {
            "pair_id": selected_pair_id,
            "chain_ids": selected_chain_ids,
            "chain_count": len(selected_chain_ids),
            "seed_count": len(config["modelSeeds"]),
            "bond_count": len(bonds),
            "modification_count": modifications_count,
            "include_peptide_bonds": include_peptide_bonds,
            "include_protein_bonds": include_protein_bonds,
        },
        "warnings": warnings,
    }
