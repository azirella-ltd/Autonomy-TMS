"""
Collaboration Service
Sprint 5: Enhanced Collaboration with A2A, H2A, and H2H

Supports three modes of collaboration:
1. Agent-to-Agent (A2A): AI agents coordinate decisions
2. Human-to-Agent (H2A): Humans interact with AI with full explainability
3. Human-to-Human (H2H): Team collaboration with rationale capture

Key Features:
- Agent action explainability
- Human decision rationale capture
- Trade-off analysis
- Approval workflows
- Real-time messaging
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
import logging
import json

from app.models.chat import ChatMessage, AgentSuggestion, WhatIfAnalysis, MessageType, SenderType
from app.models.recommendations import Recommendation
from app.models.supply_chain_config import SupplyChainConfig

logger = logging.getLogger(__name__)


class CollaborationService:
    """
    Enhanced collaboration service supporting A2A, H2A, and H2H interactions
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ========================================================================
    # Agent-to-Agent (A2A) Collaboration
    # ========================================================================

    async def send_agent_to_agent_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str = "coordination",
        context: Optional[Dict] = None,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Send message from one agent to another for coordination

        A2A messages enable agents to:
        - Negotiate shared resources
        - Coordinate timing of actions
        - Share forecast information
        - Resolve conflicts

        Args:
            from_agent: Sending agent identifier (e.g., "demand_planner_agent")
            to_agent: Receiving agent identifier (e.g., "supply_planner_agent")
            content: Message content
            message_type: Type of coordination (negotiation, information, request)
            context: Additional context (supply chain state, constraints, etc.)
            session_id: Optional session/scenario ID for context

        Returns:
            Message with agent coordination details
        """
        try:
            # Create A2A message
            message = ChatMessage(
                scenario_id=int(session_id) if session_id else None,
                sender_id=f"agent:{from_agent}",
                sender_name=from_agent,
                sender_type=SenderType.AGENT,
                recipient_id=f"agent:{to_agent}",
                content=content,
                type=MessageType.TEXT,
                message_metadata={
                    "coordination_type": message_type,
                    "context": context or {},
                    "timestamp": datetime.utcnow().isoformat(),
                    "requires_response": message_type in ["negotiation", "request"]
                },
                delivered=False,
                read=False,
                created_at=datetime.utcnow()
            )

            self.db.add(message)
            await self.db.commit()
            await self.db.refresh(message)

            logger.info(f"A2A message sent: {from_agent} -> {to_agent}")

            return {
                "id": message.id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "content": content,
                "type": message_type,
                "sent_at": message.created_at,
                "status": "sent"
            }

        except Exception as e:
            logger.error(f"Failed to send A2A message: {e}")
            await self.db.rollback()
            raise

    async def get_agent_coordination_thread(
        self,
        agent1: str,
        agent2: str,
        session_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get conversation thread between two agents

        Returns chronological sequence of A2A messages for analysis
        """
        stmt = select(ChatMessage).where(
            and_(
                ChatMessage.sender_type == SenderType.AGENT,
                or_(
                    and_(
                        ChatMessage.sender_id == f"agent:{agent1}",
                        ChatMessage.recipient_id == f"agent:{agent2}"
                    ),
                    and_(
                        ChatMessage.sender_id == f"agent:{agent2}",
                        ChatMessage.recipient_id == f"agent:{agent1}"
                    )
                )
            )
        )

        if session_id:
            stmt = stmt.where(ChatMessage.scenario_id == int(session_id))

        stmt = stmt.order_by(ChatMessage.created_at).limit(limit)

        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        return [
            {
                "id": m.id,
                "from_agent": m.sender_name,
                "to_agent": m.recipient_id.split(":")[1] if m.recipient_id else None,
                "content": m.content,
                "metadata": m.message_metadata,
                "created_at": m.created_at
            }
            for m in messages
        ]

    # ========================================================================
    # Human-to-Agent (H2A) Collaboration with Explainability
    # ========================================================================

    async def explain_agent_suggestion(
        self,
        suggestion_id: int
    ) -> Dict:
        """
        Generate comprehensive explanation for agent suggestion

        Provides full explainability including:
        - Rationale breakdown (why this decision?)
        - Alternative options considered
        - Trade-offs analyzed
        - Confidence intervals
        - Data sources used

        Args:
            suggestion_id: ID of agent suggestion to explain

        Returns:
            Detailed explanation with rationale, alternatives, trade-offs
        """
        try:
            # Get suggestion
            stmt = select(AgentSuggestion).where(AgentSuggestion.id == suggestion_id)
            result = await self.db.execute(stmt)
            suggestion = result.scalar_one_or_none()

            if not suggestion:
                return {"error": "Suggestion not found"}

            # Parse context for explainability
            context = suggestion.context or {}

            # Generate explanation
            explanation = {
                "suggestion_id": suggestion_id,
                "agent_name": suggestion.agent_name,
                "recommended_action": {
                    "order_quantity": suggestion.order_quantity,
                    "confidence": suggestion.confidence,
                    "rationale_summary": suggestion.rationale
                },

                # Why did the agent make this decision?
                "rationale_breakdown": {
                    "primary_factors": self._extract_primary_factors(context),
                    "data_sources": self._identify_data_sources(context),
                    "assumptions": self._identify_assumptions(context),
                    "constraints_considered": self._identify_constraints(context)
                },

                # What else did the agent consider?
                "alternatives_considered": self._generate_alternatives(
                    suggestion.order_quantity,
                    context
                ),

                # What are the trade-offs?
                "trade_off_analysis": self._analyze_trade_offs(
                    suggestion.order_quantity,
                    context
                ),

                # How confident is the agent?
                "confidence_breakdown": {
                    "overall_confidence": suggestion.confidence,
                    "data_quality": self._assess_data_quality(context),
                    "uncertainty_factors": self._identify_uncertainty(context)
                },

                # What might go wrong?
                "risks_and_assumptions": {
                    "key_risks": self._identify_risks(context),
                    "critical_assumptions": self._identify_critical_assumptions(context),
                    "sensitivity_analysis": self._perform_sensitivity(
                        suggestion.order_quantity,
                        context
                    )
                }
            }

            return explanation

        except Exception as e:
            logger.error(f"Failed to explain suggestion: {e}")
            raise

    async def capture_human_decision_rationale(
        self,
        suggestion_id: int,
        user_id: str,
        decision: str,  # "accept", "reject", "modify"
        rationale: str,
        modified_quantity: Optional[int] = None,
        trade_off_preferences: Optional[Dict] = None
    ) -> Dict:
        """
        Capture human decision and rationale for learning

        Records why humans accept/reject/modify agent suggestions
        Enables agent learning from human expertise

        Args:
            suggestion_id: ID of suggestion being decided
            user_id: User making the decision
            decision: accept, reject, or modify
            rationale: Human explanation for decision
            modified_quantity: If modified, the new quantity
            trade_off_preferences: Human's trade-off priorities

        Returns:
            Decision record with captured rationale
        """
        try:
            # Get suggestion
            stmt = select(AgentSuggestion).where(AgentSuggestion.id == suggestion_id)
            result = await self.db.execute(stmt)
            suggestion = result.scalar_one_or_none()

            if not suggestion:
                return {"error": "Suggestion not found"}

            # Update suggestion with decision
            suggestion.accepted = (decision == "accept")
            suggestion.decided_at = datetime.utcnow()

            # Store detailed rationale in metadata
            decision_metadata = {
                "decision": decision,
                "original_suggestion": suggestion.order_quantity,
                "modified_quantity": modified_quantity,
                "human_rationale": rationale,
                "trade_off_preferences": trade_off_preferences or {},
                "decided_by": user_id,
                "decided_at": datetime.utcnow().isoformat(),

                # Analyze why human disagreed (if applicable)
                "disagreement_analysis": self._analyze_disagreement(
                    decision,
                    suggestion.order_quantity,
                    modified_quantity,
                    suggestion.rationale,
                    rationale
                ) if decision != "accept" else None
            }

            # Create chat message with human rationale
            rationale_message = ChatMessage(
                scenario_id=suggestion.scenario_id,
                sender_id=f"user:{user_id}",
                sender_name=user_id,
                sender_type=SenderType.SCENARIO_USER,
                recipient_id=f"agent:{suggestion.agent_name}",
                content=rationale,
                type=MessageType.TEXT,
                message_metadata=decision_metadata,
                created_at=datetime.utcnow()
            )

            self.db.add(rationale_message)
            await self.db.commit()

            logger.info(f"Human decision captured: {decision} for suggestion {suggestion_id}")

            return {
                "suggestion_id": suggestion_id,
                "decision": decision,
                "rationale": rationale,
                "learning_captured": True,
                "message_id": rationale_message.id
            }

        except Exception as e:
            logger.error(f"Failed to capture decision rationale: {e}")
            await self.db.rollback()
            raise

    # ========================================================================
    # Human-to-Human (H2H) Collaboration with Rationale
    # ========================================================================

    async def request_approval(
        self,
        from_user: str,
        to_user: str,
        entity_type: str,  # "recommendation", "plan", "order"
        entity_id: str,
        request_message: str,
        rationale: str,
        trade_offs: Optional[Dict] = None,
        urgency: str = "normal"
    ) -> Dict:
        """
        Request approval from another user with full rationale

        Enables H2H collaboration with explicit rationale capture

        Args:
            from_user: User requesting approval
            to_user: User who needs to approve
            entity_type: Type of entity needing approval
            entity_id: ID of entity
            request_message: Summary of request
            rationale: Why this approval is needed
            trade_offs: Trade-offs being considered
            urgency: Priority level (low, normal, high, critical)

        Returns:
            Approval request with rationale
        """
        try:
            approval_metadata = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "rationale": rationale,
                "trade_offs": trade_offs or {},
                "urgency": urgency,
                "status": "pending",
                "requested_at": datetime.utcnow().isoformat()
            }

            # Create approval request message
            message = ChatMessage(
                sender_id=f"user:{from_user}",
                sender_name=from_user,
                sender_type=SenderType.SCENARIO_USER,
                recipient_id=f"user:{to_user}",
                content=request_message,
                type=MessageType.QUESTION,
                message_metadata=approval_metadata,
                delivered=False,
                read=False,
                created_at=datetime.utcnow()
            )

            self.db.add(message)
            await self.db.commit()
            await self.db.refresh(message)

            logger.info(f"Approval requested: {from_user} -> {to_user} for {entity_type}:{entity_id}")

            return {
                "request_id": message.id,
                "from_user": from_user,
                "to_user": to_user,
                "entity": {"type": entity_type, "id": entity_id},
                "rationale": rationale,
                "trade_offs": trade_offs,
                "status": "pending"
            }

        except Exception as e:
            logger.error(f"Failed to request approval: {e}")
            await self.db.rollback()
            raise

    async def respond_to_approval(
        self,
        request_id: int,
        user_id: str,
        decision: str,  # "approve", "reject", "request_changes"
        response_rationale: str,
        alternative_suggestion: Optional[Dict] = None
    ) -> Dict:
        """
        Respond to approval request with rationale

        Captures human reasoning in approval workflows

        Args:
            request_id: ID of approval request
            user_id: User responding
            decision: approve, reject, or request_changes
            response_rationale: Why this decision was made
            alternative_suggestion: If requesting changes, what to change

        Returns:
            Response with rationale captured
        """
        try:
            # Get original request
            stmt = select(ChatMessage).where(ChatMessage.id == request_id)
            result = await self.db.execute(stmt)
            request_msg = result.scalar_one_or_none()

            if not request_msg:
                return {"error": "Request not found"}

            # Update request metadata with decision
            metadata = request_msg.message_metadata or {}
            metadata["status"] = decision
            metadata["decided_at"] = datetime.utcnow().isoformat()
            metadata["decision_rationale"] = response_rationale
            request_msg.message_metadata = metadata

            # Create response message
            response_content = f"{decision.upper()}: {response_rationale}"
            if alternative_suggestion:
                response_content += f"\n\nAlternative: {json.dumps(alternative_suggestion)}"

            response_msg = ChatMessage(
                sender_id=f"user:{user_id}",
                sender_name=user_id,
                sender_type=SenderType.SCENARIO_USER,
                recipient_id=request_msg.sender_id,
                content=response_content,
                type=MessageType.TEXT,
                message_metadata={
                    "decision": decision,
                    "response_to": request_id,
                    "rationale": response_rationale,
                    "alternative": alternative_suggestion
                },
                created_at=datetime.utcnow()
            )

            self.db.add(response_msg)
            await self.db.commit()

            logger.info(f"Approval decision: {decision} by {user_id}")

            return {
                "request_id": request_id,
                "decision": decision,
                "rationale": response_rationale,
                "alternative": alternative_suggestion
            }

        except Exception as e:
            logger.error(f"Failed to respond to approval: {e}")
            await self.db.rollback()
            raise

    # ========================================================================
    # Trade-off Analysis
    # ========================================================================

    async def analyze_decision_tradeoffs(
        self,
        decision_context: Dict,
        options: List[Dict]
    ) -> Dict:
        """
        Analyze trade-offs between multiple decision options

        Helps humans understand implications of different choices

        Args:
            decision_context: Context of the decision (constraints, goals, etc.)
            options: List of options to compare

        Returns:
            Trade-off analysis with pros/cons/scores
        """
        try:
            trade_off_matrix = []

            for option in options:
                analysis = {
                    "option": option,
                    "scores": {
                        "cost_impact": self._score_cost(option, decision_context),
                        "service_level_impact": self._score_service_level(option, decision_context),
                        "risk_impact": self._score_risk(option, decision_context),
                        "sustainability_impact": self._score_sustainability(option, decision_context)
                    },
                    "pros": self._identify_pros(option, decision_context),
                    "cons": self._identify_cons(option, decision_context),
                    "overall_score": 0.0
                }

                # Calculate weighted overall score
                analysis["overall_score"] = (
                    analysis["scores"]["cost_impact"] * 0.3 +
                    analysis["scores"]["service_level_impact"] * 0.3 +
                    analysis["scores"]["risk_impact"] * 0.2 +
                    analysis["scores"]["sustainability_impact"] * 0.2
                )

                trade_off_matrix.append(analysis)

            # Sort by overall score
            trade_off_matrix.sort(key=lambda x: x["overall_score"], reverse=True)

            return {
                "decision_context": decision_context,
                "options_analyzed": len(options),
                "trade_off_matrix": trade_off_matrix,
                "recommendation": trade_off_matrix[0] if trade_off_matrix else None
            }

        except Exception as e:
            logger.error(f"Failed to analyze trade-offs: {e}")
            raise

    # ========================================================================
    # Helper Methods for Explainability
    # ========================================================================

    def _extract_primary_factors(self, context: Dict) -> List[Dict]:
        """Extract key factors that influenced agent decision"""
        factors = []

        # Inventory level
        if "inventory" in context:
            factors.append({
                "factor": "Current Inventory",
                "value": context["inventory"],
                "impact": "high" if context["inventory"] < 100 else "medium"
            })

        # Demand forecast
        if "demand_forecast" in context:
            factors.append({
                "factor": "Demand Forecast",
                "value": context["demand_forecast"],
                "impact": "high"
            })

        # Lead time
        if "lead_time" in context:
            factors.append({
                "factor": "Lead Time",
                "value": f"{context['lead_time']} periods",
                "impact": "medium"
            })

        return factors

    def _identify_data_sources(self, context: Dict) -> List[str]:
        """Identify data sources used in decision"""
        sources = []
        if "inventory" in context:
            sources.append("Current Inventory Records")
        if "demand_forecast" in context:
            sources.append("Statistical Demand Forecast")
        if "backlog" in context:
            sources.append("Current Backlog Status")
        return sources

    def _identify_assumptions(self, context: Dict) -> List[str]:
        """Identify key assumptions in decision"""
        return [
            "Lead times remain stable",
            "Forecast accuracy within historical range",
            "No supply chain disruptions",
            "Normal demand variability"
        ]

    def _identify_constraints(self, context: Dict) -> List[Dict]:
        """Identify constraints considered"""
        constraints = []
        if "min_order" in context:
            constraints.append({"type": "Minimum Order Quantity", "value": context["min_order"]})
        if "budget" in context:
            constraints.append({"type": "Budget Constraint", "value": context["budget"]})
        return constraints

    def _generate_alternatives(self, recommended: int, context: Dict) -> List[Dict]:
        """Generate alternative options"""
        return [
            {
                "quantity": int(recommended * 0.8),
                "rationale": "Conservative approach - lower inventory risk",
                "trade_off": "Higher stockout risk"
            },
            {
                "quantity": recommended,
                "rationale": "Recommended quantity - balanced approach",
                "trade_off": "Optimal balance"
            },
            {
                "quantity": int(recommended * 1.2),
                "rationale": "Aggressive approach - higher service level",
                "trade_off": "Higher holding cost"
            }
        ]

    def _analyze_trade_offs(self, quantity: int, context: Dict) -> Dict:
        """Analyze trade-offs of decision"""
        return {
            "service_level_vs_cost": {
                "service_level": "High (95%+)",
                "holding_cost": "Medium",
                "trade_off": "Accepting moderate inventory cost for high service"
            },
            "risk_vs_flexibility": {
                "stockout_risk": "Low",
                "excess_inventory_risk": "Medium",
                "trade_off": "Preferring stockout protection over inventory minimization"
            }
        }

    def _assess_data_quality(self, context: Dict) -> str:
        """Assess quality of data used"""
        # Simplified assessment
        if context.get("forecast_accuracy", 0) > 0.85:
            return "High"
        elif context.get("forecast_accuracy", 0) > 0.7:
            return "Medium"
        else:
            return "Low"

    def _identify_uncertainty(self, context: Dict) -> List[str]:
        """Identify sources of uncertainty"""
        return [
            "Demand forecast variability",
            "Lead time fluctuations",
            "External market conditions"
        ]

    def _identify_risks(self, context: Dict) -> List[Dict]:
        """Identify key risks"""
        return [
            {"risk": "Stockout", "probability": "Low", "impact": "High"},
            {"risk": "Excess Inventory", "probability": "Medium", "impact": "Medium"},
            {"risk": "Forecast Error", "probability": "Medium", "impact": "High"}
        ]

    def _identify_critical_assumptions(self, context: Dict) -> List[str]:
        """Identify critical assumptions"""
        return [
            "Supplier reliability maintained",
            "No major demand shocks",
            "Forecast model remains valid"
        ]

    def _perform_sensitivity(self, quantity: int, context: Dict) -> Dict:
        """Perform sensitivity analysis"""
        return {
            "demand_10pct_higher": {"impact": "Moderate", "mitigation": "Increase safety stock"},
            "lead_time_doubles": {"impact": "Severe", "mitigation": "Emergency expedite options"},
            "cost_increase_20pct": {"impact": "Low", "mitigation": "Acceptable within budget"}
        }

    def _analyze_disagreement(
        self,
        decision: str,
        agent_qty: int,
        human_qty: Optional[int],
        agent_rationale: str,
        human_rationale: str
    ) -> Dict:
        """Analyze why human disagreed with agent"""
        if decision == "accept":
            return None

        disagreement = {
            "decision_type": decision,
            "quantity_delta": (human_qty - agent_qty) if human_qty else None,
            "agent_perspective": agent_rationale,
            "human_perspective": human_rationale,
            "potential_learning": self._extract_learning_signals(
                agent_qty,
                human_qty,
                agent_rationale,
                human_rationale
            )
        }

        return disagreement

    def _extract_learning_signals(
        self,
        agent_qty: int,
        human_qty: Optional[int],
        agent_rationale: str,
        human_rationale: str
    ) -> List[str]:
        """Extract learning signals from human disagreement"""
        signals = []

        if human_qty and human_qty > agent_qty:
            signals.append("Human prefers higher service level / lower stockout risk")
        elif human_qty and human_qty < agent_qty:
            signals.append("Human prefers lower inventory cost / tighter inventory control")

        # Could add NLP analysis of rationale text here

        return signals

    # Trade-off scoring helpers
    def _score_cost(self, option: Dict, context: Dict) -> float:
        """Score cost impact (0-100, higher is better)"""
        # Simplified scoring - in production, use actual cost models
        return 75.0

    def _score_service_level(self, option: Dict, context: Dict) -> float:
        """Score service level impact (0-100, higher is better)"""
        return 85.0

    def _score_risk(self, option: Dict, context: Dict) -> float:
        """Score risk impact (0-100, higher is better/lower risk)"""
        return 70.0

    def _score_sustainability(self, option: Dict, context: Dict) -> float:
        """Score sustainability impact (0-100, higher is better)"""
        return 80.0

    def _identify_pros(self, option: Dict, context: Dict) -> List[str]:
        """Identify advantages of option"""
        return [
            "Balances cost and service level",
            "Acceptable risk profile",
            "Aligned with strategic goals"
        ]

    def _identify_cons(self, option: Dict, context: Dict) -> List[str]:
        """Identify disadvantages of option"""
        return [
            "Moderate inventory holding cost",
            "Some forecast uncertainty"
        ]
