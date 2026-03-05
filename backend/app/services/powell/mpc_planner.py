"""
Model Predictive Control (MPC) as Powell's Direct Lookahead Approximation (DLA)

MPC solves a finite-horizon optimization at each decision point,
then executes only the first-period decisions. This is repeated
at each time step (receding horizon).

Powell classifies MPC as a Direct Lookahead Approximation (DLA):
- Explicitly models future uncertainty through scenarios
- Optimizes over the lookahead horizon
- Executes first-period decisions

Phase 3: Tactical Level (MPS/Supply Planning)

Key Features:
- Deterministic MPC (using mean forecasts)
- Stochastic MPC (using scenario tree)
- Rolling horizon implementation
- Integration with GNN forecasts

References:
- Powell (2022) Sequential Decision Analytics, Chapter on DLA
- Rawlings & Mayne (2009). Model Predictive Control: Theory and Design
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

try:
    import cvxpy as cp
    CVXPY_AVAILABLE = True
except ImportError:
    CVXPY_AVAILABLE = False
    cp = None

logger = logging.getLogger(__name__)


@dataclass
class MPCState:
    """
    State for MPC planning.

    Contains current inventory, pipeline, and capacity information.
    """
    inventory: Dict[str, float]  # product_id -> quantity
    pipeline: Dict[str, List[float]]  # product_id -> [arrivals by period]
    backlog: Dict[str, float]  # product_id -> quantity
    capacity: Dict[str, float]  # resource_id -> available capacity

    # Optional work-in-progress (for manufacturing)
    wip: Optional[Dict[str, float]] = None

    # Current period
    current_period: int = 0

    def get_inventory_position(self, product_id: str) -> float:
        """Get inventory position (inventory + pipeline - backlog)"""
        inv = self.inventory.get(product_id, 0)
        pipe = sum(self.pipeline.get(product_id, []))
        back = self.backlog.get(product_id, 0)
        return inv + pipe - back


@dataclass
class MPCForecast:
    """
    Forecast for MPC planning.

    Contains demand forecasts with uncertainty quantification.
    """
    demand_mean: Dict[str, List[float]]  # product_id -> [demand by period]
    demand_p90: Optional[Dict[str, List[float]]] = None  # P90 for uncertainty
    demand_p10: Optional[Dict[str, List[float]]] = None  # P10 for uncertainty
    lead_time_mean: Optional[Dict[str, float]] = None  # supplier_id -> mean lead time
    lead_time_std: Optional[Dict[str, float]] = None

    def get_demand_uncertainty(self, product_id: str, period: int) -> float:
        """Get demand uncertainty (width of prediction interval)"""
        if self.demand_p90 is None or self.demand_p10 is None:
            return 0.0

        p90_list = self.demand_p90.get(product_id, [])
        p10_list = self.demand_p10.get(product_id, [])

        if period < len(p90_list) and period < len(p10_list):
            return p90_list[period] - p10_list[period]
        return 0.0


@dataclass
class MPCDecision:
    """
    First-period decisions from MPC.

    Only the first-period decisions are executed; the rest are
    re-planned in the next iteration (receding horizon).
    """
    production_quantities: Dict[str, float]  # product_id -> quantity
    purchase_orders: Dict[str, float]  # supplier_product_id -> quantity
    transfer_orders: Dict[Tuple[str, str, str], float]  # (product, from_site, to_site) -> qty

    # Additional decisions
    inventory_targets: Optional[Dict[str, float]] = None
    capacity_allocations: Optional[Dict[str, Dict[str, float]]] = None

    # Planning metadata
    objective_value: float = 0.0
    solve_status: str = "unknown"
    horizon_values: Optional[List[float]] = None  # Objective by period

    def to_dict(self) -> Dict[str, Any]:
        return {
            "production_quantities": self.production_quantities,
            "purchase_orders": self.purchase_orders,
            "transfer_orders": {
                f"{p}_{f}_{t}": q
                for (p, f, t), q in self.transfer_orders.items()
            },
            "objective_value": self.objective_value,
            "solve_status": self.solve_status,
        }


class MPCSupplyPlanner:
    """
    Model Predictive Control for supply planning.

    Solves a rolling-horizon optimization problem at each period.
    This is Powell's DLA (Direct Lookahead Approximation).

    The key insight: Instead of learning a value function (VFA),
    we explicitly model the future and optimize over it (DLA).
    """

    def __init__(
        self,
        horizon: int = 12,
        holding_cost: float = 0.0,
        backlog_cost: float = 0.0,
        production_cost: float = 1.0,
        expediting_cost: float = 5.0,
        use_scenarios: bool = True,
        n_scenarios: int = 10,
        safety_stock_periods: float = 2.0
    ):
        """
        Initialize MPC planner.

        Args:
            horizon: Planning horizon (periods)
            holding_cost: Per-unit per-period inventory holding cost.
                          Load from InvPolicy.holding_cost_range['min'] or
                          product.unit_cost * 0.25 / 52 before constructing.
            backlog_cost: Per-unit per-period backlog cost.
                          Load from InvPolicy.backlog_cost_range['min'] or
                          holding_cost * 4 before constructing.
            production_cost: Cost per unit produced
            expediting_cost: Premium for expedited production/delivery
            use_scenarios: Whether to use stochastic MPC
            n_scenarios: Number of scenarios for stochastic MPC
            safety_stock_periods: Target safety stock in periods of demand
        """
        if holding_cost == 0.0:
            import warnings
            warnings.warn(
                "MPCSupplyPlanner.holding_cost is 0.0 (unset). "
                "Load from InvPolicy.holding_cost_range['min'] for the config/product.",
                stacklevel=2,
            )
        if backlog_cost == 0.0:
            import warnings
            warnings.warn(
                "MPCSupplyPlanner.backlog_cost is 0.0 (unset). "
                "Load from InvPolicy.backlog_cost_range['min'] for the config/product.",
                stacklevel=2,
            )
        self.horizon = horizon
        self.holding_cost = holding_cost
        self.backlog_cost = backlog_cost
        self.production_cost = production_cost
        self.expediting_cost = expediting_cost
        self.use_scenarios = use_scenarios
        self.n_scenarios = n_scenarios
        self.safety_stock_periods = safety_stock_periods

        # Solver settings
        self.solver_timeout = 30  # seconds
        self.mip_gap = 0.01  # 1% optimality gap acceptable

    def plan(
        self,
        state: MPCState,
        forecast: MPCForecast,
        products: List[str],
        resources: Optional[List[str]] = None
    ) -> MPCDecision:
        """
        Solve MPC problem and return first-period decisions.

        Objective: Minimize expected cost over horizon
        Constraints:
        - Inventory balance
        - Capacity constraints
        - Non-negativity

        Args:
            state: Current supply chain state
            forecast: Demand forecasts
            products: List of product IDs
            resources: List of resource IDs (optional)

        Returns:
            MPCDecision with first-period decisions
        """
        resources = resources or list(state.capacity.keys())

        if self.use_scenarios and forecast.demand_p90 is not None:
            return self._plan_stochastic(state, forecast, products, resources)
        else:
            return self._plan_deterministic(state, forecast, products, resources)

    def _plan_deterministic(
        self,
        state: MPCState,
        forecast: MPCForecast,
        products: List[str],
        resources: List[str]
    ) -> MPCDecision:
        """
        Deterministic MPC using mean forecasts.

        Solves a linear/quadratic program to minimize cost.
        """
        if not CVXPY_AVAILABLE:
            logger.warning("CVXPY not available, using heuristic")
            return self._plan_heuristic(state, forecast, products)

        n_products = len(products)
        H = self.horizon

        try:
            # Decision variables
            production = cp.Variable((n_products, H), nonneg=True)
            inventory = cp.Variable((n_products, H + 1), nonneg=True)
            backlog = cp.Variable((n_products, H + 1), nonneg=True)

            constraints = []

            # Initial conditions
            for i, prod in enumerate(products):
                constraints.append(inventory[i, 0] == state.inventory.get(prod, 0))
                constraints.append(backlog[i, 0] == state.backlog.get(prod, 0))

            # Inventory balance constraints
            for t in range(H):
                for i, prod in enumerate(products):
                    demand = self._get_demand(forecast, prod, t)
                    pipeline_arrival = self._get_pipeline_arrival(state, prod, t)

                    # Flow balance: inv[t+1] - back[t+1] = inv[t] - back[t] + prod + pipe - demand
                    constraints.append(
                        inventory[i, t + 1] - backlog[i, t + 1] ==
                        inventory[i, t] - backlog[i, t] + production[i, t] + pipeline_arrival - demand
                    )

            # Capacity constraints
            if resources:
                total_capacity = sum(state.capacity.get(r, 100) for r in resources)
                for t in range(H):
                    constraints.append(cp.sum(production[:, t]) <= total_capacity)

            # Objective: minimize total cost
            holding_costs = self.holding_cost * cp.sum(inventory)
            backlog_costs = self.backlog_cost * cp.sum(backlog)
            production_costs = self.production_cost * cp.sum(production)

            objective = cp.Minimize(holding_costs + backlog_costs + production_costs)

            # Solve
            problem = cp.Problem(objective, constraints)
            problem.solve(solver=cp.ECOS, verbose=False)

            if problem.status not in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
                logger.warning(f"MPC solve failed with status: {problem.status}")
                return self._plan_heuristic(state, forecast, products)

            # Extract first-period decisions
            first_period_production = {
                products[i]: max(0, float(production.value[i, 0]))
                for i in range(n_products)
            }

            return MPCDecision(
                production_quantities=first_period_production,
                purchase_orders={},
                transfer_orders={},
                objective_value=float(problem.value),
                solve_status=problem.status,
            )

        except Exception as e:
            logger.error(f"MPC optimization failed: {e}")
            return self._plan_heuristic(state, forecast, products)

    def _plan_stochastic(
        self,
        state: MPCState,
        forecast: MPCForecast,
        products: List[str],
        resources: List[str]
    ) -> MPCDecision:
        """
        Stochastic MPC using scenario tree.

        Generates scenarios from demand distributions and solves
        a scenario-averaged optimization problem.

        This is Powell's DLA with explicit uncertainty modeling.
        """
        # Generate scenarios
        scenarios = self._generate_scenarios(forecast, products)

        # Solve scenario-averaged problem
        total_production = {prod: 0.0 for prod in products}
        scenario_objectives = []

        for scenario_demand in scenarios:
            # Create modified forecast with this scenario
            scenario_forecast = MPCForecast(
                demand_mean=scenario_demand,
                demand_p90=forecast.demand_p90,
                demand_p10=forecast.demand_p10,
                lead_time_mean=forecast.lead_time_mean,
            )

            decision = self._plan_deterministic(state, scenario_forecast, products, resources)
            scenario_objectives.append(decision.objective_value)

            for prod, qty in decision.production_quantities.items():
                total_production[prod] += qty / len(scenarios)

        # Average production across scenarios
        avg_production = {prod: qty for prod, qty in total_production.items()}

        return MPCDecision(
            production_quantities=avg_production,
            purchase_orders={},
            transfer_orders={},
            objective_value=float(np.mean(scenario_objectives)),
            solve_status="optimal_stochastic",
            horizon_values=scenario_objectives,
        )

    def _generate_scenarios(
        self,
        forecast: MPCForecast,
        products: List[str]
    ) -> List[Dict[str, List[float]]]:
        """
        Generate demand scenarios for stochastic MPC.

        Samples from distribution implied by mean and P90.
        """
        scenarios = []

        for _ in range(self.n_scenarios):
            scenario = {}
            for prod in products:
                mean = forecast.demand_mean.get(prod, [0] * self.horizon)

                # Get uncertainty bounds
                p90 = forecast.demand_p90.get(prod, mean) if forecast.demand_p90 else mean
                p10 = forecast.demand_p10.get(prod, mean) if forecast.demand_p10 else mean

                scenario_demand = []
                for t in range(self.horizon):
                    mu = mean[t] if t < len(mean) else mean[-1] if mean else 0
                    p90_t = p90[t] if t < len(p90) else p90[-1] if p90 else mu
                    p10_t = p10[t] if t < len(p10) else p10[-1] if p10 else mu

                    # Sample assuming lognormal distribution
                    if mu > 0 and p90_t > mu:
                        # Estimate sigma from P90
                        sigma = np.log(p90_t / mu) / 1.28
                        sample = np.random.lognormal(np.log(mu), sigma)
                    elif mu > 0:
                        # Fallback: normal with bounded CV
                        cv = (p90_t - p10_t) / (4 * mu) if p90_t > p10_t else 0.2
                        sample = np.random.normal(mu, mu * cv)
                    else:
                        sample = 0

                    scenario_demand.append(max(0, sample))

                scenario[prod] = scenario_demand

            scenarios.append(scenario)

        return scenarios

    def _plan_heuristic(
        self,
        state: MPCState,
        forecast: MPCForecast,
        products: List[str]
    ) -> MPCDecision:
        """
        Fallback heuristic when optimization fails.

        Uses simple base-stock policy.
        """
        production = {}

        for prod in products:
            inv = state.inventory.get(prod, 0)
            backlog = state.backlog.get(prod, 0)
            pipeline = sum(state.pipeline.get(prod, []))

            # Get average demand
            demand_list = forecast.demand_mean.get(prod, [0])
            avg_demand = np.mean(demand_list) if demand_list else 0

            # Simple base-stock heuristic
            target = avg_demand * (self.safety_stock_periods + 2)
            inv_position = inv + pipeline - backlog

            production[prod] = max(0, target - inv_position)

        return MPCDecision(
            production_quantities=production,
            purchase_orders={},
            transfer_orders={},
            objective_value=0.0,
            solve_status="heuristic_fallback",
        )

    def _get_demand(self, forecast: MPCForecast, product_id: str, period: int) -> float:
        """Get demand for product at period"""
        demand_list = forecast.demand_mean.get(product_id, [])
        if period < len(demand_list):
            return demand_list[period]
        elif demand_list:
            return demand_list[-1]  # Use last value
        return 0.0

    def _get_pipeline_arrival(self, state: MPCState, product_id: str, period: int) -> float:
        """Get pipeline arrival for product at period"""
        pipeline = state.pipeline.get(product_id, [])
        if period < len(pipeline):
            return pipeline[period]
        return 0.0

    def run_rolling_horizon(
        self,
        initial_state: MPCState,
        forecast: MPCForecast,
        products: List[str],
        simulation_horizon: int,
        demand_realizations: Optional[Dict[str, List[float]]] = None
    ) -> List[MPCDecision]:
        """
        Run MPC with rolling horizon for simulation.

        At each period:
        1. Solve MPC
        2. Execute first-period decisions
        3. Observe demand realization
        4. Update state
        5. Repeat

        Args:
            initial_state: Starting state
            forecast: Full forecast
            products: Product list
            simulation_horizon: Total simulation periods
            demand_realizations: Actual demands (for simulation)

        Returns:
            List of decisions made at each period
        """
        decisions = []
        state = initial_state

        for t in range(simulation_horizon):
            # Solve MPC for remaining horizon
            remaining_forecast = self._shift_forecast(forecast, t)
            decision = self.plan(state, remaining_forecast, products)
            decisions.append(decision)

            # Simulate state transition
            if demand_realizations:
                state = self._simulate_transition(
                    state, decision, products,
                    {p: d[t] if t < len(d) else 0 for p, d in demand_realizations.items()}
                )
            else:
                # Use forecast as realization
                state = self._simulate_transition(
                    state, decision, products,
                    {p: self._get_demand(forecast, p, t) for p in products}
                )

        return decisions

    def _shift_forecast(self, forecast: MPCForecast, periods: int) -> MPCForecast:
        """Shift forecast forward by periods"""
        return MPCForecast(
            demand_mean={
                p: d[periods:] for p, d in forecast.demand_mean.items()
            },
            demand_p90={
                p: d[periods:] for p, d in forecast.demand_p90.items()
            } if forecast.demand_p90 else None,
            demand_p10={
                p: d[periods:] for p, d in forecast.demand_p10.items()
            } if forecast.demand_p10 else None,
            lead_time_mean=forecast.lead_time_mean,
        )

    def _simulate_transition(
        self,
        state: MPCState,
        decision: MPCDecision,
        products: List[str],
        demand: Dict[str, float]
    ) -> MPCState:
        """Simulate state transition given decision and demand"""
        new_inventory = {}
        new_backlog = {}
        new_pipeline = {}

        for prod in products:
            inv = state.inventory.get(prod, 0)
            back = state.backlog.get(prod, 0)
            pipe = state.pipeline.get(prod, [])

            # Receive from pipeline
            if pipe:
                inv += pipe[0]
                pipe = pipe[1:]

            # Add production to pipeline (assume 1-period lead time)
            prod_qty = decision.production_quantities.get(prod, 0)
            pipe = pipe + [prod_qty]

            # Fulfill demand
            dem = demand.get(prod, 0)
            total_demand = dem + back

            if inv >= total_demand:
                inv -= total_demand
                back = 0
            else:
                back = total_demand - inv
                inv = 0

            new_inventory[prod] = inv
            new_backlog[prod] = back
            new_pipeline[prod] = pipe

        return MPCState(
            inventory=new_inventory,
            backlog=new_backlog,
            pipeline=new_pipeline,
            capacity=state.capacity,
            current_period=state.current_period + 1,
        )
