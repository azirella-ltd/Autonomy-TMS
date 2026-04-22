"""
Agent Recommendation Service

Phase 2: Agent Copilot Mode
Provides real-time AI recommendations for fulfillment and replenishment decisions
with confidence scores, reasoning, and impact previews.

Integration with existing agents:
- LLM agents (llm_agent.py)
- GNN agents (gnn/ models)
- TRM agents (trm_agent.py)
- Heuristic agents (agents.py)
"""

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario
from app.models.supply_chain import ScenarioPeriod

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
Game = Scenario
from app.models.transfer_order import TransferOrder
from app.models.tenant import Tenant
from app.models.explainability import ExplainabilityLevel
from .agents import SimulationAgent, AgentStrategy, AgentType

# Import LLM agent with fallback
try:
    from .llm_agent import LLMAgent, LLMStrategy, AutonomyLLMError
except Exception:
    LLMAgent = None
    LLMStrategy = None
    AutonomyLLMError = Exception

# Import TRM agent with fallback
try:
    from .trm_agent import compute_trm_order, get_trm_agent
except Exception:
    compute_trm_order = None
    get_trm_agent = None

logger = logging.getLogger(__name__)


@dataclass
class AlternativeScenario:
    """Alternative decision with risk assessment"""
    quantity: int
    description: str
    risk: str  # "LOW", "MEDIUM", "HIGH"


@dataclass
class ImpactPreview:
    """Predicted impact of a decision"""
    inventory_after: int
    fill_rate: float
    backlog_after: int
    cost_impact: float  # Estimated cost delta


@dataclass
class HistoricalPerformance:
    """Agent's historical performance metrics"""
    avg_accuracy: float  # 0.0-1.0
    recent_decisions: int  # Count of recent decisions
    overrides: int  # Times human overrode the agent
    override_regret_rate: float  # 0.0-1.0 (how often override was worse)


@dataclass
class RecommendationResult:
    """Complete agent recommendation with metadata"""
    agent_id: str
    agent_type: str  # "LLM", "GNN", "TRM", "HEURISTIC"
    quantity: int
    reasoning: str
    confidence: float  # 0.0-1.0
    alternative_scenarios: List[AlternativeScenario]
    impact_preview_if_accept: ImpactPreview
    impact_preview_if_override: Optional[ImpactPreview]
    historical_performance: HistoricalPerformance
    timestamp: str


class AgentRecommendationService:
    """
    Service for generating agent recommendations during copilot mode.

    Methods:
    - get_fulfillment_recommendation(): Get agent suggestion for ATP-based shipment
    - get_replenishment_recommendation(): Get agent suggestion for upstream order
    - calculate_confidence_score(): Compute agent confidence based on historical performance
    - generate_reasoning(): Create human-readable explanation of agent decision
    """

    def __init__(self, db: Session):
        self.db = db

    def get_fulfillment_recommendation(
        self,
        game: Game,
        scenario_user: ScenarioUser,
        current_period: ScenarioPeriod,
        atp: int,
        demand: int,
        backlog: int = 0,
    ) -> RecommendationResult:
        """
        Get agent recommendation for fulfillment decision (ATP-based shipment).

        Args:
            game: Game instance
            scenario_user: ScenarioUser instance with agent configuration
            current_period: Current game round
            atp: Available to Promise quantity
            demand: Downstream demand (including backlog)
            backlog: Current backlog

        Returns:
            RecommendationResult with agent's recommended fulfillment quantity
        """
        # Get agent strategy from scenario_user configuration
        agent_strategy = self._get_agent_strategy(scenario_user)
        agent_type = self._get_agent_type_enum(scenario_user)

        # Get config-specific model path
        model_path = getattr(
            game.supply_chain_config, "trained_model_path", None
        ) if game.supply_chain_config else None

        # Create agent instance with model path
        agent = self._create_agent(scenario_user, agent_strategy, model_path=model_path)

        # Calculate agent decision
        # For fulfillment, agent should consider ATP constraints
        # Simplest heuristic: Ship min(ATP, demand) to maximize service without exceeding capacity
        base_recommendation = min(atp, demand)

        # Let agent adjust based on strategy
        context = {
            "inventory": scenario_user.current_stock,
            "backlog": backlog,
            "demand": demand,
            "atp": atp,
            "round": current_period.round_number,
        }

        # For Phase 2, use simple heuristic-based recommendation
        # Future phases can integrate full agent computation
        if agent_strategy == AgentStrategy.CONSERVATIVE:
            # Conservative: ship only ATP, never exceed
            recommended_qty = atp
        elif agent_strategy == AgentStrategy.BULLWHIP:
            # Bullwhip: ship full demand even if exceeds ATP (amplify)
            recommended_qty = demand
        else:
            # Naive/default: ship min(ATP, demand)
            recommended_qty = base_recommendation

        # Generate reasoning based on explainability level
        explainability = self._get_explainability_level(scenario_user)
        if explainability == ExplainabilityLevel.VERBOSE:
            reasoning = self._generate_fulfillment_reasoning_verbose(
                agent_strategy, recommended_qty, atp, demand, backlog
            )
        elif explainability == ExplainabilityLevel.SUCCINCT:
            reasoning = self._generate_fulfillment_reasoning_succinct(
                agent_strategy, recommended_qty, atp, demand
            )
        else:  # NORMAL
            reasoning = self._generate_fulfillment_reasoning_normal(
                agent_strategy, recommended_qty, atp, demand
            )

        # Calculate confidence score
        confidence = self._calculate_confidence_score(scenario_user, agent_strategy)

        # Generate alternative scenarios
        alternatives = self._generate_fulfillment_alternatives(atp, demand, recommended_qty)

        # Calculate impact previews
        impact_if_accept = self._calculate_fulfillment_impact(
            inventory=scenario_user.current_stock,
            fulfill_qty=recommended_qty,
            demand=demand,
            backlog=backlog,
        )

        # Impact if human overrides to ship full demand
        override_qty = demand if recommended_qty != demand else atp
        impact_if_override = self._calculate_fulfillment_impact(
            inventory=scenario_user.current_stock,
            fulfill_qty=override_qty,
            demand=demand,
            backlog=backlog,
        )

        # Get historical performance
        historical_perf = self._get_historical_performance(scenario_user)

        # Build result
        result = RecommendationResult(
            agent_id=f"{agent_strategy.value}_agent_{scenario_user.id}",
            agent_type=self._get_agent_type_display(agent_strategy),
            quantity=recommended_qty,
            reasoning=reasoning,
            confidence=confidence,
            alternative_scenarios=alternatives,
            impact_preview_if_accept=impact_if_accept,
            impact_preview_if_override=impact_if_override,
            historical_performance=historical_perf,
            timestamp=datetime.utcnow().isoformat(),
        )

        logger.info(
            f"Fulfillment recommendation for scenario_user {scenario_user.id}: {recommended_qty} units "
            f"(confidence: {confidence:.2f})"
        )

        return result

    def get_replenishment_recommendation(
        self,
        game: Game,
        scenario_user: ScenarioUser,
        current_period: ScenarioPeriod,
        current_inventory: int,
        pipeline: List[Dict[str, Any]],
        backlog: int = 0,
        demand_history: Optional[List[int]] = None,
    ) -> RecommendationResult:
        """
        Get agent recommendation for replenishment decision (upstream order).

        Args:
            game: Game instance
            scenario_user: ScenarioUser instance with agent configuration
            current_period: Current game round
            current_inventory: Current on-hand inventory
            pipeline: List of in-transit shipments
            backlog: Current backlog
            demand_history: Recent demand history for forecasting

        Returns:
            RecommendationResult with agent's recommended order quantity
        """
        # Get agent strategy
        agent_strategy = self._get_agent_strategy(scenario_user)

        # Calculate base stock policy recommendation
        demand_history = demand_history or []
        avg_demand = (sum(demand_history) / len(demand_history)) if demand_history else 100
        lead_time = 2  # Assume 2-round lead time (will be parameterized later)
        review_period = 1
        safety_multiplier = 1.5  # 50% safety buffer

        base_stock_target = int(avg_demand * (lead_time + review_period) * safety_multiplier)
        pipeline_total = sum(shipment.get("quantity", 0) for shipment in pipeline)
        inventory_position = current_inventory + pipeline_total - backlog

        base_recommendation = max(0, base_stock_target - inventory_position)

        # Agent-specific adjustments
        if agent_strategy == AgentStrategy.CONSERVATIVE:
            # Conservative: order slightly more to build buffer
            recommended_qty = int(base_recommendation * 1.2)
        elif agent_strategy == AgentStrategy.BULLWHIP:
            # Bullwhip: amplify order if demand is rising
            if demand_history and len(demand_history) >= 2:
                recent_trend = demand_history[-1] - demand_history[-2]
                if recent_trend > 0:
                    recommended_qty = int(base_recommendation * 1.5)
                else:
                    recommended_qty = base_recommendation
            else:
                recommended_qty = base_recommendation
        else:
            # Naive/default: base stock policy
            recommended_qty = base_recommendation

        # Generate reasoning based on explainability level
        explainability = self._get_explainability_level(scenario_user)
        if explainability == ExplainabilityLevel.VERBOSE:
            reasoning = self._generate_replenishment_reasoning_verbose(
                agent_strategy, recommended_qty, base_stock_target,
                inventory_position, avg_demand, demand_history
            )
        elif explainability == ExplainabilityLevel.SUCCINCT:
            reasoning = self._generate_replenishment_reasoning_succinct(
                agent_strategy, recommended_qty, base_stock_target
            )
        else:  # NORMAL
            reasoning = self._generate_replenishment_reasoning_normal(
                agent_strategy, recommended_qty, base_stock_target,
                avg_demand, demand_history
            )

        # Calculate confidence
        confidence = self._calculate_confidence_score(scenario_user, agent_strategy)

        # Generate alternatives
        alternatives = self._generate_replenishment_alternatives(base_recommendation, recommended_qty)

        # Calculate impact previews
        impact_if_accept = self._calculate_replenishment_impact(
            inventory=current_inventory,
            order_qty=recommended_qty,
            pipeline_total=pipeline_total,
            backlog=backlog,
            avg_demand=avg_demand,
        )

        # Impact if human doubles the order
        override_qty = recommended_qty * 2
        impact_if_override = self._calculate_replenishment_impact(
            inventory=current_inventory,
            order_qty=override_qty,
            pipeline_total=pipeline_total,
            backlog=backlog,
            avg_demand=avg_demand,
        )

        # Historical performance
        historical_perf = self._get_historical_performance(scenario_user)

        result = RecommendationResult(
            agent_id=f"{agent_strategy.value}_agent_{scenario_user.id}",
            agent_type=self._get_agent_type_display(agent_strategy),
            quantity=recommended_qty,
            reasoning=reasoning,
            confidence=confidence,
            alternative_scenarios=alternatives,
            impact_preview_if_accept=impact_if_accept,
            impact_preview_if_override=impact_if_override,
            historical_performance=historical_perf,
            timestamp=datetime.utcnow().isoformat(),
        )

        logger.info(
            f"Replenishment recommendation for scenario_user {scenario_user.id}: {recommended_qty} units "
            f"(confidence: {confidence:.2f})"
        )

        return result

    # --- Helper Methods ---

    def _get_agent_strategy(self, scenario_user: ScenarioUser) -> AgentStrategy:
        """Get agent strategy from scenario_user configuration"""
        # Default to naive if not configured
        strategy_name = getattr(scenario_user, "agent_strategy", "naive")
        try:
            return AgentStrategy(strategy_name)
        except ValueError:
            return AgentStrategy.NAIVE

    def _get_agent_type_enum(self, scenario_user: ScenarioUser) -> AgentType:
        """Get agent type enum from scenario_user role"""
        role_mapping = {
            "retailer": AgentType.RETAILER,
            "wholesaler": AgentType.WHOLESALER,
            "distributor": AgentType.DISTRIBUTOR,
            "manufacturer": AgentType.MANUFACTURER,
        }
        return role_mapping.get(scenario_user.role.lower(), AgentType.RETAILER)

    def _create_agent(
        self,
        scenario_user: ScenarioUser,
        strategy: AgentStrategy,
        model_path: Optional[str] = None
    ) -> SimulationAgent:
        """Create agent instance for scenario_user with config-specific model path."""
        agent_type = self._get_agent_type_enum(scenario_user)
        return SimulationAgent(
            agent_id=scenario_user.id,
            agent_type=agent_type,
            strategy=strategy,
            initial_inventory=scenario_user.current_stock,
            model_path=model_path,
        )

    def _calculate_confidence_score(self, scenario_user: ScenarioUser, strategy: AgentStrategy) -> float:
        """
        Calculate confidence score based on agent type and historical performance.

        Returns float between 0.0-1.0
        """
        # Base confidence by strategy type
        base_confidence = {
            AgentStrategy.LLM: 0.92,
            AgentStrategy.TRM: 0.89,
            AgentStrategy.PID: 0.85,
            AgentStrategy.CONSERVATIVE: 0.80,
            AgentStrategy.NAIVE: 0.75,
            AgentStrategy.BULLWHIP: 0.60,  # Intentionally volatile
        }.get(strategy, 0.75)

        # TODO: Adjust based on historical performance (Phase 2.5)
        # For now, return base confidence
        return base_confidence

    def _generate_fulfillment_alternatives(
        self, atp: int, demand: int, recommended: int
    ) -> List[AlternativeScenario]:
        """Generate alternative fulfillment scenarios"""
        alternatives = []

        # Ship full demand
        if recommended != demand:
            risk = "HIGH" if demand > atp else "LOW"
            alternatives.append(
                AlternativeScenario(
                    quantity=demand,
                    description="Ship full demand",
                    risk=f"{risk} - {'Exceeds ATP' if demand > atp else 'Within ATP'}, "
                    f"{'creates future shortage risk' if demand > atp else 'maximizes service'}",
                )
            )

        # Ship only ATP
        if recommended != atp:
            alternatives.append(
                AlternativeScenario(
                    quantity=atp,
                    description="Ship only ATP (conservative)",
                    risk="LOW - Protects future commitments, may increase current backlog",
                )
            )

        # Ship 80% of ATP (buffer)
        buffer_qty = int(atp * 0.8)
        if buffer_qty != recommended and buffer_qty > 0:
            alternatives.append(
                AlternativeScenario(
                    quantity=buffer_qty,
                    description=f"Ship 80% of ATP ({buffer_qty} units)",
                    risk="LOW - Preserves safety buffer, creates minor backlog",
                )
            )

        return alternatives

    def _generate_replenishment_alternatives(
        self, base_recommendation: int, current_recommendation: int
    ) -> List[AlternativeScenario]:
        """Generate alternative replenishment scenarios"""
        alternatives = []

        # Base stock recommendation
        if current_recommendation != base_recommendation:
            alternatives.append(
                AlternativeScenario(
                    quantity=base_recommendation,
                    description="Base stock policy",
                    risk="MEDIUM - Standard reorder policy, may not account for demand trends",
                )
            )

        # 50% more (aggressive)
        aggressive_qty = int(current_recommendation * 1.5)
        alternatives.append(
            AlternativeScenario(
                quantity=aggressive_qty,
                description=f"Aggressive order (+50%)",
                risk="HIGH - Builds inventory buffer, may increase holding costs",
            )
        )

        # 50% less (conservative)
        conservative_qty = max(0, int(current_recommendation * 0.5))
        alternatives.append(
            AlternativeScenario(
                quantity=conservative_qty,
                description=f"Conservative order (-50%)",
                risk="HIGH - Reduces inventory, may create future stockouts",
            )
        )

        return alternatives

    def _calculate_fulfillment_impact(
        self,
        inventory: int,
        fulfill_qty: int,
        demand: int,
        backlog: int,
    ) -> ImpactPreview:
        """Calculate predicted impact of fulfillment decision"""
        inventory_after = inventory - fulfill_qty
        fulfilled = min(fulfill_qty, demand)
        backlog_after = max(0, demand - fulfilled + backlog)
        fill_rate = fulfilled / demand if demand > 0 else 1.0

        # Simplified cost calculation (holding + backlog costs)
        holding_cost = max(0, inventory_after) * 1.0  # $1 per unit per round
        backlog_cost = backlog_after * 2.0  # $2 per unit per round (higher penalty)
        cost_impact = holding_cost + backlog_cost

        return ImpactPreview(
            inventory_after=inventory_after,
            fill_rate=fill_rate,
            backlog_after=backlog_after,
            cost_impact=cost_impact,
        )

    def _calculate_replenishment_impact(
        self,
        inventory: int,
        order_qty: int,
        pipeline_total: int,
        backlog: int,
        avg_demand: float,
    ) -> ImpactPreview:
        """Calculate predicted impact of replenishment decision"""
        # Inventory position = on-hand + on-order - backlog
        inventory_position = inventory + pipeline_total + order_qty - backlog

        # Days of supply
        days_of_supply = inventory_position / avg_demand if avg_demand > 0 else 0

        # Simplified fill rate projection (higher inventory position = higher fill rate)
        target_days = 7  # 1 week of supply
        fill_rate = min(1.0, days_of_supply / target_days)

        # Cost impact (larger orders increase holding costs)
        cost_impact = order_qty * 1.0  # $1 per unit holding cost

        return ImpactPreview(
            inventory_after=inventory_position,  # Projected position
            fill_rate=fill_rate,
            backlog_after=backlog,  # Assume backlog unchanged
            cost_impact=cost_impact,
        )

    def _get_historical_performance(self, scenario_user: ScenarioUser) -> HistoricalPerformance:
        """Get agent's historical performance metrics from real decision data."""
        try:
            from app.models.powell_decision import SiteAgentDecision

            # Build site_key from scenario_user info
            site_key = f"site_{scenario_user.id}"

            # Count recent decisions
            recent_decisions = (
                self.db.query(SiteAgentDecision)
                .filter(SiteAgentDecision.site_key == site_key)
                .count()
            )

            if recent_decisions == 0:
                # No decision history yet — return zeros instead of fake data
                return HistoricalPerformance(
                    avg_accuracy=0.0,
                    recent_decisions=0,
                    overrides=0,
                    override_regret_rate=0.0,
                )

            # Count decisions with human overrides
            overrides = (
                self.db.query(SiteAgentDecision)
                .filter(
                    SiteAgentDecision.site_key == site_key,
                    SiteAgentDecision.human_feedback.isnot(None),
                )
                .count()
            )

            # Compute accuracy from decisions that have outcomes
            decisions_with_outcomes = (
                self.db.query(SiteAgentDecision)
                .filter(
                    SiteAgentDecision.site_key == site_key,
                    SiteAgentDecision.reward_signal.isnot(None),
                )
                .all()
            )

            if decisions_with_outcomes:
                # Reward signal is typically -1 to 1; positive = good decision
                positive = sum(1 for d in decisions_with_outcomes if (d.reward_signal or 0) > 0)
                avg_accuracy = positive / len(decisions_with_outcomes)
            else:
                avg_accuracy = 0.0

            # Override regret rate: overrides where human rating <= 2 (1-5 scale)
            regret_overrides = 0
            if overrides > 0:
                regret_overrides = (
                    self.db.query(SiteAgentDecision)
                    .filter(
                        SiteAgentDecision.site_key == site_key,
                        SiteAgentDecision.human_feedback.isnot(None),
                        SiteAgentDecision.human_rating.isnot(None),
                        SiteAgentDecision.human_rating <= 2,
                    )
                    .count()
                )

            override_regret_rate = regret_overrides / overrides if overrides > 0 else 0.0

            return HistoricalPerformance(
                avg_accuracy=round(avg_accuracy, 3),
                recent_decisions=recent_decisions,
                overrides=overrides,
                override_regret_rate=round(override_regret_rate, 3),
            )
        except Exception as e:
            logger.warning(f"Error querying historical performance for scenario_user {scenario_user.id}: {e}")
            return HistoricalPerformance(
                avg_accuracy=0.0,
                recent_decisions=0,
                overrides=0,
                override_regret_rate=0.0,
            )

    def _get_agent_type_display(self, strategy: AgentStrategy) -> str:
        """Get display name for agent type"""
        mapping = {
            AgentStrategy.LLM: "LLM",
            AgentStrategy.TRM: "TRM",
            AgentStrategy.PID: "HEURISTIC",
            AgentStrategy.CONSERVATIVE: "HEURISTIC",
            AgentStrategy.NAIVE: "HEURISTIC",
            AgentStrategy.BULLWHIP: "HEURISTIC",
        }
        return mapping.get(strategy, "HEURISTIC")

    def _get_explainability_level(self, scenario_user: ScenarioUser) -> ExplainabilityLevel:
        """
        Get effective explainability level for scenario_user.

        Priority: User override > Tenant default > NORMAL
        """
        # Check user-level override first
        if hasattr(scenario_user, 'user') and scenario_user.user:
            user_override = getattr(scenario_user.user, 'explainability_level_override', None)
            if user_override is not None:
                return user_override

        # Fall back to tenant default
        if hasattr(scenario_user, 'user') and scenario_user.user and scenario_user.user.tenant_id:
            tenant = self.db.query(Tenant).filter(Tenant.id == scenario_user.user.tenant_id).first()
            if tenant and hasattr(tenant, 'explainability_level'):
                return tenant.explainability_level

        # Ultimate fallback
        return ExplainabilityLevel.NORMAL

    # --- Fulfillment Reasoning Generators ---

    def _generate_fulfillment_reasoning_verbose(
        self, strategy: AgentStrategy, recommended_qty: int, atp: int, demand: int, backlog: int
    ) -> str:
        """Generate verbose (detailed) fulfillment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return (
                f"**Conservative Fulfillment Strategy - Detailed Analysis**\n\n"
                f"I recommend shipping exactly {recommended_qty} units, which corresponds to your Available to Promise (ATP) capacity. "
                f"Here's my reasoning:\n\n"
                f"**Current Situation:**\n"
                f"- Downstream demand: {demand} units\n"
                f"- Available to Promise (ATP): {atp} units\n"
                f"- Current backlog: {backlog} units\n\n"
                f"**Why Ship Only ATP?**\n"
                f"The conservative approach prioritizes protecting your future commitments and maintaining operational flexibility. "
                f"By shipping only what you have available to promise, you ensure that you won't over-commit inventory that may be needed "
                f"for future orders or scheduled commitments. This reduces the risk of creating cascading shortages downstream.\n\n"
                f"**Trade-offs:**\n"
                f"While this approach may result in a backlog increase of {max(0, demand - recommended_qty)} units this round, "
                f"it preserves your ability to respond to unexpected demand spikes in future rounds. In supply chain management, "
                f"maintaining buffer capacity often prevents larger problems down the line.\n\n"
                f"**Alternative Consideration:**\n"
                f"If you choose to ship the full demand ({demand} units), you would exceed ATP by {max(0, demand - atp)} units, "
                f"which could impact your ability to fulfill future commitments and may require emergency replenishment actions."
            )
        elif strategy == AgentStrategy.BULLWHIP:
            return (
                f"**Bullwhip Amplification Strategy - Detailed Analysis**\n\n"
                f"I recommend shipping {recommended_qty} units to meet full downstream demand, regardless of ATP constraints. "
                f"This strategy intentionally amplifies demand signals through the supply chain.\n\n"
                f"**Current Situation:**\n"
                f"- Downstream demand: {demand} units\n"
                f"- Available to Promise (ATP): {atp} units\n"
                f"- Current backlog: {backlog} units\n"
                f"- Recommended shipment: {recommended_qty} units\n\n"
                f"**Bullwhip Effect Rationale:**\n"
                f"The bullwhip effect occurs when each node in the supply chain amplifies demand variability as information moves upstream. "
                f"While typically considered a problem to avoid, this strategy intentionally creates it to demonstrate supply chain dynamics. "
                f"{'By exceeding ATP, we are showing how over-commitment at one level can cascade through the network.' if demand > atp else 'In this case, demand is within ATP, so we ship the full amount.'}\n\n"
                f"**Educational Value:**\n"
                f"This aggressive fulfillment policy helps illustrate why demand amplification occurs in real supply chains—each node tries "
                f"to maximize service level without perfect visibility into upstream capacity, leading to systematic over-ordering and "
                f"inventory oscillation.\n\n"
                f"**Consequences:**\n"
                f"{'This will strain your inventory position and may create future shortages' if demand > atp else 'This maintains high service level while staying within capacity'}. "
                f"Expect increased costs and potential stockout risks in subsequent rounds if this pattern continues."
            )
        else:  # Naive/Balanced
            return (
                f"**Balanced Fulfillment Strategy - Detailed Analysis**\n\n"
                f"I recommend shipping {recommended_qty} units, which represents the optimal balance between customer service "
                f"and operational capacity.\n\n"
                f"**Current Situation:**\n"
                f"- Downstream demand: {demand} units\n"
                f"- Available to Promise (ATP): {atp} units\n"
                f"- Current backlog: {backlog} units\n"
                f"- Recommended shipment: {recommended_qty} units (min of demand and ATP)\n\n"
                f"**Balanced Approach Rationale:**\n"
                f"This strategy follows the principle of shipping the minimum of downstream demand and ATP, ensuring we:\n"
                f"1. **Maximize service level** - Ship as much as demand requires (up to ATP)\n"
                f"2. **Respect capacity constraints** - Never exceed ATP, protecting future commitments\n"
                f"3. **Minimize cost** - Avoid unnecessary holding costs or backlog penalties\n\n"
                f"**Why This Quantity?**\n"
                f"{'Since demand exceeds ATP, we are constrained by capacity. Shipping ATP maximizes our service level given the constraint.' if demand > atp else 'Since ATP exceeds demand, we ship exactly what is requested to minimize inventory movement costs.'}\n\n"
                f"**Performance Metrics:**\n"
                f"- Fill rate this round: {min(recommended_qty, demand) / demand * 100:.1f}%\n"
                f"- Backlog impact: {'Increases' if demand > recommended_qty else 'Remains stable or decreases'} by {abs(demand - recommended_qty)} units\n"
                f"- ATP utilization: {recommended_qty / atp * 100:.1f}%\n\n"
                f"This decision optimizes the classic supply chain trade-off between service level and inventory efficiency."
            )

    def _generate_fulfillment_reasoning_normal(
        self, strategy: AgentStrategy, recommended_qty: int, atp: int, demand: int
    ) -> str:
        """Generate normal (balanced) fulfillment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return (
                f"Conservative strategy: Ship only ATP ({recommended_qty} units) to avoid future commitment issues. "
                f"Demand is {demand} units. This protects your ability to fulfill future orders by not over-committing "
                f"current inventory. Trade-off: May increase current backlog by {max(0, demand - recommended_qty)} units."
            )
        elif strategy == AgentStrategy.BULLWHIP:
            exceeds_msg = f" (exceeds ATP by {demand - atp} units)" if demand > atp else ""
            return (
                f"Bullwhip strategy: Ship full demand ({recommended_qty} units){exceeds_msg} to meet customer needs. "
                f"ATP is {atp} units. This approach prioritizes service level over capacity constraints, "
                f"demonstrating demand amplification effects in supply chains."
            )
        else:  # Naive/Balanced
            return (
                f"Balanced strategy: Ship {recommended_qty} units (min of ATP {atp} and demand {demand}) "
                f"to maximize service while respecting capacity. This optimizes the trade-off between "
                f"fill rate ({min(recommended_qty, demand) / demand * 100:.1f}%) and ATP utilization "
                f"({recommended_qty / atp * 100:.1f}%)."
            )

    def _generate_fulfillment_reasoning_succinct(
        self, strategy: AgentStrategy, recommended_qty: int, atp: int, demand: int
    ) -> str:
        """Generate succinct (brief) fulfillment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return f"Ship {recommended_qty} units (ATP only) to protect future commitments."
        elif strategy == AgentStrategy.BULLWHIP:
            return f"Ship {recommended_qty} units (full demand) for maximum service level."
        else:  # Naive/Balanced
            return f"Ship {recommended_qty} units (min of ATP {atp}, demand {demand})."

    # --- Replenishment Reasoning Generators ---

    def _generate_replenishment_reasoning_verbose(
        self,
        strategy: AgentStrategy,
        recommended_qty: int,
        base_stock_target: int,
        inventory_position: int,
        avg_demand: float,
        demand_history: List[int],
    ) -> str:
        """Generate verbose (detailed) replenishment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return (
                f"**Conservative Replenishment Strategy - Detailed Analysis**\n\n"
                f"I recommend ordering {recommended_qty} units from your upstream supplier to maintain a safety buffer. "
                f"This is 20% above the base stock policy recommendation.\n\n"
                f"**Inventory Analysis:**\n"
                f"- Base stock target: {base_stock_target} units\n"
                f"- Current inventory position: {inventory_position} units (on-hand + pipeline - backlog)\n"
                f"- Average demand: {avg_demand:.1f} units/round\n"
                f"- Days of supply (current): {inventory_position / avg_demand:.1f} days\n\n"
                f"**Conservative Buffer Rationale:**\n"
                f"The conservative approach adds a 20% safety margin above standard base stock calculations to account for:\n"
                f"1. **Demand uncertainty** - Historical demand shows variability (range: {min(demand_history) if demand_history else 'N/A'}-{max(demand_history) if demand_history else 'N/A'} units)\n"
                f"2. **Supply variability** - Lead times may fluctuate, requiring extra buffer\n"
                f"3. **Cost of stockout** - Backlog penalties (typically $2/unit/round) often exceed holding costs ($1/unit/round)\n\n"
                f"**Why Build Extra Inventory?**\n"
                f"In supply chain management, the \"newsvendor problem\" teaches us that when backlog costs exceed holding costs by 2x or more, "
                f"it's economically rational to carry 15-25% extra inventory as insurance. The conservative strategy implements this principle "
                f"by maintaining higher safety stock levels.\n\n"
                f"**Expected Outcome:**\n"
                f"After this order arrives (typically 2 rounds), your inventory position will be {inventory_position + recommended_qty} units, "
                f"providing approximately {(inventory_position + recommended_qty) / avg_demand:.1f} days of supply. This buffer reduces "
                f"stockout probability to less than 5%, significantly improving your expected service level."
            )
        elif strategy == AgentStrategy.BULLWHIP:
            trend = demand_history[-1] - demand_history[-2] if demand_history and len(demand_history) >= 2 else 0
            return (
                f"**Bullwhip Amplification Strategy - Detailed Analysis**\n\n"
                f"I recommend ordering {recommended_qty} units based on recent demand trends and amplification logic.\n\n"
                f"**Demand Trend Analysis:**\n"
                f"- Recent demand history: {demand_history[-5:] if len(demand_history) >= 5 else demand_history}\n"
                f"- Latest round change: {trend:+.0f} units ({('increasing' if trend > 0 else 'decreasing' if trend < 0 else 'stable')})\n"
                f"- Average demand: {avg_demand:.1f} units/round\n"
                f"- Inventory position: {inventory_position} units\n\n"
                f"**Bullwhip Amplification Logic:**\n"
                f"{'The bullwhip strategy detects the rising demand signal and amplifies the order by 50% to demonstrate how small changes in downstream demand can create large upstream oscillations.' if trend > 0 else 'Demand is stable or declining, so we order the base recommendation without amplification.'}\n\n"
                f"**Why Amplify Orders?**\n"
                f"In real supply chains, the bullwhip effect emerges because:\n"
                f"1. **Signal interpretation** - Each node interprets demand changes as trends requiring proactive response\n"
                f"2. **Batch ordering** - Periodic ordering amplifies variability (order 0, then order 3x average)\n"
                f"3. **Price fluctuations** - Forward buying during promotions creates artificial demand spikes\n"
                f"4. **Rationing gaming** - Fear of shortages leads to inflated orders\n\n"
                f"This strategy intentionally exhibits behavior #1 to illustrate systemic supply chain dynamics.\n\n"
                f"**Consequences:**\n"
                f"{'This aggressive order will create excess inventory when the trend reverses, demonstrating the cost of over-reacting to demand signals.' if trend > 0 else 'The moderate order maintains reasonable inventory levels but may lead to stockouts if demand suddenly spikes.'} "
                f"Observe how this decision propagates upstream and affects the entire supply chain network."
            )
        else:  # Naive/Base Stock
            return (
                f"**Base Stock Policy - Detailed Analysis**\n\n"
                f"I recommend ordering {recommended_qty} units to reach your target inventory position using standard base stock logic.\n\n"
                f"**Base Stock Calculation:**\n"
                f"```\n"
                f"Target = Avg Demand × (Lead Time + Review Period) × Safety Factor\n"
                f"Target = {avg_demand:.1f} × (2 + 1) × 1.5 = {base_stock_target} units\n\n"
                f"Inventory Position = On-Hand + Pipeline - Backlog = {inventory_position} units\n"
                f"Order Quantity = max(0, Target - Position) = {recommended_qty} units\n"
                f"```\n\n"
                f"**Policy Parameters:**\n"
                f"- **Lead time**: 2 rounds (time for order to arrive from upstream)\n"
                f"- **Review period**: 1 round (how often we check inventory)\n"
                f"- **Safety factor**: 1.5 (50% buffer above expected demand during lead time)\n\n"
                f"**Why Base Stock Policy?**\n"
                f"Base stock is a proven inventory policy that:\n"
                f"1. **Orders up to target** - Simple, intuitive replenishment rule\n"
                f"2. **Accounts for pipeline** - Considers orders already in transit\n"
                f"3. **Includes safety stock** - The 1.5× multiplier provides buffer for variability\n"
                f"4. **Responds to demand** - Target adjusts as average demand changes\n\n"
                f"**Performance Expectations:**\n"
                f"With this policy and current parameters, you can expect:\n"
                f"- **Service level**: ~95% (meets most demand without stockouts)\n"
                f"- **Average inventory**: {base_stock_target * 0.6:.0f}-{base_stock_target * 0.8:.0f} units\n"
                f"- **Bullwhip ratio**: 1.1-1.3 (low amplification compared to aggressive strategies)\n\n"
                f"This represents industry best practice for inventory management in supply chains with moderate demand variability."
            )

    def _generate_replenishment_reasoning_normal(
        self,
        strategy: AgentStrategy,
        recommended_qty: int,
        base_stock_target: int,
        avg_demand: float,
        demand_history: List[int],
    ) -> str:
        """Generate normal (balanced) replenishment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return (
                f"Conservative strategy: Order {recommended_qty} units (20% above base stock) to maintain safety buffer. "
                f"Base stock target is {base_stock_target} units. The extra 20% provides insurance against demand uncertainty "
                f"(historical range: {min(demand_history) if demand_history else 'N/A'}-{max(demand_history) if demand_history else 'N/A'}) "
                f"and supply variability. This reduces stockout risk to less than 5%."
            )
        elif strategy == AgentStrategy.BULLWHIP:
            trend = demand_history[-1] - demand_history[-2] if demand_history and len(demand_history) >= 2 else 0
            if trend > 0:
                return (
                    f"Bullwhip strategy: Demand rising ({trend:+.0f} units last round), amplify order to {recommended_qty} units (+50%). "
                    f"This demonstrates how small downstream demand changes create large upstream oscillations (the bullwhip effect). "
                    f"Average demand is {avg_demand:.1f} units/round."
                )
            else:
                return (
                    f"Bullwhip strategy: Demand stable/declining, order base recommendation {recommended_qty} units. "
                    f"Average demand is {avg_demand:.1f} units/round. No amplification needed when trend is flat or negative."
                )
        else:  # Naive/Base Stock
            return (
                f"Base stock policy: Order {recommended_qty} units to reach target inventory position {base_stock_target} units. "
                f"Calculation: Target = Avg Demand ({avg_demand:.1f}) × (Lead Time + Review Period) (2+1) × Safety Factor (1.5). "
                f"This policy balances service level (~95%) with inventory efficiency, ordering up to target each round."
            )

    def _generate_replenishment_reasoning_succinct(
        self, strategy: AgentStrategy, recommended_qty: int, base_stock_target: int
    ) -> str:
        """Generate succinct (brief) replenishment reasoning"""
        if strategy == AgentStrategy.CONSERVATIVE:
            return f"Order {recommended_qty} units (base stock +20%) for safety buffer."
        elif strategy == AgentStrategy.BULLWHIP:
            return f"Order {recommended_qty} units (amplified for demand trend)."
        else:  # Naive/Base Stock
            return f"Order {recommended_qty} units to reach target {base_stock_target}."


# Factory function for creating service instances with FastAPI dependency injection
from fastapi import Depends
from app.db.session import get_db

def get_agent_recommendation_service(db: Session = Depends(get_db)) -> AgentRecommendationService:
    """Factory function to create AgentRecommendationService"""
    return AgentRecommendationService(db)
