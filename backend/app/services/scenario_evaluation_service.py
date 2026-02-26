"""
Scenario Evaluation Service - Agent-Driven What-If Analysis

Enables agents to create and evaluate alternative scenarios to assess
the impact of different decisions using the Probabilistic Balanced Scorecard.

Key Capabilities:
1. CREATE SCENARIOS: Generate alternative scenarios from different decisions
2. EVALUATE IMPACT: Run Monte Carlo simulation for probabilistic outcomes
3. COMPARE SCENARIOS: Rank by balanced scorecard metrics
4. RECOMMEND: Select best scenario with confidence intervals

Powell Framework Integration:
- Scenarios are used for CFA (Cost Function Approximation) policy evaluation
- Each scenario represents a different policy parameterization
- Balanced scorecard provides the objective function
- Results feed back to belief state updates

Use Cases:
- ATP agent creates scenarios for different allocation priorities
- Rebalancing agent evaluates transfer alternatives
- tGNN evaluates network-wide allocation strategies
- S&OP evaluates strategic parameter changes
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import logging
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.powell import PowellBeliefState, EntityType

logger = logging.getLogger(__name__)


# =============================================================================
# Scenario Types and Configuration
# =============================================================================

class ScenarioType(str, Enum):
    """Types of scenarios that can be evaluated."""
    ATP_ALLOCATION = "atp_allocation"         # Different ATP allocation strategies
    INVENTORY_REBALANCE = "inventory_rebalance"  # Transfer alternatives
    PO_TIMING = "po_timing"                   # PO creation timing alternatives
    CAPACITY_ALLOCATION = "capacity_allocation"  # Production capacity allocation
    SOURCING_STRATEGY = "sourcing_strategy"   # Alternative sourcing decisions
    NETWORK_FLOW = "network_flow"             # Full network optimization


class ScorecardPerspective(str, Enum):
    """Balanced scorecard perspectives."""
    FINANCIAL = "financial"
    CUSTOMER = "customer"
    OPERATIONAL = "operational"
    STRATEGIC = "strategic"


# =============================================================================
# Balanced Scorecard Metrics
# =============================================================================

@dataclass
class ScoreMetric:
    """A single metric in the balanced scorecard."""
    name: str
    perspective: ScorecardPerspective
    value: float
    unit: str
    weight: float = 1.0

    # Probabilistic bounds (from Monte Carlo)
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None

    # Target and threshold
    target: Optional[float] = None
    threshold_good: Optional[float] = None
    threshold_bad: Optional[float] = None

    # Direction (higher_is_better or lower_is_better)
    direction: str = "higher_is_better"


@dataclass
class BalancedScorecard:
    """Complete balanced scorecard for a scenario."""
    # Financial Perspective
    total_cost: ScoreMetric = None
    inventory_holding_cost: ScoreMetric = None
    stockout_cost: ScoreMetric = None
    transportation_cost: ScoreMetric = None
    working_capital: ScoreMetric = None

    # Customer Perspective
    service_level: ScoreMetric = None
    otif_rate: ScoreMetric = None
    fill_rate: ScoreMetric = None
    order_lead_time: ScoreMetric = None
    customer_satisfaction: ScoreMetric = None

    # Operational Perspective
    inventory_turns: ScoreMetric = None
    days_of_supply: ScoreMetric = None
    capacity_utilization: ScoreMetric = None
    supplier_reliability: ScoreMetric = None
    planning_accuracy: ScoreMetric = None

    # Strategic Perspective
    supply_chain_flexibility: ScoreMetric = None
    resilience_score: ScoreMetric = None
    sustainability_score: ScoreMetric = None
    risk_exposure: ScoreMetric = None

    # Aggregate scores
    overall_score: float = 0.0
    confidence_interval: Tuple[float, float] = (0.0, 0.0)

    def get_all_metrics(self) -> List[ScoreMetric]:
        """Get all non-None metrics."""
        metrics = []
        for field_name in [
            "total_cost", "inventory_holding_cost", "stockout_cost",
            "transportation_cost", "working_capital",
            "service_level", "otif_rate", "fill_rate",
            "order_lead_time", "customer_satisfaction",
            "inventory_turns", "days_of_supply", "capacity_utilization",
            "supplier_reliability", "planning_accuracy",
            "supply_chain_flexibility", "resilience_score",
            "sustainability_score", "risk_exposure",
        ]:
            metric = getattr(self, field_name, None)
            if metric:
                metrics.append(metric)
        return metrics


# =============================================================================
# Scenario Definition
# =============================================================================

@dataclass
class ScenarioDefinition:
    """Definition of a scenario to evaluate."""
    scenario_id: str
    scenario_type: ScenarioType
    name: str
    description: str

    # The decision/action being evaluated
    decision: Dict[str, Any]

    # Parameters that differ from baseline
    parameter_changes: Dict[str, Any] = field(default_factory=dict)

    # Time horizon
    horizon_days: int = 30

    # Monte Carlo settings
    num_simulations: int = 100
    confidence_level: float = 0.80

    # Context
    tenant_id: Optional[int] = None
    trigger_condition: Optional[str] = None
    created_by: str = "agent"


@dataclass
class ScenarioResult:
    """Result of evaluating a scenario."""
    scenario: ScenarioDefinition
    scorecard: BalancedScorecard

    # Execution details
    evaluated_at: datetime = field(default_factory=datetime.utcnow)
    evaluation_time_ms: float = 0.0
    simulations_run: int = 0

    # Probabilistic outcomes
    outcome_distribution: Dict[str, List[float]] = field(default_factory=dict)

    # Risk metrics
    probability_of_success: float = 0.0  # P(meeting targets)
    value_at_risk: float = 0.0           # VaR at 95%
    expected_shortfall: float = 0.0      # CVaR

    # Explanation
    explanation: str = ""
    key_drivers: List[str] = field(default_factory=list)


@dataclass
class ScenarioComparison:
    """Comparison of multiple scenarios."""
    scenarios: List[ScenarioResult]
    baseline_index: int = 0

    # Ranking by perspective
    ranking_financial: List[int] = field(default_factory=list)
    ranking_customer: List[int] = field(default_factory=list)
    ranking_operational: List[int] = field(default_factory=list)
    ranking_strategic: List[int] = field(default_factory=list)
    ranking_overall: List[int] = field(default_factory=list)

    # Recommendation
    recommended_index: int = 0
    recommendation_confidence: float = 0.0
    recommendation_reason: str = ""

    # Trade-off analysis
    trade_offs: List[Dict[str, Any]] = field(default_factory=list)


# =============================================================================
# Main Service
# =============================================================================

class ScenarioEvaluationService:
    """
    Evaluates alternative scenarios using balanced scorecard metrics.

    This is a critical component that enables agents to:
    1. Generate what-if scenarios from different decisions
    2. Run Monte Carlo simulation for probabilistic outcomes
    3. Compare scenarios across multiple perspectives
    4. Make data-driven recommendations with confidence intervals
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.default_simulations = 100
        self.default_horizon_days = 30

    # =========================================================================
    # Scenario Creation
    # =========================================================================

    async def create_scenarios_for_condition(
        self,
        condition_type: str,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
    ) -> List[ScenarioDefinition]:
        """
        Create alternative scenarios based on a condition.

        This is called when a condition (like ATP shortfall) requires
        evaluating different response strategies.

        Args:
            condition_type: Type of condition (e.g., "atp_shortfall")
            entity_id: Entity with the condition
            tenant_id: Customer ID
            context: Additional context from the condition

        Returns:
            List of scenario definitions to evaluate
        """
        scenarios = []

        if condition_type == "atp_shortfall":
            scenarios = await self._create_atp_scenarios(
                entity_id, tenant_id, context
            )
        elif condition_type == "inventory_below_safety":
            scenarios = await self._create_rebalance_scenarios(
                entity_id, tenant_id, context
            )
        elif condition_type == "capacity_overload":
            scenarios = await self._create_capacity_scenarios(
                entity_id, tenant_id, context
            )
        elif condition_type == "multi_site_shortfall":
            scenarios = await self._create_network_scenarios(
                entity_id, tenant_id, context
            )

        logger.info(
            f"Created {len(scenarios)} scenarios for {condition_type}"
        )

        return scenarios

    async def _create_atp_scenarios(
        self,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
    ) -> List[ScenarioDefinition]:
        """Create scenarios for ATP allocation decisions."""
        scenarios = []

        product_id = context.get("product_id", entity_id)
        current_shortage = context.get("shortage_quantity", 0)

        # Scenario 1: Baseline - no action
        scenarios.append(ScenarioDefinition(
            scenario_id=f"atp_baseline_{entity_id}",
            scenario_type=ScenarioType.ATP_ALLOCATION,
            name="No Action (Baseline)",
            description="Continue with current allocation, accept shortfall",
            decision={"action": "none"},
            parameter_changes={},
            tenant_id=tenant_id,
            trigger_condition="atp_shortfall",
        ))

        # Scenario 2: Reallocate from lower priority
        scenarios.append(ScenarioDefinition(
            scenario_id=f"atp_reallocate_{entity_id}",
            scenario_type=ScenarioType.ATP_ALLOCATION,
            name="Reallocate from Lower Priority",
            description="Consume ATP from lower priority tiers",
            decision={
                "action": "reallocate",
                "source_priorities": [5, 4, 3],
                "quantity": current_shortage,
            },
            parameter_changes={"allow_priority_consumption": True},
            tenant_id=tenant_id,
            trigger_condition="atp_shortfall",
        ))

        # Scenario 3: Request transfer from other sites
        scenarios.append(ScenarioDefinition(
            scenario_id=f"atp_transfer_{entity_id}",
            scenario_type=ScenarioType.ATP_ALLOCATION,
            name="Request Inter-Site Transfer",
            description="Request supply transfer from sites with excess",
            decision={
                "action": "request_transfer",
                "quantity": current_shortage,
            },
            parameter_changes={
                "enable_transfers": True,
                "transfer_lead_time_days": 3,
            },
            tenant_id=tenant_id,
            trigger_condition="atp_shortfall",
        ))

        # Scenario 4: Expedite purchase order
        scenarios.append(ScenarioDefinition(
            scenario_id=f"atp_expedite_{entity_id}",
            scenario_type=ScenarioType.ATP_ALLOCATION,
            name="Expedite Purchase Order",
            description="Create expedited PO with premium shipping",
            decision={
                "action": "expedite_po",
                "quantity": current_shortage,
                "expedite_premium": 1.5,
            },
            parameter_changes={
                "lead_time_reduction_days": 5,
                "cost_multiplier": 1.5,
            },
            tenant_id=tenant_id,
            trigger_condition="atp_shortfall",
        ))

        return scenarios

    async def _create_rebalance_scenarios(
        self,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
    ) -> List[ScenarioDefinition]:
        """Create scenarios for inventory rebalancing."""
        scenarios = []

        # Scenario 1: Baseline
        scenarios.append(ScenarioDefinition(
            scenario_id=f"rebal_baseline_{entity_id}",
            scenario_type=ScenarioType.INVENTORY_REBALANCE,
            name="No Rebalancing (Baseline)",
            description="Accept current inventory distribution",
            decision={"action": "none"},
            tenant_id=tenant_id,
            trigger_condition="inventory_below_safety",
        ))

        # Scenario 2: Single source rebalance
        scenarios.append(ScenarioDefinition(
            scenario_id=f"rebal_single_{entity_id}",
            scenario_type=ScenarioType.INVENTORY_REBALANCE,
            name="Single Source Transfer",
            description="Transfer from single nearest site with excess",
            decision={"action": "transfer", "sources": 1},
            parameter_changes={"prioritize_proximity": True},
            tenant_id=tenant_id,
            trigger_condition="inventory_below_safety",
        ))

        # Scenario 3: Multi-source rebalance
        scenarios.append(ScenarioDefinition(
            scenario_id=f"rebal_multi_{entity_id}",
            scenario_type=ScenarioType.INVENTORY_REBALANCE,
            name="Multi-Source Transfer",
            description="Combine inventory from multiple sites",
            decision={"action": "transfer", "sources": "multiple"},
            parameter_changes={"allow_partial_transfers": True},
            tenant_id=tenant_id,
            trigger_condition="inventory_below_safety",
        ))

        return scenarios

    async def _create_capacity_scenarios(
        self,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
    ) -> List[ScenarioDefinition]:
        """Create scenarios for capacity allocation."""
        scenarios = []

        # Baseline
        scenarios.append(ScenarioDefinition(
            scenario_id=f"cap_baseline_{entity_id}",
            scenario_type=ScenarioType.CAPACITY_ALLOCATION,
            name="Current Allocation (Baseline)",
            description="Continue with current production schedule",
            decision={"action": "none"},
            tenant_id=tenant_id,
            trigger_condition="capacity_overload",
        ))

        # Reschedule to other periods
        scenarios.append(ScenarioDefinition(
            scenario_id=f"cap_reschedule_{entity_id}",
            scenario_type=ScenarioType.CAPACITY_ALLOCATION,
            name="Reschedule Production",
            description="Move production to periods with available capacity",
            decision={"action": "reschedule"},
            tenant_id=tenant_id,
            trigger_condition="capacity_overload",
        ))

        # Add overtime
        scenarios.append(ScenarioDefinition(
            scenario_id=f"cap_overtime_{entity_id}",
            scenario_type=ScenarioType.CAPACITY_ALLOCATION,
            name="Add Overtime Capacity",
            description="Increase capacity through overtime",
            decision={"action": "overtime", "increase_pct": 0.15},
            parameter_changes={"cost_multiplier": 1.5},
            tenant_id=tenant_id,
            trigger_condition="capacity_overload",
        ))

        return scenarios

    async def _create_network_scenarios(
        self,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
    ) -> List[ScenarioDefinition]:
        """Create network-wide scenarios for multi-site conditions."""
        scenarios = []

        # Baseline
        scenarios.append(ScenarioDefinition(
            scenario_id=f"net_baseline_{entity_id}",
            scenario_type=ScenarioType.NETWORK_FLOW,
            name="Current Flow (Baseline)",
            description="Continue with current network allocation",
            decision={"action": "none"},
            tenant_id=tenant_id,
            trigger_condition="multi_site_shortfall",
        ))

        # Optimize network flow
        scenarios.append(ScenarioDefinition(
            scenario_id=f"net_optimize_{entity_id}",
            scenario_type=ScenarioType.NETWORK_FLOW,
            name="Optimize Network Flow",
            description="Re-optimize allocation across all sites",
            decision={"action": "optimize_flow"},
            num_simulations=200,  # More simulations for network-wide
            tenant_id=tenant_id,
            trigger_condition="multi_site_shortfall",
        ))

        # Prioritize key customers
        scenarios.append(ScenarioDefinition(
            scenario_id=f"net_prioritize_{entity_id}",
            scenario_type=ScenarioType.NETWORK_FLOW,
            name="Prioritize Key Customers",
            description="Allocate to highest priority customers first",
            decision={"action": "prioritize", "priority_rule": "customer_tier"},
            tenant_id=tenant_id,
            trigger_condition="multi_site_shortfall",
        ))

        return scenarios

    # =========================================================================
    # Scenario Evaluation
    # =========================================================================

    async def evaluate_scenario(
        self,
        scenario: ScenarioDefinition,
        current_state: Dict[str, Any],
    ) -> ScenarioResult:
        """
        Evaluate a single scenario using Monte Carlo simulation.

        Args:
            scenario: The scenario to evaluate
            current_state: Current system state

        Returns:
            ScenarioResult with balanced scorecard
        """
        start_time = datetime.utcnow()

        # Run Monte Carlo simulation
        simulation_results = await self._run_monte_carlo(
            scenario=scenario,
            current_state=current_state,
            num_simulations=scenario.num_simulations,
        )

        # Calculate balanced scorecard from simulation results
        scorecard = await self._calculate_scorecard(
            simulation_results=simulation_results,
            scenario=scenario,
        )

        # Calculate risk metrics
        probability_of_success = self._calculate_success_probability(
            simulation_results, scenario
        )
        var = self._calculate_value_at_risk(simulation_results, 0.95)
        cvar = self._calculate_expected_shortfall(simulation_results, 0.95)

        # Generate explanation
        explanation, key_drivers = self._generate_explanation(
            scenario, scorecard, simulation_results
        )

        evaluation_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        return ScenarioResult(
            scenario=scenario,
            scorecard=scorecard,
            evaluated_at=datetime.utcnow(),
            evaluation_time_ms=evaluation_time,
            simulations_run=scenario.num_simulations,
            outcome_distribution=simulation_results,
            probability_of_success=probability_of_success,
            value_at_risk=var,
            expected_shortfall=cvar,
            explanation=explanation,
            key_drivers=key_drivers,
        )

    async def _run_monte_carlo(
        self,
        scenario: ScenarioDefinition,
        current_state: Dict[str, Any],
        num_simulations: int,
    ) -> Dict[str, List[float]]:
        """
        Run Monte Carlo simulation for a scenario.

        Simulates inventory dynamics with stochastic demand and lead times,
        applying the scenario's decision as a parameter modification.
        Uses current_state from DB to ground the simulation in real data.
        """
        import numpy as np

        results = {
            "total_cost": [],
            "service_level": [],
            "inventory_turns": [],
            "otif_rate": [],
            "days_of_supply": [],
            "fill_rate": [],
        }

        # Extract baseline parameters from current state
        base_cost = current_state.get("total_cost", 100000)
        base_service = current_state.get("service_level", 0.92)
        base_inventory = current_state.get("avg_inventory", 1000)
        base_demand = current_state.get("avg_daily_demand", 100)
        base_lead_time = current_state.get("avg_lead_time_days", 14)

        # Scenario-specific parameter modifications
        decision = scenario.decision
        action = decision.get("action", "none")
        params = decision.get("parameter_changes", {})

        # Apply action effects to simulation parameters
        cost_multiplier = 1.0
        service_boost = 0.0
        lead_time_reduction = 0
        demand_shift = 0.0

        if action == "none":
            pass  # baseline
        elif action in ["reallocate", "transfer"]:
            cost_multiplier = 1.02  # slight logistics cost
            service_boost = 0.03
        elif action == "expedite_po":
            cost_multiplier = params.get("expedite_premium", 1.3)
            lead_time_reduction = params.get("lead_time_reduction_days", 3)
            service_boost = 0.05
        elif action == "optimize_flow":
            cost_multiplier = 0.95  # efficiency gain
            service_boost = 0.04
            lead_time_reduction = 1
        elif action == "increase_safety_stock":
            cost_multiplier = 1.08  # higher holding cost
            service_boost = 0.06

        # Effective parameters for simulation
        eff_lead_time = max(1, base_lead_time - lead_time_reduction)
        holding_cost_rate = max(0.5, base_cost / max(1, base_inventory) / 52)
        backlog_cost_rate = holding_cost_rate * 2.0

        num_weeks = scenario.horizon_days // 7 if scenario.horizon_days else 12

        for sim_idx in range(num_simulations):
            rng = np.random.RandomState(sim_idx + 1)

            inventory = base_inventory
            backlog = 0.0
            total_cost_sim = 0.0
            weeks_met_demand = 0
            total_demand = 0.0
            total_fulfilled = 0.0
            weekly_inventories = []

            # Shipment pipeline
            lt_weeks = max(1, int(eff_lead_time / 7))
            pipeline = [0.0] * (num_weeks + lt_weeks + 1)

            for week in range(num_weeks):
                # Receive shipments
                if week < len(pipeline):
                    inventory += pipeline[week]

                # Stochastic demand
                demand = max(0, rng.normal(base_demand * 7, base_demand * 7 * 0.2))
                demand += demand_shift
                total_demand += demand

                # Fulfill
                available = inventory
                fulfilled = min(available, demand + backlog)
                total_fulfilled += min(fulfilled, demand)
                unfulfilled = (demand + backlog) - fulfilled
                inventory = max(0, inventory - fulfilled)
                backlog = max(0, unfulfilled)

                if demand <= fulfilled:
                    weeks_met_demand += 1

                # Order (base-stock)
                target = base_demand * 7 * (lt_weeks + 2)
                pip_total = sum(pipeline[week + 1:week + lt_weeks + 1])
                order_qty = max(0, target - inventory - pip_total + backlog)

                actual_lt = max(1, int(rng.normal(lt_weeks, max(1, lt_weeks * 0.15))))
                arrival = week + actual_lt
                if arrival < len(pipeline):
                    pipeline[arrival] += order_qty

                # Costs
                total_cost_sim += max(0, inventory) * holding_cost_rate
                total_cost_sim += backlog * backlog_cost_rate
                weekly_inventories.append(inventory)

            # Apply cost multiplier from action
            total_cost_sim *= cost_multiplier

            # Compute metrics
            service = (weeks_met_demand / num_weeks) if num_weeks > 0 else 0.0
            service = min(1.0, service + service_boost * rng.uniform(0.5, 1.0))
            fill_rate = total_fulfilled / total_demand if total_demand > 0 else 1.0
            avg_inv = np.mean(weekly_inventories) if weekly_inventories else base_inventory
            inv_turns = (total_demand / avg_inv) if avg_inv > 0 else 0.0
            dos = (avg_inv / (base_demand * 7)) if base_demand > 0 else 21
            otif = min(1.0, fill_rate * service)

            results["total_cost"].append(float(total_cost_sim))
            results["service_level"].append(float(max(0, min(1, service))))
            results["inventory_turns"].append(float(max(0.5, inv_turns)))
            results["otif_rate"].append(float(max(0, min(1, otif))))
            results["days_of_supply"].append(float(max(1, dos)))
            results["fill_rate"].append(float(max(0, min(1, fill_rate))))

        return results

    async def _calculate_scorecard(
        self,
        simulation_results: Dict[str, List[float]],
        scenario: ScenarioDefinition,
    ) -> BalancedScorecard:
        """Calculate balanced scorecard from simulation results."""
        scorecard = BalancedScorecard()

        # Helper to create metric from distribution
        def create_metric(
            values: List[float],
            name: str,
            perspective: ScorecardPerspective,
            unit: str,
            direction: str = "higher_is_better",
            weight: float = 1.0,
        ) -> ScoreMetric:
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            return ScoreMetric(
                name=name,
                perspective=perspective,
                value=sum(values) / n,
                unit=unit,
                weight=weight,
                p10=sorted_vals[int(n * 0.1)],
                p50=sorted_vals[int(n * 0.5)],
                p90=sorted_vals[int(n * 0.9)],
                direction=direction,
            )

        # Financial metrics
        if "total_cost" in simulation_results:
            scorecard.total_cost = create_metric(
                simulation_results["total_cost"],
                "Total Cost", ScorecardPerspective.FINANCIAL,
                "$", "lower_is_better", 2.0
            )

        # Customer metrics
        if "service_level" in simulation_results:
            scorecard.service_level = create_metric(
                simulation_results["service_level"],
                "Service Level", ScorecardPerspective.CUSTOMER,
                "%", "higher_is_better", 2.0
            )

        if "otif_rate" in simulation_results:
            scorecard.otif_rate = create_metric(
                simulation_results["otif_rate"],
                "OTIF Rate", ScorecardPerspective.CUSTOMER,
                "%", "higher_is_better", 1.5
            )

        if "fill_rate" in simulation_results:
            scorecard.fill_rate = create_metric(
                simulation_results["fill_rate"],
                "Fill Rate", ScorecardPerspective.CUSTOMER,
                "%", "higher_is_better", 1.0
            )

        # Operational metrics
        if "inventory_turns" in simulation_results:
            scorecard.inventory_turns = create_metric(
                simulation_results["inventory_turns"],
                "Inventory Turns", ScorecardPerspective.OPERATIONAL,
                "turns/year", "higher_is_better", 1.0
            )

        if "days_of_supply" in simulation_results:
            scorecard.days_of_supply = create_metric(
                simulation_results["days_of_supply"],
                "Days of Supply", ScorecardPerspective.OPERATIONAL,
                "days", "lower_is_better", 1.0
            )

        # Calculate overall score
        scorecard.overall_score = self._calculate_overall_score(scorecard)

        return scorecard

    def _calculate_overall_score(
        self,
        scorecard: BalancedScorecard,
    ) -> float:
        """Calculate weighted overall score from all metrics.

        Normalization strategy:
        - Ratio metrics (0-1 range like service_level, fill_rate): multiply by 100
        - Turns metrics (typically 1-30): scale proportionally (10 turns = 50 score)
        - Cost metrics (lower is better): use percentile rank within P5-P95 range
        - Days metrics (lower is better): 7 days=90, 30 days=50, 60+ days=10
        """
        total_score = 0.0
        total_weight = 0.0

        for metric in scorecard.get_all_metrics():
            if metric.value is None:
                continue

            if metric.direction == "higher_is_better":
                if metric.value <= 1.0:
                    # Ratio metric (service level, fill rate, OTIF)
                    normalized = metric.value * 100
                elif metric.value <= 50:
                    # Turns-type metric: scale so 10=50, 20=80, 30=100
                    normalized = min(100, metric.value * 4)
                else:
                    # Already on a 0-100ish scale
                    normalized = min(100, metric.value)
            else:
                # Lower is better
                if hasattr(metric, 'p95') and metric.p95 and hasattr(metric, 'p5') and metric.p5:
                    # Use actual distribution range for normalization
                    range_val = metric.p95 - metric.p5
                    if range_val > 0:
                        # 100 at p5 (best), 0 at p95 (worst)
                        normalized = max(0, min(100, 100 * (1 - (metric.value - metric.p5) / range_val)))
                    else:
                        normalized = 50.0
                elif metric.value <= 60:
                    # Days-type metric: 7d=90, 14d=75, 21d=60, 30d=50, 60d=10
                    normalized = max(0, min(100, 100 - (metric.value * 1.5)))
                else:
                    # Cost-type: use log scale, higher cost = lower score
                    import math
                    normalized = max(0, min(100, 100 - math.log10(max(1, metric.value)) * 15))

            total_score += normalized * metric.weight
            total_weight += metric.weight

        return total_score / total_weight if total_weight > 0 else 0.0

    def _calculate_success_probability(
        self,
        results: Dict[str, List[float]],
        scenario: ScenarioDefinition,
    ) -> float:
        """Calculate probability of meeting targets."""
        # Count simulations meeting key targets
        service_target = 0.95
        service_levels = results.get("service_level", [])

        if not service_levels:
            return 0.5

        successes = sum(1 for s in service_levels if s >= service_target)
        return successes / len(service_levels)

    def _calculate_value_at_risk(
        self,
        results: Dict[str, List[float]],
        confidence: float,
    ) -> float:
        """Calculate Value at Risk (VaR) for cost."""
        costs = results.get("total_cost", [])
        if not costs:
            return 0.0

        sorted_costs = sorted(costs)
        idx = int(len(sorted_costs) * confidence)
        return sorted_costs[min(idx, len(sorted_costs) - 1)]

    def _calculate_expected_shortfall(
        self,
        results: Dict[str, List[float]],
        confidence: float,
    ) -> float:
        """Calculate Expected Shortfall (CVaR) - average of worst cases."""
        costs = results.get("total_cost", [])
        if not costs:
            return 0.0

        sorted_costs = sorted(costs, reverse=True)
        n_worst = int(len(sorted_costs) * (1 - confidence))
        n_worst = max(1, n_worst)

        return sum(sorted_costs[:n_worst]) / n_worst

    def _generate_explanation(
        self,
        scenario: ScenarioDefinition,
        scorecard: BalancedScorecard,
        results: Dict[str, List[float]],
    ) -> Tuple[str, List[str]]:
        """Generate human-readable explanation of scenario outcome."""
        key_drivers = []
        explanation_parts = []

        action = scenario.decision.get("action", "none")
        explanation_parts.append(f"Scenario '{scenario.name}' evaluates the impact of {action}.")

        # Service level impact
        if scorecard.service_level:
            sl = scorecard.service_level
            explanation_parts.append(
                f"Expected service level: {sl.value*100:.1f}% "
                f"(P10: {sl.p10*100:.1f}%, P90: {sl.p90*100:.1f}%)"
            )
            if sl.value >= 0.95:
                key_drivers.append("High service level achievable")
            elif sl.value < 0.90:
                key_drivers.append("Service level risk")

        # Cost impact
        if scorecard.total_cost:
            tc = scorecard.total_cost
            explanation_parts.append(
                f"Expected cost: ${tc.value:,.0f} "
                f"(P10: ${tc.p10:,.0f}, P90: ${tc.p90:,.0f})"
            )
            if tc.value > tc.p50 * 1.2:
                key_drivers.append("High cost variability")

        # Key trade-offs
        if scenario.decision.get("expedite_premium"):
            key_drivers.append("Premium cost for faster delivery")

        return " ".join(explanation_parts), key_drivers

    # =========================================================================
    # Scenario Comparison
    # =========================================================================

    async def compare_scenarios(
        self,
        results: List[ScenarioResult],
        baseline_index: int = 0,
    ) -> ScenarioComparison:
        """
        Compare multiple scenario results and recommend best option.

        Args:
            results: List of evaluated scenarios
            baseline_index: Index of baseline scenario

        Returns:
            ScenarioComparison with rankings and recommendation
        """
        comparison = ScenarioComparison(
            scenarios=results,
            baseline_index=baseline_index,
        )

        if not results:
            return comparison

        n = len(results)

        # Rank by each perspective
        comparison.ranking_financial = self._rank_by_perspective(
            results, ScorecardPerspective.FINANCIAL
        )
        comparison.ranking_customer = self._rank_by_perspective(
            results, ScorecardPerspective.CUSTOMER
        )
        comparison.ranking_operational = self._rank_by_perspective(
            results, ScorecardPerspective.OPERATIONAL
        )

        # Overall ranking by scorecard score
        overall_scores = [r.scorecard.overall_score for r in results]
        comparison.ranking_overall = sorted(
            range(n), key=lambda i: overall_scores[i], reverse=True
        )

        # Determine recommendation
        best_idx = comparison.ranking_overall[0]
        comparison.recommended_index = best_idx

        # Calculate confidence in recommendation
        if n >= 2:
            best_score = overall_scores[best_idx]
            second_best = overall_scores[comparison.ranking_overall[1]]
            margin = (best_score - second_best) / best_score if best_score > 0 else 0
            comparison.recommendation_confidence = min(0.95, 0.5 + margin)
        else:
            comparison.recommendation_confidence = 0.5

        # Generate recommendation reason
        best_result = results[best_idx]
        comparison.recommendation_reason = (
            f"'{best_result.scenario.name}' ranks best overall with "
            f"score {best_result.scorecard.overall_score:.1f}, "
            f"probability of success {best_result.probability_of_success:.1%}"
        )

        # Identify trade-offs
        comparison.trade_offs = self._identify_trade_offs(results)

        return comparison

    def _rank_by_perspective(
        self,
        results: List[ScenarioResult],
        perspective: ScorecardPerspective,
    ) -> List[int]:
        """Rank scenarios by a specific perspective."""
        scores = []

        for i, result in enumerate(results):
            perspective_score = 0.0
            count = 0

            for metric in result.scorecard.get_all_metrics():
                if metric.perspective == perspective:
                    # Normalize to 0-100
                    if metric.direction == "higher_is_better":
                        norm = metric.value * 100 if metric.value <= 1 else metric.value
                    else:
                        norm = max(0, 100 - (metric.value / 1000))

                    perspective_score += norm * metric.weight
                    count += metric.weight

            scores.append((i, perspective_score / count if count > 0 else 0))

        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores]

    def _identify_trade_offs(
        self,
        results: List[ScenarioResult],
    ) -> List[Dict[str, Any]]:
        """Identify key trade-offs between scenarios."""
        trade_offs = []

        if len(results) < 2:
            return trade_offs

        # Compare each pair
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                s1, s2 = results[i], results[j]

                # Check for cost vs service trade-off
                if s1.scorecard.total_cost and s2.scorecard.total_cost:
                    cost1 = s1.scorecard.total_cost.value
                    cost2 = s2.scorecard.total_cost.value
                    svc1 = s1.scorecard.service_level.value if s1.scorecard.service_level else 0
                    svc2 = s2.scorecard.service_level.value if s2.scorecard.service_level else 0

                    # One is better on cost, other better on service
                    if (cost1 < cost2 and svc1 < svc2) or (cost1 > cost2 and svc1 > svc2):
                        trade_offs.append({
                            "type": "cost_vs_service",
                            "scenarios": [i, j],
                            "description": (
                                f"'{s1.scenario.name}' has {'lower' if cost1 < cost2 else 'higher'} cost "
                                f"but {'lower' if svc1 < svc2 else 'higher'} service level vs "
                                f"'{s2.scenario.name}'"
                            ),
                        })

        return trade_offs

    # =========================================================================
    # Integration with Agent Workflow
    # =========================================================================

    async def evaluate_and_recommend(
        self,
        condition_type: str,
        entity_id: str,
        tenant_id: int,
        context: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> Tuple[ScenarioResult, ScenarioComparison]:
        """
        Full workflow: create scenarios, evaluate, compare, and recommend.

        This is the main entry point for agent-driven scenario evaluation.

        Returns:
            (recommended_result, full_comparison)
        """
        # Create scenarios
        scenarios = await self.create_scenarios_for_condition(
            condition_type=condition_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            context=context,
        )

        if not scenarios:
            logger.warning(f"No scenarios created for {condition_type}")
            return None, None

        # Evaluate each scenario
        results = []
        for scenario in scenarios:
            result = await self.evaluate_scenario(scenario, current_state)
            results.append(result)

        # Compare and get recommendation
        comparison = await self.compare_scenarios(results, baseline_index=0)

        recommended = results[comparison.recommended_index]

        logger.info(
            f"Evaluated {len(results)} scenarios for {condition_type}, "
            f"recommending '{recommended.scenario.name}' with "
            f"confidence {comparison.recommendation_confidence:.1%}"
        )

        return recommended, comparison
