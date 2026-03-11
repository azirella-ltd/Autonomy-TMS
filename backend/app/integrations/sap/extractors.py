"""
SAP Table Extractors — Unified extraction interface for all connection methods.

All extractors produce Dict[str, pd.DataFrame] with uppercase column names,
feeding into the same SAPConfigBuilder → 3-phase loading pipeline.

Supported methods:
  - ODataExtractor: SAP S/4HANA OData v2/v4 API via httpx (async)
  - HANADBExtractor: Direct SQL to SAP HANA via hdbcli
  - RFCExtractor: RFC_READ_TABLE via pyrfc (wraps S4HANAConnector)
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# Base class
# ============================================================================

class SAPTableExtractor(ABC):
    """Abstract base for SAP table extractors.

    All subclasses must return Dict[str, pd.DataFrame] with uppercase column
    names so downstream SAPConfigBuilder / ingestion phases work identically.
    """

    @abstractmethod
    async def test_connection(self) -> Tuple[bool, str]:
        """Test connectivity. Returns (success, message)."""
        ...

    @abstractmethod
    async def extract_tables(
        self,
        tables: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], int, int]:
        """Extract requested tables.

        Args:
            tables: SAP table names to extract (e.g. ["T001W", "MARA", "MARC"])
            progress_callback: Optional async callback(table, rows_ok, rows_failed)

        Returns:
            (sap_data, total_rows, total_failed)
        """
        ...


# ============================================================================
# OData-to-SAP column rename maps
#
# OData returns CamelCase; SAPConfigBuilder expects SAP technical names.
# Derived from scripts/extract_sap_ides.py ODATA_EXTRACTIONS.
# ============================================================================

ODATA_TABLE_MAP: Dict[str, Dict[str, Any]] = {
    # ---- Master data ----
    "T001W": {
        "service": "/sap/opu/odata/sap/API_PLANT_SRV",
        "entity": "A_Plant",
        "select": [
            "Plant", "PlantName", "CompanyCode", "FactoryCalendar",
            "Street", "City", "PostalCode", "Region", "Country",
        ],
        "rename": {
            "Plant": "WERKS", "PlantName": "NAME1", "CompanyCode": "BUKRS",
            "FactoryCalendar": "FABKL", "Street": "STRAS", "City": "ORT01",
            "PostalCode": "PSTLZ", "Region": "REGIO", "Country": "LAND1",
        },
    },
    "MARA": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_Product",
        "select": [
            "Product", "ProductType", "BaseUnit", "ProductGroup",
            "GrossWeight", "NetWeight", "WeightUnit", "Volume", "VolumeUnit",
            "IndustrySector", "CreationDate", "LastChangeDate",
        ],
        "rename": {
            "Product": "MATNR", "ProductType": "MTART", "BaseUnit": "MEINS",
            "ProductGroup": "MATKL", "GrossWeight": "BRGEW", "NetWeight": "NTGEW",
            "WeightUnit": "GEWEI", "Volume": "VOLUM", "VolumeUnit": "VOLEH",
            "IndustrySector": "MBRSH", "CreationDate": "ERSDA",
            "LastChangeDate": "LAEDA",
        },
    },
    "MAKT": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_ProductDescription",
        "select": ["Product", "Language", "ProductDescription"],
        "filters": ["Language eq 'EN'"],
        "rename": {
            "Product": "MATNR", "Language": "SPRAS",
            "ProductDescription": "MAKTX",
        },
    },
    "MARC": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_ProductPlant",
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
        "rename": {
            "Product": "MATNR", "Plant": "WERKS", "PurchasingGroup": "EKGRP",
            "MRPType": "DISMM", "MRPController": "DISPO",
            "MRPResponsible": "DSESSION", "ReorderThresholdQuantity": "MINBE",
            "PlanningTimeFence": "FESSION", "LotSizingProcedure": "DISLS",
            "MinimumLotSizeQuantity": "BSTMI", "MaximumLotSizeQuantity": "BSTMA",
            "FixedLotSizeQuantity": "BSTFE", "SafetyStock": "EISBE",
            "ProcurementType": "BESKZ", "SpecialProcurementType": "SOBSL",
            "PlannedDeliveryDurationInDays": "PLIFZ",
            "GoodsReceiptDuration": "WEBAZ",
            "IsBatchManagementRequired": "XCHPF",
        },
    },
    "MBEW": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_ProductValuation",
        "select": [
            "Product", "ValuationArea", "ValuationClass",
            "StandardPrice", "MovingAveragePrice", "PriceControl",
        ],
        "rename": {
            "Product": "MATNR", "ValuationArea": "BWKEY",
            "ValuationClass": "BKLAS", "StandardPrice": "STPRS",
            "MovingAveragePrice": "VERPR", "PriceControl": "VPRSV",
        },
    },
    "MARM": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_ProductUnitsOfMeasure",
        "select": [
            "Product", "AlternativeUnit", "QuantityNumerator",
            "QuantityDenominator", "GrossWeight", "Volume",
        ],
        "rename": {
            "Product": "MATNR", "AlternativeUnit": "MEINH",
            "QuantityNumerator": "UMREZ", "QuantityDenominator": "UMREN",
            "GrossWeight": "BRGEW", "Volume": "VOLUM",
        },
    },
    "T001L": {
        "service": "/sap/opu/odata/sap/API_PRODUCT_SRV",
        "entity": "A_ProductStorageLocation",
        "select": ["Product", "Plant", "StorageLocation"],
        "rename": {
            "Product": "MATNR", "Plant": "WERKS",
            "StorageLocation": "LGORT",
        },
    },
    # ---- Trading partners ----
    "LFA1": {
        "service": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
        "entity": "A_BusinessPartner",
        "filters": ["BusinessPartnerCategory eq '2'"],
        "select": [
            "BusinessPartner", "BusinessPartnerName",
            "BusinessPartnerCategory", "Industry",
            "Country", "Region", "CityName", "PostalCode", "StreetName",
        ],
        "max_records": 2000,
        "rename": {
            "BusinessPartner": "LIFNR", "BusinessPartnerName": "NAME1",
            "BusinessPartnerCategory": "KTOKK", "Industry": "BRSCH",
            "Country": "LAND1", "Region": "REGIO", "CityName": "ORT01",
            "PostalCode": "PSTLZ", "StreetName": "STRAS",
        },
    },
    "KNA1": {
        "service": "/sap/opu/odata/sap/API_BUSINESS_PARTNER",
        "entity": "A_BusinessPartner",
        "filters": ["BusinessPartnerCategory eq '1'"],
        "select": [
            "BusinessPartner", "BusinessPartnerName",
            "BusinessPartnerCategory", "Industry",
            "Country", "Region", "CityName", "PostalCode", "StreetName",
        ],
        "max_records": 2000,
        "rename": {
            "BusinessPartner": "KUNNR", "BusinessPartnerName": "NAME1",
            "BusinessPartnerCategory": "KTOKD", "Industry": "BRSCH",
            "Country": "LAND1", "Region": "REGIO", "CityName": "ORT01",
            "PostalCode": "PSTLZ", "StreetName": "STRAS",
        },
    },
    # ---- BOMs ----
    "STKO": {
        "service": "/sap/opu/odata/sap/API_BILL_OF_MATERIAL_SRV_01",
        "entity": "MaterialBOM",
        "select": [
            "BillOfMaterial", "BillOfMaterialVariant", "Material",
            "Plant", "BOMHeaderBaseUnit", "BOMHeaderQuantityInBaseUnit",
            "BillOfMaterialStatus",
        ],
        "rename": {
            "BillOfMaterial": "STLNR", "BillOfMaterialVariant": "STLAL",
            "Material": "MATNR", "Plant": "WERKS",
            "BOMHeaderBaseUnit": "BMEIN",
            "BOMHeaderQuantityInBaseUnit": "BMENG",
            "BillOfMaterialStatus": "STLST",
        },
    },
    "STPO": {
        "service": "/sap/opu/odata/sap/API_BILL_OF_MATERIAL_SRV_01",
        "entity": "MaterialBOMItem",
        "select": [
            "BillOfMaterial", "BillOfMaterialVariant",
            "BillOfMaterialItemNodeNumber", "BillOfMaterialComponent",
            "BOMItemQuantity", "ComponentUnit", "BOMItemCategory",
            "Plant", "BillOfMaterialItemNumber",
        ],
        "rename": {
            "BillOfMaterial": "STLNR", "BillOfMaterialVariant": "STLAL",
            "BillOfMaterialItemNodeNumber": "STLKN",
            "BillOfMaterialComponent": "IDNRK",
            "BOMItemQuantity": "MENGE", "ComponentUnit": "MEINS",
            "BOMItemCategory": "POSTP", "Plant": "WERKS",
            "BillOfMaterialItemNumber": "POSNR",
        },
    },
    # ---- Purchasing ----
    "EKKO": {
        "service": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
        "entity": "A_PurchaseOrder",
        "select": [
            "PurchaseOrder", "PurchaseOrderType", "Supplier",
            "CompanyCode", "PurchasingOrganization", "PurchasingGroup",
            "CreationDate", "PurchaseOrderDate",
            "DocumentCurrency",
        ],
        "max_records": 5000,
        "rename": {
            "PurchaseOrder": "EBELN", "PurchaseOrderType": "BSART",
            "Supplier": "LIFNR", "CompanyCode": "BUKRS",
            "PurchasingOrganization": "EKORG", "PurchasingGroup": "EKGRP",
            "CreationDate": "AEDAT", "PurchaseOrderDate": "BEDAT",
            "DocumentCurrency": "WAERS",
        },
    },
    "EKPO": {
        "service": "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV",
        "entity": "A_PurchaseOrderItem",
        "select": [
            "PurchaseOrder", "PurchaseOrderItem", "Material", "Plant",
            "OrderQuantity", "PurchaseOrderQuantityUnit",
            "NetPriceAmount", "NetPriceQuantity",
            "AccountAssignmentCategory", "StorageLocation",
            "IsCompletelyDelivered",
        ],
        "max_records": 20000,
        "rename": {
            "PurchaseOrder": "EBELN", "PurchaseOrderItem": "EBELP",
            "Material": "MATNR", "Plant": "WERKS",
            "OrderQuantity": "MENGE",
            "PurchaseOrderQuantityUnit": "MEINS",
            "NetPriceAmount": "NETPR", "NetPriceQuantity": "PEINH",
            "AccountAssignmentCategory": "KNTTP",
            "StorageLocation": "LGORT",
            "IsCompletelyDelivered": "ELIKZ",
        },
    },
    # ---- Sales ----
    "VBAK": {
        "service": "/sap/opu/odata/sap/API_SALES_ORDER_SRV",
        "entity": "A_SalesOrder",
        "select": [
            "SalesOrder", "SalesOrderType", "SalesOrganization",
            "DistributionChannel", "OrganizationDivision",
            "SoldToParty", "CreationDate", "SalesOrderDate",
            "RequestedDeliveryDate", "TotalNetAmount",
            "TransactionCurrency", "OverallSDProcessStatus",
        ],
        "max_records": 5000,
        "rename": {
            "SalesOrder": "VBELN", "SalesOrderType": "AUART",
            "SalesOrganization": "VKORG", "DistributionChannel": "VTWEG",
            "OrganizationDivision": "SPART", "SoldToParty": "KUNNR",
            "CreationDate": "ERDAT", "SalesOrderDate": "AUDAT",
            "RequestedDeliveryDate": "VDATU",
            "TotalNetAmount": "NETWR",
            "TransactionCurrency": "WAERK",
            "OverallSDProcessStatus": "GBSTK",
        },
    },
    "VBAP": {
        "service": "/sap/opu/odata/sap/API_SALES_ORDER_SRV",
        "entity": "A_SalesOrderItem",
        "select": [
            "SalesOrder", "SalesOrderItem", "Material", "Plant",
            "RequestedQuantity", "RequestedQuantityUnit",
            "NetAmount", "TransactionCurrency",
            "SDProcessStatus", "DeliveryStatus",
        ],
        "max_records": 20000,
        "rename": {
            "SalesOrder": "VBELN", "SalesOrderItem": "POSNR",
            "Material": "MATNR", "Plant": "WERKS",
            "RequestedQuantity": "KWMENG", "RequestedQuantityUnit": "VRKME",
            "NetAmount": "NETPR", "TransactionCurrency": "WAERK",
            "SDProcessStatus": "GBSTA", "DeliveryStatus": "LFSTA",
        },
    },
    # ---- Deliveries ----
    "LIKP": {
        "service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV_02",
        "entity": "A_OutbDeliveryHeader",
        "select": [
            "DeliveryDocument", "DeliveryDocumentType",
            "ShipToParty", "SoldToParty", "ShippingPoint",
            "PlannedGoodsIssueDate", "ActualGoodsMovementDate",
            "OverallSDProcessStatus",
        ],
        "max_records": 5000,
        "fallback_service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV",
        "rename": {
            "DeliveryDocument": "VBELN", "DeliveryDocumentType": "LFART",
            "ShipToParty": "KUNNR", "SoldToParty": "KUNAG",
            "ShippingPoint": "VSTEL",
            "PlannedGoodsIssueDate": "WADAT",
            "ActualGoodsMovementDate": "WADAT_IST",
            "OverallSDProcessStatus": "GBSTK",
        },
    },
    "LIPS": {
        "service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV_02",
        "entity": "A_OutbDeliveryItem",
        "select": [
            "DeliveryDocument", "DeliveryDocumentItem",
            "Material", "Plant", "StorageLocation",
            "ActualDeliveryQuantity", "DeliveryQuantityUnit",
            "ReferenceSDDocument", "ReferenceSDDocumentItem",
        ],
        "max_records": 20000,
        "fallback_service": "/sap/opu/odata/sap/API_OUTBOUND_DELIVERY_SRV",
        "rename": {
            "DeliveryDocument": "VBELN", "DeliveryDocumentItem": "POSNR",
            "Material": "MATNR", "Plant": "WERKS",
            "StorageLocation": "LGORT",
            "ActualDeliveryQuantity": "LFIMG",
            "DeliveryQuantityUnit": "VRKME",
            "ReferenceSDDocument": "VGBEL",
            "ReferenceSDDocumentItem": "VGPOS",
        },
    },
    # ---- Production ----
    "AFKO": {
        "service": "/sap/opu/odata/sap/API_PRODUCTION_ORDERS",
        "entity": "A_ProductionOrder",
        "select": [
            "ManufacturingOrder", "ManufacturingOrderType",
            "Material", "ProductionPlant",
            "TotalQuantity", "ProductionUnit",
            "MfgOrderPlannedStartDate", "MfgOrderPlannedEndDate",
            "MfgOrderActualReleaseDate", "ManufacturingOrderStatus",
        ],
        "max_records": 5000,
        "fallback_service": "/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV",
        "fallback_entity": "A_ProductionOrder_2",
        "rename": {
            "ManufacturingOrder": "AUFNR",
            "ManufacturingOrderType": "AUART",
            "Material": "MATNR", "ProductionPlant": "WERKS",
            "TotalQuantity": "GAMNG", "ProductionUnit": "MEINS",
            "MfgOrderPlannedStartDate": "GSTRP",
            "MfgOrderPlannedEndDate": "GLTRP",
            "MfgOrderActualReleaseDate": "FTRMI",
            "ManufacturingOrderStatus": "STAT",
        },
    },
    # ---- Purchasing info records ----
    "EINE": {
        "service": "/sap/opu/odata/sap/API_INFORECORD_PROCESS_SRV",
        "entity": "A_PurchasingInfoRecord",
        "select": [
            "PurchasingInfoRecord", "Supplier", "Material", "Plant",
            "PurchasingOrganization", "PurchasingInfoRecordCategory",
            "NetPriceAmount", "PriceQuantity", "NetPriceQuantityUnit",
            "PlannedDeliveryDurationInDays", "StandardPurchasingOrderQty",
            "MinimumPurchaseOrderQuantity",
        ],
        "rename": {
            "PurchasingInfoRecord": "INFNR", "Supplier": "LIFNR",
            "Material": "MATNR", "Plant": "WERKS",
            "PurchasingOrganization": "EKORG",
            "PurchasingInfoRecordCategory": "ESOKZ",
            "NetPriceAmount": "NETPR", "PriceQuantity": "PEINH",
            "NetPriceQuantityUnit": "BPRME",
            "PlannedDeliveryDurationInDays": "APLFZ",
            "StandardPurchasingOrderQty": "NORBM",
            "MinimumPurchaseOrderQuantity": "MINBM",
        },
    },
    # ---- Inventory ----
    "MARD": {
        "service": "/sap/opu/odata/sap/API_MATERIAL_STOCK_SRV",
        "entity": "A_MatlStkInAcctMod",
        "select": [
            "Material", "Plant", "StorageLocation",
            "MatlWrhsStkQtyInMatlBaseUnit",
        ],
        "rename": {
            "Material": "MATNR", "Plant": "WERKS",
            "StorageLocation": "LGORT",
            "MatlWrhsStkQtyInMatlBaseUnit": "LABST",
        },
    },
}


# ============================================================================
# RFC table → field list mapping (from S4HANAConnector field constants)
# ============================================================================

RFC_TABLE_FIELDS: Dict[str, List[str]] = {
    "T001W": ["WERKS", "NAME1", "BUKRS", "FABKL", "STRAS", "ORT01", "PSTLZ", "REGIO", "LAND1"],
    "T001L": ["WERKS", "LGORT", "LGOBE"],
    "T001": ["BUKRS", "BUTXT", "LAND1", "WAERS"],
    "MARA": [
        "MATNR", "MAKTX", "MTART", "MEINS", "MATKL",
        "BRGEW", "NTGEW", "GEWEI", "VOLUM", "VOLEH", "LVORM",
    ],
    "MAKT": ["MATNR", "SPRAS", "MAKTX"],
    "MARC": [
        "MATNR", "WERKS", "DISPO", "DISGR", "DISMM", "DISLS",
        "BSTMI", "BSTMA", "BSTFE", "BSTRF", "BESKZ", "SOBSL",
        "LGPRO", "EISBE", "PLIFZ", "WEBAZ", "AUSSS", "DZEIT",
    ],
    "MBEW": ["MATNR", "BWKEY", "BKLAS", "STPRS", "VERPR", "VPRSV"],
    "MARM": ["MATNR", "MEINH", "UMREZ", "UMREN", "BRGEW", "NTGEW", "GEWEI", "VOLUM", "VOLEH"],
    "LFA1": ["LIFNR", "NAME1", "LAND1", "ORT01", "PSTLZ", "STRAS", "REGIO"],
    "KNA1": ["KUNNR", "NAME1", "LAND1", "ORT01", "PSTLZ", "STRAS", "REGIO"],
    "EORD": [
        "MATNR", "WERKS", "ZEESSION", "VDATU", "BDATU", "LIFNR",
        "FLIFN", "NOTKZ", "EKORG", "BESKZ", "SOBSL",
    ],
    "EINA": ["INFNR", "MATNR", "LIFNR", "LOEKZ"],
    "EINE": [
        "INFNR", "EKORG", "ESOKZ", "NETPR", "WAERS", "PEINH",
        "NORBM", "MINBM", "APLFZ", "UEBTO", "UNTTO",
    ],
    "EKKO": [
        "EBELN", "BUKRS", "BSTYP", "BSART", "LIFNR",
        "EKORG", "EKGRP", "BEDAT", "AEDAT",
    ],
    "EKPO": [
        "EBELN", "EBELP", "MATNR", "WERKS", "LGORT",
        "MENGE", "MEINS", "NETPR", "PEINH", "ELIKZ", "AEDAT",
    ],
    "VBAK": [
        "VBELN", "VKORG", "VTWEG", "SPART", "AUART",
        "KUNNR", "BSTNK", "ERDAT",
    ],
    "VBAP": [
        "VBELN", "POSNR", "MATNR", "WERKS",
        "KWMENG", "VRKME", "NETPR", "WAERK", "PSTYV",
    ],
    "LIKP": [
        "VBELN", "VSTEL", "VKORG", "LFART", "KUNNR",
        "WADAT_IST", "LFDAT",
    ],
    "LIPS": [
        "VBELN", "POSNR", "MATNR", "WERKS", "LGORT",
        "LFIMG", "VRKME", "PSTYV",
    ],
    "AFKO": [
        "AUFNR", "AUART", "MATNR", "WERKS",
        "PSMNG", "GAMNG", "WEMNG", "GSTRP", "GLTRP",
        "FTRMI", "FTRMS", "STAT",
    ],
    "STKO": ["STLNR", "STLAL", "STKOZ", "BMENG", "BMEIN", "STLST"],
    "STPO": [
        "STLNR", "STLAL", "STLKN", "IDNRK",
        "MENGE", "MEINS", "POSTP",
    ],
    "PLKO": [
        "PLNTY", "PLNNR", "PLNAL", "WERKS", "VERWE", "STATU",
    ],
    "PLPO": [
        "PLNTY", "PLNNR", "PLNKN", "VORNR", "ARBID", "ARBPL",
        "WERKS", "STEUS", "BMSCH", "VGW01", "VGW02", "VGW03",
    ],
    "MARD": ["MATNR", "WERKS", "LGORT", "LABST"],
}


# ============================================================================
# HANA SQL table definitions (same fields, used for SELECT)
# ============================================================================

# Reuse RFC_TABLE_FIELDS — HANA uses the same column names as RFC
HANA_TABLE_FIELDS = RFC_TABLE_FIELDS


# ============================================================================
# OData Extractor
# ============================================================================

class ODataExtractor(SAPTableExtractor):
    """Extract SAP tables via S/4HANA OData v2/v4 API using httpx."""

    def __init__(
        self,
        hostname: str,
        port: int,
        user: str,
        password: str,
        use_ssl: bool = True,
        ssl_verify: bool = False,
        client: str = "100",
        odata_base_path: Optional[str] = None,
    ):
        self.base_url = f"{'https' if use_ssl else 'http'}://{hostname}:{port}"
        self.user = user
        self.password = password
        self.ssl_verify = ssl_verify
        self.client = client
        # odata_base_path is not prepended — it's already in ODATA_TABLE_MAP service paths
        self.page_size = 5000

    async def test_connection(self) -> Tuple[bool, str]:
        """Test OData connectivity via $metadata request."""
        import httpx

        test_url = f"{self.base_url}/sap/opu/odata/sap/API_PRODUCT_SRV/$metadata"
        try:
            async with httpx.AsyncClient(verify=self.ssl_verify, timeout=30.0) as client:
                resp = await client.get(
                    test_url,
                    auth=(self.user, self.password),
                    headers={"sap-client": self.client},
                )
                if resp.status_code == 200:
                    return True, "OData connection successful (API_PRODUCT_SRV metadata OK)"
                elif resp.status_code == 401:
                    return False, "OData authentication failed (HTTP 401)"
                elif resp.status_code == 403:
                    return False, "OData authorization denied (HTTP 403)"
                else:
                    return False, f"OData returned HTTP {resp.status_code}"
        except httpx.ConnectError as e:
            return False, f"OData connection failed: {e}"
        except Exception as e:
            return False, f"OData test error: {e}"

    async def _fetch_entity_set(
        self,
        service_path: str,
        entity_set: str,
        select_fields: Optional[List[str]] = None,
        filters: Optional[List[str]] = None,
        max_records: int = 0,
        fallback_service: Optional[str] = None,
        fallback_entity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch all records from an OData entity set with pagination."""
        import httpx

        all_records: List[Dict[str, Any]] = []
        skip = 0

        params: Dict[str, str] = {"$format": "json", "$top": str(self.page_size)}
        if select_fields:
            params["$select"] = ",".join(select_fields)
        if filters:
            params["$filter"] = " and ".join(filters)

        url = f"{self.base_url}{service_path}/{entity_set}"

        async with httpx.AsyncClient(verify=self.ssl_verify, timeout=120.0) as client:
            while True:
                params["$skip"] = str(skip)
                try:
                    resp = await client.get(
                        url,
                        params=params,
                        auth=(self.user, self.password),
                        headers={"Accept": "application/json", "sap-client": self.client},
                    )

                    if resp.status_code == 404:
                        # Try fallback service if available
                        if fallback_service and skip == 0:
                            fb_entity = fallback_entity or entity_set
                            logger.info(f"  OData 404, trying fallback: {fallback_service}/{fb_entity}")
                            return await self._fetch_entity_set(
                                fallback_service, fb_entity,
                                select_fields=select_fields, filters=filters,
                                max_records=max_records,
                            )
                        logger.warning(f"  OData entity not found: {service_path}/{entity_set}")
                        return []

                    if resp.status_code != 200:
                        logger.error(f"  OData HTTP {resp.status_code}: {resp.text[:300]}")
                        return all_records

                    data = resp.json()

                    # OData v2: {"d": {"results": [...]}}
                    results = data.get("d", {}).get("results", [])
                    if not results:
                        # OData v4: {"value": [...]}
                        results = data.get("value", [])

                    if not results:
                        break

                    # Strip metadata
                    for record in results:
                        record.pop("__metadata", None)

                    all_records.extend(results)

                    if len(results) < self.page_size:
                        break
                    if max_records > 0 and len(all_records) >= max_records:
                        all_records = all_records[:max_records]
                        break

                    skip += self.page_size
                    await asyncio.sleep(0.2)  # Rate limiting

                except httpx.TimeoutException:
                    logger.error(f"  OData timeout at skip={skip}")
                    break
                except Exception as e:
                    logger.error(f"  OData error: {e}")
                    break

        return all_records

    async def extract_tables(
        self,
        tables: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], int, int]:
        sap_data: Dict[str, pd.DataFrame] = {}
        total_rows = 0
        total_failed = 0

        for table_name in tables:
            tn = table_name.upper()
            mapping = ODATA_TABLE_MAP.get(tn)

            if not mapping:
                logger.info(f"  OData: no mapping for table {tn}, skipping")
                if progress_callback:
                    await progress_callback(table_name, 0, 0)
                continue

            rows_ok = 0
            rows_fail = 0
            try:
                records = await self._fetch_entity_set(
                    service_path=mapping["service"],
                    entity_set=mapping["entity"],
                    select_fields=mapping.get("select"),
                    filters=mapping.get("filters"),
                    max_records=mapping.get("max_records", 0),
                    fallback_service=mapping.get("fallback_service"),
                    fallback_entity=mapping.get("fallback_entity"),
                )

                if records:
                    df = pd.DataFrame(records)
                    # Rename OData CamelCase → SAP technical names
                    rename_map = mapping.get("rename", {})
                    if rename_map:
                        df = df.rename(columns=rename_map)
                    # Ensure uppercase
                    df.columns = [c.upper() for c in df.columns]
                    sap_data[tn] = df
                    rows_ok = len(df)
                    logger.info(f"  OData: {tn} → {rows_ok} rows")
                else:
                    logger.info(f"  OData: {tn} → 0 records")

            except Exception as e:
                rows_fail = 1
                logger.warning(f"  OData: failed to extract {tn}: {e}")

            total_rows += rows_ok
            total_failed += rows_fail

            if progress_callback:
                await progress_callback(table_name, rows_ok, rows_fail)

        return sap_data, total_rows, total_failed


# ============================================================================
# HANA DB Extractor
# ============================================================================

class HANADBExtractor(SAPTableExtractor):
    """Extract SAP tables via direct SQL to SAP HANA using hdbcli."""

    def __init__(
        self,
        hostname: str,
        port: int,
        user: str,
        password: str,
        schema: str = "SAPHANADB",
    ):
        try:
            from hdbcli import dbapi  # noqa: F401
        except ImportError:
            raise ImportError(
                "hdbcli is required for HANA DB extraction. "
                "Install with: pip install hdbcli"
            )

        self.hostname = hostname
        self.port = port
        self.user = user
        self.password = password
        self.schema = schema
        self.batch_size = 50000

    async def test_connection(self) -> Tuple[bool, str]:
        """Test HANA connectivity."""
        def _test():
            from hdbcli import dbapi
            conn = dbapi.connect(
                address=self.hostname,
                port=self.port,
                user=self.user,
                password=self.password,
            )
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self.schema}.T001W")
            count = cur.fetchone()[0]
            conn.close()
            return count

        try:
            count = await asyncio.to_thread(_test)
            return True, f"HANA DB connection successful ({count} plants in {self.schema}.T001W)"
        except ImportError:
            return False, "hdbcli package not installed (pip install hdbcli)"
        except Exception as e:
            return False, f"HANA DB connection failed: {e}"

    def _extract_single_table(self, table_name: str, fields: List[str]) -> pd.DataFrame:
        """Synchronous extraction of a single table."""
        from hdbcli import dbapi

        conn = dbapi.connect(
            address=self.hostname,
            port=self.port,
            user=self.user,
            password=self.password,
        )
        try:
            cur = conn.cursor()

            # Check table exists
            cur.execute(
                "SELECT COUNT(*) FROM SYS.TABLES WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?",
                (self.schema, table_name.upper()),
            )
            if cur.fetchone()[0] == 0:
                logger.info(f"  HANA: table {self.schema}.{table_name} not found, skipping")
                return pd.DataFrame()

            # Build SELECT with only fields that exist
            cur.execute(
                "SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS "
                "WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?",
                (self.schema, table_name.upper()),
            )
            existing_cols = {row[0] for row in cur.fetchall()}
            valid_fields = [f for f in fields if f.upper() in existing_cols]

            if not valid_fields:
                # Fall back to SELECT *
                select_clause = "*"
            else:
                select_clause = ", ".join(f'"{f}"' for f in valid_fields)

            all_rows = []
            offset = 0

            while True:
                query = (
                    f"SELECT {select_clause} FROM {self.schema}.\"{table_name.upper()}\" "
                    f"LIMIT {self.batch_size} OFFSET {offset}"
                )
                cur.execute(query)
                rows = cur.fetchall()
                if not rows:
                    break

                col_names = [desc[0] for desc in cur.description]
                all_rows.extend(rows)

                if len(rows) < self.batch_size:
                    break
                offset += self.batch_size

            if not all_rows:
                return pd.DataFrame()

            col_names = [desc[0] for desc in cur.description]
            df = pd.DataFrame(all_rows, columns=col_names)
            df.columns = [c.upper() for c in df.columns]
            return df

        finally:
            conn.close()

    async def extract_tables(
        self,
        tables: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], int, int]:
        sap_data: Dict[str, pd.DataFrame] = {}
        total_rows = 0
        total_failed = 0

        for table_name in tables:
            tn = table_name.upper()
            fields = HANA_TABLE_FIELDS.get(tn, [])
            rows_ok = 0
            rows_fail = 0

            try:
                df = await asyncio.to_thread(self._extract_single_table, tn, fields)
                if not df.empty:
                    sap_data[tn] = df
                    rows_ok = len(df)
                    logger.info(f"  HANA: {tn} → {rows_ok} rows")
                else:
                    logger.info(f"  HANA: {tn} → 0 rows")
            except Exception as e:
                rows_fail = 1
                logger.warning(f"  HANA: failed to extract {tn}: {e}")

            total_rows += rows_ok
            total_failed += rows_fail

            if progress_callback:
                await progress_callback(table_name, rows_ok, rows_fail)

        return sap_data, total_rows, total_failed


# ============================================================================
# RFC Extractor
# ============================================================================

class RFCExtractor(SAPTableExtractor):
    """Extract SAP tables via RFC_READ_TABLE using pyrfc."""

    def __init__(
        self,
        ashost: str,
        sysnr: str,
        client: str,
        user: str,
        password: str,
        lang: str = "EN",
    ):
        try:
            from pyrfc import Connection  # noqa: F401
        except ImportError:
            raise ImportError(
                "pyrfc is required for RFC extraction. "
                "Install with: pip install pyrfc "
                "(requires SAP NW RFC SDK, see https://support.sap.com/en/product/connectors/nwrfcsdk.html)"
            )

        self.ashost = ashost
        self.sysnr = sysnr
        self.client = client
        self.user = user
        self.password = password
        self.lang = lang
        self.batch_size = 10000

    def _get_connection(self):
        from pyrfc import Connection
        return Connection(
            ashost=self.ashost,
            sysnr=self.sysnr,
            client=self.client,
            user=self.user,
            passwd=self.password,
            lang=self.lang,
        )

    async def test_connection(self) -> Tuple[bool, str]:
        """Test RFC connectivity."""
        def _test():
            conn = self._get_connection()
            # Call RFC_SYSTEM_INFO for a lightweight test
            result = conn.call("RFC_SYSTEM_INFO")
            sysid = result.get("RFCSI_EXPORT", {}).get("RFCSYSID", "?")
            conn.close()
            return sysid

        try:
            sysid = await asyncio.to_thread(_test)
            return True, f"RFC connection successful (SID: {sysid})"
        except ImportError:
            return False, "pyrfc package not installed"
        except Exception as e:
            return False, f"RFC connection failed: {e}"

    def _extract_single_table(self, table_name: str, fields: List[str]) -> pd.DataFrame:
        """Synchronous extraction of a single table via RFC_READ_TABLE."""
        from pyrfc import ABAPApplicationError, ABAPRuntimeError

        conn = self._get_connection()
        try:
            all_rows: List[List[str]] = []
            skip = 0

            # If no fields specified, pass empty list (SAP returns all fields)
            field_list = [{"FIELDNAME": f} for f in fields] if fields else []

            while True:
                try:
                    result = conn.call(
                        "RFC_READ_TABLE",
                        QUERY_TABLE=table_name.upper(),
                        DELIMITER="|",
                        FIELDS=field_list,
                        ROWCOUNT=self.batch_size,
                        ROWSKIPS=skip,
                    )
                except ABAPApplicationError as e:
                    # Table not found or access denied
                    if "NOT_FOUND" in str(e) or "TABLE_NOT_AVAILABLE" in str(e):
                        logger.info(f"  RFC: table {table_name} not found")
                        return pd.DataFrame()
                    # Row width exceeded — retry with fewer fields
                    if "DATA_BUFFER_EXCEEDED" in str(e):
                        logger.warning(
                            f"  RFC: {table_name} row width exceeded with {len(fields)} fields, "
                            f"retrying with essential fields only"
                        )
                        # Reduce to first 10 fields to fit in 512-byte buffer
                        if len(fields) > 10:
                            return self._extract_single_table(table_name, fields[:10])
                        return pd.DataFrame()
                    raise

                data = result.get("DATA", [])
                if not data:
                    break

                # Determine column names from FIELDS response
                if not all_rows and result.get("FIELDS"):
                    col_names = [f["FIELDNAME"] for f in result["FIELDS"]]
                    if fields:
                        fields = col_names  # Use actual returned field names

                for row_data in data:
                    values = [v.strip() for v in row_data["WA"].split("|")]
                    all_rows.append(values)

                if len(data) < self.batch_size:
                    break
                skip += self.batch_size

            if not all_rows:
                return pd.DataFrame()

            # Use returned FIELDS for column names, or the input fields
            if result.get("FIELDS"):
                col_names = [f["FIELDNAME"] for f in result["FIELDS"]]
            else:
                col_names = fields

            df = pd.DataFrame(all_rows, columns=col_names[:len(all_rows[0])])
            df.columns = [c.upper() for c in df.columns]
            return df

        except ABAPRuntimeError as e:
            logger.error(f"  RFC ABAP runtime error for {table_name}: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    async def extract_tables(
        self,
        tables: List[str],
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[Dict[str, pd.DataFrame], int, int]:
        sap_data: Dict[str, pd.DataFrame] = {}
        total_rows = 0
        total_failed = 0

        for table_name in tables:
            tn = table_name.upper()
            fields = RFC_TABLE_FIELDS.get(tn, [])
            rows_ok = 0
            rows_fail = 0

            try:
                df = await asyncio.to_thread(self._extract_single_table, tn, fields)
                if not df.empty:
                    sap_data[tn] = df
                    rows_ok = len(df)
                    logger.info(f"  RFC: {tn} → {rows_ok} rows")
                else:
                    logger.info(f"  RFC: {tn} → 0 rows")
            except Exception as e:
                rows_fail = 1
                logger.warning(f"  RFC: failed to extract {tn}: {e}")

            total_rows += rows_ok
            total_failed += rows_fail

            if progress_callback:
                await progress_callback(table_name, rows_ok, rows_fail)

        return sap_data, total_rows, total_failed


# ============================================================================
# Factory
# ============================================================================

def create_extractor(connection, password: str) -> SAPTableExtractor:
    """Create the appropriate extractor based on connection method.

    Args:
        connection: SAPConnectionConfig dataclass or SAPConnection DB row
        password: Decrypted SAP password

    Returns:
        SAPTableExtractor subclass

    Raises:
        ImportError: If required library is not installed
        ValueError: If connection method is unsupported
    """
    from app.services.sap_deployment_service import ConnectionMethod

    method = connection.connection_method
    if isinstance(method, str):
        method = ConnectionMethod(method)

    # SAPConnectionConfig.user is mapped from DB row.sap_user
    user = getattr(connection, "user", None) or getattr(connection, "sap_user", "") or ""

    if method == ConnectionMethod.ODATA:
        return ODataExtractor(
            hostname=connection.hostname or "",
            port=connection.port or 44301,
            user=user,
            password=password,
            use_ssl=getattr(connection, "use_ssl", True),
            ssl_verify=getattr(connection, "ssl_verify", False),
            client=connection.client or "100",
            odata_base_path=getattr(connection, "odata_base_path", None),
        )

    elif method == ConnectionMethod.HANA_DB:
        return HANADBExtractor(
            hostname=connection.hostname or "",
            port=getattr(connection, "hana_port", None) or 30215,
            user=user,
            password=password,
            schema=getattr(connection, "hana_schema", None) or "SAPHANADB",
        )

    elif method == ConnectionMethod.RFC:
        return RFCExtractor(
            ashost=connection.ashost or connection.hostname or "",
            sysnr=connection.sysnr or "00",
            client=connection.client or "100",
            user=user,
            password=password,
            lang=getattr(connection, "language", None) or "EN",
        )

    else:
        raise ValueError(f"Unsupported extraction method: {method}")
