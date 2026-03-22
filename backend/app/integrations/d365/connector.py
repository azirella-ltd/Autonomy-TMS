"""
Microsoft Dynamics 365 Finance & Operations Connector

Provides API connectivity to D365 F&O instances using:
- OData v4 (primary) — real-time CRUD on data entities
- Data Management Framework (DMF) — bulk import/export packages
- CSV file-based extraction (offline)

Authentication: Azure AD / Microsoft Entra ID (OAuth 2.0 Client Credentials)

Contoso demo data entities:
    USMF = US Manufacturing company (primary)
    USRT = US Retail company

Usage:
    connector = D365Connector(
        base_url="https://contoso.operations.dynamics.com",
        tenant_id_azure="abc-123-...",
        client_id="def-456-...",
        client_secret="...",
        data_area_id="usmf",
    )
    await connector.authenticate()
    products = await connector.odata_query("ReleasedProductsV2", top=100)
"""

import logging
import json
import csv
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import aiohttp
from urllib.parse import quote

logger = logging.getLogger(__name__)


@dataclass
class D365ConnectionConfig:
    """Configuration for a Dynamics 365 F&O connection."""
    base_url: str = ""  # e.g. https://contoso.operations.dynamics.com
    tenant_id_azure: str = ""  # Azure AD tenant GUID
    client_id: str = ""  # App registration client ID
    client_secret: str = ""  # App registration client secret
    data_area_id: str = "usmf"  # Legal entity (company) — USMF for Contoso
    resource: str = ""  # Resource URI (usually same as base_url)
    timeout: int = 120
    # CSV-based
    csv_directory: Optional[str] = None


class D365Connector:
    """OData v4 connector for Dynamics 365 Finance & Operations.

    Follows the same connection-test-extract pattern as the SAP and Odoo connectors.
    """

    TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    def __init__(self, config: D365ConnectionConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    # ── Connection Lifecycle ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── OAuth 2.0 Authentication ─────────────────────────────────────────

    async def authenticate(self) -> str:
        """Authenticate via Azure AD Client Credentials flow.

        Returns the access token.
        """
        token_url = self.TOKEN_ENDPOINT.format(tenant=self.config.tenant_id_azure)
        resource = self.config.resource or self.config.base_url.rstrip("/")

        payload = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "scope": f"{resource}/.default",
        }

        session = await self._get_session()
        async with session.post(token_url, data=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ConnectionError(f"D365 OAuth failed ({resp.status}): {body}")
            data = await resp.json()

        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = datetime.utcnow() + timedelta(seconds=expires_in - 60)
        logger.info("D365: authenticated, token expires in %ds", expires_in)
        return self._access_token

    async def _ensure_token(self):
        """Refresh token if expired."""
        if not self._access_token or (self._token_expiry and datetime.utcnow() >= self._token_expiry):
            await self.authenticate()

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection by querying the OData root."""
        try:
            await self.authenticate()
            url = f"{self.config.base_url}/data/$metadata"
            session = await self._get_session()
            async with session.get(url, headers=self._auth_headers()) as resp:
                success = resp.status == 200
                return {
                    "success": success,
                    "status_code": resp.status,
                    "data_area_id": self.config.data_area_id,
                    "base_url": self.config.base_url,
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── OData v4 Queries ─────────────────────────────────────────────────

    async def odata_query(
        self,
        entity: str,
        select: Optional[List[str]] = None,
        filter_expr: Optional[str] = None,
        top: int = 0,
        skip: int = 0,
        order_by: Optional[str] = None,
        cross_company: bool = False,
    ) -> List[Dict]:
        """Execute an OData query against a D365 data entity.

        Args:
            entity: D365 data entity name (e.g. "ReleasedProductsV2")
            select: $select fields
            filter_expr: $filter OData expression
            top: $top limit (0 = server default, typically 10000)
            skip: $skip offset
            order_by: $orderby expression
            cross_company: If True, query across all legal entities
        """
        await self._ensure_token()

        url = f"{self.config.base_url}/data/{entity}"
        params = {}

        if not cross_company:
            # Scope to legal entity
            if filter_expr:
                filter_expr = f"dataAreaId eq '{self.config.data_area_id}' and ({filter_expr})"
            else:
                filter_expr = f"dataAreaId eq '{self.config.data_area_id}'"

        if select:
            params["$select"] = ",".join(select)
        if filter_expr:
            params["$filter"] = filter_expr
        if top:
            params["$top"] = str(top)
        if skip:
            params["$skip"] = str(skip)
        if order_by:
            params["$orderby"] = order_by
        if cross_company:
            params["cross-company"] = "true"

        session = await self._get_session()
        async with session.get(url, headers=self._auth_headers(), params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ConnectionError(f"D365 OData query {entity} failed ({resp.status}): {body[:500]}")
            data = await resp.json()

        return data.get("value", [])

    async def odata_query_all(
        self,
        entity: str,
        select: Optional[List[str]] = None,
        filter_expr: Optional[str] = None,
        page_size: int = 5000,
    ) -> List[Dict]:
        """Query all records with automatic server-driven paging.

        D365 OData uses @odata.nextLink for pagination.
        """
        await self._ensure_token()

        all_records = []
        url = f"{self.config.base_url}/data/{entity}"
        params: Dict[str, str] = {}

        if not filter_expr:
            filter_expr = f"dataAreaId eq '{self.config.data_area_id}'"
        else:
            filter_expr = f"dataAreaId eq '{self.config.data_area_id}' and ({filter_expr})"

        if select:
            params["$select"] = ",".join(select)
        params["$filter"] = filter_expr
        params["$top"] = str(page_size)

        session = await self._get_session()
        while url:
            async with session.get(url, headers=self._auth_headers(), params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise ConnectionError(f"D365 paged query failed ({resp.status}): {body[:500]}")
                data = await resp.json()

            records = data.get("value", [])
            all_records.extend(records)
            url = data.get("@odata.nextLink")
            params = {}  # nextLink includes all params

            if len(records) < page_size:
                break

            logger.debug("D365 paged %s: %d records so far", entity, len(all_records))

        logger.info("D365 extract %s: %d total records", entity, len(all_records))
        return all_records

    # ── CDC (Change Tracking) ────────────────────────────────────────────

    async def extract_changes(
        self,
        entity: str,
        since: datetime,
        select: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Extract records modified since a given datetime.

        D365 F&O data entities with change tracking enabled expose
        ``ModifiedDateTime`` (or ``RecVersion`` for tracking).
        """
        filter_expr = f"ModifiedDateTime gt {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        return await self.odata_query_all(entity, select=select, filter_expr=filter_expr)

    # ── Entity Discovery ─────────────────────────────────────────────────

    async def discover_entities(self) -> List[Dict]:
        """Discover available D365 data entities relevant to supply chain."""
        SC_ENTITIES = list(D365_SC_ENTITIES.keys())
        results = []
        for entity in SC_ENTITIES:
            try:
                records = await self.odata_query(entity, top=1)
                results.append({
                    "entity": entity,
                    "available": True,
                    "sample_count": len(records),
                })
            except Exception as e:
                results.append({
                    "entity": entity,
                    "available": False,
                    "error": str(e)[:100],
                })
        return results

    # ── CSV Export ───────────────────────────────────────────────────────

    async def export_to_csv(
        self,
        entity: str,
        output_dir: str,
        select: Optional[List[str]] = None,
        filter_expr: Optional[str] = None,
    ) -> str:
        """Extract entity data and write to CSV."""
        records = await self.odata_query_all(entity, select=select, filter_expr=filter_expr)
        if not records:
            return ""

        os.makedirs(output_dir, exist_ok=True)
        filename = f"{entity}.csv"
        filepath = os.path.join(output_dir, filename)

        fieldnames = sorted(set(k for r in records for k in r.keys()))
        # Remove OData metadata fields
        fieldnames = [f for f in fieldnames if not f.startswith("@odata")]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)

        logger.info("D365 CSV export %s: %d records → %s", entity, len(records), filepath)
        return filepath

    # ── CSV Import (file-based) ──────────────────────────────────────────

    @staticmethod
    def load_csv(filepath: str) -> Tuple[List[str], List[Dict]]:
        """Load a D365 DMF-exported CSV file."""
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            records = list(reader)
        return headers, records

    @staticmethod
    def identify_d365_entity(headers: List[str]) -> Optional[str]:
        """Identify which D365 entity a CSV represents based on column headers."""
        ENTITY_SIGNATURES = {
            "ReleasedProductsV2": {"ItemNumber", "ProductName", "ProductType", "ProductGroupId", "NetWeight"},
            "OperationalSites": {"SiteId", "SiteName", "DefaultFinancialDimensionValue"},
            "Warehouses": {"WarehouseId", "WarehouseName", "SiteId", "IsInventoryManaged"},
            "Vendors": {"VendorAccountNumber", "VendorName", "VendorGroupId"},
            "CustomersV3": {"CustomerAccount", "CustomerName", "CustomerGroupId"},
            "BillOfMaterialsHeaders": {"BOMId", "ProductNumber", "SiteId", "BOMName"},
            "BillOfMaterialsLines": {"BOMId", "ItemNumber", "BOMLineQuantity"},
            "PurchaseOrderHeadersV2": {"PurchaseOrderNumber", "VendorAccountNumber", "OrderDate"},
            "PurchaseOrderLinesV2": {"PurchaseOrderNumber", "ItemNumber", "PurchasedQuantity"},
            "SalesOrderHeadersV2": {"SalesOrderNumber", "CustomerAccountNumber", "OrderDate"},
            "SalesOrderLinesV2": {"SalesOrderNumber", "ItemNumber", "OrderedSalesQuantity"},
            "InventWarehouseOnHandEntity": {"ItemNumber", "WarehouseId", "PhysicalOnHandQuantity"},
            "DemandForecastEntries": {"ItemNumber", "ForecastQuantity", "ForecastDate"},
            "ProductionOrderHeaders": {"ProductionOrderNumber", "ItemNumber", "ProductionStatus"},
        }
        header_set = set(headers)
        best_entity = None
        best_score = 0.0
        for entity, sig in ENTITY_SIGNATURES.items():
            intersection = len(header_set & sig)
            union = len(header_set | sig)
            score = intersection / union if union else 0
            if score > best_score:
                best_score = score
                best_entity = entity
        return best_entity if best_score >= 0.15 else None


# ─────────────────────────────────────────────────────────────────────────────
# D365 Data Entity → Select Fields Mapping
# ─────────────────────────────────────────────────────────────────────────────

D365_SC_ENTITIES: Dict[str, List[str]] = {
    # Organisation
    "LegalEntities": [
        "DataArea", "Name", "AddressCountryRegionId", "CurrencyCode",
    ],
    # Sites & Warehouses
    "OperationalSites": [
        "SiteId", "SiteName", "DefaultFinancialDimensionValue",
    ],
    "Warehouses": [
        "WarehouseId", "WarehouseName", "SiteId", "IsInventoryManaged",
        "WarehouseType", "OperationalSiteId",
    ],
    # Products
    "ReleasedProductsV2": [
        "ItemNumber", "ProductName", "ProductType", "ProductSubType",
        "ProductGroupId", "InventoryUnitSymbol", "SalesPrice",
        "ProductionStandardCost", "NetWeight", "GrossWeight",
        "NetVolume", "BarcodeId",
    ],
    # Product categories / hierarchy
    "ProductCategories": [
        "CategoryId", "CategoryName", "ParentCategoryId", "CategoryHierarchyName",
    ],
    # BOMs
    "BillOfMaterialsHeaders": [
        "BOMId", "ProductNumber", "SiteId", "BOMName", "IsActive",
        "BOMQuantity", "BOMUnitSymbol",
    ],
    "BillOfMaterialsLines": [
        "BOMId", "LineNumber", "ItemNumber", "BOMLineQuantity",
        "BOMLineQuantityUnitSymbol", "ScrapPercentage",
    ],
    # Vendors (suppliers)
    "Vendors": [
        "VendorAccountNumber", "VendorName", "VendorGroupId",
        "AddressCountryRegionId", "AddressCity", "AddressZipCode",
        "PrimaryContactPhone", "PrimaryContactEmail",
    ],
    # Customers
    "CustomersV3": [
        "CustomerAccount", "CustomerName", "CustomerGroupId",
        "AddressCountryRegionId", "AddressCity", "AddressZipCode",
        "PrimaryContactPhone", "PrimaryContactEmail",
    ],
    # Vendor lead times & pricing
    "VendorLeadTimes": [
        "VendorAccountNumber", "ItemNumber", "SiteId", "LeadTimeDays",
    ],
    "VendorPurchasePrices": [
        "VendorAccountNumber", "ItemNumber", "UnitPrice", "Currency",
        "MinimumQuantity", "EffectiveDate",
    ],
    # Inventory
    "InventWarehouseOnHandEntity": [
        "ItemNumber", "WarehouseId", "SiteId",
        "PhysicalOnHandQuantity", "ReservedQuantity",
        "AvailableQuantity",
    ],
    # Inventory policies
    "InventItemOrderSetups": [
        "ItemNumber", "SiteId", "WarehouseId",
        "MinimumOrderQuantity", "MaximumOrderQuantity",
        "StandardOrderQuantity", "LeadTimePurchasing",
    ],
    # Coverage / safety stock / MRP planning parameters
    "ItemCoverageSettings": [
        "ItemNumber", "SiteId", "WarehouseId",
        "MinimumInventoryLevel", "MaximumInventoryLevel",
        "SafetyStockQuantity", "CoveragePlanGroupId",
        # Planning method & lot sizing (added for heuristic mirror — DIGITAL_TWIN.md §8C)
        "CoverageCode",              # MRP type: 0=Manual, 1=Period, 2=Requirement, 3=MinMax, 4=DDMRP
        "StandardOrderQuantity",     # Fixed lot size
        "MinimumOrderQuantity",      # MOQ
        "MaximumOrderQuantity",      # Max order qty
        "MultipleQuantity",          # Order rounding multiple
        "LeadTimePurchase",          # Purchase lead time override (days)
        "LeadTimeProduction",        # Production lead time override (days)
        "LeadTimeTransfer",          # Transfer lead time override (days)
        "CoverageTimeFence",         # Planning horizon (days)
        "LockingTimeFence",          # Firming time fence (days)
        "MaxPositiveDays",           # How early supply can be accepted
        "MaxNegativeDays",           # How late supply can cover demand
        "PreferredVendor",           # Primary vendor ID
        "FulfillMinimum",            # Minimum fill policy
    ],
    # Purchase orders
    "PurchaseOrderHeadersV2": [
        "PurchaseOrderNumber", "VendorAccountNumber", "OrderDate",
        "DeliveryDate", "PurchaseOrderStatus", "CurrencyCode",
        "TotalOrderAmount",
    ],
    "PurchaseOrderLinesV2": [
        "PurchaseOrderNumber", "LineNumber", "ItemNumber",
        "PurchasedQuantity", "ReceivedQuantity", "PurchasePrice",
        "DeliveryDate",
    ],
    # Sales orders
    "SalesOrderHeadersV2": [
        "SalesOrderNumber", "CustomerAccountNumber", "OrderDate",
        "RequestedShipDate", "SalesOrderStatus", "CurrencyCode",
        "TotalOrderAmount",
    ],
    "SalesOrderLinesV2": [
        "SalesOrderNumber", "LineNumber", "ItemNumber",
        "OrderedSalesQuantity", "DeliveredQuantity", "SalesPrice",
    ],
    # Production orders
    "ProductionOrderHeaders": [
        "ProductionOrderNumber", "ItemNumber", "ProductionQuantity",
        "ProductionStatus", "ScheduledStartDate", "ScheduledEndDate",
        "SiteId",
    ],
    # Forecasts
    "DemandForecastEntries": [
        "ItemNumber", "SiteId", "WarehouseId",
        "ForecastQuantity", "ForecastDate", "ForecastModel",
    ],
    # Transportation
    "TransportationRoutes": [
        "RouteId", "RouteName", "OriginSiteId", "DestinationSiteId",
        "TransitTimeDays", "TransportMode",
    ],
}
