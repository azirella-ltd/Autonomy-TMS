"""
D365 Data Staging Models — Schema: d365_staging

Separate PostgreSQL schema for raw Microsoft Dynamics 365 F&O data.
Follows the same pattern as sap_staging.py:
  extraction_runs  — Header: one row per extraction batch
  rows             — Detail: raw D365 data in JSONB (one row per OData entity record)
  table_schemas    — Column tracking per D365 entity per tenant

Data flow:
  D365 F&O (OData/DMF/CSV) → d365_staging.rows → D365ConfigBuilder → public.* AWS SC entity tables

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

class D365DataCategory(str, PyEnum):
    """Classification of D365 entities by refresh cadence."""
    MASTER = "master"           # Weekly: products, sites, warehouses, vendors, BOMs, work centers
    TRANSACTION = "transaction" # Daily: POs, SOs, production orders, shipments
    CDC = "cdc"                 # Hourly: goods receipts, confirmations, status changes


class D365SourceMethod(str, PyEnum):
    """How data was obtained from D365."""
    ODATA = "odata"
    DMF = "dmf"
    CSV = "csv"


# ---------------------------------------------------------------------------
# D365 Entity Registry — canonical metadata for all supported D365 entities
# ---------------------------------------------------------------------------

D365_ENTITY_REGISTRY: Dict[str, Dict] = {
    # --- MASTER DATA ---
    "LegalEntities":                {"category": "master", "keys": ["DataArea"], "description": "Company Codes / Legal Entities"},
    "Sites":                        {"category": "master", "keys": ["SiteId"], "description": "Operational Sites"},
    "Warehouses":                   {"category": "master", "keys": ["WarehouseId", "SiteId"], "description": "Warehouses"},
    "StorageLocations":             {"category": "master", "keys": ["SiteId", "StorageLocationId"], "description": "Storage Locations within Warehouses"},
    "ReleasedProductsV2":           {"category": "master", "keys": ["ItemNumber"], "description": "Released Products (Items)"},
    "ProductUnitConversions":       {"category": "master", "keys": ["ItemNumber", "AlternativeUnitSymbol"], "description": "Unit of Measure Conversions"},
    "ProductCategories":            {"category": "master", "keys": ["CategoryId"], "description": "Product Hierarchy Categories"},
    "Vendors":                      {"category": "master", "keys": ["VendorAccountNumber"], "description": "Vendor Master"},
    "CustomersV3":                  {"category": "master", "keys": ["CustomerAccount"], "description": "Customer Master"},
    "CustomerSalesAreas":           {"category": "master", "keys": ["CustomerAccount", "SalesOrganization", "DistributionChannel", "Division"], "description": "Customer Sales Area Data"},
    "VendorPurchasePrices":         {"category": "master", "keys": ["VendorAccountNumber", "ItemNumber", "PurchasingOrganization"], "description": "Vendor Pricing and Lead Times"},
    "ApprovedVendorList":           {"category": "master", "keys": ["ItemNumber", "SiteId", "SourceListNumber"], "description": "Approved Vendor Source List"},
    "BillOfMaterialsHeaders":       {"category": "master", "keys": ["BOMId"], "description": "BOM Headers"},
    "BillOfMaterialsLines":         {"category": "master", "keys": ["BOMId", "LineNumber"], "description": "BOM Components"},
    "WorkCenters":                  {"category": "master", "keys": ["WorkCenterId"], "description": "Work Centers / Resources"},
    "RoutingHeaders":               {"category": "master", "keys": ["RoutingType", "RoutingNumber", "RoutingAlternative"], "description": "Production Routing Headers"},
    "RoutingOperations":            {"category": "master", "keys": ["RoutingType", "RoutingNumber", "OperationNumber"], "description": "Routing Operation Steps"},
    "CapacityData":                 {"category": "master", "keys": ["CapacityId"], "description": "Capacity Planning Data"},
    "InventWarehouseOnHandEntity":  {"category": "master", "keys": ["ItemNumber", "WarehouseId", "SiteId"], "description": "Inventory On-Hand"},
    "ItemCoverageSettings":         {"category": "master", "keys": ["ItemNumber", "SiteId", "WarehouseId"], "description": "MRP Coverage / Safety Stock / Planning Params (CoverageCode, lot sizing, time fences, lead times)"},
    "BatchMaster":                  {"category": "master", "keys": ["ItemNumber", "BatchNumber"], "description": "Batch / Lot Master"},
    "DemandForecastEntries":        {"category": "master", "keys": ["ItemNumber", "SiteId", "ForecastDate"], "description": "Demand Forecast"},
    # --- TRANSACTION DATA ---
    "PurchaseOrderHeadersV2":       {"category": "transaction", "keys": ["PurchaseOrderNumber"], "description": "Purchase Order Headers"},
    "PurchaseOrderLinesV2":         {"category": "transaction", "keys": ["PurchaseOrderNumber", "LineNumber"], "description": "Purchase Order Lines"},
    "PurchaseOrderScheduleLines":   {"category": "transaction", "keys": ["PurchaseOrderNumber", "LineNumber", "ScheduleLineNumber"], "description": "PO Delivery Schedules"},
    "PurchaseRequisitionLines":     {"category": "transaction", "keys": ["RequisitionNumber", "LineNumber"], "description": "Purchase Requisitions"},
    "SalesOrderHeadersV2":          {"category": "transaction", "keys": ["SalesOrderNumber"], "description": "Sales Order Headers"},
    "SalesOrderLinesV2":            {"category": "transaction", "keys": ["SalesOrderNumber", "LineNumber"], "description": "Sales Order Lines"},
    "SalesOrderDeliverySchedules":  {"category": "transaction", "keys": ["SalesOrderNumber", "LineNumber", "ScheduleLineNumber"], "description": "SO Delivery Schedules"},
    "ProductionOrderHeaders":       {"category": "transaction", "keys": ["ProductionOrderNumber"], "description": "Production Order Headers"},
    "ProductionOrderItems":         {"category": "transaction", "keys": ["ProductionOrderNumber", "LineNumber"], "description": "Production Order Output Items"},
    "ProductionOrderBOMLines":      {"category": "transaction", "keys": ["ReservationNumber", "LineNumber"], "description": "Production Order Component Requirements"},
    "ProductionRouteOperations":    {"category": "transaction", "keys": ["RoutingPlanNumber", "OperationSequence"], "description": "Production Order Routing Operations"},
    "PlannedOrders":                {"category": "transaction", "keys": ["PlannedOrderNumber"], "description": "MRP Planned Orders"},
    "ShipmentHeaders":              {"category": "transaction", "keys": ["ShipmentNumber"], "description": "Delivery / Shipment Headers"},
    "ShipmentLines":                {"category": "transaction", "keys": ["ShipmentNumber", "LineNumber"], "description": "Delivery / Shipment Lines"},
    # --- CDC (Change Data Capture) ---
    "PurchaseOrderReceiptJournal":  {"category": "cdc", "keys": ["PurchaseOrderNumber", "LineNumber", "PostingDate"], "description": "Goods Receipt History"},
    "ProductionOrderConfirmations": {"category": "cdc", "keys": ["ProductionOrderNumber", "OperationNumber"], "description": "Production Confirmations (Yield/Scrap)"},
    "QualityOrders":                {"category": "cdc", "keys": ["QualityOrderNumber"], "description": "Quality Inspection Lots"},
    "QualityTestResults":           {"category": "cdc", "keys": ["QualityOrderNumber", "OperationSequence", "CharacteristicNumber"], "description": "Quality Test Results"},
    "QualityNotifications":         {"category": "cdc", "keys": ["NotificationNumber"], "description": "Quality Notifications / Defects"},
    "MaintenanceAssets":            {"category": "cdc", "keys": ["EquipmentNumber"], "description": "Equipment / Maintenance Assets"},
    "ObjectStatusHistory":          {"category": "cdc", "keys": ["ObjectNumber", "StatusCode"], "description": "System Status Changes"},
}


def get_d365_tables_by_category(category: str) -> List[str]:
    return [k for k, v in D365_ENTITY_REGISTRY.items() if v["category"] == category]


def get_d365_entity_keys(entity_name: str) -> List[str]:
    return D365_ENTITY_REGISTRY.get(entity_name, {}).get("keys", [])


# ---------------------------------------------------------------------------
# Models — all in d365_staging schema
# ---------------------------------------------------------------------------

class D365ExtractionRun(Base):
    """Header: one row per extraction batch from D365 F&O."""
    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_d365_ext_tenant", "tenant_id", "extraction_date"),
        {"schema": "d365_staging"},
    )

    id = Column(PG_UUID, primary_key=True, server_default=func.gen_random_uuid())
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(Integer, ForeignKey("erp_connections.id", ondelete="SET NULL"), nullable=True)

    erp_variant = Column(String(30), nullable=False)       # D365_FO, D365_SCM
    extraction_date = Column(Date, nullable=False)
    source_method = Column(String(20), nullable=False)     # odata, dmf, csv
    data_area_id = Column(String(10), nullable=True)       # Legal entity: usmf, demf, etc.

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


class D365StagingRow(Base):
    """Detail: one row per D365 entity record, stored as JSONB."""
    __tablename__ = "rows"
    __table_args__ = (
        Index("ix_d365_rows_ext", "extraction_id"),
        Index("ix_d365_rows_tbl", "tenant_id", "d365_entity", "extraction_id"),
        Index("ix_d365_rows_bk", "tenant_id", "d365_entity", "business_key"),
        {"schema": "d365_staging"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    extraction_id = Column(PG_UUID, ForeignKey("d365_staging.extraction_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Integer, nullable=False)

    d365_entity = Column(String(60), nullable=False)
    data_category = Column(String(20), nullable=False)
    row_data = Column(JSONB, nullable=False)
    row_hash = Column(String(32), nullable=False)
    business_key = Column(String(200), nullable=True)

    is_staged = Column(Boolean, default=False)
    staged_at = Column(DateTime, nullable=True)
    staging_error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class D365TableSchema(Base):
    """Tracks column sets per D365 entity per tenant for schema drift detection."""
    __tablename__ = "table_schemas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "d365_entity", name="uq_d365_tbl_schema"),
        {"schema": "d365_staging"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    d365_entity = Column(String(60), nullable=False)
    columns = Column(JSONB, nullable=False)
    key_fields = Column(JSONB, nullable=False)
    data_category = Column(String(20), nullable=False)
    row_count = Column(Integer, default=0)
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now())
