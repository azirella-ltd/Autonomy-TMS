"""
Generalized ERP Staging Repository — Write-through layer for any ERP.

Works with any of the three staging schemas:
  sap_staging   — SAP tables (MARA, EKKO, etc.)
  d365_staging  — D365 entities (ReleasedProductsV2, Vendors, etc.)
  odoo_staging  — Odoo models (product.product, sale.order, etc.)

The schema name IS the vendor. The entity column name varies:
  sap_staging.rows.sap_table      → "MARA"
  d365_staging.rows.d365_entity   → "ReleasedProductsV2"
  odoo_staging.rows.odoo_model    → "product.product"

Usage:
    repo = ERPStagingRepository(db, tenant_id=20, erp_type="sap")
    eid = await repo.start_extraction(erp_variant="S4HANA", source_method="hana_db")
    await repo.stage_table(eid, "MARA", df)
    await repo.complete_extraction(eid)
    data = await repo.get_staged_data(eid)  # returns Dict[str, pd.DataFrame]
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

logger = logging.getLogger(__name__)


# Schema and column naming per ERP type
_ERP_SCHEMA_CONFIG = {
    "sap": {
        "schema": "sap_staging",
        "entity_column": "sap_table",
        "schema_table": "table_schemas",
        "schema_entity_col": "sap_table",
    },
    "d365": {
        "schema": "d365_staging",
        "entity_column": "d365_entity",
        "schema_table": "entity_schemas",
        "schema_entity_col": "d365_entity",
    },
    "odoo": {
        "schema": "odoo_staging",
        "entity_column": "odoo_model",
        "schema_table": "model_schemas",
        "schema_entity_col": "odoo_model",
    },
}


def _get_entity_registry(erp_type: str) -> Dict:
    """Return the entity→category→keys registry for an ERP type."""
    if erp_type == "sap":
        from app.models.sap_staging import SAP_TABLE_REGISTRY
        return SAP_TABLE_REGISTRY
    elif erp_type == "d365":
        return D365_ENTITY_REGISTRY
    elif erp_type == "odoo":
        return ODOO_MODEL_REGISTRY
    return {}


# ---------------------------------------------------------------------------
# D365 Entity Registry
# ---------------------------------------------------------------------------

D365_ENTITY_REGISTRY = {
    # Master Data
    "LegalEntities":           {"category": "master", "keys": ["DataAreaId"], "description": "Company/Legal Entity"},
    "OperationalSites":        {"category": "master", "keys": ["SiteId"], "description": "Sites/Plants"},
    "Warehouses":              {"category": "master", "keys": ["WarehouseId", "SiteId"], "description": "Warehouses"},
    "ReleasedProductsV2":      {"category": "master", "keys": ["ItemNumber"], "description": "Products"},
    "ProductCategories":       {"category": "master", "keys": ["CategoryId"], "description": "Product Categories"},
    "BillOfMaterialsHeaders":  {"category": "master", "keys": ["BOMId"], "description": "BOM Headers"},
    "BillOfMaterialsLines":    {"category": "master", "keys": ["BOMId", "LineNumber"], "description": "BOM Lines"},
    "Vendors":                 {"category": "master", "keys": ["VendorAccountNumber"], "description": "Vendors"},
    "CustomersV3":             {"category": "master", "keys": ["CustomerAccount"], "description": "Customers"},
    "VendorLeadTimes":         {"category": "master", "keys": ["VendorAccountNumber", "ItemNumber"], "description": "Vendor Lead Times"},
    "VendorPurchasePrices":    {"category": "master", "keys": ["VendorAccountNumber", "ItemNumber"], "description": "Vendor Prices"},
    "InventWarehouseOnHandEntity": {"category": "master", "keys": ["ItemId", "InventSiteId", "InventLocationId"], "description": "Inventory On Hand"},
    "InventItemOrderSetups":   {"category": "master", "keys": ["ItemId", "SiteId"], "description": "Order Settings"},
    "ItemCoverageSettings":    {"category": "master", "keys": ["ItemId", "SiteId"], "description": "Coverage/Safety Stock"},
    "TransportationRoutes":    {"category": "master", "keys": ["RouteId"], "description": "Transportation Routes"},
    "ProductionRouteHeaders":  {"category": "master", "keys": ["RouteId"], "description": "Production Routes"},
    "ProductionRouteOperations": {"category": "master", "keys": ["RouteId", "OperationNumber"], "description": "Route Operations"},
    "Resources":               {"category": "master", "keys": ["ResourceId"], "description": "Work Centers/Resources"},
    # Transaction Data
    "PurchaseOrderHeadersV2":  {"category": "transaction", "keys": ["PurchaseOrderNumber"], "description": "PO Headers"},
    "PurchaseOrderLinesV2":    {"category": "transaction", "keys": ["PurchaseOrderNumber", "LineNumber"], "description": "PO Lines"},
    "SalesOrderHeadersV2":     {"category": "transaction", "keys": ["SalesOrderNumber"], "description": "SO Headers"},
    "SalesOrderLinesV2":       {"category": "transaction", "keys": ["SalesOrderNumber", "LineNumber"], "description": "SO Lines"},
    "ProductionOrderHeaders":  {"category": "transaction", "keys": ["ProductionOrderNumber"], "description": "Production Orders"},
    "DemandForecastEntries":   {"category": "transaction", "keys": ["ItemNumber", "SiteId", "ForecastDate"], "description": "Demand Forecasts"},
    # CDC
    "InventoryTransactions":   {"category": "cdc", "keys": ["TransactionId"], "description": "Inventory Movements"},
    "ProductReceiptHeaders":   {"category": "cdc", "keys": ["ProductReceiptNumber"], "description": "Goods Receipts"},
}


# ---------------------------------------------------------------------------
# Odoo Model Registry
# ---------------------------------------------------------------------------

ODOO_MODEL_REGISTRY = {
    # Master Data
    "res.company":              {"category": "master", "keys": ["id"], "description": "Company"},
    "stock.warehouse":          {"category": "master", "keys": ["id"], "description": "Warehouses"},
    "stock.location":           {"category": "master", "keys": ["id"], "description": "Stock Locations"},
    "product.product":          {"category": "master", "keys": ["id"], "description": "Products"},
    "product.template":         {"category": "master", "keys": ["id"], "description": "Product Templates"},
    "product.category":         {"category": "master", "keys": ["id"], "description": "Product Categories"},
    "mrp.bom":                  {"category": "master", "keys": ["id"], "description": "BOM Headers"},
    "mrp.bom.line":             {"category": "master", "keys": ["id"], "description": "BOM Lines"},
    "mrp.workcenter":           {"category": "master", "keys": ["id"], "description": "Work Centers"},
    "mrp.routing.workcenter":   {"category": "master", "keys": ["id"], "description": "Routing Operations"},
    "res.partner":              {"category": "master", "keys": ["id"], "description": "Partners (Vendors+Customers)"},
    "product.supplierinfo":     {"category": "master", "keys": ["id"], "description": "Vendor Pricing/Lead Times"},
    "stock.quant":              {"category": "master", "keys": ["id"], "description": "Inventory Quantities"},
    "stock.warehouse.orderpoint": {"category": "master", "keys": ["id"], "description": "Reorder Rules"},
    # Transaction Data
    "purchase.order":           {"category": "transaction", "keys": ["id"], "description": "Purchase Orders"},
    "purchase.order.line":      {"category": "transaction", "keys": ["id"], "description": "PO Lines"},
    "sale.order":               {"category": "transaction", "keys": ["id"], "description": "Sales Orders"},
    "sale.order.line":          {"category": "transaction", "keys": ["id"], "description": "SO Lines"},
    "mrp.production":           {"category": "transaction", "keys": ["id"], "description": "Manufacturing Orders"},
    "mrp.workorder":            {"category": "transaction", "keys": ["id"], "description": "Work Orders"},
    "stock.picking":            {"category": "transaction", "keys": ["id"], "description": "Transfers/Shipments"},
    "stock.move":               {"category": "transaction", "keys": ["id"], "description": "Stock Moves"},
    # CDC
    "stock.move.line":          {"category": "cdc", "keys": ["id"], "description": "Detailed Stock Moves"},
    "account.move":             {"category": "cdc", "keys": ["id"], "description": "Journal Entries"},
}


class ERPStagingRepository:
    """Generalized staging repository that works with any ERP schema."""

    def __init__(self, db: AsyncSession, tenant_id: int, erp_type: str):
        self.db = db
        self.tenant_id = tenant_id
        self.erp_type = erp_type.lower()

        config = _ERP_SCHEMA_CONFIG.get(self.erp_type)
        if not config:
            raise ValueError(f"Unsupported ERP type: {erp_type}. Must be: sap, d365, odoo")

        self.schema = config["schema"]
        self.entity_col = config["entity_column"]
        self.schema_table = config["schema_table"]
        self.schema_entity_col = config["schema_entity_col"]
        self.registry = _get_entity_registry(self.erp_type)

    def _get_category(self, entity_name: str) -> str:
        reg = self.registry.get(entity_name, {})
        return reg.get("category", "master")

    def _get_keys(self, entity_name: str) -> List[str]:
        reg = self.registry.get(entity_name, {})
        return reg.get("keys", [])

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
        ext_date = extraction_date or date.today()
        result = await self.db.execute(
            text(f"""
                INSERT INTO {self.schema}.extraction_runs
                    (tenant_id, connection_id, erp_variant, extraction_date,
                     source_method, status, started_at)
                VALUES (:tid, :cid, :variant, :edate, :method, 'running', NOW())
                RETURNING id
            """),
            {"tid": self.tenant_id, "cid": connection_id, "variant": erp_variant,
             "edate": ext_date, "method": source_method},
        )
        extraction_id = result.fetchone()[0]
        logger.info("Started %s extraction %s: tenant=%d", self.erp_type, extraction_id, self.tenant_id)
        return extraction_id

    async def stage_entity(
        self,
        extraction_id: UUID,
        entity_name: str,
        df: pd.DataFrame,
    ) -> int:
        """Bulk-insert rows for one ERP entity/table/model."""
        if df.empty:
            return 0

        category = self._get_category(entity_name)
        key_fields = self._get_keys(entity_name)

        rows_to_insert = []
        for _, row in df.iterrows():
            row_dict = {k: _serialize(v) for k, v in row.items()}
            row_json = json.dumps(row_dict, default=str, sort_keys=True)
            row_hash = hashlib.md5(row_json.encode()).hexdigest()

            bkey_parts = [str(row_dict.get(k, "")).strip() for k in key_fields if k in row_dict]
            business_key = "|".join(bkey_parts) if bkey_parts else None

            rows_to_insert.append((
                str(extraction_id), self.tenant_id, entity_name, category,
                row_json, row_hash, business_key,
            ))

        # Batch insert
        inserted = 0
        batch_size = 2000
        for i in range(0, len(rows_to_insert), batch_size):
            batch = rows_to_insert[i:i + batch_size]
            placeholders = []
            params = {}
            for j, (eid, tid, ent, cat, rdata, rhash, bkey) in enumerate(batch):
                p = f"_{j}"
                placeholders.append(
                    f"(CAST(:eid{p} AS uuid), :tid{p}, :ent{p}, :cat{p}, "
                    f"CAST(:rd{p} AS jsonb), :rh{p}, :bk{p})"
                )
                params.update({
                    f"eid{p}": eid, f"tid{p}": tid, f"ent{p}": ent, f"cat{p}": cat,
                    f"rd{p}": rdata, f"rh{p}": rhash, f"bk{p}": bkey,
                })

            sql = (
                f"INSERT INTO {self.schema}.rows "
                f"(extraction_id, tenant_id, {self.entity_col}, data_category, "
                f"row_data, row_hash, business_key) VALUES "
                + ", ".join(placeholders)
            )
            await self.db.execute(text(sql), params)
            inserted += len(batch)

        # Update schema tracking
        columns = list(df.columns)
        await self.db.execute(
            text(f"""
                INSERT INTO {self.schema}.{self.schema_table}
                    (tenant_id, {self.schema_entity_col}, columns, key_fields, data_category, row_count, last_seen)
                VALUES (:tid, :ent, CAST(:cols AS jsonb), CAST(:keys AS jsonb), :cat, :cnt, NOW())
                ON CONFLICT (tenant_id, {self.schema_entity_col})
                DO UPDATE SET columns = EXCLUDED.columns, row_count = EXCLUDED.row_count, last_seen = NOW()
            """),
            {"tid": self.tenant_id, "ent": entity_name, "cols": json.dumps(columns),
             "keys": json.dumps(key_fields), "cat": category, "cnt": len(df)},
        )

        logger.info("Staged %s.%s: %d rows (category=%s)", self.erp_type, entity_name, inserted, category)
        return inserted

    # Alias for backward compatibility
    stage_table = stage_entity

    async def complete_extraction(
        self,
        extraction_id: UUID,
        config_id: Optional[int] = None,
        build_summary: Optional[Dict] = None,
        warnings: Optional[List[Dict]] = None,
        error: Optional[str] = None,
    ) -> None:
        counts = await self.db.execute(
            text(f"""
                SELECT data_category, COUNT(DISTINCT {self.entity_col}) AS tables, COUNT(*) AS rows
                FROM {self.schema}.rows WHERE extraction_id = CAST(:eid AS uuid)
                GROUP BY data_category
            """),
            {"eid": str(extraction_id)},
        )
        cat_counts = {r[0]: {"tables": r[1], "rows": r[2]} for r in counts.fetchall()}

        status = "failed" if error else "completed"
        await self.db.execute(
            text(f"""
                UPDATE {self.schema}.extraction_runs SET
                    status = :status, completed_at = NOW(), config_id = :cid,
                    build_summary = CAST(:summary AS jsonb),
                    master_tables = :mt, master_rows = :mr,
                    transaction_tables = :tt, transaction_rows = :tr,
                    cdc_tables = :ct, cdc_rows = :cr,
                    warnings = CAST(:warnings AS jsonb),
                    errors = CAST(:errors AS jsonb)
                WHERE id = CAST(:eid AS uuid)
            """),
            {
                "status": status, "cid": config_id,
                "summary": json.dumps(build_summary) if build_summary else None,
                "mt": cat_counts.get("master", {}).get("tables", 0),
                "mr": cat_counts.get("master", {}).get("rows", 0),
                "tt": cat_counts.get("transaction", {}).get("tables", 0),
                "tr": cat_counts.get("transaction", {}).get("rows", 0),
                "ct": cat_counts.get("cdc", {}).get("tables", 0),
                "cr": cat_counts.get("cdc", {}).get("rows", 0),
                "warnings": json.dumps(warnings) if warnings else None,
                "errors": json.dumps({"message": error}) if error else None,
                "eid": str(extraction_id),
            },
        )

    async def get_staged_data(self, extraction_id: UUID) -> Dict[str, pd.DataFrame]:
        """Load staged data as Dict[entity_name, DataFrame]."""
        entities = await self.db.execute(
            text(f"SELECT DISTINCT {self.entity_col} FROM {self.schema}.rows WHERE extraction_id = CAST(:eid AS uuid)"),
            {"eid": str(extraction_id)},
        )
        result = {}
        for (entity_name,) in entities.fetchall():
            rows = await self.db.execute(
                text(f"""
                    SELECT row_data FROM {self.schema}.rows
                    WHERE extraction_id = CAST(:eid AS uuid) AND {self.entity_col} = :ent
                    ORDER BY id
                """),
                {"eid": str(extraction_id), "ent": entity_name},
            )
            data = [r[0] for r in rows.fetchall()]
            if data:
                result[entity_name] = pd.DataFrame(data)
        return result

    async def enforce_retention(self, max_extractions: int = 5) -> int:
        result = await self.db.execute(
            text(f"""
                WITH ranked AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY extraction_date DESC, created_at DESC) AS rn
                    FROM {self.schema}.extraction_runs WHERE tenant_id = :tid
                )
                DELETE FROM {self.schema}.extraction_runs
                WHERE id IN (SELECT id FROM ranked WHERE rn > :max)
                RETURNING id
            """),
            {"tid": self.tenant_id, "max": max_extractions},
        )
        deleted = len(result.fetchall())
        if deleted:
            logger.info("Retention: deleted %d old %s extractions for tenant %d", deleted, self.erp_type, self.tenant_id)
        return deleted


def _serialize(v) -> Any:
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v
