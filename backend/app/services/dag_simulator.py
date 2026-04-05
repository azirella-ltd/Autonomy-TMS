"""
DAG-Aware Deterministic Supply Chain Simulator

Reads any SupplyChainConfig from the database and runs period-by-period
deterministic simulation using existing Powell engines (MRP, AATP,
SafetyStock, Rebalancing, OrderTracking).

Unlike engine.py (linear SupplyChainLine) or data_generator.py (linear chain),
this simulator operates on arbitrary DAG topologies with N sites, M products,
and L transportation lanes.

Usage:
    simulator = DAGSimulator(config_id=1, db=session)
    await simulator.load_topology()
    result = simulator.simulate(num_periods=52, seed=42)

Output includes:
- Period-by-period state per site per product
- All ordering/fulfillment/rebalancing decisions (for TRM behavioral cloning)
- Aggregate KPIs (fill rate, OTIF, inventory turns, total cost)

This is permanent deployment infrastructure -- used for warm-starting
AI models at every deployment.
"""

from __future__ import annotations

import logging
import math
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.supply_chain_config import (
    SupplyChainConfig,
    Node,
    TransportationLane,
)
from app.models.sc_entities import (
    Product,
    Forecast,
    InvLevel,
    InvPolicy,
)
from app.models.supplier import VendorProduct, VendorLeadTime

from app.services.powell.engines.mrp_engine import (
    MRPEngine,
    MRPConfig,
    GrossRequirement,
    PlannedOrder,
)
from app.services.powell.engines.aatp_engine import (
    AATPEngine,
    AATPConfig,
    ATPAllocation,
    Order as ATPOrder,
    ATPResult,
    Priority,
)
from app.services.powell.engines.safety_stock_calculator import (
    SafetyStockCalculator,
    SafetyStockConfig,
    SSPolicy,
    PolicyType,
    DemandStats,
)
from app.services.powell.engines.rebalancing_engine import (
    RebalancingEngine,
    RebalancingConfig,
    SiteState,
    LaneConstraints,
    TransferRecommendation,
)
from app.services.powell.engines.order_tracking_engine import (
    OrderTrackingEngine,
    OrderTrackingConfig,
    OrderSnapshot,
    ExceptionResult,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================


class OrderingStrategy(str, Enum):
    """Heuristic ordering strategy for warm-start data."""
    BASE_STOCK = "base_stock"       # Order up to target inventory
    CONSERVATIVE = "conservative"   # Smoothed ordering (moving avg)
    PID = "pid"                     # PID controller
    EOQ = "eoq"                     # Economic order quantity


@dataclass
class SiteProductState:
    """Per-site per-product inventory state."""
    on_hand: float = 0.0
    backlog: float = 0.0
    in_transit: float = 0.0
    safety_stock: float = 0.0
    target_inventory: float = 0.0
    demand_history: List[float] = field(default_factory=list)
    order_history: List[float] = field(default_factory=list)
    # PID controller state
    pid_integral: float = 0.0
    pid_prev_error: float = 0.0


@dataclass
class PipelineShipment:
    """A shipment in transit through a lane."""
    product_id: str
    quantity: float
    ship_period: int
    arrival_period: int
    lane_id: int
    order_type: str  # "purchase", "transfer"


@dataclass
class SimDecision:
    """Record of a decision made during simulation (for TRM training)."""
    period: int
    site_id: int
    site_name: str
    product_id: str
    decision_type: str  # "order"(PO), "atp", "rebalance", "exception", "transfer_order", "mo_execution", "quality", "maintenance", "subcontracting", "forecast_adjustment", "safety_stock"
    quantity: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SimPeriodState:
    """Snapshot of a site-product state at a specific period."""
    period: int
    site_id: int
    site_name: str
    product_id: str
    on_hand: float
    backlog: float
    in_transit: float
    incoming_demand: float
    fulfilled_qty: float
    order_placed: float
    holding_cost: float
    backlog_cost: float
    safety_stock: float


@dataclass
class SimKPIs:
    """Aggregate KPIs from simulation."""
    fill_rate: float = 0.0           # Fulfilled / Total Demand
    otif_rate: float = 0.0           # On-Time In-Full rate
    avg_inventory_turns: float = 0.0
    total_holding_cost: float = 0.0
    total_backlog_cost: float = 0.0
    total_cost: float = 0.0
    avg_days_of_supply: float = 0.0
    bullwhip_ratio: float = 0.0      # Var(orders) / Var(demand)


@dataclass
class SimulationResult:
    """Complete simulation output."""
    config_id: int
    config_name: str
    num_periods: int
    num_sites: int
    num_products: int
    period_states: List[SimPeriodState]
    decisions: List[SimDecision]
    shipments: List[PipelineShipment]
    kpis: SimKPIs
    # Per-site per-product time series for training
    site_product_history: Dict[str, Dict[str, List[Dict[str, float]]]]
    # Metadata
    strategy: str
    seed: int


# ============================================================================
# Topology Loader
# ============================================================================


@dataclass
class LoadedTopology:
    """Loaded and processed supply chain topology."""
    config: SupplyChainConfig
    sites: List[Node]
    lanes: List[TransportationLane]
    products: List[Product]
    forecasts: Dict[str, Dict[str, List[float]]]  # site_name -> product_id -> weekly forecast
    inv_policies: Dict[str, Dict[str, Dict]]       # site_name -> product_id -> policy params
    initial_inventory: Dict[str, Dict[str, float]]  # site_name -> product_id -> qty
    vendor_lead_times: Dict[str, Dict[str, int]]    # supplier_name -> product_id -> lead_time_days
    vendor_reliability: Dict[str, float]             # supplier_name -> reliability (0-1)

    # Topology analysis
    supply_sites: List[Node]      # vendor TradingPartner endpoints (VENDOR / VENDOR legacy)
    inventory_sites: List[Node]   # INVENTORY / MANUFACTURER
    demand_sites: List[Node]      # customer TradingPartner endpoints (CUSTOMER / CUSTOMER legacy)

    # DAG structure: site_name -> list of (upstream_site_name, lane)
    upstream_map: Dict[str, List[Tuple[str, TransportationLane]]]
    # site_name -> list of (downstream_site_name, lane)
    downstream_map: Dict[str, List[Tuple[str, TransportationLane]]]

    # Topological sort order (upstream first)
    topo_order: List[str]


async def load_topology(config_id: int, db: AsyncSession) -> LoadedTopology:
    """Load and process a supply chain config into simulation-ready format."""

    # Load config with relationships
    result = await db.execute(
        select(SupplyChainConfig)
        .where(SupplyChainConfig.id == config_id)
        .options(
            selectinload(SupplyChainConfig.sites),
            selectinload(SupplyChainConfig.transportation_lanes),
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise ValueError(f"SupplyChainConfig {config_id} not found")

    sites = list(config.sites)
    lanes = list(config.transportation_lanes)

    # Load products for this config
    prod_result = await db.execute(
        select(Product).where(Product.config_id == config_id)
    )
    products = list(prod_result.scalars().all())

    # Build site lookup
    site_by_id = {s.id: s for s in sites}
    site_by_name = {s.name: s for s in sites}

    # Classify sites by master type
    supply_sites = [s for s in sites if _is_supply(s)]
    inventory_sites = [s for s in sites if _is_inventory(s)]
    demand_sites = [s for s in sites if _is_demand(s)]

    # Build adjacency maps
    upstream_map: Dict[str, List[Tuple[str, TransportationLane]]] = defaultdict(list)
    downstream_map: Dict[str, List[Tuple[str, TransportationLane]]] = defaultdict(list)

    for lane in lanes:
        source = site_by_id.get(lane.from_site_id)
        target = site_by_id.get(lane.to_site_id)
        if source and target:
            downstream_map[source.name].append((target.name, lane))
            upstream_map[target.name].append((source.name, lane))

    # Topological sort (upstream first: VENDOR → INVENTORY → CUSTOMER)
    topo_order = _topological_sort(sites, lanes, site_by_id)

    # Load forecasts
    forecasts = await _load_forecasts(config_id, db, sites, products)

    # Load inventory policies
    inv_policies = await _load_inv_policies(config_id, db, sites, products)

    # Load initial inventory
    initial_inventory = await _load_initial_inventory(config_id, db, sites, products)

    # Load vendor lead times and reliability
    vendor_lead_times, vendor_reliability = await _load_vendor_info(db, supply_sites, products)

    return LoadedTopology(
        config=config,
        sites=sites,
        lanes=lanes,
        products=products,
        forecasts=forecasts,
        inv_policies=inv_policies,
        initial_inventory=initial_inventory,
        vendor_lead_times=vendor_lead_times,
        vendor_reliability=vendor_reliability,
        supply_sites=supply_sites,
        inventory_sites=inventory_sites,
        demand_sites=demand_sites,
        upstream_map=upstream_map,
        downstream_map=downstream_map,
        topo_order=topo_order,
    )


# ============================================================================
# Simulator
# ============================================================================


class DAGSimulator:
    """
    Deterministic supply chain simulator for arbitrary DAG topologies.

    Runs period-by-period using existing Powell deterministic engines
    to produce training data for GraphSAGE, tGNN, and TRMs.
    """

    def __init__(
        self,
        topology: LoadedTopology,
        strategy: OrderingStrategy = OrderingStrategy.BASE_STOCK,
        holding_cost_rate: float = 0.005,   # Per unit per period
        backlog_cost_rate: float = 0.01,    # Per unit per period
        # PID controller params
        pid_kp: float = 0.6,
        pid_ki: float = 0.15,
        pid_kd: float = 0.05,
    ):
        self.topology = topology
        self.strategy = strategy
        self.holding_cost_rate = holding_cost_rate
        self.backlog_cost_rate = backlog_cost_rate
        self.pid_kp = pid_kp
        self.pid_ki = pid_ki
        self.pid_kd = pid_kd

        # State: site_name -> product_id -> SiteProductState
        self.state: Dict[str, Dict[str, SiteProductState]] = {}

        # Pipeline: list of in-flight shipments
        self.pipeline: List[PipelineShipment] = []

        # Records
        self.period_states: List[SimPeriodState] = []
        self.decisions: List[SimDecision] = []
        self.all_shipments: List[PipelineShipment] = []

        # Accumulators for KPIs
        self._total_demand = 0.0
        self._total_fulfilled = 0.0
        self._total_on_time = 0
        self._total_orders_checked = 0

        # Initialize engines (reusable across periods)
        self._mrp_engines: Dict[str, MRPEngine] = {}
        self._aatp_engines: Dict[str, AATPEngine] = {}
        self._ss_calculators: Dict[str, SafetyStockCalculator] = {}
        self._rebalancing_engine = RebalancingEngine(config=RebalancingConfig())
        self._order_tracking_engine = OrderTrackingEngine(config=OrderTrackingConfig())

    def simulate(
        self,
        num_periods: int = 52,
        seed: int = 42,
        demand_noise_cv: float = 0.15,
        progress_callback=None,
    ) -> SimulationResult:
        """
        Run deterministic simulation for num_periods.

        Args:
            num_periods: Number of periods (typically weeks) to simulate
            seed: Random seed for demand noise
            demand_noise_cv: Coefficient of variation for demand noise around forecast
            progress_callback: Optional callable(period, num_periods) for progress

        Returns:
            SimulationResult with complete history and decisions
        """
        rng = np.random.default_rng(seed)

        # Initialize state
        self._initialize_state()
        self._initialize_engines()

        topo = self.topology

        for period in range(num_periods):
            sim_date = date.today() + timedelta(weeks=period)

            # Step 1: Receive arriving shipments
            self._receive_shipments(period)

            # Step 2: Generate demand at CUSTOMER sites
            demand_by_site = self._generate_demand(period, rng, demand_noise_cv)

            # Step 3: Process demand upstream through DAG
            # Walk in reverse topological order (demand sites first, then inventory, then supply)
            for site_name in reversed(topo.topo_order):
                site = self._get_site(site_name)
                if not site:
                    continue

                if _is_demand(site):
                    # Demand sites: record demand, it's been generated above
                    pass

                elif _is_inventory(site):
                    # Inventory sites (DC): run planning engines
                    self._process_inventory_site(
                        site, period, sim_date, demand_by_site, rng
                    )

                elif _is_supply(site):
                    # Supply sites: fulfill planned orders from inventory sites
                    self._process_supply_site(site, period, sim_date)

            # Step 4: Record period state for all sites
            self._record_period_state(period)

            # Step 5: Run order tracking on in-flight shipments
            self._track_orders(period, sim_date)

            if progress_callback:
                progress_callback(period + 1, num_periods)

        # Compute final KPIs
        kpis = self._compute_kpis(num_periods)

        # Build per-site per-product history
        history = self._build_history()

        return SimulationResult(
            config_id=topo.config.id,
            config_name=topo.config.name,
            num_periods=num_periods,
            num_sites=len(topo.sites),
            num_products=len(topo.products),
            period_states=self.period_states,
            decisions=self.decisions,
            shipments=self.all_shipments,
            kpis=kpis,
            site_product_history=history,
            strategy=self.strategy.value,
            seed=seed,
        )

    # ========================================================================
    # Initialization
    # ========================================================================

    def _initialize_state(self):
        """Initialize per-site per-product inventory state."""
        topo = self.topology

        self.state.clear()
        self.pipeline.clear()
        self.period_states.clear()
        self.decisions.clear()
        self.all_shipments.clear()
        self._total_demand = 0.0
        self._total_fulfilled = 0.0

        for site in topo.sites:
            self.state[site.name] = {}
            for product in topo.products:
                pid = product.id if hasattr(product, 'id') else str(product.product_id)
                initial_inv = topo.initial_inventory.get(site.name, {}).get(pid, 0.0)

                # Get safety stock from policy
                policy_params = topo.inv_policies.get(site.name, {}).get(pid, {})
                ss_days = policy_params.get("safety_stock_days", 14)
                weekly_demand = self._get_forecast(site.name, pid, 0)
                daily_demand = weekly_demand / 7.0 if weekly_demand > 0 else 0
                ss = daily_demand * ss_days

                target = ss + weekly_demand * 2  # SS + 2 weeks of demand

                self.state[site.name][pid] = SiteProductState(
                    on_hand=initial_inv,
                    safety_stock=ss,
                    target_inventory=target,
                )

    def _initialize_engines(self):
        """Initialize Powell engines for each inventory site."""
        for site in self.topology.inventory_sites:
            self._mrp_engines[site.name] = MRPEngine(
                site_key=site.name,
                config=MRPConfig(
                    planning_horizon_days=28,
                    lot_sizing_rule="lot_for_lot",
                    min_order_qty=5,
                ),
            )
            self._aatp_engines[site.name] = AATPEngine(
                site_key=site.name,
                config=AATPConfig(),
            )
            self._ss_calculators[site.name] = SafetyStockCalculator(
                site_key=site.name,
                config=SafetyStockConfig(
                    default_policy_type=PolicyType.DOC_FCST,
                    default_service_level=0.97,
                    default_days_of_coverage=14,
                ),
            )

    # ========================================================================
    # Simulation Steps
    # ========================================================================

    def _receive_shipments(self, period: int):
        """Process shipments arriving this period."""
        arriving = [s for s in self.pipeline if s.arrival_period == period]
        remaining = [s for s in self.pipeline if s.arrival_period != period]
        self.pipeline = remaining

        for shipment in arriving:
            # Find the target site for this shipment
            target_site = self._find_shipment_target(shipment)
            if target_site and target_site in self.state:
                sp = self.state[target_site].get(shipment.product_id)
                if sp:
                    sp.on_hand += shipment.quantity
                    sp.in_transit -= shipment.quantity
                    sp.in_transit = max(0, sp.in_transit)

    def _generate_demand(
        self, period: int, rng: np.random.Generator, noise_cv: float
    ) -> Dict[str, Dict[str, float]]:
        """Generate demand at CUSTOMER sites from forecasts + noise."""
        demand_by_site: Dict[str, Dict[str, float]] = {}
        topo = self.topology

        for site in topo.demand_sites:
            demand_by_site[site.name] = {}
            for product in topo.products:
                pid = self._product_id(product)
                forecast = self._get_forecast(site.name, pid, period)

                if forecast > 0:
                    noise = rng.normal(0, forecast * noise_cv)
                    demand = max(0, forecast + noise)
                else:
                    demand = 0.0

                demand_by_site[site.name][pid] = demand

        return demand_by_site

    def _process_inventory_site(
        self,
        site: Node,
        period: int,
        sim_date: date,
        demand_by_site: Dict[str, Dict[str, float]],
        rng: np.random.Generator,
    ):
        """Process an INVENTORY site: fulfill demand, compute orders, track state."""
        topo = self.topology

        for product in topo.products:
            pid = self._product_id(product)
            sp = self.state[site.name].get(pid)
            if not sp:
                continue

            # Aggregate demand from downstream sites
            total_demand = 0.0
            for ds_name, lane in topo.downstream_map.get(site.name, []):
                ds_demand = demand_by_site.get(ds_name, {}).get(pid, 0.0)
                # Downstream inventory sites may also have placed orders
                ds_state = self.state.get(ds_name, {}).get(pid)
                if ds_state and _is_inventory(self._get_site(ds_name)):
                    ds_demand = ds_state.backlog  # Their unfulfilled need
                total_demand += ds_demand

            # Add any accumulated backlog
            total_need = total_demand + sp.backlog

            # Fulfill what we can
            fulfilled = min(sp.on_hand, total_need)
            sp.on_hand -= fulfilled
            sp.backlog = total_need - fulfilled

            # Record demand and fulfillment
            sp.demand_history.append(total_demand)
            self._total_demand += total_demand
            self._total_fulfilled += fulfilled

            # Ship to downstream (create shipments)
            if fulfilled > 0:
                self._ship_downstream(site, pid, fulfilled, period)

            # Record fulfillment decision
            self.decisions.append(SimDecision(
                period=period,
                site_id=site.id,
                site_name=site.name,
                product_id=pid,
                decision_type="atp",
                quantity=fulfilled,
                context={
                    "demand": total_demand,
                    "backlog_before": sp.backlog + fulfilled - total_demand + total_need - total_demand,
                    "on_hand_before": sp.on_hand + fulfilled,
                    "fill_rate": fulfilled / total_need if total_need > 0 else 1.0,
                },
            ))

            # Decide order quantity using heuristic strategy
            order_qty = self._compute_order(site, pid, sp, period, sim_date)

            if order_qty > 0:
                sp.order_history.append(order_qty)
                self._place_order_upstream(site, pid, order_qty, period, sim_date)

                self.decisions.append(SimDecision(
                    period=period,
                    site_id=site.id,
                    site_name=site.name,
                    product_id=pid,
                    decision_type="order",
                    quantity=order_qty,
                    context={
                        "on_hand": sp.on_hand,
                        "backlog": sp.backlog,
                        "in_transit": sp.in_transit,
                        "safety_stock": sp.safety_stock,
                        "target_inventory": sp.target_inventory,
                        "strategy": self.strategy.value,
                    },
                ))
            else:
                sp.order_history.append(0)

            # Update safety stock periodically (every 4 periods)
            if period > 0 and period % 4 == 0 and len(sp.demand_history) >= 4:
                old_ss = sp.safety_stock
                self._update_safety_stock(site, pid, sp)
                if abs(sp.safety_stock - old_ss) > 0.01:
                    self.decisions.append(SimDecision(
                        period=period,
                        site_id=site.id,
                        site_name=site.name,
                        product_id=pid,
                        decision_type="safety_stock",
                        quantity=sp.safety_stock,
                        context={
                            "old_safety_stock": old_ss,
                            "new_safety_stock": sp.safety_stock,
                            "target_inventory": sp.target_inventory,
                            "avg_demand": float(np.mean(sp.demand_history[-4:])),
                        },
                    ))

            # Rebalancing: check if this site has excess inventory relative to others
            self._generate_rebalance_decision(site, pid, sp, period)

            # Forecast adjustment: detect demand deviation from expected
            self._generate_forecast_adjustment_decision(site, pid, sp, period)

            # Quality: periodic quality checks on received inventory
            if period > 0 and period % 2 == 0:
                self._generate_quality_decision(site, pid, sp, period, rng)

            # Maintenance: periodic maintenance decisions at interval
            if period > 0 and period % 8 == 0:
                self._generate_maintenance_decision(site, pid, period)

            # Subcontracting: when capacity constrained (manufacturer sites)
            if hasattr(site, 'master_type') and str(getattr(site, 'master_type', '')).lower() == 'manufacturer':
                if order_qty > 0:
                    self._generate_subcontracting_decision(site, pid, order_qty, sp, period)

            # MO execution: for manufacturer sites with active production
            if hasattr(site, 'master_type') and str(getattr(site, 'master_type', '')).lower() == 'manufacturer':
                if order_qty > 0:
                    self._generate_mo_decision(site, pid, order_qty, sp, period)

            # Compute costs
            sp_holding = max(0, sp.on_hand) * self.holding_cost_rate
            sp_backlog = max(0, sp.backlog) * self.backlog_cost_rate

            # Will be recorded in _record_period_state

    def _process_supply_site(self, site: Node, period: int, sim_date: date):
        """Process a VENDOR site: fulfill upstream orders."""
        topo = self.topology

        # Check for pending orders to this supplier
        # Orders come via pipeline (as special "order" type shipments marked for this supplier)
        # In this simulation, orders are immediately scheduled as shipments with lead time
        # So supply sites don't need active processing - shipments are scheduled
        # when _place_order_upstream is called
        pass

    def _track_orders(self, period: int, sim_date: date):
        """Run order tracking on in-flight shipments."""
        for shipment in self.pipeline:
            days_in_transit = (period - shipment.ship_period) * 7  # Convert periods to days
            lane = self._get_lane(shipment.lane_id)
            if not lane:
                continue

            lead_time_days = self._lane_lead_time(lane)
            expected_transit = lead_time_days
            days_until_expected = expected_transit - days_in_transit

            snapshot = OrderSnapshot(
                order_id=f"PO-{shipment.ship_period}-{shipment.product_id[:6]}",
                order_type="purchase_order",
                status="in_transit",
                days_until_expected=days_until_expected,
                days_since_created=days_in_transit,
                typical_transit_days=expected_transit,
                ordered_qty=shipment.quantity,
                received_qty=0,
            )

            result = self._order_tracking_engine.evaluate_order(snapshot)
            if result.exception_type != "no_exception":
                self.decisions.append(SimDecision(
                    period=period,
                    site_id=0,
                    site_name="tracking",
                    product_id=shipment.product_id,
                    decision_type="exception",
                    quantity=shipment.quantity,
                    context={
                        "exception_type": result.exception_type,
                        "severity": result.severity,
                        "recommended_action": result.recommended_action,
                        "days_in_transit": days_in_transit,
                    },
                ))

    # ========================================================================
    # New TRM Decision Generators
    # ========================================================================

    def _generate_rebalance_decision(
        self, site: Node, product_id: str, sp: SiteProductState, period: int,
    ):
        """Generate rebalancing decision when DOS imbalance detected across sites."""
        if sp.on_hand <= 0 or not sp.demand_history:
            return
        avg_demand = float(np.mean(sp.demand_history[-4:])) if len(sp.demand_history) >= 4 else sp.demand_history[-1]
        if avg_demand <= 0:
            return
        this_dos = sp.on_hand / (avg_demand / 7.0) if avg_demand > 0 else 0

        # Check peer sites for imbalance
        topo = self.topology
        downstream = topo.downstream_map.get(site.name, [])
        for ds_name, lane in downstream:
            ds_sp = self.state.get(ds_name, {}).get(product_id)
            if not ds_sp or not ds_sp.demand_history:
                continue
            ds_avg = float(np.mean(ds_sp.demand_history[-4:])) if len(ds_sp.demand_history) >= 4 else ds_sp.demand_history[-1]
            if ds_avg <= 0:
                continue
            ds_dos = ds_sp.on_hand / (ds_avg / 7.0)

            # If this site has >2x more DOS than downstream, suggest rebalance
            if this_dos > 2 * ds_dos and ds_dos < 14:
                rebalance_qty = min(sp.on_hand * 0.2, (avg_demand / 7.0) * 7)
                if rebalance_qty > 0:
                    self.decisions.append(SimDecision(
                        period=period,
                        site_id=site.id,
                        site_name=site.name,
                        product_id=product_id,
                        decision_type="rebalance",
                        quantity=rebalance_qty,
                        context={
                            "to_site": ds_name,
                            "source_dos": this_dos,
                            "dest_dos": ds_dos,
                            "reason": "dos_imbalance",
                            "urgency": "medium" if ds_dos < 7 else "low",
                        },
                    ))
                    break  # One rebalance per product per period

    def _generate_forecast_adjustment_decision(
        self, site: Node, product_id: str, sp: SiteProductState, period: int,
    ):
        """Generate forecast adjustment when actual demand deviates significantly."""
        if period < 4 or len(sp.demand_history) < 4:
            return
        recent_avg = float(np.mean(sp.demand_history[-4:]))
        forecast = self._get_forecast(site.name, product_id, period)
        if forecast <= 0:
            return
        deviation_pct = (recent_avg - forecast) / forecast
        if abs(deviation_pct) > 0.15:  # >15% deviation
            direction = "up" if deviation_pct > 0 else "down"
            self.decisions.append(SimDecision(
                period=period,
                site_id=site.id,
                site_name=site.name,
                product_id=product_id,
                decision_type="forecast_adjustment",
                quantity=recent_avg,
                context={
                    "current_forecast": forecast,
                    "actual_avg_demand": recent_avg,
                    "deviation_pct": round(deviation_pct, 4),
                    "direction": direction,
                    "adjustment_pct": round(deviation_pct, 4),
                    "signal_source": "simulation",
                    "signal_type": "demand_increase" if direction == "up" else "demand_decrease",
                    "confidence": min(0.95, 0.6 + abs(deviation_pct)),
                },
            ))

    def _generate_quality_decision(
        self, site: Node, product_id: str, sp: SiteProductState,
        period: int, rng: np.random.Generator,
    ):
        """Generate quality disposition decisions for received inventory."""
        if sp.on_hand <= 0:
            return
        # Simulate occasional quality issues (5% chance per check)
        if rng.random() > 0.05:
            return
        inspection_qty = min(sp.on_hand * 0.1, 50)
        defect_rate = rng.uniform(0.01, 0.08)
        disposition = "accept" if defect_rate < 0.03 else "rework" if defect_rate < 0.06 else "reject"
        self.decisions.append(SimDecision(
            period=period,
            site_id=site.id,
            site_name=site.name,
            product_id=product_id,
            decision_type="quality",
            quantity=inspection_qty,
            context={
                "defect_rate": round(float(defect_rate), 4),
                "disposition": disposition,
                "severity_level": "minor" if defect_rate < 0.03 else "major" if defect_rate < 0.06 else "critical",
                "inspection_type": "incoming",
                "rework_cost_estimate": round(inspection_qty * defect_rate * 5.0, 2),
                "scrap_cost_estimate": round(inspection_qty * defect_rate * 10.0, 2),
                "confidence": 0.85,
            },
        ))

    def _generate_maintenance_decision(
        self, site: Node, product_id: str, period: int,
    ):
        """Generate maintenance scheduling decisions for site equipment."""
        # Simulate preventive maintenance schedule decision
        self.decisions.append(SimDecision(
            period=period,
            site_id=site.id,
            site_name=site.name,
            product_id=product_id,
            decision_type="maintenance",
            quantity=0,
            context={
                "maintenance_type": "preventive",
                "decision_type": "schedule",
                "asset_id": f"EQUIP-{site.name}-01",
                "estimated_downtime_hours": 4.0,
                "production_impact_units": 0,
                "risk_score_if_deferred": 0.15 + (period / 52.0) * 0.1,
                "confidence": 0.9,
            },
        ))

    def _generate_subcontracting_decision(
        self, site: Node, product_id: str, order_qty: float,
        sp: SiteProductState, period: int,
    ):
        """Generate subcontracting routing decision for manufacturer sites."""
        # Simulate capacity check: if order exceeds 80% of typical throughput, consider subcontracting
        typical_weekly = sp.target_inventory * 0.5 if sp.target_inventory > 0 else 100
        if order_qty <= typical_weekly * 0.8:
            return  # Within capacity
        internal_qty = typical_weekly * 0.8
        external_qty = order_qty - internal_qty
        self.decisions.append(SimDecision(
            period=period,
            site_id=site.id,
            site_name=site.name,
            product_id=product_id,
            decision_type="subcontracting",
            quantity=external_qty,
            context={
                "decision_type": "split",
                "internal_quantity": internal_qty,
                "external_quantity": external_qty,
                "reason": "capacity_constraint",
                "internal_capacity_pct": 0.8,
                "subcontractor_lead_time_days": 14,
                "confidence": 0.75,
            },
        ))

    def _generate_mo_decision(
        self, site: Node, product_id: str, order_qty: float,
        sp: SiteProductState, period: int,
    ):
        """Generate Manufacturing Order execution decision."""
        self.decisions.append(SimDecision(
            period=period,
            site_id=site.id,
            site_name=site.name,
            product_id=product_id,
            decision_type="mo_execution",
            quantity=order_qty,
            context={
                "decision_type": "release",
                "production_order_id": f"MO-{period:04d}-{product_id[:6]}",
                "sequence_position": 1,
                "expedite": sp.backlog > sp.safety_stock,
                "on_hand": sp.on_hand,
                "backlog": sp.backlog,
                "confidence": 0.85,
            },
        ))

    # ========================================================================
    # Ordering Heuristics
    # ========================================================================

    def _compute_order(
        self,
        site: Node,
        product_id: str,
        sp: SiteProductState,
        period: int,
        sim_date: date,
    ) -> float:
        """Compute order quantity using the configured heuristic strategy."""

        inventory_position = sp.on_hand + sp.in_transit - sp.backlog

        if self.strategy == OrderingStrategy.BASE_STOCK:
            return self._order_base_stock(sp, inventory_position)

        elif self.strategy == OrderingStrategy.CONSERVATIVE:
            return self._order_conservative(sp, inventory_position)

        elif self.strategy == OrderingStrategy.PID:
            return self._order_pid(sp, inventory_position)

        elif self.strategy == OrderingStrategy.EOQ:
            return self._order_eoq(sp, inventory_position, product_id)

        return max(0, sp.target_inventory - inventory_position)

    def _order_base_stock(
        self, sp: SiteProductState, inv_position: float
    ) -> float:
        """Base stock policy: order up to target inventory."""
        order = sp.target_inventory - inv_position
        return max(0, order)

    def _order_conservative(
        self, sp: SiteProductState, inv_position: float
    ) -> float:
        """Conservative: smoothed ordering based on recent demand average."""
        if len(sp.demand_history) < 2:
            return max(0, sp.target_inventory - inv_position)

        # Moving average of last 4 periods demand
        lookback = min(4, len(sp.demand_history))
        avg_demand = sum(sp.demand_history[-lookback:]) / lookback

        # Order to cover avg demand + replenish toward target
        gap = sp.target_inventory - inv_position
        bleed = 0.3  # Slow correction toward target
        order = avg_demand + bleed * gap

        return max(0, order)

    def _order_pid(
        self, sp: SiteProductState, inv_position: float
    ) -> float:
        """PID controller: proportional + integral + derivative on inventory error."""
        error = sp.target_inventory - inv_position

        sp.pid_integral += error
        # Anti-windup: clamp integral
        sp.pid_integral = max(-sp.target_inventory * 5, min(sp.target_inventory * 5, sp.pid_integral))

        derivative = error - sp.pid_prev_error
        sp.pid_prev_error = error

        # Demand anchor (recent average)
        if sp.demand_history:
            lookback = min(4, len(sp.demand_history))
            demand_anchor = sum(sp.demand_history[-lookback:]) / lookback
        else:
            demand_anchor = sp.target_inventory / 4  # Rough estimate

        control = (
            self.pid_kp * error
            + self.pid_ki * sp.pid_integral
            + self.pid_kd * derivative
        )

        order = demand_anchor + control
        return max(0, order)

    def _order_eoq(
        self, sp: SiteProductState, inv_position: float, product_id: str
    ) -> float:
        """EOQ: order in economic order quantities when below reorder point."""
        reorder_point = sp.safety_stock + sp.target_inventory * 0.3

        if inv_position > reorder_point:
            return 0.0

        # Approximate annual demand
        if len(sp.demand_history) >= 4:
            avg_weekly = sum(sp.demand_history[-4:]) / 4
        else:
            avg_weekly = sp.target_inventory / 4

        annual_demand = avg_weekly * 52
        ordering_cost = 100.0  # Fixed ordering cost
        holding_cost = self.holding_cost_rate * 52  # Annualized

        if holding_cost > 0 and annual_demand > 0:
            eoq = math.sqrt(2 * annual_demand * ordering_cost / holding_cost)
            return max(eoq, sp.target_inventory - inv_position)

        return max(0, sp.target_inventory - inv_position)

    # ========================================================================
    # Shipment Management
    # ========================================================================

    def _ship_downstream(
        self, source_site: Node, product_id: str, quantity: float, period: int
    ):
        """Create shipments to downstream sites."""
        topo = self.topology
        downstream = topo.downstream_map.get(source_site.name, [])

        if not downstream:
            return

        # Distribute proportionally to demand from each downstream site
        total_downstream_demand = 0.0
        ds_demands = {}
        for ds_name, lane in downstream:
            ds_state = self.state.get(ds_name, {}).get(product_id)
            if ds_state:
                demand = ds_state.demand_history[-1] if ds_state.demand_history else 0
                ds_demands[ds_name] = demand + ds_state.backlog
                total_downstream_demand += ds_demands[ds_name]
            else:
                ds_demands[ds_name] = 0

        if total_downstream_demand == 0:
            # Equal split if no demand info
            per_site = quantity / len(downstream)
            for ds_name, lane in downstream:
                lead_time_periods = max(1, self._lane_lead_time(lane) // 7)
                shipment = PipelineShipment(
                    product_id=product_id,
                    quantity=per_site,
                    ship_period=period,
                    arrival_period=period + lead_time_periods,
                    lane_id=lane.id,
                    order_type="transfer",
                )
                self.pipeline.append(shipment)
                self.all_shipments.append(shipment)
                # Track in-transit at target
                ds_sp = self.state.get(ds_name, {}).get(product_id)
                if ds_sp:
                    ds_sp.in_transit += per_site
                # Record TO decision
                self.decisions.append(SimDecision(
                    period=period,
                    site_id=source_site.id,
                    site_name=source_site.name,
                    product_id=product_id,
                    decision_type="transfer_order",
                    quantity=per_site,
                    context={
                        "dest_site": ds_name,
                        "transit_periods": lead_time_periods,
                        "trigger_reason": "demand_fulfillment",
                    },
                ))
        else:
            # Proportional distribution
            for ds_name, lane in downstream:
                share = ds_demands.get(ds_name, 0) / total_downstream_demand
                qty = quantity * share
                if qty <= 0:
                    continue

                lead_time_periods = max(1, self._lane_lead_time(lane) // 7)
                shipment = PipelineShipment(
                    product_id=product_id,
                    quantity=qty,
                    ship_period=period,
                    arrival_period=period + lead_time_periods,
                    lane_id=lane.id,
                    order_type="transfer",
                )
                self.pipeline.append(shipment)
                self.all_shipments.append(shipment)
                ds_sp = self.state.get(ds_name, {}).get(product_id)
                if ds_sp:
                    ds_sp.in_transit += qty
                # Record TO decision
                self.decisions.append(SimDecision(
                    period=period,
                    site_id=source_site.id,
                    site_name=source_site.name,
                    product_id=product_id,
                    decision_type="transfer_order",
                    quantity=qty,
                    context={
                        "dest_site": ds_name,
                        "demand_share": share,
                        "transit_periods": lead_time_periods,
                        "trigger_reason": "demand_fulfillment",
                    },
                ))

    def _place_order_upstream(
        self,
        site: Node,
        product_id: str,
        quantity: float,
        period: int,
        sim_date: date,
    ):
        """Place an order with upstream supplier(s)."""
        topo = self.topology
        upstream = topo.upstream_map.get(site.name, [])

        if not upstream:
            return

        # Find suppliers that carry this product
        eligible = []
        for us_name, lane in upstream:
            us_site = self._get_site(us_name)
            if us_site and _is_supply(us_site):
                # Check if supplier carries this product
                vendor_products = topo.vendor_lead_times.get(us_name, {})
                if product_id in vendor_products or not vendor_products:
                    eligible.append((us_name, lane))

        if not eligible:
            # Fall back to first upstream
            eligible = upstream[:1]

        # Single source: order from first eligible supplier
        us_name, lane = eligible[0]
        lead_time_days = topo.vendor_lead_times.get(us_name, {}).get(
            product_id, self._lane_lead_time(lane)
        )
        lead_time_periods = max(1, lead_time_days // 7)

        shipment = PipelineShipment(
            product_id=product_id,
            quantity=quantity,
            ship_period=period,
            arrival_period=period + lead_time_periods,
            lane_id=lane.id,
            order_type="purchase",
        )
        self.pipeline.append(shipment)
        self.all_shipments.append(shipment)

        # Track in-transit at ordering site
        sp = self.state[site.name].get(product_id)
        if sp:
            sp.in_transit += quantity

    # ========================================================================
    # Safety Stock Updates
    # ========================================================================

    def _update_safety_stock(
        self, site: Node, product_id: str, sp: SiteProductState
    ):
        """Periodically recalculate safety stock from demand history."""
        if len(sp.demand_history) < 4:
            return

        # Convert weekly to daily
        recent = sp.demand_history[-min(12, len(sp.demand_history)):]
        avg_weekly = np.mean(recent)
        std_weekly = np.std(recent) if len(recent) > 1 else avg_weekly * 0.2
        avg_daily = avg_weekly / 7.0
        std_daily = std_weekly / math.sqrt(7.0)

        # Get lead time for this product
        lead_time_days = 14  # Default
        for us_name, lane in self.topology.upstream_map.get(site.name, []):
            lt = self.topology.vendor_lead_times.get(us_name, {}).get(product_id)
            if lt:
                lead_time_days = lt
                break

        calculator = self._ss_calculators.get(site.name)
        if calculator:
            stats = DemandStats(
                avg_daily_demand=avg_daily,
                std_daily_demand=std_daily,
                avg_daily_forecast=avg_daily,
                std_daily_forecast=std_daily * 0.8,
                lead_time_days=lead_time_days,
                lead_time_std=lead_time_days * 0.15,
            )
            policy = SSPolicy(
                policy_type=PolicyType.SL,
                target_service_level=0.97,
            )
            result = calculator.compute_safety_stock(
                product_id=product_id,
                location_id=site.name,
                policy=policy,
                stats=stats,
            )
            sp.safety_stock = result.safety_stock
            sp.target_inventory = result.target_inventory

    # ========================================================================
    # State Recording
    # ========================================================================

    def _record_period_state(self, period: int):
        """Record state snapshot for all sites and products."""
        for site in self.topology.sites:
            for product in self.topology.products:
                pid = self._product_id(product)
                sp = self.state.get(site.name, {}).get(pid)
                if not sp:
                    continue

                incoming_demand = sp.demand_history[-1] if sp.demand_history else 0
                order_placed = sp.order_history[-1] if sp.order_history else 0

                fulfilled = min(sp.on_hand + incoming_demand, incoming_demand)  # Simplified

                self.period_states.append(SimPeriodState(
                    period=period,
                    site_id=site.id,
                    site_name=site.name,
                    product_id=pid,
                    on_hand=sp.on_hand,
                    backlog=sp.backlog,
                    in_transit=sp.in_transit,
                    incoming_demand=incoming_demand,
                    fulfilled_qty=fulfilled,
                    order_placed=order_placed,
                    holding_cost=max(0, sp.on_hand) * self.holding_cost_rate,
                    backlog_cost=max(0, sp.backlog) * self.backlog_cost_rate,
                    safety_stock=sp.safety_stock,
                ))

    # ========================================================================
    # KPI Computation
    # ========================================================================

    def _compute_kpis(self, num_periods: int) -> SimKPIs:
        """Compute aggregate KPIs from simulation history."""

        fill_rate = (
            self._total_fulfilled / self._total_demand
            if self._total_demand > 0
            else 1.0
        )

        # Compute average holding and backlog costs
        total_holding = sum(ps.holding_cost for ps in self.period_states)
        total_backlog = sum(ps.backlog_cost for ps in self.period_states)

        # Compute inventory turns (annualized)
        inv_sites = [s.name for s in self.topology.inventory_sites]
        total_throughput = 0.0
        total_avg_inventory = 0.0

        for site_name in inv_sites:
            for product in self.topology.products:
                pid = self._product_id(product)
                sp = self.state.get(site_name, {}).get(pid)
                if not sp:
                    continue

                throughput = sum(sp.demand_history) if sp.demand_history else 0
                avg_inv = np.mean(
                    [ps.on_hand for ps in self.period_states
                     if ps.site_name == site_name and ps.product_id == pid]
                ) if self.period_states else 0

                total_throughput += throughput
                total_avg_inventory += avg_inv

        turns = (
            (total_throughput / total_avg_inventory) * (52 / num_periods)
            if total_avg_inventory > 0
            else 0.0
        )

        # Bullwhip ratio
        all_demands = []
        all_orders = []
        for site_name in inv_sites:
            for product in self.topology.products:
                pid = self._product_id(product)
                sp = self.state.get(site_name, {}).get(pid)
                if sp:
                    all_demands.extend(sp.demand_history)
                    all_orders.extend(sp.order_history)

        demand_var = np.var(all_demands) if all_demands else 1
        order_var = np.var(all_orders) if all_orders else 0
        bullwhip = order_var / demand_var if demand_var > 0 else 1.0

        # Average days of supply
        avg_dos_values = []
        for site_name in inv_sites:
            for product in self.topology.products:
                pid = self._product_id(product)
                sp = self.state.get(site_name, {}).get(pid)
                if sp and sp.demand_history:
                    avg_demand = np.mean(sp.demand_history) / 7.0
                    if avg_demand > 0:
                        avg_dos_values.append(sp.on_hand / avg_demand)

        avg_dos = np.mean(avg_dos_values) if avg_dos_values else 0

        return SimKPIs(
            fill_rate=fill_rate,
            otif_rate=fill_rate * 0.95,  # Approximate OTIF
            avg_inventory_turns=turns,
            total_holding_cost=total_holding,
            total_backlog_cost=total_backlog,
            total_cost=total_holding + total_backlog,
            avg_days_of_supply=avg_dos,
            bullwhip_ratio=bullwhip,
        )

    def _build_history(self) -> Dict[str, Dict[str, List[Dict[str, float]]]]:
        """Build per-site per-product time series for training data."""
        history: Dict[str, Dict[str, List[Dict[str, float]]]] = {}

        for site in self.topology.sites:
            history[site.name] = {}
            for product in self.topology.products:
                pid = self._product_id(product)
                sp = self.state.get(site.name, {}).get(pid)
                if not sp:
                    continue

                # Build time series from period_states
                series = []
                for ps in self.period_states:
                    if ps.site_name == site.name and ps.product_id == pid:
                        series.append({
                            "period": ps.period,
                            "on_hand": ps.on_hand,
                            "backlog": ps.backlog,
                            "in_transit": ps.in_transit,
                            "demand": ps.incoming_demand,
                            "fulfilled": ps.fulfilled_qty,
                            "order_placed": ps.order_placed,
                            "holding_cost": ps.holding_cost,
                            "backlog_cost": ps.backlog_cost,
                            "safety_stock": ps.safety_stock,
                        })

                history[site.name][pid] = series

        return history

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_site(self, name: str) -> Optional[Node]:
        """Get site by name."""
        for s in self.topology.sites:
            if s.name == name:
                return s
        return None

    def _get_lane(self, lane_id: int) -> Optional[TransportationLane]:
        """Get lane by ID."""
        for l in self.topology.lanes:
            if l.id == lane_id:
                return l
        return None

    def _get_forecast(self, site_name: str, product_id: str, period: int) -> float:
        """Get forecast for a site-product at a given period."""
        site_forecasts = self.topology.forecasts.get(site_name, {})
        product_forecasts = site_forecasts.get(product_id, [])
        if product_forecasts and period < len(product_forecasts):
            return product_forecasts[period]
        elif product_forecasts:
            return product_forecasts[-1]  # Use last known forecast
        return 0.0

    def _product_id(self, product) -> str:
        """Extract product ID string."""
        if hasattr(product, 'product_id'):
            return str(product.product_id)
        if hasattr(product, 'id'):
            return str(product.id)
        return str(product)

    def _lane_lead_time(self, lane: TransportationLane) -> int:
        """Extract lead time in days from a lane."""
        if hasattr(lane, 'lead_time') and lane.lead_time:
            lt = lane.lead_time
            if isinstance(lt, dict):
                return int(lt.get('min', 7) + lt.get('max', 7)) // 2
            return int(lt)
        return 7  # Default 1 week

    def _find_shipment_target(self, shipment: PipelineShipment) -> Optional[str]:
        """Find which site a shipment is heading to."""
        lane = self._get_lane(shipment.lane_id)
        if lane:
            site_by_id = {s.id: s for s in self.topology.sites}
            target = site_by_id.get(lane.to_site_id)
            if target:
                return target.name
        return None


# ============================================================================
# Topology Helper Functions
# ============================================================================


def _is_supply(site: Node) -> bool:
    """Check if site is a supply source (VENDOR or legacy VENDOR)."""
    master = getattr(site, 'master_type', '') or ''
    node_type = getattr(site, 'node_type', '') or ''
    tpartner_type = getattr(site, 'tpartner_type', '') or ''
    return (
        master.upper() in ('VENDOR', 'VENDOR')
        or node_type.upper() in ('VENDOR', 'VENDOR')
        or tpartner_type.lower() == 'vendor'
        or 'SUPPLY' in master.upper()
    )


def _is_demand(site: Node) -> bool:
    """Check if site is a demand sink (CUSTOMER or legacy CUSTOMER)."""
    master = getattr(site, 'master_type', '') or ''
    node_type = getattr(site, 'node_type', '') or ''
    tpartner_type = getattr(site, 'tpartner_type', '') or ''
    return (
        master.upper() in ('CUSTOMER', 'CUSTOMER')
        or node_type.upper() in ('CUSTOMER', 'CUSTOMER')
        or tpartner_type.lower() == 'customer'
        or 'DEMAND' in master.upper()
    )


def _is_inventory(site: Node) -> bool:
    """Check if site is an inventory/processing node."""
    return not _is_supply(site) and not _is_demand(site)


def _topological_sort(
    sites: List[Node],
    lanes: List[TransportationLane],
    site_by_id: Dict[int, Node],
) -> List[str]:
    """
    Topological sort of sites in the DAG.
    Returns site names in upstream-first order (suppliers first, customers last).
    """
    # Build adjacency and in-degree
    in_degree: Dict[str, int] = {s.name: 0 for s in sites}
    adj: Dict[str, List[str]] = {s.name: [] for s in sites}

    for lane in lanes:
        source = site_by_id.get(lane.from_site_id)
        target = site_by_id.get(lane.to_site_id)
        if source and target:
            adj[source.name].append(target.name)
            in_degree[target.name] = in_degree.get(target.name, 0) + 1

    # Kahn's algorithm
    queue = [name for name, deg in in_degree.items() if deg == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If not all nodes processed, there's a cycle - add remaining
    remaining = [s.name for s in sites if s.name not in result]
    result.extend(remaining)

    return result


# ============================================================================
# Data Loading Helpers (async)
# ============================================================================


async def _load_forecasts(
    config_id: int,
    db: AsyncSession,
    sites: List[Node],
    products: List[Product],
) -> Dict[str, Dict[str, List[float]]]:
    """Load forecasts organized by site_name -> product_id -> weekly values."""
    forecasts: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    result = await db.execute(
        select(Forecast).where(Forecast.config_id == config_id)
    )
    db_forecasts = result.scalars().all()

    # Build site ID -> name lookup
    site_id_to_name = {s.id: s.name for s in sites}

    for f in db_forecasts:
        site_name = site_id_to_name.get(f.site_id, "")
        if site_name and f.product_id:
            # Use P50 (median) forecast value
            value = f.forecast_p50 if hasattr(f, 'forecast_p50') and f.forecast_p50 else (
                f.forecast_quantity if hasattr(f, 'forecast_quantity') else 0
            )
            forecasts[site_name][str(f.product_id)].append(float(value or 0))

    # If no DB forecasts, generate from product definitions
    if not db_forecasts:
        for site in sites:
            if _is_demand(site):
                for product in products:
                    pid = str(product.product_id) if hasattr(product, 'product_id') else str(product.id)
                    # Use product's base demand if available
                    base_demand = getattr(product, 'weekly_demand_mean', 100)
                    if hasattr(product, 'unit_cost') and product.unit_cost:
                        base_demand = max(10, 500 / product.unit_cost)  # Rough estimate
                    forecasts[site.name][pid] = [float(base_demand)] * 52

    return dict(forecasts)


async def _load_inv_policies(
    config_id: int,
    db: AsyncSession,
    sites: List[Node],
    products: List[Product],
) -> Dict[str, Dict[str, Dict]]:
    """Load inventory policies by site_name -> product_id -> policy params."""
    policies: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(dict))

    result = await db.execute(
        select(InvPolicy).where(InvPolicy.config_id == config_id)
    )
    db_policies = result.scalars().all()

    site_id_to_name = {s.id: s.name for s in sites}

    for p in db_policies:
        site_name = site_id_to_name.get(p.site_id, "")
        if site_name and p.product_id:
            policies[site_name][str(p.product_id)] = {
                "policy_type": p.policy_type if hasattr(p, 'policy_type') else "doc_fcst",
                "safety_stock_days": p.days_of_coverage if hasattr(p, 'days_of_coverage') else 14,
                "service_level": p.service_level if hasattr(p, 'service_level') else 0.97,
            }

    return dict(policies)


async def _load_initial_inventory(
    config_id: int,
    db: AsyncSession,
    sites: List[Node],
    products: List[Product],
) -> Dict[str, Dict[str, float]]:
    """Load initial inventory levels by site_name -> product_id -> qty."""
    inventory: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    result = await db.execute(
        select(InvLevel).where(InvLevel.config_id == config_id)
    )
    db_levels = result.scalars().all()

    site_id_to_name = {s.id: s.name for s in sites}

    for inv in db_levels:
        site_name = site_id_to_name.get(inv.site_id, "")
        if site_name and inv.product_id:
            qty = inv.on_hand_qty if hasattr(inv, 'on_hand_qty') else (
                inv.quantity if hasattr(inv, 'quantity') else 0
            )
            inventory[site_name][str(inv.product_id)] = float(qty or 0)

    # If no DB inventory, use reasonable defaults for inventory sites
    if not db_levels:
        for site in sites:
            if _is_inventory(site):
                for product in products:
                    pid = str(product.product_id) if hasattr(product, 'product_id') else str(product.id)
                    # Default: 3 weeks of estimated demand
                    base_demand = getattr(product, 'weekly_demand_mean', 100)
                    inventory[site.name][pid] = float(base_demand * 3)

    return dict(inventory)


async def _load_vendor_info(
    db: AsyncSession,
    supply_sites: List[Node],
    products: List[Product],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, float]]:
    """Load vendor lead times and reliability."""
    lead_times: Dict[str, Dict[str, int]] = defaultdict(dict)
    reliability: Dict[str, float] = {}

    # Try to load from VendorLeadTime table
    try:
        result = await db.execute(select(VendorLeadTime))
        vendor_lts = result.scalars().all()

        for vlt in vendor_lts:
            vendor_name = str(vlt.vendor_id) if hasattr(vlt, 'vendor_id') else ""
            pid = str(vlt.product_id) if hasattr(vlt, 'product_id') else ""
            lt = int(vlt.lead_time_days) if hasattr(vlt, 'lead_time_days') else 7
            if vendor_name and pid:
                lead_times[vendor_name][pid] = lt
    except Exception:
        pass

    # Try to load reliability from TradingPartner
    try:
        from app.models.sc_entities import TradingPartner
        result = await db.execute(
            select(TradingPartner).where(TradingPartner.tpartner_type == 'vendor')
        )
        vendors = result.scalars().all()
        for v in vendors:
            name = v.description or str(v.id)
            reliability[name] = 0.95  # Default
    except Exception:
        pass

    # Default for supply sites without vendor info
    for site in supply_sites:
        if site.name not in lead_times:
            lead_times[site.name] = {}
            for product in products:
                pid = str(product.product_id) if hasattr(product, 'product_id') else str(product.id)
                lead_times[site.name][pid] = 7  # Default 1 week

        if site.name not in reliability:
            reliability[site.name] = 0.95

    return dict(lead_times), dict(reliability)
