"""
Exception Handling Policy using VFA

Learns optimal responses to MRP exceptions:
- Reschedule in/out
- Expedite
- Cancel
- Split order
- Substitute
- Escalate to planner

This implements Powell's VFA approach where exception handling
is viewed as a sequential decision problem. The agent learns
which actions minimize total cost (including escalation cost).

Phase 2: Operational Level (MRP/DRP)

References:
- Powell (2022) Sequential Decision Analytics, Chapter on Exception Handling
- MRP exception handling best practices from Kinaxis, SAP
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import logging

logger = logging.getLogger(__name__)


class ExceptionType(Enum):
    """Types of MRP/supply chain exceptions"""
    DEMAND_SPIKE = "demand_spike"
    DEMAND_DROP = "demand_drop"
    SUPPLY_DELAY = "supply_delay"
    SUPPLY_SHORTAGE = "supply_shortage"
    QUALITY_ISSUE = "quality_issue"
    CAPACITY_SHORTAGE = "capacity_shortage"
    INVENTORY_SHORTAGE = "inventory_shortage"
    INVENTORY_EXCESS = "inventory_excess"
    FORECAST_ERROR = "forecast_error"
    LEAD_TIME_CHANGE = "lead_time_change"


class ExceptionAction(Enum):
    """Possible actions to handle exceptions"""
    RESCHEDULE_IN = "reschedule_in"  # Pull order forward
    RESCHEDULE_OUT = "reschedule_out"  # Push order back
    EXPEDITE = "expedite"  # Pay premium for faster delivery
    CANCEL = "cancel"  # Cancel the order
    SPLIT_ORDER = "split_order"  # Fulfill partially
    SUBSTITUTE = "substitute"  # Use alternative product/supplier
    INCREASE_SAFETY = "increase_safety"  # Raise safety stock
    DECREASE_SAFETY = "decrease_safety"  # Lower safety stock
    ESCALATE = "escalate"  # Escalate to human planner
    NO_ACTION = "no_action"  # Exception resolves itself


class ExceptionSeverity(Enum):
    """Severity levels for exceptions"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class MRPException:
    """
    MRP exception requiring action.

    Represents an anomaly or issue detected in the planning process
    that requires a response.
    """
    exception_id: str
    exception_type: ExceptionType
    severity: ExceptionSeverity = ExceptionSeverity.MEDIUM
    severity_score: float = 0.5  # 0-1 continuous severity

    # Affected entities
    affected_quantity: float = 0.0
    affected_date: int = 0  # days from now
    affected_product_id: Optional[str] = None
    affected_site_id: Optional[str] = None
    affected_supplier_id: Optional[str] = None

    # Context
    current_inventory: float = 0.0
    current_backlog: float = 0.0
    pipeline_inventory: float = 0.0
    customer_priority: int = 3  # 1=highest

    # Financial impact
    potential_cost: float = 0.0
    potential_revenue_loss: float = 0.0

    # Metadata
    detected_at: Optional[str] = None
    description: str = ""

    def to_state_features(self) -> np.ndarray:
        """Convert to feature vector for VFA"""
        return np.array([
            self.exception_type.value.encode() if isinstance(self.exception_type.value, str) else 0,
            self.severity_score,
            self.affected_quantity,
            min(self.affected_date, 30),  # Cap at 30 days
            self.current_inventory,
            self.current_backlog,
            self.pipeline_inventory,
            self.customer_priority,
            self.potential_cost,
        ], dtype=np.float32)


@dataclass
class ExceptionResolution:
    """Result of exception handling decision"""
    exception_id: str
    action: ExceptionAction
    estimated_cost: float
    reasoning: str
    confidence: float = 0.5
    alternative_actions: List[Tuple[ExceptionAction, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exception_id": self.exception_id,
            "action": self.action.value,
            "estimated_cost": self.estimated_cost,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "alternatives": [
                {"action": a.value, "cost": c}
                for a, c in self.alternative_actions
            ]
        }


class ExceptionHandlerVFA:
    """
    Value function approximation for exception handling.

    Powell's approach: Learn Q(s, a) - the value of taking action a
    in exception state s. Over time, the agent learns which actions
    minimize total cost including:
    - Direct action cost
    - Downstream impact cost
    - Escalation cost (if escalating too often)

    State: (exception_type, severity, context features)
    Action: (reschedule, expedite, cancel, escalate, etc.)
    Reward: -cost (minimize total cost)
    """

    def __init__(
        self,
        escalation_cost: float = 100.0,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        exploration_rate: float = 0.1
    ):
        """
        Initialize exception handler VFA.

        Args:
            escalation_cost: Cost of escalating to human planner
            learning_rate: Step size for Q-learning updates
            discount_factor: Discount for future costs
            exploration_rate: Epsilon for epsilon-greedy exploration
        """
        self.escalation_cost = escalation_cost
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.exploration_rate = exploration_rate

        # Q-table: state_key -> {action: Q-value}
        self.q_table: Dict[str, Dict[str, float]] = {}

        # Action costs (base costs before state-dependent adjustments)
        self.action_base_costs = {
            ExceptionAction.RESCHEDULE_IN: 10.0,
            ExceptionAction.RESCHEDULE_OUT: 5.0,
            ExceptionAction.EXPEDITE: 50.0,
            ExceptionAction.CANCEL: 100.0,
            ExceptionAction.SPLIT_ORDER: 20.0,
            ExceptionAction.SUBSTITUTE: 30.0,
            ExceptionAction.INCREASE_SAFETY: 25.0,
            ExceptionAction.DECREASE_SAFETY: 5.0,
            ExceptionAction.ESCALATE: escalation_cost,
            ExceptionAction.NO_ACTION: 0.0,
        }

        # Track performance
        self.resolution_history: List[Dict] = []
        self.escalation_count = 0
        self.total_resolutions = 0

    def get_state_key(self, exception: MRPException) -> str:
        """
        Convert exception to discretized state key.

        Discretization allows tabular Q-learning while keeping
        reasonable state space size.
        """
        # Discretize continuous features
        severity_bucket = int(exception.severity_score * 10)
        qty_bucket = int(min(exception.affected_quantity, 1000) / 100)
        date_bucket = min(exception.affected_date, 30) // 7  # Weekly buckets
        inv_bucket = int(min(max(exception.current_inventory, -100), 500) / 50)

        return (
            f"{exception.exception_type.value}_"
            f"sev{severity_bucket}_"
            f"qty{qty_bucket}_"
            f"date{date_bucket}_"
            f"inv{inv_bucket}_"
            f"pri{exception.customer_priority}"
        )

    def get_valid_actions(self, exception: MRPException) -> List[ExceptionAction]:
        """Get valid actions for exception type"""
        # All actions start as valid
        valid = list(ExceptionAction)

        # Filter based on exception type
        if exception.exception_type == ExceptionType.DEMAND_SPIKE:
            # Can't decrease safety when demand is spiking
            valid.remove(ExceptionAction.DECREASE_SAFETY)
        elif exception.exception_type == ExceptionType.INVENTORY_EXCESS:
            # Can't increase safety or expedite when excess
            valid.remove(ExceptionAction.INCREASE_SAFETY)
            valid.remove(ExceptionAction.EXPEDITE)
        elif exception.exception_type == ExceptionType.SUPPLY_DELAY:
            # Can't reschedule in if supply is delayed
            valid.remove(ExceptionAction.RESCHEDULE_IN)

        return valid

    def get_action(
        self,
        exception: MRPException,
        explore: bool = True
    ) -> ExceptionAction:
        """
        Select action using epsilon-greedy policy.

        Args:
            exception: Exception to handle
            explore: Whether to explore (training) or exploit (inference)

        Returns:
            Selected action
        """
        state_key = self.get_state_key(exception)
        valid_actions = self.get_valid_actions(exception)

        # Initialize Q-values if not seen
        if state_key not in self.q_table:
            self.q_table[state_key] = {
                action.value: -self._estimate_initial_q(exception, action)
                for action in valid_actions
            }

        # Exploration
        if explore and np.random.random() < self.exploration_rate:
            return np.random.choice(valid_actions)

        # Exploitation (greedy)
        q_values = self.q_table[state_key]
        valid_q = {a.value: q_values.get(a.value, -1e6) for a in valid_actions}
        best_action_value = max(valid_q.keys(), key=lambda a: valid_q[a])
        return ExceptionAction(best_action_value)

    def resolve_exception(
        self,
        exception: MRPException,
        explore: bool = False
    ) -> ExceptionResolution:
        """
        Resolve exception with full reasoning.

        Returns action with cost estimates and alternatives.
        """
        state_key = self.get_state_key(exception)
        valid_actions = self.get_valid_actions(exception)

        # Get Q-values for all actions
        if state_key not in self.q_table:
            self.q_table[state_key] = {
                action.value: -self._estimate_initial_q(exception, action)
                for action in valid_actions
            }

        # Select best action
        best_action = self.get_action(exception, explore=explore)
        estimated_cost = self.compute_action_cost(exception, best_action)

        # Get alternatives
        alternatives = []
        for action in valid_actions:
            if action != best_action:
                cost = self.compute_action_cost(exception, action)
                alternatives.append((action, cost))
        alternatives.sort(key=lambda x: x[1])

        # Build reasoning
        reasoning = self._build_reasoning(exception, best_action, estimated_cost)

        # Track
        self.total_resolutions += 1
        if best_action == ExceptionAction.ESCALATE:
            self.escalation_count += 1

        return ExceptionResolution(
            exception_id=exception.exception_id,
            action=best_action,
            estimated_cost=estimated_cost,
            reasoning=reasoning,
            confidence=self._compute_confidence(state_key),
            alternative_actions=alternatives[:3],  # Top 3 alternatives
        )

    def update(
        self,
        exception: MRPException,
        action: ExceptionAction,
        actual_cost: float,
        next_exception: Optional[MRPException] = None
    ) -> float:
        """
        Q-learning update.

        Q(s,a) <- Q(s,a) + α * [reward + γ * max_a' Q(s',a') - Q(s,a)]

        Args:
            exception: Exception that was handled
            action: Action that was taken
            actual_cost: Observed cost (negative reward)
            next_exception: Next exception (for temporal learning)

        Returns:
            TD error
        """
        state_key = self.get_state_key(exception)

        # Ensure state exists in Q-table
        if state_key not in self.q_table:
            self.q_table[state_key] = {}

        # Current Q-value
        old_q = self.q_table[state_key].get(action.value, 0.0)

        # Future value
        if next_exception is not None:
            next_state_key = self.get_state_key(next_exception)
            if next_state_key in self.q_table:
                max_next_q = max(self.q_table[next_state_key].values())
            else:
                max_next_q = 0.0
        else:
            max_next_q = 0.0

        # TD target (reward is negative cost)
        td_target = -actual_cost + self.discount_factor * max_next_q

        # Update
        td_error = td_target - old_q
        self.q_table[state_key][action.value] = (
            old_q + self.learning_rate * td_error
        )

        # Record for analysis
        self.resolution_history.append({
            "state_key": state_key,
            "action": action.value,
            "cost": actual_cost,
            "td_error": td_error,
        })

        return td_error

    def compute_action_cost(
        self,
        exception: MRPException,
        action: ExceptionAction
    ) -> float:
        """
        Estimate cost of taking action.

        Combines base action cost with state-dependent factors.
        """
        base_cost = self.action_base_costs.get(action, 50.0)

        # State-dependent adjustments
        if action == ExceptionAction.ESCALATE:
            return self.escalation_cost

        elif action == ExceptionAction.EXPEDITE:
            # Expediting is more expensive for larger quantities
            return base_cost + exception.affected_quantity * 0.5

        elif action == ExceptionAction.CANCEL:
            # Cancellation cost depends on customer priority
            priority_multiplier = 6 - exception.customer_priority  # 1->5, 5->1
            return base_cost * priority_multiplier + exception.potential_revenue_loss

        elif action == ExceptionAction.RESCHEDULE_IN:
            # Pulling forward costs more for distant dates
            return base_cost + exception.affected_date * 2

        elif action == ExceptionAction.RESCHEDULE_OUT:
            # Pushing back is cheaper but has downstream cost
            return base_cost + exception.current_backlog * 0.5

        elif action == ExceptionAction.SUBSTITUTE:
            # Substitution cost based on quantity
            return base_cost + exception.affected_quantity * 0.2

        elif action == ExceptionAction.SPLIT_ORDER:
            # Partial fulfillment overhead
            return base_cost + 10

        elif action == ExceptionAction.INCREASE_SAFETY:
            # Holding cost increase
            return base_cost + exception.affected_quantity * 0.1

        elif action == ExceptionAction.DECREASE_SAFETY:
            # Risk cost (potential future stockout)
            return base_cost + exception.severity_score * 20

        elif action == ExceptionAction.NO_ACTION:
            # Cost of doing nothing depends on severity
            return exception.potential_cost * exception.severity_score

        return base_cost

    def _estimate_initial_q(
        self,
        exception: MRPException,
        action: ExceptionAction
    ) -> float:
        """Estimate initial Q-value (cost) for unseen state-action pair"""
        return self.compute_action_cost(exception, action)

    def _compute_confidence(self, state_key: str) -> float:
        """Compute confidence based on visit count"""
        if state_key not in self.q_table:
            return 0.1

        # More visits = higher confidence
        history_matches = sum(
            1 for h in self.resolution_history
            if h["state_key"] == state_key
        )
        return min(0.95, 0.3 + history_matches * 0.05)

    def _build_reasoning(
        self,
        exception: MRPException,
        action: ExceptionAction,
        estimated_cost: float
    ) -> str:
        """Build human-readable reasoning for action selection"""
        reasons = []

        reasons.append(f"Exception type: {exception.exception_type.value}")
        reasons.append(f"Severity: {exception.severity.name} ({exception.severity_score:.2f})")
        reasons.append(f"Affected quantity: {exception.affected_quantity:.0f}")

        if action == ExceptionAction.EXPEDITE:
            reasons.append(f"Expediting recommended due to urgency (date: {exception.affected_date} days)")
        elif action == ExceptionAction.ESCALATE:
            reasons.append("Escalating due to high complexity or severity")
        elif action == ExceptionAction.RESCHEDULE_IN:
            reasons.append(f"Pulling forward to meet demand (inventory: {exception.current_inventory:.0f})")
        elif action == ExceptionAction.NO_ACTION:
            reasons.append("Exception expected to self-resolve")

        reasons.append(f"Estimated cost: ${estimated_cost:.2f}")

        return " | ".join(reasons)

    def get_escalation_rate(self) -> float:
        """Get current escalation rate"""
        if self.total_resolutions == 0:
            return 0.0
        return self.escalation_count / self.total_resolutions

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of handler performance"""
        if not self.resolution_history:
            return {"status": "no_data"}

        costs = [h["cost"] for h in self.resolution_history]
        td_errors = [h["td_error"] for h in self.resolution_history]

        return {
            "total_resolutions": self.total_resolutions,
            "escalation_rate": self.get_escalation_rate(),
            "avg_cost": float(np.mean(costs)),
            "std_cost": float(np.std(costs)),
            "avg_td_error": float(np.mean(td_errors[-100:])) if td_errors else 0,
            "unique_states": len(self.q_table),
            "learning_rate": self.learning_rate,
            "exploration_rate": self.exploration_rate,
        }
