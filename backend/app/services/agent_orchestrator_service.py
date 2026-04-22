"""
Agent Orchestrator Service - Powell Framework Integration

This service orchestrates the execution of AI agents following the Powell
Sequential Decision Analytics framework. It manages:

1. TRIGGER DETECTION: What events should activate agents
2. AGENT SELECTION: Which agent(s) should handle each situation
3. MODE DETERMINATION: AUTOMATE vs INFORM based on confidence/impact
4. SCOPE MANAGEMENT: Ensuring agents operate within their trained span
5. COMMUNICATION: Sharing context between hierarchical agents
6. DATA FLOW INTEGRATION: CDC-triggered workflows with condition monitoring
7. SCENARIO EVALUATION: Agent-driven what-if analysis for impact assessment

Powell Agent Hierarchy:
- S&OP GraphSAGE (CFA): Weekly/Monthly policy parameter optimization
- Execution tGNN (CFA/VFA): Daily priority allocation generation
- Narrow TRMs (VFA): Real-time execution decisions

Human Participation (AIIO):
- AUTOMATE: Agent executes, no notification
- INFORM: Agent executes, user notified (can acknowledge/override)
- User can always INSPECT (understand why) and OVERRIDE (with reason)

Data Flow Integration:
- Import Scheduler → CDC → Condition Monitor → Agent Orchestrator → Scenario Eval
- Each CDC change triggers condition checks
- Persistent conditions trigger agent execution
- Agents can request scenario evaluation for complex decisions
- Scenario results feed back to planning decisions
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
import logging
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.agent_action import AgentAction, ActionMode, ActionCategory, ExecutionResult
from app.models.powell import PowellBeliefState, PowellPolicyParameters, EntityType
from app.models.planning_hierarchy import SiteHierarchyLevel, ProductHierarchyLevel, TimeBucketType
from app.services.reasoning_capture_service import (
    ReasoningCaptureService, AgentType, ReasoningOutput
)
from app.services.calibration_feedback_service import CalibrationFeedbackService
from app.services.data_import_scheduler_service import (
    DataImportSchedulerService, CDCResult, ImportTier
)
from app.services.condition_monitor_service import (
    ConditionMonitorService, ConditionState, ConditionType, ConditionSeverity
)
from app.services.scenario_evaluation_service import (
    ScenarioEvaluationService, ScenarioResult, ScenarioComparison
)

logger = logging.getLogger(__name__)


# =============================================================================
# Trigger Types
# =============================================================================

class TriggerType(str, Enum):
    """Types of events that can trigger agent execution."""
    # Time-based triggers
    PLANNING_CYCLE = "planning_cycle"        # Scheduled planning run
    PERIODIC_CHECK = "periodic_check"        # Regular monitoring

    # Event-based triggers
    NEW_ORDER = "new_order"                  # Customer order received
    ORDER_CHANGE = "order_change"            # Order modified/cancelled
    SHIPMENT_UPDATE = "shipment_update"      # ASN received, delay detected
    FORECAST_UPDATE = "forecast_update"      # Demand forecast changed
    INVENTORY_UPDATE = "inventory_update"    # Stock level changed
    SUPPLY_EXCEPTION = "supply_exception"    # Supplier issue detected

    # Threshold-based triggers
    STOCKOUT_RISK = "stockout_risk"          # Inventory below safety stock
    HIGH_RISK_SCORE = "high_risk_score"      # Risk metric exceeded
    COVERAGE_DRIFT = "coverage_drift"        # Conformal coverage degraded

    # CDC-triggered events
    CDC_SIGNIFICANT_CHANGE = "cdc_significant_change"  # Significant data change
    DATA_IMPORT_COMPLETE = "data_import_complete"      # Import tier completed

    # Condition-based triggers (persistent conditions)
    CONDITION_ATP_SHORTFALL = "condition_atp_shortfall"
    CONDITION_INVENTORY_LOW = "condition_inventory_low"
    CONDITION_CAPACITY_OVERLOAD = "condition_capacity_overload"
    CONDITION_MULTI_SITE_SHORTFALL = "condition_multi_site_shortfall"
    CONDITION_ORDER_PAST_DUE = "condition_order_past_due"

    # Plan deviation triggers
    PLAN_DEVIATION = "plan_deviation"        # Deviation from previous plan
    SOOP_TRIGGER = "soop_trigger"            # S&OP cycle triggered by conditions


@dataclass
class TriggerContext:
    """Context information for an agent trigger."""
    trigger_type: TriggerType
    tenant_id: int
    entity_type: str              # product, site, order, etc.
    entity_id: str
    priority: int = 5             # 1=highest, 10=lowest
    payload: Dict[str, Any] = None

    def __post_init__(self):
        if self.payload is None:
            self.payload = {}


# =============================================================================
# Agent Scope Configuration
# =============================================================================

@dataclass
class AgentScope:
    """Defines the trained span of control for an agent."""
    agent_type: AgentType
    decision_types: List[str]           # What decisions can it make
    entity_scope: str                   # product, site, order, etc.
    time_horizon_days: int              # How far ahead it plans
    max_impact_threshold: float         # Max $ impact for AUTOMATE mode
    confidence_threshold: float         # Min confidence for AUTOMATE mode
    requires_human_above_impact: float  # Force INFORM above this impact


# Default agent scope configurations
AGENT_SCOPES = {
    AgentType.TRM_ATP: AgentScope(
        agent_type=AgentType.TRM_ATP,
        decision_types=["allocate_atp", "consume_priority"],
        entity_scope="order",
        time_horizon_days=1,
        max_impact_threshold=10000,     # $10K per order
        confidence_threshold=0.85,
        requires_human_above_impact=50000,
    ),
    AgentType.TRM_REBALANCE: AgentScope(
        agent_type=AgentType.TRM_REBALANCE,
        decision_types=["transfer_inventory", "rebalance"],
        entity_scope="site_pair",
        time_horizon_days=7,
        max_impact_threshold=25000,
        confidence_threshold=0.80,
        requires_human_above_impact=100000,
    ),
    AgentType.TRM_PO_CREATION: AgentScope(
        agent_type=AgentType.TRM_PO_CREATION,
        decision_types=["create_po", "modify_po_qty"],
        entity_scope="product_vendor",
        time_horizon_days=14,
        max_impact_threshold=50000,
        confidence_threshold=0.80,
        requires_human_above_impact=200000,
    ),
    AgentType.TRM_ORDER_TRACKING: AgentScope(
        agent_type=AgentType.TRM_ORDER_TRACKING,
        decision_types=["flag_exception", "recommend_action"],
        entity_scope="order",
        time_horizon_days=30,
        max_impact_threshold=5000,      # Low impact, mostly informational
        confidence_threshold=0.70,
        requires_human_above_impact=25000,
    ),
    AgentType.GNN_EXECUTION: AgentScope(
        agent_type=AgentType.GNN_EXECUTION,
        decision_types=["generate_allocations", "set_priorities"],
        entity_scope="network",
        time_horizon_days=7,
        max_impact_threshold=100000,
        confidence_threshold=0.75,
        requires_human_above_impact=500000,
    ),
    AgentType.GNN_SOOP: AgentScope(
        agent_type=AgentType.GNN_SOOP,
        decision_types=["set_policy_params", "update_safety_stocks"],
        entity_scope="network",
        time_horizon_days=30,
        max_impact_threshold=500000,
        confidence_threshold=0.70,
        requires_human_above_impact=1000000,
    ),
}


# =============================================================================
# Main Orchestrator Service
# =============================================================================

class AgentOrchestratorService:
    """
    Orchestrates AI agent execution across the Powell hierarchy.

    Responsibilities:
    1. Receive triggers from various sources
    2. Select appropriate agent(s) based on trigger type and scope
    3. Determine AUTOMATE vs INFORM mode
    4. Execute agents and record actions
    5. Handle human override requests
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.reasoning_service = ReasoningCaptureService(db)
        self.calibration_service = CalibrationFeedbackService(db)
        self._agent_handlers: Dict[AgentType, callable] = {}

    def register_agent_handler(
        self,
        agent_type: AgentType,
        handler: callable,
    ) -> None:
        """
        Register an agent handler function.

        Handler signature: async def handler(context: TriggerContext, scope: AgentScope) -> Dict
        """
        self._agent_handlers[agent_type] = handler
        logger.info(f"Registered handler for {agent_type.value}")

    # =========================================================================
    # Trigger Processing
    # =========================================================================

    async def process_trigger(
        self,
        trigger: TriggerContext,
    ) -> List[AgentAction]:
        """
        Process a trigger and execute appropriate agents.

        This is the main entry point for agent orchestration.

        Args:
            trigger: The trigger context with event details

        Returns:
            List of AgentAction records created
        """
        logger.info(f"Processing trigger: {trigger.trigger_type.value} for {trigger.entity_type}:{trigger.entity_id}")

        # 1. Select agents for this trigger
        selected_agents = self._select_agents_for_trigger(trigger)

        if not selected_agents:
            logger.info(f"No agents selected for trigger {trigger.trigger_type.value}")
            return []

        # 2. Execute each selected agent
        actions = []
        for agent_type in selected_agents:
            try:
                action = await self._execute_agent(agent_type, trigger)
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Agent {agent_type.value} failed: {e}")

        return actions

    def _select_agents_for_trigger(
        self,
        trigger: TriggerContext,
    ) -> List[AgentType]:
        """Select which agents should handle this trigger."""
        selected = []

        # Map triggers to agents
        trigger_agent_map = {
            # Event-based triggers
            TriggerType.NEW_ORDER: [AgentType.TRM_ATP],
            TriggerType.ORDER_CHANGE: [AgentType.TRM_ATP, AgentType.TRM_ORDER_TRACKING],
            TriggerType.SHIPMENT_UPDATE: [AgentType.TRM_ORDER_TRACKING],
            TriggerType.STOCKOUT_RISK: [AgentType.TRM_REBALANCE, AgentType.TRM_PO_CREATION],
            TriggerType.INVENTORY_UPDATE: [AgentType.TRM_REBALANCE],
            TriggerType.FORECAST_UPDATE: [AgentType.GNN_EXECUTION, AgentType.TRM_PO_CREATION],
            TriggerType.PLANNING_CYCLE: [AgentType.GNN_SOOP, AgentType.GNN_EXECUTION],
            TriggerType.HIGH_RISK_SCORE: [AgentType.TRM_ORDER_TRACKING],
            TriggerType.COVERAGE_DRIFT: [],  # Triggers recalibration, not agents

            # CDC-triggered events
            TriggerType.CDC_SIGNIFICANT_CHANGE: [AgentType.GNN_EXECUTION],
            TriggerType.DATA_IMPORT_COMPLETE: [AgentType.GNN_EXECUTION],

            # Condition-based triggers
            TriggerType.CONDITION_ATP_SHORTFALL: [AgentType.TRM_ATP, AgentType.TRM_REBALANCE],
            TriggerType.CONDITION_INVENTORY_LOW: [AgentType.TRM_REBALANCE, AgentType.TRM_PO_CREATION],
            TriggerType.CONDITION_CAPACITY_OVERLOAD: [AgentType.GNN_EXECUTION],
            TriggerType.CONDITION_MULTI_SITE_SHORTFALL: [AgentType.GNN_SOOP, AgentType.GNN_EXECUTION],
            TriggerType.CONDITION_ORDER_PAST_DUE: [AgentType.TRM_ORDER_TRACKING],

            # Plan deviation triggers
            TriggerType.PLAN_DEVIATION: [AgentType.GNN_EXECUTION],
            TriggerType.SOOP_TRIGGER: [AgentType.GNN_SOOP, AgentType.GNN_EXECUTION],
        }

        selected = trigger_agent_map.get(trigger.trigger_type, [])

        # Filter by registered handlers
        return [a for a in selected if a in self._agent_handlers]

    # =========================================================================
    # Agent Execution
    # =========================================================================

    async def _execute_agent(
        self,
        agent_type: AgentType,
        trigger: TriggerContext,
    ) -> Optional[AgentAction]:
        """Execute a single agent and record the action."""
        scope = AGENT_SCOPES.get(agent_type)
        if not scope:
            logger.warning(f"No scope defined for {agent_type.value}")
            return None

        handler = self._agent_handlers.get(agent_type)
        if not handler:
            logger.warning(f"No handler registered for {agent_type.value}")
            return None

        # Execute the agent
        start_time = datetime.utcnow()
        try:
            result = await handler(trigger, scope)
        except Exception as e:
            logger.error(f"Agent handler failed: {e}")
            return None

        execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        if not result or not result.get("decision"):
            return None

        # Determine mode (AUTOMATE vs INFORM)
        mode = self._determine_mode(result, scope)

        # Get or create belief state for conformal prediction
        belief_state = await self._get_belief_state(trigger, result)

        # Capture reasoning
        reasoning = await self.reasoning_service.capture_trm_reasoning(
            agent_type=agent_type,
            input_features=result.get("input_features", {}),
            output_decision=result.get("decision", {}),
            attention_weights=result.get("attention_weights"),
            recursive_refinements=result.get("refinements"),
            model_version=result.get("model_version", "1.0.0"),
        )

        if belief_state:
            reasoning = await self.reasoning_service.add_conformal_prediction(
                reasoning, belief_state
            )

        # Create the action record
        action = AgentAction(
            tenant_id=trigger.tenant_id,
            action_mode=mode,
            action_type=result["decision"].get("action_type", "unknown"),
            category=self._determine_category(agent_type),
            title=result["decision"].get("title", f"{agent_type.value} decision"),
            description=result["decision"].get("description"),
            explanation=reasoning.explanation,
            reasoning_chain={"chain": [step.__dict__ for step in reasoning.reasoning_chain]},
            alternatives_considered={"alternatives": [alt.__dict__ for alt in reasoning.alternatives_considered]},

            # Hierarchy context
            site_hierarchy_level=SiteHierarchyLevel.SITE,
            site_key=result.get("site_key", trigger.entity_id),
            product_hierarchy_level=ProductHierarchyLevel.PRODUCT,
            product_key=result.get("product_key", trigger.entity_id),
            time_bucket=TimeBucketType.DAY,
            time_key=datetime.utcnow().strftime("%Y-%m-%d"),

            # Metrics
            metric_name=result["decision"].get("metric_name"),
            metric_before=result["decision"].get("metric_before"),
            metric_after=result["decision"].get("metric_after"),
            estimated_impact=result["decision"].get("estimated_impact"),

            # Execution
            executed_at=datetime.utcnow(),
            execution_result=ExecutionResult.SUCCESS,
            execution_details={"execution_time_ms": execution_time_ms},

            # Agent info
            agent_id=agent_type.value,
            agent_version=result.get("model_version", "1.0.0"),

            # Conformal prediction
            predicted_outcome=belief_state.point_estimate if belief_state else None,
            prediction_interval_lower=belief_state.conformal_lower if belief_state else None,
            prediction_interval_upper=belief_state.conformal_upper if belief_state else None,
            confidence_level=belief_state.conformal_coverage if belief_state else None,
            nonconformity_score=belief_state.nonconformity_score if belief_state else None,
            belief_state_id=belief_state.id if belief_state else None,
        )

        self.db.add(action)
        await self.db.flush()

        logger.info(f"Created {mode.value} action {action.id} from {agent_type.value}")
        return action

    def _determine_mode(
        self,
        result: Dict[str, Any],
        scope: AgentScope,
    ) -> ActionMode:
        """
        Determine whether action should be AUTOMATE or INFORM.

        AUTOMATE when:
        - Confidence above threshold
        - Impact below threshold
        - Within trained scope

        INFORM when:
        - Lower confidence
        - Higher impact
        - Edge cases
        """
        confidence = result.get("confidence", 0.5)
        estimated_impact = result.get("decision", {}).get("estimated_impact", {}).get("total", 0)

        # Force INFORM for high-impact decisions
        if abs(estimated_impact) > scope.requires_human_above_impact:
            return ActionMode.INFORM

        # Force INFORM for low confidence
        if confidence < scope.confidence_threshold:
            return ActionMode.INFORM

        # Force INFORM for moderate impact with moderate confidence
        if abs(estimated_impact) > scope.max_impact_threshold and confidence < 0.90:
            return ActionMode.INFORM

        return ActionMode.AUTOMATE

    def _determine_category(self, agent_type: AgentType) -> ActionCategory:
        """Map agent type to action category."""
        category_map = {
            AgentType.TRM_ATP: ActionCategory.ALLOCATION,
            AgentType.TRM_REBALANCE: ActionCategory.INVENTORY,
            AgentType.TRM_PO_CREATION: ActionCategory.PROCUREMENT,
            AgentType.TRM_ORDER_TRACKING: ActionCategory.LOGISTICS,
            AgentType.GNN_EXECUTION: ActionCategory.ALLOCATION,
            AgentType.GNN_SOOP: ActionCategory.INVENTORY,
        }
        return category_map.get(agent_type, ActionCategory.OTHER)

    async def _get_belief_state(
        self,
        trigger: TriggerContext,
        result: Dict[str, Any],
    ) -> Optional[PowellBeliefState]:
        """Get or create belief state for conformal prediction."""
        entity_type_map = {
            "order": EntityType.SERVICE_LEVEL,
            "product": EntityType.DEMAND,
            "site": EntityType.INVENTORY,
            "site_pair": EntityType.INVENTORY,
        }

        entity_type = entity_type_map.get(trigger.entity_type)
        if not entity_type:
            return None

        # Get prediction interval from result if available
        prediction = result.get("prediction", {})
        point = prediction.get("point_estimate", result.get("decision", {}).get("metric_after"))
        lower = prediction.get("interval_lower")
        upper = prediction.get("interval_upper")

        if point is None:
            return None

        # Default interval if not provided
        if lower is None or upper is None:
            # Default to ±20% interval
            lower = point * 0.8
            upper = point * 1.2

        return await self.reasoning_service.get_or_create_belief_state(
            tenant_id=trigger.tenant_id,
            entity_type=entity_type,
            entity_id=trigger.entity_id,
            point_estimate=point,
            interval_lower=lower,
            interval_upper=upper,
            coverage=0.80,
        )

    # =========================================================================
    # Planning Cycle Integration
    # =========================================================================

    async def run_planning_cycle(
        self,
        tenant_id: int,
        cycle_type: str,  # "daily", "weekly", "monthly"
    ) -> List[AgentAction]:
        """
        Run a scheduled planning cycle.

        This triggers the appropriate agents based on the cycle type:
        - Daily: Execution tGNN → TRM agents
        - Weekly: S&OP GraphSAGE → Execution tGNN → TRM agents
        - Monthly: Full S&OP optimization
        """
        logger.info(f"Starting {cycle_type} planning cycle for tenant {tenant_id}")

        actions = []

        if cycle_type in ["weekly", "monthly"]:
            # Run S&OP GraphSAGE first
            trigger = TriggerContext(
                trigger_type=TriggerType.PLANNING_CYCLE,
                tenant_id=tenant_id,
                entity_type="network",
                entity_id=f"customer_{tenant_id}",
                priority=1,
                payload={"cycle_type": cycle_type},
            )
            soop_actions = await self.process_trigger(trigger)
            actions.extend(soop_actions)

        if cycle_type in ["daily", "weekly", "monthly"]:
            # Run Execution tGNN to generate allocations
            trigger = TriggerContext(
                trigger_type=TriggerType.PLANNING_CYCLE,
                tenant_id=tenant_id,
                entity_type="network",
                entity_id=f"customer_{tenant_id}",
                priority=2,
                payload={"cycle_type": cycle_type},
            )
            tgnn_actions = await self.process_trigger(trigger)
            actions.extend(tgnn_actions)

        return actions

    # =========================================================================
    # Event-Driven Triggers
    # =========================================================================

    async def on_new_order(
        self,
        tenant_id: int,
        order_id: str,
        order_data: Dict[str, Any],
    ) -> List[AgentAction]:
        """Handle new customer order event."""
        trigger = TriggerContext(
            trigger_type=TriggerType.NEW_ORDER,
            tenant_id=tenant_id,
            entity_type="order",
            entity_id=order_id,
            priority=2,
            payload=order_data,
        )
        return await self.process_trigger(trigger)

    async def on_inventory_update(
        self,
        tenant_id: int,
        site_id: str,
        product_id: str,
        new_level: float,
        safety_stock: float,
    ) -> List[AgentAction]:
        """Handle inventory level update."""
        # Check for stockout risk
        trigger_type = TriggerType.INVENTORY_UPDATE
        if new_level < safety_stock:
            trigger_type = TriggerType.STOCKOUT_RISK

        trigger = TriggerContext(
            trigger_type=trigger_type,
            tenant_id=tenant_id,
            entity_type="site",
            entity_id=f"{site_id}_{product_id}",
            priority=1 if trigger_type == TriggerType.STOCKOUT_RISK else 5,
            payload={
                "site_id": site_id,
                "product_id": product_id,
                "inventory_level": new_level,
                "safety_stock": safety_stock,
            },
        )
        return await self.process_trigger(trigger)

    async def on_forecast_update(
        self,
        tenant_id: int,
        product_id: str,
        old_forecast: Dict[str, float],
        new_forecast: Dict[str, float],
    ) -> List[AgentAction]:
        """Handle demand forecast update."""
        trigger = TriggerContext(
            trigger_type=TriggerType.FORECAST_UPDATE,
            tenant_id=tenant_id,
            entity_type="product",
            entity_id=product_id,
            priority=3,
            payload={
                "old_forecast": old_forecast,
                "new_forecast": new_forecast,
            },
        )
        return await self.process_trigger(trigger)

    # =========================================================================
    # CDC-Triggered Workflows
    # =========================================================================

    async def on_cdc_result(
        self,
        cdc_result: CDCResult,
        tenant_id: int,
    ) -> List[AgentAction]:
        """
        Handle CDC result from data import.

        This is called after each data import completes CDC analysis.
        It triggers the appropriate workflow based on changes detected.

        Flow:
        1. CDC detects changes
        2. Condition monitor checks for persistent conditions
        3. Agents are triggered based on conditions
        4. Scenario evaluation if complex decision needed
        """
        actions = []

        if cdc_result.significant_changes == 0:
            logger.info(f"No significant changes in CDC result, skipping")
            return actions

        # Initialize services
        import_service = DataImportSchedulerService(self.db)
        condition_service = ConditionMonitorService(self.db)

        # Step 1: Trigger workflows based on CDC
        workflow_result = await import_service.trigger_workflows_from_cdc(
            cdc_result, tenant_id
        )

        # Step 2: Check for persistent conditions
        conditions_to_check = workflow_result.get("condition_checks", [])
        if conditions_to_check:
            # Map condition strings to ConditionType enum
            condition_types = []
            for cond in conditions_to_check:
                try:
                    condition_types.append(ConditionType(cond))
                except ValueError:
                    logger.warning(f"Unknown condition type: {cond}")

            if condition_types:
                active_conditions = await condition_service.check_conditions(
                    tenant_id=tenant_id,
                    condition_types=condition_types,
                )

                # Step 3: Process active conditions
                if active_conditions:
                    condition_actions = await self._process_conditions(
                        conditions=active_conditions,
                        tenant_id=tenant_id,
                    )
                    actions.extend(condition_actions)

        # Step 4: Trigger specific agents from CDC
        agent_triggers = workflow_result.get("agent_triggers", [])
        for agent_name in agent_triggers:
            trigger = TriggerContext(
                trigger_type=TriggerType.CDC_SIGNIFICANT_CHANGE,
                tenant_id=tenant_id,
                entity_type="data_import",
                entity_id=f"{cdc_result.data_type.value}_{cdc_result.version_hash}",
                priority=3,
                payload={
                    "data_type": cdc_result.data_type.value,
                    "tier": cdc_result.tier.value,
                    "changes_count": cdc_result.changed_records,
                    "significant_count": cdc_result.significant_changes,
                },
            )
            trigger_actions = await self.process_trigger(trigger)
            actions.extend(trigger_actions)

        logger.info(f"CDC workflow generated {len(actions)} actions")
        return actions

    async def _process_conditions(
        self,
        conditions: List[ConditionState],
        tenant_id: int,
    ) -> List[AgentAction]:
        """
        Process active conditions and trigger appropriate responses.

        For each condition:
        1. Determine which agents should handle it
        2. Check if scenario evaluation is needed
        3. Create triggers for selected agents
        """
        actions = []
        condition_service = ConditionMonitorService(self.db)
        scenario_service = ScenarioEvaluationService(self.db)

        # Get triggered actions from conditions
        triggered_actions = await condition_service.get_triggered_actions(conditions)

        # Check if S&OP should be triggered
        should_soop, soop_reason = await condition_service.should_trigger_soop(conditions)
        if should_soop:
            logger.info(f"Triggering S&OP cycle: {soop_reason}")
            soop_trigger = TriggerContext(
                trigger_type=TriggerType.SOOP_TRIGGER,
                tenant_id=tenant_id,
                entity_type="network",
                entity_id=f"customer_{tenant_id}",
                priority=1,
                payload={"reason": soop_reason},
            )
            soop_actions = await self.process_trigger(soop_trigger)
            actions.extend(soop_actions)

        for action_spec in triggered_actions:
            condition_type = action_spec["condition_type"]
            entity_id = action_spec["entity_id"]

            # Check if scenario evaluation is needed
            if action_spec.get("requires_scenario_eval"):
                # Query real current state from DB
                current_state = await self._get_current_state(tenant_id, entity_id)

                # Evaluate scenarios
                recommended, comparison = await scenario_service.evaluate_and_recommend(
                    condition_type=condition_type,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    context=action_spec.get("context", {}),
                    current_state=current_state,
                )

                if recommended:
                    # Create action from recommended scenario
                    action_payload = {
                        "condition": condition_type,
                        "recommended_scenario": recommended.scenario.name,
                        "scenario_action": recommended.scenario.decision,
                        "confidence": comparison.recommendation_confidence,
                        "probability_of_success": recommended.probability_of_success,
                        "scorecard": {
                            "overall_score": recommended.scorecard.overall_score,
                            "service_level": recommended.scorecard.service_level.value if recommended.scorecard.service_level else None,
                            "total_cost": recommended.scorecard.total_cost.value if recommended.scorecard.total_cost else None,
                        },
                        "alternatives_count": len(comparison.scenarios),
                        "trade_offs": comparison.trade_offs,
                    }

                    # Determine mode based on confidence and severity
                    severity = action_spec.get("severity", "warning")
                    auto_execute = action_spec.get("auto_execute", True)

                    if severity == "emergency" or not auto_execute:
                        mode = ActionMode.INFORM
                    elif comparison.recommendation_confidence >= 0.85:
                        mode = ActionMode.AUTOMATE
                    else:
                        mode = ActionMode.INFORM

                    # Create the agent action
                    action = AgentAction(
                        tenant_id=tenant_id,
                        action_mode=mode,
                        action_type=f"scenario_recommendation_{condition_type}",
                        category=self._determine_category_from_condition(condition_type),
                        title=f"Recommended: {recommended.scenario.name}",
                        description=recommended.explanation,
                        explanation=comparison.recommendation_reason,
                        reasoning_chain={"key_drivers": recommended.key_drivers},
                        alternatives_considered={
                            "scenarios": [
                                {
                                    "name": s.scenario.name,
                                    "score": s.scorecard.overall_score,
                                }
                                for s in comparison.scenarios
                            ]
                        },
                        site_hierarchy_level=SiteHierarchyLevel.SITE,
                        site_key=entity_id,
                        product_hierarchy_level=ProductHierarchyLevel.PRODUCT,
                        product_key=action_spec.get("context", {}).get("product_id", entity_id),
                        time_bucket=TimeBucketType.DAY,
                        time_key=datetime.utcnow().strftime("%Y-%m-%d"),
                        metric_name="overall_score",
                        metric_before=0,  # Baseline
                        metric_after=recommended.scorecard.overall_score,
                        estimated_impact={
                            "probability_of_success": recommended.probability_of_success,
                            "value_at_risk": recommended.value_at_risk,
                        },
                        executed_at=datetime.utcnow(),
                        execution_result=ExecutionResult.SUCCESS,
                        execution_details=action_payload,
                        agent_id="scenario_evaluator",
                        agent_version="1.0.0",
                        predicted_outcome=recommended.scorecard.overall_score,
                        confidence_level=comparison.recommendation_confidence,
                    )
                    self.db.add(action)
                    await self.db.flush()
                    actions.append(action)

            else:
                # Direct agent trigger without scenario evaluation
                trigger_type = self._map_condition_to_trigger(condition_type)
                trigger = TriggerContext(
                    trigger_type=trigger_type,
                    tenant_id=tenant_id,
                    entity_type=action_spec["entity_type"],
                    entity_id=entity_id,
                    priority=action_spec["priority"],
                    payload=action_spec.get("context", {}),
                )
                trigger_actions = await self.process_trigger(trigger)
                actions.extend(trigger_actions)

        return actions

    def _map_condition_to_trigger(self, condition_type: str) -> TriggerType:
        """Map condition type to trigger type."""
        mapping = {
            "atp_shortfall": TriggerType.CONDITION_ATP_SHORTFALL,
            "inventory_below_safety": TriggerType.CONDITION_INVENTORY_LOW,
            "capacity_overload": TriggerType.CONDITION_CAPACITY_OVERLOAD,
            "multi_site_shortfall": TriggerType.CONDITION_MULTI_SITE_SHORTFALL,
            "order_past_due": TriggerType.CONDITION_ORDER_PAST_DUE,
        }
        return mapping.get(condition_type, TriggerType.PERIODIC_CHECK)

    def _determine_category_from_condition(self, condition_type: str) -> ActionCategory:
        """Map condition type to action category."""
        mapping = {
            "atp_shortfall": ActionCategory.ALLOCATION,
            "inventory_below_safety": ActionCategory.INVENTORY,
            "capacity_overload": ActionCategory.PRODUCTION,
            "multi_site_shortfall": ActionCategory.INVENTORY,
            "order_past_due": ActionCategory.LOGISTICS,
        }
        return mapping.get(condition_type, ActionCategory.OTHER)

    # =========================================================================
    # Plan Deviation Detection
    # =========================================================================

    async def check_plan_deviation(
        self,
        tenant_id: int,
        current_state: Dict[str, Any],
        previous_plan: Dict[str, Any],
    ) -> List[AgentAction]:
        """
        Alternative workflow: Check deviation from plan and trigger based on delta.

        Instead of absolute thresholds, compares current state to what was planned
        and triggers actions based on deviation magnitude.

        This implements the "run full capabilities on latest data, action based on
        deviation from previous plan" approach.
        """
        actions = []
        condition_service = ConditionMonitorService(self.db)

        # Analyze deviation
        deviation_analysis = await condition_service.check_plan_deviation(
            tenant_id=tenant_id,
            current_state=current_state,
            previous_plan=previous_plan,
        )

        deviation_score = deviation_analysis["total_deviation_score"]

        # Process recommended actions
        for recommendation in deviation_analysis.get("recommended_actions", []):
            action_type = recommendation["action"]
            reason = recommendation["reason"]

            if action_type == "trigger_soop_review":
                # Trigger S&OP review
                soop_actions = await self.run_planning_cycle(
                    tenant_id=tenant_id,
                    cycle_type="weekly",
                )
                actions.extend(soop_actions)

            elif action_type == "trigger_execution_replan":
                # Trigger execution level replanning
                trigger = TriggerContext(
                    trigger_type=TriggerType.PLAN_DEVIATION,
                    tenant_id=tenant_id,
                    entity_type="network",
                    entity_id=f"customer_{tenant_id}",
                    priority=2,
                    payload={
                        "deviation_score": deviation_score,
                        "reason": reason,
                        "deviations": {
                            "inventory": len(deviation_analysis["inventory_deviations"]),
                            "demand": len(deviation_analysis["demand_deviations"]),
                            "supply": len(deviation_analysis["supply_deviations"]),
                        },
                    },
                )
                trigger_actions = await self.process_trigger(trigger)
                actions.extend(trigger_actions)

            elif action_type == "forecast_recalibration":
                # Trigger forecast recalibration
                trigger = TriggerContext(
                    trigger_type=TriggerType.FORECAST_UPDATE,
                    tenant_id=tenant_id,
                    entity_type="forecast",
                    entity_id=f"customer_{tenant_id}",
                    priority=3,
                    payload={
                        "reason": "forecast_deviation",
                        "deviation_count": len(deviation_analysis["demand_deviations"]),
                    },
                )
                trigger_actions = await self.process_trigger(trigger)
                actions.extend(trigger_actions)

        # Log deviation action
        if deviation_score > 10:  # Only log significant deviations
            action = AgentAction(
                tenant_id=tenant_id,
                action_mode=ActionMode.INFORM if deviation_score > 25 else ActionMode.AUTOMATE,
                action_type="plan_deviation_detected",
                category=ActionCategory.OTHER,
                title=f"Plan Deviation: {deviation_score:.1f}%",
                description=f"Detected deviation from previous plan. "
                           f"Inventory: {len(deviation_analysis['inventory_deviations'])} items, "
                           f"Demand: {len(deviation_analysis['demand_deviations'])} items.",
                explanation=f"Overall deviation score of {deviation_score:.1f}% triggered analysis.",
                reasoning_chain={"deviation_analysis": deviation_analysis},
                alternatives_considered={"recommended_actions": deviation_analysis["recommended_actions"]},
                site_hierarchy_level=SiteHierarchyLevel.COMPANY,
                site_key=f"customer_{tenant_id}",
                product_hierarchy_level=ProductHierarchyLevel.CATEGORY,
                product_key="all",
                time_bucket=TimeBucketType.DAY,
                time_key=datetime.utcnow().strftime("%Y-%m-%d"),
                metric_name="deviation_score",
                metric_before=0,
                metric_after=deviation_score,
                estimated_impact={"actions_triggered": len(actions)},
                executed_at=datetime.utcnow(),
                execution_result=ExecutionResult.SUCCESS,
                agent_id="plan_deviation_monitor",
                agent_version="1.0.0",
            )
            self.db.add(action)
            await self.db.flush()
            actions.append(action)

        return actions

    # =========================================================================
    # Full Workflow Orchestration
    # =========================================================================

    async def run_complete_workflow(
        self,
        tenant_id: int,
        tier: ImportTier,
        imported_data: List[Dict[str, Any]],
        previous_snapshot: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Run the complete workflow from data import to action execution.

        This is the main entry point that ties together:
        1. CDC analysis
        2. Condition monitoring
        3. Agent execution
        4. Scenario evaluation
        5. Action recording

        Args:
            tenant_id: Customer ID
            tier: Import tier (transactional, operational, tactical)
            imported_data: The newly imported data
            previous_snapshot: Previous data snapshot for CDC

        Returns:
            Summary of workflow execution
        """
        from app.models.sync_job import SyncJobExecution, SyncDataType

        logger.info(f"Starting complete workflow for tenant {tenant_id}, tier {tier.value}")

        # Initialize services
        import_service = DataImportSchedulerService(self.db)
        condition_service = ConditionMonitorService(self.db)
        scenario_service = ScenarioEvaluationService(self.db)

        result = {
            "tier": tier.value,
            "tenant_id": tenant_id,
            "cdc_analysis": None,
            "conditions_detected": [],
            "actions_created": [],
            "scenarios_evaluated": [],
            "soop_triggered": False,
        }

        # Step 1: Create mock execution for CDC (in real impl, this comes from scheduler)
        # For now, create a placeholder
        class MockExecution:
            id = 0
            config = type('obj', (object,), {
                'data_type': SyncDataType.INVENTORY,
                'name': 'Mock Import'
            })()

        mock_execution = MockExecution()

        # Step 2: Perform CDC analysis
        cdc_result = await import_service.perform_cdc_analysis(
            execution=mock_execution,
            current_data=imported_data,
            previous_snapshot=previous_snapshot,
        )

        result["cdc_analysis"] = {
            "total_records": cdc_result.total_records,
            "changed_records": cdc_result.changed_records,
            "significant_changes": cdc_result.significant_changes,
            "version_hash": cdc_result.version_hash,
        }

        # Step 3: Process CDC result (triggers conditions, agents, etc.)
        actions = await self.on_cdc_result(cdc_result, tenant_id)
        result["actions_created"] = [
            {
                "id": a.id,
                "type": a.action_type,
                "mode": a.action_mode.value,
                "title": a.title,
            }
            for a in actions
        ]

        # Step 4: Run condition check for all types
        all_conditions = await condition_service.check_conditions(tenant_id)
        result["conditions_detected"] = [
            {
                "type": c.condition_type.value,
                "entity": c.entity_id,
                "severity": c.severity.value,
                "duration_hours": c.duration_hours,
            }
            for c in all_conditions
        ]

        # Step 5: Check if S&OP was triggered
        should_soop, soop_reason = await condition_service.should_trigger_soop(all_conditions)
        result["soop_triggered"] = should_soop
        if should_soop:
            result["soop_reason"] = soop_reason

        logger.info(
            f"Workflow complete: {len(actions)} actions, "
            f"{len(all_conditions)} conditions, S&OP={should_soop}"
        )

        return result

    async def _get_current_state(self, tenant_id: int, entity_id: str) -> Dict[str, Any]:
        """
        Query current supply chain state from DB for scenario evaluation.

        Returns aggregate cost, service level, and inventory metrics
        from InvLevel and supply_plan tables.
        """
        from app.models.sc_entities import InvLevel, Forecast

        try:
            # Total on-hand inventory value (proxy for cost exposure)
            inv_result = await self.db.execute(
                select(
                    func.sum(InvLevel.on_hand_qty).label("total_on_hand"),
                    func.count(InvLevel.id).label("location_count"),
                )
            )
            inv_row = inv_result.first()
            total_on_hand = float(inv_row.total_on_hand or 0) if inv_row else 0

            # Approximate service level from inventory coverage
            # (sites with positive inventory / total sites)
            if inv_row and inv_row.location_count and inv_row.location_count > 0:
                covered_result = await self.db.execute(
                    select(func.count(InvLevel.id)).where(InvLevel.on_hand_qty > 0)
                )
                covered = covered_result.scalar() or 0
                service_level = covered / inv_row.location_count
            else:
                service_level = 0.95  # Default assumption

            return {
                "total_cost": total_on_hand * 1.5,  # Rough holding cost estimate
                "service_level": round(service_level, 3),
                "total_on_hand": total_on_hand,
                "entity_id": entity_id,
            }

        except Exception as e:
            logger.warning(f"Failed to query current state, using defaults: {e}")
            return {
                "total_cost": 100000,
                "service_level": 0.92,
            }


# =============================================================================
# Agent Handler Registration
# =============================================================================

def _build_trm_handler(trm_class, evaluate_method: str):
    """
    Build an async handler that instantiates a TRM and calls its evaluate method.

    Each TRM has a slightly different evaluate method name, but they all
    accept a state dict (from trigger payload) and return a recommendation.
    """
    async def handler(trigger: TriggerContext, scope: AgentScope) -> Dict:
        try:
            trm = trm_class()
            payload = trigger.payload or {}

            eval_fn = getattr(trm, evaluate_method, None)
            if eval_fn is None:
                return {
                    "decision": {
                        "action_type": "error",
                        "title": f"No {evaluate_method} on {trm_class.__name__}",
                    },
                    "confidence": 0.0,
                    "input_features": payload,
                }

            # TRM evaluate methods are synchronous - call directly
            result = eval_fn(payload) if callable(eval_fn) else None

            # Normalize result to dict
            if hasattr(result, '__dict__'):
                result_dict = {k: v for k, v in result.__dict__.items() if not k.startswith('_')}
            elif isinstance(result, dict):
                result_dict = result
            else:
                result_dict = {"raw_result": str(result)}

            return {
                "decision": {
                    "action_type": result_dict.get("action", result_dict.get("recommendation", "evaluate")),
                    "title": f"{trm_class.__name__} decision",
                    "details": result_dict,
                },
                "confidence": result_dict.get("confidence", 0.75),
                "input_features": payload,
            }

        except Exception as e:
            logger.warning(f"{trm_class.__name__}.{evaluate_method} failed: {e}")
            return {
                "decision": {
                    "action_type": "error",
                    "title": f"{trm_class.__name__} error: {str(e)[:100]}",
                },
                "confidence": 0.0,
                "input_features": trigger.payload or {},
            }

    return handler


def create_orchestrator_with_handlers(db: AsyncSession) -> AgentOrchestratorService:
    """
    Create an orchestrator with real TRM/GNN agent handlers registered.

    Each handler instantiates the corresponding TRM class and delegates
    to its evaluate method. Failures are caught and logged gracefully.
    """
    orchestrator = AgentOrchestratorService(db)

    # --- Import and register real TRM agents ---
    try:
        from app.services.powell.atp_executor import ATPExecutorTRM
        orchestrator.register_agent_handler(
            AgentType.TRM_ATP,
            _build_trm_handler(ATPExecutorTRM, "check_atp"),
        )
    except Exception as e:
        logger.warning(f"Failed to register TRM_ATP handler: {e}")

    try:
        from app.services.powell.inventory_rebalancing_trm import InventoryRebalancingTRM
        orchestrator.register_agent_handler(
            AgentType.TRM_REBALANCE,
            _build_trm_handler(InventoryRebalancingTRM, "evaluate_rebalancing"),
        )
    except Exception as e:
        logger.warning(f"Failed to register TRM_REBALANCE handler: {e}")

    try:
        from app.services.powell.po_creation_trm import POCreationTRM
        orchestrator.register_agent_handler(
            AgentType.TRM_PO_CREATION,
            _build_trm_handler(POCreationTRM, "evaluate_po_need"),
        )
    except Exception as e:
        logger.warning(f"Failed to register TRM_PO_CREATION handler: {e}")

    try:
        from app.services.powell.order_tracking_trm import OrderTrackingTRM
        orchestrator.register_agent_handler(
            AgentType.TRM_ORDER_TRACKING,
            _build_trm_handler(OrderTrackingTRM, "evaluate_order"),
        )
    except Exception as e:
        logger.warning(f"Failed to register TRM_ORDER_TRACKING handler: {e}")

    # --- GNN agents ---
    try:
        from app.services.powell.allocation_service import AllocationService
        async def gnn_execution_handler(trigger: TriggerContext, scope: AgentScope) -> Dict:
            try:
                alloc_svc = AllocationService()
                payload = trigger.payload or {}
                # Generate default priority allocations using the service
                allocations = alloc_svc.generate_default_allocations()
                status = alloc_svc.get_allocation_status()
                return {
                    "decision": {
                        "action_type": "generate_allocations",
                        "title": "tGNN allocation generation",
                        "details": status if isinstance(status, dict) else {"status": str(status)[:200]},
                    },
                    "confidence": 0.8,
                    "input_features": payload,
                }
            except Exception as e:
                logger.warning(f"GNN_EXECUTION handler failed: {e}")
                return {"decision": {"action_type": "error", "title": str(e)[:100]}, "confidence": 0.0, "input_features": trigger.payload or {}}

        orchestrator.register_agent_handler(AgentType.GNN_EXECUTION, gnn_execution_handler)
    except Exception as e:
        logger.warning(f"Failed to register GNN_EXECUTION handler: {e}")

    try:
        from app.services.powell.sop_inference_service import SOPInferenceService
        async def gnn_soop_handler(trigger: TriggerContext, scope: AgentScope) -> Dict:
            try:
                payload = trigger.payload or {}
                config_id = payload.get("config_id") or payload.get("tenant_id")
                if config_id:
                    sop_svc = SOPInferenceService(db, config_id=config_id)
                    result = await sop_svc.analyze_network()
                    result_dict = result.to_dict() if hasattr(result, 'to_dict') else {"result": str(result)[:200]}
                    return {
                        "decision": {
                            "action_type": "sop_inference",
                            "title": "S&OP GraphSAGE inference",
                            "details": result_dict,
                        },
                        "confidence": 0.8,
                        "input_features": payload,
                    }
                return {"decision": {"action_type": "skip", "title": "No config_id"}, "confidence": 0.0, "input_features": payload}
            except Exception as e:
                logger.warning(f"GNN_SOOP handler failed: {e}")
                return {"decision": {"action_type": "error", "title": str(e)[:100]}, "confidence": 0.0, "input_features": trigger.payload or {}}

        orchestrator.register_agent_handler(AgentType.GNN_SOOP, gnn_soop_handler)
    except Exception as e:
        logger.warning(f"Failed to register GNN_SOOP handler: {e}")

    # --- Fallback: register graceful no-op for any unregistered agent types ---
    async def fallback_handler(trigger: TriggerContext, scope: AgentScope) -> Dict:
        """Graceful fallback for agent types without a dedicated handler."""
        return {
            "decision": {
                "action_type": "not_implemented",
                "title": f"Handler not yet registered for {trigger.trigger_type.value}",
            },
            "confidence": 0.0,
            "input_features": trigger.payload or {},
        }

    for agent_type in AgentType:
        if agent_type not in [AgentType.PLAN_COMPARISON, AgentType.LLM_PLANNER, AgentType.LLM_SUPERVISOR]:
            if agent_type not in orchestrator._agent_handlers:
                orchestrator.register_agent_handler(agent_type, fallback_handler)

    return orchestrator
