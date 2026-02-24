"""
TRM Training Framework

Supports both behavioral cloning (supervised) and RL (VFA) training
for narrow TRM execution decisions.

Training Methods:
1. Behavioral Cloning: Learn from expert demonstrations (fast warm-start)
2. RL/VFA: Learn from outcomes via TD learning (can exceed expert)
3. Hybrid: Warm-start with BC, fine-tune with RL

Powell Framework Mapping:
- Behavioral Cloning = Imitation of PFA/CFA policies
- RL/VFA = True Value Function Approximation
- The narrow TRM scope makes RL tractable

References:
- Powell SDAM Chapter on VFA
- Conversation on TRM scope constraints
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Callable
from enum import Enum
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class TrainingMethod(Enum):
    """Training method for TRM"""
    BEHAVIORAL_CLONING = "behavioral_cloning"  # Supervised from experts
    TD_LEARNING = "td_learning"  # Q-learning / SARSA
    POLICY_GRADIENT = "policy_gradient"  # REINFORCE / PPO
    OFFLINE_RL = "offline_rl"  # Conservative Q-learning from logs
    HYBRID = "hybrid"  # BC warm-start + RL fine-tune


@dataclass
class TrainingConfig:
    """Configuration for TRM training"""
    method: TrainingMethod = TrainingMethod.HYBRID

    # Common parameters
    learning_rate: float = 1e-4
    batch_size: int = 64
    epochs: int = 100

    # RL-specific parameters
    gamma: float = 0.99  # Discount factor
    tau: float = 0.005  # Target network update rate
    epsilon_start: float = 1.0  # Exploration rate
    epsilon_end: float = 0.01
    epsilon_decay: float = 0.995

    # Hybrid parameters
    bc_epochs: int = 20  # Epochs for BC warm-start
    rl_epochs: int = 80  # Epochs for RL fine-tune

    # Offline RL parameters
    conservative_weight: float = 1.0  # CQL penalty weight


@dataclass
class TrainingRecord:
    """Single training record from TRM decision"""
    state_features: np.ndarray
    action: Any  # Could be int (discrete) or float (continuous)
    reward: float
    next_state_features: Optional[np.ndarray] = None
    done: bool = False

    # For behavioral cloning
    expert_action: Optional[Any] = None

    # Metadata
    trm_type: str = ""  # 'atp', 'rebalancing', 'po_creation', 'order_tracking'
    confidence: float = 1.0

    # Hive signal context (Sprint 4)
    signal_context: Optional[Dict[str, Any]] = None
    urgency_at_time: Optional[float] = None
    triggered_by: Optional[str] = None
    signals_emitted: Optional[List[str]] = None
    cycle_phase: Optional[str] = None
    cycle_id: Optional[str] = None


@dataclass
class TrainingResult:
    """Result of training run"""
    final_loss: float
    loss_history: List[float]
    validation_metrics: Dict[str, float]
    epochs_completed: int
    method_used: TrainingMethod


class RewardCalculator:
    """
    Calculates rewards from TRM outcomes.

    Each TRM type has different reward structures.
    """

    @staticmethod
    def atp_reward(outcome: Dict[str, Any]) -> float:
        """
        ATP reward: maximize fill rate, minimize unfulfillment cost

        outcome keys:
        - fulfilled_qty: actual quantity fulfilled
        - requested_qty: original request
        - was_on_time: boolean
        - customer_priority: 1-5
        """
        fill_rate = outcome.get('fulfilled_qty', 0) / max(1, outcome.get('requested_qty', 1))
        on_time_bonus = 0.2 if outcome.get('was_on_time', False) else 0
        priority_weight = 1.0 + (5 - outcome.get('customer_priority', 3)) * 0.1

        return (fill_rate + on_time_bonus) * priority_weight

    @staticmethod
    def rebalancing_reward(outcome: Dict[str, Any]) -> float:
        """
        Rebalancing reward: service improvement minus transfer cost

        outcome keys:
        - service_improvement: percentage points improvement
        - transfer_cost: actual cost incurred
        - was_executed: boolean
        """
        if not outcome.get('was_executed', False):
            return -0.1  # Small penalty for rejected recommendations

        service_value = outcome.get('service_improvement', 0) * 10  # Scale up
        cost_penalty = outcome.get('transfer_cost', 0) / 1000  # Normalize

        return service_value - cost_penalty

    @staticmethod
    def po_creation_reward(outcome: Dict[str, Any]) -> float:
        """
        PO creation reward: avoid stockouts, minimize holding cost

        outcome keys:
        - days_of_supply_after: DOS after receipt
        - target_dos: target days of supply
        - ordering_cost: cost of the order
        - stockout_occurred: boolean
        """
        if outcome.get('stockout_occurred', False):
            return -10.0  # Large penalty for stockout

        dos_after = outcome.get('days_of_supply_after', 0)
        target = outcome.get('target_dos', 14)

        # Reward being close to target DOS
        dos_deviation = abs(dos_after - target) / target
        dos_reward = 1.0 - min(1.0, dos_deviation)

        # Penalize excess inventory
        if dos_after > target * 1.5:
            excess_penalty = (dos_after - target * 1.5) / target * 0.5
            dos_reward -= excess_penalty

        return dos_reward

    @staticmethod
    def order_tracking_reward(outcome: Dict[str, Any]) -> float:
        """
        Order tracking reward: correct exception handling

        outcome keys:
        - action_was_correct: boolean (human feedback)
        - resolution_cost: actual cost
        - estimated_cost: predicted cost
        - resolution_time_hours: time to resolve
        """
        if outcome.get('action_was_correct', True):
            base_reward = 1.0
        else:
            base_reward = -1.0  # Penalty for wrong action

        # Bonus for fast resolution
        resolution_hours = outcome.get('resolution_time_hours', 24)
        speed_bonus = max(0, (48 - resolution_hours) / 48) * 0.5

        # Penalty for cost underestimation
        estimated = outcome.get('estimated_cost', 0)
        actual = outcome.get('resolution_cost', 0)
        if actual > 0 and estimated > 0:
            cost_accuracy = 1 - abs(actual - estimated) / max(actual, estimated)
            cost_bonus = cost_accuracy * 0.3
        else:
            cost_bonus = 0

        return base_reward + speed_bonus + cost_bonus

    @staticmethod
    def inventory_buffer_reward(outcome: Dict[str, Any]) -> float:
        """
        Inventory buffer reward: balance stockout prevention vs excess cost

        outcome keys:
        - actual_stockout_occurred: boolean
        - actual_dos_at_end: days of supply after the period
        - target_dos: target days of supply
        - excess_inventory_cost: cost of holding excess
        - multiplier_applied: the SS multiplier that was applied
        """
        # Heavy penalty for stockouts
        if outcome.get('actual_stockout_occurred', False):
            stockout_penalty = -2.0
        else:
            stockout_penalty = 0.5  # Reward for avoiding stockout

        # Reward being close to target DOS
        actual_dos = outcome.get('actual_dos_at_end', 0)
        target_dos = outcome.get('target_dos', 14)
        if target_dos > 0:
            dos_deviation = abs(actual_dos - target_dos) / target_dos
            dos_reward = 1.0 - min(1.0, dos_deviation)
        else:
            dos_reward = 0.0

        # Penalize excess inventory cost
        excess_cost = outcome.get('excess_inventory_cost', 0)
        excess_penalty = -min(1.0, excess_cost / 1000)

        # Stability bonus: reward multipliers close to 1.0 (less disruption)
        multiplier = outcome.get('multiplier_applied', 1.0)
        stability = 1.0 - min(1.0, abs(multiplier - 1.0) * 2)
        stability_bonus = stability * 0.3

        return stockout_penalty * 0.4 + dos_reward * 0.3 + excess_penalty * 0.2 + stability_bonus * 0.1

    @staticmethod
    def signal_attribution_bonus(outcome: Dict[str, Any]) -> float:
        """Bonus reward for signal-aware decisions (Sprint 7).

        When a TRM decision was triggered by a hive signal and the outcome
        was positive, reward the signal-response behavior.  Conversely, if
        signals were ignored and the outcome was negative, penalize.

        outcome keys (optional — returns 0.0 if absent):
          - signal_triggered: bool — was the decision triggered by a signal?
          - signal_urgency: float — urgency of the triggering signal
          - outcome_positive: bool — was the outcome beneficial?
          - cross_head_reward: float — coordination reward from the cycle
        """
        if "signal_triggered" not in outcome:
            return 0.0

        triggered = outcome.get("signal_triggered", False)
        urgency = outcome.get("signal_urgency", 0.0)
        positive = outcome.get("outcome_positive", True)
        xhr = outcome.get("cross_head_reward", 0.0)

        bonus = 0.0
        if triggered and positive:
            # Reward responding to signal when outcome was good
            bonus += 0.15 * urgency
        elif triggered and not positive:
            # Small penalty — responded to signal but outcome was bad
            bonus -= 0.05
        elif not triggered and not positive:
            # Penalty for ignoring available signals when outcome was bad
            bonus -= 0.10 * urgency

        # Additional bonus scaled by cross-head coordination reward
        bonus += xhr * 0.05

        return bonus

    def calculate_reward(self, trm_type: str, outcome: Dict[str, Any]) -> float:
        """Calculate reward based on TRM type, with signal attribution bonus."""
        calculators = {
            'atp': self.atp_reward,
            'rebalancing': self.rebalancing_reward,
            'po_creation': self.po_creation_reward,
            'order_tracking': self.order_tracking_reward,
            'inventory_buffer': self.inventory_buffer_reward,
        }

        calculator = calculators.get(trm_type, lambda x: 0.0)
        base_reward = calculator(outcome)

        # Add signal-attribution bonus (zero if no signal context in outcome)
        return base_reward + self.signal_attribution_bonus(outcome)


class TRMTrainer:
    """
    Trainer for narrow TRM models.

    Supports multiple training methods per Powell's VFA framework.
    """

    def __init__(
        self,
        model: Any,  # TRM model (PyTorch nn.Module)
        config: TrainingConfig,
        reward_calculator: Optional[RewardCalculator] = None
    ):
        self.model = model
        self.config = config
        self.reward_calculator = reward_calculator or RewardCalculator()

        # Training state
        self.replay_buffer: List[TrainingRecord] = []
        self.loss_history: List[float] = []

        # For target network (if using TD learning)
        self.target_model = None
        self.epsilon = config.epsilon_start

        if TORCH_AVAILABLE and hasattr(model, 'parameters'):
            self.optimizer = optim.Adam(model.parameters(), lr=config.learning_rate)
        else:
            self.optimizer = None

    def add_experience(
        self,
        state_features: np.ndarray,
        action: Any,
        outcome: Dict[str, Any],
        next_state_features: Optional[np.ndarray] = None,
        done: bool = False,
        trm_type: str = "",
        expert_action: Optional[Any] = None
    ):
        """
        Add experience to replay buffer.

        Called by TRM services via record_outcome().
        """
        reward = self.reward_calculator.calculate_reward(trm_type, outcome)

        record = TrainingRecord(
            state_features=state_features,
            action=action,
            reward=reward,
            next_state_features=next_state_features,
            done=done,
            expert_action=expert_action,
            trm_type=trm_type
        )

        self.replay_buffer.append(record)

        # Keep buffer bounded
        if len(self.replay_buffer) > 100000:
            self.replay_buffer = self.replay_buffer[-100000:]

    def train(self) -> TrainingResult:
        """
        Train TRM using configured method.
        """
        if self.config.method == TrainingMethod.BEHAVIORAL_CLONING:
            return self._train_behavioral_cloning()
        elif self.config.method == TrainingMethod.TD_LEARNING:
            return self._train_td_learning()
        elif self.config.method == TrainingMethod.OFFLINE_RL:
            return self._train_offline_rl()
        elif self.config.method == TrainingMethod.HYBRID:
            return self._train_hybrid()
        else:
            raise ValueError(f"Unknown training method: {self.config.method}")

    def _train_behavioral_cloning(self) -> TrainingResult:
        """
        Train via behavioral cloning (supervised learning).

        loss = MSE(predicted_action, expert_action)

        Fast warm-start but limited to expert performance.
        """
        if not TORCH_AVAILABLE:
            return self._train_heuristic()

        losses = []

        # Filter records with expert actions
        bc_records = [r for r in self.replay_buffer if r.expert_action is not None]

        if len(bc_records) < self.config.batch_size:
            logger.warning("Not enough expert data for behavioral cloning")
            return TrainingResult(
                final_loss=float('inf'),
                loss_history=[],
                validation_metrics={},
                epochs_completed=0,
                method_used=TrainingMethod.BEHAVIORAL_CLONING
            )

        for epoch in range(self.config.epochs):
            # Sample batch
            batch_indices = np.random.choice(len(bc_records), self.config.batch_size)
            batch = [bc_records[i] for i in batch_indices]

            # Prepare tensors
            states = torch.tensor(
                np.array([r.state_features for r in batch]),
                dtype=torch.float32
            )
            expert_actions = torch.tensor(
                np.array([r.expert_action for r in batch]),
                dtype=torch.float32
            )

            # Forward pass
            self.optimizer.zero_grad()
            predicted_actions = self.model(states)

            # MSE loss
            loss = nn.functional.mse_loss(predicted_actions, expert_actions)

            # Backward pass
            loss.backward()
            self.optimizer.step()

            losses.append(loss.item())

        return TrainingResult(
            final_loss=losses[-1] if losses else float('inf'),
            loss_history=losses,
            validation_metrics={},
            epochs_completed=len(losses),
            method_used=TrainingMethod.BEHAVIORAL_CLONING
        )

    def _train_td_learning(self) -> TrainingResult:
        """
        Train via TD learning (Q-learning).

        Q_target = reward + γ * max_a' Q(s', a')
        loss = MSE(Q(s, a), Q_target)

        Powell's VFA - can discover better-than-expert policies.
        """
        if not TORCH_AVAILABLE:
            return self._train_heuristic()

        # Initialize target network
        if self.target_model is None:
            import copy
            self.target_model = copy.deepcopy(self.model)

        losses = []

        # Filter records with next_state
        td_records = [r for r in self.replay_buffer if r.next_state_features is not None]

        if len(td_records) < self.config.batch_size:
            logger.warning("Not enough transition data for TD learning")
            return TrainingResult(
                final_loss=float('inf'),
                loss_history=[],
                validation_metrics={},
                epochs_completed=0,
                method_used=TrainingMethod.TD_LEARNING
            )

        for epoch in range(self.config.epochs):
            # Sample batch
            batch_indices = np.random.choice(len(td_records), self.config.batch_size)
            batch = [td_records[i] for i in batch_indices]

            # Prepare tensors
            states = torch.tensor(
                np.array([r.state_features for r in batch]),
                dtype=torch.float32
            )
            actions = torch.tensor(
                np.array([r.action for r in batch]),
                dtype=torch.long if isinstance(batch[0].action, int) else torch.float32
            )
            rewards = torch.tensor(
                np.array([r.reward for r in batch]),
                dtype=torch.float32
            )
            next_states = torch.tensor(
                np.array([r.next_state_features for r in batch]),
                dtype=torch.float32
            )
            dones = torch.tensor(
                np.array([r.done for r in batch]),
                dtype=torch.float32
            )

            # Current Q values
            self.optimizer.zero_grad()
            current_q = self.model(states)

            # For discrete actions, gather Q(s, a)
            if actions.dtype == torch.long:
                current_q = current_q.gather(1, actions.unsqueeze(1)).squeeze()

            # Target Q values (no gradient)
            with torch.no_grad():
                next_q = self.target_model(next_states)
                if actions.dtype == torch.long:
                    next_q = next_q.max(1)[0]
                target_q = rewards + self.config.gamma * next_q * (1 - dones)

            # TD loss
            loss = nn.functional.mse_loss(current_q, target_q)

            # Backward pass
            loss.backward()
            self.optimizer.step()

            # Soft update target network
            self._soft_update_target()

            # Decay epsilon
            self.epsilon = max(
                self.config.epsilon_end,
                self.epsilon * self.config.epsilon_decay
            )

            losses.append(loss.item())

        return TrainingResult(
            final_loss=losses[-1] if losses else float('inf'),
            loss_history=losses,
            validation_metrics={'epsilon': self.epsilon},
            epochs_completed=len(losses),
            method_used=TrainingMethod.TD_LEARNING
        )

    def _train_offline_rl(self) -> TrainingResult:
        """
        Train via offline RL (Conservative Q-Learning).

        Adds penalty for Q-values on unseen actions to prevent
        overestimation from logged data.

        Ideal for learning from historical TRM decision logs.
        """
        if not TORCH_AVAILABLE:
            return self._train_heuristic()

        # Similar to TD learning but with CQL penalty
        # Q_loss = TD_loss + α * (E[Q(s,a)] - E[Q(s, a_data)])

        losses = []
        td_records = [r for r in self.replay_buffer if r.next_state_features is not None]

        if len(td_records) < self.config.batch_size:
            return TrainingResult(
                final_loss=float('inf'),
                loss_history=[],
                validation_metrics={},
                epochs_completed=0,
                method_used=TrainingMethod.OFFLINE_RL
            )

        if self.target_model is None:
            import copy
            self.target_model = copy.deepcopy(self.model)

        for epoch in range(self.config.epochs):
            batch_indices = np.random.choice(len(td_records), self.config.batch_size)
            batch = [td_records[i] for i in batch_indices]

            states = torch.tensor(
                np.array([r.state_features for r in batch]),
                dtype=torch.float32
            )
            actions = torch.tensor(
                np.array([r.action for r in batch]),
                dtype=torch.long if isinstance(batch[0].action, int) else torch.float32
            )
            rewards = torch.tensor(
                np.array([r.reward for r in batch]),
                dtype=torch.float32
            )
            next_states = torch.tensor(
                np.array([r.next_state_features for r in batch]),
                dtype=torch.float32
            )
            dones = torch.tensor(
                np.array([r.done for r in batch]),
                dtype=torch.float32
            )

            self.optimizer.zero_grad()

            # Q values for all actions
            all_q = self.model(states)

            # Q value for logged action
            if actions.dtype == torch.long:
                logged_q = all_q.gather(1, actions.unsqueeze(1)).squeeze()
            else:
                logged_q = all_q.squeeze()

            # Target Q
            with torch.no_grad():
                next_q = self.target_model(next_states)
                if actions.dtype == torch.long:
                    next_q = next_q.max(1)[0]
                target_q = rewards + self.config.gamma * next_q * (1 - dones)

            # TD loss
            td_loss = nn.functional.mse_loss(logged_q, target_q)

            # CQL penalty: penalize high Q-values on non-logged actions
            if actions.dtype == torch.long:
                logsumexp_q = torch.logsumexp(all_q, dim=1)
                cql_penalty = (logsumexp_q - logged_q).mean()
            else:
                cql_penalty = torch.tensor(0.0)

            # Total loss
            loss = td_loss + self.config.conservative_weight * cql_penalty

            loss.backward()
            self.optimizer.step()
            self._soft_update_target()

            losses.append(loss.item())

        return TrainingResult(
            final_loss=losses[-1] if losses else float('inf'),
            loss_history=losses,
            validation_metrics={},
            epochs_completed=len(losses),
            method_used=TrainingMethod.OFFLINE_RL
        )

    def _train_hybrid(self) -> TrainingResult:
        """
        Hybrid training: BC warm-start + RL fine-tune.

        Best of both worlds:
        1. BC gives fast convergence to expert-level
        2. RL can then improve beyond expert
        """
        # Phase 1: Behavioral Cloning
        self.config.epochs = self.config.bc_epochs
        bc_result = self._train_behavioral_cloning()

        # Phase 2: RL Fine-tuning
        self.config.epochs = self.config.rl_epochs
        rl_result = self._train_offline_rl()  # Use offline RL for stability

        # Combine results
        return TrainingResult(
            final_loss=rl_result.final_loss,
            loss_history=bc_result.loss_history + rl_result.loss_history,
            validation_metrics={
                'bc_final_loss': bc_result.final_loss,
                'rl_final_loss': rl_result.final_loss,
            },
            epochs_completed=bc_result.epochs_completed + rl_result.epochs_completed,
            method_used=TrainingMethod.HYBRID
        )

    def _soft_update_target(self):
        """Soft update target network"""
        if self.target_model is None:
            return

        for target_param, param in zip(
            self.target_model.parameters(),
            self.model.parameters()
        ):
            target_param.data.copy_(
                self.config.tau * param.data +
                (1 - self.config.tau) * target_param.data
            )

    def _train_heuristic(self) -> TrainingResult:
        """Fallback heuristic when PyTorch unavailable"""
        logger.warning("PyTorch not available, using heuristic fallback")
        return TrainingResult(
            final_loss=0.0,
            loss_history=[],
            validation_metrics={},
            epochs_completed=0,
            method_used=self.config.method
        )

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training statistics"""
        return {
            'buffer_size': len(self.replay_buffer),
            'records_with_expert': sum(1 for r in self.replay_buffer if r.expert_action is not None),
            'records_with_next_state': sum(1 for r in self.replay_buffer if r.next_state_features is not None),
            'trm_type_distribution': self._get_type_distribution(),
            'average_reward': np.mean([r.reward for r in self.replay_buffer]) if self.replay_buffer else 0,
            'epsilon': self.epsilon,
        }

    def _get_type_distribution(self) -> Dict[str, int]:
        """Get distribution of TRM types in buffer"""
        distribution: Dict[str, int] = {}
        for record in self.replay_buffer:
            trm_type = record.trm_type or 'unknown'
            distribution[trm_type] = distribution.get(trm_type, 0) + 1
        return distribution
