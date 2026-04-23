"""
Chat and A2A Collaboration Service
Phase 7 Sprint 2
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, select, update

from app.models.chat import ChatMessage, AgentSuggestion, WhatIfAnalysis, MessageType, SenderType
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
from app.schemas.chat import (
    ChatMessageCreate,
    AgentSuggestionRequest,
    AgentSuggestionContext,
    WhatIfAnalysisRequest,
)

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling A2A chat and collaboration."""

    def __init__(self, db: Session):
        self.db = db

    # ===== Chat Messages =====

    async def get_messages(
        self,
        scenario_id: int,
        since: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[ChatMessage], int, bool]:
        """
        Get chat messages for a scenario.

        Args:
            scenario_id: Scenario ID
            since: Only return messages after this timestamp
            limit: Maximum number of messages to return
            offset: Offset for pagination

        Returns:
            Tuple of (messages, total_count, has_more)
        """
        stmt = select(ChatMessage).filter(ChatMessage.scenario_id == scenario_id)

        if since:
            stmt = stmt.filter(ChatMessage.created_at > since)

        # Get total count
        count_result = await self.db.execute(select(ChatMessage).filter(ChatMessage.scenario_id == scenario_id))
        total_count = len(count_result.scalars().all())

        # Get messages
        stmt = stmt.order_by(ChatMessage.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        # Reverse to chronological order
        messages.reverse()

        has_more = (offset + limit) < total_count

        return messages, total_count, has_more

    async def create_message(
        self,
        scenario_id: int,
        message_data: ChatMessageCreate,
    ) -> ChatMessage:
        """
        Create a new chat message.

        Args:
            scenario_id: Scenario ID
            message_data: Message data

        Returns:
            Created message
        """
        message = ChatMessage(
            scenario_id=scenario_id,
            sender_id=message_data.sender_id,
            sender_name=message_data.sender_name,
            sender_type=message_data.sender_type,
            recipient_id=message_data.recipient_id,
            content=message_data.content,
            type=message_data.type,
            message_metadata=message_data.message_metadata,
            delivered=True,
        )

        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        logger.info(
            f"Created chat message {message.id} in scenario {scenario_id} from {message.sender_name}"
        )

        return message

    async def mark_messages_read(
        self,
        scenario_id: int,
        message_ids: List[int],
    ) -> int:
        """
        Mark messages as read.

        Args:
            scenario_id: Scenario ID
            message_ids: List of message IDs to mark as read

        Returns:
            Number of messages marked as read
        """
        stmt = (
            update(ChatMessage)
            .where(
                ChatMessage.scenario_id == scenario_id,
                ChatMessage.id.in_(message_ids),
                ChatMessage.read == False,  # noqa: E712
            )
            .values(read=True, read_at=datetime.utcnow())
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        count = result.rowcount

        logger.info(f"Marked {count} messages as read in scenario {scenario_id}")

        return count

    # ===== Agent Suggestions =====

    async def get_suggestions(
        self,
        scenario_id: int,
        agent_name: Optional[str] = None,
        pending_only: bool = False,
    ) -> List[AgentSuggestion]:
        """
        Get agent suggestions for a scenario.

        Args:
            scenario_id: Scenario ID
            agent_name: Filter by agent name
            pending_only: Only return pending (not accepted/declined) suggestions

        Returns:
            List of suggestions
        """
        stmt = select(AgentSuggestion).filter(
            AgentSuggestion.scenario_id == scenario_id
        )

        if agent_name:
            stmt = stmt.filter(AgentSuggestion.agent_name == agent_name)

        if pending_only:
            stmt = stmt.filter(AgentSuggestion.accepted == None)  # noqa: E711

        stmt = stmt.order_by(desc(AgentSuggestion.created_at))
        result = await self.db.execute(stmt)
        suggestions = result.scalars().all()

        return suggestions

    async def request_suggestion(
        self,
        scenario_id: int,
        agent_name: str,
        request_data: Optional[AgentSuggestionRequest] = None,
        tenant_id: Optional[int] = None,
    ) -> AgentSuggestion:
        """
        Request an agent suggestion (LLM-powered).

        This triggers the LLM agent to generate an intelligent order recommendation.

        Args:
            scenario_id: Scenario ID
            agent_name: Agent name (retailer, wholesaler, etc.)
            request_data: Optional additional context

        Returns:
            Created suggestion with LLM reasoning
        """
        # Get scenario
        scenario_result = await self.db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = scenario_result.scalars().first()
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        # Build comprehensive context
        try:
            context = await self._build_suggestion_context(scenario_id, agent_name)
        except Exception as e:
            logger.error(f"Failed to build context for {agent_name} in scenario {scenario_id}: {e}")
            # Fallback to minimal context
            context = {
                "current_period": scenario.current_period,
                "current_inventory": 0,
                "current_backlog": 0,
            }

        # Call LLM for suggestion
        try:
            from app.services.llm_suggestion_service import get_llm_service

            llm_service = get_llm_service()

            llm_response = await llm_service.generate_suggestion(
                agent_name=agent_name,
                context=context,
                request_data=request_data.dict() if request_data else None,
                tenant_id=tenant_id,
            )

            order_quantity = llm_response['order_quantity']
            confidence = llm_response['confidence']
            rationale = llm_response['rationale']

            # Store full reasoning in context
            context['llm_reasoning'] = {
                "reasoning_steps": llm_response.get('reasoning_steps', []),
                "risk_factors": llm_response.get('risk_factors', []),
                "alternatives": llm_response.get('alternative_strategies', []),
            }

            logger.info(
                f"LLM suggestion for {agent_name} in scenario {scenario_id}: "
                f"{order_quantity} units ({confidence:.0%} confidence)"
            )

        except Exception as e:
            logger.error(f"LLM suggestion failed for {agent_name}: {e}, falling back to heuristic")

            # Fallback to heuristic
            order_quantity = self._generate_heuristic_suggestion(context)
            confidence = 0.6
            rationale = (
                f"Heuristic recommendation (LLM unavailable): Order {order_quantity} units. "
                f"Current inventory: {context.get('current_inventory', 0)}, "
                f"backlog: {context.get('current_backlog', 0)}."
            )

        # Create suggestion
        suggestion = AgentSuggestion(
            scenario_id=scenario_id,
            round=scenario.current_period,
            agent_name=agent_name,
            order_quantity=order_quantity,
            confidence=confidence,
            rationale=rationale,
            context=context,
        )

        self.db.add(suggestion)
        await self.db.commit()
        await self.db.refresh(suggestion)

        logger.info(
            f"Created suggestion {suggestion.id} from {agent_name} in scenario {scenario_id}: "
            f"{order_quantity} units ({confidence:.0%} confidence)"
        )

        return suggestion

    async def accept_suggestion(
        self,
        scenario_id: int,
        suggestion_id: int,
        scenario_user_id: int,
    ) -> AgentSuggestion:
        """
        Accept an agent suggestion.

        Args:
            scenario_id: Scenario ID
            suggestion_id: Suggestion ID
            scenario_user_id: ScenarioUser accepting the suggestion

        Returns:
            Updated suggestion
        """
        suggestion_result = await self.db.execute(
            select(AgentSuggestion).filter(
                AgentSuggestion.id == suggestion_id,
                AgentSuggestion.scenario_id == scenario_id,
            )
        )
        suggestion = suggestion_result.scalars().first()

        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found in scenario {scenario_id}")

        suggestion.accepted = True
        suggestion.scenario_user_id = scenario_user_id
        suggestion.decided_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(suggestion)

        logger.info(
            f"ScenarioUser {scenario_user_id} accepted suggestion {suggestion_id} in scenario {scenario_id}"
        )

        return suggestion

    async def decline_suggestion(
        self,
        scenario_id: int,
        suggestion_id: int,
        scenario_user_id: int,
    ) -> AgentSuggestion:
        """
        Decline an agent suggestion.

        Args:
            scenario_id: Scenario ID
            suggestion_id: Suggestion ID
            scenario_user_id: ScenarioUser declining the suggestion

        Returns:
            Updated suggestion
        """
        suggestion_result = await self.db.execute(
            select(AgentSuggestion).filter(
                AgentSuggestion.id == suggestion_id,
                AgentSuggestion.scenario_id == scenario_id,
            )
        )
        suggestion = suggestion_result.scalars().first()

        if not suggestion:
            raise ValueError(f"Suggestion {suggestion_id} not found in scenario {scenario_id}")

        suggestion.accepted = False
        suggestion.scenario_user_id = scenario_user_id
        suggestion.decided_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(suggestion)

        logger.info(
            f"ScenarioUser {scenario_user_id} declined suggestion {suggestion_id} in scenario {scenario_id}"
        )

        return suggestion

    # ===== What-If Analysis =====

    async def create_what_if_analysis(
        self,
        scenario_id: int,
        analysis_data: WhatIfAnalysisRequest,
    ) -> WhatIfAnalysis:
        """
        Create a what-if analysis request.

        Args:
            scenario_id: Scenario ID
            analysis_data: Analysis request data

        Returns:
            Created analysis
        """
        scenario_result = await self.db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = scenario_result.scalars().first()
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        analysis = WhatIfAnalysis(
            scenario_id=scenario_id,
            round=scenario.current_period,
            scenario_user_id=analysis_data.scenario_user_id,
            question=analysis_data.question,
            scenario=analysis_data.scenario,
        )

        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)

        logger.info(
            f"Created what-if analysis {analysis.id} for scenario_user {analysis_data.scenario_user_id} in scenario {scenario_id}"
        )

        # TODO: Trigger async analysis processing
        # For now, mark as pending

        return analysis

    async def get_what_if_analysis(
        self,
        scenario_id: int,
        analysis_id: int,
    ) -> Optional[WhatIfAnalysis]:
        """
        Get a what-if analysis.

        Args:
            scenario_id: Scenario ID
            analysis_id: Analysis ID

        Returns:
            Analysis or None if not found
        """
        analysis_result = await self.db.execute(
            select(WhatIfAnalysis).filter(
                WhatIfAnalysis.id == analysis_id,
                WhatIfAnalysis.scenario_id == scenario_id,
            )
        )
        analysis = analysis_result.scalars().first()

        return analysis

    # ===== Helper Methods =====

    async def _build_suggestion_context(
        self,
        scenario_id: int,
        agent_name: str,
    ) -> Dict[str, Any]:
        """
        Build comprehensive context for LLM suggestion.

        Includes:
        - Current inventory, backlog, pipeline
        - Recent demand history (last 10 rounds)
        - Forecast demand
        - Historical performance metrics
        - Bullwhip detection
        - Demand volatility

        Args:
            scenario_id: Scenario ID
            agent_name: Agent role name

        Returns:
            Dictionary with comprehensive scenario context
        """
        from app.models.supply_chain import ScenarioUserPeriod
        from sqlalchemy import func

        # Get scenario
        scenario_result = await self.db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = scenario_result.scalars().first()

        # Get scenario_user for this agent role
        scenario_user_result = await self.db.execute(
            select(ScenarioUser).filter(
                ScenarioUser.scenario_id == scenario_id,
                ScenarioUser.role == agent_name.upper()
            )
        )
        scenario_user = scenario_user_result.scalars().first()

        if not scenario_user:
            raise ValueError(f"No scenario_user found for agent {agent_name} in scenario {scenario_id}")

        # Get recent scenario_user rounds (last 10)
        rounds_result = await self.db.execute(
            select(ScenarioUserPeriod)
            .filter(ScenarioUserPeriod.scenario_user_id == scenario_user.id)
            .order_by(desc(ScenarioUserPeriod.round))
            .limit(10)
        )
        recent_rounds = list(rounds_result.scalars().all())

        # Current state (most recent round)
        current_period = recent_rounds[0] if recent_rounds else None

        # Calculate metrics from history
        recent_demand = []
        recent_orders = []

        if recent_rounds:
            # Reverse to get chronological order
            for r in reversed(recent_rounds):
                if hasattr(r, 'demand') and r.demand is not None:
                    recent_demand.append(r.demand)
                if hasattr(r, 'order_placed') and r.order_placed is not None:
                    recent_orders.append(r.order_placed)

        # Average metrics
        avg_inventory = sum(r.current_inventory for r in recent_rounds) / len(recent_rounds) if recent_rounds else 0
        avg_backlog = sum(r.current_backlog for r in recent_rounds) / len(recent_rounds) if recent_rounds else 0
        total_cost = sum(r.total_cost for r in recent_rounds) if recent_rounds else 0

        # Service level (% of demand met without backlog)
        fulfilled_rounds = sum(1 for r in recent_rounds if r.current_backlog == 0)
        service_level = fulfilled_rounds / len(recent_rounds) if recent_rounds else 0.0

        # Demand volatility calculation
        demand_volatility = "unknown"
        if len(recent_demand) > 1:
            try:
                import statistics
                demand_mean = statistics.mean(recent_demand)
                if demand_mean > 0:
                    demand_std = statistics.stdev(recent_demand)
                    cv = demand_std / demand_mean  # Coefficient of variation
                    if cv > 0.5:
                        demand_volatility = "high"
                    elif cv > 0.2:
                        demand_volatility = "moderate"
                    else:
                        demand_volatility = "low"
            except Exception as e:
                logger.warning(f"Could not calculate demand volatility: {e}")

        # Bullwhip detection (compare order variance to demand variance)
        bullwhip_detected = False
        if len(recent_orders) > 2 and len(recent_demand) > 2:
            try:
                import statistics
                if len(recent_orders) == len(recent_demand):
                    order_var = statistics.variance(recent_orders)
                    demand_var = statistics.variance(recent_demand)
                    # Bullwhip: orders more volatile than demand
                    if demand_var > 0:
                        bullwhip_detected = order_var > (demand_var * 1.5)
            except Exception as e:
                logger.warning(f"Could not detect bullwhip: {e}")

        # Forecast demand (simple moving average)
        forecast_demand = 0
        forecast_confidence = 0.5

        if len(recent_demand) >= 3:
            # Use last 3 rounds for forecast
            forecast_demand = sum(recent_demand[-3:]) / 3
            forecast_confidence = 0.7
        elif recent_demand:
            forecast_demand = recent_demand[-1]
            forecast_confidence = 0.5

        # Pipeline orders (orders placed but not yet received)
        pipeline_orders = []
        if current_period and hasattr(scenario_user, 'lead_time') and scenario_user.lead_time:
            lead_time = scenario_user.lead_time
            # Look back through recent rounds within lead time
            for r in recent_rounds[:lead_time]:
                if hasattr(r, 'order_placed') and r.order_placed:
                    eta_rounds = lead_time - (scenario.current_period - r.round)
                    if eta_rounds > 0:
                        pipeline_orders.append({
                            "round": r.round,
                            "quantity": r.order_placed,
                            "eta_rounds": eta_rounds
                        })

        # Incoming shipment
        incoming_shipment = 0
        if current_period and hasattr(current_period, 'incoming_shipment'):
            incoming_shipment = current_period.incoming_shipment or 0

        # Build comprehensive context
        context = {
            # Current state
            "current_period": scenario.current_period,
            "current_inventory": current_period.current_inventory if current_period else 0,
            "current_backlog": current_period.current_backlog if current_period else 0,
            "incoming_shipment": incoming_shipment,
            "lead_time": scenario_user.lead_time if hasattr(scenario_user, 'lead_time') else 2,

            # Pipeline
            "pipeline_orders": pipeline_orders,

            # Demand history and forecast
            "recent_demand": recent_demand,
            "forecast_demand": forecast_demand,
            "forecast_confidence": forecast_confidence,

            # Performance metrics
            "avg_inventory": avg_inventory,
            "avg_backlog": avg_backlog,
            "service_level": service_level,
            "total_cost": total_cost,

            # Strategic indicators
            "bullwhip_detected": bullwhip_detected,
            "demand_volatility": demand_volatility,
        }

        logger.debug(f"Built context for {agent_name}: {context}")

        return context

    def _generate_heuristic_suggestion(self, context: Dict[str, Any]) -> int:
        """
        Generate a simple heuristic suggestion.

        This is a placeholder until LLM integration is complete.

        Args:
            context: Scenario state context

        Returns:
            Suggested order quantity
        """
        inventory = context.get("current_inventory", 0)
        backlog = context.get("current_backlog", 0)

        # Simple base stock policy
        target_stock = 50
        order_quantity = max(0, target_stock - inventory + backlog)

        return order_quantity

    async def get_unread_count(
        self,
        scenario_id: int,
        user_id: str,
    ) -> int:
        """
        Get unread message count for a user in a scenario.

        Args:
            scenario_id: Scenario ID
            user_id: User ID (scenario_user:1)

        Returns:
            Number of unread messages
        """
        result = await self.db.execute(
            select(ChatMessage).filter(
                ChatMessage.scenario_id == scenario_id,
                ChatMessage.recipient_id == user_id,
                ChatMessage.read == False,  # noqa: E712
            )
        )
        count = len(result.scalars().all())

        return count
