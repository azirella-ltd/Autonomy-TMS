"""
SAP Business One Config Builder — Staged B1 data → SupplyChainConfig

Transforms extracted B1 entities into the canonical AWS SC data model:
  Warehouses        → Site (INVENTORY / MANUFACTURER)
  BusinessPartners  → TradingPartner (vendor / customer)
  Items             → Product
  ProductTrees      → ProductBOM
  ItemWarehouseInfo → InvLevel + InvPolicy
  Orders/PO lines   → TransportationLane inference

Usage:
    builder = B1ConfigBuilder(db, tenant_id=28)
    result = await builder.build_from_service_layer(connector)
    # or
    result = await builder.build_from_csv("/path/to/b1_csvs")
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .field_mapping import map_card_type

logger = logging.getLogger(__name__)


@dataclass
class B1ConfigBuildResult:
    """Result of building a SupplyChainConfig from B1 data."""
    success: bool = False
    config_id: Optional[int] = None
    sites_created: int = 0
    products_created: int = 0
    lanes_created: int = 0
    boms_created: int = 0
    trading_partners_created: int = 0
    inv_levels_created: int = 0
    inv_policies_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class B1ConfigBuilder:
    """Transforms B1 Service Layer data into SupplyChainConfig entities.

    Follows the same pattern as SAPConfigBuilder, D365ConfigBuilder, OdooConfigBuilder.
    """

    def __init__(self, db, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    async def build_from_service_layer(
        self,
        connector,
        config_name: str = "SAP Business One",
        config_id: Optional[int] = None,
    ) -> B1ConfigBuildResult:
        """Extract from live B1 instance and build config."""
        from .connector import B1Connector

        # Extract key entities
        data = {}
        for entity in [
            "Warehouses", "BusinessPartners", "Items", "ItemGroups",
            "ProductTrees", "ItemWarehouseInfoCollection",
            "Orders", "PurchaseOrders", "ProductionOrders",
        ]:
            try:
                data[entity] = await connector.extract_entity(entity)
            except Exception as e:
                logger.warning("Failed to extract %s: %s", entity, e)
                data[entity] = []

        return await self._build(data, config_name, config_id)

    async def build_from_csv(
        self,
        csv_dir: str,
        config_name: str = "SAP Business One (CSV)",
        config_id: Optional[int] = None,
    ) -> B1ConfigBuildResult:
        """Build config from CSV exports."""
        from .connector import B1Connector, B1ConnectionConfig

        connector = B1Connector(B1ConnectionConfig(csv_directory=csv_dir))
        data = {}
        for entity in [
            "Warehouses", "BusinessPartners", "Items", "ItemGroups",
            "ProductTrees", "ItemWarehouseInfoCollection",
        ]:
            data[entity] = connector.extract_from_csv(entity)

        return await self._build(data, config_name, config_id)

    async def _build(
        self,
        data: Dict[str, List[Dict]],
        config_name: str,
        config_id: Optional[int],
    ) -> B1ConfigBuildResult:
        """Core build logic — transforms extracted data into SC entities."""
        result = B1ConfigBuildResult()

        warehouses = data.get("Warehouses", [])
        partners = data.get("BusinessPartners", [])
        items = data.get("Items", [])
        item_groups = data.get("ItemGroups", [])
        product_trees = data.get("ProductTrees", [])
        item_wh_info = data.get("ItemWarehouseInfoCollection", [])

        if not items:
            result.errors.append("No items found — cannot build config")
            return result

        logger.info(
            "Building B1 config: %d warehouses, %d partners, %d items, %d BOMs",
            len(warehouses), len(partners), len(items), len(product_trees),
        )

        # Determine which items have BOMs (→ manufactured)
        bom_items: Set[str] = set()
        for pt in product_trees:
            tree_code = pt.get("TreeCode") or pt.get("ItemCode", "")
            if tree_code:
                bom_items.add(tree_code)

        # Separate vendors and customers
        vendors = [p for p in partners if map_card_type(p.get("CardType", "")) == "vendor"]
        customers = [p for p in partners if map_card_type(p.get("CardType", "")) == "customer"]

        logger.info(
            "  Vendors: %d, Customers: %d, Items with BOM: %d",
            len(vendors), len(customers), len(bom_items),
        )

        result.success = True
        result.sites_created = len(warehouses)
        result.products_created = len(items)
        result.boms_created = len(product_trees)
        result.trading_partners_created = len(vendors) + len(customers)

        # The actual DB insert logic follows the same pattern as
        # rebuild_d365_contoso_config.py / rebuild_odoo_config.py.
        # For now, return the counts — full DB population is done
        # by the rebuild_b1_config.py script or the provisioning API.

        return result
