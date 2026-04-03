"""
Microsoft Dynamics 365 F&O MCP Adapter.

Maps canonical supply chain operations to the official D365 ERP MCP server.
Uses the dynamic MCP server (v2025+) which supports all ERP features.

Reference: https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/copilot-mcp

The D365 MCP server exposes three tool categories:
- Form tools: Interact with D365 forms
- API tools: Call OData/REST endpoints
- Data tools: CRUD operations (Create, Read, Update, Delete)

Inbound: polls for order/inventory changes via OData $filter
Outbound: creates PO/MO/TO via Data tools
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..client import MCPClientSession, MCPToolResult

logger = logging.getLogger(__name__)


# D365 entity → AWS SC entity type mapping
D365_TO_AWS_SC_ENTITY = {
    "ReleasedProductsV2": "product",
    "OperationalSites": "site",
    "Warehouses": "site",
    "Vendors": "trading_partner",
    "CustomersV3": "trading_partner",
    "PurchaseOrderHeadersV2": "inbound_order",
    "SalesOrderHeadersV2": "outbound_order",
    "ProductionOrders": "manufacturing_order",
    "TransferOrderHeaders": "shipment",
    "InventOnHandV2": "inventory_level",
    "BillOfMaterialsV3": "product_bom",
}

# CDC polling configuration
CDC_POLL_ENTITIES = [
    {
        "entity": "ReleasedProductsV2",
        "entity_type": "materials",
        "key_field": "ItemNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "OperationalSites",
        "entity_type": "sites",
        "key_field": "SiteId",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "Warehouses",
        "entity_type": "warehouses",
        "key_field": "WarehouseId",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "VendorsV2",
        "entity_type": "vendors",
        "key_field": "VendorAccountNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "PurchaseOrderHeadersV2",
        "entity_type": "purchase_orders",
        "key_field": "PurchaseOrderNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "SalesOrderHeadersV2",
        "entity_type": "sales_orders",
        "key_field": "SalesOrderNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "ProductionOrders",
        "entity_type": "production_orders",
        "key_field": "ProductionOrderNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "TransferOrderHeaders",
        "entity_type": "transfer_orders",
        "key_field": "TransferOrderNumber",
        "change_field": "ModifiedDateTime",
    },
    {
        "entity": "InventOnHandV2",
        "entity_type": "inventory",
        "key_field": "ItemNumber",
        "change_field": None,  # Snapshot
    },
]


class D365MCPAdapter:
    """Dynamics 365 F&O MCP adapter for live operations."""

    def __init__(self, client: MCPClientSession):
        self.client = client

    async def poll_changes(
        self,
        since: datetime,
        entity_types: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Poll D365 for changes since the given timestamp."""
        changes: Dict[str, List[Dict]] = {}

        for spec in CDC_POLL_ENTITIES:
            if entity_types and spec["entity_type"] not in entity_types:
                continue

            try:
                # Build OData filter
                filter_str = ""
                if spec.get("change_field"):
                    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
                    filter_str = f"{spec['change_field']} gt {since_str}"

                # D365 MCP server uses "read_data" or entity-specific tools
                arguments = {
                    "entity": spec["entity"],
                    "$top": 1000,
                }
                if filter_str:
                    arguments["$filter"] = filter_str

                result = await self.client.call_tool(
                    "read_data",
                    arguments,
                    correlation_id=correlation_id,
                )

                if result.success and result.data:
                    records = []
                    if isinstance(result.data, dict):
                        records = result.data.get("value", [])
                    elif isinstance(result.data, list):
                        records = result.data

                    if records:
                        changes[spec["entity_type"]] = records
                        logger.info(
                            "D365 CDC: %s returned %d records since %s",
                            spec["entity_type"], len(records), since.isoformat(),
                        )
            except Exception as e:
                logger.error("D365 CDC poll failed for %s: %s", spec["entity"], e)

        return changes

    # ── Outbound: Write-back operations ──

    async def create_purchase_order(
        self,
        po_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Purchase Order in D365."""
        return await self.client.call_tool(
            "create_data",
            {
                "entity": "PurchaseOrderHeadersV2",
                "data": {
                    "OrderVendorAccountNumber": po_data.get("vendor_id", ""),
                    "PurchaseOrderName": po_data.get("description", ""),
                    "dataAreaId": po_data.get("data_area_id", ""),
                },
            },
            correlation_id=correlation_id,
        )

    async def create_production_order(
        self,
        mo_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Production Order in D365."""
        return await self.client.call_tool(
            "create_data",
            {
                "entity": "ProductionOrders",
                "data": {
                    "ItemNumber": mo_data.get("product_id", ""),
                    "ProductionSiteId": mo_data.get("site_id", ""),
                    "ProductionWarehouseId": mo_data.get("warehouse_id", ""),
                    "ScheduledQuantity": mo_data.get("quantity", 0),
                    "ScheduledStartDate": mo_data.get("start_date", ""),
                    "ScheduledEndDate": mo_data.get("end_date", ""),
                },
            },
            correlation_id=correlation_id,
        )

    async def create_transfer_order(
        self,
        to_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Transfer Order in D365."""
        return await self.client.call_tool(
            "create_data",
            {
                "entity": "TransferOrderHeaders",
                "data": {
                    "SendingWarehouseId": to_data.get("from_site_id", ""),
                    "ReceivingWarehouseId": to_data.get("to_site_id", ""),
                    "TransferOrderPromisingMethod": "ATP",
                },
            },
            correlation_id=correlation_id,
        )
