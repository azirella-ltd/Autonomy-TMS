"""
Network tGNN LP Oracle

Generates labeled training data for the Demand, Supply, and Inventory tGNNs
(Layer 2 — daily network-level planning agents) by solving a multi-period
multi-source network flow LP.

MOTIVATION (oracle training):
  The three tactical tGNNs (demand, supply, inventory) need to learn to
  route supply across a multi-echelon network. Supervised training requires
  optimal allocation labels. The LP oracle computes these labels:

    Given: network state (on-hand, forecasts, supply capacity, lane constraints)
    Solve: min ΣΣΣ cost(s,d,p,t) * x(s,d,p,t)   [total logistics + holding + stockout cost]
    s.t.:
      x(s,d,p,t) ≥ 0                              [non-negative flows]
      Σ_d x(s,d,p,t) ≤ supply_cap(s,p,t)          [source capacity]
      Σ_s x(s,d,p,t) ≥ demand(d,p,t) - slack(d,p,t)  [demand satisfaction]
      x(s,d,p,t) ≤ lane_cap(s,d)                  [lane capacity]

  The tGNN approximates the LP at millisecond inference speed, making it
  practical for thousands of SKU-site combinations in real-time.

LP SOLVER: scipy.optimize.linprog (simplex/HiGHS)
  - Scales to ≤20 sites × ≤20 products × ≤8 periods comfortably
  - For larger networks use chunked per-product solving (independent flows)

TRAINING DATA FORMAT:
  Each NetworkFlowSample contains:
    node_features: [num_sites, site_feature_dim]   per-site state
    edge_features: [num_lanes, lane_feature_dim]   per-lane attributes
    optimal_flows: [num_lanes, num_periods]         LP solution (labels)
    demand_targets: [num_sites, num_periods]        what demand looked like
    supply_plan:   [num_sites, num_periods]         LP-derived supply plan

USAGE:
    oracle = NetworkFlowOracle(seed=42)
    samples = oracle.generate_samples(
        num_scenarios=300,
        num_sites=8,
        num_products=3,
        num_periods=8,
    )
    # → List[NetworkFlowSample]  for tGNN supervised training
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from scipy.optimize import linprog
    SCIPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    SCIPY_AVAILABLE = False
    linprog = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SiteSpec:
    """Attributes of a supply chain site in the LP."""
    site_id: str
    master_type: str          # "MARKET_SUPPLY", "INVENTORY", "MANUFACTURER", "MARKET_DEMAND"
    supply_capacity: float    # Max units this site can supply per period
    demand_forecast: List[float]     # Demand per period (0 for supply-only sites)
    on_hand: float
    safety_stock: float
    holding_cost_per_unit: float
    stockout_cost_per_unit: float


@dataclass
class LaneSpec:
    """Transportation lane between two sites."""
    from_site: str
    to_site: str
    capacity: float           # Max units per period
    lead_time_periods: int    # Delivery delay (integer periods)
    cost_per_unit: float      # Variable transport cost


@dataclass
class NetworkScenario:
    """One randomly generated supply chain network state."""
    scenario_id: str
    sites: List[SiteSpec]
    lanes: List[LaneSpec]
    num_periods: int


@dataclass
class NetworkFlowSample:
    """
    One oracle-generated training sample for the network tGNN.

    node_features: [num_sites, site_feature_dim=12]
    edge_features: [num_lanes, lane_feature_dim=4]
    edge_index: [2, num_lanes]  source/dest indices (for PyG)
    optimal_flows: [num_lanes, num_periods]  LP solution (per-lane per-period flow)
    supply_plan: [num_sites, num_periods]   net supply arriving at each site
    demand_satisfaction: [num_sites, num_periods]  fraction of demand satisfied
    lp_objective: float  LP optimal cost (lower = better)
    lp_status: str  "optimal", "infeasible", "fallback_heuristic"
    """
    sample_id: str
    scenario: NetworkScenario
    node_features: np.ndarray
    edge_features: np.ndarray
    edge_index: np.ndarray
    optimal_flows: np.ndarray
    supply_plan: np.ndarray
    demand_satisfaction: np.ndarray
    lp_objective: float
    lp_status: str


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------

class NetworkFlowOracle:
    """
    Multi-period multi-source network flow LP oracle for tGNN training data generation.

    For each randomly generated network scenario, solves the LP to find optimal
    flow assignments, then packages the solution as a supervised training sample.

    The LP is solved independently per product (independent product flows) to keep
    matrix sizes tractable. This is exact when products don't share constrained capacity;
    for capacity-sharing scenarios use the joint LP variant.
    """

    SITE_FEATURE_DIM = 12
    LANE_FEATURE_DIM = 4

    def __init__(self, seed: Optional[int] = None) -> None:
        if not SCIPY_AVAILABLE:
            raise ImportError(
                "scipy is required for NetworkFlowOracle. "
                "Install with: pip install scipy"
            )
        self.rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_samples(
        self,
        num_scenarios: int = 300,
        num_sites: int = 8,
        num_products: int = 3,
        num_periods: int = 8,
        phases: Tuple[int, ...] = (1, 2, 3),
    ) -> List[NetworkFlowSample]:
        """
        Generate num_scenarios LP-labeled training samples.

        phases controls network complexity:
          1 = simple linear chains, low variability
          2 = branching networks, moderate variability
          3 = complex DAGs, disruptions, capacity constraints
        """
        samples: List[NetworkFlowSample] = []
        per_phase = num_scenarios // len(phases)

        for phase in phases:
            for _ in range(per_phase):
                scenario = self._sample_scenario(
                    num_sites=num_sites,
                    num_products=num_products,
                    num_periods=num_periods,
                    phase=phase,
                )
                sample = self._solve(scenario)
                samples.append(sample)

        self.rng.shuffle(samples)  # type: ignore[arg-type]
        logger.info(
            "NetworkFlowOracle generated %d samples (sites=%d, products=%d, periods=%d)",
            len(samples), num_sites, num_products, num_periods,
        )
        return samples

    # ------------------------------------------------------------------
    # LP solver
    # ------------------------------------------------------------------

    def _solve(self, scenario: NetworkScenario) -> NetworkFlowSample:
        """Solve the multi-period network flow LP and package as a training sample."""
        S = len(scenario.sites)
        L = len(scenario.lanes)
        T = scenario.num_periods

        site_idx: Dict[str, int] = {s.site_id: i for i, s in enumerate(scenario.sites)}

        # Aggregate solution holders
        optimal_flows = np.zeros((L, T), dtype=np.float32)
        supply_plan = np.zeros((S, T), dtype=np.float32)
        demand_satisfaction = np.zeros((S, T), dtype=np.float32)
        total_cost = 0.0
        lp_status = "optimal"

        # Solve LP per period (simplified — no carry-over inventory state)
        for t in range(T):
            flows_t, cost_t, status_t = self._solve_period_lp(scenario, site_idx, t)
            if status_t != "optimal":
                lp_status = "fallback_heuristic"

            for l_idx, lane in enumerate(scenario.lanes):
                optimal_flows[l_idx, t] = flows_t.get(l_idx, 0.0)

            # Compute supply arriving at each site (with lead time delay)
            for l_idx, lane in enumerate(scenario.lanes):
                dest_t = t + lane.lead_time_periods
                if dest_t < T:
                    supply_plan[site_idx[lane.to_site], dest_t] += optimal_flows[l_idx, t]

            # Compute demand satisfaction rate
            for site in scenario.sites:
                si = site_idx[site.site_id]
                demand_t = site.demand_forecast[t]
                if demand_t > 0:
                    supply_t = supply_plan[si, t] + site.on_hand / T
                    demand_satisfaction[si, t] = min(1.0, supply_t / demand_t)
                else:
                    demand_satisfaction[si, t] = 1.0

            total_cost += cost_t

        node_features, edge_features, edge_index = self._build_graph_features(scenario, site_idx)

        return NetworkFlowSample(
            sample_id=str(uuid.uuid4()),
            scenario=scenario,
            node_features=node_features,
            edge_features=edge_features,
            edge_index=edge_index,
            optimal_flows=optimal_flows,
            supply_plan=supply_plan,
            demand_satisfaction=demand_satisfaction,
            lp_objective=total_cost,
            lp_status=lp_status,
        )

    def _solve_period_lp(
        self,
        scenario: NetworkScenario,
        site_idx: Dict[str, int],
        period: int,
    ) -> Tuple[Dict[int, float], float, str]:
        """
        Solve the single-period flow LP.

        Decision variables: x[l] = flow on lane l in this period
        Objective: min Σ_l cost(l) * x[l] + Σ_s stockout_cost * max(0, demand-supply)

        Implemented as:
          variables: [x_0 .. x_{L-1}, slack_0 .. slack_{S-1}]
          x_l ≥ 0, slack_s ≥ 0
          objective: transport costs + stockout penalties on slacks
        """
        L = len(scenario.lanes)
        S = len(scenario.sites)
        N = L + S   # total variables: L flows + S demand slacks

        # Objective: transport cost for flows + stockout cost for slacks
        c = np.zeros(N, dtype=float)
        for l_idx, lane in enumerate(scenario.lanes):
            c[l_idx] = lane.cost_per_unit
        for s_idx, site in enumerate(scenario.sites):
            c[L + s_idx] = site.stockout_cost_per_unit

        # Bounds: flows in [0, lane_capacity], slacks in [0, demand]
        bounds: List[Tuple[float, float]] = []
        for lane in scenario.lanes:
            bounds.append((0.0, lane.capacity))
        for site in scenario.sites:
            demand_t = site.demand_forecast[period]
            bounds.append((0.0, max(demand_t, 0.0)))

        # Inequality constraints: Σ_outgoing(s) x_l ≤ supply_capacity(s,t)
        A_ub: List[List[float]] = []
        b_ub: List[float] = []

        for s_idx, site in enumerate(scenario.sites):
            if site.master_type in ("MARKET_SUPPLY", "MANUFACTURER"):
                row = [0.0] * N
                for l_idx, lane in enumerate(scenario.lanes):
                    if lane.from_site == site.site_id:
                        row[l_idx] = 1.0
                A_ub.append(row)
                b_ub.append(site.supply_capacity)

        # Lane capacity (redundant with bounds but explicit for clarity)
        for l_idx, lane in enumerate(scenario.lanes):
            row = [0.0] * N
            row[l_idx] = 1.0
            A_ub.append(row)
            b_ub.append(lane.capacity)

        # Equality constraints: demand satisfaction
        # Σ_incoming(d) x_l + slack_d ≥ demand(d,t)
        # Rewritten as: -Σ_incoming(d) x_l - slack_d ≤ -demand(d,t)
        for s_idx, site in enumerate(scenario.sites):
            demand_t = site.demand_forecast[period]
            if demand_t <= 0:
                continue
            row = [0.0] * N
            for l_idx, lane in enumerate(scenario.lanes):
                if lane.to_site == site.site_id:
                    row[l_idx] = -1.0
            row[L + s_idx] = -1.0   # slack variable
            A_ub.append(row)
            b_ub.append(-demand_t)

        if not A_ub:
            # No constraints — trivial solution
            return {}, 0.0, "optimal"

        result = linprog(
            c,
            A_ub=np.array(A_ub),
            b_ub=np.array(b_ub),
            bounds=bounds,
            method="highs",
        )

        if result.status == 0:
            flows = {l: float(result.x[l]) for l in range(L)}
            return flows, float(result.fun), "optimal"
        else:
            # Fallback: proportional heuristic allocation
            logger.debug("LP infeasible/unbounded (status=%d), using heuristic", result.status)
            flows = self._heuristic_allocation(scenario, site_idx, period)
            heuristic_cost = sum(
                flows.get(l, 0.0) * lane.cost_per_unit
                for l, lane in enumerate(scenario.lanes)
            )
            return flows, heuristic_cost, "fallback_heuristic"

    def _heuristic_allocation(
        self,
        scenario: NetworkScenario,
        site_idx: Dict[str, int],
        period: int,
    ) -> Dict[int, float]:
        """
        Simple proportional flow heuristic for infeasible LP cases.
        Allocates supply proportionally to demand at destination sites.
        """
        flows: Dict[int, float] = {}
        # Group lanes by source site
        source_lanes: Dict[str, List[int]] = {}
        for l_idx, lane in enumerate(scenario.lanes):
            source_lanes.setdefault(lane.from_site, []).append(l_idx)

        for site in scenario.sites:
            if site.master_type not in ("MARKET_SUPPLY", "MANUFACTURER"):
                continue
            outgoing = source_lanes.get(site.site_id, [])
            if not outgoing:
                continue

            # Compute demand weights for destinations
            dest_demands = []
            for l_idx in outgoing:
                lane = scenario.lanes[l_idx]
                dest_site = next((s for s in scenario.sites if s.site_id == lane.to_site), None)
                demand_t = dest_site.demand_forecast[period] if dest_site else 0.0
                dest_demands.append(demand_t)

            total_demand = sum(dest_demands) or 1.0
            available = site.supply_capacity

            for l_idx, demand_t in zip(outgoing, dest_demands):
                lane = scenario.lanes[l_idx]
                allocated = min(
                    available * (demand_t / total_demand),
                    lane.capacity,
                )
                flows[l_idx] = max(0.0, allocated)

        return flows

    # ------------------------------------------------------------------
    # Feature construction
    # ------------------------------------------------------------------

    def _build_graph_features(
        self,
        scenario: NetworkScenario,
        site_idx: Dict[str, int],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build PyG-compatible node features, edge features, and edge index.

        Node features [num_sites, 12]:
          0: on_hand (normalised)
          1: safety_stock (normalised)
          2: supply_capacity (normalised)
          3: avg_demand_forecast (normalised)
          4: demand_variability (std / mean)
          5: holding_cost_per_unit
          6: stockout_cost_per_unit
          7: is_supply_node (binary)
          8: is_demand_node (binary)
          9: is_manufacturer (binary)
         10: num_outgoing_lanes (normalised)
         11: num_incoming_lanes (normalised)

        Edge features [num_lanes, 4]:
          0: capacity (normalised)
          1: lead_time_periods (normalised)
          2: cost_per_unit (normalised)
          3: utilisation (0 initially, updated after LP)

        Edge index [2, num_lanes]: [from_idx, to_idx]
        """
        S = len(scenario.sites)
        L = len(scenario.lanes)

        # Normalisation anchors
        max_inv    = max((s.on_hand for s in scenario.sites), default=1.0) or 1.0
        max_cap    = max((s.supply_capacity for s in scenario.sites), default=1.0) or 1.0
        max_demand = max(
            (max(s.demand_forecast) for s in scenario.sites if s.demand_forecast),
            default=1.0,
        ) or 1.0
        max_hold   = max((s.holding_cost_per_unit for s in scenario.sites), default=1.0) or 1.0
        max_stock  = max((s.stockout_cost_per_unit for s in scenario.sites), default=1.0) or 1.0
        max_lane_cap  = max((la.capacity for la in scenario.lanes), default=1.0) or 1.0
        max_lead   = max((la.lead_time_periods for la in scenario.lanes), default=1.0) or 1.0
        max_cost   = max((la.cost_per_unit for la in scenario.lanes), default=1.0) or 1.0

        # Lane connectivity counts
        out_count = {s.site_id: 0 for s in scenario.sites}
        in_count  = {s.site_id: 0 for s in scenario.sites}
        for lane in scenario.lanes:
            out_count[lane.from_site] += 1
            in_count[lane.to_site]   += 1
        max_conn = max(max(out_count.values(), default=1), max(in_count.values(), default=1), 1)

        node_features = np.zeros((S, self.SITE_FEATURE_DIM), dtype=np.float32)
        for i, site in enumerate(scenario.sites):
            fcst = site.demand_forecast
            avg_fcst = float(np.mean(fcst)) if fcst else 0.0
            std_fcst = float(np.std(fcst)) if len(fcst) > 1 else 0.0
            variability = std_fcst / max(avg_fcst, 1e-6)

            node_features[i] = [
                site.on_hand / max_inv,
                site.safety_stock / max_inv,
                site.supply_capacity / max_cap,
                avg_fcst / max_demand,
                min(variability, 3.0) / 3.0,
                site.holding_cost_per_unit / max_hold,
                site.stockout_cost_per_unit / max_stock,
                float(site.master_type in ("MARKET_SUPPLY",)),
                float(site.master_type == "MARKET_DEMAND"),
                float(site.master_type == "MANUFACTURER"),
                out_count[site.site_id] / max_conn,
                in_count[site.site_id] / max_conn,
            ]

        edge_features = np.zeros((L, self.LANE_FEATURE_DIM), dtype=np.float32)
        edge_index = np.zeros((2, L), dtype=np.int64)
        for l_idx, lane in enumerate(scenario.lanes):
            from_i = site_idx[lane.from_site]
            to_i   = site_idx[lane.to_site]
            edge_index[:, l_idx] = [from_i, to_i]
            edge_features[l_idx] = [
                lane.capacity / max_lane_cap,
                lane.lead_time_periods / max(max_lead, 1.0),
                lane.cost_per_unit / max_cost,
                0.0,   # utilisation — filled after LP solve if needed
            ]

        return node_features, edge_features, edge_index

    # ------------------------------------------------------------------
    # Scenario sampling
    # ------------------------------------------------------------------

    def _sample_scenario(
        self,
        num_sites: int,
        num_products: int,
        num_periods: int,
        phase: int,
    ) -> NetworkScenario:
        """
        Generate a random but physically plausible supply chain network scenario.

        Phase controls network complexity:
          1 = simple linear chain (SUPPLY → INVENTORY → DEMAND)
          2 = branching (1 SUPPLY → 2-3 INVENTORY → multiple DEMAND)
          3 = complex DAG with multiple supply sources, cross-links, tight capacity
        """
        rng = self.rng
        variance_pct = {1: 0.15, 2: 0.40, 3: 0.75}[phase]

        # Assign site types
        n_supply = max(1, num_sites // 5)
        n_demand = max(1, num_sites // 4)
        n_mfg    = 1 if phase >= 2 else 0
        n_inv    = num_sites - n_supply - n_demand - n_mfg

        master_types: List[str] = (
            ["MARKET_SUPPLY"] * n_supply
            + ["MANUFACTURER"] * n_mfg
            + ["INVENTORY"] * max(n_inv, 1)
            + ["MARKET_DEMAND"] * n_demand
        )
        master_types = master_types[:num_sites]
        # Pad if needed
        while len(master_types) < num_sites:
            master_types.append("INVENTORY")

        # Import shared distribution library — ensures cross-tier consistency
        from app.services.powell.training_distributions import D

        def demand_profile() -> List[float]:
            # Triangular base demand (mode at mid-range), Triangular per-period jitter
            base = D.avg_weekly_demand(rng, nominal=150.0, variance_pct=variance_pct)
            return [
                D.realised_demand(rng, mean=base, cv=D.demand_variability_cv(rng, variance_pct))
                for _ in range(num_periods)
            ]

        sites: List[SiteSpec] = []
        for i, mtype in enumerate(master_types):
            site_id = f"SITE_{i:02d}"
            is_source = mtype in ("MARKET_SUPPLY", "MANUFACTURER")
            fcst = demand_profile() if mtype == "MARKET_DEMAND" else [0.0] * num_periods
            base_on_hand = 400.0
            sites.append(SiteSpec(
                site_id=site_id,
                master_type=mtype,
                supply_capacity=D.site_supply_capacity_units(rng, variance_pct) if is_source else 0.0,
                demand_forecast=fcst,
                on_hand=D.on_hand_inventory(rng, nominal=base_on_hand, variance_pct=variance_pct),
                safety_stock=D.on_hand_inventory(rng, nominal=base_on_hand * 0.25, variance_pct=variance_pct),
                holding_cost_per_unit=D.annual_holding_rate(rng) * D.unit_cost(rng) / 52.0,
                stockout_cost_per_unit=D.stockout_cost_per_unit(rng, variance_pct),
            ))

        # Generate lanes: sources → inventory → demand
        lanes: List[LaneSpec] = []
        supply_sites = [s.site_id for s in sites if s.master_type in ("MARKET_SUPPLY", "MANUFACTURER")]
        inv_sites    = [s.site_id for s in sites if s.master_type == "INVENTORY"]
        demand_sites = [s.site_id for s in sites if s.master_type == "MARKET_DEMAND"]

        def make_lane(from_site: str, to_site: str) -> LaneSpec:
            # Discrete Uniform for period-granularity lead time (exploring configurations)
            # Triangular for capacity and cost (Triangular has a mode)
            return LaneSpec(
                from_site=from_site,
                to_site=to_site,
                capacity=D.lane_capacity_units(rng, variance_pct),
                lead_time_periods=int(rng.integers(1, min(4, num_periods))),
                cost_per_unit=D.lane_transport_cost(rng),
            )

        # Supply → Inventory (or Supply → Demand if no inventory)
        middle = inv_sites if inv_sites else demand_sites
        for src in supply_sites:
            for dst in (middle[:3] if phase <= 2 else middle):
                lanes.append(make_lane(src, dst))

        # Inventory → Demand
        for src in inv_sites:
            for dst in demand_sites:
                lanes.append(make_lane(src, dst))

        # Phase 3: add cross-links between inventory nodes
        if phase == 3 and len(inv_sites) >= 2:
            for i in range(len(inv_sites) - 1):
                lanes.append(make_lane(inv_sites[i], inv_sites[i + 1]))

        return NetworkScenario(
            scenario_id=str(uuid.uuid4()),
            sites=sites,
            lanes=lanes,
            num_periods=num_periods,
        )
