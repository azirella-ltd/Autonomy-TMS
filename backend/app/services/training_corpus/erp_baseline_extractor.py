"""
ERP Baseline Extractor — Loads the tenant's current operating plan.

Reads the erp_baseline plan_version from the database to build an
ERPBaselineSnapshot that serves as the anchor for perturbation generation.

The baseline captures everything needed to reproduce the tenant's current
operating reality: topology, inventory, policies, costs, lead times, forecast.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class BaselineSite:
    site_id: str
    name: str
    master_type: str  # manufacturer, inventory, retailer, vendor, customer
    geo_id: Optional[str] = None


@dataclass
class BaselineProduct:
    product_id: str
    name: str
    unit_cost: float = 0.0
    unit_price: float = 0.0
    category: Optional[str] = None


@dataclass
class BaselineLane:
    from_site: str
    to_site: str
    lead_time_days: float
    transport_cost: float = 0.0
    capacity_units: float = float("inf")
    reliability: float = 0.95


@dataclass
class BaselineInventory:
    product_id: str
    site_id: str
    on_hand: float
    in_transit: float = 0.0
    allocated: float = 0.0
    safety_stock: float = 0.0
    reorder_point: float = 0.0
    max_stock: float = 0.0


@dataclass
class BaselineForecast:
    product_id: str
    site_id: str
    period_start: str  # ISO date
    quantity_p50: float
    quantity_p10: Optional[float] = None
    quantity_p90: Optional[float] = None


@dataclass
class BaselineOpenOrder:
    order_id: str
    order_type: str  # po, so, mo, to
    product_id: str
    site_id: str
    quantity: float
    due_date: Optional[str] = None
    vendor_id: Optional[str] = None


@dataclass
class ERPBaselineSnapshot:
    """Complete snapshot of the tenant's current ERP operating plan."""
    config_id: int
    tenant_id: int
    sites: List[BaselineSite] = field(default_factory=list)
    products: List[BaselineProduct] = field(default_factory=list)
    lanes: List[BaselineLane] = field(default_factory=list)
    inventory: List[BaselineInventory] = field(default_factory=list)
    forecast: List[BaselineForecast] = field(default_factory=list)
    open_orders: List[BaselineOpenOrder] = field(default_factory=list)

    def get_site_ids(self) -> List[str]:
        return [s.site_id for s in self.sites]

    def get_product_ids(self) -> List[str]:
        return [p.product_id for p in self.products]


class ERPBaselineExtractor:
    """Loads the ERP baseline from the database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def extract(self, config_id: int) -> ERPBaselineSnapshot:
        """Extract complete baseline snapshot for a config."""
        # Resolve tenant_id
        result = await self.db.execute(
            sql_text("SELECT tenant_id FROM supply_chain_configs WHERE id = :cid"),
            {"cid": config_id},
        )
        row = result.fetchone()
        tenant_id = row.tenant_id if row else 0

        snapshot = ERPBaselineSnapshot(config_id=config_id, tenant_id=tenant_id)

        # Sites
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT id, description as name, master_type, geo_id
                    FROM site
                    WHERE config_id = :cid
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                snapshot.sites.append(BaselineSite(
                    site_id=str(row.id),
                    name=row.name or str(row.id),
                    master_type=row.master_type or "inventory",
                    geo_id=row.geo_id,
                ))
        except Exception as e:
            logger.debug("Site extraction failed: %s", e)

        # Products
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT id, description as name,
                           COALESCE(unit_cost, 0) as unit_cost,
                           COALESCE(unit_price, 0) as unit_price
                    FROM product
                    WHERE config_id = :cid
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                snapshot.products.append(BaselineProduct(
                    product_id=str(row.id),
                    name=row.name or str(row.id),
                    unit_cost=float(row.unit_cost or 0),
                    unit_price=float(row.unit_price or 0),
                ))
        except Exception as e:
            logger.debug("Product extraction failed: %s", e)

        # Transportation lanes
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT from_site_id, to_site_id,
                           COALESCE(transit_time, 2) as transit_time,
                           COALESCE(transit_time_uom, 'day') as uom
                    FROM transportation_lane
                    WHERE config_id = :cid
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                lt_days = float(row.transit_time or 2.0)
                if row.uom == "week":
                    lt_days *= 7.0
                elif row.uom == "hour":
                    lt_days /= 24.0
                snapshot.lanes.append(BaselineLane(
                    from_site=str(row.from_site_id),
                    to_site=str(row.to_site_id),
                    lead_time_days=lt_days,
                ))
        except Exception as e:
            logger.debug("Lane extraction failed: %s", e)

        # Current inventory + policy
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT
                        il.product_id,
                        il.site_id,
                        COALESCE(il.on_hand_quantity, 0) as on_hand,
                        COALESCE(il.in_transit_quantity, 0) as in_transit,
                        COALESCE(il.allocated_quantity, 0) as allocated,
                        COALESCE(ip.safety_stock_quantity, 0) as safety_stock,
                        COALESCE(ip.reorder_point, 0) as reorder_point,
                        COALESCE(ip.max_stock_quantity, 0) as max_stock
                    FROM inventory_level il
                    LEFT JOIN inventory_policy ip
                        ON ip.product_id = il.product_id
                        AND ip.site_id = il.site_id
                        AND ip.config_id = il.config_id
                    WHERE il.config_id = :cid
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                snapshot.inventory.append(BaselineInventory(
                    product_id=str(row.product_id),
                    site_id=str(row.site_id),
                    on_hand=float(row.on_hand),
                    in_transit=float(row.in_transit),
                    allocated=float(row.allocated),
                    safety_stock=float(row.safety_stock),
                    reorder_point=float(row.reorder_point),
                    max_stock=float(row.max_stock),
                ))
        except Exception as e:
            logger.debug("Inventory extraction failed: %s", e)

        # Forecast (current P10/P50/P90)
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT product_id, site_id, period_start,
                           COALESCE(quantity, 0) as p50,
                           quantity_p10, quantity_p90
                    FROM forecast
                    WHERE config_id = :cid
                      AND plan_version = 'live'
                    LIMIT 10000
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                snapshot.forecast.append(BaselineForecast(
                    product_id=str(row.product_id),
                    site_id=str(row.site_id),
                    period_start=row.period_start.isoformat() if row.period_start else "",
                    quantity_p50=float(row.p50),
                    quantity_p10=float(row.quantity_p10) if row.quantity_p10 else None,
                    quantity_p90=float(row.quantity_p90) if row.quantity_p90 else None,
                ))
        except Exception as e:
            logger.debug("Forecast extraction failed: %s", e)

        # Open POs from erp_baseline plan_version
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT id, product_id, site_id,
                           COALESCE(quantity, 0) as quantity,
                           requested_delivery_date,
                           supplier_id
                    FROM inbound_order
                    WHERE config_id = :cid
                      AND status IN ('open', 'confirmed', 'in_transit')
                    LIMIT 5000
                """),
                {"cid": config_id},
            )
            for row in result.fetchall():
                snapshot.open_orders.append(BaselineOpenOrder(
                    order_id=str(row.id),
                    order_type="po",
                    product_id=str(row.product_id),
                    site_id=str(row.site_id),
                    quantity=float(row.quantity),
                    due_date=row.requested_delivery_date.isoformat() if row.requested_delivery_date else None,
                    vendor_id=str(row.supplier_id) if row.supplier_id else None,
                ))
        except Exception as e:
            logger.debug("Open PO extraction failed: %s", e)

        logger.info(
            "ERP baseline extracted: config=%d sites=%d products=%d lanes=%d inventory=%d forecast=%d POs=%d",
            config_id,
            len(snapshot.sites), len(snapshot.products), len(snapshot.lanes),
            len(snapshot.inventory), len(snapshot.forecast), len(snapshot.open_orders),
        )
        return snapshot
