"""
Infor M3 / CloudSuite Data Staging Models — Schema: infor_staging

Separate PostgreSQL schema for raw Infor data.
Follows the same pattern as b1_staging.py / d365_staging.py / odoo_staging.py:
  extraction_runs  — Header: one row per extraction batch
  rows             — Detail: raw Infor data in JSONB (one row per M3 record)
  table_schemas    — Column tracking per M3 table per tenant

Data flow:
  Infor M3 (ION API Gateway / M3 MI REST / CSV) → infor_staging.rows
  → InforConfigBuilder → public.* AWS SC entity tables

M3 MI Program Reference:
  Browse available APIs in M3: MRS001 (programs) / MRS002 (transactions)
  ION API Gateway SDK: https://github.com/infor-cloud/ion-api-sdk

OAGIS Schema Reference:
  Public XSD schemas: https://schema.infor.com/InforOAGIS/Nouns/
  ~196 nouns, verb+noun BOD pattern (Sync, Process, Get, Show)

Demo company: Midwest Industrial Supply (synthetic)
"""

from enum import Enum as PyEnum
from typing import Dict, List


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class InforDataCategory(str, PyEnum):
    """Classification of Infor entities by refresh cadence."""
    MASTER = "master"           # Weekly: items, warehouses, BOMs, suppliers, customers
    TRANSACTION = "transaction" # Daily: orders, production, shipments, receipts
    CDC = "cdc"                 # Hourly: inventory movements, quality, maintenance


class InforSourceMethod(str, PyEnum):
    """How data was obtained from Infor."""
    ION_API = "ion_api"          # ION API Gateway REST (primary)
    M3_MI = "m3_mi"              # M3 MI Programs via ION Gateway
    BOD_XML = "bod_xml"          # OAGIS BOD XML messages
    CSV = "csv"                  # Manual CSV/JSON export


# ---------------------------------------------------------------------------
# Infor Entity Registry — canonical metadata for all supported entities
# ---------------------------------------------------------------------------
#
# Each entity maps to:
#   - mi_program: M3 MI program name for data extraction
#   - list_transaction: Default "List" transaction for bulk extraction
#   - get_transaction: "Get" transaction for single-record lookup
#   - oagis_noun: Corresponding OAGIS noun (for BOD XML mapping)
#   - keys: Primary key fields (M3 field codes)
#   - category: master / transaction / cdc
#   - description: Business description
#
# M3 MI Program naming convention:
#   {Module}{Seq}MI — e.g., MMS200MI (Material Mgmt System, program 200)
#   Common modules: MMS (Materials), CRS (Cross-Reference), PPS (Purchase),
#   OIS (Order Information), MWS (Warehouse), PMS (Production)

INFOR_ENTITY_REGISTRY: Dict[str, Dict] = {
    # =========================================================================
    # MASTER DATA
    # =========================================================================

    # --- Organization & Locations ---
    "Company": {
        "category": "master",
        "mi_program": "CRS610MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetBasicData",
        "oagis_noun": "Organization",
        "keys": ["CONO"],
        "description": "Company / Legal Entity",
    },
    "Division": {
        "category": "master",
        "mi_program": "CRS003MI",
        "list_transaction": "LstDivisions",
        "get_transaction": "GetBasicData",
        "oagis_noun": "Organization",
        "keys": ["CONO", "DIVI"],
        "description": "Division (business unit within company)",
    },
    "Warehouse": {
        "category": "master",
        "mi_program": "MMS005MI",
        "list_transaction": "LstWarehouses",
        "get_transaction": "GetWarehouse",
        "oagis_noun": "Location",
        "keys": ["WHLO"],
        "description": "Warehouses / Storage Locations / Plants",
    },

    # --- Suppliers & Customers ---
    "Supplier": {
        "category": "master",
        "mi_program": "CRS620MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetBasicData",
        "oagis_noun": "SupplierPartyMaster",
        "keys": ["SUNO"],
        "description": "Suppliers / Vendors",
    },
    "Customer": {
        "category": "master",
        "mi_program": "CRS610MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetBasicData",
        "oagis_noun": "CustomerPartyMaster",
        "keys": ["CUNO"],
        "description": "Customers",
    },

    # --- Items (Products / Materials) ---
    "ItemMaster": {
        "category": "master",
        "mi_program": "MMS200MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetItmBasic",
        "oagis_noun": "ItemMaster",
        "keys": ["ITNO"],
        "description": "Item Master — products, raw materials, services",
    },
    "ItemWarehouse": {
        "category": "master",
        "mi_program": "MMS002MI",
        "list_transaction": "LstItemWhse",
        "get_transaction": "GetItemWhse",
        "oagis_noun": "ItemMaster",
        "keys": ["ITNO", "WHLO"],
        "description": "Item-Warehouse settings (planning params, reorder point)",
    },
    "ItemGroup": {
        "category": "master",
        "mi_program": "CRS025MI",
        "list_transaction": "LstItemGroups",
        "get_transaction": "GetItemGroup",
        "oagis_noun": "CodeDefinition",
        "keys": ["ITGR"],
        "description": "Item Groups (product categories)",
    },

    # --- Pricing ---
    "PriceList": {
        "category": "master",
        "mi_program": "OIS017MI",
        "list_transaction": "LstPriceList",
        "get_transaction": "GetBasePrice",
        "oagis_noun": "PriceList",
        "keys": ["PRRF", "ITNO", "CUNO"],
        "description": "Price Lists and customer-specific pricing",
    },

    # --- Bills of Material ---
    "BillOfMaterial": {
        "category": "master",
        "mi_program": "PDS001MI",
        "list_transaction": "LstMaterials",
        "get_transaction": "Get",
        "oagis_noun": "BillOfMaterials",
        "keys": ["PRNO", "MTNO", "MSEQ"],
        "description": "Product Structure / BOM components",
    },

    # --- Work Centers / Resources ---
    "WorkCenter": {
        "category": "master",
        "mi_program": "PDS010MI",
        "list_transaction": "LstWorkCenters",
        "get_transaction": "Get",
        "oagis_noun": "WorkCenter",
        "keys": ["PLGR"],
        "description": "Work Centers / Resources (machines, labor)",
    },
    "Routing": {
        "category": "master",
        "mi_program": "PDS002MI",
        "list_transaction": "LstOperations",
        "get_transaction": "Get",
        "oagis_noun": "BillOfResources",
        "keys": ["PRNO", "OPNO"],
        "description": "Manufacturing Routings / Operations",
    },

    # =========================================================================
    # TRANSACTION DATA
    # =========================================================================

    # --- Purchasing ---
    "PurchaseOrder": {
        "category": "transaction",
        "mi_program": "PPS200MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetHead",
        "oagis_noun": "PurchaseOrder",
        "keys": ["PUNO"],
        "description": "Purchase Orders (header)",
    },
    "PurchaseOrderLine": {
        "category": "transaction",
        "mi_program": "PPS200MI",
        "list_transaction": "LstLine",
        "get_transaction": "GetLine",
        "oagis_noun": "PurchaseOrder",
        "keys": ["PUNO", "PNLI", "PNLS"],
        "description": "Purchase Order Lines",
    },
    "PurchaseAgreement": {
        "category": "master",
        "mi_program": "PPS100MI",
        "list_transaction": "LstAgreement",
        "get_transaction": "GetAgreement",
        "oagis_noun": "PurchaseOrder",
        "keys": ["AGNB"],
        "description": "Blanket / Framework Purchase Agreements",
    },

    # --- Sales ---
    "SalesOrder": {
        "category": "transaction",
        "mi_program": "OIS100MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetHead",
        "oagis_noun": "SalesOrder",
        "keys": ["ORNO"],
        "description": "Customer Orders (header)",
    },
    "SalesOrderLine": {
        "category": "transaction",
        "mi_program": "OIS100MI",
        "list_transaction": "LstLine",
        "get_transaction": "GetLine",
        "oagis_noun": "SalesOrder",
        "keys": ["ORNO", "PONR", "POSX"],
        "description": "Customer Order Lines",
    },

    # --- Production ---
    "ProductionOrder": {
        "category": "transaction",
        "mi_program": "PMS100MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "Get",
        "oagis_noun": "ProductionOrder",
        "keys": ["MFNO"],
        "description": "Manufacturing Orders (production orders)",
    },
    "ProductionOrderComponent": {
        "category": "transaction",
        "mi_program": "PMS100MI",
        "list_transaction": "LstMaterial",
        "get_transaction": "GetMtrl",
        "oagis_noun": "ProductionOrder",
        "keys": ["MFNO", "MSEQ"],
        "description": "Manufacturing Order material components",
    },
    "ProductionOrderOperation": {
        "category": "transaction",
        "mi_program": "PMS100MI",
        "list_transaction": "LstOperation",
        "get_transaction": "GetOper",
        "oagis_noun": "ProductionOrder",
        "keys": ["MFNO", "OPNO"],
        "description": "Manufacturing Order operations / routing steps",
    },

    # --- Delivery / Shipment ---
    "Delivery": {
        "category": "transaction",
        "mi_program": "MWS410MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetHead",
        "oagis_noun": "Shipment",
        "keys": ["CONN"],
        "description": "Deliveries / Shipments (outbound)",
    },
    "DeliveryLine": {
        "category": "transaction",
        "mi_program": "MWS410MI",
        "list_transaction": "LstLine",
        "get_transaction": "GetLine",
        "oagis_noun": "Shipment",
        "keys": ["CONN", "DLIX"],
        "description": "Delivery / Shipment lines",
    },

    # --- Goods Receipt ---
    "GoodsReceipt": {
        "category": "transaction",
        "mi_program": "PPS300MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "GetHead",
        "oagis_noun": "ReceiveDelivery",
        "keys": ["REPN"],
        "description": "Goods Receipt (from PO)",
    },

    # --- Stock Transfer ---
    "TransferOrder": {
        "category": "transaction",
        "mi_program": "MMS100MI",
        "list_transaction": "LstTransfer",
        "get_transaction": "GetTransfer",
        "oagis_noun": "Transfer",
        "keys": ["RIDN"],
        "description": "Stock Transfers / Distribution Orders",
    },

    # --- Forecast ---
    "Forecast": {
        "category": "transaction",
        "mi_program": "FCS350MI",
        "list_transaction": "LstForecast",
        "get_transaction": "GetForecast",
        "oagis_noun": "PlanningSchedule",
        "keys": ["ITNO", "WHLO", "FRDT"],
        "description": "Demand Forecast",
    },

    # --- MRP / Planning ---
    "PlannedOrder": {
        "category": "transaction",
        "mi_program": "PPS170MI",
        "list_transaction": "LstPlanned",
        "get_transaction": "GetPlanned",
        "oagis_noun": "PlannedPurchaseOrder",
        "keys": ["PLPN"],
        "description": "MRP Planned Orders (planned POs, MOs, TOs)",
    },

    # =========================================================================
    # CDC (Change Data Capture)
    # =========================================================================
    "InventoryBalance": {
        "category": "cdc",
        "mi_program": "MMS235MI",
        "list_transaction": "LstInvBal",
        "get_transaction": "GetInvBal",
        "oagis_noun": "InventoryCount",
        "keys": ["ITNO", "WHLO"],
        "description": "Inventory Balances (on-hand, allocated, in-transit)",
    },
    "InventoryTransaction": {
        "category": "cdc",
        "mi_program": "MMS080MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "Get",
        "oagis_noun": "InventoryAdjustment",
        "keys": ["TRDT", "TRNR"],
        "description": "Inventory Transactions (receipts, issues, adjustments)",
    },
    "LotMaster": {
        "category": "cdc",
        "mi_program": "MMS235MI",
        "list_transaction": "LstLot",
        "get_transaction": "GetLot",
        "oagis_noun": "InventoryCount",
        "keys": ["ITNO", "BANO"],
        "description": "Lot / Batch Number tracking",
    },
    "QualityInspection": {
        "category": "cdc",
        "mi_program": "QMS300MI",
        "list_transaction": "LstInspection",
        "get_transaction": "GetInspection",
        "oagis_noun": "QualityTestResult",
        "keys": ["QRID"],
        "description": "Quality Inspection results",
    },
    "MaintenanceOrder": {
        "category": "cdc",
        "mi_program": "MOS100MI",
        "list_transaction": "LstByNumber",
        "get_transaction": "Get",
        "oagis_noun": "MaintenanceOrder",
        "keys": ["MWNO"],
        "description": "Maintenance / Service Orders",
    },
}


# ---------------------------------------------------------------------------
# Convenience lookups
# ---------------------------------------------------------------------------

INFOR_MASTER_ENTITIES = [k for k, v in INFOR_ENTITY_REGISTRY.items() if v["category"] == "master"]
INFOR_TRANSACTION_ENTITIES = [k for k, v in INFOR_ENTITY_REGISTRY.items() if v["category"] == "transaction"]
INFOR_CDC_ENTITIES = [k for k, v in INFOR_ENTITY_REGISTRY.items() if v["category"] == "cdc"]

# Entity name → OAGIS noun name
INFOR_ENTITY_TO_NOUN: Dict[str, str] = {
    k: v.get("oagis_noun", k) for k, v in INFOR_ENTITY_REGISTRY.items()
}

# Entity name → M3 MI program
INFOR_ENTITY_TO_MI: Dict[str, str] = {
    k: v.get("mi_program", "") for k, v in INFOR_ENTITY_REGISTRY.items()
}
