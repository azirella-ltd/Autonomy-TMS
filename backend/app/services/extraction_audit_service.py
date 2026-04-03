"""
Extraction Audit Service

Tracks per-table extraction status for tenant admin visibility.
Every ERP config builder records what was extracted from the source ERP,
what was empty, what was derived from alternative sources, and what was skipped.

The audit report is persisted on the ``config_provisioning_status.extraction_audit``
JSON column and served via ``GET /provisioning/audit/{config_id}``.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ExtractionAuditReport:
    """Tracks per-table extraction status for tenant admin visibility.

    Each table/entity processed during a config build is recorded with one of
    four statuses:
      - ``extracted`` — rows were present in the ERP staging data
      - ``empty``     — table existed but contained 0 rows
      - ``derived``   — data was computed from alternative ERP tables because
                         the primary table was empty
      - ``skipped``   — table was intentionally not processed (e.g. not
                         applicable to this ERP type)

    Usage in a config builder::

        audit = ExtractionAuditReport(config_id=42, erp_type="SAP")
        audit.record_extracted("MARA", rows=12345)
        audit.record_empty("MSEG", note="No goods movement data")
        audit.record_derived(
            "shipments", rows=1428,
            source="EKBE (PO history) + LIKP (deliveries)",
            note="MSEG was empty — derived 1,428 goods_receipt records from EKBE",
        )
        await audit.save(db)
    """

    def __init__(self, config_id: int, erp_type: str):
        self.config_id = config_id
        self.erp_type = erp_type
        self.tables: Dict[str, Dict[str, Any]] = {}
        self.created_at = datetime.utcnow().isoformat()

    # ── Recording methods ──────────────────────────────────────────────

    def record_extracted(self, table: str, rows: int, note: str = ""):
        """Record a table that was successfully extracted with data."""
        self.tables[table] = {
            "status": "extracted",
            "rows": rows,
            "source": "erp",
            "note": note,
        }

    def record_empty(self, table: str, note: str = ""):
        """Record a table that was present but contained 0 rows."""
        self.tables[table] = {
            "status": "empty",
            "rows": 0,
            "source": "erp",
            "note": note,
        }

    def record_derived(self, table: str, rows: int, source: str, note: str):
        """Record data that was derived from alternative sources.

        Args:
            table: The target entity/table that was populated.
            rows: Number of records created via derivation.
            source: Which ERP tables the data was derived from.
            note: Human-readable description of the derivation logic.
        """
        self.tables[table] = {
            "status": "derived",
            "rows": rows,
            "source": source,
            "note": note,
        }

    def record_skipped(self, table: str, reason: str):
        """Record a table that was intentionally skipped."""
        self.tables[table] = {
            "status": "skipped",
            "rows": 0,
            "source": "",
            "note": reason,
        }

    # ── Summarisation ──────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return {
            "config_id": self.config_id,
            "erp_type": self.erp_type,
            "created_at": self.created_at,
            "tables": self.tables,
            "summary": {
                "extracted": sum(
                    1 for t in self.tables.values() if t["status"] == "extracted"
                ),
                "derived": sum(
                    1 for t in self.tables.values() if t["status"] == "derived"
                ),
                "empty": sum(
                    1 for t in self.tables.values() if t["status"] == "empty"
                ),
                "skipped": sum(
                    1 for t in self.tables.values() if t["status"] == "skipped"
                ),
                "total_rows_extracted": sum(
                    t["rows"]
                    for t in self.tables.values()
                    if t["status"] == "extracted"
                ),
                "total_rows_derived": sum(
                    t["rows"]
                    for t in self.tables.values()
                    if t["status"] == "derived"
                ),
            },
        }

    # ── Persistence ────────────────────────────────────────────────────

    async def save(self, db: AsyncSession) -> None:
        """Persist to ``config_provisioning_status.extraction_audit`` JSON column.

        Creates the provisioning status row if it does not exist, then
        sets the ``extraction_audit`` column to the full audit JSON.
        """
        audit_json = json.dumps(self.to_dict())

        # Upsert: create the provisioning status row if missing
        await db.execute(
            sql_text(
                "INSERT INTO config_provisioning_status (config_id, extraction_audit) "
                "VALUES (:cid, CAST(:audit AS jsonb)) "
                "ON CONFLICT (config_id) DO UPDATE "
                "SET extraction_audit = CAST(:audit AS jsonb)"
            ),
            {"cid": self.config_id, "audit": audit_json},
        )
        await db.flush()
        logger.info(
            "Saved extraction audit for config %d (%s): %d tables tracked",
            self.config_id,
            self.erp_type,
            len(self.tables),
        )


async def get_extraction_audit(
    db: AsyncSession, config_id: int
) -> Optional[Dict[str, Any]]:
    """Load the extraction audit report from the DB.

    Returns:
        The audit dict if found, else ``None``.
    """
    result = await db.execute(
        sql_text(
            "SELECT extraction_audit FROM config_provisioning_status "
            "WHERE config_id = :cid"
        ),
        {"cid": config_id},
    )
    row = result.fetchone()
    if row and row[0]:
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    return None
