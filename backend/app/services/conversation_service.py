"""
Conversation Service for Multi-Turn AI Chat
Phase 7 Sprint 4 - Advanced A2A Features

Manages conversation history, context building, and multi-turn interactions
with LLM-powered AI assistant.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from sqlalchemy.orm import selectinload

from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser

# Aliases for backwards compatibility
Game = Scenario
ScenarioUser = ScenarioUser
from app.services.llm_suggestion_service import get_llm_service

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing multi-turn conversations with AI assistant."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.max_context_messages = 10  # Keep last 10 messages in context
        self.context_summary_threshold = 20  # Summarize if > 20 messages

    async def send_message(
        self,
        scenario_id: int,
        scenario_user_id: int,
        message: str,
        parent_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a message in conversation and get AI response.

        Args:
            scenario_id: Game ID
            scenario_user_id: ScenarioUser ID
            message: User message content
            parent_message_id: Optional parent message for threading

        Returns:
            Dict containing user message and AI response
        """
        try:
            # Get game and scenario_user
            game = await self._get_game(scenario_id)
            scenario_user = await self._get_scenario_user(scenario_user_id)

            # Get conversation history
            history = await self.get_conversation_history(
                scenario_id, scenario_user_id, limit=self.max_context_messages
            )

            # Build context snapshot
            context_snapshot = await self._build_context_snapshot(game, scenario_user)

            # Save user message
            user_message = await self._save_message(
                scenario_id=scenario_id,
                scenario_user_id=scenario_user_id,
                role="user",
                content=message,
                context=context_snapshot,
                parent_message_id=parent_message_id,
            )

            # Build LLM prompt with conversation history
            llm_prompt = self._build_conversation_prompt(
                message=message,
                history=history,
                context=context_snapshot,
                scenario_user_role=scenario_user.role,
            )

            # Get AI response
            llm_service = get_llm_service()
            ai_response = await llm_service.generate_conversation_response(
                prompt=llm_prompt,
                context=context_snapshot,
            )

            # Save AI message
            assistant_message = await self._save_message(
                scenario_id=scenario_id,
                scenario_user_id=scenario_user_id,
                role="assistant",
                content=ai_response["content"],
                context={
                    "confidence": ai_response.get("confidence", 0.8),
                    "reasoning": ai_response.get("reasoning", []),
                    "suggested_action": ai_response.get("suggested_action"),
                },
                parent_message_id=user_message["id"],
            )

            return {
                "user_message": user_message,
                "assistant_message": assistant_message,
                "conversation_id": user_message["id"],
            }

        except Exception as e:
            logger.error(f"Failed to send message: {e}", exc_info=True)
            raise

    async def get_conversation_history(
        self,
        scenario_id: int,
        scenario_user_id: int,
        limit: int = 50,
        include_context: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a scenario_user in a game.

        Args:
            scenario_id: Game ID
            scenario_user_id: ScenarioUser ID
            limit: Maximum number of messages
            include_context: Whether to include full context snapshots

        Returns:
            List of message dictionaries
        """
        # In a real implementation, this would query conversation_messages table
        # For now, we'll return empty list and implement when table is created
        logger.info(f"Getting conversation history for game {scenario_id}, scenario_user {scenario_user_id}")
        return []

    async def clear_conversation(self, scenario_id: int, scenario_user_id: int) -> bool:
        """
        Clear conversation history for a scenario_user.

        Args:
            scenario_id: Game ID
            scenario_user_id: ScenarioUser ID

        Returns:
            True if successful
        """
        # Implementation will mark messages as deleted or archive them
        logger.info(f"Clearing conversation for game {scenario_id}, scenario_user {scenario_user_id}")
        return True

    async def get_conversation_summary(
        self, scenario_id: int, scenario_user_id: int
    ) -> Dict[str, Any]:
        """
        Get conversation summary with key metrics.

        Args:
            scenario_id: Game ID
            scenario_user_id: ScenarioUser ID

        Returns:
            Summary dict with stats
        """
        history = await self.get_conversation_history(scenario_id, scenario_user_id)

        user_messages = [m for m in history if m["role"] == "user"]
        assistant_messages = [m for m in history if m["role"] == "assistant"]

        return {
            "total_messages": len(history),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages),
            "conversation_started": history[0]["created_at"] if history else None,
            "last_message": history[-1]["created_at"] if history else None,
        }

    def _build_conversation_prompt(
        self,
        message: str,
        history: List[Dict[str, Any]],
        context: Dict[str, Any],
        scenario_user_role: str,
    ) -> str:
        """Build LLM prompt with conversation history."""

        # Build conversation context
        conversation_context = ""
        if history:
            conversation_context = "\n\nPrevious conversation:\n"
            for msg in history[-5:]:  # Last 5 messages for context
                role = "You" if msg["role"] == "assistant" else "ScenarioUser"
                conversation_context += f"{role}: {msg['content']}\n"

        prompt = f"""You are an AI supply chain advisor for the {scenario_user_role} role.
The scenario_user is asking: "{message}"

{conversation_context}

Current Game State:
- Round: {context.get('current_round', 0)}
- Inventory: {context.get('current_inventory', 0)} units
- Backlog: {context.get('current_backlog', 0)} units
- Incoming Shipment: {context.get('incoming_shipment', 0)} units
- Recent Demand: {context.get('recent_demand', [])}

Provide a helpful, conversational response that:
1. Directly answers their question
2. References previous conversation if relevant
3. Provides actionable insights
4. Suggests follow-up questions they might ask

Respond in JSON format:
{{
    "content": "<your conversational response>",
    "confidence": <float 0.0-1.0>,
    "reasoning": ["<step 1>", "<step 2>"],
    "suggested_action": {{"type": "order", "quantity": <int>}} or null,
    "follow_up_questions": ["<question 1>", "<question 2>"]
}}"""
        return prompt

    async def _build_context_snapshot(
        self, game: Game, scenario_user: ScenarioUser
    ) -> Dict[str, Any]:
        """Build game context snapshot for this conversation turn."""

        # Get current scenario_user round data
        from app.models.supply_chain import ScenarioUserPeriod

        result = await self.db.execute(
            select(ScenarioUserPeriod)
            .filter(
                and_(
                    ScenarioUserPeriod.scenario_user_id == scenario_user.id,
                    ScenarioUserPeriod.round == game.current_round
                )
            )
        )
        current_round = result.scalars().first()

        # Get recent rounds for demand history
        history_result = await self.db.execute(
            select(ScenarioUserPeriod)
            .filter(ScenarioUserPeriod.scenario_user_id == scenario_user.id)
            .order_by(desc(ScenarioUserPeriod.round))
            .limit(10)
        )
        recent_rounds = list(history_result.scalars().all())

        recent_demand = [r.demand for r in reversed(recent_rounds) if r.demand]

        return {
            "scenario_id": game.id,
            "scenario_user_id": scenario_user.id,
            "current_round": game.current_round,
            "current_inventory": current_round.current_inventory if current_round else 0,
            "current_backlog": current_round.current_backlog if current_round else 0,
            "incoming_shipment": current_round.incoming_shipment if current_round else 0,
            "recent_demand": recent_demand,
            "scenario_user_role": scenario_user.role,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _save_message(
        self,
        scenario_id: int,
        scenario_user_id: int,
        role: str,
        content: str,
        context: Dict[str, Any],
        parent_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Save a conversation message."""

        # In production, this would insert into conversation_messages table
        # For now, return a mock message structure
        message = {
            "id": 1,  # Would be auto-generated
            "scenario_id": scenario_id,
            "scenario_user_id": scenario_user_id,
            "parent_message_id": parent_message_id,
            "role": role,
            "content": content,
            "context": context,
            "created_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Saved {role} message for scenario_user {scenario_user_id} in game {scenario_id}")
        return message

    async def _get_game(self, scenario_id: int) -> Game:
        """Get game by ID."""
        result = await self.db.execute(
            select(Game).filter(Game.id == scenario_id)
        )
        game = result.scalars().first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")
        return game

    async def _get_scenario_user(self, scenario_user_id: int) -> ScenarioUser:
        """Get scenario_user by ID."""
        result = await self.db.execute(
            select(ScenarioUser).filter(ScenarioUser.id == scenario_user_id)
        )
        scenario_user = result.scalars().first()
        if not scenario_user:
            raise ValueError(f"ScenarioUser {scenario_user_id} not found")
        return scenario_user


# Singleton service instance
_conversation_service_instance = None


def get_conversation_service(db: AsyncSession) -> ConversationService:
    """Get or create conversation service instance."""
    return ConversationService(db)
