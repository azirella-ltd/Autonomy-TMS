"""
Supply Plan Service

Orchestrates supply plan generation using deterministic planning + Monte Carlo evaluation.

Architecture:
1. Generate deterministic plan (POs, MOs, STOs) using classical policies
2. Evaluate plan across Monte Carlo scenarios with stochastic demand
3. Aggregate results into balanced scorecard
4. Generate risk-based recommendations
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session

from app.models.supply_chain_config import SupplyChainConfig, MarketDemand, Site
from app.services.deterministic_planner import (
    DeterministicPlanner,
    DemandForecast,
    PlanningOrder,
    InventoryTarget
)
from app.services.plan_evaluator import PlanEvaluator, PlanExecutionResult
from app.services.stochastic_sampling import (
    StochasticParameters,
    sample_demand,
    sample_lead_times,
    sample_supplier_reliability,
)
from app.services.monte_carlo_planner import (
    PlanObjectives,
    compute_scenario_statistics,
    compute_probability_above_threshold,
    compute_probability_below_threshold,
)


class SupplyPlanService:
    """
    Main service for supply plan generation.

    Coordinates deterministic planning, Monte Carlo evaluation, and
    balanced scorecard generation.
    """

    def __init__(
        self,
        session: Session,
        config: SupplyChainConfig
    ):
        """
        Initialize supply plan service.

        Args:
            session: Database session
            config: Supply chain configuration
        """
        self.session = session
        self.config = config

    def generate_supply_plan(
        self,
        stochastic_params: StochasticParameters,
        objectives: PlanObjectives,
        num_scenarios: int = 1000,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        Generate complete supply plan with probabilistic evaluation.

        Steps:
        1. Aggregate demand forecasts from stochastic parameters
        2. Generate deterministic plan using classical policies
        3. Evaluate plan across Monte Carlo scenarios
        4. Compute balanced scorecard
        5. Generate recommendations

        Args:
            stochastic_params: Stochastic sampling parameters
            objectives: Planning objectives
            num_scenarios: Number of Monte Carlo scenarios
            progress_callback: Optional callback(completed, total)

        Returns:
            Complete supply plan with:
            - orders: List of POs, MOs, STOs
            - inventory_targets: Safety stock and ROP levels
            - scorecard: Balanced scorecard metrics
            - recommendations: Risk-based recommendations
        """
        # Step 1: Create demand forecasts
        demand_forecasts = self._create_demand_forecasts(
            stochastic_params,
            objectives.planning_horizon
        )

        # Step 2: Generate deterministic plan
        planner = DeterministicPlanner(
            self.session,
            self.config,
            objectives.planning_horizon
        )

        orders, inventory_targets = planner.generate_plan(
            demand_forecasts,
            service_level=objectives.service_level_target,
            ordering_cost=100.0,
            holding_cost_rate=0.20
        )

        # Step 3: Evaluate plan with Monte Carlo
        execution_results = self._evaluate_plan_monte_carlo(
            orders,
            inventory_targets,
            stochastic_params,
            objectives,
            num_scenarios,
            progress_callback
        )

        # Step 4: Compute balanced scorecard
        scorecard = self._compute_balanced_scorecard(
            execution_results,
            objectives
        )

        # Step 5: Generate recommendations
        recommendations = self._generate_recommendations(
            scorecard,
            objectives
        )

        return {
            "orders": self._serialize_orders(orders),
            "inventory_targets": self._serialize_targets(inventory_targets),
            "scorecard": scorecard,
            "recommendations": recommendations,
            "num_scenarios": num_scenarios,
        }

    def _create_demand_forecasts(
        self,
        stochastic_params: StochasticParameters,
        horizon: int
    ) -> Dict[Tuple[int, int], DemandForecast]:
        """
        Create demand forecasts from stochastic parameters.

        Args:
            stochastic_params: Stochastic parameters
            horizon: Planning horizon

        Returns:
            {(item_id, node_id): DemandForecast}
        """
        forecasts = {}

        # Get market demands
        market_demands = (
            self.session.query(MarketDemand)
            .filter(MarketDemand.config_id == self.config.id)
            .all()
        )

        for market_demand in market_demands:
            # Extract mean demand
            demand_pattern = market_demand.demand_pattern or {}
            params = demand_pattern.get("parameters", {})
            mean_demand = params.get("mean", 100.0)

            # Calculate standard deviation based on model
            if stochastic_params.demand_model == "normal":
                std_dev = mean_demand * stochastic_params.demand_variability
            elif stochastic_params.demand_model == "poisson":
                std_dev = np.sqrt(mean_demand)  # Poisson: variance = mean
            else:
                std_dev = mean_demand * stochastic_params.demand_variability

            # Create weekly demand array (constant mean)
            weekly_demand = np.full(horizon, mean_demand)

            # Total demand over horizon
            total_demand = mean_demand * horizon

            # Use the product_id from the market demand record
            item_id = market_demand.product_id or 1
            node_id = market_demand.market_id or market_demand.id

            forecasts[(item_id, node_id)] = DemandForecast(
                item_id=item_id,
                node_id=node_id,
                weekly_demand=weekly_demand,
                demand_std_dev=std_dev,
                total_demand=total_demand
            )

        return forecasts

    def _evaluate_plan_monte_carlo(
        self,
        orders: List[PlanningOrder],
        inventory_targets: List[InventoryTarget],
        stochastic_params: StochasticParameters,
        objectives: PlanObjectives,
        num_scenarios: int,
        progress_callback: Optional[callable]
    ) -> List[PlanExecutionResult]:
        """
        Evaluate plan across Monte Carlo scenarios.

        Args:
            orders: Planned orders
            inventory_targets: Inventory targets
            stochastic_params: Stochastic parameters
            objectives: Planning objectives
            num_scenarios: Number of scenarios
            progress_callback: Progress callback

        Returns:
            List of execution results
        """
        evaluator = PlanEvaluator(objectives.planning_horizon)
        results = []

        for i in range(num_scenarios):
            # Sample scenario parameters
            demand_samples = sample_demand(
                self.session,
                self.config,
                stochastic_params,
                objectives.planning_horizon
            )

            lead_time_samples = sample_lead_times(
                self.session,
                self.config,
                stochastic_params
            )

            reliability_samples = sample_supplier_reliability(
                self.session,
                self.config,
                stochastic_params,
                objectives.planning_horizon
            )

            # Evaluate plan in this scenario
            result = evaluator.evaluate_plan(
                orders,
                inventory_targets,
                demand_samples,
                lead_time_samples,
                reliability_samples,
                scenario_number=i
            )

            results.append(result)

            # Progress callback
            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(i + 1, num_scenarios)

        return results

    def _compute_balanced_scorecard(
        self,
        results: List[PlanExecutionResult],
        objectives: PlanObjectives
    ) -> Dict:
        """Compute balanced scorecard from execution results."""
        # Convert to dict format for statistics
        scenarios_dict = [
            {
                "total_cost": r.total_cost,
                "inventory_carrying_cost": r.inventory_carrying_cost,
                "backlog_penalty_cost": r.backlog_penalty_cost,
                "otif": r.otif,
                "fill_rate": r.fill_rate,
                "backorder_rate": r.backorder_rate,
                "inventory_turns": r.inventory_turns,
                "avg_days_of_supply": r.avg_days_of_supply,
                "bullwhip_ratio": r.bullwhip_ratio,
                "total_throughput": r.total_throughput,
                "supplier_reliability_score": r.supplier_reliability_score,
            }
            for r in results
        ]

        # Financial
        total_cost_stats = compute_scenario_statistics(scenarios_dict, "total_cost")
        if objectives.budget_limit:
            total_cost_stats["probability_under_budget"] = compute_probability_below_threshold(
                scenarios_dict, "total_cost", objectives.budget_limit
            )

        inventory_cost_stats = compute_scenario_statistics(scenarios_dict, "inventory_carrying_cost")
        backlog_cost_stats = compute_scenario_statistics(scenarios_dict, "backlog_penalty_cost")

        # Customer
        otif_stats = compute_scenario_statistics(scenarios_dict, "otif")
        otif_stats["probability_above_target"] = compute_probability_above_threshold(
            scenarios_dict, "otif", objectives.service_level_target
        )
        otif_stats["target"] = objectives.service_level_target
        otif_stats["confidence_requirement"] = objectives.service_level_confidence

        fill_rate_stats = compute_scenario_statistics(scenarios_dict, "fill_rate")
        backorder_stats = compute_scenario_statistics(scenarios_dict, "backorder_rate")

        # Operational
        turns_stats = compute_scenario_statistics(scenarios_dict, "inventory_turns")
        dos_stats = compute_scenario_statistics(scenarios_dict, "avg_days_of_supply")
        bullwhip_stats = compute_scenario_statistics(scenarios_dict, "bullwhip_ratio")

        # Strategic
        throughput_stats = compute_scenario_statistics(scenarios_dict, "total_throughput")
        reliability_stats = compute_scenario_statistics(scenarios_dict, "supplier_reliability_score")

        return {
            "config_id": self.config.id,
            "config_name": self.config.name,
            "num_scenarios": len(results),
            "planning_horizon": objectives.planning_horizon,
            "financial": {
                "total_cost": total_cost_stats,
                "inventory_carrying_cost": inventory_cost_stats,
                "backlog_penalty_cost": backlog_cost_stats,
            },
            "customer": {
                "otif": otif_stats,
                "fill_rate": fill_rate_stats,
                "backorder_rate": backorder_stats,
            },
            "operational": {
                "inventory_turns": turns_stats,
                "days_of_supply": dos_stats,
                "bullwhip_ratio": bullwhip_stats,
            },
            "strategic": {
                "total_throughput": throughput_stats,
                "supplier_reliability": reliability_stats,
            },
        }

    def _generate_recommendations(
        self,
        scorecard: Dict,
        objectives: PlanObjectives
    ) -> List[Dict]:
        """Generate risk-based recommendations."""
        recommendations = []

        # Check OTIF confidence
        otif_prob = scorecard["customer"]["otif"].get("probability_above_target", 0)
        if otif_prob < objectives.service_level_confidence:
            recommendations.append({
                "type": "service_level_risk",
                "severity": "high" if (objectives.service_level_confidence - otif_prob) > 0.10 else "medium",
                "metric": "OTIF",
                "message": f"P(OTIF > {objectives.service_level_target*100:.0f}%) = {otif_prob*100:.1f}% is below {objectives.service_level_confidence*100:.0f}% confidence.",
                "recommendation": f"Increase safety stock by 8-12% to achieve {objectives.service_level_confidence*100:.0f}% confidence."
            })

        # Check budget risk
        if objectives.budget_limit:
            budget_prob = scorecard["financial"]["total_cost"].get("probability_under_budget", 0)
            if budget_prob < 0.90:
                recommendations.append({
                    "type": "budget_risk",
                    "severity": "high",
                    "metric": "Total Cost",
                    "message": f"P(Cost < ${objectives.budget_limit:,.0f}) = {budget_prob*100:.1f}% - high budget overrun risk.",
                    "recommendation": "Consider reducing service level target or increasing budget by 10%."
                })

        # Check bullwhip
        avg_bullwhip = scorecard["operational"]["bullwhip_ratio"]["expected"]
        if avg_bullwhip > 2.0:
            recommendations.append({
                "type": "bullwhip_effect",
                "severity": "medium",
                "metric": "Bullwhip Ratio",
                "message": f"Expected bullwhip ratio of {avg_bullwhip:.2f} indicates demand amplification.",
                "recommendation": "Improve demand visibility and consider vendor-managed inventory (VMI)."
            })

        return recommendations

    def _serialize_orders(self, orders: List[PlanningOrder]) -> List[Dict]:
        """Serialize orders to dict format."""
        return [
            {
                "order_type": order.order_type.value,
                "item_id": order.item_id,
                "source_node_id": order.source_node_id,
                "destination_node_id": order.destination_node_id,
                "quantity": float(order.quantity),
                "planned_week": order.planned_week,
                "delivery_week": order.delivery_week,
                "cost": float(order.cost),
            }
            for order in orders
        ]

    def _serialize_targets(self, targets: List[InventoryTarget]) -> List[Dict]:
        """Serialize inventory targets to dict format."""
        return [
            {
                "node_id": target.node_id,
                "item_id": target.item_id,
                "safety_stock": float(target.safety_stock),
                "reorder_point": float(target.reorder_point),
                "order_quantity": float(target.order_quantity),
                "review_period": target.review_period,
            }
            for target in targets
        ]
