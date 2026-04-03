"""
Odoo MCP Adapter.

Maps canonical supply chain operations to Odoo MCP tool calls.
Works with mcp-server-odoo (PyPI: mcp-server-odoo) which exposes:
- odoo_search_read: Search and read records from any Odoo model
- odoo_create: Create records in any Odoo model
- odoo_write: Update records in any Odoo model
- odoo_unlink: Delete records
- odoo_execute: Execute arbitrary Odoo methods

Inbound: polls for changes via write_date filtering
Outbound: creates PO/MO/TO via model-specific create calls
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..client import MCPClientSession, MCPToolResult

logger = logging.getLogger(__name__)


# Odoo model → AWS SC entity type mapping
ODOO_TO_AWS_SC_ENTITY = {
    "product.product": "product",
    "stock.warehouse": "site",
    "stock.location": "site",
    "res.partner": "trading_partner",
    "purchase.order": "inbound_order",
    "sale.order": "outbound_order",
    "mrp.production": "manufacturing_order",
    "stock.picking": "shipment",
    "stock.quant": "inventory_level",
    "mrp.bom": "product_bom",
}

# Odoo models to poll for CDC, ordered by dependency
CDC_POLL_MODELS = [
    {
        "model": "product.product",
        "entity_type": "materials",
        "key_field": "id",
        "fields": ["id", "name", "default_code", "type", "uom_id", "categ_id",
                    "standard_price", "list_price", "weight", "volume", "write_date"],
    },
    {
        "model": "stock.warehouse",
        "entity_type": "plants",
        "key_field": "id",
        "fields": ["id", "name", "code", "partner_id", "company_id", "write_date"],
    },
    {
        "model": "res.partner",
        "entity_type": "vendors",
        "key_field": "id",
        "fields": ["id", "name", "ref", "supplier_rank", "customer_rank",
                    "street", "city", "country_id", "write_date"],
        "domain": "[('supplier_rank', '>', 0)]",
    },
    {
        "model": "purchase.order",
        "entity_type": "purchase_orders",
        "key_field": "id",
        "fields": ["id", "name", "partner_id", "date_order", "date_planned",
                    "state", "amount_total", "order_line", "write_date"],
    },
    {
        "model": "sale.order",
        "entity_type": "sales_orders",
        "key_field": "id",
        "fields": ["id", "name", "partner_id", "date_order", "commitment_date",
                    "state", "amount_total", "order_line", "write_date"],
    },
    {
        "model": "mrp.production",
        "entity_type": "production_orders",
        "key_field": "id",
        "fields": ["id", "name", "product_id", "product_qty", "date_planned_start",
                    "date_planned_finished", "state", "write_date"],
    },
    {
        "model": "stock.picking",
        "entity_type": "deliveries",
        "key_field": "id",
        "fields": ["id", "name", "origin", "partner_id", "picking_type_id",
                    "state", "scheduled_date", "date_done", "write_date"],
    },
    {
        "model": "stock.quant",
        "entity_type": "inventory",
        "key_field": "id",
        "fields": ["id", "product_id", "location_id", "quantity",
                    "reserved_quantity", "write_date"],
        "domain": "[('location_id.usage', '=', 'internal')]",
    },
]


class OdooMCPAdapter:
    """Odoo MCP adapter for live operations."""

    def __init__(self, client: MCPClientSession):
        self.client = client

    async def poll_changes(
        self,
        since: datetime,
        entity_types: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Poll Odoo for changes since the given timestamp."""
        changes: Dict[str, List[Dict]] = {}

        for spec in CDC_POLL_MODELS:
            if entity_types and spec["entity_type"] not in entity_types:
                continue

            try:
                # Build domain filter with write_date
                since_str = since.strftime("%Y-%m-%d %H:%M:%S")
                domain = f"[('write_date', '>=', '{since_str}')]"
                if spec.get("domain"):
                    # Merge domains
                    base = spec["domain"].rstrip("]")
                    domain = f"{base}, ('write_date', '>=', '{since_str}')]"

                result = await self.client.call_tool(
                    "odoo_search_read",
                    {
                        "model": spec["model"],
                        "domain": domain,
                        "fields": spec["fields"],
                        "limit": 1000,
                    },
                    correlation_id=correlation_id,
                )

                if result.success and result.data:
                    records = result.data if isinstance(result.data, list) else []
                    if records:
                        changes[spec["entity_type"]] = records
                        logger.info(
                            "Odoo CDC: %s (%s) returned %d records since %s",
                            spec["entity_type"], spec["model"],
                            len(records), since.isoformat(),
                        )
            except Exception as e:
                logger.error("Odoo CDC poll failed for %s: %s", spec["model"], e)

        return changes

    # ── Outbound: Write-back operations ──

    async def create_purchase_order(
        self,
        po_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Purchase Order in Odoo."""
        # Create PO header
        header_result = await self.client.call_tool(
            "odoo_create",
            {
                "model": "purchase.order",
                "values": {
                    "partner_id": po_data.get("vendor_id"),
                    "date_planned": po_data.get("delivery_date", ""),
                },
            },
            correlation_id=correlation_id,
        )

        if not header_result.success:
            return header_result

        po_id = header_result.data
        if not po_id:
            return header_result

        # Create PO lines
        for item in po_data.get("items", []):
            await self.client.call_tool(
                "odoo_create",
                {
                    "model": "purchase.order.line",
                    "values": {
                        "order_id": po_id,
                        "product_id": item.get("product_id"),
                        "product_qty": item.get("quantity", 0),
                        "price_unit": item.get("unit_price", 0),
                        "date_planned": item.get("delivery_date", ""),
                    },
                },
                correlation_id=correlation_id,
            )

        return header_result

    async def create_manufacturing_order(
        self,
        mo_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create a Manufacturing Order in Odoo."""
        return await self.client.call_tool(
            "odoo_create",
            {
                "model": "mrp.production",
                "values": {
                    "product_id": mo_data.get("product_id"),
                    "product_qty": mo_data.get("quantity", 0),
                    "date_planned_start": mo_data.get("start_date", ""),
                    "date_planned_finished": mo_data.get("end_date", ""),
                },
            },
            correlation_id=correlation_id,
        )

    async def create_transfer_order(
        self,
        to_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> MCPToolResult:
        """Create an internal transfer (stock.picking) in Odoo."""
        return await self.client.call_tool(
            "odoo_create",
            {
                "model": "stock.picking",
                "values": {
                    "picking_type_id": to_data.get("picking_type_id"),
                    "location_id": to_data.get("from_location_id"),
                    "location_dest_id": to_data.get("to_location_id"),
                    "move_ids_without_package": [(0, 0, {
                        "name": to_data.get("description", "Inventory rebalancing"),
                        "product_id": to_data.get("product_id"),
                        "product_uom_qty": to_data.get("quantity", 0),
                        "location_id": to_data.get("from_location_id"),
                        "location_dest_id": to_data.get("to_location_id"),
                    })],
                },
            },
            correlation_id=correlation_id,
        )
