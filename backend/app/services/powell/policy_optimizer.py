"""
Policy Parameter Optimization using Powell's CFA Framework

Optimizes policy parameters θ by:
1. Sampling scenarios from stochastic engine
2. Simulating policy with candidate θ
3. Computing expected objective
4. Iterating to find optimal θ*

This is Powell's Cost Function Approximation (CFA) approach:
- Policy is parameterized by θ (e.g., safety stock levels, service levels)
- Optimize θ to minimize expected cost over scenarios
- Convert simulation-for-evaluation to simulation-for-optimization

Phase 2: Operational Level (MRP/DRP)

References:
- Powell (2022) Sequential Decision Analytics, Chapter on CFA
- Birge & Louveaux (2011). Introduction to Stochastic Programming
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Callable, Optional, Tuple
import numpy as np
import logging

try:
    from scipy.optimize import minimize, differential_evolution
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PolicyParameter:
    """
    Definition of a tunable policy parameter.

    These are the θ values that Powell's CFA optimizes.
    """
    name: str
    initial_value: float
    lower_bound: float
    upper_bound: float
    parameter_type: str = 'continuous'  # 'continuous', 'integer', 'categorical'
    description: str = ""
    category: str = "general"  # For grouping in UI

    def clip(self, value: float) -> float:
        """Clip value to bounds"""
        clipped = max(self.lower_bound, min(self.upper_bound, value))
        if self.parameter_type == 'integer':
            clipped = round(clipped)
        return clipped


@dataclass
class OptimizationResult:
    """Result of policy parameter optimization"""
    optimal_parameters: Dict[str, float]
    optimal_objective: float
    convergence_history: List[float]
    num_iterations: int
    num_simulations: int
    confidence_interval: Tuple[float, float]
    status: str = "success"
    message: str = ""

    # Additional diagnostics
    parameter_sensitivities: Optional[Dict[str, float]] = None
    scenario_objectives: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "optimal_parameters": self.optimal_parameters,
            "optimal_objective": self.optimal_objective,
            "convergence_history": self.convergence_history,
            "num_iterations": self.num_iterations,
            "num_simulations": self.num_simulations,
            "confidence_interval": list(self.confidence_interval),
            "status": self.status,
            "message": self.message,
            "parameter_sensitivities": self.parameter_sensitivities,
        }


class PolicyOptimizer:
    """
    Simulation-based policy parameter optimization.

    Uses Monte Carlo scenarios to evaluate policy performance,
    then optimizes parameters to minimize expected cost.

    This is the core of Powell's CFA (Cost Function Approximation):
    Instead of evaluating a fixed policy with simulation,
    we optimize the policy parameters using simulation.
    """

    def __init__(
        self,
        simulator: Callable[[Dict[str, float], int], float],
        parameters: List[PolicyParameter],
        n_scenarios: int = 100,
        objective: str = 'expected_cost'
    ):
        """
        Initialize policy optimizer.

        Args:
            simulator: Function(params, seed) -> cost
                Takes parameter dictionary and random seed, returns cost
            parameters: List of tunable parameters with bounds
            n_scenarios: Number of Monte Carlo scenarios
            objective: 'expected_cost', 'cvar_95', 'service_level', 'robust'
        """
        self.simulator = simulator
        self.parameters = {p.name: p for p in parameters}
        self.n_scenarios = n_scenarios
        self.objective = objective

        # Caching to avoid redundant simulations
        self.evaluation_cache: Dict[tuple, Tuple[float, float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    def evaluate_policy(
        self,
        param_values: Dict[str, float],
        use_cache: bool = True
    ) -> Tuple[float, float]:
        """
        Evaluate policy using Monte Carlo simulation.

        Args:
            param_values: Parameter values to evaluate
            use_cache: Whether to use cached results

        Returns:
            (objective_value, standard_error)
        """
        # Cache key (round to avoid floating point key issues)
        cache_key = tuple(sorted((k, round(v, 6)) for k, v in param_values.items()))

        if use_cache and cache_key in self.evaluation_cache:
            self._cache_hits += 1
            return self.evaluation_cache[cache_key]

        self._cache_misses += 1

        # Run simulations
        costs = []
        for seed in range(self.n_scenarios):
            try:
                cost = self.simulator(param_values, seed)
                costs.append(cost)
            except Exception as e:
                logger.warning(f"Simulation failed for seed {seed}: {e}")
                # Use large penalty for failed simulations
                costs.append(1e6)

        costs = np.array(costs)

        # Compute objective based on type
        if self.objective == 'expected_cost':
            obj_value = float(np.mean(costs))
        elif self.objective == 'cvar_95':
            # Conditional Value-at-Risk (average of worst 5%)
            threshold = np.percentile(costs, 95)
            tail_costs = costs[costs >= threshold]
            obj_value = float(np.mean(tail_costs)) if len(tail_costs) > 0 else float(np.max(costs))
        elif self.objective == 'service_level':
            # Maximize service level (minimize stockouts)
            # Assuming cost < 0 indicates good service
            obj_value = float(-np.mean(costs <= 0))
        elif self.objective == 'robust':
            # Worst-case objective (minimax)
            obj_value = float(np.percentile(costs, 95))
        else:
            obj_value = float(np.mean(costs))

        std_error = float(np.std(costs) / np.sqrt(len(costs)))

        if use_cache:
            self.evaluation_cache[cache_key] = (obj_value, std_error)

        return obj_value, std_error

    def optimize(
        self,
        method: str = 'differential_evolution',
        max_iterations: int = 100,
        tolerance: float = 1e-4,
        verbose: bool = False
    ) -> OptimizationResult:
        """
        Find optimal policy parameters.

        Args:
            method: 'differential_evolution', 'nelder_mead', 'bfgs', 'grid_search'
            max_iterations: Maximum optimization iterations
            tolerance: Convergence tolerance
            verbose: Print progress

        Returns:
            OptimizationResult with optimal parameters
        """
        if not SCIPY_AVAILABLE and method != 'grid_search':
            logger.warning("SciPy not available, falling back to grid search")
            method = 'grid_search'

        convergence_history = []
        num_simulations = 0

        # Define bounds
        param_names = sorted(self.parameters.keys())
        bounds = [
            (self.parameters[name].lower_bound, self.parameters[name].upper_bound)
            for name in param_names
        ]

        def objective_fn(x):
            nonlocal num_simulations
            params = {name: val for name, val in zip(param_names, x)}
            obj, _ = self.evaluate_policy(params)
            num_simulations += self.n_scenarios
            convergence_history.append(obj)
            if verbose and len(convergence_history) % 10 == 0:
                logger.info(f"Iteration {len(convergence_history)}: objective = {obj:.4f}")
            return obj

        if method == 'differential_evolution':
            result = differential_evolution(
                objective_fn,
                bounds,
                maxiter=max_iterations,
                tol=tolerance,
                seed=42,
                polish=True,
                workers=1,  # Single-threaded for reproducibility
            )
            optimal_x = result.x
            optimal_obj = result.fun
            status = "success" if result.success else "max_iterations"

        elif method == 'nelder_mead':
            x0 = [self.parameters[name].initial_value for name in param_names]
            result = minimize(
                objective_fn,
                x0,
                method='Nelder-Mead',
                options={'maxiter': max_iterations, 'xatol': tolerance}
            )
            optimal_x = result.x
            optimal_obj = result.fun
            status = "success" if result.success else "max_iterations"

        elif method == 'bfgs':
            x0 = [self.parameters[name].initial_value for name in param_names]
            result = minimize(
                objective_fn,
                x0,
                method='L-BFGS-B',
                bounds=bounds,
                options={'maxiter': max_iterations}
            )
            optimal_x = result.x
            optimal_obj = result.fun
            status = "success" if result.success else "max_iterations"

        elif method == 'grid_search':
            optimal_x, optimal_obj = self._grid_search(
                param_names, bounds, objective_fn, max_iterations
            )
            status = "success"

        else:
            raise ValueError(f"Unknown optimization method: {method}")

        # Clip to bounds and respect parameter types
        optimal_params = {}
        for i, name in enumerate(param_names):
            optimal_params[name] = self.parameters[name].clip(optimal_x[i])

        # Compute confidence interval at optimum
        _, std_error = self.evaluate_policy(optimal_params)
        ci = (optimal_obj - 1.96 * std_error, optimal_obj + 1.96 * std_error)

        # Compute parameter sensitivities
        sensitivities = self._compute_sensitivities(optimal_params, param_names)

        return OptimizationResult(
            optimal_parameters=optimal_params,
            optimal_objective=optimal_obj,
            convergence_history=convergence_history,
            num_iterations=len(convergence_history),
            num_simulations=num_simulations,
            confidence_interval=ci,
            status=status,
            parameter_sensitivities=sensitivities,
        )

    def _grid_search(
        self,
        param_names: List[str],
        bounds: List[Tuple[float, float]],
        objective_fn: Callable,
        max_evaluations: int
    ) -> Tuple[List[float], float]:
        """Simple grid search for when scipy is unavailable"""
        # Determine grid points per parameter
        n_params = len(param_names)
        points_per_param = max(2, int(max_evaluations ** (1 / n_params)))

        grids = []
        for (lb, ub) in bounds:
            grids.append(np.linspace(lb, ub, points_per_param))

        best_x = [g[0] for g in grids]
        best_obj = float('inf')

        # Evaluate grid points
        from itertools import product
        for combo in product(*grids):
            obj = objective_fn(list(combo))
            if obj < best_obj:
                best_obj = obj
                best_x = list(combo)

        return best_x, best_obj

    def _compute_sensitivities(
        self,
        optimal_params: Dict[str, float],
        param_names: List[str],
        delta_pct: float = 0.05
    ) -> Dict[str, float]:
        """
        Compute parameter sensitivities at optimum.

        Sensitivity = (change in objective) / (change in parameter)
        """
        base_obj, _ = self.evaluate_policy(optimal_params)
        sensitivities = {}

        for name in param_names:
            param = self.parameters[name]
            delta = (param.upper_bound - param.lower_bound) * delta_pct

            # Perturb up
            params_up = {**optimal_params}
            params_up[name] = min(optimal_params[name] + delta, param.upper_bound)
            obj_up, _ = self.evaluate_policy(params_up)

            # Perturb down
            params_down = {**optimal_params}
            params_down[name] = max(optimal_params[name] - delta, param.lower_bound)
            obj_down, _ = self.evaluate_policy(params_down)

            # Central difference sensitivity
            sensitivity = (obj_up - obj_down) / (2 * delta) if delta > 0 else 0
            sensitivities[name] = float(sensitivity)

        return sensitivities

    def get_cache_stats(self) -> Dict[str, int]:
        """Get caching statistics"""
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self.evaluation_cache),
        }


class InventoryPolicyOptimizer(PolicyOptimizer):
    """
    Specialized optimizer for inventory policies.

    Optimizes the 4 AWS SC policy types:
    - abs_level: Fixed safety stock quantity
    - doc_dem: Days of coverage based on demand
    - doc_fcst: Days of coverage based on forecast
    - sl: Service level with z-score
    """

    @staticmethod
    def get_policy_parameters(policy_type: str) -> List[PolicyParameter]:
        """
        Get tunable parameters for each policy type.

        These are the θ parameters in Powell's CFA framework.
        """
        if policy_type == 'abs_level':
            return [
                PolicyParameter(
                    name='safety_stock_qty',
                    initial_value=100.0,
                    lower_bound=0.0,
                    upper_bound=1000.0,
                    parameter_type='continuous',
                    description='Fixed safety stock quantity',
                    category='inventory',
                )
            ]

        elif policy_type == 'doc_dem':
            return [
                PolicyParameter(
                    name='days_of_coverage',
                    initial_value=14.0,
                    lower_bound=1.0,
                    upper_bound=90.0,
                    parameter_type='continuous',
                    description='Days of coverage based on average demand',
                    category='inventory',
                )
            ]

        elif policy_type == 'doc_fcst':
            return [
                PolicyParameter(
                    name='days_of_coverage',
                    initial_value=14.0,
                    lower_bound=1.0,
                    upper_bound=90.0,
                    parameter_type='continuous',
                    description='Days of coverage based on forecast',
                    category='inventory',
                ),
                PolicyParameter(
                    name='forecast_horizon',
                    initial_value=7.0,
                    lower_bound=1.0,
                    upper_bound=30.0,
                    parameter_type='integer',
                    description='Days ahead for forecast averaging',
                    category='forecast',
                )
            ]

        elif policy_type == 'sl':
            return [
                PolicyParameter(
                    name='service_level',
                    initial_value=0.95,
                    lower_bound=0.80,
                    upper_bound=0.99,
                    parameter_type='continuous',
                    description='Target service level (probability)',
                    category='service',
                ),
                PolicyParameter(
                    name='demand_variability_factor',
                    initial_value=1.0,
                    lower_bound=0.5,
                    upper_bound=2.0,
                    parameter_type='continuous',
                    description='Multiplier on historical demand std dev',
                    category='demand',
                )
            ]

        else:
            raise ValueError(f"Unknown policy type: {policy_type}")

    @staticmethod
    def get_mrp_parameters() -> List[PolicyParameter]:
        """Get MRP-specific parameters for optimization"""
        return [
            PolicyParameter(
                name='lot_size_weeks',
                initial_value=4.0,
                lower_bound=1.0,
                upper_bound=12.0,
                parameter_type='integer',
                description='Weeks of supply per lot',
                category='lot_sizing',
            ),
            PolicyParameter(
                name='planning_fence',
                initial_value=2.0,
                lower_bound=0.0,
                upper_bound=8.0,
                parameter_type='integer',
                description='Weeks within which changes are frozen',
                category='planning',
            ),
            PolicyParameter(
                name='safety_lead_time',
                initial_value=1.0,
                lower_bound=0.0,
                upper_bound=4.0,
                parameter_type='continuous',
                description='Additional lead time buffer (weeks)',
                category='lead_time',
            ),
            PolicyParameter(
                name='yield_factor',
                initial_value=1.0,
                lower_bound=0.8,
                upper_bound=1.2,
                parameter_type='continuous',
                description='Multiplier on expected yield',
                category='manufacturing',
            ),
        ]

    @staticmethod
    def get_base_stock_parameters() -> List[PolicyParameter]:
        """Get base stock policy parameters"""
        return [
            PolicyParameter(
                name='base_stock_multiplier',
                initial_value=3.0,
                lower_bound=1.0,
                upper_bound=10.0,
                parameter_type='continuous',
                description='Multiplier on lead time demand for base stock',
                category='inventory',
            ),
            PolicyParameter(
                name='reorder_point_buffer',
                initial_value=0.2,
                lower_bound=0.0,
                upper_bound=1.0,
                parameter_type='continuous',
                description='Additional buffer as fraction of base stock',
                category='inventory',
            ),
        ]


def create_inventory_simulator(
    demand_mean: float,
    demand_std: float,
    lead_time: int,
    holding_cost: float = 0.5,
    stockout_cost: float = 2.0,
    horizon: int = 52
) -> Callable[[Dict[str, float], int], float]:
    """
    Factory function to create inventory simulation for optimization.

    Returns a simulator function compatible with PolicyOptimizer.
    """
    def simulate(params: Dict[str, float], seed: int) -> float:
        np.random.seed(seed)

        # Extract parameters
        if 'safety_stock_qty' in params:
            safety_stock = params['safety_stock_qty']
        elif 'days_of_coverage' in params:
            safety_stock = params['days_of_coverage'] * demand_mean / 7
        elif 'service_level' in params:
            from scipy.stats import norm
            z = norm.ppf(params['service_level'])
            variability = params.get('demand_variability_factor', 1.0)
            safety_stock = z * demand_std * variability * np.sqrt(lead_time)
        else:
            safety_stock = demand_mean * lead_time

        # Base stock target
        base_stock = demand_mean * lead_time + safety_stock

        # Simulate inventory
        inventory = base_stock
        pipeline = [0.0] * lead_time
        total_cost = 0.0

        for t in range(horizon):
            # Receive shipment
            if pipeline:
                inventory += pipeline.pop(0)

            # Demand realization
            demand = max(0, np.random.normal(demand_mean, demand_std))

            # Fulfill demand
            if inventory >= demand:
                inventory -= demand
            else:
                stockout = demand - inventory
                total_cost += stockout * stockout_cost
                inventory = 0

            # Holding cost
            total_cost += inventory * holding_cost

            # Order decision (order-up-to base stock)
            inv_position = inventory + sum(pipeline)
            order = max(0, base_stock - inv_position)
            pipeline.append(order)

        return total_cost

    return simulate
