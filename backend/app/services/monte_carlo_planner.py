"""
Monte Carlo Supply Planning Engine

DB-coupled planner that runs Monte Carlo simulations with agent-driven
decision-making. Pure-math simulation, scorecard computation, and
recommendations delegate to Autonomy-Core:
  azirella_data_model.simulation.monte_carlo

This module keeps the DB-coupled MonteCarloPlanner class and re-exports
Core data classes for backward compatibility.
"""

from typing import Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.sc_entities import Product
from app.services.stochastic_sampling import (
    StochasticParameters,
    generate_scenario,
)

# Re-export Core pure-math data classes and functions for backward compat
from azirella_data_model.simulation.monte_carlo import (  # noqa: F401
    PlanObjectives,
    ScenarioResult,
    run_scenario_simulation as _run_scenario_simulation,
    compute_balanced_scorecard as _compute_balanced_scorecard,
    generate_recommendations as _generate_recommendations,
    format_scorecard_summary,
    get_agent_efficiency,
)

# Also re-export the stochastic stats functions that callers may import from here
from azirella_data_model.stochastic.sampling import (  # noqa: F401
    compute_scenario_statistics,
    compute_probability_above_threshold,
    compute_probability_below_threshold,
)


class MonteCarloPlanner:
    """Monte Carlo simulation engine for probabilistic supply planning.

    DB-coupled wrapper: holds a session and config, delegates simulation
    math to Core's pure functions.
    """

    def __init__(
        self,
        session: Session,
        config: SupplyChainConfig,
        agent_strategy: str = "trm"
    ):
        self.session = session
        self.config = config
        self.agent_strategy = agent_strategy

    def run_scenario_simulation(
        self,
        scenario: Dict,
        objectives: PlanObjectives
    ) -> ScenarioResult:
        """Run simulation for a single scenario (delegates to Core)."""
        return _run_scenario_simulation(
            scenario, objectives, self.agent_strategy
        )

    def _get_agent_efficiency(self, strategy: str) -> float:
        """Get relative efficiency of agent strategy (0-1)."""
        return get_agent_efficiency(strategy)

    def run_monte_carlo_simulation(
        self,
        parameters: StochasticParameters,
        objectives: PlanObjectives,
        num_scenarios: int = 1000,
        progress_callback: Optional[callable] = None
    ) -> List[ScenarioResult]:
        """
        Run Monte Carlo simulation with multiple scenarios.

        Args:
            parameters: Stochastic sampling parameters
            objectives: Planning objectives
            num_scenarios: Number of scenarios to simulate
            progress_callback: Optional callback(completed, total)

        Returns:
            List of ScenarioResult objects
        """
        scenario_results = []

        for i in range(num_scenarios):
            scenario = generate_scenario(
                self.session,
                self.config,
                parameters,
                objectives.planning_horizon,
                i
            )

            result = self.run_scenario_simulation(scenario, objectives)
            scenario_results.append(result)

            if progress_callback is not None and (i + 1) % 10 == 0:
                progress_callback(i + 1, num_scenarios)

        return scenario_results

    def compute_balanced_scorecard(
        self,
        scenario_results: List[ScenarioResult],
        objectives: PlanObjectives
    ) -> Dict:
        """Aggregate scenario results into probabilistic balanced scorecard."""
        return _compute_balanced_scorecard(
            scenario_results,
            objectives,
            config_id=self.config.id,
            config_name=self.config.name,
            agent_strategy=self.agent_strategy,
        )

    def generate_recommendations(
        self,
        scorecard: Dict,
        objectives: PlanObjectives
    ) -> List[Dict]:
        """Generate actionable recommendations based on scorecard results."""
        return _generate_recommendations(scorecard, objectives)
