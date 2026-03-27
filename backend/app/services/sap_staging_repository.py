"""
SAP Staging Repository — Write-through layer for SAP data extraction.

All SAP data (from any source: CSV, HANA DB, RFC, OData) flows through
the sap_staging schema before being mapped to AWS SC entity tables.

Flow:
  1. start_extraction() → creates extraction_runs header
  2. stage_table() → bulk-inserts rows for one SAP table
  3. complete_extraction() → finalizes with counts and warnings
  4. get_staged_data() → returns DataFrames for the builder (replaces CSV loading)

The staging tables provide:
  - Audit trail (every row ever extracted)
  - Delta detection (row_hash comparison between extractions)
  - Schema drift detection (column tracking)
  - Re-mappable (can rebuild entity tables without re-extracting from SAP)
"""

import hashlib
import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sap_staging import (
    SAP_TABLE_REGISTRY,
    get_table_category,
    get_table_keys,
)

logger = logging.getLogger(__name__)


class SAPStagingRepository:
    """Read/write access to the sap_staging schema."""

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Extraction lifecycle
    # ------------------------------------------------------------------

    async def start_extraction(
        self,
        erp_variant: str,
        source_method: str,
        connection_id: Optional[int] = None,
        extraction_date: Optional[date] = None,
    ) -> UUID:
        """Create an extraction_runs header. Returns the extraction_id."""
        ext_date = extraction_date or date.today()
        result = await self.db.execute(
            text("""
                INSERT INTO sap_staging.extraction_runs
                    (tenant_id, connection_id, erp_variant, extraction_date,
                     source_method, status, started_at)
                VALUES (:tid, :cid, :variant, :edate, :method, 'running', NOW())
                RETURNING id
            """),
            {
                "tid": self.tenant_id,
                "cid": connection_id,
                "variant": erp_variant,
                "edate": ext_date,
                "method": source_method,
            },
        )
        row = result.fetchone()
        extraction_id = row[0]
        logger.info(
            "Started extraction %s: tenant=%d variant=%s method=%s",
            extraction_id, self.tenant_id, erp_variant, source_method,
        )
        return extraction_id

    async def stage_table(
        self,
        extraction_id: UUID,
        sap_table: str,
        df: pd.DataFrame,
    ) -> int:
        """Bulk-insert rows from a DataFrame into sap_staging.rows.

        Returns the number of rows inserted.
        """
        if df.empty:
            return 0

        category = get_table_category(sap_table)
        key_fields = get_table_keys(sap_table)

        if not category:
            logger.warning(
                "Table '%s' not found in SAP_TABLE_REGISTRY — staging with empty category. "
                "Add it to backend/app/models/sap_staging.py to enable proper categorization.",
                sap_table,
            )

        # Build rows for bulk insert
        rows_to_insert = []
        for _, row in df.iterrows():
            row_dict = {k: _serialize(v) for k, v in row.items()}
            row_json = json.dumps(row_dict, default=str, sort_keys=True)
            row_hash = hashlib.md5(row_json.encode()).hexdigest()

            bkey_parts = [str(row_dict.get(k, "")).strip() for k in key_fields if k in row_dict]
            business_key = "|".join(bkey_parts) if bkey_parts else None

            rows_to_insert.append((
                str(extraction_id), self.tenant_id, sap_table, category,
                row_json, row_hash, business_key,
            ))

        # Bulk insert using raw COPY-style multi-row VALUES
        inserted = 0
        batch_size = 2000
        for i in range(0, len(rows_to_insert), batch_size):
            batch = rows_to_insert[i:i + batch_size]
            if not batch:
                break
            # Build multi-row VALUES clause
            placeholders = []
            params = {}
            for j, (eid, tid, tbl, cat, rdata, rhash, bkey) in enumerate(batch):
                p = f"_{j}"
                placeholders.append(
                    f"(CAST(:eid{p} AS uuid), :tid{p}, :tbl{p}, :cat{p}, "
                    f"CAST(:rd{p} AS jsonb), :rh{p}, :bk{p})"
                )
                params[f"eid{p}"] = eid
                params[f"tid{p}"] = tid
                params[f"tbl{p}"] = tbl
                params[f"cat{p}"] = cat
                params[f"rd{p}"] = rdata
                params[f"rh{p}"] = rhash
                params[f"bk{p}"] = bkey

            sql = (
                "INSERT INTO sap_staging.rows "
                "(extraction_id, tenant_id, sap_table, data_category, "
                "row_data, row_hash, business_key) VALUES "
                + ", ".join(placeholders)
            )
            await self.db.execute(text(sql), params)
            inserted += len(batch)

        # Update schema tracking
        columns = list(df.columns)
        await self.db.execute(
            text("""
                INSERT INTO sap_staging.table_schemas
                    (tenant_id, sap_table, columns, key_fields, data_category, row_count, last_seen)
                VALUES (:tid, :tbl, CAST(:cols AS jsonb), CAST(:keys AS jsonb), :cat, :cnt, NOW())
                ON CONFLICT (tenant_id, sap_table)
                DO UPDATE SET columns = EXCLUDED.columns, row_count = EXCLUDED.row_count,
                              last_seen = NOW()
            """),
            {
                "tid": self.tenant_id,
                "tbl": sap_table,
                "cols": json.dumps(columns),
                "keys": json.dumps(key_fields),
                "cat": category,
                "cnt": len(df),
            },
        )

        logger.info("Staged %s: %d rows (category=%s)", sap_table, inserted, category)
        return inserted

    async def complete_extraction(
        self,
        extraction_id: UUID,
        config_id: Optional[int] = None,
        build_summary: Optional[Dict] = None,
        warnings: Optional[List[Dict]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Finalize an extraction run with counts and status."""
        # Count rows by category
        counts = await self.db.execute(
            text("""
                SELECT data_category, COUNT(DISTINCT sap_table) AS tables, COUNT(*) AS rows
                FROM sap_staging.rows
                WHERE extraction_id = :eid
                GROUP BY data_category
            """),
            {"eid": str(extraction_id)},
        )
        cat_counts = {r[0]: {"tables": r[1], "rows": r[2]} for r in counts.fetchall()}

        # Detect empty/sparse tables
        table_warnings = warnings or []
        table_counts = await self.db.execute(
            text("""
                SELECT sap_table, COUNT(*) AS cnt
                FROM sap_staging.rows WHERE extraction_id = :eid
                GROUP BY sap_table
            """),
            {"eid": str(extraction_id)},
        )
        for row in table_counts.fetchall():
            if row[1] == 0:
                table_warnings.append({"table": row[0], "issue": "empty", "rows": 0})
            elif row[1] < 5:
                table_warnings.append({"table": row[0], "issue": "sparse", "rows": row[1]})

        status = "failed" if error else "completed"

        await self.db.execute(
            text("""
                UPDATE sap_staging.extraction_runs SET
                    status = :status,
                    completed_at = NOW(),
                    config_id = :cid,
                    build_summary = CAST(:summary AS jsonb),
                    master_tables = :mt, master_rows = :mr,
                    transaction_tables = :tt, transaction_rows = :tr,
                    cdc_tables = :ct, cdc_rows = :cr,
                    warnings = CAST(:warnings AS jsonb),
                    errors = CAST(:errors AS jsonb)
                WHERE id = :eid
            """),
            {
                "status": status,
                "cid": config_id,
                "summary": json.dumps(build_summary) if build_summary else None,
                "mt": cat_counts.get("master", {}).get("tables", 0),
                "mr": cat_counts.get("master", {}).get("rows", 0),
                "tt": cat_counts.get("transaction", {}).get("tables", 0),
                "tr": cat_counts.get("transaction", {}).get("rows", 0),
                "ct": cat_counts.get("cdc", {}).get("tables", 0),
                "cr": cat_counts.get("cdc", {}).get("rows", 0),
                "warnings": json.dumps(table_warnings) if table_warnings else None,
                "errors": json.dumps({"message": error}) if error else None,
                "eid": str(extraction_id),
            },
        )

    # ------------------------------------------------------------------
    # Read staged data (replaces CSV loading for the builder)
    # ------------------------------------------------------------------

    async def get_staged_data(
        self,
        extraction_id: UUID,
    ) -> Dict[str, pd.DataFrame]:
        """Load staged data as a dict of DataFrames (same format as CSV loader).

        This replaces the CSV file reading — the builder gets its data from
        PostgreSQL instead of the filesystem.
        """
        # Get distinct tables in this extraction
        tables_result = await self.db.execute(
            text("""
                SELECT DISTINCT sap_table FROM sap_staging.rows
                WHERE extraction_id = :eid
            """),
            {"eid": str(extraction_id)},
        )
        table_names = [r[0] for r in tables_result.fetchall()]

        sap_data: Dict[str, pd.DataFrame] = {}
        for table_name in table_names:
            rows_result = await self.db.execute(
                text("""
                    SELECT row_data FROM sap_staging.rows
                    WHERE extraction_id = :eid AND sap_table = :tbl
                    ORDER BY id
                """),
                {"eid": str(extraction_id), "tbl": table_name},
            )
            rows = [r[0] for r in rows_result.fetchall()]
            if rows:
                sap_data[table_name] = pd.DataFrame(rows)

        logger.info(
            "Loaded %d tables from staging for extraction %s",
            len(sap_data), extraction_id,
        )
        return sap_data

    # ------------------------------------------------------------------
    # Delta detection
    # ------------------------------------------------------------------

    async def compute_delta(
        self,
        extraction_id: UUID,
        previous_extraction_id: UUID,
    ) -> Dict[str, Dict[str, int]]:
        """Compare two extractions and return delta per table.

        Returns: {"MARA": {"new": 12, "changed": 5, "deleted": 0, "unchanged": 919}}
        """
        delta = {}
        # Get tables in current extraction
        tables = await self.db.execute(
            text("SELECT DISTINCT sap_table FROM sap_staging.rows WHERE extraction_id = :eid"),
            {"eid": str(extraction_id)},
        )
        for (table_name,) in tables.fetchall():
            result = await self.db.execute(
                text("""
                    WITH curr AS (
                        SELECT business_key, row_hash FROM sap_staging.rows
                        WHERE extraction_id = :curr AND sap_table = :tbl AND business_key IS NOT NULL
                    ), prev AS (
                        SELECT business_key, row_hash FROM sap_staging.rows
                        WHERE extraction_id = :prev AND sap_table = :tbl AND business_key IS NOT NULL
                    )
                    SELECT
                        COUNT(*) FILTER (WHERE prev.business_key IS NULL) AS new_rows,
                        COUNT(*) FILTER (WHERE curr.row_hash != prev.row_hash AND prev.business_key IS NOT NULL) AS changed,
                        (SELECT COUNT(*) FROM prev p2 WHERE NOT EXISTS (
                            SELECT 1 FROM curr c2 WHERE c2.business_key = p2.business_key
                        )) AS deleted,
                        COUNT(*) FILTER (WHERE curr.row_hash = prev.row_hash) AS unchanged
                    FROM curr
                    LEFT JOIN prev ON curr.business_key = prev.business_key
                """),
                {"curr": str(extraction_id), "prev": str(previous_extraction_id), "tbl": table_name},
            )
            row = result.fetchone()
            delta[table_name] = {
                "new": row[0] or 0, "changed": row[1] or 0,
                "deleted": row[2] or 0, "unchanged": row[3] or 0,
            }
        return delta

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    async def enforce_retention(self, max_extractions: int = 5) -> int:
        """Delete old extractions beyond the retention limit. Returns count deleted."""
        result = await self.db.execute(
            text("""
                WITH ranked AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY extraction_date DESC, created_at DESC) AS rn
                    FROM sap_staging.extraction_runs
                    WHERE tenant_id = :tid
                )
                DELETE FROM sap_staging.extraction_runs
                WHERE id IN (SELECT id FROM ranked WHERE rn > :max)
                RETURNING id
            """),
            {"tid": self.tenant_id, "max": max_extractions},
        )
        deleted = len(result.fetchall())
        if deleted:
            logger.info("Retention: deleted %d old extractions for tenant %d", deleted, self.tenant_id)
        return deleted


def _serialize(v) -> Any:
    """Convert pandas/numpy types to JSON-serializable Python types."""
    if pd.isna(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v
