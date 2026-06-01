from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import time
import urllib.parse
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"

DEFAULT_DB = DATA_DIR / "peppcdb.sqlite3"
DEFAULT_USAGE_DB = DATA_DIR / "usage_stats.sqlite3"
DEFAULT_DATASET = DATA_DIR / "filtered_peppi"
DEFAULT_TARGET_CARDS = DATA_DIR / "records" / "target_cards.jsonl"
DEFAULT_PEP_ANNOTATIONS = DATA_DIR / "records" / "pep_annotations_patched.jsonl"


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


DB_PATH = env_path("PEPPCDB_DB", DEFAULT_DB)
USAGE_DB_PATH = env_path("PEPPCDB_USAGE_DB", DEFAULT_USAGE_DB)
DATASET_ROOT = env_path("PEPPCDB_DATASET", DEFAULT_DATASET)
TARGET_CARDS_JSONL = env_path("PEPPCDB_TARGET_CARDS_JSONL", DEFAULT_TARGET_CARDS)
PEP_ANNOTATIONS_JSONL = env_path("PEPPCDB_PEP_ANNOTATIONS_JSONL", DEFAULT_PEP_ANNOTATIONS)
APP_VERSION = "0.2.0"
PDB_SOURCE_SNAPSHOT_DATE = os.environ.get("PEPPCDB_PDB_SOURCE_SNAPSHOT_DATE", "2025-12-29")
DOWNLOAD_RATE_LIMIT = int(os.environ.get("PEPPCDB_DOWNLOAD_RATE_LIMIT", "100"))
DOWNLOAD_RATE_WINDOW_SECONDS = 3600
USAGE_SALT = os.environ.get("PEPPCDB_USAGE_SALT", "")


app = FastAPI(title="PepPCDB", version=APP_VERSION)
_download_rate_state: dict[str, tuple[float, int]] = {}


class RateLimitExceeded(Exception):
    pass


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"error": "rate limit exceeded"}, status_code=429)


@app.on_event("startup")
def validate_required_assets() -> None:
    init_usage_db()
    missing = [
        str(path)
        for path in (DB_PATH, DATASET_ROOT, TARGET_CARDS_JSONL, PEP_ANNOTATIONS_JSONL)
        if not path.exists()
    ]
    if missing:
        raise RuntimeError("Missing required PepPCDB deployment assets: " + ", ".join(missing))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail=f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows(rows_: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows_]


def parse_json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_json_any(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def canonical_entry(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if "__" in raw:
        raw = raw.rsplit("__", 1)[-1].strip()
    return raw


def pdb_url(pdb_id: str | None) -> str | None:
    return f"https://www.rcsb.org/structure/{pdb_id.upper()}" if pdb_id else None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def db_update_date(conn: sqlite3.Connection) -> str | None:
    try:
        row = conn.execute(
            "SELECT meta_value FROM db_meta WHERE meta_key = 'dataset_update_date' LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row and row[0] else None


def manual_stamp() -> tuple[int, int]:
    t = TARGET_CARDS_JSONL.stat().st_mtime_ns if TARGET_CARDS_JSONL.exists() else -1
    p = PEP_ANNOTATIONS_JSONL.stat().st_mtime_ns if PEP_ANNOTATIONS_JSONL.exists() else -1
    return t, p


_manual_cache: dict[str, Any] = {}


def manual_state() -> dict[str, Any]:
    stamp = manual_stamp()
    if _manual_cache.get("stamp") == stamp:
        return _manual_cache["data"]

    targets: dict[str, dict[str, Any]] = {}
    for obj in load_jsonl(TARGET_CARDS_JSONL):
        target_id = str(obj.get("target_id", "")).strip()
        if not target_id:
            continue
        function_classes = obj.get("canonical_function_classes")
        if not isinstance(function_classes, list):
            function_classes = [] if function_classes in (None, "") else [function_classes]
        accessions = obj.get("canonical_accessions")
        if not isinstance(accessions, list):
            accessions = [] if accessions in (None, "") else [accessions]
        targets[target_id] = {
            "target_id": target_id,
            "target_name": str(obj.get("target_name", "")).strip(),
            "mechanism_text": str(obj.get("mechanism_text", "")).strip(),
            "opentarget_url": str(obj.get("opentarget_url", "")).strip(),
            "status": str(obj.get("status", "")).strip(),
            "updated_at": str(obj.get("updated_at", "")).strip(),
            "notes": str(obj.get("notes", "")).strip(),
            "annotator": str(obj.get("annotator", "")).strip(),
            "canonical_target_id": str(obj.get("canonical_target_id", "")).strip(),
            "canonical_target_name": str(obj.get("canonical_target_name", "")).strip(),
            "canonical_entity_type": str(obj.get("canonical_entity_type", "")).strip(),
            "canonical_function_classes": [str(x).strip() for x in function_classes if str(x).strip()],
            "canonical_organism": str(obj.get("canonical_organism", "")).strip(),
            "canonical_accessions": [str(x).strip() for x in accessions if str(x).strip()],
            "axis_type": str(obj.get("axis_type", "")).strip(),
            "axis_summary": str(obj.get("axis_summary", "")).strip(),
            "normalization_status": str(obj.get("normalization_status", "")).strip(),
        }

    peps: dict[str, dict[str, Any]] = {}
    for obj in load_jsonl(PEP_ANNOTATIONS_JSONL):
        entry_key = canonical_entry(obj.get("entry_key"))
        pep_id = str(obj.get("pep_id", "")).strip() or str(obj.get("pair_id", "")).strip()
        chain_ids = [str(x).strip() for x in (obj.get("chain_ids") or []) if str(x).strip()]
        if not chain_ids and pep_id:
            chain_ids = [pep_id]
        ligand_id = str(obj.get("ligand_id", "")).strip() or pep_id or (chain_ids[0] if chain_ids else "")
        if not entry_key or not ligand_id or not chain_ids:
            continue
        peps[f"{entry_key}::{ligand_id}"] = {
            "entry_key": entry_key,
            "pair_id": chain_ids[0],
            "pep_id": pep_id,
            "ligand_id": ligand_id,
            "chain_ids": list(dict.fromkeys(chain_ids)),
            "pep_sequence": obj.get("pep_sequence"),
            "pep_length": obj.get("pep_length"),
            "function_text": str(obj.get("function_text", "")).strip(),
            "notes": str(obj.get("notes", "")).strip(),
            "affinity_text": str(obj.get("affinity_text", "")).strip(),
            "target_tags": [str(x).strip() for x in (obj.get("target_tags") or []) if str(x).strip()],
            "status": str(obj.get("status", "")).strip(),
            "updated_at": str(obj.get("updated_at", "")).strip(),
            "has_affinity": obj.get("has_affinity"),
        }

    affinity_entries = {
        str(rec.get("entry_key", "")).strip().lower()
        for rec in peps.values()
        if rec.get("has_affinity") is True and str(rec.get("affinity_text", "")).strip()
    }
    affinity_annotation_count = sum(
        1
        for rec in peps.values()
        if rec.get("has_affinity") is True and str(rec.get("affinity_text", "")).strip()
    )
    data = {
        "targets_by_id": targets,
        "peps_by_key": peps,
        "affinity_entries": affinity_entries,
        "affinity_annotation_count": affinity_annotation_count,
    }
    _manual_cache.clear()
    _manual_cache.update({"stamp": stamp, "data": data})
    return data


def get_entry_min(conn: sqlite3.Connection, entry_key: str) -> sqlite3.Row | None:
    ref = canonical_entry(entry_key)
    if not ref:
        return None
    return conn.execute(
        """
        SELECT id, entry_key, pdb_id
        FROM entries
        WHERE lower(pdb_id) = ? OR entry_key = ?
        ORDER BY CASE WHEN lower(pdb_id) = ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (ref, ref, ref),
    ).fetchone()


def resolve_file(conn: sqlite3.Connection, entry_key: str, filename: str) -> tuple[Path, str]:
    entry = get_entry_min(conn, entry_key)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    row = conn.execute(
        "SELECT rel_path FROM entry_files WHERE entry_id = ? AND file_name = ? LIMIT 1",
        (entry["id"], filename),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    resolved = (DATASET_ROOT / row["rel_path"]).resolve()
    root = DATASET_ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(status_code=404, detail="File not found")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return resolved, row["rel_path"]


def public_download_name(pdb_id: str, filename: str) -> str:
    raw = str(filename or "").strip()
    prefix = str(pdb_id or "").strip().lower()
    if not raw or not prefix:
        return raw
    lower = raw.lower()
    if lower == "annotations.json":
        return f"{prefix}_annotations.json"
    if lower == "interface.jsonl":
        return f"{prefix}_interface.jsonl"
    if lower == "function.json":
        return f"{prefix}_function.json"
    return raw


def source_file_name_from_public(pdb_id: str, filename: str) -> str:
    raw = str(filename or "").strip()
    prefix = str(pdb_id or "").strip().lower()
    lower = raw.lower()
    if prefix and lower == f"{prefix}_annotations.json":
        return "annotations.json"
    if prefix and lower == f"{prefix}_interface.jsonl":
        return "interface.jsonl"
    return raw


def client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
    return request.client.host if request.client else "unknown"


def usage_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def usage_ip_hash(request: Request) -> str:
    raw = f"{USAGE_SALT}:{client_key(request)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def usage_connect() -> sqlite3.Connection:
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(USAGE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_usage_db() -> None:
    with usage_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_daily_unique (
                date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('visit', 'download')),
                ip_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (date, kind, ip_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_kind_date
            ON usage_daily_unique(kind, date)
            """
        )


def record_usage(request: Request, kind: str) -> None:
    if kind not in {"visit", "download"}:
        return
    today = date.today().isoformat()
    now = usage_now()
    try:
        with usage_connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_daily_unique (date, kind, ip_hash, first_seen_at, last_seen_at, hits)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(date, kind, ip_hash) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    hits = usage_daily_unique.hits + 1
                """,
                (today, kind, usage_ip_hash(request), now, now),
            )
    except sqlite3.Error:
        return


def usage_summary() -> dict[str, Any]:
    today = date.today().isoformat()
    with usage_connect() as conn:
        rows_ = conn.execute(
            """
            SELECT kind,
                   SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS today_count,
                   COUNT(*) AS total_count
            FROM usage_daily_unique
            GROUP BY kind
            """,
            (today,),
        ).fetchall()
    counts = {row["kind"]: {"today": row["today_count"], "total": row["total_count"]} for row in rows_}
    return {
        "visit_today": int(counts.get("visit", {}).get("today", 0) or 0),
        "visit_total": int(counts.get("visit", {}).get("total", 0) or 0),
        "download_today": int(counts.get("download", {}).get("today", 0) or 0),
        "download_total": int(counts.get("download", {}).get("total", 0) or 0),
        "updated_at": usage_now(),
    }


def check_download_rate_limit(request: Request) -> None:
    key = client_key(request)
    now = time.time()
    window_start, count = _download_rate_state.get(key, (now, 0))
    if now - window_start >= DOWNLOAD_RATE_WINDOW_SECONDS:
        window_start, count = now, 0
    if count >= DOWNLOAD_RATE_LIMIT:
        raise RateLimitExceeded()
    _download_rate_state[key] = (window_start, count + 1)


def function_payload(entry_key: str) -> dict[str, Any]:
    detail = entry_detail(entry_key)
    return {
        "entry_key": detail.get("entry_key"),
        "pdb_id": detail.get("pdb_id"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "peptide_functions": detail.get("peptide_functions", []),
        "target_cards": detail.get("target_cards", []),
    }


@app.middleware("http")
async def record_home_visit(request: Request, call_next: Any) -> Response:
    response = await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    if response.status_code < 400 and path in {"/", "/index.html"}:
        record_usage(request, "visit")
    return response


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": APP_VERSION}


@app.get("/api/usage-stats")
def usage_stats() -> dict[str, Any]:
    return usage_summary()


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with connect() as conn:
        payload = {
            "entries": conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"],
            "peptide_chains": conn.execute("SELECT COUNT(*) AS n FROM peptide_chains").fetchone()["n"],
            "interface_pairs": conn.execute("SELECT COUNT(*) AS n FROM interface_pairs").fetchone()["n"],
            "peppi_interface_pairs": conn.execute(
                "SELECT COUNT(*) AS n FROM interface_pairs WHERE interface_kind='PepPI'"
            ).fetchone()["n"],
            "cif_files": conn.execute(
                "SELECT COUNT(*) AS n FROM entry_files WHERE file_type='cif'"
            ).fetchone()["n"],
            "nonpoly": conn.execute("SELECT COUNT(*) AS n FROM entry_nonpoly").fetchone()["n"],
            "connect": conn.execute("SELECT COUNT(*) AS n FROM entry_connect").fetchone()["n"],
            "cyclic_pdb_ids": conn.execute("SELECT COUNT(*) AS n FROM entries WHERE is_cyclic = 1").fetchone()["n"],
            "clusters": conn.execute("SELECT COUNT(DISTINCT cluster_id) AS n FROM entry_clusters").fetchone()["n"],
            "db_update_date": db_update_date(conn),
            "pdb_source_snapshot_date": PDB_SOURCE_SNAPSHOT_DATE,
        }
    manual = manual_state()
    payload["affinity_annotations"] = manual.get("affinity_annotation_count", 0)
    return payload


@app.get("/api/entries")
def entries(
    q: str = "",
    method: str = "",
    date_from: str = "",
    date_to: str = "",
    has_nonstd: str = "",
    has_affinity: str = "",
    is_cyclic: str = "",
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    keyword = q.strip().lower()
    if keyword:
        where.append(
            """
            (
                lower(e.pdb_id) LIKE ?
                OR lower(e.source_hash) LIKE ?
                OR EXISTS (SELECT 1 FROM entry_clusters ec WHERE ec.entry_id = e.id AND lower(ec.cluster_id) LIKE ?)
                OR lower(COALESCE(e.entry_id, '')) LIKE ?
                OR lower(COALESCE(e.exptl_method, '')) LIKE ?
                OR EXISTS (
                    SELECT 1 FROM peptide_chains pc
                    WHERE pc.entry_id = e.id AND (lower(pc.chain_id) LIKE ? OR lower(pc.sequence) LIKE ?)
                )
            )
            """
        )
        like = f"%{keyword}%"
        params.extend([like, like, like, like, like, like, like])
    if method.strip():
        where.append("e.exptl_method = ?")
        params.append(method.strip())
    if date_from:
        try:
            date.fromisoformat(date_from)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date_from") from exc
        where.append("e.deposition_date >= ?")
        params.append(date_from)
    if date_to:
        try:
            date.fromisoformat(date_to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date_to") from exc
        where.append("e.deposition_date <= ?")
        params.append(date_to)
    if has_nonstd == "1":
        where.append("e.nonstd_chain_count > 0")
    elif has_nonstd == "0":
        where.append("e.nonstd_chain_count = 0")
    if is_cyclic in {"0", "1"}:
        where.append("e.is_cyclic = ?")
        params.append(int(is_cyclic))
    affinity_entries = set(manual_state().get("affinity_entries") or set())
    if has_affinity in {"0", "1"} and affinity_entries:
        placeholders = ",".join("?" for _ in affinity_entries)
        operator = "IN" if has_affinity == "1" else "NOT IN"
        where.append(f"lower(e.pdb_id) {operator} ({placeholders})")
        params.extend(sorted(affinity_entries))

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sort_map = {
        "date": "e.deposition_date",
        "res": "e.d_res_high",
        "chains": "e.chain_count",
        "peptides": "e.peptide_chain_count",
        "nonstd_chains": "e.nonstd_chain_count",
        "interfaces": "(SELECT COUNT(*) FROM interface_pairs ip WHERE ip.entry_id = e.id AND ip.interface_kind='PepPI')",
        "clusters": "(SELECT COUNT(DISTINCT ec2.entry_id) FROM entry_clusters ec2 WHERE ec2.cluster_id = e.source_hash)",
    }
    order_col = sort_map.get(sort_by.lower(), "e.deposition_date")
    order_dir = "ASC" if sort_dir.lower() == "asc" else "DESC"
    offset = (page - 1) * page_size

    with connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM entries e {where_sql}", params).fetchone()["n"]
        result_rows = conn.execute(
            f"""
            SELECT
                e.entry_key, e.pdb_id, e.entry_id, e.source_hash AS cluster_id,
                e.exptl_method, e.deposition_date, e.d_res_high, e.chain_count,
                e.peptide_chain_count, e.nonstd_chain_count, e.nonstd_mod_count,
                e.is_cyclic, e.cyclic_chain_count, e.cyclic_types_json, e.interface_pair_count,
                (
                    SELECT COUNT(*)
                    FROM interface_pairs ip
                    WHERE ip.entry_id = e.id AND ip.interface_kind='PepPI'
                ) AS peppi_interface_pair_count,
                CASE WHEN e.nonstd_chain_count > 0 THEN 1 ELSE 0 END AS has_nonstd,
                (SELECT COUNT(DISTINCT ec2.entry_id) FROM entry_clusters ec2 WHERE ec2.cluster_id = e.source_hash) AS cluster_member_count
            FROM entries e
            {where_sql}
            ORDER BY {order_col} {order_dir}, e.pdb_id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
        methods = conn.execute(
            "SELECT exptl_method, COUNT(*) AS n FROM entries GROUP BY exptl_method ORDER BY n DESC"
        ).fetchall()

    items = rows(result_rows)
    for item in items:
        item["entry_key"] = str(item.get("pdb_id") or "").lower()
        item["has_affinity"] = item["entry_key"] in affinity_entries
        item["pdb_url"] = pdb_url(item.get("pdb_id"))
        item["cyclic_types"] = parse_json_list(item.pop("cyclic_types_json", "[]"))
    return {"page": page, "page_size": page_size, "total": total, "items": items, "facets": {"methods": rows(methods)}}


@app.get("/api/entries/{entry_key}")
def entry_detail(entry_key: str) -> dict[str, Any]:
    ref = canonical_entry(entry_key)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                id, entry_key, pdb_id, source_hash AS cluster_id, entry_id, exptl_method, deposition_date,
                d_res_high, d_res_low, r_work, r_free, chain_count,
                peptide_chain_count, CASE WHEN nonstd_chain_count > 0 THEN 1 ELSE 0 END AS has_nonstd,
                nonstd_chain_count, nonstd_mod_count, is_cyclic, cyclic_chain_count, cyclic_types_json,
                interface_pair_count,
                (
                    SELECT COUNT(*)
                    FROM interface_pairs ip
                    WHERE ip.entry_id = entries.id AND ip.interface_kind='PepPI'
                ) AS peppi_interface_pair_count,
                (SELECT COUNT(DISTINCT ec2.entry_id) FROM entry_clusters ec2 WHERE ec2.cluster_id = entries.source_hash) AS cluster_member_count
            FROM entries
            WHERE lower(pdb_id) = ? OR entry_key = ?
            ORDER BY CASE WHEN lower(pdb_id) = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (ref, ref, ref),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entry not found")
        entry_id = row["id"]
        citations = conn.execute(
            "SELECT citation_key, title, journal, year, doi, pubmed FROM citations WHERE entry_id = ? ORDER BY id",
            (entry_id,),
        ).fetchall()
        files = conn.execute(
            "SELECT file_name, rel_path, file_type, size_bytes FROM entry_files WHERE entry_id = ? ORDER BY file_name",
            (entry_id,),
        ).fetchall()
        cluster_ids = conn.execute("SELECT cluster_id FROM entry_clusters WHERE entry_id = ? ORDER BY cluster_id", (entry_id,)).fetchall()
        peptide_rows = conn.execute(
            "SELECT chain_id, length, sequence, chain_type, has_nonstd, n_cyclic FROM peptide_chains WHERE entry_id = ? ORDER BY chain_id",
            (entry_id,),
        ).fetchall()
        cluster_members = conn.execute(
            """
            SELECT e.entry_key, e.pdb_id
            FROM entry_clusters ec
            JOIN entries e ON e.id = ec.entry_id
            WHERE ec.cluster_id = ?
            ORDER BY e.pdb_id ASC
            """,
            (row["cluster_id"],),
        ).fetchall()
        cluster_total = conn.execute("SELECT COUNT(DISTINCT cluster_id) AS n FROM entry_clusters").fetchone()["n"]
        update_date = db_update_date(conn)

    payload = row_dict(row) or {}
    payload["entry_key"] = str(payload.get("pdb_id") or "").lower()
    payload["pdb_url"] = pdb_url(payload.get("pdb_id"))
    payload["cyclic_types"] = parse_json_list(payload.pop("cyclic_types_json", "[]"))
    payload["db_update_date"] = update_date
    payload["citations"] = rows(citations)
    payload["files"] = rows(files)
    payload["cluster_ids"] = [str(x["cluster_id"]) for x in cluster_ids]
    payload["cluster_total"] = cluster_total
    payload["cluster_members"] = rows(cluster_members)
    for member in payload["cluster_members"]:
        member["entry_key"] = str(member.get("pdb_id") or "").lower()

    manual = manual_state()
    target_by_id = manual.get("targets_by_id") or {}
    peps_for_entry = [
        rec for rec in (manual.get("peps_by_key") or {}).values() if str(rec.get("entry_key", "")) == payload["entry_key"]
    ]
    peps_for_entry.sort(key=lambda x: str(x.get("pair_id", "")))
    ligand_by_id = {str(x["chain_id"]): dict(x) for x in peptide_rows}
    blocks = []
    used_targets: dict[str, dict[str, Any]] = {}
    for item in peps_for_entry:
        chain_ids = [str(x).strip() for x in (item.get("chain_ids") or []) if str(x).strip()]
        target_ids = [str(x).strip() for x in (item.get("target_tags") or []) if str(x).strip()]
        linked = [target_by_id[x] for x in target_ids if x in target_by_id]
        for target in linked:
            used_targets[str(target.get("target_id", ""))] = target
        chain_lengths = [ligand_by_id[x].get("length") for x in chain_ids if x in ligand_by_id]
        chain_types = [ligand_by_id[x].get("chain_type") for x in chain_ids if x in ligand_by_id]
        blocks.append(
            {
                "ligand_id": item.get("ligand_id") or item.get("pair_id") or (chain_ids[0] if chain_ids else ""),
                "ligand_chain_ids": chain_ids,
                "ligand_chain_id": ",".join(chain_ids),
                "ligand_length": chain_lengths[0] if chain_lengths else item.get("pep_length"),
                "ligand_kind": ",".join([str(x) for x in chain_types if x]) or "-",
                "function_text": item.get("function_text", ""),
                "notes": item.get("notes", ""),
                "affinity_text": item.get("affinity_text", ""),
                "has_affinity": item.get("has_affinity"),
                "target_tags": target_ids,
                "linked_targets": linked,
                "status": item.get("status", "missing"),
                "updated_at": item.get("updated_at", ""),
                "source": "ligand-group",
            }
        )
    payload["pair_annotations"] = peps_for_entry
    payload["target_cards"] = sorted(used_targets.values(), key=lambda x: str(x.get("target_id", "")))
    payload["peptide_functions"] = blocks
    payload["pep_ligand_annotations"] = blocks
    payload["function_blocks"] = blocks
    payload["function_annotation"] = None
    return payload


@app.get("/api/entries/{entry_key}/annotations")
def entry_annotations(entry_key: str) -> dict[str, Any]:
    with connect() as conn:
        entry = get_entry_min(conn, entry_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        chains = conn.execute(
            """
            SELECT
                chain_id, chain_type, length, sequence, has_nonstd,
                mod_has_linker, mod_positions_json, mod_types_json,
                cyclic_head2tail, cyclic_head2side, cyclic_side2tail, cyclic_side2side,
                cyclic_has_cyc_linker, n_ss, n_nc, n_cyclic, n_cyclic_nonstd
            FROM peptide_chains
            WHERE entry_id = ?
            ORDER BY chain_id
            """,
            (entry["id"],),
        ).fetchall()
        nonpoly = conn.execute("SELECT entity_id, comp_id, name FROM entry_nonpoly WHERE entry_id = ? ORDER BY id", (entry["id"],)).fetchall()
        connect_rows = conn.execute(
            """
            SELECT connect_id, connect_type, leaving_atom,
                   ptnr1_chain, ptnr1_comp, ptnr1_seq, ptnr1_atom,
                   ptnr2_chain, ptnr2_comp, ptnr2_seq, ptnr2_atom
            FROM entry_connect
            WHERE entry_id = ?
            ORDER BY id
            """,
            (entry["id"],),
        ).fetchall()
    chain_items = rows(chains)
    for chain in chain_items:
        chain["mod_positions"] = parse_json_list(chain.pop("mod_positions_json", "[]"))
        chain["mod_types"] = parse_json_list(chain.pop("mod_types_json", "[]"))
    return {"entry_key": str(entry["pdb_id"]).lower(), "pdb_id": entry["pdb_id"], "chains": chain_items, "nonpoly": rows(nonpoly), "connect": rows(connect_rows)}


@app.get("/api/entries/{entry_key}/interfaces")
def entry_interfaces(entry_key: str) -> dict[str, Any]:
    with connect() as conn:
        entry = get_entry_min(conn, entry_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        pair_rows = conn.execute(
            """
            SELECT pair_id, chain1_id, chain2_id, chain1_len, chain2_len,
                   interface_kind, interface_residues1, interface_residues2
            FROM interface_pairs
            WHERE entry_id = ?
            ORDER BY pair_id
            """,
            (entry["id"],),
        ).fetchall()
    return {"entry_key": str(entry["pdb_id"]).lower(), "pdb_id": entry["pdb_id"], "pairs": rows(pair_rows)}


@app.get("/api/entries/{entry_key}/interfaces/{pair_id}")
def entry_interface_detail(entry_key: str, pair_id: str) -> dict[str, Any]:
    with connect() as conn:
        entry = get_entry_min(conn, entry_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        row = conn.execute(
            """
            SELECT pair_id, chain1_id, chain2_id, chain1_sequence, chain2_sequence,
                   interface_mask1_sequence, interface_mask2_sequence, ss1, ss2
            FROM interface_details
            WHERE entry_id = ? AND pair_id = ?
            LIMIT 1
            """,
            (entry["id"], pair_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Interface pair not found")
    return dict(row)


@app.get("/api/entries/{entry_key}/structure")
def entry_structure(entry_key: str) -> dict[str, Any]:
    ref = canonical_entry(entry_key)
    with connect() as conn:
        row = conn.execute(
            """
            SELECT e.pdb_id, ef.file_name
            FROM entries e
            JOIN entry_files ef ON ef.entry_id = e.id
            WHERE (lower(e.pdb_id) = ? OR e.entry_key = ?) AND ef.file_type = 'cif'
            ORDER BY ef.file_name
            LIMIT 1
            """,
            (ref, ref),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Structure not found")
    public_key = str(row["pdb_id"]).lower()
    file_name = row["file_name"]
    return {
        "entry_key": public_key,
        "pdb_id": row["pdb_id"],
        "format": "cif",
        "download_url": f"/api/download/{public_key}/{urllib.parse.quote(file_name)}",
        "pdb_url": pdb_url(row["pdb_id"]),
    }


@app.get("/api/download/{entry_key}.zip")
def download_zip(entry_key: str, request: Request) -> StreamingResponse:
    check_download_rate_limit(request)
    with connect() as conn:
        entry = get_entry_min(conn, entry_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        file_rows = conn.execute(
            """
            SELECT ef.file_name, ef.rel_path, e.pdb_id
            FROM entry_files ef
            JOIN entries e ON e.id = ef.entry_id
            WHERE e.id = ?
            ORDER BY ef.file_name
            """,
            (entry["id"],),
        ).fetchall()
    if not file_rows:
        raise HTTPException(status_code=404, detail="Entry not found")

    root = DATASET_ROOT.resolve()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_row in file_rows:
            src = (DATASET_ROOT / file_row["rel_path"]).resolve()
            if src.is_file() and (src == root or root in src.parents):
                zf.write(src, arcname=public_download_name(file_row["pdb_id"], file_row["file_name"]))
        pdb_id = file_rows[0]["pdb_id"]
        function_data = json.dumps(function_payload(str(pdb_id).lower()), ensure_ascii=False, indent=2) + "\n"
        zf.writestr(f"{str(pdb_id).lower()}_function.json", function_data)
    buffer.seek(0)
    pdb_id = file_rows[0]["pdb_id"]
    record_usage(request, "download")
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pdb_id}.zip"'},
    )


def function_json_response(entry_key: str, request: Request) -> Response:
    payload = function_payload(entry_key)
    public_key = str(payload.get("pdb_id") or entry_key).lower()
    record_usage(request, "download")
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{public_key}_function.json"'},
    )


@app.get("/api/download/{entry_key}/function.json")
def download_function_json(entry_key: str, request: Request) -> Response:
    check_download_rate_limit(request)
    return function_json_response(entry_key, request)


@app.get("/api/download/{entry_key}/{filename}")
def download_file(entry_key: str, filename: str, request: Request) -> Response:
    check_download_rate_limit(request)
    with connect() as conn:
        entry = get_entry_min(conn, entry_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        if filename.lower() == f"{str(entry['pdb_id']).lower()}_function.json":
            return function_json_response(entry_key, request)
        source_name = source_file_name_from_public(entry["pdb_id"], filename)
        path, _ = resolve_file(conn, entry_key, source_name)
    media_type = "chemical/x-cif" if source_name.lower().endswith(".cif") else "application/octet-stream"
    record_usage(request, "download")
    return FileResponse(path, media_type=media_type, filename=public_download_name(entry["pdb_id"], source_name))


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    @app.get("/")
    def no_static() -> JSONResponse:
        return JSONResponse({"error": f"Static directory not found: {STATIC_DIR}"}, status_code=503)
