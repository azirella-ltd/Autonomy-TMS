"""
Odoo Data Staging Models — Schema: odoo_staging

Separate PostgreSQL schema for raw Odoo data.
Follows the same pattern as sap_staging.py:
  extraction_runs  — Header: one row per extraction batch
  rows             — Detail: raw Odoo data in JSONB (one row per Odoo model record)
  table_schemas    — Column tracking per Odoo model per tenant

Data flow:
  Odoo (JSON-RPC/XML-RPC/CSV) → odoo_staging.rows → OdooConfigBuilder → public.* AWS SC entity tables

The erp_vendor field is NOT stored — it's implicit from the schema name.
"""

from enum import Enum as PyEnum
from typing import Dict, List

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.sql import func

from .base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class OdooDataCategory(str, PyEnum):
    """Classification of Odoo models by refresh cadence."""
    MASTER = "master"           # Weekly: products, warehouses, BOMs, partners
    TRANSACTION = "transaction" # Daily: POs, SOs, production orders, stock moves
    CDC = "cdc"                 # Hourly: stock quants, lot changes


class OdooSourceMethod(str, PyEnum):
    """How data was obtained from Odoo."""
    JSON_RPC = "json_rpc"
    XML_RPC = "xml_rpc"
    CSV = "csv"
    DB_DIRECT = "db_direct"


# ---------------------------------------------------------------------------
# Odoo Model Registry — canonical metadata for all supported Odoo models
# ---------------------------------------------------------------------------

ODOO_MODEL_REGISTRY: Dict[str, Dict] = {
    # --- MASTER DATA ---
    "res.company":                  {"category": "master", "keys": ["id"], "description": "Companies"},
    "stock.warehouse":              {"category": "master", "keys": ["id"], "description": "Warehouses"},
    "stock.location":               {"category": "master", "keys": ["id"], "description": "Stock Locations"},
    "product.product":              {"category": "master", "keys": ["id"], "description": "Product Variants"},
    "product.template":             {"category": "master", "keys": ["id"], "description": "Product Templates"},
    "product.category":             {"category": "master", "keys": ["id"], "description": "Product Categories"},
    "res.partner":                  {"category": "master", "keys": ["id"], "description": "Partners (Vendors + Customers)"},
    "product.supplierinfo":         {"category": "master", "keys": ["id"], "description": "Vendor Pricelists & Lead Times"},
    "mrp.bom":                      {"category": "master", "keys": ["id"], "description": "Bill of Materials Headers"},
    "mrp.bom.line":                 {"category": "master", "keys": ["id"], "description": "BOM Components"},
    "mrp.workcenter":               {"category": "master", "keys": ["id"], "description": "Work Centers"},
    "mrp.routing.workcenter":       {"category": "master", "keys": ["id"], "description": "Routing Operations"},
    "stock.warehouse.orderpoint":   {"category": "master", "keys": ["id"], "description": "Reordering Rules (Min/Max)"},
    "uom.uom":                      {"category": "master", "keys": ["id"], "description": "Units of Measure"},
    "uom.category":                 {"category": "master", "keys": ["id"], "description": "UoM Categories"},
    # --- TRANSACTION DATA ---
    "purchase.order":               {"category": "transaction", "keys": ["id"], "description": "Purchase Orders"},
    "purchase.order.line":          {"category": "transaction", "keys": ["id"], "description": "Purchase Order Lines"},
    "sale.order":                   {"category": "transaction", "keys": ["id"], "description": "Sale Orders"},
    "sale.order.line":              {"category": "transaction", "keys": ["id"], "description": "Sale Order Lines"},
    "mrp.production":               {"category": "transaction", "keys": ["id"], "description": "Manufacturing Orders"},
    "mrp.workorder":                {"category": "transaction", "keys": ["id"], "description": "Work Orders"},
    "stock.picking":                {"category": "transaction", "keys": ["id"], "description": "Stock Transfers (Receipts/Deliveries)"},
    "stock.move":                   {"category": "transaction", "keys": ["id"], "description": "Stock Movements"},
    # --- CDC ---
    "stock.quant":                  {"category": "cdc", "keys": ["id"], "description": "Inventory On-Hand (real-time)"},
    "stock.lot":                    {"category": "cdc", "keys": ["id"], "description": "Lot / Serial Numbers"},
    "stock.move.line":              {"category": "cdc", "keys": ["id"], "description": "Detailed Stock Movements"},
}


def get_odoo_models_by_category(category: str) -> List[str]:
    return [k for k, v in ODOO_MODEL_REGISTRY.items() if v["category"] == category]


def get_odoo_model_keys(model_name: str) -> List[str]:
    return ODOO_MODEL_REGISTRY.get(model_name, {}).get("keys", ["id"])


# ---------------------------------------------------------------------------
# Models — all in odoo_staging schema
# ---------------------------------------------------------------------------

class OdooExtractionRun(Base):
    """Header: one row per extraction batch from Odoo."""
    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_odoo_ext_tenant", "tenant_id", "extraction_date"),
        {"schema": "odoo_staging"},
    )

    id = Column(PG_UUID, primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("erp_connections.id", ondelete="SET NULL"), nullable=True)

    erp_variant = Column(String(30), nullable=False)       # community, enterprise
    extraction_date = Column(Date, nullable=False)
    source_method = Column(String(20), nullable=False)     # json_rpc, xml_rpc, csv, db_direct
    odoo_database = Column(String(100), nullable=True)     # Odoo database name

    master_tables = Column(Integer, default=0)
    master_rows = Column(Integer, default=0)
    transaction_tables = Column(Integer, default=0)
    transaction_rows = Column(Integer, default=0)
    cdc_tables = Column(Integer, default=0)
    cdc_rows = Column(Integer, default=0)

    status = Column(String(20), default="pending")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)
    build_summary = Column(JSONB, nullable=True)
    delta_summary = Column(JSONB, nullable=True)
    errors = Column(JSONB, nullable=True)
    warnings = Column(JSONB, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class OdooStagingRow(Base):
    """Detail: one row per Odoo model record, stored as JSONB."""
    __tablename__ = "rows"
    __table_args__ = (
        Index("ix_odoo_rows_ext", "extraction_id"),
        Index("ix_odoo_rows_tbl", "tenant_id", "odoo_model", "extraction_id"),
        Index("ix_odoo_rows_bk", "tenant_id", "odoo_model", "business_key"),
        {"schema": "odoo_staging"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    extraction_id = Column(PG_UUID, ForeignKey("odoo_staging.extraction_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Integer, nullable=False)

    odoo_model = Column(String(60), nullable=False)
    data_category = Column(String(20), nullable=False)
    row_data = Column(JSONB, nullable=False)
    row_hash = Column(String(32), nullable=False)
    business_key = Column(String(200), nullable=True)

    is_staged = Column(Boolean, default=False)
    staged_at = Column(DateTime, nullable=True)
    staging_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class OdooTableSchema(Base):
    """Tracks column sets per Odoo model per tenant for schema drift detection."""
    __tablename__ = "table_schemas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "odoo_model", name="uq_odoo_tbl_schema"),
        {"schema": "odoo_staging"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    odoo_model = Column(String(60), nullable=False)
    columns = Column(JSONB, nullable=False)
    key_fields = Column(JSONB, nullable=False)
    data_category = Column(String(20), nullable=False)
    row_count = Column(Integer, default=0)
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())
