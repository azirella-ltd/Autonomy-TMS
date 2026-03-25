"""
Demo Date Shift Service

Shifts all date/timestamp columns forward for demo tenants to keep demo data
fresh relative to the current date. Designed to run daily at 04:00 UTC via
APScheduler, or manually via API.

Design:
- Uses raw SQL with INTERVAL for performance (100K+ rows across many tables)
- Wraps all updates in a single transaction
- Only shifts if gap >= 1 day since last shift
- Handles missing columns/tables gracefully (try/except per table)
- Logs shift details to demo_date_shift_log

Tables affected:
  Config-scoped (config_id): forecast, supply_plan, inv_level, inv_policy,
      inventory_projection, sourcing_rules, and all 11 powell_*_decisions tables
  Company-scoped (company_id LIKE 'UF_CORP%'): fulfillment_order, purchase_order,
      inbound_order, shipment, backorder, maintenance_order, turnaround_order
  Tenant-scoped (tenant_id): executive_briefings, decision_stream_digests
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Table definitions: (table_name, filter_type, [columns])
#   filter_type: "config" => WHERE config_id = :config_id
#                "company" => WHERE company_id LIKE 'UF_CORP%'
#                "tenant" => WHERE tenant_id = :tenant_id
# ---------------------------------------------------------------------------

_CONFIG_SCOPED_TABLES = [
    # AWS SC Planning tables
    ("forecast", "config", [
        "forecast_date",
        "created_dttm",
        "source_update_dttm",
    ]),
    ("supply_plan", "config", [
        "plan_date",
        "planned_order_date",
        "planned_receipt_date",
        "created_dttm",
        "source_update_dttm",
    ]),
    ("inv_level", "config", [
        "inventory_date",
        "lot_expiration_date",
        "source_update_dttm",
    ]),
    ("inv_policy", "config", [
        "eff_start_date",
        "eff_end_date",
        "source_update_dttm",
    ]),
    ("inventory_projection", "config", [
        "period_start",
        "period_end",
        "created_at",
    ]),
    ("sourcing_rules", "config", [
        "eff_start_date",
        "eff_end_date",
        "source_update_dttm",
    ]),
]

_COMPANY_SCOPED_TABLES = [
    ("fulfillment_order", "company", [
        "created_date",
        "promised_date",
        "allocated_date",
        "pick_date",
        "pack_date",
        "ship_date",
        "delivery_date",
        "created_at",
        "updated_at",
    ]),
    ("purchase_order", "company", [
        "order_date",
        "requested_delivery_date",
        "promised_delivery_date",
        "actual_delivery_date",
        "source_update_dttm",
        "created_at",
        "updated_at",
        "approved_at",
        "sent_at",
        "acknowledged_at",
        "received_at",
    ]),
    ("inbound_order", "company", [
        "order_date",
        "requested_delivery_date",
        "promised_delivery_date",
        "actual_delivery_date",
        "source_update_dttm",
        "created_at",
        "updated_at",
    ]),
    ("shipment", "company", [
        "ship_date",
        "expected_delivery_date",
        "actual_delivery_date",
        "last_tracking_update",
        "source_update_dttm",
        "created_at",
    ]),
    ("backorder", "company", [
        "requested_delivery_date",
        "expected_fill_date",
        "created_date",
        "allocated_date",
        "fulfilled_date",
        "closed_date",
        "created_at",
        "updated_at",
    ]),
    ("maintenance_order", "company", [
        "order_date",
        "scheduled_start_date",
        "scheduled_completion_date",
        "actual_start_date",
        "actual_completion_date",
        "last_maintenance_date",
        "next_maintenance_due",
        "source_update_dttm",
        "created_at",
        "updated_at",
    ]),
    ("turnaround_order", "company", [
        "order_date",
        "return_requested_date",
        "return_approved_date",
        "pickup_scheduled_date",
        "pickup_actual_date",
        "received_date",
        "inspection_date",
        "refurbishment_start_date",
        "refurbishment_completion_date",
        "disposition_date",
        "source_update_dttm",
        "created_at",
        "updated_at",
        "approved_at",
        "received_at",
        "inspected_at",
        "disposed_at",
    ]),
]

_POWELL_DECISION_TABLES = [
    "powell_atp_decisions",
    "powell_po_decisions",
    "powell_rebalance_decisions",
    "powell_buffer_decisions",
    "powell_mo_decisions",
    "powell_to_decisions",
    "powell_quality_decisions",
    "powell_maintenance_decisions",
    "powell_subcontracting_decisions",
    "powell_forecast_adjustment_decisions",
    "powell_order_exceptions",
]

_TENANT_SCOPED_TABLES = [
    ("executive_briefings", "tenant", [
        "created_at",
        "completed_at",
    ]),
]


class DemoDateShiftService:
    """Shifts demo data dates forward to keep them fresh."""

    def __init__(self, db: Session):
        self.db = db

    def shift_demo_dates(self, tenant_id: int, config_id: int) -> dict:
        """
        Calculate gap between now and last_shifted_at.
        Shift all date/timestamp columns forward by that gap.
        Update last_shifted_at and total_shift_days.

        If no record exists, create one with last_shifted_at=now (no shift on first run).

        Returns:
            dict with keys: shifted (bool), days (int), tables_updated (dict),
            rows_affected (int), errors (list)
        """
        now = datetime.utcnow()

        # Check for existing shift log entry
        row = self.db.execute(
            text(
                "SELECT id, last_shifted_at, total_shift_days "
                "FROM demo_date_shift_log "
                "WHERE tenant_id = :tenant_id AND config_id = :config_id"
            ),
            {"tenant_id": tenant_id, "config_id": config_id},
        ).fetchone()

        if row is None:
            # First run: create entry, no shift
            self.db.execute(
                text(
                    "INSERT INTO demo_date_shift_log "
                    "(tenant_id, config_id, last_shifted_at, total_shift_days) "
                    "VALUES (:tenant_id, :config_id, :now, 0)"
                ),
                {"tenant_id": tenant_id, "config_id": config_id, "now": now},
            )
            self.db.commit()
            logger.info(
                "Created demo_date_shift_log entry for tenant=%d config=%d (no shift on first run)",
                tenant_id, config_id,
            )
            return {
                "shifted": False,
                "days": 0,
                "tables_updated": {},
                "rows_affected": 0,
                "errors": [],
                "message": "First run — created tracking entry, no shift needed",
            }

        last_shifted_at = row[1]
        total_shift_days = row[2]
        shift_log_id = row[0]

        # Calculate gap in whole days
        gap = now - last_shifted_at
        shift_days = gap.days

        if shift_days < 1:
            logger.info(
                "Demo date shift skipped for tenant=%d config=%d: gap=%s (< 1 day)",
                tenant_id, config_id, gap,
            )
            return {
                "shifted": False,
                "days": 0,
                "tables_updated": {},
                "rows_affected": 0,
                "errors": [],
                "message": f"Gap is {gap} — less than 1 day, skipping",
            }

        logger.info(
            "Shifting demo dates for tenant=%d config=%d by %d days",
            tenant_id, config_id, shift_days,
        )

        tables_updated = {}
        total_rows = 0
        errors = []

        # Resolve company_id pattern for this config
        company_pattern = self._resolve_company_pattern(config_id)

        # ── Config-scoped tables ──────────────────────────────────
        for table_name, _, columns in _CONFIG_SCOPED_TABLES:
            rows, err = self._shift_table(
                table_name, columns, shift_days,
                where_clause="config_id = :filter_id",
                filter_id=config_id,
            )
            if err:
                errors.append(err)
            elif rows > 0:
                tables_updated[table_name] = rows
                total_rows += rows

        # ── Company-scoped tables ─────────────────────────────────
        if company_pattern:
            for table_name, _, columns in _COMPANY_SCOPED_TABLES:
                rows, err = self._shift_table(
                    table_name, columns, shift_days,
                    where_clause="company_id LIKE :filter_id",
                    filter_id=company_pattern,
                )
                if err:
                    errors.append(err)
                elif rows > 0:
                    tables_updated[table_name] = rows
                    total_rows += rows

        # ── Powell decision tables (config-scoped, created_at only) ───
        for table_name in _POWELL_DECISION_TABLES:
            rows, err = self._shift_table(
                table_name, ["created_at"], shift_days,
                where_clause="config_id = :filter_id",
                filter_id=config_id,
            )
            if err:
                errors.append(err)
            elif rows > 0:
                tables_updated[table_name] = rows
                total_rows += rows

        # ── Tenant-scoped tables ──────────────────────────────────
        for table_name, _, columns in _TENANT_SCOPED_TABLES:
            rows, err = self._shift_table(
                table_name, columns, shift_days,
                where_clause="tenant_id = :filter_id",
                filter_id=tenant_id,
            )
            if err:
                errors.append(err)
            elif rows > 0:
                tables_updated[table_name] = rows
                total_rows += rows

        # ── Clear decision stream digest cache ────────────────────
        try:
            result = self.db.execute(
                text("DELETE FROM decision_stream_digests WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            digest_rows = result.rowcount
            if digest_rows > 0:
                tables_updated["decision_stream_digests (cleared)"] = digest_rows
                logger.info("Cleared %d decision_stream_digests rows for tenant=%d", digest_rows, tenant_id)
        except Exception as e:
            errors.append(f"decision_stream_digests: {e}")
            logger.warning("Could not clear decision_stream_digests: %s", e)

        # ── Update tracking record ────────────────────────────────
        new_total = total_shift_days + shift_days
        self.db.execute(
            text(
                "UPDATE demo_date_shift_log "
                "SET last_shifted_at = :now, total_shift_days = :total "
                "WHERE id = :log_id"
            ),
            {"now": now, "total": new_total, "log_id": shift_log_id},
        )

        self.db.commit()

        logger.info(
            "Demo date shift completed: tenant=%d config=%d days=%d total_shift=%d rows=%d tables=%d errors=%d",
            tenant_id, config_id, shift_days, new_total, total_rows,
            len(tables_updated), len(errors),
        )

        return {
            "shifted": True,
            "days": shift_days,
            "total_shift_days": new_total,
            "tables_updated": tables_updated,
            "rows_affected": total_rows,
            "errors": errors,
        }

    def _resolve_company_pattern(self, config_id: int) -> Optional[str]:
        """Resolve the company_id LIKE pattern for company-scoped tables.

        For config_id=22 (Food Dist) the convention is 'UF_CORP%'.
        For other configs, look up the company_id from the forecast table.
        """
        # Fast path for known configs
        if config_id == 22:
            return "UF_CORP%"

        # Try to infer from forecast table
        try:
            row = self.db.execute(
                text(
                    "SELECT DISTINCT company_id FROM forecast "
                    "WHERE config_id = :cid AND company_id IS NOT NULL "
                    "LIMIT 1"
                ),
                {"cid": config_id},
            ).fetchone()
            if row and row[0]:
                return f"{row[0]}%"
        except Exception:
            pass

        return None

    def _shift_table(
        self,
        table_name: str,
        columns: list[str],
        shift_days: int,
        where_clause: str,
        filter_id,
    ) -> tuple[int, Optional[str]]:
        """Shift date columns in a single table.

        Builds a single UPDATE with SET col = col + INTERVAL for all columns
        that exist. Returns (rows_affected, error_string_or_None).
        """
        # First check which columns actually exist in this table
        existing_columns = self._get_existing_columns(table_name, columns)

        if not existing_columns:
            return 0, None

        # Build SET clauses
        set_parts = []
        for col in existing_columns:
            set_parts.append(f"{col} = {col} + INTERVAL '{shift_days} days'")

        set_clause = ", ".join(set_parts)
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"

        try:
            # Use a savepoint so failures in one table don't rollback the rest
            nested = self.db.begin_nested()
            result = self.db.execute(text(sql), {"filter_id": filter_id})
            rows = result.rowcount
            nested.commit()
            if rows > 0:
                logger.info(
                    "  %s: shifted %d rows (%d columns) by %d days",
                    table_name, rows, len(existing_columns), shift_days,
                )
            return rows, None
        except Exception as e:
            logger.warning("Failed to shift %s: %s", table_name, e)
            try:
                nested.rollback()
            except Exception:
                pass
            return 0, f"{table_name}: {e}"

    def _get_existing_columns(self, table_name: str, candidate_columns: list[str]) -> list[str]:
        """Check which columns actually exist in the table via information_schema."""
        try:
            result = self.db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :tbl AND column_name = ANY(:cols)"
                ),
                {"tbl": table_name, "cols": candidate_columns},
            )
            return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.warning("Could not check columns for %s: %s", table_name, e)
            return candidate_columns  # Optimistic fallback

    def get_shift_status(self, tenant_id: int, config_id: int) -> Optional[dict]:
        """Get the current shift status for a tenant/config pair."""
        row = self.db.execute(
            text(
                "SELECT last_shifted_at, total_shift_days, created_at "
                "FROM demo_date_shift_log "
                "WHERE tenant_id = :tid AND config_id = :cid"
            ),
            {"tid": tenant_id, "cid": config_id},
        ).fetchone()

        if row is None:
            return None

        return {
            "tenant_id": tenant_id,
            "config_id": config_id,
            "last_shifted_at": row[0].isoformat() if row[0] else None,
            "total_shift_days": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
        }

    def get_all_tracked_configs(self) -> list[dict]:
        """Get all tenant/config pairs that are tracked for date shifting."""
        rows = self.db.execute(
            text(
                "SELECT tenant_id, config_id, last_shifted_at, total_shift_days "
                "FROM demo_date_shift_log ORDER BY tenant_id, config_id"
            )
        ).fetchall()

        return [
            {
                "tenant_id": r[0],
                "config_id": r[1],
                "last_shifted_at": r[2].isoformat() if r[2] else None,
                "total_shift_days": r[3],
            }
            for r in rows
        ]
