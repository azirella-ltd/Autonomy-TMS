"""
Value Function Approximation (VFA) for Powell Framework

Wraps TRM agent with explicit value function semantics:
- Post-decision state formulation
- Temporal difference updates
- Exploration via knowledge gradient or UCB

This is Phase 1 of the Powell implementation focusing on Execution level.

Powell's VFA Framework:
- V(Sˣ): Value of post-decision state (after decision x but before exogenous info W)
- Q(S,x): Value of taking action x in pre-decision state S
- TD Learning: Update V based on observed transitions

References:
- Powell (2022) Sequential Decision Analytics, Chapter 6-8
- Powell (2011) Approximate Dynamic Programming, Chapters on VFA
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Tuple, List, Union
import numpy as np
import logging

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class PostDecisionState:
    """
    Post-decision state (Sˣ) after decision x but before exogenous info W

    In supply chain context:
    - inventory_position: inventory + on_order - backlog (after ordering)
    - time_until_next_decision: periods until next decision point

    Powell's formulation separates:
    - Pre-decision state S_t: state before making decision
    - Post-decision state S^x_t: state after decision, before new info arrives
    """
    inventory_position: float
    pipeline_inventory: float
    expected_demand: float
    demand_uncertainty: float  # From conformal prediction
    time_index: int
    node_id: Optional[str] = None
    node_type: Optional[str] = None

    # Additional context for multi-node supply chains
    upstream_inventory: Optional[float] = None
    downstream_backlog: Optional[float] = None

    def to_tensor(self) -> 'torch.Tensor':
        """Convert to PyTorch tensor for neural network input"""
        if not TORCH_AVAILABLE:
            raise RuntimeError("PyTorch not available")

        features = [
            self.inventory_position,
            self.pipeline_inventory,
            self.expected_demand,
            self.demand_uncertainty,
            float(self.time_index),
        ]

        # Add optional features if available
        if self.upstream_inventory is not None:
            features.append(self.upstream_inventory)
        if self.downstream_backlog is not None:
            features.append(self.downstream_backlog)

        return torch.tensor(features, dtype=torch.float32)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "inventory_position": self.inventory_position,
            "pipeline_inventory": self.pipeline_inventory,
            "expected_demand": self.expected_demand,
            "demand_uncertainty": self.demand_uncertainty,
            "time_index": self.time_index,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "upstream_inventory": self.upstream_inventory,
            "downstream_backlog": self.downstream_backlog,
        }


class ValueFunctionApproximator:
    """
    VFA wrapper for TRM agent with Powell semantics

    This class wraps any neural network model (like TRM) and provides
    Powell-compliant value function operations:
    - V(Sˣ): Value of post-decision state
    - Q(S, x): Action-value function
    - TD updates for online learning
    """

    def __init__(
        self,
        model: Any = None,
        gamma: float = 0.99,
        learning_rate: float = 0.01,
        exploration_bonus: float = 0.1,
    ):
        """
        Initialize VFA wrapper.

        Args:
            model: Neural network model (TRM or similar) with get_value() method
            gamma: Discount factor for future rewards
            learning_rate: Step size for TD updates
            exploration_bonus: Exploration bonus coefficient (UCB-style)
        """
        self.model = model
        self.gamma = gamma
        self.learning_rate = learning_rate
        self.exploration_bonus = exploration_bonus

        # Tracking for convergence monitoring
        self.td_errors: List[float] = []
        self.update_count = 0

        # Visit counts for exploration (UCB-style)
        self.state_visits: Dict[str, int] = {}

        # Tabular fallback for small state spaces
        self.value_table: Dict[str, float] = {}

    def compute_value(self, state: PostDecisionState) -> float:
        """
        Compute V(Sˣ) - value of post-decision state

        If neural network available, use it. Otherwise fall back to tabular.
        """
        if self.model is not None and TORCH_AVAILABLE:
            try:
                with torch.no_grad():
                    features = state.to_tensor().unsqueeze(0)
                    if hasattr(self.model, 'get_value'):
                        value = self.model.get_value(features)
                    elif hasattr(self.model, 'forward'):
                        # Assume model outputs [action_logits, value]
                        output = self.model(features)
                        if isinstance(output, tuple):
                            value = output[1]
                        else:
                            value = output
                    else:
                        value = self._tabular_value(state)
                        return float(value)

                    return float(value.item() if hasattr(value, 'item') else value)
            except Exception as e:
                logger.warning(f"Model inference failed, using tabular: {e}")
                return self._tabular_value(state)
        else:
            return self._tabular_value(state)

    def _tabular_value(self, state: PostDecisionState) -> float:
        """Tabular value function fallback"""
        state_key = self._discretize_state(state)
        return self.value_table.get(state_key, 0.0)

    def _discretize_state(self, state: PostDecisionState) -> str:
        """Discretize continuous state for tabular storage"""
        # Round to reduce state space
        inv_bucket = int(state.inventory_position / 10) * 10
        pipe_bucket = int(state.pipeline_inventory / 10) * 10
        dem_bucket = int(state.expected_demand / 10) * 10
        return f"{inv_bucket}_{pipe_bucket}_{dem_bucket}_{state.time_index % 52}"

    def compute_q_value(self, state: Dict[str, Any], action: int) -> float:
        """
        Compute Q(S, x) = C(S, x) + gamma * E[V(Sˣ)]

        Args:
            state: Pre-decision state dictionary
            action: Action (order quantity)

        Returns:
            Q-value for state-action pair
        """
        # Immediate cost
        immediate_cost = self._compute_immediate_cost(state, action)

        # Post-decision state
        post_state = self._compute_post_decision_state(state, action)

        # Expected future value
        future_value = self.compute_value(post_state)

        # Q = -cost + gamma * V (negative because we minimize cost)
        return -immediate_cost + self.gamma * future_value

    def get_best_action(
        self,
        state: Dict[str, Any],
        action_space: List[int],
        explore: bool = False
    ) -> Tuple[int, float]:
        """
        Get best action using Q-values with optional exploration.

        Args:
            state: Pre-decision state
            action_space: List of possible actions
            explore: Whether to add exploration bonus

        Returns:
            (best_action, q_value)
        """
        best_action = action_space[0]
        best_q = float('-inf')

        state_key = self._state_to_key(state)

        for action in action_space:
            q = self.compute_q_value(state, action)

            if explore:
                # UCB-style exploration bonus
                visit_key = f"{state_key}_{action}"
                visits = self.state_visits.get(visit_key, 1)
                bonus = self.exploration_bonus * np.sqrt(np.log(self.update_count + 1) / visits)
                q += bonus

            if q > best_q:
                best_q = q
                best_action = action

        return best_action, best_q

    def update_from_transition(
        self,
        pre_state: Dict[str, Any],
        action: int,
        cost: float,
        post_state: PostDecisionState,
        next_pre_state: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Temporal difference update

        TD error = C(S,x) + gamma * V(Sˣ') - V(Sˣ)

        Args:
            pre_state: State before decision
            action: Action taken
            cost: Observed cost
            post_state: Post-decision state after action
            next_pre_state: Next pre-decision state (for computing next value)

        Returns:
            TD error
        """
        # Current value estimate
        current_post_state = self._compute_post_decision_state(pre_state, action)
        current_value = self.compute_value(current_post_state)

        # TD target
        if next_pre_state is not None:
            # Get greedy action for next state
            next_action = self._get_greedy_action(next_pre_state)
            next_post_state = self._compute_post_decision_state(next_pre_state, next_action)
            next_value = self.compute_value(next_post_state)
            td_target = -cost + self.gamma * next_value
        else:
            # Terminal state
            td_target = -cost

        # TD error
        td_error = td_target - current_value
        self.td_errors.append(td_error)

        # Update tabular value (neural network updates happen via training)
        state_key = self._discretize_state(current_post_state)
        old_value = self.value_table.get(state_key, 0.0)
        self.value_table[state_key] = old_value + self.learning_rate * td_error

        # Update visit counts
        self.update_count += 1
        visit_key = f"{self._state_to_key(pre_state)}_{action}"
        self.state_visits[visit_key] = self.state_visits.get(visit_key, 0) + 1

        return td_error

    def _compute_immediate_cost(self, state: Dict[str, Any], action: int) -> float:
        """
        Compute single-period cost C(S, x)

        Standard inventory cost model:
        - Holding cost for excess inventory
        - Backlog/stockout cost for unmet demand
        - Optional: ordering cost
        """
        inventory = state.get('inventory', 0)
        backlog = state.get('backlog', 0)
        holding_cost_per_unit = state.get('holding_cost_per_unit')
        if holding_cost_per_unit is None:
            raise ValueError(
                "VFA state dict is missing 'holding_cost_per_unit'. "
                "Load this from InvPolicy.holding_cost_range['min'] (or "
                "product.unit_cost * 0.25 / 52 as fallback) for the site/product "
                "before calling _compute_immediate_cost()."
            )
        backlog_cost_per_unit = state.get('backlog_cost_per_unit')
        if backlog_cost_per_unit is None:
            raise ValueError(
                "VFA state dict is missing 'backlog_cost_per_unit'. "
                "Load this from InvPolicy.backlog_cost_range['min'] (or "
                "holding_cost_per_unit * 4 as fallback) for the site/product "
                "before calling _compute_immediate_cost()."
            )
        ordering_cost_per_unit = state.get('ordering_cost_per_unit', 0.0)

        holding_cost = holding_cost_per_unit * max(0, inventory)
        stockout_cost = backlog_cost_per_unit * backlog
        order_cost = ordering_cost_per_unit * action

        return holding_cost + stockout_cost + order_cost

    def _compute_post_decision_state(
        self,
        state: Dict[str, Any],
        action: int
    ) -> PostDecisionState:
        """
        Compute post-decision state Sˣ = Sᴹ,ˣ(S, x)

        After ordering 'action' units:
        - Inventory position increases by action (order placed)
        - Pipeline increases by action (order in transit)
        """
        inventory = state.get('inventory', 0)
        backlog = state.get('backlog', 0)
        pipeline = state.get('pipeline', [])
        if isinstance(pipeline, list):
            pipeline_total = sum(pipeline)
        else:
            pipeline_total = pipeline

        return PostDecisionState(
            inventory_position=inventory + action - backlog,
            pipeline_inventory=pipeline_total + action,
            expected_demand=state.get('forecast_mean', state.get('demand', 0)),
            demand_uncertainty=(
                state.get('forecast_p90', 0) - state.get('forecast_p10', 0)
            ) if 'forecast_p90' in state else state.get('demand_std', 10),
            time_index=state.get('period', 0),
            node_id=state.get('node_id'),
            node_type=state.get('node_type'),
        )

    def _get_greedy_action(self, state: Dict[str, Any]) -> int:
        """Get greedy action from current policy"""
        # Simple base-stock heuristic as default
        inventory = state.get('inventory', 0)
        backlog = state.get('backlog', 0)
        pipeline = state.get('pipeline', [])
        if isinstance(pipeline, list):
            pipeline_total = sum(pipeline)
        else:
            pipeline_total = pipeline

        forecast = state.get('forecast_mean', state.get('demand', 50))
        lead_time = state.get('lead_time', 2)

        # Base stock target
        target = forecast * (lead_time + 2)

        # Inventory position
        inv_position = inventory + pipeline_total - backlog

        # Order up to target
        order = max(0, int(target - inv_position))
        return order

    def _state_to_key(self, state: Dict[str, Any]) -> str:
        """Convert state dict to hashable key"""
        inv = int(state.get('inventory', 0) / 10) * 10
        back = int(state.get('backlog', 0) / 10) * 10
        period = state.get('period', 0) % 52
        return f"{inv}_{back}_{period}"

    def get_convergence_stats(self) -> Dict[str, Any]:
        """Get statistics for monitoring convergence"""
        if not self.td_errors:
            return {"status": "no_updates"}

        recent = self.td_errors[-100:]
        return {
            "total_updates": self.update_count,
            "avg_td_error": float(np.mean(recent)),
            "std_td_error": float(np.std(recent)),
            "max_td_error": float(np.max(np.abs(recent))),
            "unique_states": len(self.value_table),
            "converged": float(np.std(recent)) < 0.1 if len(recent) > 50 else False,
        }


class TRMValueFunctionWrapper(ValueFunctionApproximator):
    """
    Specialized VFA wrapper for TRM (Tiny Recursive Model) agent.

    Integrates with existing TRM infrastructure while providing
    Powell-compliant value function operations.
    """

    def __init__(
        self,
        trm_agent: Any = None,
        model_path: Optional[str] = None,
        gamma: float = 0.99,
        **kwargs
    ):
        """
        Initialize TRM VFA wrapper.

        Args:
            trm_agent: Existing TRMAgent instance
            model_path: Path to TRM checkpoint (alternative to trm_agent)
            gamma: Discount factor
            **kwargs: Additional arguments for base class
        """
        super().__init__(gamma=gamma, **kwargs)

        self.trm_agent = trm_agent
        self.model_path = model_path

        # Try to get model from TRM agent
        if trm_agent is not None:
            self.model = getattr(trm_agent, 'model', None)
        elif model_path is not None:
            self._load_from_path(model_path)

    def _load_from_path(self, model_path: str):
        """Load TRM model from checkpoint path"""
        try:
            from app.services.trm_agent import TRMAgent
            agent = TRMAgent(model_path=model_path)
            self.trm_agent = agent
            self.model = agent.model
        except Exception as e:
            logger.warning(f"Failed to load TRM from path: {e}")

    def get_action(self, state: Dict[str, Any]) -> int:
        """
        Get action using TRM agent with VFA interpretation.

        The TRM output is interpreted as the argmax of Q(s, a).
        """
        if self.trm_agent is not None and hasattr(self.trm_agent, 'compute_order'):
            try:
                return self.trm_agent.compute_order(
                    inventory=state.get('inventory', 0),
                    backlog=state.get('backlog', 0),
                    pipeline=state.get('pipeline', []),
                    demand_history=state.get('demand_history', []),
                    node_type=state.get('node_type', 'retailer'),
                    node_position=state.get('node_position', 0),
                )
            except Exception as e:
                logger.warning(f"TRM compute_order failed: {e}")

        # Fallback to greedy
        return self._get_greedy_action(state)

    def compute_value_with_reasoning(
        self,
        state: PostDecisionState
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Compute value with chain-of-thought reasoning trace.

        TRM's recursive refinement provides natural reasoning steps.
        """
        value = self.compute_value(state)

        # Build reasoning trace
        reasoning = {
            "state_summary": state.to_dict(),
            "value_estimate": value,
            "factors": {
                "inventory_effect": -0.5 * max(0, state.inventory_position),
                "pipeline_security": 0.3 * state.pipeline_inventory,
                "demand_pressure": -0.7 * state.expected_demand,
                "uncertainty_penalty": -0.2 * state.demand_uncertainty,
            },
            "confidence": 0.8 if self.model is not None else 0.5,
        }

        return value, reasoning
