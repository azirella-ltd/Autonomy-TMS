"""
SAP Data Staging Models — Schema: sap_staging

Separate PostgreSQL schema for raw SAP data. The schema name IS the vendor
(sap_staging for SAP, future: oracle_staging, d365_staging).

Three tables in sap_staging schema:
  extraction_runs  — Header: one row per extraction batch
  rows             — Detail: raw SAP data in JSONB (one row per SAP table row)
  table_schemas    — Column tracking per SAP table per tenant

Data flow:
  SAP (RFC/OData/HANA/CSV) → sap_staging.rows → SAPConfigBuilder → public.* entity tables

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

class SAPDataCategory(str, PyEnum):
    """Classification of SAP tables by refresh cadence."""
    MASTER = "master"           # Weekly: materials, plants, BOMs, vendors, customers
    TRANSACTION = "transaction" # Daily: sales orders, POs, production orders, deliveries
    CDC = "cdc"                 # Hourly: goods movements, confirmations, status changes


class SAPSourceMethod(str, PyEnum):
    """How data was obtained from the SAP system."""
    CSV = "csv"
    RFC = "rfc"
    ODATA = "odata"
    HANA_DB = "hana_db"


# ---------------------------------------------------------------------------
# SAP Table Registry — canonical metadata for all supported SAP tables
# ---------------------------------------------------------------------------

SAP_TABLE_REGISTRY: Dict[str, Dict] = {
    # --- MASTER DATA ---
    "T001":  {"category": "master", "keys": ["BUKRS"], "description": "Company Codes"},
    "T001W": {"category": "master", "keys": ["WERKS"], "description": "Plants"},
    "T001L": {"category": "master", "keys": ["WERKS", "LGORT"], "description": "Storage Locations"},
    "ADRC":  {"category": "master", "keys": ["ADDRNUMBER"], "description": "Addresses"},
    "MARA":  {"category": "master", "keys": ["MATNR"], "description": "Material General"},
    "MAKT":  {"category": "master", "keys": ["MATNR", "SPRAS"], "description": "Material Descriptions"},
    "MARC":  {"category": "master", "keys": ["MATNR", "WERKS"], "description": "Material Plant"},
    "MARD":  {"category": "master", "keys": ["MATNR", "WERKS", "LGORT"], "description": "Material Storage Stock"},
    "MARM":  {"category": "master", "keys": ["MATNR", "MEINH"], "description": "UoM Conversions"},
    "MBEW":  {"category": "master", "keys": ["MATNR", "BWKEY"], "description": "Material Valuation"},
    "MVKE":  {"category": "master", "keys": ["MATNR", "VKORG", "VTWEG"], "description": "Material Sales Data"},
    "MAST":  {"category": "master", "keys": ["MATNR", "WERKS", "STLAN", "STLNR"], "description": "Material BOM Assignment"},
    "KNA1":  {"category": "master", "keys": ["KUNNR"], "description": "Customers"},
    "KNVV":  {"category": "master", "keys": ["KUNNR", "VKORG", "VTWEG", "SPART"], "description": "Customer Sales Area"},
    "LFA1":  {"category": "master", "keys": ["LIFNR"], "description": "Vendors"},
    "STKO":  {"category": "master", "keys": ["STLNR", "STLAL"], "description": "BOM Headers"},
    "STPO":  {"category": "master", "keys": ["STLNR", "STLKN", "STPOZ"], "description": "BOM Items"},
    "EORD":  {"category": "master", "keys": ["MATNR", "WERKS"], "description": "Source List"},
    "EINA":  {"category": "master", "keys": ["INFNR"], "description": "Purchasing Info General"},
    "EINE":  {"category": "master", "keys": ["INFNR", "EKORG"], "description": "Purchasing Info Org"},
    "EBAN":  {"category": "master", "keys": ["BANFN", "BNFPO"], "description": "Purchase Requisitions"},
    "CRHD":  {"category": "master", "keys": ["OBJID"], "description": "Work Centers"},
    "EQUI":  {"category": "master", "keys": ["EQUNR"], "description": "Equipment"},
    "PLKO":  {"category": "master", "keys": ["PLNTY", "PLNNR", "PLNAL"], "description": "Routing Headers"},
    "PLPO":  {"category": "master", "keys": ["PLNTY", "PLNNR", "PLNAL", "VORNR"], "description": "Routing Operations"},
    "PBIM":  {"category": "master", "keys": ["BDZEI"], "description": "PIR Headers"},
    "PBED":  {"category": "master", "keys": ["BDZEI", "PDATU"], "description": "PIR Schedule Lines"},
    "PLAF":  {"category": "master", "keys": ["PLNUM"], "description": "Planned Orders"},
    "T179":  {"category": "master", "keys": ["PRODH"], "description": "Product Hierarchy"},
    "KAKO":  {"category": "master", "keys": ["KAPID"], "description": "Capacity Headers"},
    # --- TRANSACTION DATA ---
    "VBAK":  {"category": "transaction", "keys": ["VBELN"], "description": "Sales Order Headers"},
    "VBAP":  {"category": "transaction", "keys": ["VBELN", "POSNR"], "description": "Sales Order Items"},
    "VBEP":  {"category": "transaction", "keys": ["VBELN", "POSNR", "ETENR"], "description": "SO Schedule Lines"},
    "VBUK":  {"category": "transaction", "keys": ["VBELN"], "description": "SO Header Status"},
    "VBUP":  {"category": "transaction", "keys": ["VBELN", "POSNR"], "description": "SO Item Status"},
    "EKKO":  {"category": "transaction", "keys": ["EBELN"], "description": "PO Headers"},
    "EKPO":  {"category": "transaction", "keys": ["EBELN", "EBELP"], "description": "PO Items"},
    "EKET":  {"category": "transaction", "keys": ["EBELN", "EBELP", "ETENR"], "description": "PO Schedule Lines"},
    "AFKO":  {"category": "transaction", "keys": ["AUFNR"], "description": "Production Order Headers"},
    "AFPO":  {"category": "transaction", "keys": ["AUFNR", "POSNR"], "description": "Production Order Items"},
    "AFVC":  {"category": "transaction", "keys": ["AUFPL", "APLZL"], "description": "Order Operations"},
    "AUFK":  {"category": "transaction", "keys": ["AUFNR"], "description": "Order Master"},
    "LIKP":  {"category": "transaction", "keys": ["VBELN"], "description": "Delivery Headers"},
    "LIPS":  {"category": "transaction", "keys": ["VBELN", "POSNR"], "description": "Delivery Items"},
    "LTAK":  {"category": "transaction", "keys": ["TESSION", "TAESSION"], "description": "Transfer Order Headers"},
    "LTAP":  {"category": "transaction", "keys": ["TESSION", "TAESSION", "TAPESSION"], "description": "Transfer Order Items"},
    "RESB":  {"category": "transaction", "keys": ["RSNUM", "RSPOS"], "description": "Reservations"},
    "QMEL":  {"category": "transaction", "keys": ["QMNUM"], "description": "Quality Notifications"},
    "QALS":  {"category": "transaction", "keys": ["PRUESSION"], "description": "Inspection Lots"},
    "QASE":  {"category": "transaction", "keys": ["PRUESSION", "VESSION"], "description": "Inspection Results"},
    "KONV":  {"category": "transaction", "keys": ["KNUMV", "KPOSN", "STUNR"], "description": "Pricing Conditions"},
    # --- CDC (Change Data Capture) ---
    "MSEG":  {"category": "cdc", "keys": ["MBLNR", "MJAHR", "ZEESSION"], "description": "Goods Movement Items"},
    "MKPF":  {"category": "cdc", "keys": ["MBLNR", "MJAHR"], "description": "Goods Movement Headers"},
    "EKBE":  {"category": "cdc", "keys": ["EBELN", "EBELP", "ZEESSION", "VGABE"], "description": "PO History"},
    "AFRU":  {"category": "cdc", "keys": ["RUESSION", "RMESSION"], "description": "Production Confirmations"},
    "JEST":  {"category": "cdc", "keys": ["OBJNR", "STAT"], "description": "System Status"},
    "TJ02T": {"category": "cdc", "keys": ["ISTAT", "SPRAS"], "description": "Status Texts"},
    "MCH1":  {"category": "cdc", "keys": ["MATNR", "CHARG"], "description": "Batch Master"},
    "MCHA":  {"category": "cdc", "keys": ["MATNR", "CHARG", "WERKS"], "description": "Batch Plant"},
    "CDHDR": {"category": "cdc", "keys": ["CHANGENR"], "description": "Change Document Header"},
    "CDPOS": {"category": "cdc", "keys": ["CHANGENR", "TABNAME", "FNAME"], "description": "Change Document Items"},
    "CRCO":  {"category": "cdc", "keys": ["OBJID", "ARBPL"], "description": "Work Center Cost Center"},
}


def get_tables_by_category(category: str) -> List[str]:
    """Return list of SAP table names for a given category."""
    return [k for k, v in SAP_TABLE_REGISTRY.items() if v["category"] == category]


def get_table_keys(table_name: str) -> List[str]:
    """Return the business key fields for a SAP table."""
    reg = SAP_TABLE_REGISTRY.get(table_name, {})
    return reg.get("keys", [])


def get_table_category(table_name: str) -> str:
    """Return the data category for a SAP table."""
    reg = SAP_TABLE_REGISTRY.get(table_name, {})
    return reg.get("category", "master")


# ---------------------------------------------------------------------------
# Models — all in sap_staging schema
# ---------------------------------------------------------------------------

class SAPExtractionRun(Base):
    """Header: one row per extraction batch.

    Links to tenant, tracks what was extracted, what was built, and any issues.
    """
    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_sap_ext_tenant", "tenant_id", "extraction_date"),
        {"schema": "sap_staging"},
    )

    id = Column(PG_UUID, primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("sap_connections.id", ondelete="SET NULL"), nullable=True)

    # ERP context (vendor is implicit from schema name)
    erp_variant = Column(String(30), nullable=False)       # S4HANA, ECC, APO, IBP
    extraction_date = Column(Date, nullable=False)
    source_method = Column(String(20), nullable=False)     # csv, rfc, odata, hana_db

    # Counts per category
    master_tables = Column(Integer, default=0)
    master_rows = Column(Integer, default=0)
    transaction_tables = Column(Integer, default=0)
    transaction_rows = Column(Integer, default=0)
    cdc_tables = Column(Integer, default=0)
    cdc_rows = Column(Integer, default=0)

    # Lifecycle
    status = Column(String(20), default="pending")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # What was built from this extraction
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="SET NULL"), nullable=True)
    build_summary = Column(JSONB, nullable=True)

    # Delta and diagnostics
    delta_summary = Column(JSONB, nullable=True)
    errors = Column(JSONB, nullable=True)
    warnings = Column(JSONB, nullable=True)  # empty/sparse tables, schema drift

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class SAPStagingRow(Base):
    """Detail: one row per SAP table row, stored as JSONB.

    Every row extracted from SAP passes through here before being
    mapped to AWS SC entity tables. Provides audit trail and delta detection.
    """
    __tablename__ = "rows"
    __table_args__ = (
        Index("ix_sap_rows_ext", "extraction_id"),
        Index("ix_sap_rows_tbl", "tenant_id", "sap_table", "extraction_id"),
        Index("ix_sap_rows_bk", "tenant_id", "sap_table", "business_key"),
        {"schema": "sap_staging"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    extraction_id = Column(PG_UUID, ForeignKey("sap_staging.extraction_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Integer, nullable=False)

    sap_table = Column(String(40), nullable=False)
    data_category = Column(String(20), nullable=False)
    row_data = Column(JSONB, nullable=False)
    row_hash = Column(String(32), nullable=False)
    business_key = Column(String(200), nullable=True)

    # Processing
    is_staged = Column(Boolean, default=False)
    staged_at = Column(DateTime, nullable=True)
    staging_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class SAPTableSchema(Base):
    """Tracks column sets per SAP table per tenant for schema drift detection."""
    __tablename__ = "table_schemas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sap_table", name="uq_sap_tbl_schema"),
        {"schema": "sap_staging"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    sap_table = Column(String(40), nullable=False)
    columns = Column(JSONB, nullable=False)
    key_fields = Column(JSONB, nullable=False)
    data_category = Column(String(20), nullable=False)
    row_count = Column(Integer, default=0)
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())
