"""
Food Distribution 3-Year History Generator

Generates 3 years of daily transactional history for the Food Dist config
across 16 AWS SC data model entity types:

Existing (10):
1. OutboundOrder — customer order headers (parent for order lines)
2. OutboundOrderLine — customer demand order lines (with cancellations)
3. InboundOrder / InboundOrderLine — supplier purchase orders
4. Shipment + ShipmentLot — material movement with food lot traceability
5. Forecast — daily P10/P50/P90 demand forecasts
6. InvLevel — daily inventory snapshots per site×product
7. FulfillmentOrder — warehouse pick/pack/ship execution
8. ConsensusDemand — monthly S&OP consensus records
9. SupplementaryTimeSeries — external demand signals (promo-correlated)
10. InventoryProjection — weekly ATP/CTP projections
11. Backorder — unfulfilled demand tracking

New Tier 1 (4):
12. PurchaseOrder + PurchaseOrderLineItem — typed PO records (FK base for GR)
13. GoodsReceipt + GoodsReceiptLineItem — supplier quality-at-receipt with inspection
14. QualityOrder + QualityOrderLineItem — incoming inspection with characteristic checks
15. InboundOrderLineSchedule — split delivery schedules with promised vs actual dates

New Tier 2 (3):
16. TransferOrder + TransferOrderLineItem �� inter-DC transfers with damage tracking
17. MaintenanceOrder — cold chain equipment preventive/corrective/emergency maintenance
18. ProductionOrder — CDC repackaging/cross-docking operations (case breakdown, relabeling)

Demand model enhancements:
- Holiday spikes (Thanksgiving, July 4th, Super Bowl, Christmas, etc.)
- Customer churn (2 accounts lost, 1 gained over 2-year horizon)
- Promotional demand lifts correlated with SupplementaryTimeSeries signals
- Log-normal noise (right-skewed instead of symmetric Gaussian)
- Basket correlations between product pairs
- Order cancellations (~1.5% rate)
- Day-of-week demand variation

Lead time enhancements:
- Log-normal distribution (right-skewed, fat tails)
- Q4 seasonal freight slowdown (Oct-Dec)
- Supplier outlier delays (3% extreme events)

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

from app.models.supply_chain_config import Site
from app.models.sc_entities import (
    OutboundOrder, OutboundOrderLine, InboundOrder,
    Shipment, ShipmentLot, Forecast, InvLevel,
    FulfillmentOrder, ConsensusDemand, SupplementaryTimeSeries,
    InventoryProjection, Backorder, InboundOrderLineSchedule,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.goods_receipt import GoodsReceipt, GoodsReceiptLineItem
from app.models.quality_order import QualityOrder, QualityOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.maintenance_order import MaintenanceOrder
from app.models.production_order import ProductionOrder
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
# Holiday / Event Calendar
# (month, day), affected product groups, demand multiplier, lead-in window days
# ============================================================================

HOLIDAY_SPIKES = [
    # Thanksgiving — frozen proteins, dairy, desserts, pantry surge
    ((11, 22), ["FRZ_PROTEIN", "REF_DAIRY", "DRY_PANTRY", "FRZ_DESSERT"], 1.45, 14),
    # July 4th — grilling + beverages
    ((7, 4), ["FRZ_PROTEIN", "BEV", "FRZ_DESSERT"], 1.35, 10),
    # Super Bowl — snack proteins, beverages, desserts
    ((2, 9), ["FRZ_PROTEIN", "BEV", "FRZ_DESSERT", "REF_DAIRY"], 1.30, 7),
    # Back-to-school — pantry, dairy, beverages
    ((8, 20), ["DRY_PANTRY", "REF_DAIRY", "BEV"], 1.25, 14),
    # Christmas — all categories
    ((12, 25), ["FRZ_PROTEIN", "REF_DAIRY", "DRY_PANTRY", "FRZ_DESSERT", "BEV"], 1.40, 14),
    # Memorial Day — grilling + beverages
    ((5, 27), ["FRZ_PROTEIN", "BEV"], 1.25, 7),
    # Easter — dairy, desserts, proteins
    ((4, 13), ["REF_DAIRY", "FRZ_DESSERT", "FRZ_PROTEIN"], 1.20, 10),
    # Labor Day — grilling + beverages
    ((9, 1), ["FRZ_PROTEIN", "BEV", "FRZ_DESSERT"], 1.20, 7),
]

# ============================================================================
# Customer Churn Events (day_offset thresholds over 730-day horizon)
# ============================================================================

# Gained customer: Reno Fresh Markets joins at month 10 (~day 300)
CUST_RNO = CustomerDefinition(
    code="CUST_RNO", name="Reno Fresh Markets", segment="Natural/Specialty Retail",
    size="small", delivery_frequency="weekly", order_lead_time_days=3,
    credit_limit=22000.00, avg_order_value=3800.00, demand_multiplier=0.75,
    latitude=39.5296, longitude=-119.8138, city="Reno", state="NV", region="NW",
)

# (day_offset_threshold, customer_code, "LOST" or "GAINED")
CUSTOMER_CHURN_EVENTS = [
    (240, "CUST_SAL", "LOST"),    # Small Salem customer lost at month 8
    (425, "CUST_TUS", "LOST"),    # Small Tucson customer lost at month 14
    (300, "CUST_RNO", "GAINED"),  # Reno gained at month 10
]

CUSTOMER_ORDER_DAY_EXTENDED = {
    "CUST_RNO": 3,  # Thursday orders for gained customer
}

# ============================================================================
# Basket Correlations (product pairs that co-occur in orders)
# ============================================================================

BASKET_PAIRS = [
    ("FP001", "RD001", 0.6),   # Chicken + cheddar (combo platters)
    ("FP002", "RD002", 0.5),   # Beef patties + mozzarella (burgers + pizza)
    ("DP001", "RD003", 0.4),   # Pasta + cream cheese (Italian dishes)
    ("FD001", "FD003", 0.7),   # Ice cream + gelato (dessert basket)
    ("BV001", "BV003", 0.5),   # OJ + lemonade (beverage basket)
    ("FP001", "BV004", 0.3),   # Chicken + iced tea (meal combo)
    ("DP003", "DP004", 0.6),   # Flour + sugar (baking basket)
    ("FP003", "DP002", 0.35),  # Pork chops + rice (meal pairing)
    ("FP006", "FP001", 0.25),  # Wagyu + chicken (premium protein upsell)
]

# ============================================================================
# New Product Introductions (NPI)
# SKU → (launch_day_offset_from_end, ramp_up_days)
# launch_day_offset_from_end: how many days before the end of the history
# ramp_up_days: how many days to ramp from 0% to 100% of base demand
# ============================================================================

NPI_PRODUCTS = {
    "FP006": {
        "launch_days_before_end": 21,   # Launched 3 weeks before end of history
        "ramp_up_days": 14,             # 2-week ramp to steady-state demand
        "initial_stocking_multiplier": 2.5,  # Initial orders 2.5x normal for pipeline fill
    },
}

# ============================================================================
# Cold Chain Equipment (for maintenance order generation)
# ============================================================================

COLD_CHAIN_EQUIPMENT = [
    ("EQ-CDC-FRZ-01", "Walk-in Freezer Unit A", "WALK_IN_FREEZER", "CDC_WEST", 90),
    ("EQ-CDC-FRZ-02", "Walk-in Freezer Unit B", "WALK_IN_FREEZER", "CDC_WEST", 90),
    ("EQ-CDC-REF-01", "Refrigeration Compressor A", "COMPRESSOR", "CDC_WEST", 60),
    ("EQ-CDC-REF-02", "Refrigeration Compressor B", "COMPRESSOR", "CDC_WEST", 60),
    ("EQ-CDC-DOC-01", "Dock Leveler Station 1-4", "DOCK_EQUIPMENT", "CDC_WEST", 120),
    ("EQ-CDC-CON-01", "Conveyor System Main", "CONVEYOR", "CDC_WEST", 45),
    ("EQ-NW-FRZ-01", "Walk-in Freezer NW", "WALK_IN_FREEZER", "RDC_NW", 90),
    ("EQ-NW-REF-01", "Refrigeration Compressor NW", "COMPRESSOR", "RDC_NW", 60),
    ("EQ-SW-FRZ-01", "Walk-in Freezer SW", "WALK_IN_FREEZER", "RDC_SW", 90),
    ("EQ-SW-REF-01", "Refrigeration Compressor SW", "COMPRESSOR", "RDC_SW", 60),
]

# Maintenance work description templates per equipment type
_MAINT_WORK_DESC = {
    "WALK_IN_FREEZER": {
        "PREVENTIVE": "Scheduled PM: Inspect evaporator coils, check door seals, verify temperature calibration, clean condenser",
        "CORRECTIVE": "Corrective: Repair — temperature excursion detected, compressor cycling abnormally",
        "EMERGENCY": "Emergency: Freezer temperature rising, product at risk — immediate compressor diagnosis",
    },
    "COMPRESSOR": {
        "PREVENTIVE": "Scheduled PM: Check refrigerant levels, inspect belt tension, clean air filters, verify pressure readings",
        "CORRECTIVE": "Corrective: Unusual noise/vibration detected — bearing inspection and refrigerant leak check",
        "EMERGENCY": "Emergency: Compressor failure — immediate replacement of failed component to restore cold chain",
    },
    "DOCK_EQUIPMENT": {
        "PREVENTIVE": "Scheduled PM: Lubricate hydraulics, inspect dock leveler plates, test safety interlock mechanisms",
        "CORRECTIVE": "Corrective: Dock leveler not leveling properly — hydraulic cylinder inspection",
        "EMERGENCY": "Emergency: Dock leveler stuck in raised position — hydraulic line failure",
    },
    "CONVEYOR": {
        "PREVENTIVE": "Scheduled PM: Inspect belt tracking, lubricate bearings, check motor amperage, clean sensors",
        "CORRECTIVE": "Corrective: Belt misalignment causing product jams — re-tension and realign rollers",
        "EMERGENCY": "Emergency: Conveyor motor failure — production line stopped, immediate motor replacement",
    },
}

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
    """Generates 3 years of daily transactional history for Food Dist."""

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
        self._gr_seq = 0
        self._qo_seq = 0
        self._to_transfer_seq = 0
        self._mo_seq = 0
        self._prod_order_seq = 0

        # Cross-method data for FK linkage
        self._po_records: List[PurchaseOrder] = []
        self._po_line_records: List[PurchaseOrderLineItem] = []
        # Promotion events: (day_offset, sku) → lift_factor
        self._promotion_events: Dict[Tuple[int, str], float] = {}
        # All customers including churn-gained ones
        self._all_customers: List[CustomerDefinition] = list(CUSTOMERS) + [CUST_RNO]
        # Total days of history (set in generate_history, used by NPI gate)
        self._total_days: int = 730

    # ------------------------------------------------------------------
    # Network loading
    # ------------------------------------------------------------------

    async def _load_network(self):
        """Load node IDs and product IDs from DB for this config."""
        result = await self.db.execute(
            select(Site).where(Site.config_id == self.config_id)
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
    # Demand model (enhanced with holiday spikes, promos, log-normal noise,
    # customer churn, basket correlations)
    # ------------------------------------------------------------------

    def _pre_generate_promotion_events(self, days: int, start_date: date):
        """Pre-generate promotion events so demand lifts correlate with signals."""
        for day_off in range(days):
            d = start_date + timedelta(days=day_off)
            if d.weekday() >= 5:
                continue
            if random.random() < 0.03:
                sku = random.choice(_ALL_SKUS)
                lift = random.uniform(0.15, 0.40)
                duration = random.randint(5, 10)
                for dd in range(duration):
                    idx = day_off + dd
                    if idx < days:
                        existing = self._promotion_events.get((idx, sku), 0.0)
                        self._promotion_events[(idx, sku)] = max(existing, lift)

    def _daily_demand(
        self, sku: str, customer: CustomerDefinition, d: date, day_offset: int
    ) -> float:
        """Compute expected daily demand for one product×customer.

        Enhanced with: NPI ramp-up, holiday spikes, promotional lifts, log-normal noise.
        """
        # NPI gate: zero demand before launch, ramp-up curve after
        npi = NPI_PRODUCTS.get(sku)
        if npi:
            launch_offset = self._total_days - npi["launch_days_before_end"]
            if day_offset < launch_offset:
                return 0.0
            days_since_launch = day_offset - launch_offset
            ramp_days = npi["ramp_up_days"]
            if days_since_launch < ramp_days:
                # S-curve ramp: slow start, accelerate, flatten
                t = days_since_launch / ramp_days  # 0.0 → 1.0
                ramp_pct = 3 * t * t - 2 * t * t * t  # Smoothstep
            else:
                ramp_pct = 1.0
            # Initial stocking multiplier decays over ramp period
            stocking_mult = 1.0 + (npi["initial_stocking_multiplier"] - 1.0) * max(0, 1.0 - days_since_launch / ramp_days)
        else:
            ramp_pct = 1.0
            stocking_mult = 1.0

        prod = _SKU_TO_PRODUCT[sku]
        group_code = _SKU_TO_GROUP[sku]

        # Base daily demand (weekly mean / 5 business days, scaled by customer)
        base = (prod.weekly_demand_mean / 5.0) * customer.demand_multiplier

        # Normalize across all customers so total demand is reasonable
        avg_mult = sum(c.demand_multiplier for c in self._all_customers) / len(self._all_customers)
        base /= avg_mult

        # Day-of-week weighting
        dow = d.weekday()
        if 0 <= dow <= 4:
            base *= DOW_WEIGHTS[dow]

        # Seasonality
        season = SEASON_PROFILES[group_code][d.month - 1]

        # Annual growth trend (2% per year)
        trend = 1.0 + 0.02 * (day_offset / 365.0)

        # Holiday spikes — ramp up in the lead-in window before each holiday
        holiday_mult = 1.0
        for (h_month, h_day), affected_groups, spike_mult, window in HOLIDAY_SPIKES:
            if group_code not in affected_groups:
                continue
            event_date = date(d.year, h_month, min(h_day, 28))
            days_before = (event_date - d).days
            if 0 <= days_before <= window:
                ramp = 1.0 - (days_before / window) * 0.5
                holiday_mult = max(holiday_mult, 1.0 + (spike_mult - 1.0) * ramp)

        # Promotional demand lift (correlated with SupplementaryTimeSeries signals)
        promo_lift = self._promotion_events.get((day_offset, sku), 0.0)
        promo_mult = 1.0 + promo_lift

        # Log-normal noise (right-skewed instead of symmetric Gaussian)
        # NPI products get higher noise during ramp (more demand uncertainty)
        noise_cv = prod.demand_cv * 0.4
        if npi and ramp_pct < 1.0:
            noise_cv *= 1.5  # 50% more variance during NPI ramp
        sigma = noise_cv
        mu_ln = -0.5 * sigma * sigma  # Ensures E[X] = 1.0
        noise = random.lognormvariate(mu_ln, sigma)

        return max(0.0, base * season * trend * holiday_mult * promo_mult * noise * ramp_pct * stocking_mult)

    def _is_customer_active(self, cust_code: str, day_offset: int) -> bool:
        """Check if a customer is active at a given day_offset (churn model)."""
        for threshold, code, action in CUSTOMER_CHURN_EVENTS:
            if code == cust_code:
                if action == "LOST" and day_offset >= threshold:
                    return False
                if action == "GAINED" and day_offset < threshold:
                    return False
        return True

    def _compute_demand_matrix(
        self, days: int, start_date: date
    ) -> Dict[str, Dict[str, List[float]]]:
        """Pre-compute daily demand: [customer_code][sku][day_offset] = qty.

        Includes customer churn: lost customers zero out, gained customers ramp in.
        Weekend values are 0.
        """
        matrix: Dict[str, Dict[str, List[float]]] = {}

        for cust in self._all_customers:
            matrix[cust.code] = {}
            for sku in _ALL_SKUS:
                daily = []
                for day_off in range(days):
                    d = start_date + timedelta(days=day_off)
                    if d.weekday() >= 5 or not self._is_customer_active(cust.code, day_off):
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
    ) -> Tuple[List, List, List, List, List, List]:
        """Generate customer orders and downstream fulfillment records.

        Returns:
            (outbound_orders, order_lines, fulfillments, shipments, shipment_lots, backorders)
        """
        outbound_orders: List[OutboundOrder] = []
        order_lines: List[OutboundOrderLine] = []
        fulfillments: List[FulfillmentOrder] = []
        shipments: List[Shipment] = []
        shipment_lots: List[ShipmentLot] = []
        backorders: List[Backorder] = []

        # Merge order day lookups
        order_day_map = dict(CUSTOMER_ORDER_DAY)
        order_day_map.update(CUSTOMER_ORDER_DAY_EXTENDED)

        for cust in self._all_customers:
            # Skip customers without a site in the DB (e.g., CUST_RNO if config hasn't been updated)
            if cust.code not in self.site_ids:
                continue
            cust_region = cust.region
            rdc_name = f"RDC_{cust_region}"
            rdc_id = self.site_ids[rdc_name]
            cust_site_id = self.site_ids[cust.code]
            order_day = order_day_map.get(cust.code, 0)
            is_biweekly = cust.delivery_frequency == "bi-weekly"

            week_counter = 0
            for day_off in range(days):
                d = start_date + timedelta(days=day_off)
                if d.weekday() != order_day:
                    continue
                # Customer churn check
                if not self._is_customer_active(cust.code, day_off):
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

                # Basket correlations: if one SKU is selected, partner has higher pull-in chance
                additional = []
                for sku_a, sku_b, strength in BASKET_PAIRS:
                    if sku_a in selected_skus and sku_b not in selected_skus:
                        if random.random() < strength:
                            additional.append(sku_b)
                    elif sku_b in selected_skus and sku_a not in selected_skus:
                        if random.random() < strength:
                            additional.append(sku_a)
                selected_skus = list(dict.fromkeys(selected_skus + additional))  # Dedup preserving order

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
                total_ordered_qty = 0.0
                total_order_value = 0.0
                order_has_backlog = False
                order_all_cancelled = True

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

                    # Order cancellation (~1.5% of lines)
                    is_cancelled = random.random() < 0.015

                    # Fulfillment determination
                    if is_cancelled:
                        shipped = 0.0
                        backlog = 0.0
                        status = "CANCELLED"
                    elif has_issue and line_num == 1:
                        # First line of problem orders gets partial fill
                        fill_pct = random.uniform(0.3, 0.8)
                        shipped = round(qty * fill_pct)
                        backlog = round(qty - shipped)
                        status = "PARTIALLY_FULFILLED"
                    else:
                        shipped = round(qty)
                        backlog = 0.0
                        status = "FULFILLED"

                    # Track order-level totals
                    total_ordered_qty += qty
                    total_order_value += qty * prod.unit_price
                    if not is_cancelled:
                        order_all_cancelled = False
                    if backlog > 0:
                        order_has_backlog = True

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

                    # Skip fulfillment/shipment for cancelled lines
                    if is_cancelled:
                        continue

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

                # OutboundOrder header (parent for all order lines in this order)
                if order_all_cancelled:
                    oo_status = "CANCELLED"
                elif order_has_backlog:
                    oo_status = "PARTIALLY_FULFILLED"
                else:
                    oo_status = "FULFILLED"

                oo = OutboundOrder(
                    id=order_id,
                    company_id=self.company_id,
                    order_type="SALES",
                    customer_id=cust.code,
                    customer_name=cust.name,
                    ship_from_site_id=rdc_id,
                    ship_to_site_id=cust_site_id,
                    status=oo_status,
                    order_date=d,
                    requested_delivery_date=delivery_date,
                    promised_delivery_date=delivery_date,
                    actual_delivery_date=delivery_date if oo_status == "FULFILLED" else None,
                    total_ordered_qty=total_ordered_qty,
                    total_fulfilled_qty=total_ship_qty,
                    total_value=round(total_order_value, 2),
                    currency="USD",
                    priority=priority,  # Last line's priority (representative)
                    reference_number=f"CUST-PO-{cust.code}-{d.strftime('%Y%m%d')}",
                    config_id=self.config_id,
                    source="HISTORY_GEN",
                )
                outbound_orders.append(oo)

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
            f"Outbound flow: {len(outbound_orders)} orders, {len(order_lines)} order lines, "
            f"{len(fulfillments)} fulfillments, {len(shipments)} shipments, "
            f"{len(shipment_lots)} lots, {len(backorders)} backorders"
        )
        return outbound_orders, order_lines, fulfillments, shipments, shipment_lots, backorders

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
                # Log-normal lead time (right-skewed, realistic tail behavior)
                sigma_lt = supplier.lead_time_variability
                mu_lt = math.log(lt) - 0.5 * sigma_lt * sigma_lt
                lt_raw = random.lognormvariate(mu_lt, sigma_lt)
                # Q4 seasonal freight slowdown (Oct-Dec)
                if order_date.month >= 10:
                    lt_raw *= random.uniform(1.05, 1.15)
                # Supplier outlier: 3% chance of extreme delay (weather, port congestion)
                if random.random() < 0.03:
                    lt_raw *= random.uniform(1.5, 3.0)
                lt_actual = max(1, round(lt_raw))
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
                            demand[c.code][sku][day_off] for c in self._all_customers
                        ) * 0.15  # CDC holds ~15% of total flow as buffer
                    elif site_name == "RDC_NW":
                        daily_demand = sum(
                            demand[c.code][sku][day_off]
                            for c in self._all_customers if c.region == "NW"
                        )
                    else:  # RDC_SW
                        daily_demand = sum(
                            demand[c.code][sku][day_off]
                            for c in self._all_customers if c.region == "SW"
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
                        actual = sum(demand[c.code][sku][day_off] for c in self._all_customers)
                    else:
                        actual = sum(
                            demand[c.code][sku][day_off]
                            for c in self._all_customers if c.region == region_filter
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
                                demand[c.code][sku][day_off] for c in self._all_customers
                            )
                        else:
                            monthly_actual += sum(
                                demand[c.code][sku][day_off]
                                for c in self._all_customers if c.region == region_filter
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
        """Generate external demand signals — promotions correlated with demand lifts,
        plus weather, market, and economic signals."""
        records: List[SupplementaryTimeSeries] = []
        emitted_promos: set = set()

        # Non-promotion signal types
        other_signals = [
            ("WEATHER", "Weather Impact", 0.02),
            ("MARKET_INDEX", "Market Price Index", 0.01),
            ("ECONOMIC_INDICATOR", "Economic Indicator", 0.005),
        ]

        for day_off in range(days):
            d = start_date + timedelta(days=day_off)
            if d.weekday() >= 5:
                continue

            # Emit PROMOTION signals correlated with actual demand lifts
            for sku in _ALL_SKUS:
                key = (day_off, sku)
                if key in self._promotion_events and key not in emitted_promos:
                    emitted_promos.add(key)
                    lift = self._promotion_events[key]
                    site_name = random.choice(["RDC_NW", "RDC_SW"])
                    site_id = self.site_ids[site_name]
                    records.append(SupplementaryTimeSeries(
                        company_id=self.company_id,
                        series_name=f"Promotional Event - {sku}",
                        series_type="PROMOTION",
                        product_id=self._pid(sku),
                        site_id=site_id,
                        observation_date=d,
                        value=round(lift * 100, 1),  # Discount percentage
                        unit="pct_discount",
                        confidence=random.uniform(0.7, 0.95),
                        source_channel="internal",
                        signal_direction="UP",
                        magnitude=round(lift, 3),
                        is_processed=True,
                        processed_at=datetime.combine(d, datetime.min.time()),
                        forecast_impact=round(lift * random.uniform(0.7, 1.0), 3),
                        source="HISTORY_GEN",
                    ))

            # Other signal types (random)
            for series_type, series_name, prob in other_signals:
                if random.random() > prob:
                    continue

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
                else:
                    value = random.uniform(0.5, 3.0)
                    unit = "index"

                records.append(SupplementaryTimeSeries(
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
                ))

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
                                demand[c.code][sku][idx] for c in self._all_customers
                            )
                        else:
                            gross_req += sum(
                                demand[c.code][sku][idx]
                                for c in self._all_customers if c.region == region_filter
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
    # Tier 1: Purchase Orders (FK base for GoodsReceipts)
    # ------------------------------------------------------------------

    def _generate_purchase_orders(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> Tuple[List[PurchaseOrder], List[PurchaseOrderLineItem]]:
        """Generate PurchaseOrder + PurchaseOrderLineItem records matching InboundOrder POs.

        These typed PO records are the FK base that GoodsReceipt.po_id references.
        """
        po_list: List[PurchaseOrder] = []
        po_line_list: List[PurchaseOrderLineItem] = []
        cdc_id = self.site_ids["CDC_WEST"]

        for supplier in SUPPLIERS:
            sup_site_id = self.site_ids.get(supplier.code, cdc_id)

            for day_off in range(0, days, 7):
                d = start_date + timedelta(days=day_off)
                order_date = d + timedelta(days=random.randint(-1, 1))
                if order_date.weekday() >= 5:
                    order_date = d

                self._po_seq += 1
                po_number = f"TPO-{order_date.strftime('%Y%m%d')}-{supplier.code}-{self._po_seq:05d}"

                lt = supplier.lead_time_days
                # Log-normal lead time (same distribution as inbound flow)
                sigma_lt = supplier.lead_time_variability
                mu_lt = math.log(lt) - 0.5 * sigma_lt * sigma_lt
                lt_raw = random.lognormvariate(mu_lt, sigma_lt)
                if order_date.month >= 10:
                    lt_raw *= random.uniform(1.05, 1.15)
                if random.random() < 0.03:
                    lt_raw *= random.uniform(1.5, 3.0)
                lt_actual = max(1, round(lt_raw))

                requested_del = order_date + timedelta(days=lt)
                actual_del = order_date + timedelta(days=lt_actual)

                total_amount = 0.0
                line_idx = 0

                po = PurchaseOrder(
                    po_number=po_number,
                    vendor_id=supplier.code,
                    supplier_site_id=sup_site_id,
                    destination_site_id=cdc_id,
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    company_id=self.company_id,
                    status="RECEIVED",
                    order_date=order_date,
                    requested_delivery_date=requested_del,
                    promised_delivery_date=requested_del,
                    actual_delivery_date=actual_del,
                    currency="USD",
                    source="HISTORY_GEN",
                )
                po_list.append(po)

                for sku in supplier.product_skus:
                    prod = _SKU_TO_PRODUCT[sku]
                    line_idx += 1

                    # Order qty: ~2 weeks of aggregate demand
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

                    line_total = order_qty * prod.unit_cost
                    total_amount += line_total

                    po_line = PurchaseOrderLineItem(
                        # po_id set after flush
                        line_number=line_idx,
                        product_id=self._pid(sku),
                        quantity=float(order_qty),
                        shipped_quantity=float(received),
                        received_quantity=float(received),
                        unit_price=prod.unit_cost,
                        line_total=round(line_total, 2),
                        requested_delivery_date=requested_del,
                        promised_delivery_date=requested_del,
                        actual_delivery_date=actual_del,
                    )
                    # Store for later FK assignment
                    po_line._parent_po = po
                    po_line_list.append(po_line)

                po.total_amount = round(total_amount, 2)

        self._po_records = po_list
        self._po_line_records = po_line_list
        logger.info(f"Purchase orders: {len(po_list)} POs, {len(po_line_list)} lines")
        return po_list, po_line_list

    # ------------------------------------------------------------------
    # Tier 1: Goods Receipts + Line Items
    # ------------------------------------------------------------------

    def _generate_goods_receipts(
        self,
        days: int,
        start_date: date,
    ) -> Tuple[List[GoodsReceipt], List[GoodsReceiptLineItem]]:
        """Generate GoodsReceipt + GoodsReceiptLineItem from PO records.

        ~1,000 GR headers with inspection outcomes:
        - 70% single delivery, 25% 2-split, 5% 3-split
        - 5% of lines have inspection failures
        """
        gr_list: List[GoodsReceipt] = []
        gr_line_list: List[GoodsReceiptLineItem] = []
        cdc_id = self.site_ids["CDC_WEST"]

        for po in self._po_records:
            # Determine number of deliveries for this PO
            r = random.random()
            if r < 0.70:
                n_deliveries = 1
            elif r < 0.95:
                n_deliveries = 2
            else:
                n_deliveries = 3

            # Get PO lines for this PO
            po_lines = [pl for pl in self._po_line_records if pl._parent_po is po]
            if not po_lines:
                continue

            receipt_date_base = po.actual_delivery_date or po.requested_delivery_date
            if not receipt_date_base:
                continue

            # Split quantities across deliveries
            for delivery_idx in range(n_deliveries):
                self._gr_seq += 1
                receipt_date = receipt_date_base + timedelta(days=delivery_idx * random.randint(2, 5))
                gr_number = f"GR-{receipt_date.strftime('%Y%m%d')}-{self._gr_seq:05d}"

                total_received = 0.0
                total_accepted = 0.0
                total_rejected = 0.0
                has_variance = False
                line_items = []

                for line_num, po_line in enumerate(po_lines, start=1):
                    # Split fraction for this delivery
                    if n_deliveries == 1:
                        frac = 1.0
                    elif n_deliveries == 2:
                        frac = 0.6 if delivery_idx == 0 else 0.4
                    else:
                        fracs = [0.5, 0.3, 0.2]
                        frac = fracs[delivery_idx]

                    expected = round(po_line.quantity * frac)
                    if expected <= 0:
                        continue

                    # Received qty with variance
                    variance_roll = random.random()
                    if variance_roll < 0.015:
                        # Under-delivery
                        received = round(expected * random.uniform(0.85, 0.97))
                    elif variance_roll < 0.02:
                        # Over-delivery
                        received = round(expected * random.uniform(1.02, 1.08))
                    else:
                        received = expected

                    variance_qty = received - expected
                    if variance_qty > 0:
                        variance_type = "OVER"
                    elif variance_qty < 0:
                        variance_type = "UNDER"
                    else:
                        variance_type = "EXACT"
                    if variance_type != "EXACT":
                        has_variance = True

                    # Inspection (30% of lines require it for food safety)
                    inspection_required = random.random() < 0.30
                    if inspection_required:
                        insp_roll = random.random()
                        if insp_roll < 0.85:
                            inspection_status = "PASSED"
                            accepted = received
                            rejected = 0.0
                            rejection_reason = None
                        elif insp_roll < 0.92:
                            inspection_status = "PARTIAL"
                            rejected = round(received * random.uniform(0.02, 0.08))
                            accepted = received - rejected
                            rejection_reason = random.choice(["QUALITY", "DAMAGED"])
                        else:
                            inspection_status = "FAILED"
                            rejected = round(received * random.uniform(0.10, 0.30))
                            accepted = received - rejected
                            rejection_reason = random.choice(["QUALITY", "DAMAGED", "WRONG_ITEM"])
                    else:
                        inspection_status = None
                        accepted = received
                        rejected = 0.0
                        rejection_reason = None

                    total_received += received
                    total_accepted += accepted
                    total_rejected += rejected

                    prod = _SKU_TO_PRODUCT.get(po_line.product_id.replace(f"CFG{self.config_id}_", ""))
                    shelf_life = prod.shelf_life_days if prod else 365
                    mfg_date = receipt_date - timedelta(days=random.randint(3, 30))

                    gr_line = GoodsReceiptLineItem(
                        # gr_id set after flush
                        po_line_id=0,  # Set after PO line flush
                        line_number=line_num,
                        product_id=po_line.product_id,
                        expected_qty=float(expected),
                        received_qty=float(received),
                        accepted_qty=float(accepted),
                        rejected_qty=float(rejected),
                        variance_qty=float(variance_qty),
                        variance_type=variance_type,
                        variance_reason=f"Supplier shipment variance" if variance_type != "EXACT" else None,
                        inspection_required=inspection_required,
                        inspection_status=inspection_status,
                        rejection_reason=rejection_reason,
                        batch_number=f"B-{po_line.product_id.split('_')[-1]}-{mfg_date.strftime('%y%m%d')}",
                        lot_number=f"LOT-{po_line.product_id.split('_')[-1]}-{mfg_date.strftime('%Y%m%d')}-{random.randint(1,99):02d}",
                        expiry_date=mfg_date + timedelta(days=shelf_life),
                    )
                    gr_line._parent_gr = None  # Will be set
                    gr_line._parent_po_line = po_line
                    line_items.append(gr_line)

                if not line_items:
                    continue

                carrier = random.choice(CARRIERS)
                has_failure = any(li.inspection_status == "FAILED" for li in line_items)

                gr = GoodsReceipt(
                    gr_number=gr_number,
                    po_id=0,  # Set after PO flush
                    receipt_date=datetime.combine(receipt_date, datetime.min.time()),
                    delivery_note_number=f"DN-{po.vendor_id}-{receipt_date.strftime('%Y%m%d')}",
                    carrier=carrier[1],
                    tracking_number=f"TRK-GR-{self._gr_seq:08d}",
                    status="REJECTED" if has_failure and total_rejected > total_accepted else "COMPLETED",
                    receiving_site_id=cdc_id,
                    receiving_location=f"Dock-{random.randint(1,4)}",
                    total_received_qty=round(total_received, 1),
                    total_accepted_qty=round(total_accepted, 1),
                    total_rejected_qty=round(total_rejected, 1),
                    has_variance=has_variance,
                    completed_at=datetime.combine(receipt_date, datetime.min.time()),
                    config_id=self.config_id,
                    source="HISTORY_GEN",
                )
                gr._parent_po = po
                gr._line_items = line_items
                for li in line_items:
                    li._parent_gr = gr

                gr_list.append(gr)
                gr_line_list.extend(line_items)

        logger.info(f"Goods receipts: {len(gr_list)} GRs, {len(gr_line_list)} lines")
        return gr_list, gr_line_list

    # ------------------------------------------------------------------
    # Tier 1: Quality Orders + Line Items
    # ------------------------------------------------------------------

    def _generate_quality_orders(
        self,
        gr_line_list: List[GoodsReceiptLineItem],
        days: int,
        start_date: date,
    ) -> Tuple[List[QualityOrder], List[QualityOrderLineItem]]:
        """Generate QualityOrder + QualityOrderLineItem from GR inspection lines.

        One QO per GR line with inspection_required=True (sampled).
        Each QO has 2-4 characteristic checks.
        """
        qo_list: List[QualityOrder] = []
        qo_line_list: List[QualityOrderLineItem] = []

        inspection_lines = [li for li in gr_line_list if li.inspection_required]
        # Sample ~40% of inspection lines for full QO records
        selected = random.sample(inspection_lines, min(len(inspection_lines), max(300, len(inspection_lines) * 2 // 5)))

        for gr_line in selected:
            self._qo_seq += 1
            gr = gr_line._parent_gr
            if not gr:
                continue

            receipt_dt = gr.receipt_date if isinstance(gr.receipt_date, date) else gr.receipt_date.date() if gr.receipt_date else start_date
            if isinstance(receipt_dt, datetime):
                receipt_dt = receipt_dt.date()

            qo_number = f"QO-{receipt_dt.strftime('%Y%m%d')}-{self._qo_seq:05d}"

            # Determine disposition based on inspection status
            insp_status = gr_line.inspection_status or "PASSED"
            if insp_status == "PASSED":
                disposition = "ACCEPT"
                defect_rate = 0.0
                severity = "MINOR"
            elif insp_status == "PARTIAL":
                disposition = random.choice(["CONDITIONAL_ACCEPT", "ACCEPT", "USE_AS_IS"])
                defect_rate = round(random.uniform(0.01, 0.08), 4)
                severity = random.choices(["MINOR", "MAJOR"], weights=[0.7, 0.3])[0]
            else:  # FAILED
                disposition = random.choices(
                    ["REJECT", "RETURN_TO_VENDOR", "REWORK", "SCRAP"],
                    weights=[0.4, 0.3, 0.2, 0.1]
                )[0]
                defect_rate = round(random.uniform(0.05, 0.20), 4)
                severity = random.choices(["MAJOR", "CRITICAL"], weights=[0.6, 0.4])[0]

            insp_start = datetime.combine(receipt_dt, datetime.min.time()) + timedelta(hours=random.randint(1, 4))
            insp_end = insp_start + timedelta(hours=random.randint(1, 8))

            # Compute quantities
            insp_qty = gr_line.received_qty
            accepted_qty = gr_line.accepted_qty
            rejected_qty = gr_line.rejected_qty
            rework_qty = round(rejected_qty * 0.3) if disposition == "REWORK" else 0.0
            scrap_qty = round(rejected_qty * 0.5) if disposition == "SCRAP" else 0.0
            use_as_is_qty = round(rejected_qty * 0.5) if disposition == "USE_AS_IS" else 0.0

            # Base sku for vendor lookup
            base_sku = gr_line.product_id.replace(f"CFG{self.config_id}_", "")
            vendor_id = _SKU_TO_SUPPLIER.get(base_sku, SUPPLIERS[0]).code if base_sku in _SKU_TO_SUPPLIER else None

            qo = QualityOrder(
                quality_order_number=qo_number,
                company_id=self.company_id,
                site_id=gr.receiving_site_id or self.site_ids["CDC_WEST"],
                config_id=self.config_id,
                tenant_id=self.tenant_id,
                inspection_type="INCOMING",
                status="CLOSED",
                origin_type="GOODS_RECEIPT",
                origin_order_id=gr.gr_number,
                origin_order_type="purchase_order",
                product_id=gr_line.product_id,
                lot_number=gr_line.lot_number,
                batch_number=gr_line.batch_number,
                inspection_quantity=float(insp_qty),
                sample_size=round(insp_qty * random.uniform(0.05, 0.20)),
                accepted_quantity=float(accepted_qty),
                rejected_quantity=float(rejected_qty),
                rework_quantity=float(rework_qty),
                scrap_quantity=float(scrap_qty),
                use_as_is_quantity=float(use_as_is_qty),
                disposition=disposition,
                disposition_reason=f"Incoming inspection {insp_status.lower()}" if insp_status != "PASSED" else None,
                defect_rate=defect_rate,
                defect_category=gr_line.rejection_reason if gr_line.rejection_reason else None,
                severity_level=severity,
                vendor_id=vendor_id,
                vendor_lot=gr_line.lot_number,
                order_date=receipt_dt,
                inspection_start_date=insp_start,
                inspection_end_date=insp_end,
                inspection_cost=round(random.uniform(25, 150), 2),
                rework_cost=round(random.uniform(100, 500), 2) if rework_qty > 0 else 0.0,
                scrap_cost=round(scrap_qty * random.uniform(5, 20), 2) if scrap_qty > 0 else 0.0,
                total_quality_cost=0.0,  # Computed below
                hold_inventory=True,
                mrp_impact=disposition in ("REJECT", "SCRAP", "RETURN_TO_VENDOR"),
                source="HISTORY_GEN",
            )
            qo.total_quality_cost = round(
                (qo.inspection_cost or 0) + (qo.rework_cost or 0) + (qo.scrap_cost or 0), 2
            )
            qo_list.append(qo)

            # Generate 2-4 characteristic line items
            sku_group = _SKU_TO_GROUP.get(base_sku, "DRY_PANTRY")
            is_frozen = sku_group in ("FRZ_PROTEIN", "FRZ_DESSERT")
            is_refrigerated = sku_group == "REF_DAIRY"
            is_perishable = is_frozen or is_refrigerated

            characteristics = []
            # 1. Temperature check (for temp-sensitive products)
            if is_perishable:
                target_temp = -10.0 if is_frozen else 36.0
                measured = target_temp + random.gauss(0, 2.0)
                passed = abs(measured - target_temp) < 5.0
                characteristics.append((
                    "Temperature Check", "QUANTITATIVE",
                    target_temp, target_temp - 5.0, target_temp + 5.0, "°F",
                    measured, None, "PASS" if passed else "FAIL",
                    "Digital thermometer probe"
                ))

            # 2. Visual inspection (always)
            visual_pass = random.random() < 0.92
            characteristics.append((
                "Visual Inspection", "QUALITATIVE",
                None, None, None, None,
                None, "No visible damage or contamination" if visual_pass else "Visible package damage detected",
                "PASS" if visual_pass else "FAIL",
                None
            ))

            # 3. Weight verification (always)
            target_wt = insp_qty * random.uniform(8, 25)  # Approximate case weight
            measured_wt = target_wt * random.gauss(1.0, 0.01)
            wt_pass = abs(measured_wt - target_wt) / target_wt < 0.03
            characteristics.append((
                "Weight Verification", "QUANTITATIVE",
                target_wt, target_wt * 0.97, target_wt * 1.03, "lbs",
                measured_wt, None, "PASS" if wt_pass else "FAIL",
                "Platform scale"
            ))

            # 4. Microbiological test (for perishables)
            if is_perishable and random.random() < 0.5:
                colony_count = random.lognormvariate(3.0, 0.8)  # CFU/g
                micro_pass = colony_count < 10000
                characteristics.append((
                    "Microbiological Test", "QUANTITATIVE",
                    0.0, 0.0, 10000.0, "CFU/g",
                    colony_count, None, "PASS" if micro_pass else "FAIL",
                    "Lab incubation 48h"
                ))

            for char_idx, (name, char_type, target, lower, upper, uom, mval, mtext, result, instrument) in enumerate(characteristics, start=1):
                qo_line = QualityOrderLineItem(
                    # quality_order_id set after flush
                    line_number=char_idx,
                    characteristic_name=name,
                    characteristic_type=char_type,
                    target_value=target,
                    lower_limit=lower,
                    upper_limit=upper,
                    unit_of_measure=uom,
                    measured_value=round(mval, 2) if mval is not None else None,
                    measured_text=mtext,
                    result=result,
                    defect_count=1 if result == "FAIL" else 0,
                    measurement_instrument=instrument,
                    inspected_at=insp_end,
                )
                qo_line._parent_qo = qo
                qo_line_list.append(qo_line)

        logger.info(f"Quality orders: {len(qo_list)} QOs, {len(qo_line_list)} characteristics")
        return qo_list, qo_line_list

    # ------------------------------------------------------------------
    # Tier 1: Inbound Order Line Schedules
    # ------------------------------------------------------------------

    async def _generate_and_insert_schedules(self, inbound_lines_raw: List[dict]):
        """Generate InboundOrderLineSchedule records after inbound lines are inserted.

        Queries back auto-increment IDs, then generates 1-3 schedule lines per inbound line.
        """
        # Query back the IDs
        result = await self.db.execute(
            text("SELECT id, order_id, line_number FROM inbound_order_line WHERE config_id = :cid"),
            {"cid": self.config_id}
        )
        rows = result.fetchall()
        # rows are (id, order_id, line_number)
        line_id_map = {}
        for row in rows:
            line_id_map[(row[1], row[2])] = row[0]

        schedule_records = []
        for ibl in inbound_lines_raw:
            order_id = ibl["order_id"]
            line_number = ibl["line_number"]
            db_id = line_id_map.get((order_id, line_number))
            if not db_id:
                continue

            total_qty = ibl["quantity_submitted"]
            expected_date = ibl["expected_delivery_date"]
            actual_date = ibl.get("order_receive_date", expected_date)

            # Number of schedule lines
            r = random.random()
            if r < 0.60:
                n_sched = 1
            elif r < 0.90:
                n_sched = 2
            else:
                n_sched = 3

            remaining = total_qty
            for sched_idx in range(n_sched):
                if sched_idx == n_sched - 1:
                    sched_qty = remaining
                else:
                    frac = 0.6 if n_sched == 2 else (0.5 if sched_idx == 0 else 0.3)
                    sched_qty = round(total_qty * frac)
                    remaining -= sched_qty

                if sched_qty <= 0:
                    continue

                sched_date = expected_date + timedelta(days=sched_idx * random.randint(2, 5))
                # Actual: slight variance from scheduled
                act_delay = random.randint(-1, 3)
                act_date = sched_date + timedelta(days=act_delay)
                is_delayed = act_delay > 2

                # Received qty: 95% exact, 5% slight variance
                if random.random() < 0.05:
                    recv_qty = round(sched_qty * random.uniform(0.92, 0.99))
                else:
                    recv_qty = sched_qty

                schedule_records.append({
                    "order_line_id": db_id,
                    "schedule_number": sched_idx + 1,
                    "scheduled_quantity": float(sched_qty),
                    "received_quantity": float(recv_qty),
                    "scheduled_date": sched_date,
                    "actual_date": act_date,
                    "status": "DELAYED" if is_delayed else "RECEIVED",
                    "source": "HISTORY_GEN",
                })

        if schedule_records:
            insert_sql = text("""
                INSERT INTO inbound_order_line_schedule
                    (order_line_id, schedule_number, scheduled_quantity, received_quantity,
                     scheduled_date, actual_date, status, source)
                VALUES
                    (:order_line_id, :schedule_number, :scheduled_quantity, :received_quantity,
                     :scheduled_date, :actual_date, :status, :source)
            """)
            for i in range(0, len(schedule_records), 500):
                batch = schedule_records[i:i + 500]
                await self.db.execute(insert_sql, batch)
                await self.db.flush()

        logger.info(f"Inbound order line schedules: {len(schedule_records)} records")
        return len(schedule_records)

    # ------------------------------------------------------------------
    # Tier 2: Transfer Orders + Line Items
    # ------------------------------------------------------------------

    def _generate_transfer_orders(
        self,
        demand: Dict[str, Dict[str, List[float]]],
        days: int,
        start_date: date,
    ) -> Tuple[List[TransferOrder], List[TransferOrderLineItem]]:
        """Generate TransferOrder + TransferOrderLineItem for CDC→RDC transfers.

        ~500 headers, ~2,000 lines. 2% damage rate, log-normal transit times.
        """
        to_list: List[TransferOrder] = []
        to_line_list: List[TransferOrderLineItem] = []
        cdc_id = self.site_ids["CDC_WEST"]

        for rdc_def in RDCS:
            rdc_id = self.site_ids[rdc_def.code]

            for day_off in range(0, days, 7):
                d = start_date + timedelta(days=day_off)
                # Transfers happen mid-week (Wednesday)
                transfer_date = d + timedelta(days=(2 - d.weekday()) % 7)
                if (transfer_date - start_date).days >= days:
                    continue

                self._to_transfer_seq += 1
                to_number = f"XFR-{transfer_date.strftime('%Y%m%d')}-{rdc_def.code}-{self._to_transfer_seq:05d}"

                # Log-normal transit time (1-3 day base for internal transfers)
                base_transit = 1.5
                sigma_t = 0.3
                mu_t = math.log(base_transit) - 0.5 * sigma_t * sigma_t
                transit_raw = random.lognormvariate(mu_t, sigma_t)
                if transfer_date.month >= 10:
                    transit_raw *= random.uniform(1.05, 1.10)
                transit_days = max(1, round(transit_raw))

                ship_date = transfer_date
                est_delivery = transfer_date + timedelta(days=transit_days)
                # Actual delivery: slight variance
                actual_delivery = est_delivery + timedelta(days=random.randint(-1, 2))

                # Status distribution
                status_roll = random.random()
                if status_roll < 0.95:
                    status = "RECEIVED"
                elif status_roll < 0.98:
                    status = "SHIPPED"
                else:
                    status = "CANCELLED"

                carrier = random.choice(CARRIERS)

                to = TransferOrder(
                    to_number=to_number,
                    source_site_id=cdc_id,
                    destination_site_id=rdc_id,
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    company_id=self.company_id,
                    order_type="transfer",
                    status=status,
                    order_date=transfer_date,
                    shipment_date=ship_date,
                    estimated_delivery_date=est_delivery,
                    actual_ship_date=ship_date if status != "CANCELLED" else None,
                    actual_delivery_date=actual_delivery if status == "RECEIVED" else None,
                    transportation_mode="truck",
                    carrier=carrier[1],
                    tracking_number=f"TRK-XFR-{self._to_transfer_seq:08d}",
                    source="HISTORY_GEN",
                )
                to_list.append(to)

                # Generate line items (products with demand for this RDC's customers)
                line_num = 0
                for sku in _ALL_SKUS:
                    wk_demand = 0.0
                    for cust in self._all_customers:
                        if cust.region != rdc_def.region:
                            continue
                        for dd in range(7):
                            idx = day_off + dd
                            if idx < days:
                                wk_demand += demand[cust.code][sku][idx]
                    if wk_demand < 1:
                        continue

                    line_num += 1
                    transfer_qty = max(1, round(wk_demand * random.uniform(1.0, 1.2)))

                    # 2% damage rate for cold chain transit
                    if random.random() < 0.02:
                        damaged = round(transfer_qty * random.uniform(0.01, 0.05))
                    else:
                        damaged = 0.0
                    received_qty = transfer_qty - damaged if status == "RECEIVED" else 0.0

                    to_line = TransferOrderLineItem(
                        # to_id set after flush
                        line_number=line_num,
                        product_id=self._pid(sku),
                        quantity=float(transfer_qty),
                        picked_quantity=float(transfer_qty) if status != "CANCELLED" else 0.0,
                        shipped_quantity=float(transfer_qty) if status in ("SHIPPED", "RECEIVED") else 0.0,
                        received_quantity=float(received_qty),
                        damaged_quantity=float(damaged),
                        requested_ship_date=ship_date,
                        requested_delivery_date=est_delivery,
                        actual_ship_date=ship_date if status != "CANCELLED" else None,
                        actual_delivery_date=actual_delivery if status == "RECEIVED" else None,
                    )
                    to_line._parent_to = to
                    to_line_list.append(to_line)

        logger.info(f"Transfer orders: {len(to_list)} TOs, {len(to_line_list)} lines")
        return to_list, to_line_list

    # ------------------------------------------------------------------
    # Tier 2: Maintenance Orders
    # ------------------------------------------------------------------

    def _generate_maintenance_orders(
        self,
        days: int,
        start_date: date,
    ) -> List[MaintenanceOrder]:
        """Generate ~150 maintenance orders for cold chain equipment.

        Mix: ~70% preventive, ~25% corrective, ~5% emergency.
        """
        mo_list: List[MaintenanceOrder] = []

        for asset_id, asset_name, asset_type, site_code, freq_days in COLD_CHAIN_EQUIPMENT:
            site_id = self.site_ids.get(site_code)
            if not site_id:
                continue

            # Preventive maintenance at scheduled intervals
            last_maint = start_date - timedelta(days=random.randint(0, freq_days))
            maint_date = last_maint + timedelta(days=freq_days)

            while maint_date < start_date + timedelta(days=days):
                self._mo_seq += 1
                mo_number = f"MO-{site_code}-{maint_date.strftime('%Y%m%d')}-{self._mo_seq:04d}"

                est_downtime = random.uniform(2.0, 4.0)
                sigma_dt = 0.2
                actual_downtime = est_downtime * random.lognormvariate(0, sigma_dt)
                est_labor = est_downtime * random.uniform(1.0, 1.5)
                actual_labor = actual_downtime * random.uniform(0.8, 1.2)
                est_cost = random.uniform(200, 500)
                actual_cost = est_cost * random.uniform(0.8, 1.3)

                sched_start = datetime.combine(maint_date, datetime.min.time()) + timedelta(hours=6)
                sched_end = sched_start + timedelta(hours=est_downtime)
                actual_start = sched_start + timedelta(minutes=random.randint(-30, 60))
                actual_end = actual_start + timedelta(hours=actual_downtime)

                work_desc = _MAINT_WORK_DESC.get(asset_type, {}).get("PREVENTIVE", "Scheduled preventive maintenance")

                mo = MaintenanceOrder(
                    maintenance_order_number=mo_number,
                    asset_id=asset_id,
                    asset_name=asset_name,
                    asset_type=asset_type,
                    site_id=site_id,
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    company_id=self.company_id,
                    maintenance_type="PREVENTIVE",
                    status="COMPLETED",
                    priority="NORMAL",
                    order_date=maint_date,
                    scheduled_start_date=sched_start,
                    scheduled_completion_date=sched_end,
                    actual_start_date=actual_start,
                    actual_completion_date=actual_end,
                    last_maintenance_date=last_maint,
                    next_maintenance_due=maint_date + timedelta(days=freq_days),
                    maintenance_frequency_days=freq_days,
                    downtime_required="Y",
                    estimated_downtime_hours=round(est_downtime, 1),
                    actual_downtime_hours=round(actual_downtime, 1),
                    work_description=work_desc,
                    estimated_labor_hours=round(est_labor, 1),
                    actual_labor_hours=round(actual_labor, 1),
                    estimated_cost=round(est_cost, 2),
                    actual_cost=round(actual_cost, 2),
                    quality_check_passed="Y" if random.random() < 0.95 else "N",
                    source="HISTORY_GEN",
                )
                mo_list.append(mo)
                last_maint = maint_date
                maint_date = maint_date + timedelta(days=freq_days)

            # Corrective maintenance — random failures
            # Compressors and freezers fail more often
            failure_rate = 0.04 if asset_type in ("COMPRESSOR", "WALK_IN_FREEZER") else 0.02
            for day_off in range(days):
                if random.random() >= failure_rate / 30:  # Monthly probability → daily
                    continue
                d = start_date + timedelta(days=day_off)

                self._mo_seq += 1
                mo_number = f"MO-{site_code}-{d.strftime('%Y%m%d')}-{self._mo_seq:04d}"

                # Corrective: more downtime and cost
                est_downtime = random.uniform(4.0, 16.0)
                actual_downtime = est_downtime * random.lognormvariate(0, 0.3)
                est_cost = random.uniform(500, 5000)
                actual_cost = est_cost * random.uniform(0.9, 2.0)

                sched_start = datetime.combine(d, datetime.min.time()) + timedelta(hours=random.randint(0, 18))
                actual_start = sched_start + timedelta(minutes=random.randint(15, 120))
                actual_end = actual_start + timedelta(hours=actual_downtime)

                is_emergency = random.random() < 0.20  # 20% of corrective → emergency
                maint_type = "EMERGENCY" if is_emergency else "CORRECTIVE"
                priority = "EMERGENCY" if is_emergency else "HIGH"
                work_desc = _MAINT_WORK_DESC.get(asset_type, {}).get(maint_type, f"{maint_type} maintenance")

                mo = MaintenanceOrder(
                    maintenance_order_number=mo_number,
                    asset_id=asset_id,
                    asset_name=asset_name,
                    asset_type=asset_type,
                    site_id=site_id,
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    company_id=self.company_id,
                    maintenance_type=maint_type,
                    status="COMPLETED",
                    priority=priority,
                    order_date=d,
                    scheduled_start_date=sched_start,
                    scheduled_completion_date=sched_start + timedelta(hours=est_downtime),
                    actual_start_date=actual_start,
                    actual_completion_date=actual_end,
                    downtime_required="Y",
                    estimated_downtime_hours=round(est_downtime, 1),
                    actual_downtime_hours=round(actual_downtime, 1),
                    work_description=work_desc,
                    failure_description=f"Unscheduled failure detected on {asset_name}" if maint_type == "CORRECTIVE"
                        else f"Emergency: {asset_name} critical failure, product at risk",
                    estimated_labor_hours=round(est_downtime * 1.5, 1),
                    actual_labor_hours=round(actual_downtime * 1.3, 1),
                    estimated_cost=round(est_cost, 2),
                    actual_cost=round(actual_cost, 2),
                    quality_check_passed="Y" if random.random() < 0.90 else "N",
                    source="HISTORY_GEN",
                )
                mo_list.append(mo)

        logger.info(f"Maintenance orders: {len(mo_list)} records")
        return mo_list

    # ------------------------------------------------------------------
    # Production Orders (CDC repackaging / cross-docking operations)
    # ------------------------------------------------------------------

    def _generate_production_orders(
        self,
        days: int,
        start_date: date,
    ) -> List[ProductionOrder]:
        """Generate production orders for CDC repackaging operations.

        Food distribution CDCs perform case-to-each breakdown, relabeling,
        and mixed-pallet building. These are modeled as simple production orders.
        ~75 records over the 2-year horizon (roughly bi-weekly).
        """
        prod_orders: List[ProductionOrder] = []
        cdc_id = self.site_ids["CDC_WEST"]

        # Repackaging product candidates (frozen proteins and dry pantry are
        # commonly broken down from master cases to individual eaches)
        repack_skus = [
            ("FP001", "Case-to-each breakdown: chicken breast portions"),
            ("FP002", "Case-to-each breakdown: beef patties"),
            ("FP003", "Repack: pork chops portion control"),
            ("DP001", "Relabel/repack: pasta multi-packs"),
            ("DP003", "Repack: flour into foodservice bags"),
            ("FD001", "Mixed-pallet build: ice cream variety packs"),
            ("BV001", "Mixed-pallet build: juice variety packs"),
        ]

        # Generate roughly bi-weekly production orders
        order_interval = 14  # days between production runs
        for day_off in range(0, days, order_interval):
            d = start_date + timedelta(days=day_off)
            # Skip weekends
            if d.weekday() >= 5:
                d += timedelta(days=(7 - d.weekday()))
            if (d - start_date).days >= days:
                continue

            # Pick 1-2 SKUs per production run
            n_skus = random.randint(1, 2)
            selected = random.sample(repack_skus, min(n_skus, len(repack_skus)))

            for sku, description in selected:
                prod = _SKU_TO_PRODUCT.get(sku)
                if not prod:
                    continue

                self._prod_order_seq += 1
                order_number = f"MO-CDC-{d.strftime('%Y%m%d')}-{self._prod_order_seq:04d}"

                planned_qty = random.randint(50, 300)
                # Yield: 95-100% for repackaging (minor losses)
                yield_pct = random.uniform(95.0, 100.0)
                actual_qty = round(planned_qty * yield_pct / 100.0)
                scrap_qty = planned_qty - actual_qty

                planned_start = datetime.combine(d, datetime.min.time()) + timedelta(hours=6)
                # Repackaging takes 2-6 hours
                duration_hours = random.uniform(2.0, 6.0)
                planned_end = planned_start + timedelta(hours=duration_hours)
                # Actual times with slight variance
                actual_start = planned_start + timedelta(minutes=random.randint(-30, 30))
                actual_end = planned_end + timedelta(minutes=random.randint(-20, 45))

                status = "COMPLETED"
                # 5% chance still in progress (recent orders)
                if day_off > days - 30 and random.random() < 0.15:
                    status = "IN_PROGRESS"
                    actual_end = None
                    actual_qty = None
                    scrap_qty = 0

                po = ProductionOrder(
                    order_number=order_number,
                    item_id=self._pid(sku),
                    site_id=cdc_id,
                    config_id=self.config_id,
                    planned_quantity=planned_qty,
                    actual_quantity=actual_qty,
                    scrap_quantity=scrap_qty,
                    yield_percentage=yield_pct if status == "COMPLETED" else None,
                    status=status,
                    planned_start_date=planned_start,
                    planned_completion_date=planned_end,
                    actual_start_date=actual_start,
                    actual_completion_date=actual_end,
                    released_date=planned_start - timedelta(hours=1),
                    closed_date=actual_end + timedelta(hours=2) if actual_end else None,
                    lead_time_planned=1,
                    lead_time_actual=1 if actual_end else None,
                    priority=random.choice([3, 4, 5]),
                    resource_hours_planned=round(duration_hours, 1),
                    resource_hours_actual=round((actual_end - actual_start).total_seconds() / 3600, 1) if actual_end else None,
                    setup_cost=round(random.uniform(25.0, 75.0), 2),
                    unit_cost=round(prod.unit_cost * 0.05, 2),  # Repack cost ~5% of product cost
                    order_type="REPACK",
                    notes=description,
                )
                po.total_cost = round(po.setup_cost + po.unit_cost * planned_qty, 2)
                prod_orders.append(po)

        logger.info(f"Production orders: {len(prod_orders)} records (CDC repackaging)")
        return prod_orders

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

        Agent evaluation uses the Digital Twin (stochastic simulation) for
        train/test split, not historical data. This history establishes
        the baseline operational data for the tenant.

        Args:
            days: Number of days of history (default 730 = 2 years)
            start_date: Start date for history (default: today - days)
            seed: Random seed for reproducibility

        Returns:
            Dict with record counts per entity type
        """
        random.seed(seed)
        self._total_days = days

        if start_date is None:
            start_date = date.today() - timedelta(days=days)

        end_date = start_date + timedelta(days=days - 1)
        logger.info(
            f"Generating {days}-day history from {start_date} to {end_date} "
            f"for config {self.config_id}"
        )

        # 1. Load network topology
        await self._load_network()

        # 2. Pre-generate promotion events (before demand matrix)
        logger.info("Pre-generating promotion events...")
        self._pre_generate_promotion_events(days, start_date)

        # 3. Compute demand matrix (now includes churn, holidays, promos, log-normal noise)
        logger.info("Computing demand matrix...")
        demand = self._compute_demand_matrix(days, start_date)

        # 4. Generate all entity records
        counts: Dict[str, int] = {}

        # Outbound flow (with basket correlations, cancellations)
        logger.info("Generating outbound flow...")
        oo, ool, fo, ob_sh, ob_lots, bo = self._generate_outbound_flow(demand, days, start_date)
        counts["outbound_orders"] = len(oo)
        counts["outbound_order_lines"] = len(ool)
        counts["fulfillment_orders"] = len(fo)
        counts["outbound_shipments"] = len(ob_sh)
        counts["outbound_shipment_lots"] = len(ob_lots)
        counts["backorders"] = len(bo)

        # Inbound flow (with log-normal lead times)
        logger.info("Generating inbound flow...")
        ibo, ibl, ib_sh, ib_lots = self._generate_inbound_flow(demand, days, start_date)
        counts["inbound_orders"] = len(ibo)
        counts["inbound_order_lines"] = len(ibl)
        counts["inbound_shipments"] = len(ib_sh)
        counts["inbound_shipment_lots"] = len(ib_lots)

        # Purchase Orders (Tier 1 — FK base for GoodsReceipts)
        logger.info("Generating purchase orders...")
        po_list, po_line_list = self._generate_purchase_orders(demand, days, start_date)
        counts["purchase_orders"] = len(po_list)
        counts["purchase_order_lines"] = len(po_line_list)

        # Transfer Orders (Tier 2)
        logger.info("Generating transfer orders...")
        to_list, to_line_list = self._generate_transfer_orders(demand, days, start_date)
        counts["transfer_orders"] = len(to_list)
        counts["transfer_order_lines"] = len(to_line_list)

        # Maintenance Orders (Tier 2)
        logger.info("Generating maintenance orders...")
        mo_list = self._generate_maintenance_orders(days, start_date)
        counts["maintenance_orders"] = len(mo_list)

        # Production Orders (CDC repackaging)
        logger.info("Generating production orders...")
        prod_order_list = self._generate_production_orders(days, start_date)
        counts["production_orders"] = len(prod_order_list)

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

        # Supplementary signals (promo signals now correlated with demand lifts)
        logger.info("Generating supplementary signals...")
        sts = self._generate_supplementary_signals(days, start_date)
        counts["supplementary_signals"] = len(sts)

        # Inventory projections
        logger.info("Generating inventory projections...")
        ip = self._generate_inventory_projections(demand, days, start_date)
        counts["inventory_projections"] = len(ip)

        # ========================================================
        # 5. Bulk insert — phased to respect FK constraints
        # ========================================================
        logger.info("Bulk inserting records...")

        # --- Phase 1: Core entities (no new FK deps) ---

        # Inbound orders first (PK referenced by lines)
        await _batch_add(self.db, ibo, batch_size=500)

        # Inbound order lines (raw SQL — DB schema differs from ORM model)
        await self._batch_insert_inbound_lines(ibl)

        # Inbound order line schedules (Tier 1 — requires inbound_order_line IDs)
        logger.info("Generating inbound order line schedules...")
        sched_count = await self._generate_and_insert_schedules(ibl)
        counts["inbound_order_line_schedules"] = sched_count

        # Outbound orders (headers — must precede order lines for FK)
        await _batch_add(self.db, oo, batch_size=1000)

        # Outbound order lines
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

        # --- Phase 2: PO → GR → QO chain (sequential flushes for FK linkage) ---

        # Purchase Orders
        logger.info("Inserting purchase orders...")
        await _batch_add(self.db, po_list, batch_size=500)
        await self.db.flush()  # Get PO auto-increment IDs

        # Assign po_id to PO line items
        for po_line in po_line_list:
            po_line.po_id = po_line._parent_po.id
        await _batch_add(self.db, po_line_list, batch_size=1000)
        await self.db.flush()  # Get PO line auto-increment IDs

        # Goods Receipts (Tier 1)
        logger.info("Generating goods receipts...")
        gr_list, gr_line_list = self._generate_goods_receipts(days, start_date)
        counts["goods_receipts"] = len(gr_list)
        counts["goods_receipt_lines"] = len(gr_line_list)

        # Assign po_id to GR headers
        for gr in gr_list:
            gr.po_id = gr._parent_po.id
        await _batch_add(self.db, gr_list, batch_size=500)
        await self.db.flush()  # Get GR auto-increment IDs

        # Assign gr_id and po_line_id to GR line items
        for gr_line in gr_line_list:
            gr_line.gr_id = gr_line._parent_gr.id
            gr_line.po_line_id = gr_line._parent_po_line.id
        await _batch_add(self.db, gr_line_list, batch_size=1000)
        await self.db.flush()

        # Quality Orders (Tier 1)
        logger.info("Generating quality orders...")
        qo_list, qo_line_list = self._generate_quality_orders(gr_line_list, days, start_date)
        counts["quality_orders"] = len(qo_list)
        counts["quality_order_lines"] = len(qo_line_list)

        await _batch_add(self.db, qo_list, batch_size=500)
        await self.db.flush()  # Get QO auto-increment IDs

        # Assign quality_order_id to QO line items
        for qo_line in qo_line_list:
            qo_line.quality_order_id = qo_line._parent_qo.id
        await _batch_add(self.db, qo_line_list, batch_size=1000)

        # --- Phase 3: Transfer Orders (Tier 2, independent) ---

        logger.info("Inserting transfer orders...")
        await _batch_add(self.db, to_list, batch_size=500)
        await self.db.flush()  # Get TO auto-increment IDs

        # Assign to_id to TO line items
        for to_line in to_line_list:
            to_line.to_id = to_line._parent_to.id
        await _batch_add(self.db, to_line_list, batch_size=1000)

        # --- Phase 4: Maintenance Orders (Tier 2, independent) ---

        logger.info("Inserting maintenance orders...")
        await _batch_add(self.db, mo_list, batch_size=500)

        # --- Phase 4b: Production Orders (CDC repackaging) ---

        logger.info("Inserting production orders...")
        await _batch_add(self.db, prod_order_list, batch_size=500)

        # --- Phase 5: Analytics entities (unchanged) ---

        await _batch_add(self.db, inv, batch_size=5000)
        await _batch_add(self.db, fcst, batch_size=5000)
        await _batch_add(self.db, cd, batch_size=1000)
        await _batch_add(self.db, sts, batch_size=500)
        await _batch_add(self.db, ip, batch_size=5000)

        # Final commit
        await self.db.commit()

        # Seed Experiential Knowledge from DAG topology + transaction patterns
        try:
            ek_count = await self._seed_experiential_knowledge()
            counts["experiential_knowledge"] = ek_count
        except Exception as e:
            logger.warning(f"EK seeding failed (non-critical): {e}")

        total = sum(counts.values())
        counts["total"] = total

        logger.info(f"History generation complete: {total:,} total records")
        for entity, count in sorted(counts.items()):
            if entity != "total":
                logger.info(f"  {entity}: {count:,}")

        return counts

    async def _seed_experiential_knowledge(self) -> int:
        """Seed Experiential Knowledge entries derived from DAG topology and transactions.

        Generates realistic EK patterns a food distribution network would have learned:
        - Seasonal demand shifts for perishable products
        - Vendor lead time variability by region/season
        - Quality inspection patterns by product category
        - Rebalancing patterns between regions
        - Capacity constraints at manufacturing/DC sites
        """
        from app.models.experiential_knowledge import ExperientialKnowledge
        from sqlalchemy import text

        # Clean existing EK for this config
        await self.db.execute(text(
            "DELETE FROM experiential_knowledge WHERE config_id = :cfg"
        ), {"cfg": self.config_id})

        entries = []
        now = datetime.utcnow()

        # Get products and sites for realistic entity references
        products = await self.db.execute(text(
            "SELECT id, description FROM product WHERE config_id = :cfg LIMIT 30"
        ), {"cfg": self.config_id})
        prod_rows = products.fetchall()

        sites = await self.db.execute(text(
            "SELECT id, name, type, master_type FROM site WHERE config_id = :cfg AND is_external = false"
        ), {"cfg": self.config_id})
        site_rows = sites.fetchall()

        vendors = await self.db.execute(text(
            "SELECT id, description FROM trading_partners WHERE tpartner_type = 'vendor' "
            "AND company_id = (SELECT company_id FROM site WHERE config_id = :cfg LIMIT 1) LIMIT 10"
        ), {"cfg": self.config_id})
        vendor_rows = vendors.fetchall()

        # 1. Seasonal demand patterns per product category
        seasonal_patterns = [
            ("Q4 holiday demand surge for desserts and bakery items",
             "demand_seasonality", {"season": "Q4", "product_category": "desserts_bakery"},
             {"variable": "demand", "direction": "increase", "multiplier": 1.35, "confidence_interval": [1.2, 1.5]},
             ["forecast_adjustment", "inventory_buffer"]),
            ("Summer demand spike for beverages and juices",
             "demand_seasonality", {"season": "summer", "months": [6, 7, 8]},
             {"variable": "demand", "direction": "increase", "multiplier": 1.45, "confidence_interval": [1.3, 1.6]},
             ["forecast_adjustment", "inventory_buffer", "po_creation"]),
            ("Post-holiday demand drop in January for dairy products",
             "demand_seasonality", {"month": 1, "product_category": "dairy"},
             {"variable": "demand", "direction": "decrease", "multiplier": 0.75, "confidence_interval": [0.65, 0.85]},
             ["forecast_adjustment"]),
        ]

        for summary, ptype, conditions, effect, trms in seasonal_patterns:
            entries.append(ExperientialKnowledge(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                entity_type="product_category",
                entity_ids={"category": conditions.get("product_category", "all")},
                pattern_type=ptype,
                conditions=conditions,
                effect=effect,
                confidence=0.82,
                knowledge_type="GENUINE",
                knowledge_type_rationale="Observed consistent seasonal pattern across 2+ years of order history",
                source_type="transaction_analysis",
                evidence=[{"source": "outbound_order_line", "period": "2024-2025", "sample_size": 500}],
                source_user_ids=[],
                trm_types_affected=trms,
                state_feature_names=[f"ek_{ptype}_{conditions.get('season', conditions.get('month', 'all'))}"],
                reward_shaping_bonus=0.05,
                cdt_uncertainty_multiplier=1.2,
                status="CONFIRMED",
                summary=summary,
                created_at=now,
            ))

        # 2. Vendor lead time variability
        for vendor in vendor_rows[:5]:
            vid, vname = vendor
            entries.append(ExperientialKnowledge(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                entity_type="vendor",
                entity_ids={"vendor_id": str(vid)},
                pattern_type="lead_time_variability",
                conditions={"vendor_id": str(vid), "day_of_week": "friday"},
                effect={"variable": "lead_time", "direction": "increase", "multiplier": 1.3,
                        "additive_days": 1, "confidence_interval": [1.1, 1.5]},
                confidence=0.75,
                knowledge_type="GENUINE",
                knowledge_type_rationale=f"Friday POs to {vname} consistently arrive 1 day later due to weekend cutoff",
                source_type="po_receipt_analysis",
                evidence=[{"source": "goods_receipt", "vendor_id": str(vid), "sample_size": 120}],
                source_user_ids=[],
                trm_types_affected=["po_creation", "order_tracking"],
                state_feature_names=["ek_vendor_lt_risk"],
                reward_shaping_bonus=0.03,
                cdt_uncertainty_multiplier=1.3,
                status="CONFIRMED",
                summary=f"Vendor {vname}: Friday POs arrive ~1 day late (weekend processing delay)",
                created_at=now,
            ))

        # 3. Quality inspection patterns
        for prod in prod_rows[:3]:
            pid, pdesc = prod
            short_name = pdesc.split("[")[0].strip() if "[" in pdesc else pdesc
            entries.append(ExperientialKnowledge(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                entity_type="product",
                entity_ids={"product_id": str(pid)},
                pattern_type="quality_risk",
                conditions={"product_id": str(pid), "temperature_excursion": True},
                effect={"variable": "defect_rate", "direction": "increase", "multiplier": 2.5,
                        "confidence_interval": [1.8, 3.2]},
                confidence=0.88,
                knowledge_type="GENUINE",
                knowledge_type_rationale=f"Temperature excursions during transit double defect rate for {short_name}",
                source_type="quality_analysis",
                evidence=[{"source": "quality_order", "product_id": str(pid), "sample_size": 45}],
                source_user_ids=[],
                trm_types_affected=["quality_disposition", "order_tracking"],
                state_feature_names=["ek_temp_excursion_risk"],
                reward_shaping_bonus=0.04,
                cdt_uncertainty_multiplier=1.5,
                status="CONFIRMED",
                summary=f"{short_name}: temperature excursions double defect rate — inspect immediately on receipt",
                created_at=now,
            ))

        # 4. Rebalancing patterns between regions
        dc_sites = [s for s in site_rows if s[3] in ("INVENTORY", "inventory")]
        if len(dc_sites) >= 2:
            entries.append(ExperientialKnowledge(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                entity_type="site_pair",
                entity_ids={"from_site": str(dc_sites[0][0]), "to_site": str(dc_sites[1][0])},
                pattern_type="rebalancing_pattern",
                conditions={"day_of_week": "monday", "demand_region": "southwest"},
                effect={"variable": "transfer_qty", "direction": "increase", "multiplier": 1.2,
                        "confidence_interval": [1.1, 1.4]},
                confidence=0.70,
                knowledge_type="GENUINE",
                knowledge_type_rationale=f"Monday restocking from {dc_sites[0][1]} to {dc_sites[1][1]} consistently 20% higher due to weekend depletion",
                source_type="transfer_analysis",
                evidence=[{"source": "transfer_order", "sample_size": 80}],
                source_user_ids=[],
                trm_types_affected=["rebalancing", "to_execution"],
                state_feature_names=["ek_monday_restock_boost"],
                reward_shaping_bonus=0.03,
                cdt_uncertainty_multiplier=1.1,
                status="CONFIRMED",
                summary=f"Monday restocking {dc_sites[0][1]} → {dc_sites[1][1]} runs 20% higher (weekend depletion pattern)",
                created_at=now,
            ))

        # 5. Capacity constraint at manufacturing
        mfg_sites = [s for s in site_rows if s[3] in ("MANUFACTURER", "manufacturer")]
        for mfg in mfg_sites[:2]:
            entries.append(ExperientialKnowledge(
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                entity_type="site",
                entity_ids={"site_id": str(mfg[0])},
                pattern_type="capacity_constraint",
                conditions={"site_id": str(mfg[0]), "season": "Q4"},
                effect={"variable": "capacity", "direction": "decrease", "multiplier": 0.85,
                        "confidence_interval": [0.78, 0.92]},
                confidence=0.78,
                knowledge_type="GENUINE",
                knowledge_type_rationale=f"{mfg[1]} operates at 85% effective capacity in Q4 due to maintenance windows",
                source_type="production_analysis",
                evidence=[{"source": "production_orders", "site_id": str(mfg[0]), "sample_size": 60}],
                source_user_ids=[],
                trm_types_affected=["mo_execution", "subcontracting"],
                state_feature_names=["ek_q4_capacity_constraint"],
                reward_shaping_bonus=0.04,
                cdt_uncertainty_multiplier=1.15,
                status="CONFIRMED",
                summary=f"{mfg[1]}: Q4 effective capacity drops to 85% (scheduled maintenance windows)",
                created_at=now,
            ))

        # 6. Compensating knowledge (workaround — not used for reward shaping)
        entries.append(ExperientialKnowledge(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            entity_type="process",
            entity_ids={"process": "po_splitting"},
            pattern_type="order_splitting_workaround",
            conditions={"order_qty_threshold": 500, "single_vendor": True},
            effect={"variable": "order_qty", "direction": "split", "max_per_po": 250},
            confidence=0.65,
            knowledge_type="COMPENSATING",
            knowledge_type_rationale="Planners split POs above 500 units to avoid single-vendor concentration. This is a workaround for missing multi-sourcing policy.",
            source_type="override_analysis",
            evidence=[{"source": "powell_po_decisions", "override_count": 18, "period": "2025-Q3"}],
            source_user_ids=[],
            trm_types_affected=["po_creation"],
            state_feature_names=[],
            reward_shaping_bonus=0.0,  # COMPENSATING: no reward shaping
            cdt_uncertainty_multiplier=1.0,
            status="CONFIRMED",
            summary="Planners split POs above 500 units (workaround for single-vendor risk — root cause: no multi-sourcing policy)",
            created_at=now,
        ))

        # Persist
        for entry in entries:
            self.db.add(entry)
        await self.db.flush()

        logger.info(f"Seeded {len(entries)} Experiential Knowledge entries for config {self.config_id}")
        return len(entries)
