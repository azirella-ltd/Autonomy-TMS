"""
SAP S/4HANA MCP Adapter.

Maps canonical supply chain operations to SAP OData MCP tool calls.
Works with:
- btp-sap-odata-to-mcp-server (BTP-hosted, auto-discovers OData services)
- odata-mcp-proxy (zero-code JSON config)
- hana-mcp-server (direct HANA SQL via MCP)

Inbound: polls for material/order/inventory changes since last sync
Outbound: creates PO/MO/TO/stock transfer via OData/BAPI MCP tools
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..client import MCPClientSession, MCPToolResult

logger = logging.getLogger(__name__)


# Default tool name mappings for btp-sap-odata-to-mcp-server
# These map canonical operations to the OData entity set names exposed by SAP
# The actual MCP tool names depend on the server implementation;
# these are overridden by MCPServerConfig.tool_mappings if set.
DEFAULT_TOOL_MAPPINGS = {
    # ── Inbound (read) ──
    "get_materials": "query_entities",        # A_Product
    "get_plants": "query_entities",           # A_Plant
    "get_purchase_orders": "query_entities",  # A_PurchaseOrder
    "get_sales_orders": "query_entities",     # A_SalesOrder
    "get_production_orders": "query_entities",  # A_ProductionOrder
    "get_inventory": "query_entities",        # A_MaterialStock
    "get_deliveries": "query_entities",       # A_InboundDelivery / A_OutboundDelivery
    "get_bom": "query_entities",              # A_BillOfMaterial
    "get_vendors": "query_entities",          # A_Supplier
    "get_customers": "query_entities",        # A_Customer

    # ── Outbound (write) ──
    "create_purchase_order": "create_entity",
    "update_purchase_order": "update_entity",
    "create_production_order": "create_entity",
    "create_stock_transfer": "create_entity",
    "update_sales_order": "update_entity",
}

# OData service paths for each entity type (SAP S/4HANA Cloud)
SAP_ENTITY_SETS = {
    "materials": {
        "service": "API_PRODUCT_SRV",
        "entity_set": "A_Product",
        "change_date_field": "LastChangeDateTime",
        "key_field": "Product",
    },
    "plants": {
        "service": "API_PLANT_SRV",
        "entity_set": "A_Plant",
        "change_date_field": None,
        "key_field": "Plant",
    },
    "purchase_orders": {
        "service": "API_PURCHASEORDER_PROCESS_SRV",
        "entity_set": "A_PurchaseOrder",
        "change_date_field": "LastChangeDateTime",
        "key_field": "PurchaseOrder",
    },
    "sales_orders": {
        "service": "API_SALES_ORDER_SRV",
        "entity_set": "A_SalesOrder",
        "change_date_field": "LastChangeDateTime",
        "key_field": "SalesOrder",
    },
    "production_orders": {
        "service": "API_PRODUCTION_ORDER_2_SRV",
        "entity_set": "A_ProductionOrder",
        "change_date_field": "LastChangeDateTime",
        "key_field": "ManufacturingOrder",
    },
    "inventory": {
        "service": "API_MATERIAL_STOCK_SRV",
        "entity_set": "A_MatlStkInAcctMod",
        "change_date_field": None,  # Inventory is snapshot, not delta
        "key_field": "Material",
    },
    "deliveries_inbound": {
        "service": "API_INBOUND_DELIVERY_SRV;v=0002",
        "entity_set": "A_InbDeliveryHeader",
        "change_date_field": "LastChangeDateTime",
        "key_field": "DeliveryDocument",
    },
    "deliveries_outbound": {
        "service": "API_OUTBOUND_DELIVERY_SRV;v=0002",
        "entity_set": "A_OutbDeliveryHeader",
        "change_date_field": "LastChangeDateTime",
        "key_field": "DeliveryDocument",
    },
    "bom": {
        "service": "API_BILL_OF_MATERIAL_SRV;v=0002",
        "entity_set": "A_BillOfMaterial",
        "change_date_field": "LastChangeDate",
        "key_field": "BillOfMaterial",
    },
    "vendors": {
        "service": "API_BUSINESS_PARTNER",
        "entity_set": "A_Supplier",
        "change_date_field": "LastChangeDateTime",
        "key_field": "Supplier",
    },
    "customers": {
        "service": "API_BUSINESS_PARTNER",
        "entity_set": "A_Customer",
        "change_date_field": "LastChangeDateTime",
        "key_field": "Customer",
    },
}

# Map SAP entity types to AWS SC data model entity types
SAP_TO_AWS_SC_ENTITY = {
    "materials": "product",
    "plants": "site",
    "purchase_orders": "inbound_order",
    "sales_orders": "outbound_order",
    "production_orders": "manufacturing_order",
    "inventory": "inventory_level",
    "deliveries_inbound": "shipment",
    "deliveries_outbound": "shipment",
    "bom": "product_bom",
    "vendors": "trading_partner",
    "customers": "trading_partner",
}


class SAPS4MCPAdapter:
    """SAP S/4HANA MCP adapter for live operations.

    Handles both inbound (CDC polling) and outbound (write-back) operations.
    """

    # Entity types to poll for CDC (ordered by dependency tier)
    CDC_POLL_ENTITIES = [
        "materials",       # Tier 1: master data
        "plants",
        "vendors",
        "customers",
        "bom",
        "purchase_orders",  # Tier 2: transactions
        "sales_orders",
        "production_orders",
        "deliveries_inbound",
        "deliveries_outbound",
        "inventory",        # Tier 3: snapshots
    ]

    def __init__(self, client: MCPClientSession):
        self.client = client

    async def poll_changes(
        self,
        since: datetime,
        entity_types: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Poll SAP for changes since the given timestamp.

        Args:
            since: Only return records changed after this timestamp
            entity_types: Optional filter — if None, polls all CDC_POLL_ENTITIES
            correlation_id: Tracing ID

        Returns:
            Dict mapping entity type → list of changed records
        """
        entities = entity_types or self.CDC_POLL_ENTITIES
        changes: Dict[str, List[Dict]] = {}

        for entity_type in entities:
            spec = SAP_ENTITY_SETS.get(entity_type)
            if not spec:
                logger.warning("Unknown SAP entity type: %s", entity_type)
                continue

            try:
                records = await self._query_entity(
                    entity_type=entity_type,
                    spec=spec,
                    since=since,
                    correlation_id=correlation_id,
                )
                if records:
                    changes[entity_type] = records
                    logger.info(
                        "SAP CDC: %s returned %d records since %s",
                        entity_type, len(records), since.isoformat(),
                    )
            except Exception as e:
                logger.error("SAP CDC poll failed for %s: %s", entity_type, e)

        return changes

    async def _query_entity(
        self,
        entity_type: str,
        spec: Dict,
        since: Optional[datetime] = None,
        top: int = 1000,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query a single SAP OData entity set via MCP."""
        # Build OData filter for CDC
        filters = []
        if since and spec.get("change_date_field"):
            # SAP OData datetime format
            since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
            filters.append(f"{spec['change_date_field']} gt datetime'{since_str}'")

        arguments = {
            "service": spec["service"],
            "entitySet": spec["entity_set"],
            "$top": top,
        }
        if filters:
            arguments["$filter"] = " and ".join(filters)

        # Resolve tool name
        canonical = f"get_{entity_type}" if not entity_type.startswith("get_") else entity_type
        tool_name = DEFAULT_TOOL_MAPPINGS.get(canonical, "query_entities")

        # Override from config mappings if available
        if self.client.params.tool_mappings:
            tool_name = self.client.params.tool_mappings.get(canonical, tool_name)

        result = await self.client.call_tool(
            tool_name, arguments, correlation_id=correlation_id
        )

        if not result.success:
            raise RuntimeError(f"SAP query failed for {entity_type}: {result.error}")

        # Parse result — OData returns {"d": {"results": [...]}} or {"value": [...]}
        data = result.data
        if isinstance(data, dict):
            if "d" in data and "results" in data["d"]:
                return data["d"]["results"]
            if "value" in data:
                return data["value"]
            if "results" in data:
                return data["results"]
        if isinstance(data, list):
            return data

        return []

    # ── Outbound: Write-back operations ──

    async def create_purchase_order(
        self,
        po_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Purchase Order in SAP S/4HANA via MCP.

        Args:
            po_data: PO payload in SAP OData format:
                {
                    "CompanyCode": "1000",
                    "PurchaseOrderType": "NB",
                    "Supplier": "VENDOR001",
                    "PurchasingOrganization": "1000",
                    "PurchasingGroup": "001",
                    "to_PurchaseOrderItem": [
                        {
                            "PurchaseOrderItem": "00010",
                            "Material": "MAT001",
                            "OrderQuantity": "100",
                            "Plant": "1000",
                            "NetPriceAmount": "10.00",
                            "NetPriceCurrency": "USD",
                        }
                    ]
                }
        """
        return await self.client.call_tool(
            "create_purchase_order",
            {
                "service": "API_PURCHASEORDER_PROCESS_SRV",
                "entitySet": "A_PurchaseOrder",
                "data": po_data,
            },
            correlation_id=correlation_id,
        )

    async def create_production_order(
        self,
        mo_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Production Order (planned order → production order conversion)."""
        return await self.client.call_tool(
            "create_production_order",
            {
                "service": "API_PRODUCTION_ORDER_2_SRV",
                "entitySet": "A_ProductionOrder",
                "data": mo_data,
            },
            correlation_id=correlation_id,
        )

    async def create_stock_transfer(
        self,
        to_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Stock Transfer Order for inventory rebalancing."""
        return await self.client.call_tool(
            "create_stock_transfer",
            {
                "service": "API_MATERIAL_DOCUMENT_SRV",
                "entitySet": "A_MaterialDocumentHeader",
                "data": to_data,
            },
            correlation_id=correlation_id,
        )

    async def update_sales_order(
        self,
        sales_order_id: str,
        update_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Update a Sales Order (e.g., ATP confirmation, schedule line update)."""
        return await self.client.call_tool(
            "update_sales_order",
            {
                "service": "API_SALES_ORDER_SRV",
                "entitySet": "A_SalesOrder",
                "key": sales_order_id,
                "data": update_data,
            },
            correlation_id=correlation_id,
        )

    async def check_material_availability(
        self,
        material: str,
        plant: str,
        requirement_date: str,
        requirement_qty: float,
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Real-time ATP check via MCP (replaces BAPI_MATERIAL_AVAILABILITY)."""
        return await self.client.call_tool(
            "query_entities",
            {
                "service": "API_MATERIAL_AVAILABILITY_INFO_BASIC_SRV",
                "entitySet": "A_MatlAvailInfo",
                "$filter": (
                    f"Material eq '{material}' and "
                    f"Plant eq '{plant}' and "
                    f"MatlAvailDate eq datetime'{requirement_date}'"
                ),
            },
            correlation_id=correlation_id,
        )
