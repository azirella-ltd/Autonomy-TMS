"""
Food Distribution 2-Year History Generator

Generates 2 years of daily transactional history for the Food Dist config
across 10 AWS SC data model entity types:

1. OutboundOrderLine — customer demand orders
2. InboundOrder / InboundOrderLine — supplier purchase orders
3. Shipment + ShipmentLot — material movement with food lot traceability
4. Forecast — daily P10/P50/P90 demand forecasts
5. InvLevel — daily inventory snapshots per site×product
6. FulfillmentOrder — warehouse pick/pack/ship execution
7. ConsensusDemand — monthly S&OP consensus records
8. SupplementaryTimeSeries — external demand signals
9. InventoryProjection — weekly ATP/CTP projections
10. Backorder — unfulfilled demand tracking

All entities strictly follow the AWS SC Data Model definitions in sc_entities.py.
"""

import random
import math
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.supply_chain_config import Node
from app.models.sc_entities import (
    OutboundOrderLine, InboundOrder,
    Shipment, ShipmentLot, Forecast, InvLevel,
    FulfillmentOrder, ConsensusDemand, SupplementaryTimeSeries,
    InventoryProjection, Backorder,
)
from app.services.food_dist_config_generator import (
    ALL_PRODUCT_GROUPS, SUPPLIERS, CUSTOMERS, RDCS, DC_CONFIG,
    ProductDefinition, CustomerDefinition, SupplierDefinition,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Seasonality Profiles (month index 0=Jan through 11=Dec)
# ============================================================================

SEASON_PROFILES = {
    "FRZ_PROTEIN": [0.85, 0.85, 0.90, 0.95, 1.05, 1.15, 1.25, 1.15, 1.00, 0.90, 1.10, 1.20],
    "REF_DAIRY":   [1.05, 1.00, 0.95, 0.95, 1.00, 1.00, 1.00, 1.00, 0.95, 0.95, 1.05, 1.10],
    "DRY_PANTRY":  [0.90, 0.90, 0.95, 0.95, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.10, 1.15],
    "FRZ_DESSERT": [0.70, 0.75, 0.85, 0.95, 1.10, 1.30, 1.40, 1.30, 1.05, 0.85, 0.90, 1.00],
    "BEV":         [0.75, 0.80, 0.90, 1.00, 1.15, 1.30, 1.40, 1.35, 1.10, 0.90, 0.80, 0.75],
}

# Day-of-week order weight (Mon=0 to Fri=4)
DOW_WEIGHTS = [1.30, 1.15, 1.05, 0.95, 0.55]

# Customer primary order day (0=Mon to 4=Fri)
CUSTOMER_ORDER_DAY = {
    "CUST_PDX": 0, "CUST_EUG": 1, "CUST_SAL": 0,
    "CUST_SEA": 1, "CUST_TAC": 2, "CUST_SPO": 3,
    "CUST_LAX": 0, "CUST_SFO": 1, "CUST_SDG": 2,
    "CUST_SAC": 3, "CUST_PHX": 0, "CUST_TUS": 1,
    "CUST_MES": 2,
}

# Carrier pool for shipments
CARRIERS = [
    ("CARRIER_SYSCO", "Sysco Logistics"),
    ("CARRIER_USFD", "US Foods Delivery"),
    ("CARRIER_PFG", "Performance Food Group"),
    ("CARRIER_MCLANE", "McLane Foodservice"),
]

# ============================================================================
# Reverse lookups
# ============================================================================

# Build SKU → supplier mapping
_SKU_TO_SUPPLIER: Dict[str, SupplierDefinition] = {}
for _sup in SUPPLIERS:
    for _sku in _sup.product_skus:
        _SKU_TO_SUPPLIER[_sku] = _sup

# Build SKU → ProductDefinition and SKU → group code
_SKU_TO_PRODUCT: Dict[str, ProductDefinition] = {}
_SKU_TO_GROUP: Dict[str, str] = {}
_ALL_SKUS: List[str] = []
for _grp in ALL_PRODUCT_GROUPS:
    for _prod in _grp.products:
        _SKU_TO_PRODUCT[_prod.sku] = _prod
        _SKU_TO_GROUP[_prod.sku] = _grp.code
        _ALL_SKUS.append(_prod.sku)

# Customer → region
_CUST_REGION: Dict[str, str] = {c.code: c.region for c in CUSTOMERS}
_CUST_MAP: Dict[str, CustomerDefinition] = {c.code: c for c in CUSTOMERS}


# ============================================================================
# Helper: batch insert
# ============================================================================

async def _batch_add(db: AsyncSession, records: list, batch_size: int = 2000):
    """Add records in batches to avoid memory pressure."""
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        db.add_all(batch)
        await db.flush()


# ============================================================================
# Main Generator
# ============================================================================

class FoodDistHistoryGenerator:
    """Generates 2 years of daily transactional history for Food Dist."""

    def __init__(self, db: AsyncSession, config_id: int, tenant_id: int,
                 company_id: str = None):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self.company_id = company_id  # AWS SC company_id, loaded from DB if not provided

        # Site ID mappings loaded from DB
        self.site_ids: Dict[str, int] = {}

        # Counters for unique IDs
        self._order_seq = 0
        self._po_seq = 0
        self._sh_seq = 0
        self._fo_seq = 0
        self._bo_seq = 0

    # ------------------------------------------------------------------
    # Network loading
    # ------------------------------------------------------------------

    async def _load_network(self):
        """Load node IDs and product IDs from DB for this config."""
        result = await self.db.execute(
            select(Node).where(Node.config_id == self.config_id)
        )
        nodes = result.scalars().all()
        for node in nodes:
            self.site_ids[node.name] = node.id
        logger.info(f"Loaded {len(self.site_ids)} site IDs for config {self.config_id}")

        # Validate critical sites exist
        for name in ["CDC_WEST", "RDC_NW", "RDC_SW"]:
            if name not in self.site_ids:
                raise ValueError(f"Missing internal site node: {name}")

        # Resolve company_id from first site if not provided
        if not self.company_id:
            for node in nodes:
                if node.company_id:
                    self.company_id = node.company_id
                    break
        logger.info(f"Using company_id: {self.company_id}")

        # Load product ID mapping (base SKU → actual DB product ID)
        # Products are stored as "CFG{config_id}_{SKU}" in the DB
        from app.models.sc_entities import Product
        prod_result = await self.db.execute(
            select(Product).where(Product.id.like(f"CFG{self.config_id}_%"))
        )
        products = prod_result.scalars().all()
        self._product_id_map: Dict[str, str] = {}
        prefix = f"CFG{self.config_id}_"
        for prod in products:
            base_sku = prod.id.replace(prefix, "")
            self._product_id_map[base_sku] = prod.id
        logger.info(f"Loaded {len(self._product_id_map)} product ID mappings")

    def _pid(self, sku: str) -> str:
        """Map base SKU to actual DB product ID."""
        return self._product_id_map.get(sku, sku)

    # ------------------------------------------------------------------
    # Demand model
    # ------------------------------------------------------------------

    def _daily_demand(
        self, sku: str, customer: CustomerDefinition, d: date, day_offset: int
    ) -> float:
        """Compute expected daily demand for one product×customer."""
        prod = _SKU_TO_PRODUCT[sku]
        group_code = _SKU_TO_GROUP[sku]

        # Base daily demand (weekly mean / 5 business days, scaled by customer)
        base = (prod.weekly_demand_mean / 5.0) * customer.demand_multiplier

        # Normalize across 13 customers so total demand is reasonable
        base /= sum(c.demand_multiplier for c in CUSTOMERS) / len(CUSTOMERS)

        # Seasonality
        season = SEASON_PROFILES[group_code][d.month - 1]

        # Annual growth trend (2% per year)
        trend = 1.0 + 0.02 * (day_offset / 365.0)

        # Random noise
        noise = random.gauss(1.0, prod.demand_cv * 0.4)

        return max(0.0, base * season * trend * noise)

    def _compute_demand_matrix(
        self, days: int, start_date: date
    ) -> Dict[str, Dict[str, List[float]]]:
        """Pre-compute daily demand: [customer_code][sku][day_offset] = qty.

        Only computes for business days (weekdays). Weekend values are 0.
        """
        matrix: Dict[str, Dict[str, List[float]]] = {}

        for cust in CUSTOMERS:
            matrix[cust.code] = {}
            for sku in _ALL_SKUS:
                daily = []
                for day_off in range(days):
                    d = start_date + timedelta(days=day_off)
                    if d.weekday() >= 5:  # weekend
                        daily.append(0.0)
                    else:
                        daily.append(self._daily_demand(sku, cust, d, day_off))
                matrix[cust.code][sku] = daily

        return matrix

    # ------------------------------------------------------------------
    # Outbound flow: Orders → Fulfillment → Shipments → Backorders
    # ------------------------------------------------------------------

    def _generate_outbound_flow(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> Tuple[List, List, List, List, List]:
        """Generate customer orders and downstream fulfillment records."""
        order_lines: List[OutboundOrderLine] = []
        fulfillments: List[FulfillmentOrder] = []
        shipments: List[Shipment] = []
        shipment_lots: List[ShipmentLot] = []
        backorders: List[Backorder] = []

        for cust in CUSTOMERS:
            cust_region = cust.region
            rdc_name = f"RDC_{cust_region}"
            rdc_id = self.site_ids[rdc_name]
            cust_site_id = self.site_ids[cust.code]
            order_day = CUSTOMER_ORDER_DAY[cust.code]
            is_biweekly = cust.delivery_frequency == "bi-weekly"

            week_counter = 0
            for day_off in range(days):
                d = start_date + timedelta(days=day_off)
                if d.weekday() != order_day:
                    continue

                week_counter += 1
                if is_biweekly and week_counter % 2 != 0:
                    continue

                # Generate order for this customer on this day
                self._order_seq += 1
                order_id = f"OO-{d.strftime('%Y%m%d')}-{cust.code}-{self._order_seq:05d}"
                delivery_date = d + timedelta(days=cust.order_lead_time_days)

                # Pick products — larger customers order more variety
                if cust.size == "large":
                    n_products = random.randint(18, 25)
                elif cust.size == "medium":
                    n_products = random.randint(12, 18)
                else:
                    n_products = random.randint(8, 14)

                selected_skus = random.sample(_ALL_SKUS, min(n_products, len(_ALL_SKUS)))

                # Aggregate demand for order period (5 days for weekly, 10 for bi-weekly)
                order_period = 10 if is_biweekly else 5
                line_num = 0

                # Shipment for this order
                self._sh_seq += 1
                ship_date_dt = datetime.combine(
                    d + timedelta(days=max(1, cust.order_lead_time_days - 1)),
                    datetime.min.time(),
                )
                delivery_dt = datetime.combine(delivery_date, datetime.min.time())
                ship_id = f"SH-OB-{d.strftime('%Y%m%d')}-{self._sh_seq:06d}"
                carrier = random.choice(CARRIERS)

                # Determine if this order has fulfillment issues (~3%)
                has_issue = random.random() < 0.03

                total_ship_qty = 0.0

                for sku in selected_skus:
                    # Sum demand over order period
                    qty = 0.0
                    for dd in range(order_period):
                        idx = day_off + dd
                        if idx < days:
                            qty += demand[cust.code][sku][idx]
                    qty = max(1.0, round(qty))

                    line_num += 1
                    prod = _SKU_TO_PRODUCT[sku]

                    # Fulfillment determination
                    if has_issue and line_num == 1:
                        # First line of problem orders gets partial fill
                        fill_pct = random.uniform(0.3, 0.8)
                        shipped = round(qty * fill_pct)
                        backlog = round(qty - shipped)
                        status = "PARTIALLY_FULFILLED"
                    else:
                        shipped = round(qty)
                        backlog = 0.0
                        status = "FULFILLED"

                    priority = random.choices(
                        ["STANDARD", "HIGH", "VIP"],
                        weights=[0.80, 0.15, 0.05],
                    )[0]

                    ool = OutboundOrderLine(
                        order_id=order_id,
                        line_number=line_num,
                        product_id=self._pid(sku),
                        site_id=rdc_id,
                        ordered_quantity=qty,
                        requested_delivery_date=delivery_date,
                        order_date=d,
                        config_id=self.config_id,
                        promised_quantity=float(shipped),
                        shipped_quantity=float(shipped),
                        backlog_quantity=float(backlog),
                        status=status,
                        priority_code=priority,
                        promised_delivery_date=delivery_date,
                        first_ship_date=ship_date_dt.date(),
                        last_ship_date=delivery_date,
                        market_demand_site_id=cust_site_id,
                    )
                    order_lines.append(ool)
                    total_ship_qty += shipped

                    # Fulfillment order for each line
                    self._fo_seq += 1
                    fo = FulfillmentOrder(
                        company_id=self.company_id,
                        fulfillment_order_id=f"FO-{d.strftime('%Y%m%d')}-{self._fo_seq:06d}",
                        order_id=order_id,
                        order_line_id=str(line_num),
                        site_id=rdc_id,
                        product_id=self._pid(sku),
                        quantity=float(qty),
                        status="DELIVERED" if backlog == 0 else "SHIPPED",
                        created_date=datetime.combine(d, datetime.min.time()),
                        promised_date=delivery_dt,
                        allocated_date=datetime.combine(d, datetime.min.time()),
                        pick_date=ship_date_dt - timedelta(hours=random.randint(2, 8)),
                        pack_date=ship_date_dt - timedelta(hours=random.randint(1, 2)),
                        ship_date=ship_date_dt,
                        delivery_date=delivery_dt if backlog == 0 else None,
                        allocated_quantity=float(shipped),
                        picked_quantity=float(shipped),
                        shipped_quantity=float(shipped),
                        delivered_quantity=float(shipped) if backlog == 0 else 0.0,
                        short_quantity=float(backlog),
                        carrier=carrier[1],
                        tracking_number=f"TRK{self._sh_seq:08d}",
                        ship_method="GROUND",
                        priority={"VIP": 1, "HIGH": 2, "STANDARD": 3}.get(priority, 3),
                        customer_id=cust.code,
                        source="HISTORY_GEN",
                    )
                    fulfillments.append(fo)

                    # Backorder for unfulfilled
                    if backlog > 0:
                        self._bo_seq += 1
                        fill_date = delivery_date + timedelta(days=random.randint(3, 10))
                        bo = Backorder(
                            company_id=self.company_id,
                            backorder_id=f"BO-{d.strftime('%Y%m%d')}-{self._bo_seq:05d}",
                            order_id=order_id,
                            product_id=self._pid(sku),
                            site_id=rdc_id,
                            customer_id=cust.code,
                            backorder_quantity=float(backlog),
                            allocated_quantity=float(backlog),
                            fulfilled_quantity=float(backlog),
                            status="CLOSED",
                            requested_delivery_date=delivery_date,
                            expected_fill_date=fill_date,
                            created_date=datetime.combine(delivery_date, datetime.min.time()),
                            fulfilled_date=datetime.combine(fill_date, datetime.min.time()),
                            closed_date=datetime.combine(fill_date, datetime.min.time()),
                            priority={"VIP": 1, "HIGH": 2, "STANDARD": 3}.get(priority, 3),
                            priority_code=priority,
                            aging_days=(fill_date - delivery_date).days,
                            config_id=self.config_id,
                            source="HISTORY_GEN",
                        )
                        backorders.append(bo)

                # One shipment per customer order (aggregated)
                if total_ship_qty > 0:
                    actual_delivery = delivery_dt
                    # 5% of shipments have slight delay
                    if random.random() < 0.05:
                        delay_hours = random.randint(4, 48)
                        actual_delivery = delivery_dt + timedelta(hours=delay_hours)
                        risk_level = "MEDIUM"
                    else:
                        risk_level = "LOW"

                    sh = Shipment(
                        id=ship_id,
                        company_id=self.company_id,
                        order_id=order_id,
                        product_id=self._pid(selected_skus[0]),  # Primary product
                        quantity=total_ship_qty,
                        from_site_id=rdc_id,
                        to_site_id=cust_site_id,
                        carrier_id=carrier[0],
                        carrier_name=carrier[1],
                        tracking_number=f"TRK{self._sh_seq:08d}",
                        status="delivered",
                        ship_date=ship_date_dt,
                        expected_delivery_date=delivery_dt,
                        actual_delivery_date=actual_delivery,
                        risk_level=risk_level,
                        config_id=self.config_id,
                        tenant_id=self.tenant_id,
                        source="HISTORY_GEN",
                    )
                    shipments.append(sh)

                    # ShipmentLot per product line (food traceability)
                    for sku in selected_skus:
                        prod = _SKU_TO_PRODUCT[sku]
                        # Manufacture date is shelf_life_days before expiry
                        mfg_date = d - timedelta(days=random.randint(3, 30))
                        exp_date = mfg_date + timedelta(days=prod.shelf_life_days)
                        lot_qty = demand[cust.code][sku][day_off] if day_off < days else 1.0
                        if lot_qty <= 0:
                            lot_qty = 1.0

                        sl = ShipmentLot(
                            shipment_id=ship_id,
                            product_id=self._pid(sku),
                            lot_number=f"LOT-{sku}-{mfg_date.strftime('%Y%m%d')}-{random.randint(1, 99):02d}",
                            batch_id=f"B-{sku}-{mfg_date.strftime('%y%m%d')}",
                            quantity=round(lot_qty),
                            manufacture_date=mfg_date,
                            expiration_date=exp_date,
                            shelf_life_days=prod.shelf_life_days,
                            quality_status="RELEASED",
                            origin_site_id=self.site_ids.get(
                                _SKU_TO_SUPPLIER[sku].code, rdc_id
                            ),
                            source="HISTORY_GEN",
                        )
                        shipment_lots.append(sl)

        logger.info(
            f"Outbound flow: {len(order_lines)} order lines, "
            f"{len(fulfillments)} fulfillments, {len(shipments)} shipments, "
            f"{len(shipment_lots)} lots, {len(backorders)} backorders"
        )
        return order_lines, fulfillments, shipments, shipment_lots, backorders

    # ------------------------------------------------------------------
    # Inbound flow: Supplier POs → Receipts → Shipments
    # ------------------------------------------------------------------

    def _generate_inbound_flow(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> Tuple[List, List, List, List]:
        """Generate purchase orders from suppliers to CDC, and transfers CDC→RDC."""
        inbound_orders: List[InboundOrder] = []
        inbound_lines: List[InboundOrderLine] = []
        ib_shipments: List[Shipment] = []
        ib_lots: List[ShipmentLot] = []

        cdc_id = self.site_ids["CDC_WEST"]

        # --- Supplier → CDC purchase orders ---
        # Each supplier orders roughly weekly
        for supplier in SUPPLIERS:
            sup_site_id = self.site_ids.get(supplier.code)
            week_counter = 0

            for day_off in range(0, days, 7):
                d = start_date + timedelta(days=day_off)
                # Jitter order day ±1
                order_date = d + timedelta(days=random.randint(-1, 1))
                if order_date.weekday() >= 5:
                    order_date = d

                self._po_seq += 1
                po_id = f"PO-{order_date.strftime('%Y%m%d')}-{supplier.code}-{self._po_seq:05d}"

                lt = supplier.lead_time_days
                lt_actual = max(1, int(lt * random.gauss(1.0, supplier.lead_time_variability)))
                requested_del = order_date + timedelta(days=lt)
                actual_del = order_date + timedelta(days=lt_actual)

                # Determine if delivered on time
                on_time = actual_del <= requested_del + timedelta(days=1)
                status = "RECEIVED"

                total_qty = 0.0
                total_value = 0.0
                line_records = []

                for line_idx, sku in enumerate(supplier.product_skus, start=1):
                    prod = _SKU_TO_PRODUCT[sku]

                    # Order quantity: ~2 weeks of aggregate demand
                    agg_demand = 0.0
                    for dd in range(14):
                        idx = day_off + dd
                        if idx < days:
                            for cust_code in demand:
                                agg_demand += demand[cust_code][sku][idx]
                    order_qty = max(prod.min_order_qty, round(agg_demand * random.uniform(0.9, 1.1)))

                    # Slight under-delivery occasionally (2%)
                    if random.random() < 0.02:
                        received = round(order_qty * random.uniform(0.85, 0.95))
                    else:
                        received = order_qty

                    mfg_date = order_date - timedelta(days=random.randint(1, 14))
                    lot_num = f"LOT-{sku}-{mfg_date.strftime('%Y%m%d')}-{random.randint(1, 99):02d}"

                    # Use dict for raw SQL insert (DB schema differs from ORM model)
                    ibl = {
                        "order_id": po_id,
                        "line_number": line_idx,
                        "product_id": self._pid(sku),
                        "to_site_id": cdc_id,
                        "from_site_id": sup_site_id,
                        "order_type": "PURCHASE",
                        "quantity_submitted": float(order_qty),
                        "quantity_received": float(received),
                        "expected_delivery_date": requested_del,
                        "order_receive_date": actual_del,
                        "status": "RECEIVED" if received >= order_qty else "PARTIALLY_RECEIVED",
                        "config_id": self.config_id,
                    }
                    line_records.append(ibl)
                    total_qty += order_qty
                    total_value += order_qty * prod.unit_cost

                    # ShipmentLot for inbound
                    exp_date = mfg_date + timedelta(days=prod.shelf_life_days)
                    sl = ShipmentLot(
                        shipment_id=f"SH-IB-{order_date.strftime('%Y%m%d')}-{self._po_seq:06d}",
                        product_id=self._pid(sku),
                        lot_number=lot_num,
                        batch_id=f"B-{sku}-{mfg_date.strftime('%y%m%d')}",
                        quantity=float(received),
                        manufacture_date=mfg_date,
                        expiration_date=exp_date,
                        shelf_life_days=prod.shelf_life_days,
                        quality_status="RELEASED",
                        origin_site_id=sup_site_id,
                        country_of_origin="US",
                        source="HISTORY_GEN",
                    )
                    ib_lots.append(sl)

                ibo = InboundOrder(
                    id=po_id,
                    company_id=self.company_id,
                    order_type="PURCHASE",
                    supplier_id=supplier.code,
                    supplier_name=supplier.name,
                    ship_from_site_id=sup_site_id,
                    ship_to_site_id=cdc_id,
                    status=status,
                    order_date=order_date,
                    requested_delivery_date=requested_del,
                    promised_delivery_date=requested_del,
                    actual_delivery_date=actual_del,
                    total_ordered_qty=total_qty,
                    total_received_qty=sum(l["quantity_received"] for l in line_records),
                    total_value=total_value,
                    currency="USD",
                    config_id=self.config_id,
                    source="HISTORY_GEN",
                )
                inbound_orders.append(ibo)
                inbound_lines.extend(line_records)

                # Inbound shipment
                sh = Shipment(
                    id=f"SH-IB-{order_date.strftime('%Y%m%d')}-{self._po_seq:06d}",
                    company_id=self.company_id,
                    order_id=po_id,
                    product_id=self._pid(supplier.product_skus[0]),
                    quantity=total_qty,
                    from_site_id=sup_site_id if sup_site_id else cdc_id,
                    to_site_id=cdc_id,
                    carrier_id=random.choice(CARRIERS)[0],
                    carrier_name=random.choice(CARRIERS)[1],
                    status="delivered",
                    ship_date=datetime.combine(
                        order_date + timedelta(days=1), datetime.min.time()
                    ),
                    expected_delivery_date=datetime.combine(
                        requested_del, datetime.min.time()
                    ),
                    actual_delivery_date=datetime.combine(
                        actual_del, datetime.min.time()
                    ),
                    risk_level="LOW" if on_time else "MEDIUM",
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    source="HISTORY_GEN",
                )
                ib_shipments.append(sh)

        # --- CDC → RDC transfer orders (weekly) ---
        for rdc_def in RDCS:
            rdc_id = self.site_ids[rdc_def.code]
            for day_off in range(0, days, 7):
                d = start_date + timedelta(days=day_off)
                # Transfers happen mid-week (Wednesday)
                transfer_date = d + timedelta(days=(2 - d.weekday()) % 7)
                if (transfer_date - start_date).days >= days:
                    continue

                self._po_seq += 1
                to_id = f"TO-{transfer_date.strftime('%Y%m%d')}-{rdc_def.code}-{self._po_seq:05d}"

                total_qty = 0.0
                to_lines = []

                for sku in _ALL_SKUS:
                    # Transfer qty: ~1 week of demand for this RDC's customers
                    wk_demand = 0.0
                    for cust in CUSTOMERS:
                        if cust.region != rdc_def.region:
                            continue
                        for dd in range(7):
                            idx = day_off + dd
                            if idx < days:
                                wk_demand += demand[cust.code][sku][idx]
                    if wk_demand < 1:
                        continue

                    transfer_qty = max(1, round(wk_demand * random.uniform(1.0, 1.2)))

                    ibl = {
                        "order_id": to_id,
                        "line_number": len(to_lines) + 1,
                        "product_id": self._pid(sku),
                        "to_site_id": rdc_id,
                        "from_site_id": cdc_id,
                        "order_type": "TRANSFER",
                        "quantity_submitted": float(transfer_qty),
                        "quantity_received": float(transfer_qty),
                        "expected_delivery_date": transfer_date + timedelta(days=1),
                        "order_receive_date": transfer_date + timedelta(days=1),
                        "status": "RECEIVED",
                        "config_id": self.config_id,
                    }
                    to_lines.append(ibl)
                    total_qty += transfer_qty

                if not to_lines:
                    continue

                ibo = InboundOrder(
                    id=to_id,
                    company_id=self.company_id,
                    order_type="TRANSFER",
                    ship_from_site_id=cdc_id,
                    ship_to_site_id=rdc_id,
                    status="RECEIVED",
                    order_date=transfer_date,
                    requested_delivery_date=transfer_date + timedelta(days=1),
                    actual_delivery_date=transfer_date + timedelta(days=1),
                    total_ordered_qty=total_qty,
                    total_received_qty=total_qty,
                    config_id=self.config_id,
                    source="HISTORY_GEN",
                )
                inbound_orders.append(ibo)
                inbound_lines.extend(to_lines)

                # Transfer shipment
                self._sh_seq += 1
                sh = Shipment(
                    id=f"SH-TR-{transfer_date.strftime('%Y%m%d')}-{self._sh_seq:06d}",
                    company_id=self.company_id,
                    order_id=to_id,
                    product_id=self._pid(_ALL_SKUS[0]),
                    quantity=total_qty,
                    from_site_id=cdc_id,
                    to_site_id=rdc_id,
                    status="delivered",
                    ship_date=datetime.combine(transfer_date, datetime.min.time()),
                    expected_delivery_date=datetime.combine(
                        transfer_date + timedelta(days=1), datetime.min.time()
                    ),
                    actual_delivery_date=datetime.combine(
                        transfer_date + timedelta(days=1), datetime.min.time()
                    ),
                    risk_level="LOW",
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    source="HISTORY_GEN",
                )
                ib_shipments.append(sh)

        logger.info(
            f"Inbound flow: {len(inbound_orders)} orders, "
            f"{len(inbound_lines)} lines, {len(ib_shipments)} shipments, "
            f"{len(ib_lots)} lots"
        )
        return inbound_orders, inbound_lines, ib_shipments, ib_lots

    # ------------------------------------------------------------------
    # Inventory levels (daily snapshots)
    # ------------------------------------------------------------------

    def _generate_inventory_levels(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> List[InvLevel]:
        """Generate daily InvLevel snapshots for 3 internal sites × 25 products."""
        records: List[InvLevel] = []
        internal_sites = ["CDC_WEST", "RDC_NW", "RDC_SW"]

        for site_name in internal_sites:
            site_id = self.site_ids[site_name]

            for sku in _ALL_SKUS:
                prod = _SKU_TO_PRODUCT[sku]

                # Initial inventory: ~3 weeks of average daily demand
                avg_daily = prod.weekly_demand_mean / 5.0
                on_hand = avg_daily * 15 * random.uniform(0.8, 1.2)
                safety_stock = avg_daily * 7  # 1 week safety stock

                for day_off in range(days):
                    d = start_date + timedelta(days=day_off)

                    # Demand for this site
                    if site_name == "CDC_WEST":
                        # CDC aggregate demand = sum of both RDC replenishment
                        daily_demand = sum(
                            demand[c.code][sku][day_off] for c in CUSTOMERS
                        ) * 0.15  # CDC holds ~15% of total flow as buffer
                    elif site_name == "RDC_NW":
                        daily_demand = sum(
                            demand[c.code][sku][day_off]
                            for c in CUSTOMERS if c.region == "NW"
                        )
                    else:  # RDC_SW
                        daily_demand = sum(
                            demand[c.code][sku][day_off]
                            for c in CUSTOMERS if c.region == "SW"
                        )

                    # Simple inventory model: deplete and replenish
                    on_hand -= daily_demand
                    backorder = 0.0

                    # Replenishment when on_hand drops below safety stock
                    if on_hand < safety_stock:
                        replen = avg_daily * 14 * random.uniform(0.9, 1.1)
                        on_hand += replen

                    if on_hand < 0:
                        backorder = abs(on_hand)
                        on_hand = 0.0

                    # In-transit and on-order based on pipeline
                    in_transit = avg_daily * random.uniform(2, 5)
                    on_order = avg_daily * random.uniform(5, 10)
                    allocated = daily_demand * random.uniform(0.8, 1.0)
                    available = max(0, on_hand - allocated)

                    inv = InvLevel(
                        company_id=self.company_id,
                        product_id=self._pid(sku),
                        site_id=site_id,
                        inventory_date=d,
                        on_hand_qty=round(max(0, on_hand), 1),
                        in_transit_qty=round(in_transit, 1),
                        on_order_qty=round(on_order, 1),
                        allocated_qty=round(allocated, 1),
                        available_qty=round(available, 1),
                        backorder_qty=round(backorder, 1),
                        safety_stock_qty=round(safety_stock, 1),
                        config_id=self.config_id,
                        source="HISTORY_GEN",
                    )
                    records.append(inv)

        logger.info(f"Inventory levels: {len(records)} records")
        return records

    # ------------------------------------------------------------------
    # Forecasts (daily P10/P50/P90)
    # ------------------------------------------------------------------

    def _generate_forecasts(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> List[Forecast]:
        """Generate daily forecast records per product × site (3 internal sites)."""
        records: List[Forecast] = []

        for site_name, region_filter in [
            ("CDC_WEST", None),
            ("RDC_NW", "NW"),
            ("RDC_SW", "SW"),
        ]:
            site_id = self.site_ids[site_name]

            for sku in _ALL_SKUS:
                prod = _SKU_TO_PRODUCT[sku]

                for day_off in range(days):
                    d = start_date + timedelta(days=day_off)
                    if d.weekday() >= 5:
                        continue  # No forecasts on weekends

                    # Actual demand aggregated for this site
                    if region_filter is None:
                        actual = sum(demand[c.code][sku][day_off] for c in CUSTOMERS)
                    else:
                        actual = sum(
                            demand[c.code][sku][day_off]
                            for c in CUSTOMERS if c.region == region_filter
                        )

                    if actual <= 0:
                        continue

                    # Forecast = actual with bias and noise
                    # Older history has worse forecast accuracy
                    days_ago = days - day_off
                    accuracy_factor = 1.0 - (days_ago / days) * 0.1  # 0.9-1.0
                    bias = random.gauss(0.02, 0.05)  # Slight positive bias
                    noise_std = prod.demand_cv * 0.3 / accuracy_factor

                    p50 = actual * (1.0 + bias + random.gauss(0, noise_std))
                    p50 = max(0.0, p50)
                    p10 = p50 * random.uniform(0.70, 0.85)
                    p90 = p50 * random.uniform(1.15, 1.35)
                    std_dev = (p90 - p10) / 2.56  # ~80% interval

                    # Forecast error (computed vs actual)
                    error = (p50 - actual) / actual if actual > 0 else 0.0

                    fc = Forecast(
                        company_id=self.company_id,
                        product_id=self._pid(sku),
                        site_id=site_id,
                        forecast_date=d,
                        forecast_type="statistical",
                        forecast_level="product",
                        forecast_method="exponential_smoothing",
                        forecast_quantity=round(p50, 1),
                        forecast_p10=round(p10, 1),
                        forecast_p50=round(p50, 1),
                        forecast_median=round(p50, 1),
                        forecast_p90=round(p90, 1),
                        forecast_std_dev=round(std_dev, 2),
                        forecast_confidence=round(accuracy_factor, 3),
                        forecast_error=round(error, 4),
                        forecast_bias=round(bias, 4),
                        is_active="Y",
                        config_id=self.config_id,
                        source="HISTORY_GEN",
                    )
                    records.append(fc)

        logger.info(f"Forecasts: {len(records)} records")
        return records

    # ------------------------------------------------------------------
    # Consensus Demand (monthly S&OP)
    # ------------------------------------------------------------------

    def _generate_consensus_demand(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> List[ConsensusDemand]:
        """Generate monthly consensus demand records."""
        records: List[ConsensusDemand] = []

        # Iterate month by month
        current = date(start_date.year, start_date.month, 1)
        end = start_date + timedelta(days=days)

        while current < end:
            # Month boundaries
            if current.month == 12:
                next_month = date(current.year + 1, 1, 1)
            else:
                next_month = date(current.year, current.month + 1, 1)
            period_end = next_month - timedelta(days=1)

            for site_name, region_filter in [
                ("CDC_WEST", None),
                ("RDC_NW", "NW"),
                ("RDC_SW", "SW"),
            ]:
                site_id = self.site_ids[site_name]

                for sku in _ALL_SKUS:
                    # Aggregate actual demand for the month
                    monthly_actual = 0.0
                    for day_off in range(days):
                        d = start_date + timedelta(days=day_off)
                        if d < current or d >= next_month:
                            continue
                        if region_filter is None:
                            monthly_actual += sum(
                                demand[c.code][sku][day_off] for c in CUSTOMERS
                            )
                        else:
                            monthly_actual += sum(
                                demand[c.code][sku][day_off]
                                for c in CUSTOMERS if c.region == region_filter
                            )

                    if monthly_actual <= 0:
                        continue

                    stat_fcst = monthly_actual * random.uniform(0.92, 1.08)
                    sales_fcst = monthly_actual * random.uniform(0.95, 1.10)
                    mkt_fcst = monthly_actual * random.uniform(0.90, 1.05)
                    consensus = (stat_fcst * 0.4 + sales_fcst * 0.4 + mkt_fcst * 0.2)

                    cd = ConsensusDemand(
                        company_id=self.company_id,
                        product_id=self._pid(sku),
                        site_id=site_id,
                        period_start=current,
                        period_end=period_end,
                        period_type="MONTHLY",
                        statistical_forecast=round(stat_fcst, 1),
                        sales_forecast=round(sales_fcst, 1),
                        marketing_forecast=round(mkt_fcst, 1),
                        consensus_quantity=round(consensus, 1),
                        confidence_level=random.uniform(0.70, 0.95),
                        consensus_p10=round(consensus * 0.80, 1),
                        consensus_p50=round(consensus, 1),
                        consensus_p90=round(consensus * 1.25, 1),
                        adjustment_type="SEASON" if current.month in (6, 7, 8, 11, 12) else None,
                        sop_cycle_id=f"SOP-{current.strftime('%Y-%m')}",
                        version=1,
                        source="HISTORY_GEN",
                    )
                    records.append(cd)

            current = next_month

        logger.info(f"Consensus demand: {len(records)} records")
        return records

    # ------------------------------------------------------------------
    # Supplementary Time Series (external signals)
    # ------------------------------------------------------------------

    def _generate_supplementary_signals(
        self, days: int, start_date: date
    ) -> List[SupplementaryTimeSeries]:
        """Generate sparse external demand signals (promotions, weather, market)."""
        records: List[SupplementaryTimeSeries] = []

        signal_types = [
            ("PROMOTION", "Promotional Event", 0.03),
            ("WEATHER", "Weather Impact", 0.02),
            ("MARKET_INDEX", "Market Price Index", 0.01),
            ("ECONOMIC_INDICATOR", "Economic Indicator", 0.005),
        ]

        for day_off in range(days):
            d = start_date + timedelta(days=day_off)
            if d.weekday() >= 5:
                continue

            for series_type, series_name, prob in signal_types:
                if random.random() > prob:
                    continue

                # Pick a random product and site
                sku = random.choice(_ALL_SKUS)
                site_name = random.choice(["RDC_NW", "RDC_SW"])
                site_id = self.site_ids[site_name]

                direction = random.choice(["UP", "DOWN", "NEUTRAL"])
                magnitude = random.uniform(0.05, 0.30) if direction != "NEUTRAL" else 0.0

                if series_type == "MARKET_INDEX":
                    value = random.uniform(90.0, 130.0)
                    unit = "index"
                elif series_type == "WEATHER":
                    value = random.uniform(-15.0, 115.0)
                    unit = "fahrenheit"
                elif series_type == "PROMOTION":
                    value = random.uniform(10.0, 40.0)
                    unit = "pct_discount"
                else:
                    value = random.uniform(0.5, 3.0)
                    unit = "index"

                ts = SupplementaryTimeSeries(
                    company_id=self.company_id,
                    series_name=f"{series_name} - {sku}",
                    series_type=series_type,
                    product_id=self._pid(sku),
                    site_id=site_id,
                    observation_date=d,
                    value=round(value, 2),
                    unit=unit,
                    confidence=random.uniform(0.5, 0.95),
                    source_channel="market_feed" if series_type == "MARKET_INDEX" else "internal",
                    signal_direction=direction,
                    magnitude=round(magnitude, 3),
                    is_processed=True,
                    processed_at=datetime.combine(d, datetime.min.time()),
                    forecast_impact=round(magnitude * random.uniform(0.5, 1.0), 3) if magnitude > 0 else None,
                    source="HISTORY_GEN",
                )
                records.append(ts)

        logger.info(f"Supplementary signals: {len(records)} records")
        return records

    # ------------------------------------------------------------------
    # Inventory Projections (weekly ATP/CTP)
    # ------------------------------------------------------------------

    def _generate_inventory_projections(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> List[InventoryProjection]:
        """Generate weekly inventory projections per product × site."""
        records: List[InventoryProjection] = []

        for site_name, region_filter in [
            ("CDC_WEST", None),
            ("RDC_NW", "NW"),
            ("RDC_SW", "SW"),
        ]:
            site_id = self.site_ids[site_name]

            for sku in _ALL_SKUS:
                prod = _SKU_TO_PRODUCT[sku]
                avg_daily = prod.weekly_demand_mean / 5.0
                safety = avg_daily * 7
                on_hand = avg_daily * 15

                for week_start_off in range(0, days, 7):
                    week_start = start_date + timedelta(days=week_start_off)
                    week_end = week_start + timedelta(days=6)

                    # Gross requirements (week of demand)
                    gross_req = 0.0
                    for dd in range(7):
                        idx = week_start_off + dd
                        if idx >= days:
                            break
                        if region_filter is None:
                            gross_req += sum(
                                demand[c.code][sku][idx] for c in CUSTOMERS
                            )
                        else:
                            gross_req += sum(
                                demand[c.code][sku][idx]
                                for c in CUSTOMERS if c.region == region_filter
                            )

                    # Simple netting
                    boh = on_hand
                    sched_receipts = avg_daily * 5 * random.uniform(0.8, 1.2)
                    planned_receipts = max(0, gross_req - on_hand + safety) if on_hand < safety * 1.5 else 0
                    poh = boh + sched_receipts + planned_receipts - gross_req
                    poh = max(0, poh)
                    atp = max(0, poh - safety)

                    # Update running on_hand
                    on_hand = poh

                    ip = InventoryProjection(
                        company_id=self.company_id,
                        site_id=site_id,
                        product_id=self._pid(sku),
                        period_start=week_start,
                        period_end=week_end,
                        period_type="WEEKLY",
                        beginning_on_hand=round(boh, 1),
                        gross_requirements=round(gross_req, 1),
                        scheduled_receipts=round(sched_receipts, 1),
                        planned_receipts=round(planned_receipts, 1),
                        projected_on_hand=round(poh, 1),
                        atp_quantity=round(atp, 1),
                        cumulative_atp=round(atp, 1),
                        safety_stock=round(safety, 1),
                        projected_available=round(max(0, poh - safety), 1),
                        projected_on_hand_p10=round(poh * 0.75, 1),
                        projected_on_hand_p50=round(poh, 1),
                        projected_on_hand_p90=round(poh * 1.30, 1),
                        atp_p10=round(atp * 0.70, 1),
                        atp_p90=round(atp * 1.35, 1),
                        source="HISTORY_GEN",
                    )
                    records.append(ip)

        logger.info(f"Inventory projections: {len(records)} records")
        return records

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def _batch_insert_inbound_lines(self, lines: List[dict]):
        """Insert inbound_order_line records via raw SQL (DB schema mismatch with ORM)."""
        if not lines:
            return
        insert_sql = text("""
            INSERT INTO inbound_order_line
                (order_id, line_number, product_id, to_site_id, from_site_id,
                 order_type, quantity_submitted, quantity_received,
                 expected_delivery_date, order_receive_date, status, config_id)
            VALUES
                (:order_id, :line_number, :product_id, :to_site_id, :from_site_id,
                 :order_type, :quantity_submitted, :quantity_received,
                 :expected_delivery_date, :order_receive_date, :status, :config_id)
        """)
        for i in range(0, len(lines), 500):
            batch = lines[i:i + 500]
            await self.db.execute(insert_sql, batch)
            await self.db.flush()

    async def generate_history(
        self,
        days: int = 730,
        start_date: Optional[date] = None,
        seed: int = 42,
    ) -> Dict[str, int]:
        """
        Generate complete 2-year transactional history.

        Args:
            days: Number of days of history (default 730 = 2 years)
            start_date: Start date for history (default: today - days)
            seed: Random seed for reproducibility

        Returns:
            Dict with record counts per entity type
        """
        random.seed(seed)

        if start_date is None:
            start_date = date.today() - timedelta(days=days)

        end_date = start_date + timedelta(days=days - 1)
        logger.info(
            f"Generating {days}-day history from {start_date} to {end_date} "
            f"for config {self.config_id}"
        )

        # 1. Load network topology
        await self._load_network()

        # 2. Pre-compute demand matrix
        logger.info("Computing demand matrix...")
        demand = self._compute_demand_matrix(days, start_date)

        # 3. Generate all entity records
        counts: Dict[str, int] = {}

        # Outbound flow
        logger.info("Generating outbound flow...")
        ool, fo, ob_sh, ob_lots, bo = self._generate_outbound_flow(demand, days, start_date)
        counts["outbound_order_lines"] = len(ool)
        counts["fulfillment_orders"] = len(fo)
        counts["outbound_shipments"] = len(ob_sh)
        counts["outbound_shipment_lots"] = len(ob_lots)
        counts["backorders"] = len(bo)

        # Inbound flow
        logger.info("Generating inbound flow...")
        ibo, ibl, ib_sh, ib_lots = self._generate_inbound_flow(demand, days, start_date)
        counts["inbound_orders"] = len(ibo)
        counts["inbound_order_lines"] = len(ibl)
        counts["inbound_shipments"] = len(ib_sh)
        counts["inbound_shipment_lots"] = len(ib_lots)

        # Inventory levels
        logger.info("Generating inventory levels...")
        inv = self._generate_inventory_levels(demand, days, start_date)
        counts["inv_levels"] = len(inv)

        # Forecasts
        logger.info("Generating forecasts...")
        fcst = self._generate_forecasts(demand, days, start_date)
        counts["forecasts"] = len(fcst)

        # Consensus demand
        logger.info("Generating consensus demand...")
        cd = self._generate_consensus_demand(demand, days, start_date)
        counts["consensus_demand"] = len(cd)

        # Supplementary signals
        logger.info("Generating supplementary signals...")
        sts = self._generate_supplementary_signals(days, start_date)
        counts["supplementary_signals"] = len(sts)

        # Inventory projections
        logger.info("Generating inventory projections...")
        ip = self._generate_inventory_projections(demand, days, start_date)
        counts["inventory_projections"] = len(ip)

        # 4. Bulk insert all records in order (respecting FK constraints)
        logger.info("Bulk inserting records...")

        # Inbound orders first (PK referenced by lines)
        await _batch_add(self.db, ibo, batch_size=500)

        # Inbound order lines (raw SQL — DB schema differs from ORM model)
        await self._batch_insert_inbound_lines(ibl)

        # Outbound order lines (no FK dependencies beyond product/site)
        await _batch_add(self.db, ool, batch_size=2000)

        # Shipments (before shipment lots)
        all_shipments = ob_sh + ib_sh
        await _batch_add(self.db, all_shipments, batch_size=1000)

        # Shipment lots
        all_lots = ob_lots + ib_lots
        await _batch_add(self.db, all_lots, batch_size=2000)

        # Fulfillment orders
        await _batch_add(self.db, fo, batch_size=2000)

        # Backorders
        await _batch_add(self.db, bo, batch_size=500)

        # Inventory levels
        await _batch_add(self.db, inv, batch_size=5000)

        # Forecasts
        await _batch_add(self.db, fcst, batch_size=5000)

        # Consensus demand
        await _batch_add(self.db, cd, batch_size=1000)

        # Supplementary signals
        await _batch_add(self.db, sts, batch_size=500)

        # Inventory projections
        await _batch_add(self.db, ip, batch_size=5000)

        # Final commit
        await self.db.commit()

        total = sum(counts.values())
        counts["total"] = total

        logger.info(f"History generation complete: {total:,} total records")
        for entity, count in sorted(counts.items()):
            if entity != "total":
                logger.info(f"  {entity}: {count:,}")

        return counts
