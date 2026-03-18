"""
SAP Data Staging Models — Intermediate layer between SAP extraction and AWS SC entities.

Three tables:
  sap_extraction_runs  — One row per extraction batch (metadata, counts, delta summary)
  sap_staging_rows     — Raw SAP data preserved in JSONB for audit, delta detection, re-mapping
  sap_table_schemas    — Tracks column sets per SAP table per tenant for schema drift detection

Data flows:  SAP (RFC/OData) → sap_staging_rows → SAPConfigBuilder → AWS SC entities
             CSV upload       → sap_staging_rows → SAPConfigBuilder → AWS SC entities
"""

from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, DateTime, Date,
    ForeignKey, Index, JSON, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.sql import func

from .base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SAPDataCategory(str, PyEnum):
    """Classification of SAP tables by refresh cadence."""
    MASTER = "master"           # Weekly refresh: materials, plants, BOMs, vendors, customers
    TRANSACTION = "transaction" # Daily refresh: sales orders, POs, production orders, deliveries
    CDC = "cdc"                 # Hourly/real-time: goods movements, confirmations, status changes
    USER_IMPORT = "user_import" # Weekly: user accounts, roles, authorizations


class SAPSourceMethod(str, PyEnum):
    """How data was obtained from the SAP system."""
    CSV = "csv"         # Customer uploaded CSV files
    RFC = "rfc"         # Remote Function Call (direct SAP connection)
    ODATA = "odata"     # SAP OData API
    HANA_DB = "hana_db" # Direct HANA SQL query


# ---------------------------------------------------------------------------
# SAP Table Registry — canonical metadata for all supported SAP tables
# ---------------------------------------------------------------------------

SAP_TABLE_REGISTRY = {
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
    "EORD":  {"category": "master", "keys": ["MATNR", "WERKS", "ZEESSION"], "description": "Source List"},
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

    # --- USER IMPORT ---
    "USR02":      {"category": "user_import", "keys": ["BNAME"], "description": "User Master"},
    "USR21":      {"category": "user_import", "keys": ["BNAME"], "description": "User Address Keys"},
    "ADRP":       {"category": "user_import", "keys": ["PERSNUMBER"], "description": "Person Data"},
    "AGR_USERS":  {"category": "user_import", "keys": ["AGR_NAME", "UNAME"], "description": "Role Assignments"},
    "AGR_DEFINE": {"category": "user_import", "keys": ["AGR_NAME"], "description": "Role Definitions"},
    "AGR_1251":   {"category": "user_import", "keys": ["AGR_NAME", "OBJECT", "AUTH", "FIELD"], "description": "Auth Objects"},
    "AGR_TCODES": {"category": "user_import", "keys": ["AGR_NAME", "TCODE"], "description": "Role T-Codes"},
}


def get_tables_by_category(category: str):
    """Return list of SAP table names for a given category."""
    return [k for k, v in SAP_TABLE_REGISTRY.items() if v["category"] == category]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SAPExtractionRun(Base):
    """Metadata for one extraction batch from an SAP system.

    Each run represents a point-in-time snapshot. Multiple runs per tenant
    enable delta detection and historical audit.
    """
    __tablename__ = "sap_extraction_runs"

    id = Column(PG_UUID, primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("sap_connections.id", ondelete="SET NULL"), nullable=True)

    extraction_date = Column(Date, nullable=False)
    erp_system = Column(String(100), nullable=True)       # e.g. "S4HANA_1710"
    source_method = Column(String(20), nullable=False)     # csv, rfc, odata, hana_db

    # Row counts per category
    master_tables = Column(Integer, default=0)
    master_rows = Column(Integer, default=0)
    transaction_tables = Column(Integer, default=0)
    transaction_rows = Column(Integer, default=0)
    cdc_tables = Column(Integer, default=0)
    cdc_rows = Column(Integer, default=0)
    user_tables = Column(Integer, default=0)
    user_rows = Column(Integer, default=0)

    # Lifecycle
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Storage
    csv_directory = Column(String(500), nullable=True)  # Filesystem path to CSV dir
    manifest = Column(JSONB, nullable=True)              # Full MANIFEST.json

    # Delta detection (compared to previous extraction)
    delta_summary = Column(JSONB, nullable=True)
    # {"MARA": {"new": 12, "changed": 5, "deleted": 0, "unchanged": 919}}

    # Validation
    errors = Column(JSONB, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_extraction_runs_tenant", "tenant_id", "extraction_date"),
    )


class SAPStagingRow(Base):
    """One raw SAP table row preserved in JSONB.

    Serves as the audit layer and delta detection substrate. Every row
    extracted from SAP (via any method) passes through this table before
    being mapped to AWS SC entities.
    """
    __tablename__ = "sap_staging_rows"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("sap_connections.id", ondelete="SET NULL"), nullable=True)

    extraction_id = Column(PG_UUID, ForeignKey("sap_extraction_runs.id", ondelete="CASCADE"), nullable=False)
    extraction_date = Column(Date, nullable=False)

    sap_table = Column(String(40), nullable=False)       # e.g. "MARA", "EKKO"
    data_category = Column(String(20), nullable=False)    # master, transaction, cdc, user_import
    source_method = Column(String(20), nullable=False)    # csv, rfc, odata, hana_db

    row_data = Column(JSONB, nullable=False)              # All SAP columns as key-value
    row_hash = Column(String(32), nullable=False)         # MD5 of row_data for delta detection
    business_key = Column(String(200), nullable=True)     # Composite key for matching

    # Processing status
    is_staged = Column(Boolean, default=False)            # True after mapped to AWS SC entity
    staged_at = Column(DateTime, nullable=True)
    staging_errors = Column(JSONB, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_staging_tenant_table_date", "tenant_id", "sap_table", "extraction_date"),
        Index("ix_staging_extraction", "extraction_id"),
        Index("ix_staging_bkey", "tenant_id", "sap_table", "business_key"),
        Index("ix_staging_unstaged", "tenant_id", "is_staged",
              postgresql_where="NOT is_staged"),
        Index("ix_staging_row_data", "row_data", postgresql_using="gin"),
    )


class SAPTableSchema(Base):
    """Tracks the column set for each SAP table per tenant.

    Enables schema drift detection — if a new extraction has different
    columns than the previous one, flag for review (common when SAP
    upgrades or Z-fields are added/removed).
    """
    __tablename__ = "sap_table_schemas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    sap_table = Column(String(40), nullable=False)

    columns = Column(JSONB, nullable=False)       # ["MATNR", "MTART", "MEINS", ...]
    column_types = Column(JSONB, nullable=True)    # {"MATNR": "str", "BRGEW": "float"}
    key_fields = Column(JSONB, nullable=False)     # ["MATNR"] or ["MATNR", "WERKS"]
    data_category = Column(String(20), nullable=False)

    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "sap_table", name="uq_sap_table_schema"),
    )
