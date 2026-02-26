"""
TRM Training Pipeline - Span of Control Training

This module implements the training pipeline for Narrow TRM (Tiny Recursive Model)
agents. Each TRM is trained on a specific span of control:

TRM Agents and Their Spans:
- ATPExecutorTRM: Order-level decisions, <10ms latency
- RebalancingTRM: Site-pair inventory transfers, daily decisions
- POCreationTRM: Product-vendor purchase orders, weekly decisions
- OrderTrackingTRM: Order exception detection, continuous monitoring

Training Approach (Powell VFA):
1. Behavioral Cloning: Warm-start from expert/optimal decisions
2. TD Learning: Fine-tune using actual outcomes
3. Curriculum Learning: Progressive complexity (single-node → multi-echelon)

Key Principle: TRM scope is NARROW by design:
- Small state space → RL is tractable
- Fast feedback → rapid learning
- Clear reward signal → stable training
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import numpy as np

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.powell import PowellValueFunction, PowellBeliefState
from app.models.agent_action import AgentAction, ExecutionResult

logger = logging.getLogger(__name__)


# =============================================================================
# Training Configuration
# =============================================================================

class CurriculumStage(str, Enum):
    """Progressive training stages for TRM curriculum learning."""
    SINGLE_NODE = "single_node"       # One site, one product
    TWO_NODE = "two_node"             # Source-destination pair
    FOUR_NODE = "four_node"           # Classic 4-site topology
    MULTI_ECHELON = "multi_echelon"   # Full network
    PRODUCTION = "production"          # Real data fine-tuning


@dataclass
class TRMConfig:
    """Configuration for a specific TRM agent."""
    name: str
    agent_id: str

    # Scope definition
    decision_type: str              # allocate, transfer, order, flag
    entity_scope: str               # order, site_pair, product_vendor
    time_horizon_days: int

    # Model architecture
    hidden_dims: List[int] = field(default_factory=lambda: [64, 64])
    num_recursive_steps: int = 3
    attention_heads: int = 4

    # Training parameters
    learning_rate: float = 0.001
    discount_factor: float = 0.99
    batch_size: int = 32
    epochs_per_stage: int = 100

    # State encoding
    state_features: List[str] = field(default_factory=list)
    action_space_size: int = 10


# Default TRM configurations
TRM_CONFIGS = {
    "trm_atp": TRMConfig(
        name="ATP Executor",
        agent_id="trm_atp",
        decision_type="allocate",
        entity_scope="order",
        time_horizon_days=1,
        state_features=[
            "order_priority",
            "order_quantity",
            "available_atp",
            "days_to_request_date",
            "customer_importance",
        ],
        action_space_size=5,  # Allocation tiers
    ),
    "trm_rebalance": TRMConfig(
        name="Inventory Rebalancing",
        agent_id="trm_rebalance",
        decision_type="transfer",
        entity_scope="site_pair",
        time_horizon_days=7,
        state_features=[
            "source_inventory",
            "source_days_of_supply",
            "target_inventory",
            "target_days_of_supply",
            "transfer_cost",
            "transfer_lead_time",
        ],
        action_space_size=10,  # Quantity buckets
    ),
    "trm_po_creation": TRMConfig(
        name="PO Creation",
        agent_id="trm_po_creation",
        decision_type="order",
        entity_scope="product_vendor",
        time_horizon_days=14,
        state_features=[
            "current_inventory",
            "safety_stock",
            "lead_time_days",
            "demand_forecast",
            "forecast_uncertainty",
            "vendor_reliability",
        ],
        action_space_size=15,  # Quantity + timing buckets
    ),
    "trm_order_tracking": TRMConfig(
        name="Order Tracking",
        agent_id="trm_order_tracking",
        decision_type="flag",
        entity_scope="order",
        time_horizon_days=30,
        state_features=[
            "days_since_order",
            "expected_delivery_date",
            "current_status",
            "supplier_history_otif",
            "quantity",
            "criticality",
        ],
        action_space_size=5,  # Exception types
    ),
}


# =============================================================================
# State Encoder
# =============================================================================

class TRMStateEncoder:
    """
    Encodes supply chain state into TRM input features.

    Each TRM has a specific state encoding based on its scope:
    - ATPExecutorTRM: Order features + available ATP
    - RebalancingTRM: Source/target inventory levels
    - POCreationTRM: Inventory position + demand forecast
    - OrderTrackingTRM: Order status + supplier metrics
    """

    def __init__(self, config: TRMConfig):
        self.config = config
        self.feature_names = config.state_features
        self.state_dim = len(self.feature_names)

    def encode(self, raw_state: Dict[str, Any]) -> np.ndarray:
        """Encode raw state dictionary into feature vector."""
        features = []
        for name in self.feature_names:
            value = raw_state.get(name, 0.0)
            # Normalize based on feature type
            if "days" in name:
                value = value / 30.0  # Normalize days to ~month
            elif "inventory" in name or "quantity" in name:
                value = np.log1p(value) / 10.0  # Log-scale for quantities
            elif "cost" in name:
                value = value / 1000.0  # Normalize costs
            elif "reliability" in name or "importance" in name:
                pass  # Already 0-1
            features.append(float(value))
        return np.array(features, dtype=np.float32)

    def decode_action(self, action_idx: int) -> Dict[str, Any]:
        """Decode action index to interpretable action."""
        if self.config.decision_type == "allocate":
            # Priority tiers 1-5
            return {"priority_tier": action_idx + 1}
        elif self.config.decision_type == "transfer":
            # Quantity buckets: 0, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000
            quantities = [0, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000]
            return {"transfer_quantity": quantities[min(action_idx, len(quantities)-1)]}
        elif self.config.decision_type == "order":
            # Quantity + timing combinations
            return {"order_quantity_bucket": action_idx}
        elif self.config.decision_type == "flag":
            # Exception types
            types = ["no_action", "monitor", "expedite", "escalate", "critical"]
            return {"exception_type": types[min(action_idx, len(types)-1)]}
        return {"action_idx": action_idx}


# =============================================================================
# Training Data Generator
# =============================================================================

class TRMTrainingDataGenerator:
    """
    Generates training data for TRM agents.

    Sources:
    1. Historical decisions from AgentAction table
    2. Simulated scenarios using SimPy
    3. Expert-labeled optimal decisions
    """

    def __init__(self, db: AsyncSession, config: TRMConfig):
        self.db = db
        self.config = config
        self.encoder = TRMStateEncoder(config)

    async def generate_behavioral_cloning_data(
        self,
        tenant_id: int,
        lookback_days: int = 90,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate training data from historical successful decisions.

        Returns:
            states: (N, state_dim) array of encoded states
            actions: (N,) array of action indices
            rewards: (N,) array of outcomes (for weighting)
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        # Get successful actions for this agent type
        result = await self.db.execute(
            select(AgentAction)
            .where(
                AgentAction.tenant_id == tenant_id,
                AgentAction.agent_id == self.config.agent_id,
                AgentAction.execution_result == ExecutionResult.SUCCESS,
                AgentAction.executed_at >= cutoff,
                AgentAction.actual_outcome != None,  # Has feedback
            )
        )
        actions = result.scalars().all()

        if not actions:
            logger.warning(f"No historical data for {self.config.agent_id}")
            return np.array([]), np.array([]), np.array([])

        states = []
        action_indices = []
        rewards = []

        for action in actions:
            # Extract state from reasoning chain
            reasoning = action.reasoning_chain or {}
            input_features = reasoning.get("chain", [{}])[0].get("input", {})

            if not input_features:
                continue

            # Encode state
            state = self.encoder.encode(input_features)
            states.append(state)

            # Extract action (this is simplified - real impl would decode properly)
            action_idx = hash(action.action_type) % self.config.action_space_size
            action_indices.append(action_idx)

            # Use outcome as reward signal
            if action.outcome_within_interval:
                reward = 1.0
            elif action.actual_outcome is not None and action.predicted_outcome is not None:
                # Reward based on prediction error
                error = abs(action.actual_outcome - action.predicted_outcome)
                reward = max(0, 1 - error / max(action.predicted_outcome, 1))
            else:
                reward = 0.5  # Unknown outcome

            rewards.append(reward)

        return (
            np.array(states, dtype=np.float32),
            np.array(action_indices, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
        )

    async def generate_curriculum_data(
        self,
        stage: CurriculumStage,
        num_episodes: int = 1000,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate simulated training data for curriculum learning.

        Each stage progressively increases complexity:
        - SINGLE_NODE: One site, constant demand
        - TWO_NODE: Source-target with lead time
        - FOUR_NODE: Classic 4-site topology
        - MULTI_ECHELON: Full network
        """
        # This would use SimPy simulation
        # For now, generate synthetic data based on stage
        complexity_factors = {
            CurriculumStage.SINGLE_NODE: (1, 0.1),    # 1 node, low variance
            CurriculumStage.TWO_NODE: (2, 0.2),
            CurriculumStage.FOUR_NODE: (4, 0.3),
            CurriculumStage.MULTI_ECHELON: (8, 0.4),
            CurriculumStage.PRODUCTION: (10, 0.5),
        }

        num_nodes, variance = complexity_factors[stage]

        states = []
        actions = []
        rewards = []

        for _ in range(num_episodes):
            # Generate random state
            state = np.random.randn(self.encoder.state_dim).astype(np.float32)
            state = np.clip(state * variance + 0.5, 0, 1)  # Normalize to [0,1]

            # Optimal action (simplified heuristic)
            if self.config.decision_type == "allocate":
                # Higher priority for urgent orders
                urgency = state[3] if len(state) > 3 else 0.5  # days_to_request_date
                action = int(4 * (1 - urgency))  # 0-4
            elif self.config.decision_type == "transfer":
                # Transfer if target has low inventory
                target_dos = state[3] if len(state) > 3 else 0.5
                action = int(9 * (1 - target_dos))  # 0-9
            else:
                action = np.random.randint(self.config.action_space_size)

            # Reward based on action quality (simplified)
            reward = 1.0 - 0.1 * np.random.rand()

            states.append(state)
            actions.append(action)
            rewards.append(reward)

        return (
            np.array(states, dtype=np.float32),
            np.array(actions, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
        )


# =============================================================================
# TRM Model (Simplified)
# =============================================================================

class TRMModel:
    """
    Tiny Recursive Model with recursive refinement.

    Architecture:
    - Input encoder: state → hidden
    - Recursive block: 3-step refinement with attention
    - Output head: hidden → action distribution

    This is a simplified version - real implementation uses PyTorch.
    """

    def __init__(self, config: TRMConfig):
        self.config = config
        self.encoder = TRMStateEncoder(config)

        # Placeholder weights (real impl uses torch.nn)
        self.weights = {
            "encoder": np.random.randn(len(config.state_features), config.hidden_dims[0]) * 0.1,
            "recursive": np.random.randn(config.hidden_dims[0], config.hidden_dims[0]) * 0.1,
            "output": np.random.randn(config.hidden_dims[-1], config.action_space_size) * 0.1,
        }

    def forward(self, state: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        """
        Forward pass with recursive refinement.

        Returns:
            action_probs: (action_space_size,) probability distribution
            refinements: List of refinement step details
        """
        # Encode
        hidden = np.tanh(state @ self.weights["encoder"])

        # Recursive refinement
        refinements = []
        for step in range(self.config.num_recursive_steps):
            # Self-attention (simplified)
            attention = np.exp(hidden @ hidden.T)
            attention = attention / attention.sum()

            # Update hidden
            hidden_new = np.tanh(hidden @ self.weights["recursive"])
            hidden = 0.5 * hidden + 0.5 * hidden_new

            refinements.append({
                "step": step + 1,
                "attention_entropy": -np.sum(attention * np.log(attention + 1e-10)),
                "hidden_norm": np.linalg.norm(hidden),
            })

        # Output
        logits = hidden @ self.weights["output"]
        probs = np.exp(logits - logits.max())
        probs = probs / probs.sum()

        return probs, refinements

    def predict(self, raw_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make a prediction from raw state."""
        state = self.encoder.encode(raw_state)
        probs, refinements = self.forward(state)

        action_idx = np.argmax(probs)
        action = self.encoder.decode_action(action_idx)

        return {
            "action": action,
            "action_idx": int(action_idx),
            "confidence": float(probs[action_idx]),
            "refinements": refinements,
            "action_distribution": probs.tolist(),
        }


# =============================================================================
# Training Pipeline
# =============================================================================

class TRMTrainingPipeline:
    """
    Full training pipeline for TRM agents.

    Stages:
    1. Behavioral Cloning: Initialize from expert decisions
    2. Curriculum Learning: Progressive complexity
    3. TD Learning: Fine-tune with actual outcomes
    4. Evaluation: Measure against holdout data
    """

    def __init__(self, db: AsyncSession, config: TRMConfig):
        self.db = db
        self.config = config
        self.model = TRMModel(config)
        self.data_generator = TRMTrainingDataGenerator(db, config)

    async def train(
        self,
        tenant_id: int,
        stages: Optional[List[CurriculumStage]] = None,
    ) -> Dict[str, Any]:
        """
        Run full training pipeline.

        Returns training metrics and final model state.
        """
        if stages is None:
            stages = list(CurriculumStage)

        metrics = {
            "config": self.config.name,
            "stages_completed": [],
            "final_accuracy": 0.0,
        }

        # Phase 1: Behavioral Cloning
        logger.info(f"Phase 1: Behavioral cloning for {self.config.name}")
        bc_states, bc_actions, bc_rewards = await self.data_generator.generate_behavioral_cloning_data(
            tenant_id
        )
        if len(bc_states) > 0:
            bc_accuracy = self._train_supervised(bc_states, bc_actions, bc_rewards)
            metrics["behavioral_cloning_accuracy"] = bc_accuracy
            logger.info(f"BC accuracy: {bc_accuracy:.3f}")

        # Phase 2: Curriculum Learning
        for stage in stages:
            logger.info(f"Phase 2: Curriculum stage {stage.value}")
            curr_states, curr_actions, curr_rewards = await self.data_generator.generate_curriculum_data(
                stage, num_episodes=self.config.epochs_per_stage
            )
            stage_accuracy = self._train_supervised(curr_states, curr_actions, curr_rewards)
            metrics["stages_completed"].append({
                "stage": stage.value,
                "accuracy": stage_accuracy,
            })
            logger.info(f"Stage {stage.value} accuracy: {stage_accuracy:.3f}")

        # Phase 3: TD Learning (would use actual outcomes)
        # This requires online learning during operation

        metrics["final_accuracy"] = metrics["stages_completed"][-1]["accuracy"] if metrics["stages_completed"] else 0

        return metrics

    def _train_supervised(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        rewards: np.ndarray,
        epochs: int = 10,
    ) -> float:
        """Simple supervised training (placeholder for real PyTorch training)."""
        if len(states) == 0:
            return 0.0

        # Simplified training loop
        correct = 0
        total = len(states)

        for state, target_action in zip(states, actions):
            probs, _ = self.model.forward(state)
            predicted = np.argmax(probs)
            if predicted == target_action:
                correct += 1

        accuracy = correct / total
        return accuracy

    async def evaluate(
        self,
        tenant_id: int,
        test_size: int = 100,
    ) -> Dict[str, float]:
        """Evaluate model on holdout data."""
        # Generate test data
        states, actions, _ = await self.data_generator.generate_curriculum_data(
            CurriculumStage.PRODUCTION, num_episodes=test_size
        )

        if len(states) == 0:
            return {"accuracy": 0, "samples": 0}

        correct = 0
        for state, target in zip(states, actions):
            probs, _ = self.model.forward(state)
            if np.argmax(probs) == target:
                correct += 1

        return {
            "accuracy": correct / len(states),
            "samples": len(states),
        }


# =============================================================================
# Factory Function
# =============================================================================

async def train_all_trm_agents(
    db: AsyncSession,
    tenant_id: int,
) -> Dict[str, Any]:
    """Train all TRM agents for a customer."""
    results = {}

    for agent_id, config in TRM_CONFIGS.items():
        logger.info(f"Training {config.name}...")
        pipeline = TRMTrainingPipeline(db, config)
        metrics = await pipeline.train(tenant_id)
        results[agent_id] = metrics

    return results
