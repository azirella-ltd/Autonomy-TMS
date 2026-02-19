"""
Monte Carlo Supply Planning Engine

Runs Monte Carlo simulations with agent-driven decision-making to generate
probabilistic supply plans with balanced scorecard metrics.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session
from dataclasses import dataclass

from app.models.supply_chain_config import SupplyChainConfig, Node
from app.models.sc_entities import Product
from app.services.stochastic_sampling import (
    StochasticParameters,
    generate_scenario,
    compute_scenario_statistics,
    compute_probability_above_threshold,
    compute_probability_below_threshold
)


@dataclass
class PlanObjectives:
    """Business objectives and constraints for supply plan generation."""

    planning_horizon: int = 52  # weeks
    primary_objective: str = "minimize_cost"  # minimize_cost, maximize_service, balance
    service_level_target: float = 0.95  # OTIF target
    service_level_confidence: float = 0.90  # P(OTIF > target) >= confidence
    budget_limit: Optional[float] = None
    inventory_dos_min: Optional[int] = None
    inventory_dos_max: Optional[int] = None


@dataclass
class ScenarioResult:
    """Results from a single Monte Carlo scenario."""

    scenario_number: int

    # Financial metrics
    total_cost: float
    inventory_carrying_cost: float
    backlog_penalty_cost: float
    ordering_cost: float

    # Customer metrics
    otif: float  # On-Time-In-Full %
    fill_rate: float
    backorder_rate: float
    service_level: float

    # Operational metrics
    inventory_turns: float
    avg_days_of_supply: float
    forecast_accuracy: Optional[float]
    bullwhip_ratio: float

    # Strategic metrics
    total_throughput: float
    avg_lead_time: float
    supplier_reliability_score: float

    # Detailed state for this scenario
    final_inventory: Dict[int, float]  # {node_id: inventory}
    final_backlog: Dict[int, float]  # {node_id: backlog}
    avg_inventory: Dict[int, float]  # {node_id: avg_inventory}


class MonteCarloPlanner:
    """Monte Carlo simulation engine for probabilistic supply planning."""

    def __init__(
        self,
        session: Session,
        config: SupplyChainConfig,
        agent_strategy: str = "trm"
    ):
        """
        Initialize Monte Carlo planner.

        Args:
            session: Database session
            config: Supply chain configuration
            agent_strategy: Agent strategy to use (trm, gnn, llm, pid, naive)
        """
        self.session = session
        self.config = config
        self.agent_strategy = agent_strategy

    def run_scenario_simulation(
        self,
        scenario: Dict,
        objectives: PlanObjectives
    ) -> ScenarioResult:
        """
        Run simulation for a single scenario.

        NOTE: This is a PROTOTYPE implementation using simplified period-by-period
        simulation with heuristics. Full production implementation (Phase 5) will
        integrate with the actual SupplyChainLine/DAG engine.

        Args:
            scenario: Scenario parameters (demand, lead times, etc.)
            objectives: Planning objectives

        Returns:
            ScenarioResult with all metrics computed
        """
        horizon = objectives.planning_horizon
        demand_samples = scenario["demand_samples"]
        lead_time_samples = scenario["lead_time_samples"]
        supplier_reliability = scenario["supplier_reliability"]

        # Get agent efficiency factor
        agent_efficiency = self._get_agent_efficiency(self.agent_strategy)

        # Number of nodes (lanes proxy for node count)
        num_nodes = max(len(lead_time_samples), 1)

        # Initialize node states (simplified multi-echelon)
        # Each node has inventory, backlog, pipeline shipments
        node_inventories = np.zeros((num_nodes, horizon + 1))
        node_backlogs = np.zeros((num_nodes, horizon + 1))
        node_orders = np.zeros((num_nodes, horizon))
        node_shipments = np.zeros((num_nodes, horizon))

        # Initial inventory (proportional to expected demand)
        total_demand = sum(
            np.sum(demands) for demands in demand_samples.values()
        )
        avg_period_demand = total_demand / horizon if horizon > 0 else 100

        # Safety stock increases with lower agent efficiency
        # Each node holds 2-4 periods of demand as safety stock
        safety_stock_periods = 2.0 + 2.0 * (1 - agent_efficiency)
        for i in range(num_nodes):
            node_inventories[i, 0] = avg_period_demand * safety_stock_periods

        # Track period demands for metrics
        period_demands = []

        # Simulate period by period
        for t in range(horizon):
            # Get demand for this period (from first market)
            period_demand = 0
            for market_id, demands in demand_samples.items():
                if t < len(demands):
                    period_demand += demands[t]

            period_demands.append(period_demand)

            # Process each node (downstream to upstream)
            for i in range(num_nodes):
                # Starting inventory for this period (from last period's ending + incoming shipments)
                current_inventory = node_inventories[i, t]
                current_backlog = node_backlogs[i, t]

                # Receive shipments from upstream (if not first node)
                if i > 0:
                    # Shipment arrives based on lead time
                    avg_lead_time = 2  # Default
                    if lead_time_samples:
                        avg_lead_time = int(np.round(np.mean(list(lead_time_samples.values()))))

                    if t >= avg_lead_time:
                        past_order_period = max(0, int(t - avg_lead_time))
                        # Get shipment from upstream node's previous production
                        shipment = node_orders[i, past_order_period]

                        # Apply supplier reliability (random delays/shortages)
                        if supplier_reliability:
                            reliability_list = list(supplier_reliability.values())
                            if reliability_list and t < len(reliability_list[0]):
                                on_time = reliability_list[min(i, len(reliability_list) - 1)][t]
                                if on_time < 0.5:  # Delayed shipment
                                    shipment *= 0.6

                        current_inventory += shipment

                # Fulfill demand from downstream (or customer)
                if i == 0:
                    # First node receives customer demand
                    incoming_demand = period_demand + current_backlog
                else:
                    # Receive orders from downstream node
                    incoming_demand = node_orders[i - 1, t] + current_backlog

                # Ship what's available
                shipped = min(current_inventory, incoming_demand)
                node_shipments[i, t] = shipped

                # Update inventory and backlog for next period
                node_inventories[i, t + 1] = current_inventory - shipped
                unfulfilled = max(0, incoming_demand - shipped)
                node_backlogs[i, t + 1] = unfulfilled

                # Decide order quantity (agent policy)
                # Base order on actual demand signal
                base_order = period_demand

                # Better agents order more accurately with less bullwhip
                if agent_efficiency > 0.7:
                    # High efficiency: order close to actual demand
                    order_multiplier = 1.0 + 0.05 * (1 - agent_efficiency)
                else:
                    # Low efficiency: creates bullwhip effect
                    order_multiplier = 1.0 + 0.3 * (1 - agent_efficiency)

                # Add stochastic noise
                noise_factor = 0.15 * (1 - agent_efficiency)
                order_noise = np.random.normal(0, noise_factor * max(base_order, 1))

                # Inventory position adjustment (gradual)
                inventory_position = node_inventories[i, t + 1] - node_backlogs[i, t + 1]
                target_inventory = avg_period_demand * safety_stock_periods
                inventory_gap = target_inventory - inventory_position
                adjustment = inventory_gap * agent_efficiency * 0.08  # Gentle adjustment

                order_quantity = base_order * order_multiplier + order_noise + adjustment

                # Bounds checking
                node_orders[i, t] = np.clip(order_quantity, 0, avg_period_demand * 5)

        # Calculate metrics from simulation results

        # Financial metrics
        total_inventory = np.sum(node_inventories[:, :-1])
        total_backlog = np.sum(node_backlogs[:, :-1])

        inventory_carrying_cost = total_inventory * 1.0  # $1 per unit per period
        backlog_penalty_cost = total_backlog * 2.0  # $2 per unit per period
        ordering_cost = np.sum(node_orders) * 0.05  # $0.05 per unit ordered
        total_cost = inventory_carrying_cost + backlog_penalty_cost + ordering_cost

        # Customer metrics
        # Total demand is sum of all market demands across all periods
        total_demand_all_periods = total_demand
        total_shipped = np.sum(node_shipments[0, :])  # First node ships to customer
        fill_rate = min(1.0, total_shipped / max(1, total_demand_all_periods))

        # OTIF: delivered on time (no backlog) and in full
        periods_with_backlog = np.sum(node_backlogs[0, 1:] > 0)
        otif = 1.0 - (periods_with_backlog / horizon)

        backorder_rate = 1.0 - fill_rate
        service_level = otif

        # Operational metrics
        avg_inventory = np.mean(node_inventories[:, :-1])
        if avg_inventory > 0 and total_demand > 0:
            # Annualized inventory turns
            inventory_turns = (total_demand / avg_inventory) * (52 / horizon)
        else:
            inventory_turns = 0

        avg_days_of_supply = (avg_inventory / max(1, avg_period_demand)) * 7  # Convert to days

        # Bullwhip effect: ratio of order variability to demand variability
        if len(period_demands) > 1:
            demand_std = np.std(period_demands)
            order_std = np.std(node_orders[0, :])
            bullwhip_ratio = order_std / max(demand_std, 0.01)
        else:
            bullwhip_ratio = 1.0

        # Strategic metrics
        total_throughput = total_shipped
        avg_lead_time = np.mean(list(lead_time_samples.values())) if lead_time_samples else 2

        supplier_reliability_score = np.mean([
            np.mean(reliability) for reliability in supplier_reliability.values()
        ]) if supplier_reliability else 0.95

        # Final states
        final_inventory = {i: float(node_inventories[i, -1]) for i in range(num_nodes)}
        final_backlog = {i: float(node_backlogs[i, -1]) for i in range(num_nodes)}
        avg_inventory_by_node = {i: float(np.mean(node_inventories[i, :-1])) for i in range(num_nodes)}

        return ScenarioResult(
            scenario_number=scenario["scenario_number"],
            total_cost=total_cost,
            inventory_carrying_cost=inventory_carrying_cost,
            backlog_penalty_cost=backlog_penalty_cost,
            ordering_cost=ordering_cost,
            otif=otif,
            fill_rate=fill_rate,
            backorder_rate=backorder_rate,
            service_level=service_level,
            inventory_turns=inventory_turns,
            avg_days_of_supply=avg_days_of_supply,
            forecast_accuracy=None,  # Would require historical data
            bullwhip_ratio=bullwhip_ratio,
            total_throughput=total_throughput,
            avg_lead_time=avg_lead_time,
            supplier_reliability_score=supplier_reliability_score,
            final_inventory=final_inventory,
            final_backlog=final_backlog,
            avg_inventory=avg_inventory_by_node
        )

    def _get_agent_efficiency(self, strategy: str) -> float:
        """
        Get relative efficiency of agent strategy (0-1).

        Args:
            strategy: Agent strategy name

        Returns:
            Efficiency factor (higher = better performance)
        """
        efficiency_map = {
            "naive": 0.3,
            "bullwhip": 0.2,
            "conservative": 0.5,
            "pid": 0.6,
            "reactive": 0.55,
            "ml_forecast": 0.7,
            "optimizer": 0.75,
            "trm": 0.85,
            "gnn": 0.90,
            "llm": 0.80
        }
        return efficiency_map.get(strategy.lower(), 0.5)

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
            progress_callback: Optional callback(completed, total) for progress updates

        Returns:
            List of ScenarioResult objects
        """
        scenario_results = []

        for i in range(num_scenarios):
            # Generate scenario with stochastic parameters
            scenario = generate_scenario(
                self.session,
                self.config,
                parameters,
                objectives.planning_horizon,
                i
            )

            # Run simulation for this scenario
            result = self.run_scenario_simulation(scenario, objectives)
            scenario_results.append(result)

            # Progress callback
            if progress_callback is not None and (i + 1) % 10 == 0:
                progress_callback(i + 1, num_scenarios)

        return scenario_results

    def compute_balanced_scorecard(
        self,
        scenario_results: List[ScenarioResult],
        objectives: PlanObjectives
    ) -> Dict:
        """
        Aggregate scenario results into probabilistic balanced scorecard.

        Args:
            scenario_results: List of scenario results
            objectives: Planning objectives (for thresholds)

        Returns:
            Balanced scorecard with probability distributions
        """
        # Convert scenario results to dict format for statistics computation
        scenarios_dict = [
            {
                "total_cost": s.total_cost,
                "inventory_carrying_cost": s.inventory_carrying_cost,
                "backlog_penalty_cost": s.backlog_penalty_cost,
                "otif": s.otif,
                "fill_rate": s.fill_rate,
                "backorder_rate": s.backorder_rate,
                "inventory_turns": s.inventory_turns,
                "avg_days_of_supply": s.avg_days_of_supply,
                "bullwhip_ratio": s.bullwhip_ratio,
                "total_throughput": s.total_throughput,
                "supplier_reliability_score": s.supplier_reliability_score
            }
            for s in scenario_results
        ]

        # Financial perspective
        total_cost_stats = compute_scenario_statistics(scenarios_dict, "total_cost")
        if objectives.budget_limit:
            total_cost_stats["probability_under_budget"] = compute_probability_below_threshold(
                scenarios_dict, "total_cost", objectives.budget_limit
            )

        inventory_cost_stats = compute_scenario_statistics(scenarios_dict, "inventory_carrying_cost")
        backlog_cost_stats = compute_scenario_statistics(scenarios_dict, "backlog_penalty_cost")

        # Customer perspective
        otif_stats = compute_scenario_statistics(scenarios_dict, "otif")
        otif_stats["probability_above_target"] = compute_probability_above_threshold(
            scenarios_dict, "otif", objectives.service_level_target
        )
        otif_stats["target"] = objectives.service_level_target
        otif_stats["confidence_requirement"] = objectives.service_level_confidence

        fill_rate_stats = compute_scenario_statistics(scenarios_dict, "fill_rate")
        backorder_rate_stats = compute_scenario_statistics(scenarios_dict, "backorder_rate")

        # Operational perspective
        inventory_turns_stats = compute_scenario_statistics(scenarios_dict, "inventory_turns")
        dos_stats = compute_scenario_statistics(scenarios_dict, "avg_days_of_supply")

        if objectives.inventory_dos_min and objectives.inventory_dos_max:
            dos_in_range = sum(
                1 for s in scenarios_dict
                if objectives.inventory_dos_min <= s["avg_days_of_supply"] <= objectives.inventory_dos_max
            ) / len(scenarios_dict)
            dos_stats["probability_in_target_range"] = dos_in_range

        bullwhip_stats = compute_scenario_statistics(scenarios_dict, "bullwhip_ratio")

        # Strategic perspective
        throughput_stats = compute_scenario_statistics(scenarios_dict, "total_throughput")
        reliability_stats = compute_scenario_statistics(scenarios_dict, "supplier_reliability_score")

        # Build balanced scorecard
        scorecard = {
            "config_id": self.config.id,
            "config_name": self.config.name,
            "agent_strategy": self.agent_strategy,
            "num_scenarios": len(scenario_results),
            "planning_horizon": objectives.planning_horizon,

            "financial": {
                "total_cost": total_cost_stats,
                "inventory_carrying_cost": inventory_cost_stats,
                "backlog_penalty_cost": backlog_cost_stats
            },

            "customer": {
                "otif": otif_stats,
                "fill_rate": fill_rate_stats,
                "backorder_rate": backorder_rate_stats
            },

            "operational": {
                "inventory_turns": inventory_turns_stats,
                "days_of_supply": dos_stats,
                "bullwhip_ratio": bullwhip_stats
            },

            "strategic": {
                "total_throughput": throughput_stats,
                "supplier_reliability": reliability_stats
            }
        }

        return scorecard

    def generate_recommendations(
        self,
        scorecard: Dict,
        objectives: PlanObjectives
    ) -> List[Dict]:
        """
        Generate actionable recommendations based on scorecard results.

        Args:
            scorecard: Balanced scorecard results
            objectives: Planning objectives

        Returns:
            List of recommendation dictionaries
        """
        recommendations = []

        # Check OTIF confidence
        otif_prob = scorecard["customer"]["otif"].get("probability_above_target", 0)
        required_confidence = objectives.service_level_confidence

        if otif_prob < required_confidence:
            gap_pct = (required_confidence - otif_prob) * 100
            recommendations.append({
                "type": "service_level_risk",
                "severity": "high" if gap_pct > 10 else "medium",
                "metric": "OTIF",
                "current_probability": otif_prob,
                "target_probability": required_confidence,
                "message": f"P(OTIF > {objectives.service_level_target*100:.0f}%) = {otif_prob*100:.1f}% is below {required_confidence*100:.0f}% confidence requirement.",
                "recommendation": f"Increase safety stock by 8-12% to achieve {required_confidence*100:.0f}% confidence."
            })

        # Check budget risk
        if objectives.budget_limit:
            budget_prob = scorecard["financial"]["total_cost"].get("probability_under_budget", 0)
            if budget_prob < 0.90:
                recommendations.append({
                    "type": "budget_risk",
                    "severity": "high",
                    "metric": "Total Cost",
                    "current_probability": budget_prob,
                    "target_probability": 0.90,
                    "message": f"P(Cost < ${objectives.budget_limit:,.0f}) = {budget_prob*100:.1f}% - high risk of budget overrun.",
                    "recommendation": "Consider reducing service level target or increasing budget by 10%."
                })

        # Check bullwhip effect
        avg_bullwhip = scorecard["operational"]["bullwhip_ratio"]["expected"]
        if avg_bullwhip > 2.0:
            recommendations.append({
                "type": "bullwhip_effect",
                "severity": "medium",
                "metric": "Bullwhip Ratio",
                "current_value": avg_bullwhip,
                "target_value": 1.5,
                "message": f"Expected bullwhip ratio of {avg_bullwhip:.2f} indicates demand amplification.",
                "recommendation": "Improve demand visibility and consider vendor-managed inventory (VMI)."
            })

        # Check inventory efficiency
        avg_turns = scorecard["operational"]["inventory_turns"]["expected"]
        if avg_turns < 8.0:
            recommendations.append({
                "type": "inventory_efficiency",
                "severity": "low",
                "metric": "Inventory Turns",
                "current_value": avg_turns,
                "target_value": 10.0,
                "message": f"Expected inventory turns of {avg_turns:.1f} is below target.",
                "recommendation": "Reduce safety stock levels or improve forecast accuracy to increase turns."
            })

        return recommendations


def format_scorecard_summary(scorecard: Dict) -> str:
    """
    Format balanced scorecard into human-readable summary.

    Args:
        scorecard: Balanced scorecard dictionary

    Returns:
        Formatted string summary
    """
    summary = f"""
Balanced Scorecard Summary
==========================
Configuration: {scorecard['config_name']}
Agent Strategy: {scorecard['agent_strategy']}
Scenarios: {scorecard['num_scenarios']}
Planning Horizon: {scorecard['planning_horizon']} weeks

Financial Perspective:
  Total Cost: ${scorecard['financial']['total_cost']['expected']:,.0f} (Expected)
    Range: ${scorecard['financial']['total_cost']['p10']:,.0f} - ${scorecard['financial']['total_cost']['p90']:,.0f} (P10-P90)
  Inventory Carrying: ${scorecard['financial']['inventory_carrying_cost']['expected']:,.0f}
  Backlog Penalty: ${scorecard['financial']['backlog_penalty_cost']['expected']:,.0f}

Customer Perspective:
  OTIF: {scorecard['customer']['otif']['expected']*100:.1f}% (Expected)
    P(OTIF > {scorecard['customer']['otif']['target']*100:.0f}%) = {scorecard['customer']['otif']['probability_above_target']*100:.1f}%
  Fill Rate: {scorecard['customer']['fill_rate']['expected']*100:.1f}%

Operational Perspective:
  Inventory Turns: {scorecard['operational']['inventory_turns']['expected']:.1f} per year
  Days of Supply: {scorecard['operational']['days_of_supply']['expected']:.0f} days
  Bullwhip Ratio: {scorecard['operational']['bullwhip_ratio']['expected']:.2f}

Strategic Perspective:
  Total Throughput: {scorecard['strategic']['total_throughput']['expected']:,.0f} units
  Supplier Reliability: {scorecard['strategic']['supplier_reliability']['expected']*100:.1f}%
"""
    return summary
