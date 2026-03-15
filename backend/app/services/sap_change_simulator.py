"""
SAP Change Simulator — Extract Once, Simulate Ongoing

Generates realistic supply chain events from extracted SAP baseline data,
triggering Autonomy's existing CDC pipeline without requiring a running
SAP instance. Saves ~$75/day in SAP hosting costs.

Three layers:
  1. Demand Generator — new outbound orders from fitted demand distributions
  2. Supply Event Generator — PO receipts, production completions, inventory moves
  3. CDC Event Emitter — writes to AWS SC tables, fires CDC signals

Architecture:
  Simulator → AWS SC tables → CDCMonitor → OutcomeCollector → CDT → Retraining
"""

import asyncio
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sc_entities import (
    Forecast,
    InboundOrder,
    InboundOrderLine,
    InvLevel,
    OutboundOrderLine,
    Product,
)
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Configuration
# ---------------------------------------------------------------------------

class ClockSpeed(str, Enum):
    REALTIME = "1x"         # 1 sim day = 1 real day
    ACCELERATED = "10x"     # 1 sim day = 2.4 hours
    FAST_FORWARD = "100x"   # 1 sim day = ~15 min
    TURBO = "1000x"         # 1 sim day = ~1.5 min


class DisruptionScenario(str, Enum):
    STEADY_STATE = "steady_state"
    DEMAND_SPIKE = "demand_spike"
    SUPPLIER_DISRUPTION = "supplier_disruption"
    QUALITY_EVENT = "quality_event"
    BULLWHIP = "bullwhip"


CLOCK_MULTIPLIER = {
    ClockSpeed.REALTIME: 1.0,
    ClockSpeed.ACCELERATED: 10.0,
    ClockSpeed.FAST_FORWARD: 100.0,
    ClockSpeed.TURBO: 1000.0,
}


@dataclass
class SimulatorConfig:
    """Configuration for the SAP Change Simulator."""
    config_id: int
    tenant_id: int
    clock_speed: ClockSpeed = ClockSpeed.ACCELERATED
    scenario: DisruptionScenario = DisruptionScenario.STEADY_STATE

    # Demand generation
    orders_per_day: float = 15.0        # Average outbound orders per simulated day
    demand_cv: float = 0.25             # Coefficient of variation for demand
    priority_distribution: Dict[str, float] = field(default_factory=lambda: {
        "VIP": 0.05, "HIGH": 0.15, "STANDARD": 0.65, "LOW": 0.15,
    })

    # Supply generation
    po_receipts_per_day: float = 5.0
    lead_time_mean_days: float = 5.0
    lead_time_cv: float = 0.30
    yield_mean: float = 0.97
    yield_std: float = 0.02

    # Disruption parameters
    spike_multiplier: float = 2.5       # Demand spike: multiply by this
    spike_sku_fraction: float = 0.2     # Fraction of SKUs affected
    disruption_lead_time_multiplier: float = 2.0
    disruption_vendor_fraction: float = 0.15
    quality_yield_drop: float = 0.20
    bullwhip_amplification: float = 1.5


@dataclass
class SimulatorState:
    """Running state of the simulator."""
    is_running: bool = False
    sim_date: date = field(default_factory=date.today)
    start_time: Optional[datetime] = None
    ticks_completed: int = 0
    events_generated: int = 0
    last_tick_time: Optional[datetime] = None

    # Cached baseline data
    products: List[Dict[str, Any]] = field(default_factory=list)
    sites: List[Dict[str, Any]] = field(default_factory=list)
    lanes: List[Dict[str, Any]] = field(default_factory=list)
    demand_baseline: Dict[str, float] = field(default_factory=dict)  # product_id → avg daily demand
    lead_time_baseline: Dict[str, float] = field(default_factory=dict)  # supplier_name → avg lead time


# ---------------------------------------------------------------------------
# SAP Change Simulator Service
# ---------------------------------------------------------------------------

class SAPChangeSimulator:
    """
    Generates realistic supply chain events from extracted SAP baseline data.

    Writes to the same AWS SC tables and triggers the same CDC pipeline as
    a real SAP integration. Autonomy's TRM Hive, GNN, and relearning pipeline
    cannot distinguish simulated events from real ones.
    """

    def __init__(self, db: AsyncSession, config: SimulatorConfig):
        self.db = db
        self.config = config
        self.state = SimulatorState()
        self._order_counter = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> Dict[str, Any]:
        """Load baseline data from DB (previously extracted from SAP)."""
        logger.info(
            "Initializing SAP Change Simulator for config_id=%d, scenario=%s, clock=%s",
            self.config.config_id, self.config.scenario.value, self.config.clock_speed.value,
        )

        # Load products
        result = await self.db.execute(
            select(Product.id, Product.product_name, Product.base_uom, Product.unit_cost)
            .join(Site, Site.config_id == self.config.config_id)
            .join(
                OutboundOrderLine,
                (OutboundOrderLine.product_id == Product.id)
                & (OutboundOrderLine.site_id == Site.id),
            )
            .where(Site.config_id == self.config.config_id)
            .distinct()
        )
        products = result.all()
        if not products:
            # Fallback: get all products linked to config via inv_level
            result = await self.db.execute(
                select(Product.id, Product.product_name, Product.base_uom, Product.unit_cost)
                .join(InvLevel, InvLevel.product_id == Product.id)
                .where(InvLevel.config_id == self.config.config_id)
                .distinct()
            )
            products = result.all()

        self.state.products = [
            {"id": p.id, "name": p.product_name, "uom": p.base_uom, "unit_cost": p.unit_cost or 10.0}
            for p in products
        ]

        # Load sites by master_type
        result = await self.db.execute(
            select(Site.id, Site.name, Site.master_type, Site.dag_type)
            .where(Site.config_id == self.config.config_id)
        )
        all_sites = result.all()
        self.state.sites = [
            {"id": s.id, "name": s.name, "master_type": s.master_type, "dag_type": s.dag_type}
            for s in all_sites
        ]

        # Load lanes
        result = await self.db.execute(
            select(
                TransportationLane.id,
                TransportationLane.from_site_id,
                TransportationLane.to_site_id,
                TransportationLane.capacity,
                TransportationLane.supply_lead_time,
            )
            .where(TransportationLane.config_id == self.config.config_id)
        )
        lanes = result.all()
        self.state.lanes = [
            {
                "id": ln.id,
                "from_site_id": ln.from_site_id,
                "to_site_id": ln.to_site_id,
                "capacity": ln.capacity or 1000,
                "lead_time": _extract_lead_time(ln.supply_lead_time),
            }
            for ln in lanes
        ]

        # Compute demand baseline from existing outbound orders
        result = await self.db.execute(
            select(
                OutboundOrderLine.product_id,
                func.avg(OutboundOrderLine.ordered_quantity).label("avg_qty"),
            )
            .where(OutboundOrderLine.config_id == self.config.config_id)
            .group_by(OutboundOrderLine.product_id)
        )
        for row in result.all():
            self.state.demand_baseline[row.product_id] = float(row.avg_qty or 50.0)

        # Fill in products with no order history
        for p in self.state.products:
            if p["id"] not in self.state.demand_baseline:
                self.state.demand_baseline[p["id"]] = 50.0

        # Compute lead time baseline from lanes
        supply_sites = {s["id"] for s in self.state.sites if s["master_type"] in ("VENDOR", "VENDOR")}
        for ln in self.state.lanes:
            if ln["from_site_id"] in supply_sites:
                site_name = next(
                    (s["name"] for s in self.state.sites if s["id"] == ln["from_site_id"]),
                    str(ln["from_site_id"]),
                )
                self.state.lead_time_baseline[site_name] = ln["lead_time"]

        self.state.sim_date = date.today()
        self.state.start_time = datetime.utcnow()

        summary = {
            "products": len(self.state.products),
            "sites": len(self.state.sites),
            "lanes": len(self.state.lanes),
            "demand_baselines": len(self.state.demand_baseline),
            "lead_time_baselines": len(self.state.lead_time_baseline),
            "scenario": self.config.scenario.value,
            "clock_speed": self.config.clock_speed.value,
        }
        logger.info("SAP Change Simulator initialized: %s", summary)
        return summary

    async def start(self) -> Dict[str, Any]:
        """Start the simulator (must be initialized first)."""
        if not self.state.products:
            await self.initialize()
        self.state.is_running = True
        self.state.start_time = datetime.utcnow()
        logger.info("SAP Change Simulator started")
        return {"status": "running", "sim_date": str(self.state.sim_date)}

    def stop(self) -> Dict[str, Any]:
        """Stop the simulator."""
        self.state.is_running = False
        logger.info(
            "SAP Change Simulator stopped after %d ticks, %d events",
            self.state.ticks_completed, self.state.events_generated,
        )
        return {
            "status": "stopped",
            "ticks_completed": self.state.ticks_completed,
            "events_generated": self.state.events_generated,
            "sim_date": str(self.state.sim_date),
        }

    def get_status(self) -> Dict[str, Any]:
        """Return current simulator status."""
        return {
            "is_running": self.state.is_running,
            "sim_date": str(self.state.sim_date),
            "ticks_completed": self.state.ticks_completed,
            "events_generated": self.state.events_generated,
            "last_tick": str(self.state.last_tick_time) if self.state.last_tick_time else None,
            "config": {
                "config_id": self.config.config_id,
                "scenario": self.config.scenario.value,
                "clock_speed": self.config.clock_speed.value,
                "orders_per_day": self.config.orders_per_day,
            },
        }

    # ------------------------------------------------------------------
    # Core Tick — one simulated day
    # ------------------------------------------------------------------

    async def tick(self) -> Dict[str, Any]:
        """
        Execute one simulated day. Generates demand, supply, and disruption
        events, writes them to AWS SC tables, and advances the sim clock.

        Call this on a schedule matching the clock speed, or manually.
        """
        if not self.state.is_running:
            return {"error": "Simulator not running"}

        tick_events = 0
        tick_start = datetime.utcnow()

        # Layer 1: Demand generation
        demand_count = await self._generate_demand_events()
        tick_events += demand_count

        # Layer 2: Supply events
        supply_count = await self._generate_supply_events()
        tick_events += supply_count

        # Layer 3: Inventory updates
        inv_count = await self._update_inventory_levels()
        tick_events += inv_count

        # Apply disruption scenario modifiers
        disruption_count = await self._apply_disruption_scenario()
        tick_events += disruption_count

        await self.db.commit()

        # Advance simulation clock
        self.state.sim_date += timedelta(days=1)
        self.state.ticks_completed += 1
        self.state.events_generated += tick_events
        self.state.last_tick_time = datetime.utcnow()

        result = {
            "sim_date": str(self.state.sim_date),
            "tick": self.state.ticks_completed,
            "events": tick_events,
            "breakdown": {
                "demand_orders": demand_count,
                "supply_receipts": supply_count,
                "inventory_updates": inv_count,
                "disruption_events": disruption_count,
            },
            "duration_ms": int((datetime.utcnow() - tick_start).total_seconds() * 1000),
        }
        logger.info("Tick %d: %d events on sim_date=%s", self.state.ticks_completed, tick_events, self.state.sim_date)
        return result

    # ------------------------------------------------------------------
    # Layer 1: Demand Generator
    # ------------------------------------------------------------------

    async def _generate_demand_events(self) -> int:
        """Generate new outbound orders (customer demand)."""
        demand_sites = [s for s in self.state.sites if s["master_type"] in ("CUSTOMER", "CUSTOMER")]
        inventory_sites = [s for s in self.state.sites if s["master_type"] == "INVENTORY"]
        if not demand_sites or not inventory_sites or not self.state.products:
            return 0

        # Poisson number of orders per day
        n_orders = np.random.poisson(self.config.orders_per_day)
        count = 0

        for _ in range(n_orders):
            product = random.choice(self.state.products)
            customer = random.choice(demand_sites)
            fulfillment_site = random.choice(inventory_sites)

            # Demand quantity from lognormal fitted to baseline
            base_demand = self.state.demand_baseline.get(product["id"], 50.0)
            sigma = self.config.demand_cv
            mu = math.log(base_demand) - 0.5 * sigma ** 2
            qty = max(1.0, float(np.random.lognormal(mu, sigma)))

            # Priority
            priority = _sample_priority(self.config.priority_distribution)

            # Delivery date: 1-14 days out
            lead_days = random.randint(1, 14)

            self._order_counter += 1
            order_id = f"SIM-OB-{self.state.sim_date:%Y%m%d}-{self._order_counter:06d}"

            order_line = OutboundOrderLine(
                order_id=order_id,
                line_number=1,
                product_id=product["id"],
                site_id=fulfillment_site["id"],
                ordered_quantity=round(qty, 2),
                requested_delivery_date=self.state.sim_date + timedelta(days=lead_days),
                order_date=self.state.sim_date,
                config_id=self.config.config_id,
                status="CONFIRMED",
                priority_code=priority,
                promised_delivery_date=self.state.sim_date + timedelta(days=lead_days),
                market_demand_site_id=customer["id"],
            )
            self.db.add(order_line)
            count += 1

        return count

    # ------------------------------------------------------------------
    # Layer 2: Supply Event Generator
    # ------------------------------------------------------------------

    async def _generate_supply_events(self) -> int:
        """Generate PO receipts and update inbound order statuses."""
        count = 0

        # Find open inbound order lines with delivery dates <= sim_date
        result = await self.db.execute(
            select(InboundOrderLine)
            .join(InboundOrder, InboundOrderLine.order_id == InboundOrder.id)
            .where(
                InboundOrderLine.status.in_(["OPEN", "PARTIALLY_RECEIVED"]),
                InboundOrderLine.promised_delivery_date <= self.state.sim_date,
                InboundOrder.source == "SAP_SIMULATOR",
            )
        )
        due_lines = result.scalars().all()

        for line in due_lines:
            # Apply stochastic yield
            yield_rate = max(0.5, min(1.0, np.random.normal(
                self.config.yield_mean, self.config.yield_std
            )))
            received = round(line.ordered_quantity * yield_rate, 2)

            line.received_quantity = (line.received_quantity or 0.0) + received
            line.actual_receipt_date = self.state.sim_date
            if line.received_quantity >= line.ordered_quantity * 0.95:
                line.status = "RECEIVED"
            else:
                line.status = "PARTIALLY_RECEIVED"
            line.open_quantity = max(0.0, line.ordered_quantity - line.received_quantity)
            count += 1

        # Generate new POs (replenishment)
        n_pos = np.random.poisson(self.config.po_receipts_per_day)
        supply_sites = [s for s in self.state.sites if s["master_type"] in ("VENDOR", "VENDOR")]
        inv_sites = [s for s in self.state.sites if s["master_type"] == "INVENTORY"]

        if supply_sites and inv_sites and self.state.products:
            for _ in range(n_pos):
                product = random.choice(self.state.products)
                supplier = random.choice(supply_sites)
                dest = random.choice(inv_sites)

                base_demand = self.state.demand_baseline.get(product["id"], 50.0)
                order_qty = round(base_demand * random.uniform(3.0, 10.0), 2)

                # Stochastic lead time (lognormal)
                lt_mean = self.state.lead_time_baseline.get(
                    next((s["name"] for s in self.state.sites if s["id"] == supplier["id"]), ""),
                    self.config.lead_time_mean_days,
                )
                lt_sigma = self.config.lead_time_cv
                lt_mu = math.log(lt_mean) - 0.5 * lt_sigma ** 2
                lead_time = max(1.0, float(np.random.lognormal(lt_mu, lt_sigma)))

                self._order_counter += 1
                po_id = f"SIM-PO-{self.state.sim_date:%Y%m%d}-{self._order_counter:06d}"

                inbound_order = InboundOrder(
                    id=po_id,
                    order_type="PURCHASE",
                    supplier_name=next(
                        (s["name"] for s in self.state.sites if s["id"] == supplier["id"]), ""
                    ),
                    ship_from_site_id=supplier["id"],
                    ship_to_site_id=dest["id"],
                    status="CONFIRMED",
                    order_date=self.state.sim_date,
                    requested_delivery_date=self.state.sim_date + timedelta(days=int(lead_time)),
                    promised_delivery_date=self.state.sim_date + timedelta(days=int(lead_time)),
                    total_ordered_qty=order_qty,
                    source="SAP_SIMULATOR",
                    source_event_id=f"SIM-{uuid.uuid4().hex[:8]}",
                    source_update_dttm=datetime.utcnow(),
                )
                self.db.add(inbound_order)

                inbound_line = InboundOrderLine(
                    order_id=po_id,
                    line_number=1,
                    product_id=product["id"],
                    site_id=dest["id"],
                    ordered_quantity=order_qty,
                    requested_delivery_date=self.state.sim_date + timedelta(days=int(lead_time)),
                    promised_delivery_date=self.state.sim_date + timedelta(days=int(lead_time)),
                    status="OPEN",
                    source="SAP_SIMULATOR",
                )
                self.db.add(inbound_line)
                count += 1

        return count

    # ------------------------------------------------------------------
    # Layer 3: Inventory Level Updates
    # ------------------------------------------------------------------

    async def _update_inventory_levels(self) -> int:
        """
        Update inv_level snapshots based on day's demand consumption
        and supply receipts. Writes new InvLevel rows for the sim_date.
        """
        inv_sites = [s for s in self.state.sites if s["master_type"] == "INVENTORY"]
        if not inv_sites or not self.state.products:
            return 0

        count = 0
        for site in inv_sites:
            for product in self.state.products:
                # Get latest inventory
                result = await self.db.execute(
                    select(InvLevel)
                    .where(
                        InvLevel.product_id == product["id"],
                        InvLevel.site_id == site["id"],
                        InvLevel.config_id == self.config.config_id,
                    )
                    .order_by(InvLevel.inventory_date.desc())
                    .limit(1)
                )
                latest = result.scalar_one_or_none()
                if not latest:
                    continue

                on_hand = latest.on_hand_qty or 0.0
                safety = latest.safety_stock_qty or 0.0

                # Demand consumption: sum of today's confirmed orders for this product-site
                result = await self.db.execute(
                    select(func.coalesce(func.sum(OutboundOrderLine.ordered_quantity), 0.0))
                    .where(
                        OutboundOrderLine.product_id == product["id"],
                        OutboundOrderLine.site_id == site["id"],
                        OutboundOrderLine.order_date == self.state.sim_date,
                        OutboundOrderLine.config_id == self.config.config_id,
                    )
                )
                demand_today = float(result.scalar() or 0.0)

                # Supply receipts: sum of received quantities today
                result = await self.db.execute(
                    select(func.coalesce(func.sum(InboundOrderLine.received_quantity), 0.0))
                    .where(
                        InboundOrderLine.product_id == product["id"],
                        InboundOrderLine.site_id == site["id"],
                        InboundOrderLine.actual_receipt_date == self.state.sim_date,
                    )
                )
                receipts_today = float(result.scalar() or 0.0)

                new_on_hand = max(0.0, on_hand - demand_today + receipts_today)
                backorder = max(0.0, demand_today - on_hand - receipts_today)

                new_inv = InvLevel(
                    product_id=product["id"],
                    site_id=site["id"],
                    config_id=self.config.config_id,
                    inventory_date=self.state.sim_date,
                    on_hand_qty=round(new_on_hand, 2),
                    in_transit_qty=latest.in_transit_qty or 0.0,
                    on_order_qty=latest.on_order_qty or 0.0,
                    allocated_qty=round(demand_today, 2),
                    available_qty=round(max(0.0, new_on_hand - safety), 2),
                    backorder_qty=round(backorder, 2),
                    safety_stock_qty=safety,
                    source="SAP_SIMULATOR",
                    source_event_id=f"SIM-INV-{self.state.sim_date:%Y%m%d}",
                    source_update_dttm=datetime.utcnow(),
                )
                self.db.add(new_inv)
                count += 1

        return count

    # ------------------------------------------------------------------
    # Disruption Scenario Modifiers
    # ------------------------------------------------------------------

    async def _apply_disruption_scenario(self) -> int:
        """Apply scenario-specific disruption events."""
        scenario = self.config.scenario
        if scenario == DisruptionScenario.STEADY_STATE:
            return 0

        count = 0

        if scenario == DisruptionScenario.DEMAND_SPIKE:
            count = await self._apply_demand_spike()
        elif scenario == DisruptionScenario.SUPPLIER_DISRUPTION:
            count = await self._apply_supplier_disruption()
        elif scenario == DisruptionScenario.QUALITY_EVENT:
            count = await self._apply_quality_event()
        elif scenario == DisruptionScenario.BULLWHIP:
            count = await self._apply_bullwhip()

        return count

    async def _apply_demand_spike(self) -> int:
        """Inject 2-3x demand surge on a subset of SKUs."""
        n_affected = max(1, int(len(self.state.products) * self.config.spike_sku_fraction))
        affected = random.sample(self.state.products, n_affected)
        demand_sites = [s for s in self.state.sites if s["master_type"] in ("CUSTOMER", "CUSTOMER")]
        inv_sites = [s for s in self.state.sites if s["master_type"] == "INVENTORY"]
        if not demand_sites or not inv_sites:
            return 0

        count = 0
        for product in affected:
            n_extra = np.random.poisson(3)
            for _ in range(n_extra):
                customer = random.choice(demand_sites)
                site = random.choice(inv_sites)
                base = self.state.demand_baseline.get(product["id"], 50.0)
                qty = round(base * self.config.spike_multiplier * random.uniform(0.8, 1.2), 2)

                self._order_counter += 1
                order_id = f"SIM-SPIKE-{self.state.sim_date:%Y%m%d}-{self._order_counter:06d}"

                self.db.add(OutboundOrderLine(
                    order_id=order_id,
                    line_number=1,
                    product_id=product["id"],
                    site_id=site["id"],
                    ordered_quantity=qty,
                    requested_delivery_date=self.state.sim_date + timedelta(days=random.randint(1, 3)),
                    order_date=self.state.sim_date,
                    config_id=self.config.config_id,
                    status="CONFIRMED",
                    priority_code="HIGH",
                    market_demand_site_id=customer["id"],
                ))
                count += 1

        return count

    async def _apply_supplier_disruption(self) -> int:
        """Delay open POs from a subset of suppliers."""
        supply_sites = [s for s in self.state.sites if s["master_type"] in ("VENDOR", "VENDOR")]
        if not supply_sites:
            return 0

        n_affected = max(1, int(len(supply_sites) * self.config.disruption_vendor_fraction))
        affected_ids = {s["id"] for s in random.sample(supply_sites, n_affected)}

        result = await self.db.execute(
            select(InboundOrderLine)
            .join(InboundOrder, InboundOrderLine.order_id == InboundOrder.id)
            .where(
                InboundOrderLine.status == "OPEN",
                InboundOrder.ship_from_site_id.in_(affected_ids),
                InboundOrder.source == "SAP_SIMULATOR",
            )
        )
        open_lines = result.scalars().all()

        count = 0
        for line in open_lines:
            if line.promised_delivery_date:
                delay = timedelta(days=int(
                    self.config.disruption_lead_time_multiplier *
                    random.uniform(2, 7)
                ))
                line.promised_delivery_date = line.promised_delivery_date + delay
                count += 1

        return count

    async def _apply_quality_event(self) -> int:
        """Reduce received quantities on today's receipts (yield drop)."""
        result = await self.db.execute(
            select(InboundOrderLine)
            .where(
                InboundOrderLine.actual_receipt_date == self.state.sim_date,
                InboundOrderLine.status == "RECEIVED",
            )
        )
        received_today = result.scalars().all()

        count = 0
        for line in received_today:
            if random.random() < 0.3:  # 30% of receipts have quality issues
                reduction = line.received_quantity * self.config.quality_yield_drop
                line.received_quantity = max(0.0, line.received_quantity - reduction)
                line.inspection_status = "FAILED"
                line.status = "PARTIALLY_RECEIVED"
                count += 1

        return count

    async def _apply_bullwhip(self) -> int:
        """Amplify demand signals through the network tiers."""
        # Increase order quantities on today's generated orders
        result = await self.db.execute(
            select(OutboundOrderLine)
            .where(
                OutboundOrderLine.order_date == self.state.sim_date,
                OutboundOrderLine.config_id == self.config.config_id,
                OutboundOrderLine.order_id.like("SIM-%"),
            )
        )
        todays_orders = result.scalars().all()

        count = 0
        for order in todays_orders:
            amplified = order.ordered_quantity * self.config.bullwhip_amplification
            noise = amplified * random.uniform(-0.1, 0.3)
            order.ordered_quantity = round(amplified + noise, 2)
            count += 1

        return count


# ---------------------------------------------------------------------------
# Singleton manager for the running simulator
# ---------------------------------------------------------------------------

class SimulatorManager:
    """
    Manages a single running SAP Change Simulator instance.
    Used by the API layer and scheduler to control the simulator.
    """

    _instance: Optional[SAPChangeSimulator] = None
    _config: Optional[SimulatorConfig] = None

    @classmethod
    def get_instance(cls) -> Optional[SAPChangeSimulator]:
        return cls._instance

    @classmethod
    async def create(
        cls, db: AsyncSession, config: SimulatorConfig
    ) -> SAPChangeSimulator:
        if cls._instance and cls._instance.state.is_running:
            cls._instance.stop()
        sim = SAPChangeSimulator(db=db, config=config)
        await sim.initialize()
        cls._instance = sim
        cls._config = config
        return sim

    @classmethod
    def stop(cls) -> Optional[Dict[str, Any]]:
        if cls._instance:
            result = cls._instance.stop()
            cls._instance = None
            cls._config = None
            return result
        return None

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        if cls._instance:
            return cls._instance.get_status()
        return {"is_running": False, "message": "No simulator instance"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_lead_time(lt_json) -> float:
    """Extract lead time days from JSON field."""
    if isinstance(lt_json, dict):
        return float(lt_json.get("mean", lt_json.get("value", 5.0)))
    if isinstance(lt_json, (int, float)):
        return float(lt_json)
    return 5.0


def _sample_priority(distribution: Dict[str, float]) -> str:
    """Sample a priority code from a weighted distribution."""
    codes = list(distribution.keys())
    weights = list(distribution.values())
    return random.choices(codes, weights=weights, k=1)[0]
