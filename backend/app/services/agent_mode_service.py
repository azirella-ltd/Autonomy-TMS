"""
Agent Mode Service

Phase 4: Multi-Agent Orchestration
Handles dynamic switching between agent modes (manual, copilot, autonomous)
during active gameplay.

Features:
- Mode switching with validation
- Mode history tracking
- State transition rules
- WebSocket notifications for mode changes
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from sqlalchemy.orm import Session

from app.models.participant import Participant
from app.models.scenario import Scenario

# Aliases for backwards compatibility
Player = Participant
Game = Scenario
from app.services.llm_agent import LLMAgent as LLMAgentWrapper


class AgentMode(str, Enum):
    """Agent operation modes."""
    MANUAL = "manual"
    COPILOT = "copilot"
    AUTONOMOUS = "autonomous"


class ModeSwitchReason(str, Enum):
    """Reasons for mode switch."""
    USER_REQUEST = "user_request"
    PERFORMANCE_THRESHOLD = "performance_threshold"
    SYSTEM_OVERRIDE = "system_override"
    LEARNING_OPPORTUNITY = "learning_opportunity"
    TESTING = "testing"


@dataclass
class ModeSwitchResult:
    """Result of mode switch operation."""
    success: bool
    previous_mode: str
    new_mode: str
    player_id: int
    scenario_id: int
    round_number: int
    reason: str
    message: str
    timestamp: str
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class ModeHistory:
    """Historical record of mode switches."""
    id: int
    player_id: int
    scenario_id: int
    round_number: int
    previous_mode: str
    new_mode: str
    reason: str
    triggered_by: str  # "user", "system", "agent"
    timestamp: str
    switch_metadata: Optional[Dict[str, Any]] = None


class AgentModeService:
    """
    Service for managing dynamic agent mode switching.

    Responsibilities:
    - Validate mode switches based on game state
    - Record mode history for RLHF training
    - Broadcast mode change notifications
    - Apply transition rules and constraints
    """

    def __init__(self, db: Session):
        self.db = db

    def switch_agent_mode(
        self,
        player_id: int,
        scenario_id: int,
        new_mode: AgentMode,
        reason: ModeSwitchReason,
        triggered_by: str = "user",
        force: bool = False
    ) -> ModeSwitchResult:
        """
        Switch player's agent mode during active gameplay.

        Args:
            player_id: Player to switch mode for
            scenario_id: Game context
            new_mode: Target agent mode
            reason: Reason for switch
            triggered_by: Who initiated switch (user, system, agent)
            force: Skip validation checks if True

        Returns:
            ModeSwitchResult with success status and details

        Raises:
            ValueError: If player or game not found
            RuntimeError: If mode switch not allowed
        """
        # Fetch player and game
        player = self.db.query(Player).filter_by(
            id=player_id, scenario_id=scenario_id
        ).first()

        if not player:
            raise ValueError(f"Player {player_id} not found in game {scenario_id}")

        game = self.db.query(Game).filter_by(id=scenario_id).first()
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        # Get current mode
        current_mode = player.agent_mode or AgentMode.MANUAL.value

        # Check if mode is already set
        if current_mode == new_mode.value:
            return ModeSwitchResult(
                success=True,
                previous_mode=current_mode,
                new_mode=new_mode.value,
                player_id=player_id,
                scenario_id=scenario_id,
                round_number=game.current_round,
                reason=reason.value,
                message=f"Mode already set to {new_mode.value}",
                timestamp=datetime.utcnow().isoformat(),
                warnings=["No change needed - mode already active"]
            )

        # Validate mode switch (unless forced)
        if not force:
            validation_result = self.validate_mode_switch(
                player=player,
                game=game,
                current_mode=AgentMode(current_mode),
                new_mode=new_mode,
                reason=reason
            )

            if not validation_result["allowed"]:
                raise RuntimeError(
                    f"Mode switch not allowed: {validation_result['reason']}"
                )

        # Record mode history BEFORE switching
        self._record_mode_history(
            player_id=player_id,
            scenario_id=scenario_id,
            round_number=game.current_round,
            previous_mode=current_mode,
            new_mode=new_mode.value,
            reason=reason.value,
            triggered_by=triggered_by
        )

        # Update player mode
        player.agent_mode = new_mode.value
        self.db.commit()

        # Generate warnings based on mode transition
        warnings = self._generate_transition_warnings(
            current_mode=AgentMode(current_mode),
            new_mode=new_mode,
            game=game
        )

        return ModeSwitchResult(
            success=True,
            previous_mode=current_mode,
            new_mode=new_mode.value,
            player_id=player_id,
            scenario_id=scenario_id,
            round_number=game.current_round,
            reason=reason.value,
            message=f"Successfully switched from {current_mode} to {new_mode.value}",
            timestamp=datetime.utcnow().isoformat(),
            warnings=warnings
        )

    def validate_mode_switch(
        self,
        player: Player,
        game: Game,
        current_mode: AgentMode,
        new_mode: AgentMode,
        reason: ModeSwitchReason
    ) -> Dict[str, Any]:
        """
        Validate if mode switch is allowed based on game state and rules.

        Args:
            player: Player to validate
            game: Game context
            current_mode: Current agent mode
            new_mode: Target agent mode
            reason: Reason for switch

        Returns:
            Dict with 'allowed' (bool) and 'reason' (str) keys
        """
        # Rule 1: Game must be active
        if game.status != "in_progress":
            return {
                "allowed": False,
                "reason": f"Game not active (status: {game.status})"
            }

        # Rule 2: Cannot switch during round processing
        # (This would require checking if round is being processed - omitted for now)

        # Rule 3: Manual → Copilot → Autonomous (progressive learning)
        # Allow switching in any direction for flexibility
        # (Original plan was to enforce progression, but users may want to step back)

        # Rule 4: Copilot mode requires LLM agent availability
        if new_mode == AgentMode.COPILOT:
            # Check if LLM agent is configured
            try:
                llm_wrapper = LLMAgentWrapper()
                if not llm_wrapper.is_available():
                    return {
                        "allowed": False,
                        "reason": "LLM agent not available for copilot mode"
                    }
            except Exception as e:
                return {
                    "allowed": False,
                    "reason": f"LLM agent initialization failed: {str(e)}"
                }

        # Rule 5: Autonomous mode requires agent_config_id
        if new_mode == AgentMode.AUTONOMOUS:
            if not player.agent_config_id:
                return {
                    "allowed": False,
                    "reason": "Player has no agent_config_id set (required for autonomous mode)"
                }

        # Rule 6: System overrides bypass validation
        if reason == ModeSwitchReason.SYSTEM_OVERRIDE:
            return {"allowed": True, "reason": "System override approved"}

        # All checks passed
        return {"allowed": True, "reason": "Validation successful"}

    def get_mode_history(
        self,
        player_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        limit: int = 50
    ) -> List[ModeHistory]:
        """
        Retrieve mode switch history.

        Args:
            player_id: Filter by player (optional)
            scenario_id: Filter by game (optional)
            limit: Max records to return

        Returns:
            List of ModeHistory records
        """
        query = self.db.query(AgentModeHistory)

        if player_id:
            query = query.filter_by(player_id=player_id)
        if scenario_id:
            query = query.filter_by(scenario_id=scenario_id)

        query = query.order_by(AgentModeHistory.timestamp.desc()).limit(limit)

        records = query.all()

        return [
            ModeHistory(
                id=record.id,
                player_id=record.player_id,
                scenario_id=record.scenario_id,
                round_number=record.round_number,
                previous_mode=record.previous_mode,
                new_mode=record.new_mode,
                reason=record.reason,
                triggered_by=record.triggered_by,
                timestamp=record.timestamp.isoformat(),
                metadata=record.switch_metadata
            )
            for record in records
        ]

    def get_current_mode_distribution(self, scenario_id: int) -> Dict[str, int]:
        """
        Get count of players in each mode for a game.

        Args:
            scenario_id: Game to analyze

        Returns:
            Dict with mode counts: {"manual": 2, "copilot": 1, "autonomous": 1}
        """
        players = self.db.query(Player).filter_by(scenario_id=scenario_id).all()

        distribution = {
            AgentMode.MANUAL.value: 0,
            AgentMode.COPILOT.value: 0,
            AgentMode.AUTONOMOUS.value: 0
        }

        for player in players:
            mode = player.agent_mode or AgentMode.MANUAL.value
            distribution[mode] += 1

        return distribution

    def suggest_mode_switch(
        self,
        player: Player,
        game: Game,
        performance_metrics: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest mode switch based on performance metrics (proactive).

        Args:
            player: Player to analyze
            game: Game context
            performance_metrics: Dict with service_level, cost, inventory_turns, etc.

        Returns:
            Suggestion dict with recommended_mode, reason, confidence
            None if no switch recommended
        """
        current_mode = AgentMode(player.agent_mode or AgentMode.MANUAL.value)

        # Thresholds for suggestions
        POOR_SERVICE_LEVEL = 0.75  # Below 75% fill rate
        HIGH_COST = 10000  # Cumulative cost threshold
        HIGH_INVENTORY_VARIANCE = 200  # Excessive inventory fluctuation

        # Analyze metrics
        service_level = performance_metrics.get("service_level", 1.0)
        cumulative_cost = performance_metrics.get("cumulative_cost", 0)
        inventory_variance = performance_metrics.get("inventory_variance", 0)

        # Suggestion logic
        if current_mode == AgentMode.MANUAL:
            # Suggest copilot if struggling
            if service_level < POOR_SERVICE_LEVEL or cumulative_cost > HIGH_COST:
                return {
                    "recommended_mode": AgentMode.COPILOT.value,
                    "reason": "Performance below target - AI assistance recommended",
                    "confidence": 0.8,
                    "metrics": {
                        "service_level": service_level,
                        "cumulative_cost": cumulative_cost
                    }
                }

        elif current_mode == AgentMode.COPILOT:
            # Suggest autonomous if consistently accepting AI recommendations
            # (Would require tracking accept/reject ratio - not implemented yet)
            pass

        elif current_mode == AgentMode.AUTONOMOUS:
            # Suggest manual if AI performance is poor
            if service_level < POOR_SERVICE_LEVEL:
                return {
                    "recommended_mode": AgentMode.MANUAL.value,
                    "reason": "Autonomous agent underperforming - manual override suggested",
                    "confidence": 0.7,
                    "metrics": {
                        "service_level": service_level
                    }
                }

        return None

    def _record_mode_history(
        self,
        player_id: int,
        scenario_id: int,
        round_number: int,
        previous_mode: str,
        new_mode: str,
        reason: str,
        triggered_by: str
    ):
        """Record mode switch in history table."""
        history_record = AgentModeHistory(
            player_id=player_id,
            scenario_id=scenario_id,
            round_number=round_number,
            previous_mode=previous_mode,
            new_mode=new_mode,
            reason=reason,
            triggered_by=triggered_by,
            timestamp=datetime.utcnow()
        )
        self.db.add(history_record)
        self.db.commit()

    def _generate_transition_warnings(
        self,
        current_mode: AgentMode,
        new_mode: AgentMode,
        game: Game
    ) -> List[str]:
        """Generate warnings for mode transition."""
        warnings = []

        if current_mode == AgentMode.MANUAL and new_mode == AgentMode.AUTONOMOUS:
            warnings.append(
                "Switching directly from manual to autonomous. "
                "Consider using copilot mode first for guided learning."
            )

        if new_mode == AgentMode.COPILOT:
            warnings.append(
                "Copilot mode provides AI suggestions. "
                "You can accept, modify, or reject each recommendation."
            )

        if new_mode == AgentMode.AUTONOMOUS:
            warnings.append(
                "Autonomous mode: AI agent will make all decisions. "
                "You can observe and override if needed."
            )

        if game.current_round < 5:
            warnings.append(
                f"Early in game (Round {game.current_round}/52). "
                "AI agents perform better with more historical data."
            )

        return warnings


# Database model for mode history
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from app.models.base import Base


class AgentModeHistory(Base):
    """
    Tracks history of agent mode switches for RLHF training.

    This data is used to:
    - Analyze when and why users switch modes
    - Train agents to recognize when to suggest mode switches
    - Generate training data for RLHF fine-tuning
    """
    __tablename__ = "agent_mode_history"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    scenario_id = Column(Integer, ForeignKey("games.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False)
    previous_mode = Column(String(20), nullable=False)  # manual, copilot, autonomous
    new_mode = Column(String(20), nullable=False)
    reason = Column(String(50), nullable=False)  # user_request, performance_threshold, etc.
    triggered_by = Column(String(20), nullable=False)  # user, system, agent
    timestamp = Column(DateTime, nullable=False, index=True)
    switch_metadata = Column(JSON, nullable=True)  # Additional context (performance metrics, etc.)


# Dependency injection
from fastapi import Depends
from app.db.session import get_db

def get_agent_mode_service(db: Session = Depends(get_db)) -> AgentModeService:
    """FastAPI dependency for AgentModeService."""
    return AgentModeService(db)
