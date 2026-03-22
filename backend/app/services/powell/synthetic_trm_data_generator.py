"""
Synthetic TRM Training Data Generator

Generates realistic synthetic transactional data for TRM training:
1. Forecasts - demand forecasts at different hierarchy levels
2. Inventory Levels - historical inventory positions
3. Orders - inbound (PO) and outbound (customer) order history
4. TRM Decision Logs - simulated expert planner decisions with context
5. Outcomes - simulated outcomes after each decision
6. Replay Buffer - (state, action, reward, next_state) tuples for RL training

The generator simulates realistic supply chain operations with:
- Demand variability (seasonal, trending, random)
- Lead time variability
- Supplier reliability issues
- Inventory imbalances
- Order exceptions

Usage:
    generator = SyntheticTRMDataGenerator(db, config_id, tenant_id)
    stats = await generator.generate(
        num_days=365,
        num_orders_per_day=50,
        num_decisions_per_day=20
    )
"""

import logging
import random
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import numpy as np
from enum import Enum

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trm_training_data import (
    ATPDecisionLog,
    ATPOutcome,
    RebalancingDecisionLog,
    RebalancingOutcome,
    PODecisionLog,
    POOutcome,
    OrderTrackingDecisionLog,
    OrderTrackingOutcome,
    SafetyStockDecisionLog,
    SafetyStockOutcome,
    TRMReplayBuffer,
    DecisionSource,
    OutcomeStatus
)

# Deterministic engines - used for expert labels
from app.services.powell.engines.aatp_engine import (
    AATPEngine, AATPConfig, ATPAllocation,
    Order as EngineOrder, Priority as EnginePriority,
)
from app.services.powell.engines.rebalancing_engine import (
    RebalancingEngine, RebalancingConfig,
    SiteState as EngineSiteState, LaneConstraints as EngineLaneConstraints,
)
from app.services.powell.engines.order_tracking_engine import (
    OrderTrackingEngine, OrderTrackingConfig,
    OrderSnapshot,
)
from app.services.powell.engines.buffer_calculator import (
    BufferCalculator, BufferConfig,
    DemandStats, BufferPolicy, PolicyType,
)
from app.models.sc_entities import (
    Forecast,
    InvLevel,
    OutboundOrderLine,
    Product,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.powell_training_config import TRMType, DEFAULT_TRM_REWARD_WEIGHTS
from app.services.sc_planning.stochastic_sampler import StochasticSampler

logger = logging.getLogger(__name__)


class DemandPattern(str, Enum):
    """Demand patterns for simulation"""
    STABLE = "stable"
    SEASONAL = "seasonal"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANDOM = "random"
    STEP_CHANGE = "step_change"
    PROMOTIONAL = "promotional"


@dataclass
class SiteState:
    """Current state of a site for simulation"""
    site_id: int
    site_name: str
    site_type: str
    inventory: Dict[str, float]  # product_id -> qty
    backlog: Dict[str, float]  # product_id -> qty
    pipeline: Dict[str, float]  # product_id -> qty in transit
    pending_orders: int
    last_demand: Dict[str, float]  # product_id -> last demand


@dataclass
class GenerationStats:
    """Statistics from data generation"""
    forecasts_created: int = 0
    inventory_snapshots_created: int = 0
    outbound_orders_created: int = 0
    purchase_orders_created: int = 0
    atp_decisions_created: int = 0
    rebalancing_decisions_created: int = 0
    po_decisions_created: int = 0
    order_tracking_decisions_created: int = 0
    inventory_buffer_decisions_created: int = 0
    replay_buffer_entries_created: int = 0


class SyntheticTRMDataGenerator:
    """
    Generates synthetic transactional data for TRM training.

    Creates a realistic simulation of supply chain operations including
    demand patterns, inventory movements, order creation, and planner decisions.
    """

    def __init__(
        self,
        db: AsyncSession,
        config_id: int,
        tenant_id: int,
        seed: Optional[int] = None,
        signal_bus=None,
        phase: int = 2,
    ):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self.signal_bus = signal_bus  # Optional HiveSignalBus for signal-enriched data
        self.phase = phase  # Curriculum phase (1=low variance, 2=moderate, 3=high)

        # Set random seed for reproducibility
        if seed:
            random.seed(seed)
            np.random.seed(seed)

        # Stochastic sampler for distribution-based sampling
        self.stochastic_sampler = StochasticSampler(scenario_id=tenant_id)

        # Will be loaded
        self.sc_config: Optional[SupplyChainConfig] = None
        self.sites: List[Site] = []
        self.lanes: List[TransportationLane] = []
        self.products: List[str] = []  # product IDs
        self.company_id: str = f"UF_CORP_{tenant_id}"  # Default company ID format

        # Simulation state
        self.site_states: Dict[int, SiteState] = {}
        self.current_date: date = date.today() - timedelta(days=365)

        # Statistics
        self.stats = GenerationStats()

        # Configuration
        self.demand_patterns = {
            DemandPattern.STABLE: 0.2,
            DemandPattern.SEASONAL: 0.25,
            DemandPattern.TRENDING_UP: 0.15,
            DemandPattern.TRENDING_DOWN: 0.1,
            DemandPattern.RANDOM: 0.15,
            DemandPattern.STEP_CHANGE: 0.1,
            DemandPattern.PROMOTIONAL: 0.05
        }

        # Decision source distribution (how decisions are made)
        self.decision_source_weights = {
            DecisionSource.EXPERT_HUMAN: 0.4,
            DecisionSource.AI_ACCEPTED: 0.25,
            DecisionSource.AI_MODIFIED: 0.15,
            DecisionSource.AI_REJECTED: 0.1,
            DecisionSource.AI_AUTONOMOUS: 0.1
        }

        # Phase-aware variance multipliers (curriculum progression)
        self._phase_variance_map = {1: 0.15, 2: 0.40, 3: 0.75}

        # Deterministic engines for expert labels
        self.aatp_engine = AATPEngine()
        self.rebalancing_engine = RebalancingEngine()
        self.order_tracking_engine = OrderTrackingEngine()
        self.ss_calculator = BufferCalculator()

    def _phase_variance(self, phase: Optional[int] = None) -> float:
        """Return variance multiplier based on curriculum phase.

        Phase 1: low uncertainty (0.15) — simple, clear-signal scenarios
        Phase 2: moderate uncertainty (0.40) — trade-offs, variability
        Phase 3: high uncertainty (0.75) — disruptions, edge cases

        Args:
            phase: Curriculum phase (1-3). Defaults to self.phase.

        Returns:
            Variance multiplier as a fraction of the mean.
        """
        p = phase if phase is not None else self.phase
        return self._phase_variance_map.get(p, 0.40)

    def _make_dist_config(self, dist_type: str, mean: float, variance_pct: Optional[float] = None) -> dict:
        """Create a distribution config dict compatible with StochasticSampler.

        Args:
            dist_type: Distribution type ('normal', 'lognormal', 'triangular', etc.)
            mean: Mean value.
            variance_pct: Std-dev as fraction of mean. If None, uses phase variance.

        Returns:
            Dict suitable for StochasticSampler.sample_from_distribution().
        """
        pct = variance_pct if variance_pct is not None else self._phase_variance()
        std = abs(mean) * pct
        if dist_type == "triangular":
            # Triangular: mode=mean, low=mean-2*std, high=mean+2*std
            return {
                "type": "triangular",
                "low": max(0, mean - 2 * std),
                "mode": mean,
                "high": mean + 2 * std,
            }
        # Default: normal-family distribution
        return {"type": dist_type, "mean": mean, "stddev": std}

    async def load_config(self):
        """Load supply chain configuration from database."""
        # Load SC config
        result = await self.db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.id == self.config_id)
        )
        self.sc_config = result.scalar_one_or_none()
        if not self.sc_config:
            raise ValueError(f"Supply chain config {self.config_id} not found")

        # Load sites
        result = await self.db.execute(
            select(Site).where(Site.config_id == self.config_id)
        )
        self.sites = list(result.scalars().all())

        # Load lanes
        result = await self.db.execute(
            select(TransportationLane).where(TransportationLane.config_id == self.config_id)
        )
        self.lanes = list(result.scalars().all())

        # Load products
        result = await self.db.execute(
            select(Product).where(Product.config_id == self.config_id)
        )
        products_from_db = list(result.scalars().all())

        if products_from_db:
            self.products = [p.id for p in products_from_db]
        else:
            # Generate synthetic product IDs if none defined
            self.products = [f"PROD-{i:03d}" for i in range(min(10, max(5, len(self.sites))))]

        logger.info(f"Loaded config: {self.sc_config.name}")
        logger.info(f"Sites: {len(self.sites)}, Lanes: {len(self.lanes)}, Products: {len(self.products)}")

    def _initialize_site_states(self):
        """Initialize site states for simulation."""
        for site in self.sites:
            initial_inventory = {}
            initial_backlog = {}
            initial_pipeline = {}
            last_demand = {}

            for product_id in self.products:
                # Random initial inventory based on site type
                base_inv = random.uniform(50, 200)
                if site.master_type == "MANUFACTURER":
                    base_inv *= 1.5
                elif site.master_type in ("CUSTOMER", "CUSTOMER"):
                    base_inv *= 0.3

                initial_inventory[product_id] = base_inv
                initial_backlog[product_id] = random.uniform(0, 10)
                initial_pipeline[product_id] = random.uniform(20, 60)
                last_demand[product_id] = random.uniform(20, 50)

            self.site_states[site.id] = SiteState(
                site_id=site.id,
                site_name=site.name,
                site_type=site.master_type or "INVENTORY",
                inventory=initial_inventory,
                backlog=initial_backlog,
                pipeline=initial_pipeline,
                pending_orders=random.randint(5, 20),
                last_demand=last_demand
            )

    async def generate(
        self,
        num_days: int = 365,
        num_orders_per_day: int = 50,
        num_decisions_per_day: int = 20,
        batch_size: int = 100
    ) -> GenerationStats:
        """
        Generate synthetic training data.

        Args:
            num_days: Number of days to simulate
            num_orders_per_day: Average number of orders per day
            num_decisions_per_day: Average number of TRM decisions per day
            batch_size: Number of records to batch before committing

        Returns:
            GenerationStats with counts of generated records
        """
        await self.load_config()
        self._initialize_site_states()

        logger.info(f"Generating {num_days} days of synthetic data...")

        start_date = date.today() - timedelta(days=num_days)

        records_pending = 0

        for day_offset in range(num_days):
            self.current_date = start_date + timedelta(days=day_offset)

            # Generate daily transactional data
            await self._generate_daily_forecasts()
            await self._generate_daily_inventory_snapshots()
            await self._generate_daily_orders(num_orders_per_day)
            await self._generate_daily_decisions(num_decisions_per_day)

            # Update site states for next day
            self._simulate_day_end()

            records_pending += 1

            # Batch commit
            if records_pending >= batch_size:
                await self.db.commit()
                records_pending = 0

                if (day_offset + 1) % 30 == 0:
                    logger.info(f"Generated {day_offset + 1}/{num_days} days")

        # Final commit
        await self.db.commit()

        logger.info(f"Data generation complete: {self.stats}")
        return self.stats

    async def _generate_daily_forecasts(self):
        """Generate daily forecast records."""
        for site in self.sites:
            if site.master_type in ("VENDOR", "VENDOR"):
                continue  # Vendors don't have demand forecasts

            for product_id in self.products:
                # Generate forecast with P10/P50/P90
                base_demand = self._generate_demand(site.id, product_id)
                # Phase-scaled variance: phase 1 = tight, phase 3 = wide
                variance_pct = self._phase_variance()
                dist_config = self._make_dist_config("normal", base_demand, variance_pct)
                std_dev = dist_config["stddev"]

                forecast = Forecast(
                    company_id=self.company_id,
                    product_id=product_id,
                    site_id=site.id,
                    forecast_date=self.current_date,
                    forecast_type="statistical",
                    forecast_level="product",
                    forecast_method="ml",
                    forecast_quantity=base_demand,
                    forecast_p10=max(0, base_demand - 1.28 * std_dev),
                    forecast_p50=base_demand,
                    forecast_p90=base_demand + 1.28 * std_dev,
                    forecast_std_dev=std_dev,
                    forecast_confidence=random.uniform(0.7, 0.95),
                    config_id=self.config_id,
                    is_active="true"
                )
                self.db.add(forecast)
                self.stats.forecasts_created += 1

    async def _generate_daily_inventory_snapshots(self):
        """Generate daily inventory level snapshots."""
        for site in self.sites:
            state = self.site_states[site.id]

            for product_id in self.products:
                on_hand = state.inventory.get(product_id, 0)
                in_transit = state.pipeline.get(product_id, 0)
                allocated = random.uniform(0, on_hand * 0.3)

                inv_level = InvLevel(
                    company_id=self.company_id,
                    product_id=product_id,
                    site_id=site.id,
                    inventory_date=self.current_date,
                    on_hand_qty=on_hand,
                    in_transit_qty=in_transit,
                    on_order_qty=state.pipeline.get(product_id, 0),
                    allocated_qty=allocated,
                    available_qty=max(0, on_hand - allocated),
                    reserved_qty=0,
                    config_id=self.config_id
                )
                self.db.add(inv_level)
                self.stats.inventory_snapshots_created += 1

    async def _generate_daily_orders(self, num_orders: int):
        """Generate daily customer orders and purchase orders."""
        # Skip OutboundOrderLine creation - schema mismatch between items and product tables
        # The TRM decision data is generated separately and doesn't depend on these orders
        # TODO: Fix when items/product schema is consolidated
        logger.debug(f"Skipping outbound order creation (schema migration pending)")

        # Purchase orders (inbound)
        num_po = int(num_orders * random.uniform(0.1, 0.2))
        for i in range(num_po):
            # Find supplier and destination sites
            inventory_sites = [s for s in self.sites if s.master_type in ["INVENTORY", "MANUFACTURER"]]
            supplier_sites = [s for s in self.sites if s.master_type in ("VENDOR", "VENDOR")]

            if not inventory_sites or not supplier_sites:
                continue

            dest_site = random.choice(inventory_sites)
            supplier_site = random.choice(supplier_sites)

            po_number = f"PO-{self.current_date.strftime('%Y%m%d')}-{i:04d}"

            # Sample lead time from stochastic distribution (phase-aware)
            lt_mean = 12.0  # midpoint of original 3-21 range
            lt_config = self._make_dist_config("normal", lt_mean)
            sampled_lt = self.stochastic_sampler.sample_from_distribution(lt_config, lt_mean)
            po_lead_time_days = max(1, int(round(sampled_lt)))

            po = PurchaseOrder(
                po_number=po_number,
                supplier_site_id=supplier_site.id,
                destination_site_id=dest_site.id,
                config_id=self.config_id,
                tenant_id=self.tenant_id,
                company_id=self.company_id,
                order_type="po",
                status="APPROVED",
                order_date=self.current_date,
                requested_delivery_date=self.current_date + timedelta(days=po_lead_time_days),
                total_amount=random.uniform(1000, 50000)
            )
            self.db.add(po)
            self.stats.purchase_orders_created += 1

    async def _generate_daily_decisions(self, num_decisions: int):
        """Generate daily TRM decisions with outcomes and replay buffer entries."""
        # Distribute decisions across TRM types
        decision_distribution = {
            TRMType.ATP_EXECUTOR: 0.35,
            TRMType.REBALANCING: 0.15,
            TRMType.PO_CREATION: 0.20,
            TRMType.ORDER_TRACKING: 0.15,
            TRMType.SAFETY_STOCK: 0.15,
        }

        for trm_type, ratio in decision_distribution.items():
            type_decisions = int(num_decisions * ratio)

            for _ in range(type_decisions):
                if trm_type == TRMType.ATP_EXECUTOR:
                    await self._generate_atp_decision()
                elif trm_type == TRMType.REBALANCING:
                    await self._generate_rebalancing_decision()
                elif trm_type == TRMType.PO_CREATION:
                    await self._generate_po_decision()
                elif trm_type == TRMType.ORDER_TRACKING:
                    await self._generate_order_tracking_decision()
                elif trm_type == TRMType.SAFETY_STOCK:
                    await self._generate_inventory_buffer_decision()

    async def _generate_atp_decision(self):
        """Generate an ATP decision using AATP engine for expert labels."""
        site = random.choice([s for s in self.sites if s.master_type not in ("VENDOR", "VENDOR")])
        state = self.site_states[site.id]
        product_id = random.choice(self.products)

        # State features
        inventory = state.inventory.get(product_id, 50)
        pipeline = state.pipeline.get(product_id, 30)
        backlog = state.backlog.get(product_id, 5)
        demand_forecast = state.last_demand.get(product_id, 40)

        requested_qty = random.uniform(10, 80)
        priority = random.randint(1, 5)
        available_atp = max(0, inventory + pipeline - backlog)

        # Use AATP engine for expert decision
        from datetime import date as date_type
        engine_order = EngineOrder(
            order_id=f"ORD-{random.randint(10000, 99999)}",
            product_id=product_id,
            location_id=str(site.id),
            requested_qty=requested_qty,
            requested_date=date_type.today(),
            priority=EnginePriority.from_value(priority),
            tenant_id=f"CUST-{random.randint(100, 999)}",
        )
        # Set up allocations for the engine
        allocation = ATPAllocation(
            product_id=product_id,
            location_id=str(site.id),
            priority=EnginePriority.from_value(priority),
            allocated_qty=available_atp,
            period_start=date_type.today(),
            period_end=date_type.today() + timedelta(days=7),
        )
        self.aatp_engine.load_allocations([allocation])
        engine_result = self.aatp_engine.check_availability(engine_order)

        if engine_result.can_fulfill_full:
            action_type = "fulfill"
            qty_fulfilled = requested_qty
            qty_backordered = 0
        elif engine_result.available_qty > 0:
            action_type = "partial"
            qty_fulfilled = engine_result.available_qty
            qty_backordered = engine_result.shortage_qty
        else:
            action_type = random.choice(["defer", "reject"])
            qty_fulfilled = 0
            qty_backordered = requested_qty if action_type == "defer" else 0

        source = self._random_decision_source()

        # Create decision log
        decision = ATPDecisionLog(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            product_id=self.products.index(product_id),
            decision_date=self.current_date,
            order_id=f"ORD-{random.randint(10000, 99999)}",
            tenant_id=f"CUST-{random.randint(100, 999)}",
            requested_qty=requested_qty,
            requested_date=self.current_date + timedelta(days=random.randint(1, 7)),
            priority=priority,
            state_inventory=inventory,
            state_pipeline=pipeline,
            state_backlog=backlog,
            state_allocated=random.uniform(0, inventory * 0.3),
            state_available_atp=available_atp,
            state_demand_forecast=demand_forecast,
            state_other_orders_pending=state.pending_orders,
            state_features={"day_of_week": self.current_date.weekday()},
            action_type=action_type,
            action_qty_fulfilled=qty_fulfilled,
            action_qty_backordered=qty_backordered,
            action_promise_date=self.current_date + timedelta(days=random.randint(1, 7)),
            action_allocation_tier=priority,
            action_reason=f"Expert decision: {action_type} based on ATP={available_atp:.1f}",
            source=source,
            ai_confidence=random.uniform(0.7, 0.95) if source != DecisionSource.EXPERT_HUMAN else None
        )
        self.db.add(decision)
        await self.db.flush()  # Get decision ID
        self.stats.atp_decisions_created += 1

        # Generate outcome (simulated)
        on_time = random.random() < 0.85 if action_type == "fulfill" else random.random() < 0.5
        in_full = qty_fulfilled >= requested_qty
        fill_rate = qty_fulfilled / requested_qty if requested_qty > 0 else 0

        # Calculate reward
        reward_weights = DEFAULT_TRM_REWARD_WEIGHTS[TRMType.ATP_EXECUTOR]
        reward = (
            reward_weights["fill_rate"] * fill_rate +
            reward_weights["on_time_bonus"] * (1.0 if on_time else 0.0) +
            reward_weights["priority_weight"] * (6 - priority) / 5 +
            reward_weights["fairness_penalty"] * (1.0 if fill_rate > 0.5 else 0.5)
        )

        outcome = ATPOutcome(
            decision_id=decision.id,
            status=OutcomeStatus.MEASURED,
            measured_at=datetime.utcnow(),
            actual_qty_shipped=qty_fulfilled,
            actual_ship_date=self.current_date + timedelta(days=random.randint(0, 3)),
            on_time=on_time,
            in_full=in_full,
            otif=on_time and in_full,
            days_late=0 if on_time else random.randint(1, 5),
            fill_rate=fill_rate,
            customer_satisfaction_impact=fill_rate - 0.5,
            revenue_impact=qty_fulfilled * random.uniform(10, 50),
            cost_impact=random.uniform(0, 100) if not on_time else 0,
            reward=reward,
            reward_components={
                "fill_rate": fill_rate,
                "on_time": on_time,
                "priority_weighted": (6 - priority) / 5
            },
            next_state_inventory=inventory - qty_fulfilled,
            next_state_backlog=backlog + qty_backordered
        )
        self.db.add(outcome)

        # Create replay buffer entry
        state_vector = [
            inventory / 200, pipeline / 100, backlog / 50,
            available_atp / 200, demand_forecast / 100,
            requested_qty / 100, priority / 5,
            state.pending_orders / 50
        ]
        next_state_vector = [
            (inventory - qty_fulfilled) / 200, pipeline / 100,
            (backlog + qty_backordered) / 50, (available_atp - qty_fulfilled) / 200,
            demand_forecast / 100, 0, 0, (state.pending_orders - 1) / 50
        ]

        # Action: 0=fulfill, 1=partial, 2=defer, 3=reject
        action_map = {"fulfill": 0, "partial": 1, "defer": 2, "reject": 3}

        is_expert = source == DecisionSource.EXPERT_HUMAN
        replay_entry = TRMReplayBuffer(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            trm_type=TRMType.ATP_EXECUTOR.value,
            decision_log_id=decision.id,
            decision_log_table="trm_atp_decision_log",
            state_vector=state_vector,
            state_dim=len(state_vector),
            action_discrete=action_map.get(action_type, 0),
            action_dim=1,
            reward=reward,
            reward_components={"fill_rate": fill_rate, "on_time": float(on_time)},
            next_state_vector=next_state_vector,
            done=False,
            is_expert=is_expert,
            override_effectiveness=self._synthetic_override_effectiveness() if is_expert else None,
            priority=1.0 + abs(reward),  # Higher reward = higher priority
            transition_date=self.current_date
        )
        self.db.add(replay_entry)
        self.stats.replay_buffer_entries_created += 1

    async def _generate_rebalancing_decision(self):
        """Generate a rebalancing decision using engine for expert labels."""
        if len(self.sites) < 2:
            return

        # Find sites with inventory imbalance
        inventory_sites = [s for s in self.sites if s.master_type in ["INVENTORY", "MANUFACTURER"]]
        if len(inventory_sites) < 2:
            return

        from_site = random.choice(inventory_sites)
        to_site = random.choice([s for s in inventory_sites if s.id != from_site.id])
        product_id = random.choice(self.products)

        from_state = self.site_states[from_site.id]
        to_state = self.site_states[to_site.id]

        from_inv = from_state.inventory.get(product_id, 50)
        to_inv = to_state.inventory.get(product_id, 50)

        # Build state
        site_inventories = {s.id: self.site_states[s.id].inventory.get(product_id, 50)
                          for s in inventory_sites}
        site_backlogs = {s.id: self.site_states[s.id].backlog.get(product_id, 0)
                        for s in inventory_sites}
        site_demands = {s.id: self.site_states[s.id].last_demand.get(product_id, 30)
                       for s in inventory_sites}

        avg_inv = np.mean(list(site_inventories.values()))
        network_imbalance = np.std(list(site_inventories.values())) / (avg_inv + 1e-6)

        # Use rebalancing engine for expert decision
        from_demand = from_state.last_demand.get(product_id, 30)
        to_demand = to_state.last_demand.get(product_id, 30)
        from_safety = from_demand * 1.5
        to_safety = to_demand * 1.5
        from_daily = from_demand / 7 if from_demand > 0 else 1e-6
        to_daily = to_demand / 7 if to_demand > 0 else 1e-6
        target_dos = 14.0

        engine_from = EngineSiteState(
            site_id=str(from_site.id),
            available=from_inv,
            safety_stock=from_safety,
            days_of_supply=from_inv / from_daily if from_daily > 0 else 999,
            target_dos=target_dos,
            stockout_risk=max(0, min(1, 1 - from_inv / (from_safety + 1e-6))),
            demand_forecast=from_demand,
        )
        engine_to = EngineSiteState(
            site_id=str(to_site.id),
            available=to_inv,
            safety_stock=to_safety,
            days_of_supply=to_inv / to_daily if to_daily > 0 else 999,
            target_dos=target_dos,
            stockout_risk=max(0, min(1, 1 - to_inv / (to_safety + 1e-6))),
            demand_forecast=to_demand,
        )
        # Sample transit time from stochastic distribution (phase-aware)
        transit_mean = 3.0  # midpoint of original 1-5 range
        transit_config = self._make_dist_config("normal", transit_mean)
        sampled_transit = max(0.5, self.stochastic_sampler.sample_from_distribution(transit_config, transit_mean))

        engine_lane = EngineLaneConstraints(
            from_site=str(from_site.id),
            to_site=str(to_site.id),
            transfer_time=sampled_transit,
            cost_per_unit=random.uniform(0.5, 2.0),
        )

        engine_result = self.rebalancing_engine.evaluate_pair(engine_from, engine_to, engine_lane)

        if engine_result is not None and engine_result.quantity > 0:
            action_type = "transfer"
            transfer_qty = engine_result.quantity
        elif network_imbalance > 0.4:
            action_type = "transfer"
            transfer_qty = random.uniform(10, 30)
        else:
            action_type = "hold"
            transfer_qty = 0

        source = self._random_decision_source()

        decision = RebalancingDecisionLog(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            product_id=self.products.index(product_id),
            decision_date=self.current_date,
            state_site_inventories=site_inventories,
            state_site_backlogs=site_backlogs,
            state_site_demands=site_demands,
            state_transit_matrix={},
            state_network_imbalance=network_imbalance,
            state_features={"num_sites": len(inventory_sites)},
            action_type=action_type,
            action_from_site_id=from_site.id if action_type == "transfer" else None,
            action_to_site_id=to_site.id if action_type == "transfer" else None,
            action_qty=transfer_qty,
            action_urgency="normal",
            action_reason=f"Network imbalance: {network_imbalance:.2f}",
            source=source,
            ai_confidence=random.uniform(0.7, 0.95) if source != DecisionSource.EXPERT_HUMAN else None
        )
        self.db.add(decision)
        await self.db.flush()
        self.stats.rebalancing_decisions_created += 1

        # Outcome
        transfer_completed = random.random() < 0.9 if action_type == "transfer" else True
        stockout_prevented = random.random() < 0.7 if action_type == "transfer" else random.random() < 0.3

        service_before = random.uniform(0.8, 0.95)
        service_after = service_before + (0.05 if stockout_prevented else -0.02)

        reward_weights = DEFAULT_TRM_REWARD_WEIGHTS[TRMType.REBALANCING]
        reward = (
            reward_weights["service_improvement"] * (service_after - service_before) * 10 +
            reward_weights["transfer_cost_penalty"] * (-transfer_qty / 100 if action_type == "transfer" else 0) +
            reward_weights["balance_improvement"] * (0.5 if stockout_prevented else 0)
        )

        outcome = RebalancingOutcome(
            decision_id=decision.id,
            status=OutcomeStatus.MEASURED,
            measured_at=datetime.utcnow(),
            actual_transfer_qty=transfer_qty if transfer_completed else 0,
            actual_arrival_date=self.current_date + timedelta(days=random.randint(1, 5)),
            transfer_completed=transfer_completed,
            from_site_stockout_prevented=stockout_prevented,
            to_site_stockout_prevented=stockout_prevented,
            service_level_before=service_before,
            service_level_after=service_after,
            transfer_cost=transfer_qty * random.uniform(0.5, 2) if action_type == "transfer" else 0,
            holding_cost_delta=random.uniform(-10, 10),
            reward=reward,
            reward_components={
                "service_improvement": service_after - service_before,
                "transfer_cost": transfer_qty * 0.5
            },
            next_state_site_inventories={
                from_site.id: from_inv - transfer_qty,
                to_site.id: to_inv + transfer_qty
            },
            next_state_network_imbalance=network_imbalance * 0.9
        )
        self.db.add(outcome)

        # Replay buffer
        state_vector = [
            from_inv / 200, to_inv / 200, network_imbalance,
            from_state.backlog.get(product_id, 0) / 50,
            to_state.backlog.get(product_id, 0) / 50,
            avg_inv / 200
        ]
        next_state_vector = [
            (from_inv - transfer_qty) / 200, (to_inv + transfer_qty) / 200,
            network_imbalance * 0.9,
            from_state.backlog.get(product_id, 0) / 50,
            to_state.backlog.get(product_id, 0) / 50,
            avg_inv / 200
        ]

        action_map = {"transfer": 1, "hold": 0, "expedite": 2}

        is_expert = source == DecisionSource.EXPERT_HUMAN
        replay_entry = TRMReplayBuffer(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=from_site.id,
            trm_type=TRMType.REBALANCING.value,
            decision_log_id=decision.id,
            decision_log_table="trm_rebalancing_decision_log",
            state_vector=state_vector,
            state_dim=len(state_vector),
            action_discrete=action_map.get(action_type, 0),
            action_continuous=[transfer_qty / 100],
            action_dim=2,
            reward=reward,
            reward_components={"service_improvement": service_after - service_before},
            next_state_vector=next_state_vector,
            done=False,
            is_expert=is_expert,
            override_effectiveness=self._synthetic_override_effectiveness() if is_expert else None,
            priority=1.0 + abs(reward),
            transition_date=self.current_date
        )
        self.db.add(replay_entry)
        self.stats.replay_buffer_entries_created += 1

    async def _generate_po_decision(self):
        """Generate a PO creation decision using SS calculator for expert labels."""
        inventory_sites = [s for s in self.sites if s.master_type in ["INVENTORY", "MANUFACTURER"]]
        if not inventory_sites:
            return

        site = random.choice(inventory_sites)
        state = self.site_states[site.id]
        product_id = random.choice(self.products)

        inventory = state.inventory.get(product_id, 50)
        pipeline = state.pipeline.get(product_id, 30)
        backlog = state.backlog.get(product_id, 5)
        demand_forecast = state.last_demand.get(product_id, 40)

        # Use safety stock calculator for ROP-based expert decision
        # Sample supplier lead time from stochastic distribution (phase-aware)
        lt_mean = 13.0  # midpoint of original 5-21 range
        lt_config = self._make_dist_config("normal", lt_mean)
        sampled_supplier_lt = max(1.0, self.stochastic_sampler.sample_from_distribution(lt_config, lt_mean))
        # Lead time std also phase-scaled
        lt_std_config = self._make_dist_config("normal", 2.0)
        sampled_lt_std = max(0.1, self.stochastic_sampler.sample_from_distribution(lt_std_config, 2.0))

        demand_stats = DemandStats(
            avg_daily_demand=demand_forecast / 7 if demand_forecast > 0 else 5.0,
            std_daily_demand=demand_forecast * 0.2 / 7,
            avg_lead_time=sampled_supplier_lt,
            std_lead_time=sampled_lt_std,
        )
        ss_policy = SSPolicy(
            policy_type=PolicyType.SERVICE_LEVEL,
            service_level=0.95,
        )
        ss_result = self.ss_calculator.compute_safety_stock(demand_stats, ss_policy)
        safety_stock = ss_result.safety_stock
        reorder_point = ss_result.reorder_point
        days_of_supply = inventory / (demand_stats.avg_daily_demand + 1e-6)

        # Decision logic using engine-computed ROP
        if inventory + pipeline < reorder_point:
            action_type = "order"
            # Order-up-to level from engine
            order_up_to = reorder_point + safety_stock
            order_qty = max(0, order_up_to - inventory - pipeline)
            if inventory < safety_stock * 0.5:
                action_type = "expedite"
        else:
            action_type = "defer"
            order_qty = 0

        supplier_lead_time = demand_stats.avg_lead_time
        supplier_reliability = random.uniform(0.7, 0.98)

        source = self._random_decision_source()

        decision = PODecisionLog(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            product_id=self.products.index(product_id),
            supplier_id=random.randint(1, 5),
            decision_date=self.current_date,
            state_inventory=inventory,
            state_pipeline=pipeline,
            state_backlog=backlog,
            state_reorder_point=reorder_point,
            state_safety_stock=safety_stock,
            state_days_of_supply=days_of_supply,
            state_demand_forecast=[demand_forecast] * 4,
            state_demand_variability=random.uniform(0.1, 0.3),
            state_supplier_lead_time=supplier_lead_time,
            state_supplier_reliability=supplier_reliability,
            state_features={"week_of_year": self.current_date.isocalendar()[1]},
            action_type=action_type,
            action_order_qty=order_qty,
            action_requested_date=self.current_date + timedelta(days=int(supplier_lead_time)),
            action_expedite=action_type == "expedite",
            action_reason=f"DOS={days_of_supply:.1f}, ROP={reorder_point:.1f}",
            po_number=f"PO-{self.current_date.strftime('%Y%m%d')}-{random.randint(1000, 9999)}" if action_type != "defer" else None,
            po_unit_cost=random.uniform(5, 50),
            source=source,
            ai_confidence=random.uniform(0.7, 0.95) if source != DecisionSource.EXPERT_HUMAN else None
        )
        self.db.add(decision)
        await self.db.flush()
        self.stats.po_decisions_created += 1

        # Outcome
        lead_time_actual = int(supplier_lead_time * random.uniform(0.8, 1.3))
        receipt_qty = order_qty * random.uniform(0.95, 1.0) if action_type != "defer" else 0
        stockout_occurred = random.random() < 0.2 if action_type == "defer" else random.random() < 0.05

        reward_weights = DEFAULT_TRM_REWARD_WEIGHTS[TRMType.PO_CREATION]
        reward = (
            reward_weights["stockout_penalty"] * (-1.0 if stockout_occurred else 0.5) +
            reward_weights["dos_target_reward"] * min(1.0, days_of_supply / 14) +
            reward_weights["cost_efficiency"] * (1.0 - order_qty / 500 if order_qty > 0 else 0.5) +
            reward_weights["timing_accuracy"] * (1.0 if abs(lead_time_actual - supplier_lead_time) < 3 else 0.5)
        )

        outcome = POOutcome(
            decision_id=decision.id,
            status=OutcomeStatus.MEASURED,
            measured_at=datetime.utcnow(),
            actual_receipt_qty=receipt_qty,
            actual_receipt_date=self.current_date + timedelta(days=lead_time_actual),
            lead_time_actual=lead_time_actual,
            stockout_occurred=stockout_occurred,
            stockout_days=random.randint(1, 5) if stockout_occurred else 0,
            excess_inventory_cost=max(0, (inventory + receipt_qty - reorder_point) * 0.1),
            expedite_cost=random.uniform(50, 200) if action_type == "expedite" else 0,
            dos_at_receipt=(inventory + receipt_qty) / (demand_forecast + 1e-6) * 7,
            reward=reward,
            reward_components={
                "stockout": -1.0 if stockout_occurred else 0,
                "dos": days_of_supply,
                "cost": order_qty * 0.1 if order_qty > 0 else 0
            },
            next_state_inventory=inventory + receipt_qty,
            next_state_days_of_supply=(inventory + receipt_qty) / (demand_forecast + 1e-6) * 7
        )
        self.db.add(outcome)

        # Replay buffer
        state_vector = [
            inventory / 200, pipeline / 100, backlog / 50,
            reorder_point / 200, safety_stock / 100,
            days_of_supply / 30, demand_forecast / 100,
            supplier_lead_time / 30, supplier_reliability
        ]
        next_state_vector = [
            (inventory + receipt_qty) / 200, (pipeline + order_qty) / 100, backlog / 50,
            reorder_point / 200, safety_stock / 100,
            (inventory + receipt_qty) / (demand_forecast + 1e-6) * 7 / 30,
            demand_forecast / 100, supplier_lead_time / 30, supplier_reliability
        ]

        action_map = {"order": 1, "defer": 0, "expedite": 2, "cancel": 3}

        is_expert = source == DecisionSource.EXPERT_HUMAN
        replay_entry = TRMReplayBuffer(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            trm_type=TRMType.PO_CREATION.value,
            decision_log_id=decision.id,
            decision_log_table="trm_po_decision_log",
            state_vector=state_vector,
            state_dim=len(state_vector),
            action_discrete=action_map.get(action_type, 0),
            action_continuous=[order_qty / 500],
            action_dim=2,
            reward=reward,
            reward_components={"stockout": float(stockout_occurred), "dos": days_of_supply},
            next_state_vector=next_state_vector,
            done=False,
            is_expert=is_expert,
            override_effectiveness=self._synthetic_override_effectiveness() if is_expert else None,
            priority=1.0 + abs(reward),
            transition_date=self.current_date
        )
        self.db.add(replay_entry)
        self.stats.replay_buffer_entries_created += 1

    async def _generate_order_tracking_decision(self):
        """Generate an order tracking decision using engine for expert labels."""
        site = random.choice(self.sites)
        state = self.site_states[site.id]

        order_id = f"ORD-{random.randint(10000, 99999)}"
        order_type = random.choice(["PO", "TO", "SO"])
        order_type_map = {"PO": "purchase_order", "TO": "transfer_order", "SO": "customer_order"}
        order_qty = random.uniform(20, 100)
        expected_date = self.current_date + timedelta(days=random.randint(-3, 7))

        days_from_expected = (expected_date - self.current_date).days  # positive = future
        days_since_created = random.randint(1, 30)
        received_qty = order_qty * random.uniform(0, 1)
        expected_price = random.uniform(10, 50)
        actual_price = expected_price * random.uniform(0.85, 1.15)

        # Pick a random status
        status = random.choice(["created", "confirmed", "in_transit", "partially_received"])

        # Use order tracking engine for expert decision
        snapshot = OrderSnapshot(
            order_id=order_id,
            order_type=order_type_map.get(order_type, "purchase_order"),
            status=status,
            days_until_expected=days_from_expected,
            days_since_created=days_since_created,
            typical_transit_days=random.uniform(3, 10),
            ordered_qty=order_qty,
            received_qty=received_qty if status == "partially_received" else 0,
            expected_unit_price=expected_price,
            actual_unit_price=actual_price,
            partner_on_time_rate=random.uniform(0.7, 0.98),
            partner_fill_rate=random.uniform(0.85, 0.99),
        )
        engine_result = self.order_tracking_engine.evaluate_order(snapshot)

        # Map engine results to decision fields
        if engine_result is not None:
            exception_type = engine_result.exception_type.split("_")[0] if "_" in engine_result.exception_type else engine_result.exception_type
            # Map to simple types used in log
            exc_type_map = {
                "late": "late", "early": "early", "quantity": "short",
                "price": "quality", "missing": "quality", "stuck": "late",
                "no": "late",  # fallback
            }
            exception_type = exc_type_map.get(exception_type, "late")
            severity = engine_result.severity
            # Map engine recommended actions to decision action types
            action_map_engine = {
                "no_action": "accept", "monitor": "accept", "expedite": "expedite",
                "find_alternate": "reorder", "contact_supplier": "escalate",
                "adjust_schedule": "accept", "review_pricing": "accept",
                "escalate": "escalate",
            }
            action_type = action_map_engine.get(engine_result.recommended_action, "accept")
        else:
            exception_type = "late"
            severity = "low"
            action_type = "accept"

        # Convert engine severity to match log expectations
        severity_map = {"info": "low", "warning": "medium", "high": "high", "critical": "critical"}
        severity = severity_map.get(severity, severity)

        inventory_position = state.inventory.get(self.products[0], 50) if self.products else 50
        customer_impact = "high" if severity in ["high", "critical"] else "medium" if severity == "medium" else "low"

        days_from_expected_log = (self.current_date - expected_date).days
        qty_variance = order_qty - received_qty if exception_type == "short" else 0

        source = self._random_decision_source()

        decision = OrderTrackingDecisionLog(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            order_id=order_id,
            order_type=order_type,
            decision_date=self.current_date,
            exception_type=exception_type,
            exception_severity=severity,
            days_from_expected=days_from_expected_log,
            qty_variance=qty_variance,
            state_order_status=status.upper(),
            state_order_qty=order_qty,
            state_expected_date=expected_date,
            state_inventory_position=inventory_position,
            state_other_pending_orders=state.pending_orders,
            state_customer_impact=customer_impact,
            state_features={"order_age_days": days_since_created},
            action_type=action_type,
            action_new_expected_date=self.current_date + timedelta(days=random.randint(2, 7)) if action_type in ["expedite", "accept"] else None,
            action_reorder_qty=abs(qty_variance) if action_type == "reorder" else None,
            action_escalated_to="Regional Manager" if action_type == "escalate" else None,
            action_reason=f"Engine: {engine_result.description}" if engine_result else f"Exception: {exception_type}, Severity: {severity}",
            source=source,
            ai_confidence=random.uniform(0.7, 0.95) if source != DecisionSource.EXPERT_HUMAN else None
        )
        self.db.add(decision)
        await self.db.flush()
        self.stats.order_tracking_decisions_created += 1

        # Outcome
        exception_resolved = random.random() < 0.85
        resolution_time = random.uniform(1, 48) if exception_resolved else random.uniform(48, 168)
        customer_satisfied = random.random() < 0.8 if exception_resolved else random.random() < 0.3

        reward_weights = DEFAULT_TRM_REWARD_WEIGHTS[TRMType.ORDER_TRACKING]
        reward = (
            reward_weights["correct_exception_detection"] * (0.8 if exception_resolved else 0.2) +
            reward_weights["resolution_speed"] * max(0, 1.0 - resolution_time / 48) +
            reward_weights["escalation_appropriateness"] * (
                0.8 if (action_type == "escalate" and severity in ["high", "critical"]) or
                       (action_type != "escalate" and severity in ["low", "medium"])
                else 0.3
            )
        )

        outcome = OrderTrackingOutcome(
            decision_id=decision.id,
            status=OutcomeStatus.MEASURED,
            measured_at=datetime.utcnow(),
            exception_resolved=exception_resolved,
            resolution_time_hours=resolution_time,
            final_order_status="DELIVERED" if exception_resolved else "EXCEPTION",
            customer_notified=random.random() < 0.9,
            customer_satisfied=customer_satisfied,
            additional_cost=random.uniform(0, 500) if action_type in ["expedite", "reorder"] else 0,
            service_recovery_successful=customer_satisfied and exception_resolved,
            reward=reward,
            reward_components={
                "resolved": float(exception_resolved),
                "resolution_time": resolution_time,
                "customer_satisfied": float(customer_satisfied)
            },
            next_state_order_status="DELIVERED" if exception_resolved else "EXCEPTION"
        )
        self.db.add(outcome)

        # Replay buffer
        severity_map = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
        exception_map = {"late": 0, "short": 1, "damaged": 2, "quality": 3}

        state_vector = [
            exception_map.get(exception_type, 0) / 3,
            severity_map.get(severity, 0.5),
            days_from_expected_log / 10,
            qty_variance / order_qty if order_qty > 0 else 0,
            inventory_position / 200,
            state.pending_orders / 50,
            1.0 if customer_impact == "high" else 0.5 if customer_impact == "medium" else 0.25
        ]
        next_state_vector = [
            0, 0, 0, 0,  # Exception resolved
            inventory_position / 200,
            (state.pending_orders - 1) / 50,
            0.25
        ]

        action_map = {"accept": 0, "expedite": 1, "reorder": 2, "escalate": 3, "cancel": 4}

        is_expert = source == DecisionSource.EXPERT_HUMAN
        replay_entry = TRMReplayBuffer(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            trm_type=TRMType.ORDER_TRACKING.value,
            decision_log_id=decision.id,
            decision_log_table="trm_order_tracking_decision_log",
            state_vector=state_vector,
            state_dim=len(state_vector),
            action_discrete=action_map.get(action_type, 0),
            action_dim=1,
            reward=reward,
            reward_components={
                "resolved": float(exception_resolved),
                "resolution_speed": max(0, 1.0 - resolution_time / 48)
            },
            next_state_vector=next_state_vector,
            done=exception_resolved,
            is_expert=is_expert,
            override_effectiveness=self._synthetic_override_effectiveness() if is_expert else None,
            priority=1.0 + abs(reward),
            transition_date=self.current_date
        )
        self.db.add(replay_entry)
        self.stats.replay_buffer_entries_created += 1

    async def _generate_inventory_buffer_decision(self):
        """Generate an inventory buffer adjustment decision using buffer calculator for expert labels."""
        inventory_sites = [s for s in self.sites if s.master_type in ["INVENTORY", "MANUFACTURER"]]
        if not inventory_sites:
            return

        site = random.choice(inventory_sites)
        state = self.site_states[site.id]
        product_id = random.choice(self.products)

        inventory = state.inventory.get(product_id, 50)
        demand_forecast = state.last_demand.get(product_id, 40)
        backlog = state.backlog.get(product_id, 0)

        # Build demand context — phase-aware stochastic sampling
        avg_daily_demand = demand_forecast / 7 if demand_forecast > 0 else 5.0
        # demand_cv scales with phase: phase 1 → tight (0.05-0.30), phase 3 → wide (0.05-0.80)
        phase_var = self._phase_variance()
        demand_cv_mean = 0.15 + phase_var  # ranges: ~0.30 (p1), ~0.55 (p2), ~0.90 (p3)
        demand_cv = max(0.05, min(0.95, self.stochastic_sampler.sample_from_distribution(
            self._make_dist_config("normal", demand_cv_mean, 0.3), demand_cv_mean
        )))
        demand_trend = random.uniform(-0.2, 0.3)
        day_of_year = self.current_date.timetuple().tm_yday
        seasonal_index = 1 + 0.3 * np.sin(2 * np.pi * day_of_year / 365)
        recent_stockout_count = random.choices([0, 1, 2, 3, 4], weights=[0.5, 0.2, 0.15, 0.1, 0.05])[0]
        recent_excess_days = random.choices([0, 10, 30, 60, 90], weights=[0.3, 0.3, 0.2, 0.15, 0.05])[0]
        forecast_bias = random.uniform(-0.15, 0.15)
        # Lead time via stochastic sampler (phase-aware)
        lt_mean_buf = 13.0  # midpoint of original 5-21
        lt_config_buf = self._make_dist_config("normal", lt_mean_buf)
        lead_time_days = max(1.0, self.stochastic_sampler.sample_from_distribution(lt_config_buf, lt_mean_buf))
        # Lead time CV also phase-scaled
        lt_cv_mean = 0.10 + phase_var * 0.3  # ranges: ~0.15 (p1), ~0.22 (p2), ~0.33 (p3)
        lead_time_cv = max(0.01, min(0.5, self.stochastic_sampler.sample_from_distribution(
            self._make_dist_config("normal", lt_cv_mean, 0.3), lt_cv_mean
        )))

        # Use SS calculator for baseline
        demand_stats = DemandStats(
            avg_daily_demand=avg_daily_demand,
            std_daily_demand=avg_daily_demand * demand_cv,
            avg_lead_time=lead_time_days,
            std_lead_time=lead_time_days * lead_time_cv,
        )
        ss_policy = SSPolicy(
            policy_type=PolicyType.SERVICE_LEVEL,
            service_level=0.95,
        )
        ss_result = self.ss_calculator.compute_safety_stock(demand_stats, ss_policy)
        baseline_ss = ss_result.safety_stock
        current_dos = inventory / (avg_daily_demand + 1e-6)

        # Expert heuristic adjustment (same logic as InventoryBufferTRM._heuristic_evaluate)
        multiplier = 1.0
        reason = "no_adjustment"

        if recent_stockout_count >= 3:
            multiplier = 1.4
            reason = "recent_stockout"
        elif recent_stockout_count >= 1:
            multiplier = 1.2
            reason = "recent_stockout"
        elif demand_cv > 0.5:
            multiplier = 1.3
            reason = "high_volatility"
        elif seasonal_index > 1.3:
            multiplier = 1.2
            reason = "seasonal_peak"
        elif seasonal_index < 0.7:
            multiplier = 0.85
            reason = "seasonal_trough"
        elif demand_trend > 0.1:
            multiplier = 1.1
            reason = "trend_up"
        elif demand_trend < -0.1:
            multiplier = 0.9
            reason = "trend_down"
        elif recent_excess_days > 60:
            multiplier = 0.85
            reason = "excess_inventory"
        elif abs(forecast_bias) > 0.1:
            multiplier = 1.0 + forecast_bias
            reason = "forecast_bias"

        adjusted_ss = baseline_ss * multiplier

        source = self._random_decision_source()

        decision = SafetyStockDecisionLog(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            product_id=self.products.index(product_id),
            location_id=str(site.id),
            decision_date=self.current_date,
            state_baseline_ss=baseline_ss,
            state_policy_type="sl",
            state_current_dos=current_dos,
            state_current_on_hand=inventory,
            state_demand_cv=demand_cv,
            state_avg_daily_demand=avg_daily_demand,
            state_demand_trend=demand_trend,
            state_seasonal_index=seasonal_index,
            state_recent_stockout_count=recent_stockout_count,
            state_recent_excess_days=recent_excess_days,
            state_forecast_bias=forecast_bias,
            state_lead_time_days=lead_time_days,
            state_lead_time_cv=lead_time_cv,
            state_features={"day_of_year": day_of_year},
            action_multiplier=multiplier,
            action_adjusted_ss=adjusted_ss,
            action_reason=reason,
            source=source,
            ai_confidence=random.uniform(0.7, 0.95) if source != DecisionSource.EXPERT_HUMAN else None,
        )
        self.db.add(decision)
        await self.db.flush()
        self.stats.inventory_buffer_decisions_created += 1

        # Outcome (simulated over review period)
        stockout_occurred = random.random() < (0.05 if multiplier >= 1.0 else 0.15)
        actual_dos = current_dos * random.uniform(0.7, 1.3)
        excess_cost = max(0, (adjusted_ss - baseline_ss) * 0.1) if multiplier > 1.0 else 0
        actual_service = 0.98 if not stockout_occurred else random.uniform(0.8, 0.95)

        reward_weights = DEFAULT_TRM_REWARD_WEIGHTS[TRMType.SAFETY_STOCK]
        reward = (
            reward_weights["stockout_penalty"] * (-1.0 if stockout_occurred else 0.5) +
            reward_weights["dos_target_reward"] * min(1.0, actual_dos / 14) +
            reward_weights["excess_cost_penalty"] * (-excess_cost / 100) +
            reward_weights["stability_bonus"] * (1.0 - min(1.0, abs(multiplier - 1.0) * 2))
        )

        outcome = SafetyStockOutcome(
            decision_id=decision.id,
            status=OutcomeStatus.MEASURED,
            measured_at=datetime.utcnow(),
            actual_stockout_occurred=stockout_occurred,
            actual_stockout_days=random.randint(1, 5) if stockout_occurred else 0,
            actual_dos_at_end=actual_dos,
            actual_excess_inventory_cost=excess_cost,
            actual_service_level=actual_service,
            reward=reward,
            reward_components={
                "stockout": float(stockout_occurred),
                "dos": actual_dos,
                "excess_cost": excess_cost,
                "multiplier": multiplier,
            },
            next_state_dos=actual_dos,
            next_state_demand_cv=demand_cv * random.uniform(0.9, 1.1),
        )
        self.db.add(outcome)

        # Replay buffer
        state_vector = [
            baseline_ss / 200, current_dos / 30, demand_cv,
            demand_trend, seasonal_index, recent_stockout_count / 5,
            recent_excess_days / 90, forecast_bias,
            lead_time_days / 30, lead_time_cv, inventory / 200,
        ]
        next_state_vector = [
            adjusted_ss / 200, actual_dos / 30, demand_cv * random.uniform(0.9, 1.1),
            demand_trend, seasonal_index, max(0, recent_stockout_count - (0 if not stockout_occurred else -1)) / 5,
            recent_excess_days / 90, forecast_bias,
            lead_time_days / 30, lead_time_cv, inventory / 200,
        ]

        is_expert = source == DecisionSource.EXPERT_HUMAN
        replay_entry = TRMReplayBuffer(
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            site_id=site.id,
            trm_type=TRMType.SAFETY_STOCK.value,
            decision_log_id=decision.id,
            decision_log_table="trm_safety_stock_decision_log",
            state_vector=state_vector,
            state_dim=len(state_vector),
            action_continuous=[multiplier],
            action_dim=1,
            reward=reward,
            reward_components={
                "stockout": float(stockout_occurred),
                "dos": actual_dos,
                "multiplier": multiplier,
            },
            next_state_vector=next_state_vector,
            done=False,
            is_expert=is_expert,
            override_effectiveness=self._synthetic_override_effectiveness() if is_expert else None,
            priority=1.0 + abs(reward),
            transition_date=self.current_date,
        )
        self.db.add(replay_entry)
        self.stats.replay_buffer_entries_created += 1

    @staticmethod
    def _synthetic_override_effectiveness() -> str:
        """Generate realistic override effectiveness labels for synthetic data.

        Distribution: 60% BENEFICIAL, 25% NEUTRAL, 15% DETRIMENTAL.
        Reflects a plausible real-world scenario where most human overrides
        add value (experts override for good reason) but some don't.
        """
        return random.choices(
            ["BENEFICIAL", "NEUTRAL", "DETRIMENTAL"],
            weights=[60, 25, 15],
        )[0]

    def _generate_demand(self, site_id: int, product_id: str) -> float:
        """Generate demand based on pattern for site/product."""
        state = self.site_states.get(site_id)
        base_demand = state.last_demand.get(product_id, 40) if state else 40

        # Select pattern randomly
        pattern = random.choices(
            list(self.demand_patterns.keys()),
            weights=list(self.demand_patterns.values())
        )[0]

        day_of_year = self.current_date.timetuple().tm_yday

        if pattern == DemandPattern.STABLE:
            demand = base_demand * random.uniform(0.9, 1.1)
        elif pattern == DemandPattern.SEASONAL:
            seasonal_factor = 1 + 0.3 * np.sin(2 * np.pi * day_of_year / 365)
            demand = base_demand * seasonal_factor * random.uniform(0.9, 1.1)
        elif pattern == DemandPattern.TRENDING_UP:
            trend = 1 + (day_of_year / 365) * 0.3
            demand = base_demand * trend * random.uniform(0.9, 1.1)
        elif pattern == DemandPattern.TRENDING_DOWN:
            trend = 1 - (day_of_year / 365) * 0.2
            demand = base_demand * max(0.5, trend) * random.uniform(0.9, 1.1)
        elif pattern == DemandPattern.STEP_CHANGE:
            step = 1.5 if day_of_year > 180 else 1.0
            demand = base_demand * step * random.uniform(0.9, 1.1)
        elif pattern == DemandPattern.PROMOTIONAL:
            promo = 2.0 if random.random() < 0.1 else 1.0
            demand = base_demand * promo * random.uniform(0.9, 1.1)
        else:  # RANDOM
            demand = base_demand * random.uniform(0.5, 1.5)

        return max(0, demand)

    def _random_decision_source(self) -> DecisionSource:
        """Get random decision source based on weights."""
        sources = list(self.decision_source_weights.keys())
        weights = list(self.decision_source_weights.values())
        return random.choices(sources, weights=weights)[0]

    def _simulate_day_end(self):
        """Update site states at end of day."""
        for site_id, state in self.site_states.items():
            for product_id in self.products:
                # Consume some inventory (demand)
                demand = self._generate_demand(site_id, product_id)
                current_inv = state.inventory.get(product_id, 50)

                if current_inv >= demand:
                    state.inventory[product_id] = current_inv - demand
                else:
                    state.inventory[product_id] = 0
                    state.backlog[product_id] = state.backlog.get(product_id, 0) + (demand - current_inv)

                # Receive some pipeline inventory
                pipeline = state.pipeline.get(product_id, 30)
                receipt = pipeline * random.uniform(0.1, 0.3)
                state.pipeline[product_id] = pipeline - receipt
                state.inventory[product_id] = state.inventory.get(product_id, 0) + receipt

                # Update last demand
                state.last_demand[product_id] = demand

            # Update pending orders
            state.pending_orders = max(0, state.pending_orders + random.randint(-5, 5))


async def generate_synthetic_trm_data(
    db: AsyncSession,
    config_id: int,
    tenant_id: int,
    num_days: int = 365,
    num_orders_per_day: int = 50,
    num_decisions_per_day: int = 20,
    seed: Optional[int] = None,
    signal_bus=None,
    phase: int = 2,
) -> GenerationStats:
    """
    Convenience function to generate synthetic TRM training data.

    Args:
        db: Database session
        config_id: Supply chain config ID
        tenant_id: Customer ID
        num_days: Number of days to simulate
        num_orders_per_day: Average orders per day
        num_decisions_per_day: Average TRM decisions per day
        seed: Random seed for reproducibility
        signal_bus: Optional HiveSignalBus for signal-enriched generation
        phase: Curriculum phase (1=low variance, 2=moderate, 3=high). Default 2.

    Returns:
        GenerationStats with counts of generated records
    """
    generator = SyntheticTRMDataGenerator(
        db, config_id, tenant_id, seed, signal_bus=signal_bus, phase=phase
    )
    return await generator.generate(
        num_days=num_days,
        num_orders_per_day=num_orders_per_day,
        num_decisions_per_day=num_decisions_per_day
    )
