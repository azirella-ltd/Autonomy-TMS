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

from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser
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
    scenario_user_id: int
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
    scenario_user_id: int
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
    - Validate mode switches based on scenario state
    - Record mode history for RLHF training
    - Broadcast mode change notifications
    - Apply transition rules and constraints
    """

    def __init__(self, db: Session):
        self.db = db

    def switch_agent_mode(
        self,
        scenario_user_id: int,
        scenario_id: int,
        new_mode: AgentMode,
        reason: ModeSwitchReason,
        triggered_by: str = "user",
        force: bool = False
    ) -> ModeSwitchResult:
        """
        Switch scenario_user's agent mode during active gameplay.

        Args:
            scenario_user_id: ScenarioUser to switch mode for
            scenario_id: Scenario context
            new_mode: Target agent mode
            reason: Reason for switch
            triggered_by: Who initiated switch (user, system, agent)
            force: Skip validation checks if True

        Returns:
            ModeSwitchResult with success status and details

        Raises:
            ValueError: If scenario_user or scenario not found
            RuntimeError: If mode switch not allowed
        """
        # Fetch scenario_user and scenario
        scenario_user = self.db.query(ScenarioUser).filter_by(
            id=scenario_user_id, scenario_id=scenario_id
        ).first()

        if not scenario_user:
            raise ValueError(f"ScenarioUser {scenario_user_id} not found in scenario {scenario_id}")

        scenario = self.db.query(Scenario).filter_by(id=scenario_id).first()
        if not scenario:
            raise ValueError(f"Scenario {scenario_id} not found")

        # Get current mode
        current_mode = scenario_user.agent_mode or AgentMode.MANUAL.value

        # Check if mode is already set
        if current_mode == new_mode.value:
            return ModeSwitchResult(
                success=True,
                previous_mode=current_mode,
                new_mode=new_mode.value,
                scenario_user_id=scenario_user_id,
                scenario_id=scenario_id,
                round_number=scenario.current_period,
                reason=reason.value,
                message=f"Mode already set to {new_mode.value}",
                timestamp=datetime.utcnow().isoformat(),
                warnings=["No change needed - mode already active"]
            )

        # Validate mode switch (unless forced)
        if not force:
            validation_result = self.validate_mode_switch(
                scenario_user=scenario_user,
                scenario=scenario,
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
            scenario_user_id=scenario_user_id,
            scenario_id=scenario_id,
            round_number=scenario.current_period,
            previous_mode=current_mode,
            new_mode=new_mode.value,
            reason=reason.value,
            triggered_by=triggered_by
        )

        # Update scenario_user mode
        scenario_user.agent_mode = new_mode.value
        self.db.commit()

        # Generate warnings based on mode transition
        warnings = self._generate_transition_warnings(
            current_mode=AgentMode(current_mode),
            new_mode=new_mode,
            scenario=scenario
        )

        return ModeSwitchResult(
            success=True,
            previous_mode=current_mode,
            new_mode=new_mode.value,
            scenario_user_id=scenario_user_id,
            scenario_id=scenario_id,
            round_number=scenario.current_period,
            reason=reason.value,
            message=f"Successfully switched from {current_mode} to {new_mode.value}",
            timestamp=datetime.utcnow().isoformat(),
            warnings=warnings
        )

    def validate_mode_switch(
        self,
        scenario_user: ScenarioUser,
        scenario: Scenario,
        current_mode: AgentMode,
        new_mode: AgentMode,
        reason: ModeSwitchReason
    ) -> Dict[str, Any]:
        """
        Validate if mode switch is allowed based on scenario state and rules.

        Args:
            scenario_user: ScenarioUser to validate
            scenario: Scenario context
            current_mode: Current agent mode
            new_mode: Target agent mode
            reason: Reason for switch

        Returns:
            Dict with 'allowed' (bool) and 'reason' (str) keys
        """
        # Rule 1: Scenario must be active
        if scenario.status != "in_progress":
            return {
                "allowed": False,
                "reason": f"Scenario not active (status: {scenario.status})"
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
            if not scenario_user.agent_config_id:
                return {
                    "allowed": False,
                    "reason": "ScenarioUser has no agent_config_id set (required for autonomous mode)"
                }

        # Rule 6: System overrides bypass validation
        if reason == ModeSwitchReason.SYSTEM_OVERRIDE:
            return {"allowed": True, "reason": "System override approved"}

        # All checks passed
        return {"allowed": True, "reason": "Validation successful"}

    def get_mode_history(
        self,
        scenario_user_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        limit: int = 50
    ) -> List[ModeHistory]:
        """
        Retrieve mode switch history.

        Args:
            scenario_user_id: Filter by scenario_user (optional)
            scenario_id: Filter by scenario (optional)
            limit: Max records to return

        Returns:
            List of ModeHistory records
        """
        query = self.db.query(AgentModeHistory)

        if scenario_user_id:
            query = query.filter_by(scenario_user_id=scenario_user_id)
        if scenario_id:
            query = query.filter_by(scenario_id=scenario_id)

        query = query.order_by(AgentModeHistory.timestamp.desc()).limit(limit)

        records = query.all()

        return [
            ModeHistory(
                id=record.id,
                scenario_user_id=record.scenario_user_id,
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
        Get count of scenario_users in each mode for a scenario.

        Args:
            scenario_id: Scenario to analyze

        Returns:
            Dict with mode counts: {"manual": 2, "copilot": 1, "autonomous": 1}
        """
        scenario_users = self.db.query(ScenarioUser).filter_by(scenario_id=scenario_id).all()

        distribution = {
            AgentMode.MANUAL.value: 0,
            AgentMode.COPILOT.value: 0,
            AgentMode.AUTONOMOUS.value: 0
        }

        for scenario_user in scenario_users:
            mode = scenario_user.agent_mode or AgentMode.MANUAL.value
            distribution[mode] += 1

        return distribution

    def suggest_mode_switch(
        self,
        scenario_user: ScenarioUser,
        scenario: Scenario,
        performance_metrics: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest mode switch based on performance metrics (proactive).

        Args:
            scenario_user: ScenarioUser to analyze
            scenario: Scenario context
            performance_metrics: Dict with service_level, cost, inventory_turns, etc.

        Returns:
            Suggestion dict with recommended_mode, reason, confidence
            None if no switch recommended
        """
        current_mode = AgentMode(scenario_user.agent_mode or AgentMode.MANUAL.value)

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
        scenario_user_id: int,
        scenario_id: int,
        round_number: int,
        previous_mode: str,
        new_mode: str,
        reason: str,
        triggered_by: str
    ):
        """Record mode switch in history table."""
        history_record = AgentModeHistory(
            scenario_user_id=scenario_user_id,
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
        scenario: Scenario
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

        if scenario.current_period < 5:
            warnings.append(
                f"Early in scenario (Round {scenario.current_period}/52). "
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
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id"), nullable=False, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
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
