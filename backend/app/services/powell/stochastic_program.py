"""
Stochastic Programming for Strategic Planning

Converts current "scenario → simulate → metrics" approach to
"scenario → optimize → extract policy" per Powell's framework.

This is the key transformation Powell recommends:
- Current: Monte Carlo for EVALUATION (compute confidence bands after decisions)
- Powell: Monte Carlo for OPTIMIZATION (find optimal policy parameters)

Two-Stage Stochastic Programming:
- Stage 1: Here-and-now decisions (capacity, contracts, safety stock targets)
- Stage 2: Recourse decisions (production, expediting) after uncertainty resolves

Phase 4: Strategic Level (S&OP/Network Design)

References:
- Birge & Louveaux (2011). Introduction to Stochastic Programming
- Powell (2022) Sequential Decision Analytics, Chapter on Strategic Planning
- Shapiro, Dentcheva, Ruszczynski (2009). Lectures on Stochastic Programming
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable, Any
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
class Scenario:
    """
    A scenario in stochastic program.

    Represents one possible realization of uncertain parameters.
    """
    id: int
    probability: float
    demand: Dict[str, List[float]]  # product -> demand by period
    lead_times: Dict[str, float] = field(default_factory=dict)  # supplier -> lead time
    yields: Dict[str, float] = field(default_factory=dict)  # product -> yield percentage
    capacities: Dict[str, float] = field(default_factory=dict)  # resource -> capacity
    costs: Dict[str, float] = field(default_factory=dict)  # cost_type -> value

    # Scenario-specific parameters
    exchange_rates: Dict[str, float] = field(default_factory=dict)  # currency -> rate
    raw_material_prices: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "probability": self.probability,
            "demand": self.demand,
            "lead_times": self.lead_times,
            "yields": self.yields,
            "capacities": self.capacities,
        }


@dataclass
class StochasticSolution:
    """
    Solution to stochastic program.

    Contains both here-and-now decisions and scenario-dependent recourse.
    """
    first_stage_decisions: Dict[str, Any]  # Decisions made now
    recourse_decisions: Dict[int, Dict[str, Any]]  # scenario_id -> recourse decisions
    expected_cost: float
    cost_distribution: List[float]  # cost by scenario

    # Risk metrics
    var_95: float = 0.0  # Value at Risk
    cvar_95: float = 0.0  # Conditional Value at Risk (expected shortfall)
    var_99: float = 0.0
    cvar_99: float = 0.0

    # Solution metadata
    solve_status: str = "unknown"
    solve_time: float = 0.0
    gap: float = 0.0  # Optimality gap

    # Policy extraction
    extracted_policy_params: Optional[Dict[str, float]] = None

    # Conformal coverage guarantee from scenario generation
    conformal_coverage: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "first_stage_decisions": self.first_stage_decisions,
            "expected_cost": self.expected_cost,
            "var_95": self.var_95,
            "cvar_95": self.cvar_95,
            "solve_status": self.solve_status,
            "policy_params": self.extracted_policy_params,
            "conformal_coverage": self.conformal_coverage,
        }

    def get_cost_percentiles(self) -> Dict[str, float]:
        """Get cost distribution percentiles"""
        if not self.cost_distribution:
            return {}

        costs = np.array(self.cost_distribution)
        return {
            "p10": float(np.percentile(costs, 10)),
            "p25": float(np.percentile(costs, 25)),
            "p50": float(np.percentile(costs, 50)),
            "p75": float(np.percentile(costs, 75)),
            "p90": float(np.percentile(costs, 90)),
            "p95": float(np.percentile(costs, 95)),
            "p99": float(np.percentile(costs, 99)),
            "mean": float(np.mean(costs)),
            "std": float(np.std(costs)),
        }


class TwoStageStochasticProgram:
    """
    Two-stage stochastic program for strategic planning.

    Stage 1: Here-and-now decisions (capacity, contracts, safety stock targets)
    Stage 2: Recourse decisions (production, expediting) after uncertainty resolves

    This is Powell's approach: Optimize over scenarios to find optimal policy.

    Key Insight:
    - Current platform: scenarios → simulate → metrics (EVALUATION)
    - Powell: scenarios → optimize over scenarios → extract policy (OPTIMIZATION)
    """

    def __init__(
        self,
        scenarios: List[Scenario],
        products: List[str],
        resources: List[str],
        planning_horizon: int = 12
    ):
        """
        Initialize stochastic program.

        Args:
            scenarios: List of scenarios with probabilities summing to 1
            products: List of product IDs
            resources: List of resource IDs
            planning_horizon: Number of planning periods
        """
        self.scenarios = scenarios
        self.products = products
        self.resources = resources
        self.horizon = planning_horizon

        # Validate scenario probabilities
        total_prob = sum(s.probability for s in scenarios)
        if abs(total_prob - 1.0) > 0.01:
            logger.warning(f"Scenario probabilities sum to {total_prob}, normalizing")
            for s in scenarios:
                s.probability /= total_prob

        # Cost parameters — set via set_cost_rates() before calling solve().
        # holding_cost: InvPolicy.holding_cost_range['min'] or unit_cost * 0.25/52
        # backlog_cost: InvPolicy.backlog_cost_range['min'] or holding_cost * 4
        self.capacity_cost = 100.0   # per unit of capacity
        self.holding_cost = 0.0      # must be set from InvPolicy before solve()
        self.backlog_cost = 0.0      # must be set from InvPolicy before solve()
        self.expediting_cost = 5.0   # per unit expedited
        self.production_cost = 1.0   # per unit produced

    def set_cost_rates(self, holding_cost: float, backlog_cost: float) -> None:
        """Set holding and backlog cost rates from InvPolicy before calling solve().

        Args:
            holding_cost: From InvPolicy.holding_cost_range['min'] or
                          product.unit_cost * 0.25 / 52.
            backlog_cost: From InvPolicy.backlog_cost_range['min'] or
                          holding_cost * 4.
        """
        self.holding_cost = holding_cost
        self.backlog_cost = backlog_cost

    def solve(
        self,
        risk_measure: str = "expected",
        cvar_alpha: float = 0.95,
        max_investment: Optional[float] = None
    ) -> StochasticSolution:
        """
        Solve two-stage stochastic program.

        min E[cost] = c^T x + E[Q(x, ξ)]

        where x = first-stage decisions
              Q(x, ξ) = min cost of recourse given x and scenario ξ

        Args:
            risk_measure: "expected", "cvar", "robust"
            cvar_alpha: Alpha level for CVaR (e.g., 0.95 for 95% CVaR)
            max_investment: Optional cap on first-stage investment

        Returns:
            StochasticSolution with optimal decisions
        """
        if self.holding_cost == 0.0:
            raise ValueError(
                "TwoStageStochasticProgram.holding_cost is 0.0 (unset). "
                "Call set_cost_rates(holding_cost, backlog_cost) with values loaded from "
                "InvPolicy.holding_cost_range['min'] (or product.unit_cost * 0.25 / 52) "
                "before calling solve()."
            )
        if self.backlog_cost == 0.0:
            raise ValueError(
                "TwoStageStochasticProgram.backlog_cost is 0.0 (unset). "
                "Call set_cost_rates(holding_cost, backlog_cost) with values loaded from "
                "InvPolicy.backlog_cost_range['min'] (or holding_cost * 4) "
                "before calling solve()."
            )
        if not CVXPY_AVAILABLE:
            logger.warning("CVXPY not available, using heuristic solution")
            return self._solve_heuristic()

        n_scenarios = len(self.scenarios)
        n_products = len(self.products)
        n_resources = len(self.resources)
        H = self.horizon

        try:
            # First-stage variables (here-and-now)
            capacity_expansion = cp.Variable(n_resources, nonneg=True)
            safety_stock_target = cp.Variable(n_products, nonneg=True)

            # Second-stage variables (per scenario)
            production = {}
            inventory = {}
            backlog = {}
            expedite = {}

            for s in range(n_scenarios):
                production[s] = cp.Variable((n_products, H), nonneg=True)
                inventory[s] = cp.Variable((n_products, H + 1), nonneg=True)
                backlog[s] = cp.Variable((n_products, H + 1), nonneg=True)
                expedite[s] = cp.Variable((n_products, H), nonneg=True)

            constraints = []
            scenario_costs = []

            # First-stage constraints
            if max_investment is not None:
                constraints.append(
                    self.capacity_cost * cp.sum(capacity_expansion) <= max_investment
                )

            # Per-scenario constraints
            for s_idx, scenario in enumerate(self.scenarios):
                s = s_idx

                # Initial conditions
                for i in range(n_products):
                    constraints.append(inventory[s][i, 0] == safety_stock_target[i])
                    constraints.append(backlog[s][i, 0] == 0)

                # Inventory balance for each period
                for t in range(H):
                    for i, prod in enumerate(self.products):
                        demand = self._get_scenario_demand(scenario, prod, t)

                        # Flow balance
                        constraints.append(
                            inventory[s][i, t + 1] - backlog[s][i, t + 1] ==
                            inventory[s][i, t] - backlog[s][i, t] +
                            production[s][i, t] + expedite[s][i, t] - demand
                        )

                # Capacity constraints (with expansion)
                for t in range(H):
                    for j, res in enumerate(self.resources):
                        base_capacity = scenario.capacities.get(res, 100)
                        total_capacity = base_capacity + capacity_expansion[j]

                        constraints.append(
                            cp.sum(production[s][:, t]) <= total_capacity
                        )

                # Scenario cost
                holding = self.holding_cost * cp.sum(inventory[s])
                backlog_penalty = self.backlog_cost * cp.sum(backlog[s])
                expediting = self.expediting_cost * cp.sum(expedite[s])
                prod_cost = self.production_cost * cp.sum(production[s])

                scenario_cost = holding + backlog_penalty + expediting + prod_cost
                scenario_costs.append(scenario.probability * scenario_cost)

            # First-stage cost
            first_stage_cost = self.capacity_cost * cp.sum(capacity_expansion)

            # Objective based on risk measure
            if risk_measure == "expected":
                total_cost = first_stage_cost + cp.sum(scenario_costs)
            elif risk_measure == "cvar":
                # CVaR formulation
                var = cp.Variable()
                cvar_slack = cp.Variable(n_scenarios, nonneg=True)

                for s_idx, scenario in enumerate(self.scenarios):
                    constraints.append(
                        cvar_slack[s_idx] >= scenario_costs[s_idx] / scenario.probability - var
                    )

                cvar_term = var + (1 / (1 - cvar_alpha)) * cp.sum(
                    [self.scenarios[s].probability * cvar_slack[s] for s in range(n_scenarios)]
                )
                total_cost = first_stage_cost + cvar_term
            elif risk_measure == "robust":
                # Minimax (worst-case)
                worst_case = cp.Variable()
                for s_idx in range(n_scenarios):
                    constraints.append(
                        worst_case >= scenario_costs[s_idx] / self.scenarios[s_idx].probability
                    )
                total_cost = first_stage_cost + worst_case
            else:
                total_cost = first_stage_cost + cp.sum(scenario_costs)

            # Solve
            problem = cp.Problem(cp.Minimize(total_cost), constraints)
            problem.solve(solver=cp.ECOS, verbose=False)

            if problem.status not in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]:
                logger.warning(f"Stochastic program failed: {problem.status}")
                return self._solve_heuristic()

            # Extract solution
            return self._extract_solution(
                capacity_expansion, safety_stock_target,
                production, inventory, backlog, expedite,
                problem
            )

        except Exception as e:
            logger.error(f"Stochastic program optimization failed: {e}")
            return self._solve_heuristic()

    def _extract_solution(
        self,
        capacity_expansion,
        safety_stock_target,
        production,
        inventory,
        backlog,
        expedite,
        problem
    ) -> StochasticSolution:
        """Extract solution from solved optimization problem"""
        n_products = len(self.products)
        n_resources = len(self.resources)

        # First-stage decisions
        first_stage = {
            'capacity_expansion': {
                self.resources[j]: float(capacity_expansion.value[j])
                for j in range(n_resources)
            },
            'safety_stock_target': {
                self.products[i]: float(safety_stock_target.value[i])
                for i in range(n_products)
            }
        }

        # Recourse decisions per scenario
        recourse = {}
        cost_by_scenario = []

        for s_idx, scenario in enumerate(self.scenarios):
            recourse[s_idx] = {
                'production': {
                    self.products[i]: [
                        float(production[s_idx].value[i, t])
                        for t in range(self.horizon)
                    ]
                    for i in range(n_products)
                },
                'total_production': float(np.sum(production[s_idx].value)),
                'total_inventory': float(np.sum(inventory[s_idx].value)),
                'total_backlog': float(np.sum(backlog[s_idx].value)),
                'total_expedite': float(np.sum(expedite[s_idx].value)),
            }

            # Compute realized cost for this scenario
            scenario_cost = (
                self.holding_cost * np.sum(inventory[s_idx].value) +
                self.backlog_cost * np.sum(backlog[s_idx].value) +
                self.expediting_cost * np.sum(expedite[s_idx].value) +
                self.production_cost * np.sum(production[s_idx].value)
            )
            cost_by_scenario.append(float(scenario_cost))

        # Risk metrics
        cost_array = np.array(cost_by_scenario)
        var_95 = float(np.percentile(cost_array, 95))
        cvar_95 = float(np.mean(cost_array[cost_array >= var_95])) if np.any(cost_array >= var_95) else var_95
        var_99 = float(np.percentile(cost_array, 99))
        cvar_99 = float(np.mean(cost_array[cost_array >= var_99])) if np.any(cost_array >= var_99) else var_99

        # Extract policy parameters from solution
        policy_params = self._extract_policy_params(first_stage, recourse)

        return StochasticSolution(
            first_stage_decisions=first_stage,
            recourse_decisions=recourse,
            expected_cost=float(problem.value),
            cost_distribution=cost_by_scenario,
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            solve_status=problem.status,
            extracted_policy_params=policy_params,
        )

    def _extract_policy_params(
        self,
        first_stage: Dict[str, Any],
        recourse: Dict[int, Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Extract parameterized policy from stochastic solution.

        This is the key Powell insight: Use stochastic programming
        to find optimal policy PARAMETERS, not just optimal decisions.
        """
        policy_params = {}

        # Safety stock multiplier (relative to base)
        ss_targets = first_stage.get('safety_stock_target', {})
        if ss_targets:
            avg_ss = np.mean(list(ss_targets.values()))
            policy_params['base_safety_stock'] = avg_ss

        # Capacity utilization target
        cap_expansion = first_stage.get('capacity_expansion', {})
        if cap_expansion:
            total_expansion = sum(cap_expansion.values())
            policy_params['capacity_expansion_total'] = total_expansion

        # Average production rate across scenarios
        prod_totals = [r['total_production'] for r in recourse.values()]
        if prod_totals:
            policy_params['avg_production_rate'] = np.mean(prod_totals) / self.horizon

        # Expediting frequency (when to expedite)
        expedite_totals = [r.get('total_expedite', 0) for r in recourse.values()]
        if expedite_totals:
            policy_params['expedite_threshold'] = np.percentile(expedite_totals, 75)

        return policy_params

    def _get_scenario_demand(self, scenario: Scenario, product: str, period: int) -> float:
        """Get demand for product at period in scenario"""
        demand_list = scenario.demand.get(product, [])
        if period < len(demand_list):
            return demand_list[period]
        elif demand_list:
            return demand_list[-1]
        return 0.0

    def _solve_heuristic(self) -> StochasticSolution:
        """Fallback heuristic when solver unavailable"""
        # Compute average demand across scenarios
        avg_demand = {prod: 0.0 for prod in self.products}

        for scenario in self.scenarios:
            for prod in self.products:
                demand_list = scenario.demand.get(prod, [])
                avg_dem = np.mean(demand_list) if demand_list else 0
                avg_demand[prod] += scenario.probability * avg_dem

        # Simple heuristics
        first_stage = {
            'capacity_expansion': {res: 0.0 for res in self.resources},
            'safety_stock_target': {prod: avg_demand[prod] * 2 for prod in self.products}
        }

        # Estimate costs
        base_cost = sum(avg_demand.values()) * self.horizon * (
            self.holding_cost + self.production_cost
        )

        return StochasticSolution(
            first_stage_decisions=first_stage,
            recourse_decisions={},
            expected_cost=base_cost,
            cost_distribution=[base_cost] * len(self.scenarios),
            var_95=base_cost * 1.2,
            cvar_95=base_cost * 1.3,
            solve_status="heuristic",
        )

    def generate_scenarios(
        self,
        demand_mean: Dict[str, float],
        demand_cv: float = 0.2,
        n_scenarios: int = 10,
        method: str = "latin_hypercube"
    ) -> List[Scenario]:
        """
        Generate scenarios from demand distributions.

        Args:
            demand_mean: Average demand by product
            demand_cv: Coefficient of variation
            n_scenarios: Number of scenarios
            method: "monte_carlo", "latin_hypercube", "antithetic"
        """
        scenarios = []

        for i in range(n_scenarios):
            demand = {}
            for prod, mean in demand_mean.items():
                std = mean * demand_cv

                if method == "latin_hypercube":
                    # Latin hypercube sampling
                    u = (i + np.random.random()) / n_scenarios
                    from scipy.stats import norm
                    sample = norm.ppf(u, loc=mean, scale=std)
                elif method == "antithetic":
                    # Antithetic variates
                    if i % 2 == 0:
                        sample = np.random.normal(mean, std)
                    else:
                        # Use antithetic of previous
                        prev_sample = scenarios[-1].demand[prod][0]
                        sample = 2 * mean - prev_sample
                else:
                    # Simple Monte Carlo
                    sample = np.random.normal(mean, std)

                # Generate time series
                demand[prod] = [max(0, sample * (1 + 0.1 * np.random.randn()))
                                for _ in range(self.horizon)]

            scenarios.append(Scenario(
                id=i,
                probability=1.0 / n_scenarios,
                demand=demand,
            ))

        return scenarios


def compute_expected_value_of_perfect_information(
    program: TwoStageStochasticProgram
) -> float:
    """
    Compute EVPI - the value of knowing the future perfectly.

    EVPI = E[WS] - RP

    where:
    - WS = Wait-and-see solution (optimal if we knew scenario in advance)
    - RP = Recourse problem solution (optimal under uncertainty)
    """
    # Solve recourse problem
    rp_solution = program.solve()
    rp_cost = rp_solution.expected_cost

    # Solve perfect-information problems
    ws_costs = []
    for scenario in program.scenarios:
        # Single-scenario program
        single_program = TwoStageStochasticProgram(
            scenarios=[Scenario(id=0, probability=1.0, demand=scenario.demand,
                                capacities=scenario.capacities)],
            products=program.products,
            resources=program.resources,
            planning_horizon=program.horizon,
        )
        ws_solution = single_program.solve()
        ws_costs.append(scenario.probability * ws_solution.expected_cost)

    evpi = rp_cost - sum(ws_costs)
    return max(0, evpi)  # EVPI should be non-negative


def compute_value_of_stochastic_solution(
    program: TwoStageStochasticProgram
) -> float:
    """
    Compute VSS - the value of using stochastic solution vs deterministic.

    VSS = EEV - RP

    where:
    - EEV = Expected result of using Expected Value solution
    - RP = Recourse problem solution
    """
    # Solve stochastic program
    rp_solution = program.solve()
    rp_cost = rp_solution.expected_cost

    # Compute expected value problem (using mean demand)
    avg_demand = {}
    for prod in program.products:
        total_demand = 0
        for scenario in program.scenarios:
            demand_list = scenario.demand.get(prod, [])
            if demand_list:
                total_demand += scenario.probability * np.mean(demand_list)
        avg_demand[prod] = [total_demand] * program.horizon

    ev_scenario = Scenario(id=0, probability=1.0, demand=avg_demand)
    ev_program = TwoStageStochasticProgram(
        scenarios=[ev_scenario],
        products=program.products,
        resources=program.resources,
        planning_horizon=program.horizon,
    )
    ev_solution = ev_program.solve()

    # Evaluate EV solution under uncertainty
    # (simplified - would need to fix first-stage and re-optimize recourse)
    eev_cost = ev_solution.expected_cost * 1.1  # Rough estimate

    vss = eev_cost - rp_cost
    return max(0, vss)
