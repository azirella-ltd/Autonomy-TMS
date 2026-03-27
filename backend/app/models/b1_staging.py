"""
SAP Business One (B1) Data Staging Models — Schema: b1_staging

Separate PostgreSQL schema for raw SAP Business One data.
Follows the same pattern as sap_staging.py / d365_staging.py / odoo_staging.py:
  extraction_runs  — Header: one row per extraction batch
  rows             — Detail: raw B1 data in JSONB (one row per Service Layer entity record)
  table_schemas    — Column tracking per B1 table per tenant

Data flow:
  B1 (Service Layer OData v4 / DI API / CSV) → b1_staging.rows → B1ConfigBuilder → public.* AWS SC entity tables

SAP Business One Service Layer API Reference:
  https://help.sap.com/doc/056f69366b5345a386bb8149f1700c19/10.0/en-US/Service%20Layer%20API%20Reference.html

Demo company: OEC Computers (pre-loaded in B1 demo databases)
"""

from enum import Enum as PyEnum
from typing import Dict, List


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class B1DataCategory(str, PyEnum):
    """Classification of B1 entities by refresh cadence."""
    MASTER = "master"           # Weekly: items, BPs, BOMs, warehouses, price lists
    TRANSACTION = "transaction" # Daily: orders, invoices, deliveries, production
    CDC = "cdc"                 # Hourly: inventory postings, goods receipts, status changes


class B1SourceMethod(str, PyEnum):
    """How data was obtained from SAP Business One."""
    SERVICE_LAYER = "service_layer"  # OData v4 REST API (primary)
    DI_API = "di_api"                # DI API / DI Server (SDK, .NET/Java)
    CSV = "csv"                      # Manual CSV export


# ---------------------------------------------------------------------------
# B1 Entity Registry — canonical metadata for all supported B1 tables
# ---------------------------------------------------------------------------
#
# Table naming: B1 uses "O" prefix for header tables, detail tables use
# different prefixes (e.g., RDR1 = sales order lines for ORDR).
#
# Service Layer entity names differ from DB table names:
#   OCRD → BusinessPartners, OITM → Items, ORDR → Orders, OPOR → PurchaseOrders
#   We use Service Layer entity names as the registry key.

B1_ENTITY_REGISTRY: Dict[str, Dict] = {
    # =========================================================================
    # MASTER DATA
    # =========================================================================

    # --- Organization & Locations ---
    "Companies": {
        "category": "master",
        "keys": ["DbName"],
        "description": "Company database (one per B1 tenant)",
        "db_table": "OADM",
    },
    "Warehouses": {
        "category": "master",
        "keys": ["WarehouseCode"],
        "description": "Warehouses / Storage Locations",
        "db_table": "OWHS",
    },
    "BinLocations": {
        "category": "master",
        "keys": ["AbsEntry"],
        "description": "Bin locations within warehouses",
        "db_table": "OBIN",
    },

    # --- Business Partners (Customers + Vendors) ---
    "BusinessPartners": {
        "category": "master",
        "keys": ["CardCode"],
        "description": "Business Partners (Customers, Vendors, Leads)",
        "db_table": "OCRD",
    },
    "BusinessPartnerGroups": {
        "category": "master",
        "keys": ["Code"],
        "description": "BP Grouping codes (customer/vendor groups)",
        "db_table": "OCRG",
    },

    # --- Items (Products / Materials) ---
    "Items": {
        "category": "master",
        "keys": ["ItemCode"],
        "description": "Item Master — products, raw materials, services",
        "db_table": "OITM",
    },
    "ItemGroups": {
        "category": "master",
        "keys": ["Number"],
        "description": "Item Groups (product categories)",
        "db_table": "OITB",
    },
    "ItemWarehouseInfoCollection": {
        "category": "master",
        "keys": ["ItemCode", "WarehouseCode"],
        "description": "Item-Warehouse settings (reorder point, min/max qty)",
        "db_table": "OITW",
    },
    "UnitOfMeasurements": {
        "category": "master",
        "keys": ["AbsEntry"],
        "description": "Units of Measurement",
        "db_table": "OUOM",
    },
    "UnitOfMeasurementGroups": {
        "category": "master",
        "keys": ["AbsEntry"],
        "description": "UoM Groups (conversion groups)",
        "db_table": "OUGP",
    },

    # --- Pricing ---
    "PriceLists": {
        "category": "master",
        "keys": ["PriceListNo"],
        "description": "Price Lists",
        "db_table": "OPLN",
    },
    "SpecialPrices": {
        "category": "master",
        "keys": ["CardCode", "ItemCode"],
        "description": "BP-specific special prices",
        "db_table": "OSPP",
    },

    # --- Bills of Material ---
    "ProductTrees": {
        "category": "master",
        "keys": ["TreeCode"],
        "description": "Bill of Materials (Product Trees / BOMs)",
        "db_table": "OITT",
    },
    "ProductTreeLines": {
        "category": "master",
        "keys": ["TreeCode", "LineNum"],
        "description": "BOM component lines",
        "db_table": "ITT1",
    },

    # --- Resources / Work Centers ---
    "Resources": {
        "category": "master",
        "keys": ["ResCode"],
        "description": "Resources (machines, labor, work centers)",
        "db_table": "ORES",
    },
    "ResourceCapacities": {
        "category": "master",
        "keys": ["AbsEntry"],
        "description": "Resource capacity planning data",
        "db_table": "ORSC",
    },

    # =========================================================================
    # TRANSACTION DATA
    # =========================================================================

    # --- Sales ---
    "Orders": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Sales Orders",
        "db_table": "ORDR",
    },
    "DeliveryNotes": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Deliveries / Shipments",
        "db_table": "ODLN",
    },
    "Invoices": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "A/R Invoices",
        "db_table": "OINV",
    },
    "Returns": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Sales Returns",
        "db_table": "ORDN",
    },

    # --- Purchasing ---
    "PurchaseOrders": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Purchase Orders",
        "db_table": "OPOR",
    },
    "GoodsReturns": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Purchase Returns (goods returned to vendor)",
        "db_table": "ORPD",
    },
    "PurchaseDeliveryNotes": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Goods Receipt POs",
        "db_table": "OPDN",
    },
    "PurchaseInvoices": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "A/P Invoices",
        "db_table": "OPCH",
    },
    "PurchaseRequests": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Purchase Requests",
        "db_table": "OPRQ",
    },

    # --- Production ---
    "ProductionOrders": {
        "category": "transaction",
        "keys": ["AbsoluteEntry"],
        "description": "Production Orders / Manufacturing Orders",
        "db_table": "OWOR",
    },

    # --- Inventory ---
    "InventoryTransferRequests": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Inventory Transfer Requests",
        "db_table": "OWTQ",
    },
    "StockTransfers": {
        "category": "transaction",
        "keys": ["DocEntry"],
        "description": "Inventory Transfers (executed)",
        "db_table": "OWTR",
    },

    # --- Blanket Agreements ---
    "BlanketAgreements": {
        "category": "master",
        "keys": ["AgreementNo"],
        "description": "Blanket/Framework Agreements (long-term vendor/customer contracts)",
        "db_table": "OAGL",
    },

    # --- Forecasting ---
    "ForecastReport": {
        "category": "transaction",
        "keys": ["AbsEntry"],
        "description": "Demand Forecast (MRP forecast data)",
        "db_table": "OFCT",
    },

    # --- MRP Results ---
    "MRPResults": {
        "category": "transaction",
        "keys": ["AbsEntry"],
        "description": "MRP Run Results (planned orders from MRP wizard)",
        "db_table": "OMRP",
    },

    # =========================================================================
    # CDC (Change Data Capture)
    # =========================================================================
    "InventoryGenEntries": {
        "category": "cdc",
        "keys": ["DocEntry"],
        "description": "Inventory Postings (goods issue/receipt, adjustments)",
        "db_table": "OIGE",
    },
    "InventoryGenExits": {
        "category": "cdc",
        "keys": ["DocEntry"],
        "description": "Inventory Exits (goods issues)",
        "db_table": "OIGE",
    },
    "StockTakings": {
        "category": "cdc",
        "keys": ["AbsEntry"],
        "description": "Physical Inventory Counts",
        "db_table": "OINC",
    },
    "BatchNumberDetails": {
        "category": "cdc",
        "keys": ["AbsEntry"],
        "description": "Batch / Lot details",
        "db_table": "OBTN",
    },
    "SerialNumberDetails": {
        "category": "cdc",
        "keys": ["AbsEntry"],
        "description": "Serial Number tracking",
        "db_table": "OSRN",
    },
    "QualityTests": {
        "category": "cdc",
        "keys": ["AbsEntry"],
        "description": "Quality Control tests (if QC module active)",
        "db_table": "OQCN",
    },
    "ServiceCalls": {
        "category": "cdc",
        "keys": ["ServiceCallID"],
        "description": "Service Calls (maintenance/field service requests)",
        "db_table": "OSCL",
    },
}

# Convenience lookups
B1_MASTER_ENTITIES = [k for k, v in B1_ENTITY_REGISTRY.items() if v["category"] == "master"]
B1_TRANSACTION_ENTITIES = [k for k, v in B1_ENTITY_REGISTRY.items() if v["category"] == "transaction"]
B1_CDC_ENTITIES = [k for k, v in B1_ENTITY_REGISTRY.items() if v["category"] == "cdc"]

# Service Layer entity name → DB table name
B1_ENTITY_TO_TABLE: Dict[str, str] = {
    k: v.get("db_table", k) for k, v in B1_ENTITY_REGISTRY.items()
}
