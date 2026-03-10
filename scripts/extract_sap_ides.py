#!/usr/bin/env python3
"""
SAP S/4HANA IDES Data Extraction Script

Extracts ALL master data AND transactional data from SAP S/4HANA 2025 FAA
for Autonomy tenant configuration and operational data population.

Target: Company Code 1710 (US), Plant 1710 (Palo Alto)

Categories extracted:
  1. Master Data — Sites, Products, BOMs, Vendors, Customers, Routings, Capacities
  2. Inventory Policies — MRP settings, safety stock, lot sizing
  3. Demand — Forecasts, independent requirements, sales orders
  4. Procurement — Purchase orders, schedule lines, purchasing info records
  5. Manufacturing — Production orders, confirmations, component reservations
  6. Distribution — Deliveries (inbound/outbound), transfer orders
  7. Quality — Notifications, inspection orders, results, dispositions
  8. Maintenance — Work orders, plans, history, confirmations
  9. Subcontracting — Subcontracting POs, components sent
 10. Inventory — Stock on hand, stock movements, reservations

Usage:
    python scripts/extract_sap_ides.py \\
        --host <SAP_PUBLIC_IP> \\
        --user DDIC \\
        --password <PASSWORD> \\
        --client 100

    # Or use environment variables:
    SAP_HOST=<IP> SAP_USER=DDIC SAP_PASS=<PW> python scripts/extract_sap_ides.py

    # Test connection only:
    python scripts/extract_sap_ides.py --host <IP> --user DDIC --password <PW> --dry-run

    # Extract specific categories only:
    python scripts/extract_sap_ides.py --host <IP> --user DDIC --password <PW> \\
        --categories master demand procurement

Output: imports/SAP/IDES_1710/*.csv + MANIFEST.json
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Suppress SSL warnings for self-signed certs on FAA
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================================
# Configuration
# ============================================================================

OUTPUT_DIR = Path(__file__).parent.parent / "imports" / "SAP" / "IDES_1710"

COMPANY_CODE = "1710"
PLANT = "1710"
SALES_ORG = "1710"
PURCH_ORG = "1710"

# All extraction categories
ALL_CATEGORIES = [
    "master",          # Organization, sites, products, BOMs, trading partners
    "inventory_policy",# MRP settings, safety stock, lot sizing
    "sourcing",        # Vendor products, lead times, source lists
    "demand",          # Forecasts, sales orders + items
    "procurement",     # Purchase orders + items + schedule lines
    "manufacturing",   # Production orders, confirmations, component reservations
    "distribution",    # Deliveries (inbound/outbound), transfer orders
    "quality",         # Notifications, inspection orders, results
    "maintenance",     # Work orders, plans, confirmations
    "subcontracting",  # Subcontracting POs + components
    "inventory",       # Stock on hand, stock movements, reservations
]


# ============================================================================
# OData Entity Definitions — organized by category
#
# Each entry maps to one CSV output file. The script iterates through all
# entries in the requested categories and extracts via OData API.
#
# S/4HANA 2025 OData services:
#   - API_PRODUCT_SRV (materials, plant data, storage locations)
#   - API_BUSINESS_PARTNER (vendors, customers)
#   - API_BILL_OF_MATERIAL_SRV_01 (BOMs)
#   - API_PURCHASEORDER_PROCESS_SRV (POs)
#   - API_SALES_ORDER_SRV (sales orders)
#   - API_MATERIAL_STOCK_SRV (inventory)
#   - API_INFORECORD_PROCESS_SRV (purchasing info records)
#   - API_PLANT_SRV (plants)
#   - API_WORK_CENTERS (work centers)
#   - API_PLANNED_ORDERS (planned orders / MRP output)
#   - API_PRODUCTION_ORDERS (manufacturing orders)
#   - API_QUALITY_NOTIFICATION (quality)
#   - API_MAINTNOTIFICATION (maintenance)
#   - API_RESERVATION_DOCUMENT_SRV (reservations)
#   - API_MATERIAL_DOCUMENT_SRV (goods movements)
#   - API_INBOUND_DELIVERY_SRV_02 (inbound deliveries)
#   - API_OUTBOUND_DELIVERY_SRV_02 (outbound deliveries)
# ============================================================================

ODATA_EXTRACTIONS = {

    # ========================================================================
    # CATEGORY: master — Organization, Sites, Products, BOMs, Trading Partners
    # ========================================================================
    "master": [
        {
            "name": "plants",
            "service": "/sap/opu/odata/sap/API_PLANT_SRV",
            "entity": "A_Plant",
            "description": "Plants / Sites (T001W)",
            "filters": [],
            "select": [
                "Plant", "PlantName", "CompanyCode", "FactoryCalendar",
                "Street", "City", "PostalCode", "Region", "Country",
            ],
            "filename": "T001W_plants.csv",
        },
        {
            "name": "materials",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_Product",
            "description": "Materials (MARA)",
            "filters": [],
            "select": [
                "Product", "ProductType", "BaseUnit", "ProductGroup",
                "GrossWeight", "NetWeight", "WeightUnit", "Volume", "VolumeUnit",
                "IndustrySector", "CreationDate", "LastChangeDate",
                "ProductStandardID", "InternationalArticleNumberCat",
            ],
            "filename": "MARA_materials.csv",
        },
        {
            "name": "material_descriptions",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductDescription",
            "description": "Material Descriptions (MAKT)",
            "filters": ["Language eq 'EN'"],
            "select": ["Product", "Language", "ProductDescription"],
            "filename": "MAKT_descriptions.csv",
        },
        {
            "name": "material_plant",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductPlant",
            "description": "Material-Plant Data (MARC) — MRP, procurement type",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "Product", "Plant", "PurchasingGroup", "MRPType",
                "MRPController", "MRPResponsible", "ReorderThresholdQuantity",
                "PlanningTimeFence", "LotSizingProcedure",
                "MinimumLotSizeQuantity", "MaximumLotSizeQuantity",
                "FixedLotSizeQuantity", "SafetyStock",
                "ProcurementType", "SpecialProcurementType",
                "PlannedDeliveryDurationInDays", "GoodsReceiptDuration",
                "IsBatchManagementRequired",
            ],
            "filename": "MARC_material_plant.csv",
        },
        {
            "name": "material_valuation",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductValuation",
            "description": "Material Valuation (MBEW) — unit costs",
            "filters": [f"ValuationArea eq '{PLANT}'"],
            "select": [
                "Product", "ValuationArea", "ValuationClass",
                "StandardPrice", "MovingAveragePrice", "PriceControl",
                "PriceDeterminationControl",
            ],
            "filename": "MBEW_valuation.csv",
        },
        {
            "name": "material_sales",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductSalesDelivery",
            "description": "Material Sales Data (MVKE)",
            "filters": [f"ProductSalesOrg eq '{SALES_ORG}'"],
            "select": [
                "Product", "ProductSalesOrg", "ProductDistributionChnl",
                "ProductHierarchy", "DeliveryNoteProcMinDelivQty",
                "ItemCategoryGroup",
            ],
            "filename": "MVKE_sales_data.csv",
        },
        {
            "name": "uom_conversions",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductUnitsOfMeasure",
            "description": "UOM Conversions (MARM)",
            "filters": [],
            "select": [
                "Product", "AlternativeUnit", "QuantityNumerator",
                "QuantityDenominator", "GrossWeight", "Volume",
            ],
            "filename": "MARM_uom_conversions.csv",
        },
        {
            "name": "storage_locations",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductStorageLocation",
            "description": "Storage Locations (T001L)",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": ["Product", "Plant", "StorageLocation"],
            "filename": "T001L_storage_locations.csv",
        },
        {
            "name": "bom_items",
            "service": "/sap/opu/odata/sap/API_BILL_OF_MATERIAL_SRV_01",
            "entity": "MaterialBOMItem",
            "description": "BOM Items (STPO) — product recipes",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "BillOfMaterial", "BillOfMaterialVariant",
                "BillOfMaterialItemNodeNumber", "BillOfMaterialComponent",
                "BOMItemQuantity", "ComponentUnit", "BOMItemCategory",
                "Plant", "BillOfMaterialItemNumber",
            ],
            "filename": "STPO_bom_items.csv",
        },
        {
            "name": "bom_headers",
            "service": "/sap/opu/odata/sap/API_BILL_OF_MATERIAL_SRV_01",
            "entity": "MaterialBOM",
            "description": "BOM Headers (STKO)",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "BillOfMaterial", "BillOfMaterialVariant", "Material",
                "Plant", "BOMHeaderBaseUnit", "BOMHeaderQuantityInBaseUnit",
                "BillOfMaterialStatus", "IsMultipleBOMAlt",
            ],
            "filename": "STKO_bom_headers.csv",
        },
        {
            "name": "vendors",
            "service": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
            "entity": "A_BusinessPartner",
            "description": "Vendors / Suppliers (LFA1 via BP)",
            "filters": ["BusinessPartnerGrouping eq 'BPVN'"],
            "select": [
                "BusinessPartner", "BusinessPartnerName",
                "BusinessPartnerCategory", "Industry",
                "Country", "Region", "CityName", "PostalCode", "StreetName",
            ],
            "filename": "LFA1_vendors.csv",
            "max_records": 1000,
            "fallback_filters": ["BusinessPartnerCategory eq '2'"],
        },
        {
            "name": "customers",
            "service": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
            "entity": "A_BusinessPartner",
            "description": "Customers (KNA1 via BP)",
            "filters": ["BusinessPartnerGrouping eq 'BPCU'"],
            "select": [
                "BusinessPartner", "BusinessPartnerName",
                "BusinessPartnerCategory", "Industry",
                "Country", "Region", "CityName", "PostalCode", "StreetName",
            ],
            "filename": "KNA1_customers.csv",
            "max_records": 1000,
            "fallback_filters": ["BusinessPartnerCategory eq '1'"],
        },
        {
            "name": "bp_addresses",
            "service": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
            "entity": "A_BusinessPartnerAddress",
            "description": "Business Partner Addresses (ADRC)",
            "filters": [],
            "select": [
                "BusinessPartner", "AddressID",
                "Country", "Region", "CityName", "PostalCode",
                "StreetName", "HouseNumber",
            ],
            "filename": "ADRC_addresses.csv",
            "max_records": 2000,
        },
        {
            "name": "work_centers",
            "service": "/sap/opu/odata/sap/API_WORK_CENTERS",
            "entity": "WorkCenters",
            "description": "Work Centers / Resources (CRHD)",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "WorkCenterInternalID", "WorkCenterTypeCode", "WorkCenter",
                "Plant", "WorkCenterCategoryCode", "WorkCenterDesc",
            ],
            "filename": "CRHD_work_centers.csv",
        },
    ],

    # ========================================================================
    # CATEGORY: inventory_policy — MRP settings, safety stock, lot sizing
    # (Already extracted in MARC, but this gives a focused view)
    # ========================================================================
    "inventory_policy": [
        # MARC is already in master; this is a placeholder for any
        # additional inv policy tables. The key fields are:
        # DISMM (MRP type), DISPO (controller), DISLS (lot size),
        # EISBE (safety stock), MINBE (reorder point), BSTRF (fixed qty),
        # PLIFZ (planned lead time), WEBAZ (GR processing time)
        # Those are extracted via material_plant in the master category.
    ],

    # ========================================================================
    # CATEGORY: sourcing — Vendor products, lead times, source lists
    # ========================================================================
    "sourcing": [
        {
            "name": "purchasing_info_records",
            "service": "/sap/opu/odata/sap/API_INFORECORD_PROCESS_SRV",
            "entity": "A_PurchasingInfoRecord",
            "description": "Purchasing Info Records (EINA/EINE) — vendor catalog",
            "filters": [],
            "select": [
                "PurchasingInfoRecord", "Supplier", "Material", "Plant",
                "PurchasingOrganization", "PurchasingInfoRecordCategory",
                "NetPriceAmount", "PriceQuantity", "NetPriceQuantityUnit",
                "PlannedDeliveryDurationInDays", "StandardPurchasingOrderQty",
                "MinimumPurchaseOrderQuantity",
            ],
            "filename": "EINE_purchasing_info.csv",
        },
        {
            "name": "source_list",
            "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
            "entity": "A_ProductSupplyPlanning",
            "description": "Supply Planning / Source List (EORD-like)",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "Product", "Plant", "MRPType", "ProcurementType",
                "SpecialProcurementType",
            ],
            "filename": "EORD_source_list.csv",
        },
    ],

    # ========================================================================
    # CATEGORY: demand — Forecasts, sales orders + items
    # ========================================================================
    "demand": [
        {
            "name": "sales_orders",
            "service": "/sap/opu/odata/sap/API_SALES_ORDER_SRV",
            "entity": "A_SalesOrder",
            "description": "Sales Orders (VBAK) — customer demand",
            "filters": [f"SalesOrganization eq '{SALES_ORG}'"],
            "select": [
                "SalesOrder", "SalesOrderType", "SalesOrganization",
                "DistributionChannel", "OrganizationDivision",
                "SoldToParty", "CreationDate", "SalesOrderDate",
                "RequestedDeliveryDate", "TotalNetAmount",
                "TransactionCurrency", "OverallSDProcessStatus",
            ],
            "filename": "VBAK_sales_orders.csv",
            "max_records": 5000,
        },
        {
            "name": "sales_order_items",
            "service": "/sap/opu/odata/sap/API_SALES_ORDER_SRV",
            "entity": "A_SalesOrderItem",
            "description": "Sales Order Items (VBAP) — line-level demand",
            "filters": [],
            "select": [
                "SalesOrder", "SalesOrderItem", "Material", "Plant",
                "RequestedQuantity", "RequestedQuantityUnit",
                "NetAmount", "TransactionCurrency",
                "SDProcessStatus", "DeliveryStatus",
            ],
            "filename": "VBAP_sales_order_items.csv",
            "max_records": 20000,
        },
        {
            "name": "sales_order_schedule_lines",
            "service": "/sap/opu/odata/sap/API_SALES_ORDER_SRV",
            "entity": "A_SalesOrderScheduleLine",
            "description": "Sales Order Schedule Lines (VBEP) — delivery dates",
            "filters": [],
            "select": [
                "SalesOrder", "SalesOrderItem", "ScheduleLine",
                "RequestedDeliveryDate", "ScheduleLineOrderQuantity",
                "ConfdOrderQtyByMatlAvailCheck", "DeliveredQtyInOrderQtyUnit",
                "OpenConfdDelivQtyInOrdQtyUnit",
            ],
            "filename": "VBEP_schedule_lines.csv",
            "max_records": 20000,
        },
    ],

    # ========================================================================
    # CATEGORY: procurement — Purchase orders + items + schedule lines
    # ========================================================================
    "procurement": [
        {
            "name": "purchase_orders",
            "service": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
            "entity": "A_PurchaseOrder",
            "description": "Purchase Orders (EKKO)",
            "filters": [f"CompanyCode eq '{COMPANY_CODE}'"],
            "select": [
                "PurchaseOrder", "PurchaseOrderType", "Supplier",
                "CompanyCode", "PurchasingOrganization", "PurchasingGroup",
                "CreationDate", "PurchaseOrderDate",
                "DocumentCurrency", "NetPriceAmount",
            ],
            "filename": "EKKO_purchase_orders.csv",
            "max_records": 5000,
        },
        {
            "name": "purchase_order_items",
            "service": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
            "entity": "A_PurchaseOrderItem",
            "description": "Purchase Order Items (EKPO)",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "PurchaseOrder", "PurchaseOrderItem", "Material", "Plant",
                "OrderQuantity", "PurchaseOrderQuantityUnit",
                "NetPriceAmount", "NetPriceQuantity",
                "AccountAssignmentCategory", "StorageLocation",
                "IsCompletelyDelivered",
            ],
            "filename": "EKPO_purchase_order_items.csv",
            "max_records": 20000,
        },
        {
            "name": "po_schedule_lines",
            "service": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
            "entity": "A_PurOrdScheduleLine",
            "description": "PO Schedule Lines (EKET) — delivery schedule + receipts",
            "filters": [],
            "select": [
                "PurchaseOrder", "PurchaseOrderItem", "ScheduleLine",
                "ScheduleLineDeliveryDate", "OrderQuantity",
                "ScheduleLineCommittedQuantity",
            ],
            "filename": "EKET_po_schedule_lines.csv",
            "max_records": 20000,
        },
        {
            "name": "purchase_requisitions",
            "service": "/sap/opu/odata/sap/API_PURCHASEREQ_PROCESS_SRV",
            "entity": "A_PurchaseRequisitionItem",
            "description": "Purchase Requisitions (EBAN) — procurement needs",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "PurchaseRequisition", "PurchaseRequisitionItem",
                "Material", "Plant", "PurchasingGroup",
                "RequestedQuantity", "BaseUnit",
                "PurchaseRequisitionPrice", "PurReqnReleaseStatus",
                "DeliveryDate", "PurchaseRequisitionType",
            ],
            "filename": "EBAN_purchase_requisitions.csv",
            "max_records": 10000,
        },
    ],

    # ========================================================================
    # CATEGORY: manufacturing — Production orders, confirmations, reservations
    # ========================================================================
    "manufacturing": [
        {
            "name": "production_orders",
            "service": "/sap/opu/odata/sap/API_PRODUCTION_ORDERS",
            "entity": "A_ProductionOrder",
            "description": "Production Orders (AFKO) — manufacturing orders",
            "filters": [f"ProductionPlant eq '{PLANT}'"],
            "select": [
                "ManufacturingOrder", "ManufacturingOrderType",
                "Material", "ProductionPlant",
                "TotalQuantity", "ProductionUnit",
                "MfgOrderPlannedStartDate", "MfgOrderPlannedEndDate",
                "MfgOrderActualReleaseDate",
                "ManufacturingOrderStatus",
            ],
            "filename": "AFKO_production_orders.csv",
            "max_records": 5000,
            # Fallback: older API path
            "fallback_service": "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV",
            "fallback_entity": "A_ProductionOrder_2",
        },
        {
            "name": "production_order_components",
            "service": "/sap/opu/odata/sap/API_PRODUCTION_ORDERS",
            "entity": "A_ProductionOrderComponent",
            "description": "Production Order Components (RESB via MO)",
            "filters": [],
            "select": [
                "ManufacturingOrder", "ManufacturingOrderItem",
                "Material", "Plant", "StorageLocation",
                "RequiredQuantity", "BaseUnit",
                "RequirementDate", "WithdrawnQuantity",
            ],
            "filename": "RESB_mo_components.csv",
            "max_records": 20000,
        },
        {
            "name": "production_order_operations",
            "service": "/sap/opu/odata/sap/API_PRODUCTION_ORDERS",
            "entity": "A_ProductionOrderOperation",
            "description": "Production Order Operations (AFVC via MO)",
            "filters": [],
            "select": [
                "ManufacturingOrder", "ManufacturingOrderOperation",
                "WorkCenter", "Plant",
                "OpPlannedTotalQuantity", "OpTotalConfirmedYieldQty",
                "OperationSetupDuration", "OperationMachineDuration",
                "OperationLaborDuration",
            ],
            "filename": "AFVC_mo_operations.csv",
            "max_records": 20000,
        },
        {
            "name": "planned_orders",
            "service": "/sap/opu/odata/sap/API_PLANNED_ORDERS",
            "entity": "A_PlannedOrder",
            "description": "Planned Orders (PLAF) — MRP output",
            "filters": [f"ProductionPlant eq '{PLANT}'"],
            "select": [
                "PlannedOrder", "PlannedOrderType", "Material",
                "ProductionPlant", "TotalQuantity", "BaseUnit",
                "PlannedOrderPlannedStartDate", "PlannedOrderPlannedEndDate",
                "PlannedOrderIsFirm", "PlannedOrderOpeningDate",
            ],
            "filename": "PLAF_planned_orders.csv",
            "max_records": 10000,
        },
        {
            "name": "routings",
            "service": "/sap/opu/odata/sap/API_PRODUCTION_ROUTING",
            "entity": "A_ProductionRtgHeader",
            "description": "Routings (PLKO) — manufacturing sequences",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "ProductionRoutingGroup", "ProductionRouting",
                "Plant", "RoutingStatus",
                "Material", "ProductionRoutingDesc",
            ],
            "filename": "PLKO_routing_headers.csv",
        },
        {
            "name": "routing_operations",
            "service": "/sap/opu/odata/sap/API_PRODUCTION_ROUTING",
            "entity": "A_ProductionRtgSequence",
            "description": "Routing Operations (PLPO) — operation steps",
            "filters": [],
            "select": [
                "ProductionRoutingGroup", "ProductionRouting",
                "ProductionRoutingSequence",
                "ProductionRoutingOpIntID", "WorkCenter",
                "OperationSetupDuration", "OperationSetupDurationUnit",
                "StandardWorkQuantity1", "StandardWorkQuantity2",
            ],
            "filename": "PLPO_routing_operations.csv",
        },
    ],

    # ========================================================================
    # CATEGORY: distribution — Deliveries (inbound/outbound), transfer orders
    # ========================================================================
    "distribution": [
        {
            "name": "outbound_deliveries",
            "service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV_02",
            "entity": "A_OutbDeliveryHeader",
            "description": "Outbound Deliveries (LIKP) — shipments to customers",
            "filters": [],
            "select": [
                "DeliveryDocument", "DeliveryDocumentType",
                "ShipToParty", "SoldToParty",
                "ActualDeliveryRoute", "ShippingPoint",
                "PlannedGoodsIssueDate", "ActualGoodsMovementDate",
                "HeaderGrossWeight", "HeaderNetWeight", "HeaderVolume",
                "OverallSDProcessStatus",
            ],
            "filename": "LIKP_outbound_deliveries.csv",
            "max_records": 5000,
            "fallback_service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV",
        },
        {
            "name": "outbound_delivery_items",
            "service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV_02",
            "entity": "A_OutbDeliveryItem",
            "description": "Outbound Delivery Items (LIPS) — shipped line items",
            "filters": [],
            "select": [
                "DeliveryDocument", "DeliveryDocumentItem",
                "Material", "Plant", "StorageLocation",
                "ActualDeliveryQuantity", "DeliveryQuantityUnit",
                "ReferenceSDDocument", "ReferenceSDDocumentItem",
            ],
            "filename": "LIPS_outbound_delivery_items.csv",
            "max_records": 20000,
            "fallback_service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV",
        },
        {
            "name": "inbound_deliveries",
            "service": "/sap/opu/odata/sap/API_INBOUND_DELIVERY_SRV_02",
            "entity": "A_InbDeliveryHeader",
            "description": "Inbound Deliveries (LIKP inbound) — receipts from vendors",
            "filters": [],
            "select": [
                "DeliveryDocument", "DeliveryDocumentType",
                "VendorAccountNumber",
                "PlannedGoodsReceiptDate", "ActualGoodsMovementDate",
                "HeaderGrossWeight", "HeaderNetWeight",
                "OverallGoodsMovementStatus",
            ],
            "filename": "LIKP_inbound_deliveries.csv",
            "max_records": 5000,
            "fallback_service": "/sap/opu/odata/sap/API_INBOUND_DELIVERY_SRV",
        },
        {
            "name": "inbound_delivery_items",
            "service": "/sap/opu/odata/sap/API_INBOUND_DELIVERY_SRV_02",
            "entity": "A_InbDeliveryItem",
            "description": "Inbound Delivery Items — received line items",
            "filters": [],
            "select": [
                "DeliveryDocument", "DeliveryDocumentItem",
                "Material", "Plant", "StorageLocation",
                "ActualDeliveryQuantity", "DeliveryQuantityUnit",
                "ReferenceSDDocument", "ReferenceSDDocumentItem",
            ],
            "filename": "LIPS_inbound_delivery_items.csv",
            "max_records": 20000,
            "fallback_service": "/sap/opu/odata/sap/API_INBOUND_DELIVERY_SRV",
        },
    ],

    # ========================================================================
    # CATEGORY: quality — Notifications, inspection orders, results
    # ========================================================================
    "quality": [
        {
            "name": "quality_notifications",
            "service": "/sap/opu/odata/sap/API_QUALITYNOTIFICATION",
            "entity": "QualityNotification",
            "description": "Quality Notifications (QMEL) — defects, complaints, audits",
            "filters": [],
            "select": [
                "QualityNotification", "QualityNotificationType",
                "Material", "Plant",
                "QualityNotificationCreationDate",
                "QualityNotifcnPriority",
                "QltyNotifcnProcessingStatus",
            ],
            "filename": "QMEL_quality_notifications.csv",
            "max_records": 5000,
        },
        {
            "name": "quality_notification_items",
            "service": "/sap/opu/odata/sap/API_QUALITYNOTIFICATION",
            "entity": "QualityNotificationItem",
            "description": "Quality Notification Items (QMIH)",
            "filters": [],
            "select": [
                "QualityNotification", "QualityNotificationItem",
                "QltyNotifItemDefectClass", "QltyNotifItemShortText",
            ],
            "filename": "QMIH_quality_items.csv",
            "max_records": 10000,
        },
        {
            "name": "inspection_lots",
            "service": "/sap/opu/odata/sap/API_INSPECTIONLOT_SRV",
            "entity": "A_InspectionLot",
            "description": "Inspection Lots (QALS) — QC inspection orders",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "InspectionLot", "Material", "Plant",
                "InspectionLotQuantity", "InspectionLotActualQuantity",
                "InspLotAcceptedQuantity", "InspLotRejectedQuantity",
                "InspLotCreationDate", "InspectionLotType",
                "InspLotUsageDecision",
            ],
            "filename": "QALS_inspection_lots.csv",
            "max_records": 5000,
        },
    ],

    # ========================================================================
    # CATEGORY: maintenance — Work orders, plans, confirmations
    # ========================================================================
    "maintenance": [
        {
            "name": "maintenance_notifications",
            "service": "/sap/opu/odata/sap/API_MAINTNOTIFICATION",
            "entity": "MaintenanceNotification",
            "description": "Maintenance Notifications (QMEL PM type)",
            "filters": [],
            "select": [
                "MaintenanceNotification", "NotificationType",
                "TechnicalObject", "Equipment", "FunctionalLocation",
                "NotificationCreationDate", "NotificationPriority",
                "NotifProcessingPhase",
                "MaintenancePlant",
            ],
            "filename": "QMEL_maintenance_notifications.csv",
            "max_records": 5000,
        },
        {
            "name": "maintenance_orders",
            "service": "/sap/opu/odata/sap/API_MAINTENANCEORDER",
            "entity": "MaintenanceOrder",
            "description": "Maintenance Orders (AUFK PM)",
            "filters": [f"MaintenancePlant eq '{PLANT}'"],
            "select": [
                "MaintenanceOrder", "MaintenanceOrderType",
                "Equipment", "FunctionalLocation",
                "MaintenancePlant", "MaintenanceActivityType",
                "MaintPriority",
                "MaintOrdBasicStartDate", "MaintOrdBasicEndDate",
                "MaintenancePlanningPlant",
            ],
            "filename": "AUFK_maintenance_orders.csv",
            "max_records": 5000,
        },
        {
            "name": "equipment_master",
            "service": "/sap/opu/odata/sap/API_EQUIPMENT",
            "entity": "Equipment",
            "description": "Equipment Master (EQUI) — assets",
            "filters": [f"MaintenancePlant eq '{PLANT}'"],
            "select": [
                "Equipment", "EquipmentName", "EquipmentCategory",
                "MaintenancePlant", "FunctionalLocation",
                "ManufacturerPartNmbr", "ManufacturerSerialNumber",
                "EquipmentIsActive",
            ],
            "filename": "EQUI_equipment.csv",
            "max_records": 5000,
        },
    ],

    # ========================================================================
    # CATEGORY: subcontracting — Subcontracting POs + components
    # ========================================================================
    "subcontracting": [
        # Subcontracting POs are extracted via procurement (EKKO/EKPO)
        # with PurchaseOrderType = 'L' (subcontracting).
        # Components sent to subcontractors are in RESB (reservations).
        # No separate OData service needed — filtered from procurement data.
    ],

    # ========================================================================
    # CATEGORY: inventory — Stock on hand, movements, reservations
    # ========================================================================
    "inventory": [
        {
            "name": "stock_on_hand",
            "service": "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV",
            "entity": "A_MatlStkInAcctMod",
            "description": "Stock on Hand (MARD) — current inventory position",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "Material", "Plant", "StorageLocation",
                "MatlWrhsStkQtyInMatlBaseUnit",
            ],
            "filename": "MARD_stock_on_hand.csv",
        },
        {
            "name": "material_documents",
            "service": "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV",
            "entity": "A_MaterialDocumentHeader",
            "description": "Material Documents (MKPF) — goods movements",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "MaterialDocument", "MaterialDocumentYear",
                "PostingDate", "DocumentDate",
                "GoodsMovementCode",
            ],
            "filename": "MKPF_material_doc_headers.csv",
            "max_records": 10000,
            "fallback_service": "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV;v=0002",
        },
        {
            "name": "material_document_items",
            "service": "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV",
            "entity": "A_MaterialDocumentItem",
            "description": "Material Document Items (MSEG) — movement line items",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "MaterialDocument", "MaterialDocumentYear",
                "MaterialDocumentItem",
                "Material", "Plant", "StorageLocation",
                "GoodsMovementType", "QuantityInBaseUnit", "BaseUnit",
                "PurchaseOrder", "PurchaseOrderItem",
                "ManufacturingOrder", "ManufacturingOrderItem",
                "DeliveryDocument", "DeliveryDocumentItem",
            ],
            "filename": "MSEG_material_doc_items.csv",
            "max_records": 50000,
            "fallback_service": "/sap/opu/odata/sap/API_MATERIAL_DOCUMENT_SRV;v=0002",
        },
        {
            "name": "reservations",
            "service": "/sap/opu/odata/sap/API_RESERVATION_DOCUMENT_SRV",
            "entity": "A_ReservationDocumentHeader",
            "description": "Reservations (RKPF) — inventory reservations",
            "filters": [],
            "select": [
                "Reservation", "GoodsMovementType",
                "CostCenter", "GoodsRecipientName",
                "ReservationDate",
            ],
            "filename": "RKPF_reservation_headers.csv",
            "max_records": 5000,
        },
        {
            "name": "reservation_items",
            "service": "/sap/opu/odata/sap/API_RESERVATION_DOCUMENT_SRV",
            "entity": "A_ReservationDocumentItem",
            "description": "Reservation Items (RESB) — reserved materials",
            "filters": [f"Plant eq '{PLANT}'"],
            "select": [
                "Reservation", "ReservationItem",
                "Material", "Plant", "StorageLocation",
                "ReqdQuantity", "BaseUnit",
                "ReservationDate", "GoodsMovementType",
            ],
            "filename": "RESB_reservation_items.csv",
            "max_records": 20000,
        },
    ],
}


# ============================================================================
# OData Client
# ============================================================================

class SAPODataClient:
    """Client for SAP S/4HANA OData APIs."""

    def __init__(self, host: str, user: str, password: str, client: str = "100",
                 port: int = 44301, use_ssl: bool = True):
        self.base_url = f"{'https' if use_ssl else 'http'}://{host}:{port}"
        self.auth = HTTPBasicAuth(user, password)
        self.client = client
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = False  # Self-signed cert on FAA
        self.session.headers.update({
            "Accept": "application/json",
            "sap-client": client,
        })

    def test_connection(self) -> bool:
        """Test connectivity to SAP system."""
        test_urls = [
            f"{self.base_url}/sap/opu/odata/sap/API_PRODUCT_SRV/$metadata",
            f"{self.base_url}/sap/opu/odata/sap/API_PRODUCT_SRV/",
        ]
        for url in test_urls:
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    logger.info(f"Connection successful: HTTP {resp.status_code}")
                    return True
                elif resp.status_code == 401:
                    logger.error("Authentication failed (HTTP 401). Check user/password.")
                    return False
                elif resp.status_code == 403:
                    logger.error("Authorization failed (HTTP 403). User may lack OData access.")
                    return False
                else:
                    logger.warning(f"HTTP {resp.status_code} for {url}")
            except requests.ConnectionError as e:
                logger.warning(f"Connection failed: {e}")
            except requests.Timeout:
                logger.warning(f"Timeout for {url}")

        # Try HTTP fallback (port 50000)
        http_url = f"http://{self.base_url.split('//')[1].split(':')[0]}:50000/sap/opu/odata/sap/API_PRODUCT_SRV/$metadata"
        try:
            resp = self.session.get(http_url, timeout=30)
            if resp.status_code == 200:
                logger.info(f"Connection successful on HTTP port 50000")
                self.base_url = f"http://{self.base_url.split('//')[1].split(':')[0]}:50000"
                return True
        except Exception:
            pass

        logger.error("All connection attempts failed. Check host, port, and network.")
        return False

    def fetch_entity_set(
        self,
        service_path: str,
        entity_set: str,
        filters: Optional[List[str]] = None,
        select_fields: Optional[List[str]] = None,
        max_records: int = 0,
        top: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Fetch all records from an OData entity set with server-side paging."""
        all_records = []
        skip = 0

        params = {"$format": "json", "$top": str(top)}
        if filters:
            params["$filter"] = " and ".join(filters)
        if select_fields:
            params["$select"] = ",".join(select_fields)

        url = f"{self.base_url}{service_path}/{entity_set}"

        while True:
            params["$skip"] = str(skip)
            try:
                resp = self.session.get(url, params=params, timeout=120)

                if resp.status_code == 404:
                    logger.warning(f"  Service not found: {service_path}/{entity_set}")
                    return []
                if resp.status_code != 200:
                    logger.error(f"  HTTP {resp.status_code}: {resp.text[:300]}")
                    return all_records

                data = resp.json()

                # OData v2 format
                results = data.get("d", {}).get("results", [])
                if not results:
                    # OData v4 format
                    results = data.get("value", [])

                if not results:
                    break

                for record in results:
                    record.pop("__metadata", None)

                all_records.extend(results)

                if len(results) < top:
                    break

                if max_records > 0 and len(all_records) >= max_records:
                    all_records = all_records[:max_records]
                    break

                skip += top
                time.sleep(0.3)  # Rate limiting

            except requests.Timeout:
                logger.error(f"  Timeout at skip={skip}")
                break
            except json.JSONDecodeError:
                logger.error(f"  Invalid JSON response")
                break
            except Exception as e:
                logger.error(f"  Error: {e}")
                break

        return all_records

    def extract(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract entity set, trying fallback service/entity/filters if primary fails."""
        records = self.fetch_entity_set(
            service_path=config["service"],
            entity_set=config["entity"],
            filters=config.get("filters"),
            select_fields=config.get("select"),
            max_records=config.get("max_records", 0),
        )

        # Try fallback filters (e.g., different BP grouping)
        if not records and "fallback_filters" in config:
            logger.info(f"  Trying fallback filters...")
            records = self.fetch_entity_set(
                service_path=config["service"],
                entity_set=config["entity"],
                filters=config["fallback_filters"],
                select_fields=config.get("select"),
                max_records=config.get("max_records", 0),
            )

        # Try fallback service
        if not records and "fallback_service" in config:
            fallback_entity = config.get("fallback_entity", config["entity"])
            logger.info(f"  Trying fallback: {config['fallback_service']}/{fallback_entity}")
            records = self.fetch_entity_set(
                service_path=config["fallback_service"],
                entity_set=fallback_entity,
                filters=config.get("filters"),
                select_fields=config.get("select"),
                max_records=config.get("max_records", 0),
            )

        return records


# ============================================================================
# CSV Writer
# ============================================================================

def save_csv(records: List[Dict[str, Any]], fields: List[str], filepath: Path):
    """Save records to CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        logger.warning(f"  No records — writing header-only file")
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
        return

    # Use actual keys from records (OData may return different names)
    actual_fields = list(records[0].keys())
    if set(fields) - set(actual_fields):
        fields = actual_fields

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def generate_manifest(results: Dict[str, Dict[str, Any]]):
    """Write manifest file with extraction metadata."""
    manifest = {
        "extraction_timestamp": datetime.now().isoformat(),
        "source_system": "S/4HANA 2025 FAA (IDES)",
        "company_code": COMPANY_CODE,
        "plant": PLANT,
        "client": "100",
        "categories": {},
        "files": {},
        "total_records": 0,
        "total_files": 0,
    }

    for category, extractions in results.items():
        cat_total = sum(info["records"] for info in extractions.values())
        manifest["categories"][category] = {
            "files": len(extractions),
            "total_records": cat_total,
        }
        for name, info in extractions.items():
            manifest["files"][info["filename"]] = {
                "category": category,
                "description": info["description"],
                "records": info["records"],
                "status": "ok" if info["records"] > 0 else "empty",
            }
            manifest["total_records"] += info["records"]
            manifest["total_files"] += 1

    manifest_path = OUTPUT_DIR / "MANIFEST.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"\nManifest: {manifest_path}")
    return manifest


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract SAP S/4HANA IDES data to CSV for Autonomy tenant config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full extraction (all categories):
  python scripts/extract_sap_ides.py --host 1.2.3.4 --user DDIC --password MyPass123

  # Master data only (fastest, for config generation):
  python scripts/extract_sap_ides.py --host 1.2.3.4 --user DDIC --password MyPass123 \\
      --categories master sourcing inventory

  # Test connection without extracting:
  python scripts/extract_sap_ides.py --host 1.2.3.4 --user DDIC --password MyPass123 --dry-run

  # Using environment variables:
  export SAP_HOST=1.2.3.4 SAP_USER=DDIC SAP_PASS=MyPass123
  python scripts/extract_sap_ides.py
        """,
    )
    parser.add_argument("--host", default=os.environ.get("SAP_HOST"),
                       help="SAP S/4HANA external IP")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SAP_PORT", "44301")),
                       help="HTTPS port (default: 44301)")
    parser.add_argument("--user", default=os.environ.get("SAP_USER", "DDIC"),
                       help="SAP user (default: DDIC)")
    parser.add_argument("--password", default=os.environ.get("SAP_PASS"),
                       help="SAP password")
    parser.add_argument("--client", default=os.environ.get("SAP_CLIENT", "100"),
                       help="SAP client (default: 100)")
    parser.add_argument("--categories", nargs="+", choices=ALL_CATEGORIES,
                       default=None,
                       help="Categories to extract (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Test connection only")
    parser.add_argument("--output", type=Path, default=None,
                       help=f"Output directory (default: {OUTPUT_DIR})")
    args = parser.parse_args()

    if not args.host:
        print("\nERROR: SAP host required. Use --host <IP> or set SAP_HOST env var.")
        print("Get the IP from: SAP CAL > Appliances > Info tab (S/4HANA VM external IP)")
        sys.exit(1)
    if not args.password:
        print("\nERROR: SAP password required. Use --password <PW> or set SAP_PASS env var.")
        sys.exit(1)

    global OUTPUT_DIR
    if args.output:
        OUTPUT_DIR = args.output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    categories = args.categories or ALL_CATEGORIES

    logger.info("=" * 70)
    logger.info("SAP S/4HANA IDES — Full Data Extraction")
    logger.info("=" * 70)
    logger.info(f"Host:       {args.host}:{args.port}")
    logger.info(f"User:       {args.user}, Client: {args.client}")
    logger.info(f"Company:    {COMPANY_CODE}, Plant: {PLANT}")
    logger.info(f"Categories: {', '.join(categories)}")
    logger.info(f"Output:     {OUTPUT_DIR}")
    logger.info("")

    client = SAPODataClient(
        host=args.host, user=args.user, password=args.password,
        client=args.client, port=args.port,
    )

    if not client.test_connection():
        logger.error("Connection failed. Troubleshooting:")
        logger.error("  1. Is the SAP instance Active in CAL? (not Suspended)")
        logger.error("  2. Does Access Points allow your IP? (curl ifconfig.me)")
        logger.error("  3. Try: curl -k -u DDIC:<pw> https://<host>:44301/sap/opu/odata/sap/API_PRODUCT_SRV/")
        sys.exit(1)

    if args.dry_run:
        logger.info("Dry run — connection successful. Exiting.")
        sys.exit(0)

    # ---- Extract all requested categories ----
    all_results = {}

    for category in categories:
        extractions = ODATA_EXTRACTIONS.get(category, [])
        if not extractions:
            logger.info(f"\n--- {category.upper()} --- (no dedicated extractions, covered by other categories)")
            continue

        logger.info(f"\n{'=' * 50}")
        logger.info(f"CATEGORY: {category.upper()} ({len(extractions)} extractions)")
        logger.info(f"{'=' * 50}")

        cat_results = {}
        for config in extractions:
            name = config["name"]
            logger.info(f"\n  [{name}] {config['description']}")

            records = client.extract(config)
            filepath = OUTPUT_DIR / config["filename"]

            if records:
                save_csv(records, config.get("select", []), filepath)
                logger.info(f"  -> {len(records):,} records -> {config['filename']}")
            else:
                save_csv([], config.get("select", []), filepath)
                logger.warning(f"  -> 0 records (header-only) -> {config['filename']}")

            cat_results[name] = {
                "filename": config["filename"],
                "description": config["description"],
                "records": len(records),
            }

        all_results[category] = cat_results

    # ---- Summary ----
    logger.info("\n" + "=" * 70)
    logger.info("EXTRACTION COMPLETE")
    logger.info("=" * 70)

    manifest = generate_manifest(all_results)

    grand_total = 0
    for category, extractions in all_results.items():
        cat_total = sum(info["records"] for info in extractions.values())
        grand_total += cat_total
        status_icon = "+" if cat_total > 0 else "-"
        logger.info(f"  {status_icon} {category:20s} {cat_total:>8,} records ({len(extractions)} files)")
        for name, info in extractions.items():
            icon = "ok" if info["records"] > 0 else "--"
            logger.info(f"      [{icon}] {info['filename']:40s} {info['records']:>8,}")

    logger.info(f"\n  TOTAL: {grand_total:,} records across {manifest['total_files']} files")
    logger.info(f"  Output: {OUTPUT_DIR}/")

    logger.info("\nNext steps:")
    logger.info("  1. Review CSVs in imports/SAP/IDES_1710/")
    logger.info("  2. SUSPEND SAP instance in CAL to save ~$75/day")
    logger.info("  3. Create SAP connection in Autonomy (CSV method):")
    logger.info(f"     Admin > SAP Data Management > New Connection > CSV")
    logger.info(f"     csv_directory: {OUTPUT_DIR}")
    logger.info("  4. Run field mapping + ingestion to create tenant config")
    logger.info("  5. Start SAP Change Simulator for ongoing CDC events")


if __name__ == "__main__":
    main()
