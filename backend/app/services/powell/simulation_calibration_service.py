"""
Simulation Calibration Service

Bootstraps CDT (Conformal Decision Theory) calibration for all 11 TRM agents
immediately after provisioning warm-start, without waiting for real production
feedback horizons (4h–14 days per TRM type).

The Problem
-----------
TRM agents are trained in two phases:

  Phase 1 – Behavioral Cloning (BC): Expert heuristics make decisions.
    TRMs learn by watching ("AlphaZero learning from grandmaster games").
    Outcomes belong to the HEURISTIC, not the TRM.

  Phase 2 – RL fine-tuning: TRMs make decisions, receive rewards.
    Outcomes NOW belong to the TRM. This is where CDT should calibrate from.

CDT calibration requires (confidence, actual_loss) pairs from TRM decisions.
After provisioning, Phase 2 RL may not have enough history, so the CDT banner
shows "0/11 agents ready" for days or weeks.

The Solution
------------
Run the tenant's ACTUAL supply chain DAG as a digital twin simulation for N
episodes using deterministic heuristics per TRM type as expert demonstrators,
analogous to AlphaZero watching grandmaster games.

All simulation parameters come directly from the SC config:
  - Sites and DAG topology from `site` + `transportation_lane`
  - Demand mean and CV from `forecast` (per site, per product)
  - Lead time (mean + distribution) from `transportation_lane.supply_lead_time`
    and `supply_lead_time_dist`
  - Holding and backlog costs from `inv_policy.holding_cost_range` and
    `backlog_cost_range` (per site, per product)
  - Initial inventory from `inv_level` (latest snapshot per site+product)
  - Reorder point and order-up-to from `inv_policy.reorder_point` and
    `order_up_to_level`

Architecture
------------
Config DAG (loaded from DB):
    VENDOR(s) → [Manufacturer | Distributor | Wholesaler | Retailer] → CUSTOMER(s)

Only internal sites (is_external=False) are simulated as inventory nodes.
Demand enters at sites adjacent to CUSTOMER nodes.
Supply is unlimited at sites adjacent to VENDOR nodes.

Topological order (demand-source → supply-sink):
    Sites closest to CUSTOMER nodes are processed first each tick.
    Sites closest to VENDOR nodes are processed last.

Time bucket: 1 day (365 periods = 1 year per episode).
All costs and lead times from DB are converted to daily rates.

Total CDT pairs: 365 days × 50 episodes = 18,250 per TRM type (>> 30 minimum).
"""

import logging
import math
import random
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.services.powell.cdt_calibration_service import (
    CDTCalibrationService,
    TRM_COST_MAPPING,
)


# ---------------------------------------------------------------------------
# BSC weights (loaded from TenantBscConfig; defaults if not configured)
# ---------------------------------------------------------------------------

@dataclass
class _BscWeights:
    """
    Weighted Balanced Scorecard for CDT loss computation.

    Phase 1: holding_cost + backlog_cost.  Both are costs to MINIMISE —
    a higher value is a worse outcome.  Weights control relative importance.

    Constraint: all weights sum to 1.0.
    Default: equal split between holding and backlog costs.
    """
    holding_cost_weight: float = 0.5
    backlog_cost_weight: float = 0.5
    # Reserved Phase 2+ (always 0.0 until metrics are wired up)
    customer_weight: float = 0.0
    operational_weight: float = 0.0
    strategic_weight: float = 0.0

    @classmethod
    def default(cls) -> "_BscWeights":
        return cls()

    def bsc_loss(
        self,
        normalized_holding: float,
        normalized_backlog: float,
    ) -> float:
        """
        Compute the BSC loss as a weighted sum of cost components.

        Both inputs are in [0, 1] (normalised against max_cost_ref).
        Higher values = worse outcome = higher loss.
        """
        return min(
            1.0,
            self.holding_cost_weight * normalized_holding
            + self.backlog_cost_weight * normalized_backlog,
        )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults / limits
# ---------------------------------------------------------------------------

_DEFAULT_N_EPISODES = 50
_MIN_EPISODES = 10
_DEFAULT_PERIODS = 365          # 1 year at daily time bucket
_DEFAULT_TIME_BUCKET_DAYS = 1   # daily simulation

# Fallback cost rates when not found in InvPolicy (per unit per day)
_FALLBACK_HOLDING_RATE = 0.05
_FALLBACK_BACKLOG_RATE = 0.25

# Service level z-score for safety stock heuristic (95%)
_Z95 = 1.645

# Demand history window (days) for CV and EMA calculations
_HISTORY_WINDOW = 30

# Quality threshold for quality_disposition heuristic
_QUALITY_THRESHOLD = 0.95

# Maintenance thresholds
_MAINTENANCE_UTIL_THRESHOLD = 0.85
_MAINTENANCE_PM_INTERVAL_DAYS = 90

# Subcontracting capacity threshold
_SUBCONTRACTING_THRESHOLD = 0.90

# EMA alpha for forecast adjustment heuristic
_FORECAST_ALPHA = 0.20


# ---------------------------------------------------------------------------
# Site simulation configuration (loaded from SC config DB)
# ---------------------------------------------------------------------------

@dataclass
class _SiteSimConfig:
    """Parameters for one internal site, loaded directly from the SC config."""
    site_id: int
    site_name: str
    master_type: str            # INVENTORY or MANUFACTURER

    # Primary product for this site (from InvPolicy or Forecast)
    product_id: str

    # Demand (populated for demand-source sites adjacent to CUSTOMER nodes)
    is_demand_source: bool
    demand_mean_daily: float    # daily demand units
    demand_cv: float            # coefficient of variation

    # Lead time from the incoming transportation lane (days)
    lead_time_days: float
    lead_time_cv: float

    # Costs (per unit per day, converted from config time_bucket)
    holding_cost_daily: float
    backlog_cost_daily: float

    # Inventory policy
    initial_inventory: float
    reorder_point: float        # ROP in units
    order_up_to: float          # base-stock level in units
    safety_stock: float

    # DAG connections (internal site IDs only)
    upstream_site_id: Optional[int]   # site that supplies this site
    downstream_site_ids: List[int] = field(default_factory=list)

    # --- ERP heuristic dispatch (from SitePlanningConfig) ---
    # Default values ensure backward compatibility when no SitePlanningConfig exists.
    planning_method: str = "REORDER_POINT"
    lot_sizing_rule: str = "LOT_FOR_LOT"
    fixed_lot_size: float = 0.0
    min_order_quantity: float = 0.0
    max_order_quantity: float = 0.0
    order_multiple: float = 0.0
    max_inventory: float = 0.0       # for MIN_MAX / REPLENISH_TO_MAX
    review_period_days: int = 7
    frozen_horizon_days: int = 0
    forecast_daily: float = 0.0      # current-period forecast for forecast-based methods


# ---------------------------------------------------------------------------
# Stochastic generators
# ---------------------------------------------------------------------------

class _StochasticDemand:
    """Lognormal daily demand process."""

    def __init__(self, mean_daily: float, cv: float, seed: int = 0):
        self.mean = max(0.1, mean_daily)
        self.cv = max(0.05, cv)
        self._rng = random.Random(seed)

    def next(self) -> float:
        sigma = math.sqrt(math.log(1 + self.cv ** 2))
        mu = math.log(self.mean) - 0.5 * sigma ** 2
        return max(0.0, self._rng.lognormvariate(mu, sigma))


class _StochasticLeadTime:
    """Lead time sampler (integer days)."""

    def __init__(self, mean_days: float, cv: float, seed: int = 0):
        self.mean = max(1.0, mean_days)
        self.cv = max(0.0, cv)
        self._rng = random.Random(seed)

    def sample(self) -> int:
        if self.cv < 0.01:
            return max(1, round(self.mean))
        std = self.mean * self.cv
        return max(1, round(self._rng.gauss(self.mean, std)))


# ---------------------------------------------------------------------------
# Simulation site node
# ---------------------------------------------------------------------------

class _SimSite:
    """
    One internal supply chain site in the DAG simulation.

    Implements deterministic heuristics for each TRM type decision scope.
    All parameters come from _SiteSimConfig, which was loaded from the DB.
    """

    def __init__(self, cfg: _SiteSimConfig, seed: int = 0):
        self.cfg = cfg
        self.site_id = cfg.site_id
        self.name = cfg.site_name

        self.inventory = cfg.initial_inventory
        self.backlog = 0.0

        # In-transit pipeline: list of (quantity, remaining_lead_time_days)
        self._pipeline: List[Tuple[float, int]] = []

        # History for statistical signals
        self._demand_history: deque = deque(maxlen=_HISTORY_WINDOW)
        self._forecast: float = cfg.demand_mean_daily if cfg.demand_mean_daily > 0 else 1.0

        # Capacity state (for MO / maintenance / subcontracting heuristics)
        self._capacity_total: float = max(cfg.initial_inventory * 2.0, 100.0)
        self._capacity_used: float = self._capacity_total * 0.5
        self._days_since_pm: int = 0

        # Lead time sampler (uses lane's cv or default 0.20)
        self._lt_sampler = _StochasticLeadTime(
            mean_days=cfg.lead_time_days, cv=cfg.lead_time_cv, seed=seed
        )
        self._rng = random.Random(seed + 1)

        # Period metrics (reset each tick)
        self.period_demand: float = 0.0
        self.period_fill_rate: float = 1.0
        self.period_stockout: bool = False
        self.period_order_qty: float = 0.0
        self.period_holding_cost: float = 0.0
        self.period_backlog_cost: float = 0.0

    # ------------------------------------------------------------------
    # Tick operations
    # ------------------------------------------------------------------

    def advance_pipeline(self) -> float:
        """Decrement lead times; add arrived shipments to inventory."""
        received = 0.0
        remaining = []
        for qty, days_left in self._pipeline:
            if days_left <= 1:
                received += qty
            else:
                remaining.append((qty, days_left - 1))
        self._pipeline = remaining
        self.inventory += received
        return received

    def fulfill(self, demand: float) -> float:
        """
        FIFO fulfillment (ATP heuristic).
        Serves backlog + current demand; excess becomes backlog.
        """
        need = self.backlog + demand
        shipped = min(self.inventory, need)
        self.inventory -= shipped
        self.backlog = max(0.0, need - shipped)

        self.period_demand = demand
        self.period_fill_rate = shipped / max(need, 1e-9)
        self.period_stockout = self.backlog > 0

        self._demand_history.append(demand)
        self._update_forecast(demand)
        return shipped

    def compute_replenishment_order(self, sim_day: int = 0) -> float:
        """Dispatch to the correct ERP heuristic via heuristic_library.

        Uses SitePlanningConfig.planning_method and lot_sizing_rule
        loaded from the customer's ERP configuration.  Falls back to
        reorder-point (s,S) when no SitePlanningConfig exists (backward
        compatible).

        See DIGITAL_TWIN.md §8A for full algorithmic specification.
        """
        from app.services.powell.heuristic_library import (
            compute_replenishment, ReplenishmentState, ReplenishmentConfig,
        )

        state = ReplenishmentState(
            inventory_position=self.inventory_position,
            on_hand=self.inventory,
            backlog=self.backlog,
            pipeline_qty=sum(qty for qty, _ in self._pipeline),
            avg_daily_demand=self._forecast,
            demand_cv=self.cfg.demand_cv,
            lead_time_days=self.cfg.lead_time_days,
            forecast_daily=self.cfg.forecast_daily,
            day_of_week=sim_day % 7,
            day_of_month=(sim_day % 30) + 1,
        )

        config = ReplenishmentConfig(
            planning_method=self.cfg.planning_method,
            lot_sizing_rule=self.cfg.lot_sizing_rule,
            reorder_point=self.cfg.reorder_point,
            order_up_to=self.cfg.order_up_to,
            safety_stock=self.cfg.safety_stock,
            fixed_lot_size=self.cfg.fixed_lot_size,
            min_order_quantity=self.cfg.min_order_quantity,
            max_order_quantity=self.cfg.max_order_quantity,
            order_multiple=self.cfg.order_multiple,
            review_period_days=self.cfg.review_period_days,
            max_inventory=self.cfg.max_inventory,
        )

        order_qty = compute_replenishment(state, config)
        self.period_order_qty = order_qty
        return order_qty

    def place_order(self, qty: float) -> None:
        """Submit a replenishment order; arrives after stochastic lead time."""
        if qty > 0:
            self._pipeline.append((qty, self._lt_sampler.sample()))

    def receive_vendor_supply(self, qty: float) -> None:
        """For VENDOR-adjacent sites: immediate supply (vendor = infinite source)."""
        if qty > 0:
            self.inventory += qty

    def accrue_costs(self) -> Tuple[float, float]:
        hc = self.cfg.holding_cost_daily * max(self.inventory, 0.0)
        bc = self.cfg.backlog_cost_daily * max(self.backlog, 0.0)
        self.period_holding_cost = hc
        self.period_backlog_cost = bc
        return hc, bc

    # ------------------------------------------------------------------
    # Heuristic decision signals (one per TRM type)
    # ------------------------------------------------------------------

    def quality_outcome(self) -> Tuple[float, bool]:
        quality = min(1.0, self._rng.gauss(_QUALITY_THRESHOLD, 0.03))
        accepted = quality >= _QUALITY_THRESHOLD
        return quality, accepted

    def maintenance_decision(self) -> Tuple[float, bool]:
        self._days_since_pm += 1
        drift = self.period_demand * 0.1 + self._rng.gauss(0, self._capacity_total * 0.005)
        self._capacity_used = min(self._capacity_total, self._capacity_used + drift)
        utilization = self._capacity_used / max(self._capacity_total, 1.0)
        pm = (utilization > _MAINTENANCE_UTIL_THRESHOLD
              or self._days_since_pm >= _MAINTENANCE_PM_INTERVAL_DAYS)
        if pm:
            self._capacity_used *= 0.7
            self._days_since_pm = 0
        return utilization, pm

    def subcontracting_decision(self) -> Tuple[float, bool]:
        utilization = self._capacity_used / max(self._capacity_total, 1.0)
        return utilization, utilization > _SUBCONTRACTING_THRESHOLD

    def rebalancing_signal(self, network_avg_days_cover: float) -> Tuple[float, bool]:
        days_cover = self.inventory / max(self.avg_daily_demand, 0.01)
        imbalance = abs(days_cover - network_avg_days_cover) / max(network_avg_days_cover, 1.0)
        return imbalance, imbalance > 0.20

    def order_tracking_signal(self) -> Tuple[float, bool]:
        threshold = self.avg_daily_demand * self._lt_sampler.mean
        backlog_ratio = self.backlog / max(threshold, 1.0)
        return backlog_ratio, self.backlog > threshold

    def forecast_adjustment_signal(self) -> Tuple[float, float]:
        if not self._demand_history:
            return 0.0, self._forecast
        actual = self._demand_history[-1]
        error = abs(actual - self._forecast) / max(self._forecast, 0.01)
        return error, self._forecast

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def inventory_position(self) -> float:
        in_transit = sum(q for q, _ in self._pipeline)
        return self.inventory + in_transit - self.backlog

    @property
    def avg_daily_demand(self) -> float:
        h = list(self._demand_history)
        return statistics.mean(h) if h else max(self.cfg.demand_mean_daily, 0.01)

    @property
    def demand_cv(self) -> float:
        h = list(self._demand_history)
        if len(h) < 2:
            return self.cfg.demand_cv
        mean = statistics.mean(h)
        if mean <= 0:
            return self.cfg.demand_cv
        try:
            return statistics.stdev(h) / mean
        except statistics.StatisticsError:
            return self.cfg.demand_cv

    @property
    def total_period_cost(self) -> float:
        return self.period_holding_cost + self.period_backlog_cost

    def _update_forecast(self, actual: float) -> None:
        self._forecast = _FORECAST_ALPHA * actual + (1 - _FORECAST_ALPHA) * self._forecast


# ---------------------------------------------------------------------------
# DAG-based simulation chain
# ---------------------------------------------------------------------------

class _DagChain:
    """
    Simulates the actual supply chain DAG loaded from the SC config.

    Sites are processed in topological order (demand sources first).
    Demand enters at sites adjacent to CUSTOMER external nodes.
    Supply is unlimited at sites adjacent to VENDOR external nodes.
    """

    def __init__(
        self,
        site_configs: List[_SiteSimConfig],
        topo_order: List[int],
        seed: int = 0,
    ):
        self.nodes: Dict[int, _SimSite] = {
            cfg.site_id: _SimSite(cfg, seed=seed + cfg.site_id)
            for cfg in site_configs
        }
        self.topo_order = topo_order  # demand-source → supply-sink order
        self.site_configs: Dict[int, _SiteSimConfig] = {
            cfg.site_id: cfg for cfg in site_configs
        }
        # Demand generators for demand-source sites
        self.demand_gens: Dict[int, _StochasticDemand] = {
            cfg.site_id: _StochasticDemand(
                mean_daily=cfg.demand_mean_daily,
                cv=cfg.demand_cv,
                seed=seed + cfg.site_id * 100,
            )
            for cfg in site_configs
            if cfg.is_demand_source
        }

        # Max cost reference for loss normalisation
        max_demand = max(
            (c.demand_mean_daily for c in site_configs if c.demand_mean_daily > 0),
            default=10.0,
        )
        max_backlog_rate = max(
            (c.backlog_cost_daily for c in site_configs if c.backlog_cost_daily > 0),
            default=_FALLBACK_BACKLOG_RATE,
        )
        max_lt = max((c.lead_time_days for c in site_configs if c.lead_time_days > 0), default=7.0)
        self._max_cost_ref = max_demand * max_backlog_rate * max_lt * 2.0
        self._day_counter = 0

    def tick(
        self,
        policy: Any = None,
        policy_site_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute one daily time step across the DAG.

        Args:
            policy: Optional DecisionPolicy. When provided AND policy_site_id
                matches the current site, ``policy.decide(node, cfg, ctx)``
                is called instead of ``node.compute_replenishment_order()``.
                All other sites continue to use the default heuristic.
                Default ``None`` preserves existing behavior.
            policy_site_id: The site ID to which the policy applies.  If
                ``None``, the policy applies to ALL sites.
        """
        self._day_counter += 1

        # Step 1: All sites receive arriving shipments
        for node in self.nodes.values():
            node.advance_pipeline()

        # Step 2: Process demand source-to-sink (topological order)
        # demand_source sites get external demand
        # upstream sites get orders forwarded from their downstream sites
        pending_demand: Dict[int, float] = defaultdict(float)

        # Tick context made available to policy.decide()
        tick_context: Dict[str, Any] = {
            "day": self._day_counter,
            "network_size": len(self.nodes),
        }

        for site_id in self.topo_order:
            node = self.nodes[site_id]
            cfg = self.site_configs[site_id]

            # Demand at this site
            if cfg.is_demand_source:
                demand = self.demand_gens[site_id].next()
            else:
                demand = pending_demand.get(site_id, 0.0)

            # Fulfill demand (FIFO ATP heuristic)
            node.fulfill(demand)

            # Compute replenishment order:
            # Use policy.decide() when a policy is provided and this site matches
            use_policy = (
                policy is not None
                and (policy_site_id is None or policy_site_id == site_id)
            )
            if use_policy:
                order_qty = policy.decide(node, cfg, tick_context)
                node.period_order_qty = order_qty
            else:
                order_qty = node.compute_replenishment_order(sim_day=self._day_counter)

            # Route order upstream
            if cfg.upstream_site_id and cfg.upstream_site_id in self.nodes:
                node.place_order(order_qty)
                pending_demand[cfg.upstream_site_id] += order_qty
            else:
                # No internal upstream → VENDOR-adjacent; receive immediately
                node.receive_vendor_supply(order_qty)

        # Step 3: Accrue costs at all sites
        for node in self.nodes.values():
            node.accrue_costs()

        # Network aggregates
        sites = list(self.nodes.values())
        total_holding = sum(s.period_holding_cost for s in sites)
        total_backlog = sum(s.period_backlog_cost for s in sites)
        total_cost = total_holding + total_backlog

        fill_rates = [s.period_fill_rate for s in sites]
        avg_fill_rate = statistics.mean(fill_rates) if fill_rates else 1.0

        demand_cvs = [s.demand_cv for s in sites if len(s._demand_history) >= 2]
        avg_demand_cv = statistics.mean(demand_cvs) if demand_cvs else 0.3

        inventories = [s.inventory for s in sites]
        demands = [s.avg_daily_demand for s in sites]
        days_cover_list = [
            inv / max(d, 0.01)
            for inv, d in zip(inventories, demands)
        ]
        network_avg_days_cover = statistics.mean(days_cover_list) if days_cover_list else 7.0

        return {
            "total_cost": total_cost,
            "total_holding": total_holding,
            "total_backlog": total_backlog,
            "avg_fill_rate": avg_fill_rate,
            "avg_demand_cv": avg_demand_cv,
            "any_stockout": any(s.period_stockout for s in sites),
            "network_avg_days_cover": network_avg_days_cover,
            "sites": sites,
            "max_cost_ref": self._max_cost_ref,
        }


# ---------------------------------------------------------------------------
# Per-TRM (confidence, loss) derivation
# ---------------------------------------------------------------------------

def _derive_trm_pairs(
    tick_result: Dict[str, Any],
    bsc: "_BscWeights",
) -> Dict[str, Tuple[float, float]]:
    """
    Map one daily tick's supply chain outcomes to one (confidence, loss) pair
    per TRM type, using the tenant's BSC weights.

    confidence = how predictable / stable the system is (drives TRM certainty)
    loss       = BSC-weighted cost outcome (both costs are to be MINIMISED;
                 higher cost = higher loss)

    The BSC loss is the primary cost signal shared across all TRM types.
    Each TRM type uses it as its base loss, adjusted by a scope-specific
    signal that reflects which cost component is most relevant to that agent.
    """
    avg_fill = tick_result["avg_fill_rate"]
    demand_cv = tick_result["avg_demand_cv"]
    total_holding = tick_result["total_holding"]
    total_backlog_cost = tick_result["total_backlog"]
    max_cost_ref = max(tick_result["max_cost_ref"], 1.0)
    any_stockout = tick_result["any_stockout"]
    network_avg_days_cover = tick_result["network_avg_days_cover"]
    sites: List[_SimSite] = tick_result["sites"]

    # Use first site as the primary demand-facing node (topologically first = retailer)
    primary = sites[0]
    # Use last site as the manufacturing/upstream node
    upstream = sites[-1]
    # Middle site for transfer signals
    mid = sites[len(sites) // 2]

    # Normalised cost components — both are costs to MINIMISE
    norm_holding = min(1.0, total_holding / max_cost_ref)
    norm_backlog = min(1.0, total_backlog_cost / max_cost_ref)

    # BSC-weighted aggregate loss (Phase 1: holding + backlog, equal default weight)
    bsc_loss = bsc.bsc_loss(norm_holding, norm_backlog)

    total_demand = sum(s.avg_daily_demand for s in sites)
    total_backlog_units = sum(s.backlog for s in sites)
    backlog_ratio = min(1.0, total_backlog_units / max(total_demand, 1.0))

    # Base confidence: network fill rate, demand predictability, BSC cost stability
    fill_cmp = avg_fill
    cv_cmp = max(0.0, 1.0 - demand_cv * 1.5)
    cost_cmp = max(0.0, 1.0 - bsc_loss)
    base_conf = 0.75 * (0.5 * fill_cmp + 0.3 * cv_cmp + 0.2 * cost_cmp)
    base_conf = min(0.95, max(0.05, base_conf))

    pairs: Dict[str, Tuple[float, float]] = {}

    # atp_executor: FIFO service quality — primarily a backlog-cost signal
    # Backlog is the direct cost of unfulfilled ATP promises (to minimise)
    atp_loss = bsc.bsc_loss(norm_holding * 0.2, norm_backlog)
    pairs["atp"] = (
        min(0.95, max(0.05, primary.period_fill_rate * 0.85 + 0.10)),
        atp_loss,
    )

    # po_creation: replenishment timing — both costs equally relevant
    pairs["po_creation"] = (base_conf, bsc_loss)

    # inventory_rebalancing: imbalance amplifies holding cost at overstocked sites
    imbalance, _ = primary.rebalancing_signal(network_avg_days_cover)
    rebalance_loss = bsc.bsc_loss(norm_holding * (1 + imbalance), norm_backlog)
    pairs["inventory_rebalancing"] = (
        min(0.95, max(0.05, 1.0 - imbalance * 0.5)),
        min(1.0, rebalance_loss),
    )

    # order_tracking: late detection = backlog persists longer (backlog cost)
    ot_loss = bsc.bsc_loss(norm_holding * 0.3, min(1.0, norm_backlog + backlog_ratio * 0.3))
    pairs["order_tracking"] = (
        min(0.95, max(0.05, avg_fill * 0.80 + 0.15)),
        min(1.0, ot_loss),
    )

    # mo_execution: manufacturing delays raise backlog cost at downstream sites
    mo_loss = bsc.bsc_loss(norm_holding * 0.3, norm_backlog)
    pairs["mo_execution"] = (
        min(0.95, max(0.05, upstream.period_fill_rate * 0.80 + 0.10)),
        mo_loss,
    )

    # to_execution: transfer delays raise both holding (idle stock) and backlog
    pairs["to_execution"] = (
        min(0.95, max(0.05, mid.period_fill_rate * 0.80 + 0.10)),
        bsc_loss,
    )

    # quality_disposition: quality failures drive backlog (rejected batches = shortage)
    quality_val, accepted = upstream.quality_outcome()
    quality_loss = bsc.bsc_loss(norm_holding * 0.2, norm_backlog if not accepted else 0.0)
    pairs["quality_disposition"] = (
        min(0.95, max(0.05, quality_val * 0.90 + 0.05)),
        quality_loss if accepted else min(1.0, quality_loss + (1.0 - quality_val) * 0.5),
    )

    # maintenance_scheduling: deferred PM → capacity loss → backlog cost
    utilization, pm_done = upstream.maintenance_decision()
    util_excess = max(0.0, utilization - _MAINTENANCE_UTIL_THRESHOLD)
    maint_loss = bsc.bsc_loss(norm_holding * 0.2, min(1.0, norm_backlog + util_excess))
    pairs["maintenance_scheduling"] = (
        min(0.95, max(0.05, 1.0 - utilization * 0.5)),
        min(1.0, maint_loss),
    )

    # subcontracting: unnecessary external routing raises unit cost (→ holding cost proxy)
    util_sub, subcontracted = upstream.subcontracting_decision()
    sub_holding_adj = norm_holding * (1.3 if subcontracted else 1.0)
    sub_loss = bsc.bsc_loss(min(1.0, sub_holding_adj), norm_backlog)
    pairs["subcontracting"] = (
        min(0.95, max(0.05, 1.0 - util_sub * 0.4)),
        min(1.0, sub_loss),
    )

    # forecast_adjustment: poor forecast inflates safety stock (holding) and
    # stockouts (backlog); error drives both components
    forecast_error, _ = primary.forecast_adjustment_signal()
    fa_loss = bsc.bsc_loss(
        min(1.0, norm_holding * (1 + forecast_error)),
        min(1.0, norm_backlog * (1 + forecast_error)),
    )
    pairs["forecast_adjustment"] = (
        min(0.95, max(0.05, 1.0 - demand_cv)),
        min(1.0, fa_loss),
    )

    # inventory_buffer: buffer levels directly set holding vs backlog trade-off
    # Buffer too low → backlog cost; buffer too high → holding cost
    stockout_boost = 0.4 if any_stockout else 0.0
    ib_loss = bsc.bsc_loss(norm_holding, min(1.0, norm_backlog + stockout_boost))
    pairs["inventory_buffer"] = (
        min(0.95, max(0.05, avg_fill * 0.85 + 0.10)),
        min(1.0, ib_loss),
    )

    return pairs


# ---------------------------------------------------------------------------
# DB topology loader
# ---------------------------------------------------------------------------

class _ConfigLoader:
    """
    Loads the supply chain DAG parameters from the SC config DB records.

    Returns a list of _SiteSimConfig (one per internal site) and the
    topological sort order for the simulation.
    """

    def __init__(self, db: Session, config_id: int):
        self.db = db
        self.config_id = config_id

    def load(self) -> Tuple[List[_SiteSimConfig], List[int]]:
        """
        Returns (site_configs, topo_order).

        site_configs: one _SiteSimConfig per internal site
        topo_order:   site IDs from demand-source to supply-sink
        """
        from app.models.supply_chain_config import Site, TransportationLane, SupplyChainConfig
        from app.models.sc_entities import Forecast, InvPolicy, InvLevel, Product

        config = self.db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == self.config_id
        ).first()
        if not config:
            raise ValueError(f"SupplyChainConfig {self.config_id} not found")

        # Config time_bucket determines forecast frequency → daily conversion factor
        tb = getattr(config, "time_bucket", None)
        tb_name = tb.value if tb is not None else "week"
        if tb_name == "day":
            bucket_days = 1
        elif tb_name == "month":
            bucket_days = 30
        else:
            bucket_days = 7  # default: week

        # --- Load all sites for this config ---
        all_sites: List[Site] = (
            self.db.query(Site)
            .filter(Site.config_id == self.config_id)
            .all()
        )

        # Separate internal vs external
        internal_sites = [s for s in all_sites if not s.is_external]
        external_site_ids: Set[int] = {s.id for s in all_sites if s.is_external}
        # Distinguish customer-type vs vendor-type external nodes
        customer_ext_ids: Set[int] = {
            s.id for s in all_sites if s.is_external and s.tpartner_type == "customer"
        }
        vendor_ext_ids: Set[int] = {
            s.id for s in all_sites if s.is_external and s.tpartner_type == "vendor"
        }

        if not internal_sites:
            raise ValueError(
                f"Config {self.config_id} has no internal sites to simulate"
            )

        # --- Load all transportation lanes ---
        lanes: List[TransportationLane] = (
            self.db.query(TransportationLane)
            .filter(TransportationLane.config_id == self.config_id)
            .all()
        )

        # Build adjacency: internal site → upstream internal site
        # Lane direction: from_site_id (upstream/supplier) → to_site_id (downstream/customer)
        # so for each internal to_site_id, the upstream is from_site_id
        upstream_of: Dict[int, Optional[int]] = {}   # to_site_id → from_site_id (internal only)
        downstream_of: Dict[int, Set[int]] = defaultdict(set)  # from_site_id → {to_site_id}
        demand_sources: Set[int] = set()   # internal sites that ship to CUSTOMER externals
        vendor_adjacent: Set[int] = set()  # internal sites that receive from VENDOR externals

        # Lead times per (to_site_id): populated from incoming lane
        lane_lead_times: Dict[int, Tuple[float, float]] = {}  # site_id → (mean_days, cv)

        for lane in lanes:
            from_id = lane.from_site_id
            to_id = lane.to_site_id
            from_partner = lane.from_partner_id
            to_partner = lane.to_partner_id

            # Internal → internal lane
            if from_id and to_id and from_id not in external_site_ids and to_id not in external_site_ids:
                upstream_of[to_id] = from_id
                downstream_of[from_id].add(to_id)
                # Lead time for the to_site (material travels FROM upstream TO here)
                lt_mean, lt_cv = self._parse_lead_time(lane)
                lane_lead_times[to_id] = (lt_mean * bucket_days, lt_cv)

            # VENDOR (external partner) → internal site
            elif from_partner and to_id and to_id not in external_site_ids:
                vendor_adjacent.add(to_id)
                lt_mean, lt_cv = self._parse_lead_time(lane)
                lane_lead_times[to_id] = (lt_mean * bucket_days, lt_cv)

            # Internal site → CUSTOMER external partner
            elif from_id and to_partner and from_id not in external_site_ids:
                demand_sources.add(from_id)

            # External VENDOR site → internal site (is_external=True VENDOR node)
            elif from_id and from_id in vendor_ext_ids and to_id and to_id not in external_site_ids:
                vendor_adjacent.add(to_id)
                lt_mean, lt_cv = self._parse_lead_time(lane)
                lane_lead_times[to_id] = (lt_mean * bucket_days, lt_cv)

            # Internal site → external CUSTOMER site
            elif from_id and to_id and to_id in customer_ext_ids and from_id not in external_site_ids:
                demand_sources.add(from_id)

        # Fallback: if no demand sources found, treat sites with no downstream
        # internal sites as demand sources
        if not demand_sources:
            all_internal_ids = {s.id for s in internal_sites}
            for sid in all_internal_ids:
                if not downstream_of.get(sid):
                    demand_sources.add(sid)

        # --- Topological sort (demand-source first, supply-sink last) ---
        topo_order = self._topological_sort(
            internal_sites=[s.id for s in internal_sites],
            upstream_of=upstream_of,
            demand_sources=demand_sources,
        )

        # --- Per-site: load primary product and parameters ---
        site_configs: List[_SiteSimConfig] = []

        for site in internal_sites:
            sid = site.id

            # Primary product: first from InvPolicy, else first from Forecast
            product_id = self._get_primary_product(sid)

            # Demand params from Forecast (for demand-source sites) or 0
            demand_mean_daily, demand_cv = self._get_demand_params(
                site_id=sid,
                product_id=product_id,
                bucket_days=bucket_days,
                is_demand_source=(sid in demand_sources),
            )

            # Lead time from incoming lane
            lt_days, lt_cv = lane_lead_times.get(sid, (7.0, 0.20))

            # Costs from InvPolicy (per unit per day)
            holding_daily, backlog_daily = self._get_cost_rates(
                site_id=sid,
                product_id=product_id,
                bucket_days=bucket_days,
            )

            # Initial inventory from InvLevel or compute from SS
            initial_inv = self._get_initial_inventory(sid, product_id)

            # Reorder point and order-up-to from InvPolicy
            rop, out, ss = self._get_policy_levels(
                site_id=sid,
                product_id=product_id,
                demand_mean_daily=demand_mean_daily,
                demand_cv=demand_cv,
                lt_days=lt_days,
            )
            if initial_inv <= 0:
                initial_inv = out  # start at order-up-to if no inventory snapshot

            # --- Load ERP heuristic config from SitePlanningConfig ---
            from app.models.site_planning_config import SitePlanningConfig

            spc = (
                self.db.query(SitePlanningConfig)
                .filter(
                    SitePlanningConfig.config_id == self.config_id,
                    SitePlanningConfig.site_id == sid,
                    SitePlanningConfig.product_id == product_id,
                )
                .first()
            )
            # Defaults to REORDER_POINT / LOT_FOR_LOT when no SPC exists (backward compat)
            planning_method = spc.planning_method if spc else "REORDER_POINT"
            lot_sizing_rule = spc.lot_sizing_rule if spc else "LOT_FOR_LOT"
            fixed_lot_size = (spc.fixed_lot_size or 0.0) if spc else 0.0
            moq = (spc.min_order_quantity or 0.0) if spc else 0.0
            max_oq = (spc.max_order_quantity or 0.0) if spc else 0.0
            order_mult = (spc.order_multiple or 0.0) if spc else 0.0
            max_inv = max_oq  # approximate — MIN_MAX uses this as target
            review_days = int(spc.planning_time_fence_days or 7) if spc else 7
            frozen_days = int(spc.frozen_horizon_days or 0) if spc else 0

            cfg = _SiteSimConfig(
                site_id=sid,
                site_name=site.name,
                master_type=site.master_type or "INVENTORY",
                product_id=product_id,
                is_demand_source=(sid in demand_sources),
                demand_mean_daily=demand_mean_daily,
                demand_cv=demand_cv,
                lead_time_days=max(1.0, lt_days),
                lead_time_cv=lt_cv,
                holding_cost_daily=holding_daily,
                backlog_cost_daily=backlog_daily,
                initial_inventory=initial_inv,
                reorder_point=rop,
                order_up_to=out,
                safety_stock=ss,
                upstream_site_id=upstream_of.get(sid),
                downstream_site_ids=list(downstream_of.get(sid, set())),
                # ERP heuristic dispatch fields
                planning_method=planning_method,
                lot_sizing_rule=lot_sizing_rule,
                fixed_lot_size=fixed_lot_size,
                min_order_quantity=moq,
                max_order_quantity=max_oq,
                order_multiple=order_mult,
                max_inventory=max_inv,
                review_period_days=review_days,
                frozen_horizon_days=frozen_days,
                forecast_daily=demand_mean_daily,
            )
            site_configs.append(cfg)

        logger.debug(
            "CDT bootstrap: loaded %d internal sites from config %d "
            "(%d demand sources, %d vendor-adjacent, topo_order=%s)",
            len(site_configs),
            self.config_id,
            len(demand_sources),
            len(vendor_adjacent),
            topo_order,
        )

        return site_configs, topo_order

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _parse_lead_time(self, lane) -> Tuple[float, float]:
        """
        Extract (mean, cv) from a TransportationLane.

        Prefers supply_lead_time_dist (stochastic spec) over supply_lead_time
        (deterministic). Values are in the config's time bucket units (usually
        weeks) — the caller multiplies by bucket_days.
        """
        # Try stochastic distribution spec first
        dist = getattr(lane, "supply_lead_time_dist", None)
        if dist and isinstance(dist, dict):
            mean = float(dist.get("mean", dist.get("value", 1.0)))
            stddev = float(dist.get("stddev", dist.get("std", 0.0)))
            cv = stddev / mean if mean > 0 else 0.20
            return mean, min(cv, 1.0)

        # Fall back to deterministic supply_lead_time
        lt = getattr(lane, "supply_lead_time", None)
        if lt is None:
            return 1.0, 0.20
        if isinstance(lt, dict):
            val = lt.get("value") or lt.get("mean") or lt.get("min") or 1.0
            return float(val), 0.20
        if isinstance(lt, (int, float)):
            return float(lt), 0.20
        return 1.0, 0.20

    def _get_primary_product(self, site_id: int) -> str:
        """Return the primary product_id for this site from InvPolicy or Forecast."""
        from app.models.sc_entities import InvPolicy, Forecast

        row = (
            self.db.query(InvPolicy.product_id)
            .filter(
                InvPolicy.config_id == self.config_id,
                InvPolicy.site_id == site_id,
                InvPolicy.product_id.isnot(None),
            )
            .first()
        )
        if row and row.product_id:
            return row.product_id

        row = (
            self.db.query(Forecast.product_id)
            .filter(
                Forecast.config_id == self.config_id,
                Forecast.site_id == site_id,
                Forecast.product_id.isnot(None),
            )
            .first()
        )
        if row and row.product_id:
            return row.product_id

        return "PRIMARY"

    def _get_demand_params(
        self,
        site_id: int,
        product_id: str,
        bucket_days: int,
        is_demand_source: bool,
    ) -> Tuple[float, float]:
        """
        Load demand mean (daily) and CV from Forecast records.
        Demand params are only meaningful for demand-source sites.
        """
        from app.models.sc_entities import Forecast

        if not is_demand_source:
            return 0.0, 0.30

        rows = (
            self.db.query(
                Forecast.forecast_p50,
                Forecast.forecast_p10,
                Forecast.forecast_p90,
            )
            .filter(
                Forecast.config_id == self.config_id,
                Forecast.site_id == site_id,
                Forecast.product_id == product_id,
                Forecast.forecast_p50.isnot(None),
            )
            .order_by(Forecast.forecast_date.desc())
            .limit(52)
            .all()
        )

        if not rows:
            # Try config-level forecast (no site_id filter)
            rows = (
                self.db.query(
                    Forecast.forecast_p50,
                    Forecast.forecast_p10,
                    Forecast.forecast_p90,
                )
                .filter(
                    Forecast.config_id == self.config_id,
                    Forecast.forecast_p50.isnot(None),
                )
                .order_by(Forecast.forecast_date.desc())
                .limit(52)
                .all()
            )

        if not rows:
            return 10.0, 0.30

        p50_vals = [float(r.forecast_p50) for r in rows if r.forecast_p50 and r.forecast_p50 > 0]
        if not p50_vals:
            return 10.0, 0.30

        # Convert from bucket frequency to daily
        demand_mean_daily = statistics.mean(p50_vals) / bucket_days

        # CV from p10/p90 spread  (≈ ±1.28σ for Normal → σ ≈ (p90-p10)/2.56)
        spreads = []
        for r in rows:
            if r.forecast_p10 and r.forecast_p90 and r.forecast_p50 and r.forecast_p50 > 0:
                spread = (float(r.forecast_p90) - float(r.forecast_p10)) / (
                    2.56 * float(r.forecast_p50)
                )
                spreads.append(max(0.05, min(1.0, spread)))
        demand_cv = statistics.mean(spreads) if spreads else 0.30

        return max(0.01, demand_mean_daily), demand_cv

    def _get_cost_rates(
        self,
        site_id: int,
        product_id: str,
        bucket_days: int,
    ) -> Tuple[float, float]:
        """
        Load holding and backlog cost per unit per day from InvPolicy.

        InvPolicy.holding_cost_range and backlog_cost_range are JSON with
        {"min": X, "max": Y} representing cost per unit per config time bucket.
        Use mean of min/max and convert to daily rate.
        """
        from app.models.sc_entities import InvPolicy, Product

        def _mean_of_range(rng) -> Optional[float]:
            if not rng or not isinstance(rng, dict):
                return None
            lo = rng.get("min") or rng.get("low") or rng.get("value")
            hi = rng.get("max") or rng.get("high") or rng.get("value")
            if lo is not None and hi is not None:
                return (float(lo) + float(hi)) / 2.0
            if lo is not None:
                return float(lo)
            if hi is not None:
                return float(hi)
            return None

        # Try product+site specific policy first, then site-only, then config-level
        for filters in [
            (InvPolicy.site_id == site_id, InvPolicy.product_id == product_id),
            (InvPolicy.site_id == site_id,),
            (InvPolicy.config_id == self.config_id,),
        ]:
            policy = (
                self.db.query(InvPolicy)
                .filter(InvPolicy.config_id == self.config_id, *filters)
                .first()
            )
            if not policy:
                continue

            holding_per_bucket = _mean_of_range(getattr(policy, "holding_cost_range", None))
            backlog_per_bucket = _mean_of_range(getattr(policy, "backlog_cost_range", None))

            if holding_per_bucket is not None and backlog_per_bucket is not None:
                return (
                    holding_per_bucket / bucket_days,
                    backlog_per_bucket / bucket_days,
                )
            if holding_per_bucket is not None:
                return (
                    holding_per_bucket / bucket_days,
                    (holding_per_bucket * 4.0) / bucket_days,
                )

        # Fallback: derive from Product.unit_cost (25% annual holding rate)
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if product and product.unit_cost:
            holding_daily = float(product.unit_cost) * 0.25 / 365.0
            return holding_daily, holding_daily * 4.0

        return _FALLBACK_HOLDING_RATE, _FALLBACK_BACKLOG_RATE

    def _get_initial_inventory(self, site_id: int, product_id: str) -> float:
        """Latest on-hand inventory from InvLevel, or 0 if not found."""
        from app.models.sc_entities import InvLevel

        row = (
            self.db.query(InvLevel.on_hand_qty)
            .filter(
                InvLevel.site_id == site_id,
                InvLevel.product_id == product_id,
            )
            .order_by(InvLevel.inventory_date.desc())
            .first()
        )
        if row and row.on_hand_qty is not None:
            return max(0.0, float(row.on_hand_qty))
        return 0.0

    def _get_policy_levels(
        self,
        site_id: int,
        product_id: str,
        demand_mean_daily: float,
        demand_cv: float,
        lt_days: float,
    ) -> Tuple[float, float, float]:
        """
        Load (reorder_point, order_up_to_level, safety_stock) from InvPolicy.

        Falls back to heuristic computation if not set:
          safety_stock = z95 × σ_demand × √lead_time
          reorder_point = SS + avg_daily_demand × lead_time
          order_up_to   = ROP + avg_daily_demand × review_period (default 7 days)
        """
        from app.models.sc_entities import InvPolicy

        # Heuristic defaults
        std_daily = demand_mean_daily * demand_cv
        ss_heuristic = _Z95 * std_daily * math.sqrt(max(lt_days, 1.0))
        rop_heuristic = ss_heuristic + demand_mean_daily * lt_days
        out_heuristic = rop_heuristic + demand_mean_daily * 7.0  # 7-day review cycle

        policy = (
            self.db.query(InvPolicy)
            .filter(
                InvPolicy.config_id == self.config_id,
                InvPolicy.site_id == site_id,
                InvPolicy.product_id == product_id,
            )
            .first()
        )
        if not policy:
            policy = (
                self.db.query(InvPolicy)
                .filter(
                    InvPolicy.config_id == self.config_id,
                    InvPolicy.site_id == site_id,
                )
                .first()
            )

        if not policy:
            return rop_heuristic, out_heuristic, ss_heuristic

        # Use explicit policy values where available
        ss = float(policy.ss_quantity) if policy.ss_quantity else ss_heuristic
        rop = float(policy.reorder_point) if policy.reorder_point else (
            ss + demand_mean_daily * lt_days
        )
        out = float(policy.order_up_to_level) if policy.order_up_to_level else (
            rop + demand_mean_daily * max(float(policy.review_period or 7), 1.0)
        )

        return rop, out, ss

    @staticmethod
    def _topological_sort(
        internal_sites: List[int],
        upstream_of: Dict[int, Optional[int]],
        demand_sources: Set[int],
    ) -> List[int]:
        """
        Kahn's algorithm: demand-source sites first, supply-sink sites last.

        In supply chain DAG terms:
          - "in-degree" here = number of internal DOWNSTREAM sites that depend on this site
          - Sites with no dependants (demand sources / retailers) come first
          - Sites depended on by many come last (manufacturers / supply sinks)
        """
        site_set = set(internal_sites)

        # Build forward graph: upstream → downstream (demand flows upstream for orders,
        # material flows downstream for fulfillment). For simulation tick order we
        # process demand sources first; they push orders upstream.
        # So topo order = demand sources → ... → supply sinks
        # In the upstream_of dict: upstream_of[child] = parent
        # We want to visit child before parent.

        # Build in-degree count in "parent first" sense is wrong;
        # we want children first. Use upstream_of to build children mapping.
        children: Dict[int, Set[int]] = defaultdict(set)  # parent → {children}
        for child, parent in upstream_of.items():
            if child in site_set and parent and parent in site_set:
                children[parent].add(child)

        # in-degree = number of parents (upstream sites) in the internal site set
        in_degree: Dict[int, int] = {sid: 0 for sid in internal_sites}
        for child, parent in upstream_of.items():
            if child in site_set and parent and parent in site_set:
                in_degree[child] += 1

        # Kahn: start from sites with no internal upstream (demand sources / retailers)
        queue = [sid for sid in internal_sites if in_degree[sid] == 0]
        # Prefer demand_sources first
        queue.sort(key=lambda sid: (0 if sid in demand_sources else 1))

        order: List[int] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            # Visit children (upstream sites)
            for upstream_sid in [upstream_of.get(node)] if upstream_of.get(node) else []:
                if upstream_sid not in site_set:
                    continue
                in_degree[upstream_sid] -= 1
                if in_degree[upstream_sid] == 0:
                    queue.append(upstream_sid)

        # Append any remaining sites (cycles or disconnected)
        remaining = [sid for sid in internal_sites if sid not in order]
        order.extend(remaining)

        return order


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class SimulationCalibrationService:
    """
    Bootstrap CDT calibration from the tenant's actual supply chain DAG.

    Loads the real topology (sites, transportation lanes, inventory policies,
    forecasts, inventory levels) from the SC config and runs a daily
    simulation for N episodes (default 50) × 365 days = 18,250 CDT pairs
    per TRM type.

    All parameters come from the SC config — no hardcoded values.
    """

    def __init__(self, db: Session, config_id: int, tenant_id: int):
        self.db = db
        self.config_id = config_id
        self.tenant_id = tenant_id
        self._cdt_service = CDTCalibrationService(db=db, tenant_id=tenant_id)

    def _load_bsc_weights(self) -> _BscWeights:
        """Return default BSC weights (0.5/0.5 holding/backlog).

        These weights are internal to the simulation calibration service.
        TenantBscConfig no longer carries cost weight columns.
        """
        return _BscWeights.default()

    def bootstrap_calibration(
        self,
        n_episodes: int = _DEFAULT_N_EPISODES,
        periods_per_episode: int = _DEFAULT_PERIODS,
        time_bucket_days: int = _DEFAULT_TIME_BUCKET_DAYS,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run DAG simulation and calibrate all 11 CDT wrappers.

        Args:
            n_episodes:          Number of independent simulation episodes.
            periods_per_episode: Days per episode (default 365 = 1 year).
            time_bucket_days:    Time bucket in days (default 1 = daily).
            force:               Re-calibrate even if already calibrated.
        """
        n_episodes = max(_MIN_EPISODES, n_episodes)

        if not force:
            diag = self._cdt_service.get_all_diagnostics()
            if diag and all(
                d.get("is_calibrated", False)
                for d in diag.values()
                if isinstance(d, dict)
            ):
                logger.info(
                    "CDT simulation bootstrap skipped — all %d wrappers already calibrated",
                    len(diag),
                )
                return {"status": "already_calibrated", "skipped": True}

        # Load the actual supply chain DAG from the config
        loader = _ConfigLoader(db=self.db, config_id=self.config_id)
        try:
            site_configs, topo_order = loader.load()
        except Exception as exc:
            logger.error(
                "CDT bootstrap: failed to load DAG for config %d — %s",
                self.config_id,
                exc,
                exc_info=True,
            )
            return {"status": "error", "error": str(exc)}

        # Summarize loaded params for the log
        demand_sources = [c for c in site_configs if c.is_demand_source]
        avg_demand = statistics.mean(
            [c.demand_mean_daily for c in demand_sources]
        ) if demand_sources else 0.0
        avg_lt = statistics.mean(
            [c.lead_time_days for c in site_configs]
        ) if site_configs else 0.0

        # Load BSC weights — all costs are to be MINIMISED
        bsc = self._load_bsc_weights()

        logger.info(
            "CDT simulation bootstrap: %d episodes × %d days (1-day bucket) "
            "| %d internal sites | avg_demand=%.2f/d avg_lead_time=%.1fd "
            "| BSC weights holding=%.2f backlog=%.2f "
            "| config_id=%d tenant_id=%d",
            n_episodes,
            periods_per_episode,
            len(site_configs),
            avg_demand,
            avg_lt,
            bsc.holding_cost_weight,
            bsc.backlog_cost_weight,
            self.config_id,
            self.tenant_id,
        )

        simulation_pairs = self._run_episodes(
            site_configs=site_configs,
            topo_order=topo_order,
            n_episodes=n_episodes,
            periods_per_episode=periods_per_episode,
            bsc=bsc,
        )

        stats = self._cdt_service.calibrate_from_simulation(simulation_pairs)

        calibrated = sum(1 for s in stats.values() if s.get("status") == "calibrated")
        total = len(stats)

        logger.info(
            "CDT simulation bootstrap complete: %d/%d agents calibrated "
            "(%d pairs per agent)",
            calibrated,
            total,
            n_episodes * periods_per_episode,
        )

        return {
            "status": "complete",
            "agents_calibrated": calibrated,
            "agents_total": total,
            "per_agent": stats,
            "episodes_run": n_episodes,
            "periods_per_episode": periods_per_episode,
            "time_bucket_days": time_bucket_days,
            "sites_simulated": len(site_configs),
            "site_names": [c.site_name for c in site_configs],
            "bsc_weights": {
                "holding_cost_weight": bsc.holding_cost_weight,
                "backlog_cost_weight": bsc.backlog_cost_weight,
            },
        }

    def _run_episodes(
        self,
        site_configs: List[_SiteSimConfig],
        topo_order: List[int],
        n_episodes: int,
        periods_per_episode: int,
        bsc: "_BscWeights",
    ) -> Dict[str, List[Tuple[float, float]]]:
        """Run N independent episodes; collect {trm_type: [(confidence, loss)]}."""
        pairs: Dict[str, List[Tuple[float, float]]] = {k: [] for k in TRM_COST_MAPPING}

        for episode in range(n_episodes):
            seed = episode * 137 + self.config_id
            chain = _DagChain(
                site_configs=site_configs,
                topo_order=topo_order,
                seed=seed,
            )
            for _period in range(periods_per_episode):
                tick_result = chain.tick()
                for trm_type, (conf, loss) in _derive_trm_pairs(tick_result, bsc).items():
                    if trm_type in pairs:
                        pairs[trm_type].append((conf, loss))

        return pairs


# ---------------------------------------------------------------------------
# Convenience wrapper (called from provisioning_service.py)
# ---------------------------------------------------------------------------

def run_simulation_calibration_bootstrap(
    db: Session,
    config_id: int,
    tenant_id: int,
    n_episodes: int = _DEFAULT_N_EPISODES,
    time_bucket_days: int = _DEFAULT_TIME_BUCKET_DAYS,
    periods_per_episode: int = _DEFAULT_PERIODS,
    force: bool = False,
) -> Dict[str, Any]:
    """Synchronous convenience wrapper for the provisioning step."""
    svc = SimulationCalibrationService(db=db, config_id=config_id, tenant_id=tenant_id)
    return svc.bootstrap_calibration(
        n_episodes=n_episodes,
        periods_per_episode=periods_per_episode,
        time_bucket_days=time_bucket_days,
        force=force,
    )
