"""
SAP Directory Manager — Standardized CSV file storage and retrieval.

Convention:  imports/{TENANT_NAME}/{ERP_SYSTEM}/{YYYY-MM-DD}/
             imports/{TENANT_NAME}/{ERP_SYSTEM}/latest -> {YYYY-MM-DD}  (symlink)

Each extraction date directory contains:
  - One CSV per SAP table (e.g., MARA.csv, EKKO.csv)
  - MANIFEST.json with extraction metadata, row counts, checksums

Supports:
  - Multiple tenants, multiple ERP sources, multiple extraction dates
  - Automatic symlink management (latest points to newest)
  - Retention policy (keep N most recent snapshots)
  - CSV filename normalization (strip suffixes like _materials)
"""

import hashlib
import json
import logging
import os
import re
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models.sap_staging import SAP_TABLE_REGISTRY, SAPDataCategory

logger = logging.getLogger(__name__)

# Base imports directory — overridable via env or tenant config
SAP_IMPORTS_BASE = os.getenv("SAP_IMPORTS_DIR", "/app/imports")


def get_tenant_import_base(tenant) -> str:
    """Get the import base directory for a tenant.

    Priority: tenant.import_base_dir > default ({IMPORTS_BASE}/{tenant_name}/CSV_Generic)
    """
    if tenant and getattr(tenant, 'import_base_dir', None):
        return tenant.import_base_dir
    tenant_name = getattr(tenant, 'name', 'default') if tenant else 'default'
    return str(Path(SAP_IMPORTS_BASE) / _sanitize_name(tenant_name) / 'CSV_Generic')


def _sanitize_name(name: str) -> str:
    """Convert a tenant/ERP name to a filesystem-safe directory name."""
    return re.sub(r'[^\w\-.]', '_', name).strip('_')


def get_extraction_dir(
    tenant_name: str,
    erp_system: str,
    extraction_date: Optional[date] = None,
) -> Path:
    """Build the canonical path for an extraction directory.

    Returns: imports/{TENANT_NAME}/{ERP_SYSTEM}/{YYYY-MM-DD}/
    """
    if extraction_date is None:
        extraction_date = date.today()
    return Path(SAP_IMPORTS_BASE) / _sanitize_name(tenant_name) / _sanitize_name(erp_system) / extraction_date.isoformat()


def get_latest_dir(tenant_name: str, erp_system: str) -> Path:
    """Return the 'latest' symlink path."""
    return Path(SAP_IMPORTS_BASE) / _sanitize_name(tenant_name) / _sanitize_name(erp_system) / "latest"


def ensure_extraction_dir(
    tenant_name: str,
    erp_system: str,
    extraction_date: Optional[date] = None,
) -> Path:
    """Create the extraction directory if it doesn't exist. Returns the path."""
    path = get_extraction_dir(tenant_name, erp_system, extraction_date)
    path.mkdir(parents=True, exist_ok=True)
    return path


def update_latest_symlink(tenant_name: str, erp_system: str, extraction_date: date) -> None:
    """Point the 'latest' symlink to the given extraction date."""
    latest = get_latest_dir(tenant_name, erp_system)
    target = extraction_date.isoformat()

    # Remove existing symlink or directory
    if latest.is_symlink() or latest.exists():
        latest.unlink(missing_ok=True)

    latest.symlink_to(target)
    logger.info("Updated latest symlink: %s -> %s", latest, target)


def list_extractions(tenant_name: str, erp_system: str) -> List[date]:
    """List all extraction dates for a tenant/ERP, newest first."""
    base = Path(SAP_IMPORTS_BASE) / _sanitize_name(tenant_name) / _sanitize_name(erp_system)
    if not base.exists():
        return []

    dates = []
    for entry in base.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            try:
                dates.append(date.fromisoformat(entry.name))
            except ValueError:
                continue
    return sorted(dates, reverse=True)


def enforce_retention(
    tenant_name: str,
    erp_system: str,
    max_snapshots: int = 5,
) -> List[date]:
    """Delete extraction directories beyond the retention limit.

    Returns list of deleted dates.
    """
    dates = list_extractions(tenant_name, erp_system)
    if len(dates) <= max_snapshots:
        return []

    to_delete = dates[max_snapshots:]
    deleted = []
    base = Path(SAP_IMPORTS_BASE) / _sanitize_name(tenant_name) / _sanitize_name(erp_system)

    for d in to_delete:
        dir_path = base / d.isoformat()
        if dir_path.exists():
            shutil.rmtree(dir_path)
            deleted.append(d)
            logger.info("Retention: deleted extraction %s/%s/%s", tenant_name, erp_system, d)

    return deleted


def normalize_csv_filename(filename: str) -> str:
    """Normalize CSV filenames to standard {TABLE}.csv format.

    Handles: MARA_materials.csv -> MARA.csv
             MAKT_descriptions.csv -> MAKT.csv
             KNA1_customers.csv -> KNA1.csv
    """
    stem = Path(filename).stem
    # Check if the stem contains an underscore after a known SAP table name
    for table_name in SAP_TABLE_REGISTRY:
        if stem.upper().startswith(table_name):
            return f"{table_name}.csv"
    # If not in registry, take everything before the first underscore
    parts = stem.split('_', 1)
    return f"{parts[0].upper()}.csv"


def write_manifest(
    extraction_dir: Path,
    *,
    tenant_id: int,
    connection_id: Optional[int],
    extraction_date: date,
    source_method: str,
    erp_system: str,
    table_stats: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Write MANIFEST.json to the extraction directory.

    Args:
        table_stats: {"MARA": {"rows": 936, "columns": 15, "md5": "abc..."}}
    """
    # Aggregate by category
    category_counts = {}
    for table_name, stats in table_stats.items():
        reg = SAP_TABLE_REGISTRY.get(table_name, {})
        cat = reg.get("category", "unknown")
        if cat not in category_counts:
            category_counts[cat] = {"tables": 0, "total_rows": 0}
        category_counts[cat]["tables"] += 1
        category_counts[cat]["total_rows"] += stats.get("rows", 0)

    manifest = {
        "extraction_id": None,  # Set by caller after DB insert
        "tenant_id": tenant_id,
        "connection_id": connection_id,
        "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
        "extraction_date": extraction_date.isoformat(),
        "source_method": source_method,
        "erp_system": erp_system,
        "categories": category_counts,
        "tables": table_stats,
    }

    manifest_path = extraction_dir / "MANIFEST.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def read_manifest(extraction_dir: Path) -> Optional[Dict[str, Any]]:
    """Read MANIFEST.json from an extraction directory."""
    manifest_path = extraction_dir / "MANIFEST.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path) as f:
        return json.load(f)


def compute_file_md5(filepath: Path) -> str:
    """Compute MD5 hash of a CSV file."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_csv_directory(directory: Path) -> Dict[str, Dict[str, Any]]:
    """Scan a directory for CSV files and return stats per table.

    Returns: {"MARA": {"rows": 936, "columns": 15, "md5": "abc...", "filename": "MARA.csv"}}
    """
    stats = {}
    for csv_file in sorted(directory.glob("*.csv")):
        normalized = normalize_csv_filename(csv_file.name)
        table_name = Path(normalized).stem

        # Count rows and columns
        with open(csv_file) as f:
            header = f.readline().strip()
            columns = len(header.split(",")) if header else 0
            rows = sum(1 for _ in f)  # excludes header

        stats[table_name] = {
            "rows": rows,
            "columns": columns,
            "md5": compute_file_md5(csv_file),
            "filename": csv_file.name,
        }

    return stats


def migrate_legacy_directory(
    source_dir: Path,
    tenant_name: str,
    erp_system: str,
    extraction_date: date,
    normalize_filenames: bool = True,
) -> Path:
    """Migrate a legacy CSV directory to the new convention.

    Copies (not moves) files to: imports/{tenant}/{erp}/{date}/
    Optionally normalizes filenames (strips _descriptions suffixes).
    Updates the 'latest' symlink.

    Returns the new directory path.
    """
    target = ensure_extraction_dir(tenant_name, erp_system, extraction_date)

    for csv_file in source_dir.glob("*.csv"):
        dest_name = normalize_csv_filename(csv_file.name) if normalize_filenames else csv_file.name
        dest_path = target / dest_name
        if not dest_path.exists():
            shutil.copy2(csv_file, dest_path)

    # Also copy MANIFEST.json if it exists
    src_manifest = source_dir / "MANIFEST.json"
    if src_manifest.exists():
        shutil.copy2(src_manifest, target / "MANIFEST.json")

    update_latest_symlink(tenant_name, erp_system, extraction_date)

    logger.info(
        "Migrated %s -> %s (%d CSV files)",
        source_dir, target,
        len(list(target.glob("*.csv"))),
    )
    return target
