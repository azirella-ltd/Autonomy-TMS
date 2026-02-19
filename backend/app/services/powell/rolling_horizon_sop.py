"""
Rolling Horizon S&OP with Conformal Updates

Implements Powell's adaptive policy framework at the S&OP (strategic) level:
1. Solve stochastic program with current conformal scenarios
2. Execute first-period decisions
3. Observe actuals and update conformal predictors
4. Re-solve with updated conformal regions
5. Repeat

This creates a continuous learning loop where the planning system
improves as it observes outcomes.

Key Innovation:
- Traditional: Static uncertainty models (Normal distributions assumed)
- This approach: Adaptive uncertainty models (conformal regions update with data)

The system learns from its mistakes:
- If forecasts consistently under-predict, intervals widen
- If forecasts are accurate, intervals tighten
- Coverage guarantees are maintained throughout

References:
- Powell (2022). Sequential Decision Analytics and Modeling
- Gibbs & Candès (2021). Adaptive Conformal Inference Under Distribution Shift
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging

import numpy as np

from ..conformal_prediction.suite import SupplyChainConformalSuite
from .conformal_scenario_generator import (
    ConformalScenarioGenerator,
    ConformalScenarioConfig,
)
from .scenario_reduction import reduce_conformal_scenarios
from .stochastic_program import StochasticSolution, TwoStageStochasticProgram

logger = logging.getLogger(__name__)


@dataclass
class SOPPlanningCycle:
    """Result of a single S&OP planning cycle"""

    cycle_id: int
    planning_date: date
    solution: StochasticSolution
    conformal_coverage: float
    n_scenarios_generated: int
    n_scenarios_after_reduction: int
    calibration_updates: Dict[str, int]  # predictor_key -> n_new_points

    # Decisions made
    first_stage_decisions: Dict[str, Any]

    # Performance metrics (if actuals available)
    realized_cost: Optional[float] = None
    service_level_achieved: Optional[float] = None
    coverage_met: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "cycle_id": self.cycle_id,
            "planning_date": self.planning_date.isoformat(),
            "expected_cost": self.solution.expected_cost,
            "var_95": self.solution.var_95,
            "cvar_95": self.solution.cvar_95,
            "conformal_coverage": self.conformal_coverage,
            "n_scenarios_generated": self.n_scenarios_generated,
            "n_scenarios_after_reduction": self.n_scenarios_after_reduction,
            "calibration_updates": self.calibration_updates,
            "first_stage_decisions": self.first_stage_decisions,
            "realized_cost": self.realized_cost,
            "service_level_achieved": self.service_level_achieved,
            "coverage_met": self.coverage_met,
        }


@dataclass
class RollingHorizonSOPConfig:
    """Configuration for rolling horizon S&OP"""

    planning_frequency_days: int = 30  # Monthly S&OP
    stochastic_horizon_periods: int = 12  # 12-month horizon
    tactical_horizon_periods: int = 4  # 4-week tactical

    # Scenario generation
    n_scenarios: int = 100
    n_scenarios_after_reduction: int = 30

    # Risk settings
    risk_measure: str = "cvar"  # "expected", "cvar", "robust"
    cvar_alpha: float = 0.95

    # Recalibration settings
    min_calibration_points: int = 20
    recalibration_trigger_coverage_gap: float = 0.05  # Recalibrate if gap > 5%
    auto_recalibrate: bool = True

    # Cost parameters
    capacity_cost: float = 100.0
    holding_cost: float = 0.5
    backlog_cost: float = 2.0
    expediting_cost: float = 5.0
    production_cost: float = 1.0


class RollingHorizonSOP:
    """
    Rolling Horizon S&OP Planner with Conformal Learning.

    Key Innovation: The conformal predictors update each cycle based on
    observed outcomes, so the uncertainty quantification improves over time.

    This implements Powell's "Approximate Dynamic Programming" at the S&OP level:
    - State: Current inventory, backlog, calibration data
    - Decision: Capacity, contracts, safety stock targets (Stage 1)
    - Exogenous info: Demand, lead time, yield realizations
    - Transition: State update + conformal recalibration

    Usage:
        sop = RollingHorizonSOP(
            products=["PROD001", "PROD002"],
            sites=[1, 2],
            suppliers=["SUP001"],
            resources=["MACHINE1"],
        )

        # Run planning cycle
        cycle = sop.run_planning_cycle(
            current_date=date.today(),
            demand_forecasts={("PROD001", 1): [100, 110, 105, ...]},
            expected_lead_times={"SUP001": 5},
        )

        # Later, observe actuals and update
        sop.observe_actuals(
            observation_date=date.today() + timedelta(days=30),
            actual_demands={("PROD001", 1): 108},
            forecasts_used={("PROD001", 1): 100},
        )

        # Run next cycle with updated predictors
        next_cycle = sop.run_planning_cycle(...)
    """

    def __init__(
        self,
        products: List[str],
        sites: List[int],
        suppliers: List[str],
        resources: List[str],
        config: Optional[RollingHorizonSOPConfig] = None,
    ):
        """
        Initialize Rolling Horizon S&OP planner.

        Args:
            products: List of product IDs
            sites: List of site IDs
            suppliers: List of supplier IDs
            resources: List of resource IDs
            config: Planning configuration
        """
        self.products = products
        self.sites = sites
        self.suppliers = suppliers
        self.resources = resources
        self.config = config or RollingHorizonSOPConfig()

        # Initialize conformal suite
        self.conformal_suite = SupplyChainConformalSuite(
            demand_coverage=0.90,
            lead_time_coverage=0.90,
            yield_coverage=0.95,
        )

        # History of planning cycles
        self.cycle_history: List[SOPPlanningCycle] = []

        # Observation buffers for conformal updates
        self._demand_observations: Dict[str, List[Tuple[float, float]]] = {}
        self._lead_time_observations: Dict[str, List[Tuple[float, float]]] = {}
        self._yield_observations: Dict[str, List[Tuple[float, float]]] = {}

        logger.info(
            f"Initialized RollingHorizonSOP: "
            f"{len(products)} products, {len(sites)} sites, "
            f"{len(suppliers)} suppliers, {len(resources)} resources"
        )

    def run_planning_cycle(
        self,
        current_date: date,
        demand_forecasts: Dict[Tuple[str, int], List[float]],
        expected_lead_times: Dict[str, float],
        expected_yields: Optional[Dict[str, float]] = None,
        current_state: Optional[Dict[str, Any]] = None,
        max_investment: Optional[float] = None,
    ) -> SOPPlanningCycle:
        """
        Run a single S&OP planning cycle.

        This is the main entry point for each planning period.

        Args:
            current_date: Planning cycle date
            demand_forecasts: Point forecasts by (product, site)
            expected_lead_times: Expected lead times by supplier
            expected_yields: Expected yields by product (optional)
            current_state: Current inventory/backlog state (optional)
            max_investment: Optional cap on first-stage investment

        Returns:
            SOPPlanningCycle with decisions and metadata
        """
        cycle_id = len(self.cycle_history)
        logger.info(f"Starting S&OP cycle {cycle_id} for {current_date}")

        # Step 1: Generate scenarios from current conformal regions
        generator = ConformalScenarioGenerator(
            self.conformal_suite,
            ConformalScenarioConfig(
                n_scenarios=self.config.n_scenarios,
                horizon=self.config.stochastic_horizon_periods,
            ),
        )

        scenarios = generator.generate_scenarios(
            products=self.products,
            sites=self.sites,
            suppliers=self.suppliers,
            demand_forecasts=demand_forecasts,
            expected_lead_times=expected_lead_times,
            expected_yields=expected_yields,
        )

        n_generated = len(scenarios)
        logger.info(f"  Generated {n_generated} conformal scenarios")

        # Step 2: Reduce scenarios if needed
        if len(scenarios) > self.config.n_scenarios_after_reduction:
            scenarios = reduce_conformal_scenarios(
                scenarios,
                target_count=self.config.n_scenarios_after_reduction,
                method="fast_forward",
            )
            logger.info(f"  Reduced to {len(scenarios)} scenarios")

        n_reduced = len(scenarios)

        # Step 3: Solve stochastic program
        program = TwoStageStochasticProgram(
            scenarios=scenarios,
            products=self.products,
            resources=self.resources,
            planning_horizon=self.config.stochastic_horizon_periods,
        )

        # Set cost parameters from config
        program.capacity_cost = self.config.capacity_cost
        program.holding_cost = self.config.holding_cost
        program.backlog_cost = self.config.backlog_cost
        program.expediting_cost = self.config.expediting_cost
        program.production_cost = self.config.production_cost

        solution = program.solve(
            risk_measure=self.config.risk_measure,
            cvar_alpha=self.config.cvar_alpha,
            max_investment=max_investment,
        )

        logger.info(
            f"  Solved stochastic program: "
            f"expected_cost={solution.expected_cost:.2f}, "
            f"status={solution.solve_status}"
        )

        # Step 4: Create cycle record
        cycle = SOPPlanningCycle(
            cycle_id=cycle_id,
            planning_date=current_date,
            solution=solution,
            conformal_coverage=generator.compute_coverage_guarantee(),
            n_scenarios_generated=n_generated,
            n_scenarios_after_reduction=n_reduced,
            calibration_updates={},
            first_stage_decisions=solution.first_stage_decisions,
        )

        self.cycle_history.append(cycle)

        logger.info(
            f"S&OP cycle {cycle_id} complete: "
            f"expected_cost={solution.expected_cost:.2f}, "
            f"coverage={cycle.conformal_coverage:.1%}"
        )

        return cycle

    def observe_actuals(
        self,
        observation_date: date,
        actual_demands: Dict[Tuple[str, int], float],
        actual_lead_times: Optional[Dict[str, float]] = None,
        actual_yields: Optional[Dict[str, float]] = None,
        forecasts_used: Optional[Dict[Tuple[str, int], float]] = None,
        promised_lead_times: Optional[Dict[str, float]] = None,
        expected_yields_used: Optional[Dict[str, float]] = None,
    ):
        """
        Observe actual outcomes and update conformal predictors.

        This is the KEY LEARNING STEP:
        - Compare predictions to actuals
        - Update conformal calibration
        - Improved uncertainty quantification for next cycle

        Args:
            observation_date: Date of observation
            actual_demands: Realized demands by (product, site)
            actual_lead_times: Realized lead times by supplier (optional)
            actual_yields: Realized yields by product (optional)
            forecasts_used: Original forecasts for calibration update
            promised_lead_times: Promised/expected lead times for calibration
            expected_yields_used: Expected yields for calibration
        """
        updates = {}

        # Update demand predictors
        if forecasts_used:
            for (prod, site), actual in actual_demands.items():
                key = f"demand:{prod}:{site}"
                forecast = forecasts_used.get((prod, site))

                if forecast is not None:
                    if key not in self._demand_observations:
                        self._demand_observations[key] = []
                    self._demand_observations[key].append((forecast, actual))

                    # Trigger recalibration if enough new observations
                    if (
                        self.config.auto_recalibrate
                        and len(self._demand_observations[key]) >= self.config.min_calibration_points
                    ):
                        self._recalibrate_demand(prod, site)
                        updates[key] = len(self._demand_observations[key])

        # Update lead time predictors
        if actual_lead_times and promised_lead_times:
            for supplier, actual_lt in actual_lead_times.items():
                key = f"lead_time:{supplier}"
                promised = promised_lead_times.get(supplier)

                if promised is not None:
                    if key not in self._lead_time_observations:
                        self._lead_time_observations[key] = []
                    self._lead_time_observations[key].append((promised, actual_lt))

                    # Trigger recalibration
                    if (
                        self.config.auto_recalibrate
                        and len(self._lead_time_observations[key]) >= self.config.min_calibration_points
                    ):
                        self._recalibrate_lead_time(supplier)
                        updates[key] = len(self._lead_time_observations[key])

        # Update yield predictors
        if actual_yields and expected_yields_used:
            for prod, actual_yield in actual_yields.items():
                key = f"yield:{prod}"
                expected = expected_yields_used.get(prod)

                if expected is not None:
                    if key not in self._yield_observations:
                        self._yield_observations[key] = []
                    self._yield_observations[key].append((expected, actual_yield))

                    # Trigger recalibration
                    if (
                        self.config.auto_recalibrate
                        and len(self._yield_observations[key]) >= self.config.min_calibration_points
                    ):
                        self._recalibrate_yield(prod)
                        updates[key] = len(self._yield_observations[key])

        # Update most recent cycle with calibration updates
        if self.cycle_history:
            self.cycle_history[-1].calibration_updates = updates

        logger.info(
            f"Observed actuals for {observation_date}: "
            f"{len(actual_demands)} demands, "
            f"{len(actual_lead_times or {})} lead times, "
            f"{len(actual_yields or {})} yields. "
            f"Updated {len(updates)} predictors."
        )

    def _recalibrate_demand(self, product_id: str, site_id: int):
        """Recalibrate demand predictor with accumulated observations"""
        key = f"demand:{product_id}:{site_id}"
        observations = self._demand_observations.get(key, [])

        if len(observations) < self.config.min_calibration_points:
            return

        forecasts = [o[0] for o in observations]
        actuals = [o[1] for o in observations]

        self.conformal_suite.calibrate_demand(
            product_id=product_id,
            site_id=site_id,
            historical_forecasts=forecasts,
            historical_actuals=actuals,
        )

        logger.info(
            f"Recalibrated demand predictor for {key} with {len(observations)} observations"
        )

    def _recalibrate_lead_time(self, supplier_id: str):
        """Recalibrate lead time predictor with accumulated observations"""
        key = f"lead_time:{supplier_id}"
        observations = self._lead_time_observations.get(key, [])

        if len(observations) < self.config.min_calibration_points:
            return

        promised = [o[0] for o in observations]
        actuals = [o[1] for o in observations]

        self.conformal_suite.calibrate_lead_time(
            supplier_id=supplier_id,
            predicted_lead_times=promised,
            actual_lead_times=actuals,
        )

        logger.info(
            f"Recalibrated lead time predictor for {key} with {len(observations)} observations"
        )

    def _recalibrate_yield(self, product_id: str):
        """Recalibrate yield predictor with accumulated observations"""
        key = f"yield:{product_id}"
        observations = self._yield_observations.get(key, [])

        if len(observations) < self.config.min_calibration_points:
            return

        expected = [o[0] for o in observations]
        actuals = [o[1] for o in observations]

        self.conformal_suite.calibrate_yield(
            product_id=product_id,
            process_id=None,
            expected_yields=expected,
            actual_yields=actuals,
        )

        logger.info(
            f"Recalibrated yield predictor for {key} with {len(observations)} observations"
        )

    def evaluate_performance(
        self,
        cycle_id: int,
        realized_cost: float,
        service_level_achieved: float,
    ):
        """
        Evaluate performance of a planning cycle against actuals.

        This enables tracking of:
        - Did conformal coverage hold? (service level >= guarantee)
        - How accurate were cost estimates?
        - Is the system improving over time?

        Args:
            cycle_id: ID of the cycle to evaluate
            realized_cost: Actual realized cost
            service_level_achieved: Actual service level (0-1)
        """
        if cycle_id >= len(self.cycle_history):
            raise ValueError(f"No cycle {cycle_id}")

        cycle = self.cycle_history[cycle_id]
        cycle.realized_cost = realized_cost
        cycle.service_level_achieved = service_level_achieved
        cycle.coverage_met = service_level_achieved >= cycle.conformal_coverage

        # Log performance
        expected_cost = cycle.solution.expected_cost
        cost_error = (
            abs(realized_cost - expected_cost) / expected_cost if expected_cost else 0
        )

        logger.info(
            f"Cycle {cycle_id} performance: "
            f"cost_error={cost_error:.1%}, "
            f"service_level={service_level_achieved:.1%} "
            f"(guarantee={cycle.conformal_coverage:.1%}, met={cycle.coverage_met})"
        )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of performance across all cycles"""
        if not self.cycle_history:
            return {"n_cycles": 0}

        evaluated = [c for c in self.cycle_history if c.realized_cost is not None]

        if not evaluated:
            return {
                "n_cycles": len(self.cycle_history),
                "n_evaluated": 0,
            }

        # Coverage analysis
        coverage_met = sum(1 for c in evaluated if c.coverage_met)

        # Cost accuracy
        cost_errors = []
        for c in evaluated:
            if c.solution.expected_cost > 0:
                error = abs(c.realized_cost - c.solution.expected_cost) / c.solution.expected_cost
                cost_errors.append(error)

        return {
            "n_cycles": len(self.cycle_history),
            "n_evaluated": len(evaluated),
            "coverage_hit_rate": coverage_met / len(evaluated),
            "avg_cost_error": float(np.mean(cost_errors)) if cost_errors else None,
            "avg_service_level": float(
                np.mean([c.service_level_achieved for c in evaluated])
            ),
            "avg_conformal_coverage": float(
                np.mean([c.conformal_coverage for c in evaluated])
            ),
            "calibrated_predictors": self.conformal_suite.get_calibration_summary(),
        }

    def get_cycle_history(self) -> List[Dict[str, Any]]:
        """Get history of all planning cycles as dictionaries"""
        return [cycle.to_dict() for cycle in self.cycle_history]

    def get_learning_progress(self) -> Dict[str, Any]:
        """
        Analyze learning progress over cycles.

        Shows how prediction accuracy and coverage have evolved.
        """
        if len(self.cycle_history) < 2:
            return {"message": "Need at least 2 cycles to analyze learning progress"}

        # Analyze trends
        evaluated = [c for c in self.cycle_history if c.realized_cost is not None]

        if len(evaluated) < 2:
            return {"message": "Need at least 2 evaluated cycles"}

        # Split into early and late cycles
        mid = len(evaluated) // 2
        early = evaluated[:mid]
        late = evaluated[mid:]

        early_coverage_hit = sum(1 for c in early if c.coverage_met) / len(early)
        late_coverage_hit = sum(1 for c in late if c.coverage_met) / len(late)

        early_cost_errors = []
        late_cost_errors = []

        for c in early:
            if c.solution.expected_cost > 0:
                early_cost_errors.append(
                    abs(c.realized_cost - c.solution.expected_cost) / c.solution.expected_cost
                )

        for c in late:
            if c.solution.expected_cost > 0:
                late_cost_errors.append(
                    abs(c.realized_cost - c.solution.expected_cost) / c.solution.expected_cost
                )

        return {
            "n_early_cycles": len(early),
            "n_late_cycles": len(late),
            "early_coverage_hit_rate": early_coverage_hit,
            "late_coverage_hit_rate": late_coverage_hit,
            "coverage_improvement": late_coverage_hit - early_coverage_hit,
            "early_avg_cost_error": float(np.mean(early_cost_errors)) if early_cost_errors else None,
            "late_avg_cost_error": float(np.mean(late_cost_errors)) if late_cost_errors else None,
            "cost_accuracy_improvement": (
                (np.mean(early_cost_errors) - np.mean(late_cost_errors))
                if early_cost_errors and late_cost_errors
                else None
            ),
            "is_improving": (
                late_coverage_hit >= early_coverage_hit
                and (
                    not late_cost_errors
                    or not early_cost_errors
                    or np.mean(late_cost_errors) <= np.mean(early_cost_errors)
                )
            ),
        }

    def reset(self):
        """Reset the planner state"""
        self.conformal_suite.reset()
        self.cycle_history.clear()
        self._demand_observations.clear()
        self._lead_time_observations.clear()
        self._yield_observations.clear()
        logger.info("Reset RollingHorizonSOP - all state cleared")
