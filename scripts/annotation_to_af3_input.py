#!/usr/bin/env python3
"""Generate AlphaFold 3 input JSON from a PepPCDB entry annotation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.af3_input import AF3InputError, build_af3_input, build_af3_options  # noqa: E402


def default_path(env_name: str, fallback: Path) -> Path:
    return Path(os.environ.get(env_name, str(fallback))).expanduser().resolve()


def parse_seed_args(values: list[str] | None) -> list[int] | None:
    if not values:
        return None
    raw_parts: list[str] = []
    for value in values:
        raw_parts.extend(str(value).replace(";", ",").split(","))
    seeds = [int(x.strip()) for x in raw_parts if x.strip()]
    return seeds or None


def parse_chain_args(chains: str | None, extras: list[str] | None) -> list[str] | None:
    out: list[str] = []
    if chains:
        out.extend(x.strip() for x in chains.replace(";", ",").split(","))
    if extras:
        for item in extras:
            out.extend(x.strip() for x in item.replace(";", ",").split(","))
    cleaned: list[str] = []
    seen: set[str] = set()
    for chain_id in out:
        if not chain_id or chain_id in seen:
            continue
        cleaned.append(chain_id)
        seen.add(chain_id)
    return cleaned or None


def option_default_chains(options: dict[str, Any], pair_id: str | None) -> list[str]:
    if pair_id:
        for pair in options.get("pairs", []):
            if pair.get("pair_id") == pair_id:
                return list(pair.get("default_chain_ids") or [])
    return list((options.get("defaults") or {}).get("chain_ids") or [])


def resolve_chain_args(args: argparse.Namespace) -> list[str] | None:
    if args.chains:
        return parse_chain_args(args.chains, args.extra_chain)
    extras = parse_chain_args(None, args.extra_chain)
    if not extras:
        return None
    options = build_af3_options(args.db, args.dataset, args.entry_key)
    return parse_chain_args(",".join(option_default_chains(options, args.pair_id)), extras)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("entry_key", help="PDB ID or PepPCDB entry key")
    p.add_argument("--db", type=Path, default=default_path("PEPPCDB_DB", ROOT_DIR / "data" / "peppcdb.sqlite3"))
    p.add_argument("--dataset", type=Path, default=default_path("PEPPCDB_DATASET", ROOT_DIR / "data" / "filtered_peppi"))
    p.add_argument("--pair-id", default=None, help="PepPI pair ID. Defaults to the first PepPI pair.")
    p.add_argument("--chains", default=None, help="Comma-separated chain IDs. Overrides the pair default.")
    p.add_argument("--extra-chain", action="append", default=[], help="Additional chain ID(s), comma-separated if needed.")
    p.add_argument("--seeds", nargs="+", default=None, help="Random seeds, e.g. --seeds 42 or --seeds 42,55.")
    p.add_argument("--job-id", default=None, help="AF3 job name. Defaults to the PDB ID.")
    p.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults to stdout.")
    p.add_argument("--show-options", action="store_true", help="Print available AF3 pair/chain options and exit.")
    p.add_argument("--no-include-peptide-bonds", action="store_true", help="Disable peptide-related bonded atom pairs.")
    p.add_argument("--include-protein-bonds", action="store_true", help="Include protein-only covalent/disulfide bonded atom pairs.")
    return p


def write_json(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def main() -> int:
    args = parser().parse_args()
    try:
        if args.show_options:
            write_json(build_af3_options(args.db, args.dataset, args.entry_key), args.output)
            return 0

        result = build_af3_input(
            args.db,
            args.dataset,
            args.entry_key,
            pair_id=args.pair_id,
            chain_ids=resolve_chain_args(args),
            seeds=parse_seed_args(args.seeds),
            job_id=args.job_id,
            include_peptide_bonds=not args.no_include_peptide_bonds,
            include_protein_bonds=args.include_protein_bonds,
        )
    except (AF3InputError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    write_json(result["config"], args.output)
    if result.get("warnings"):
        for warning in result["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
