# Tiny Recursive Models (TRM) Implementation Plan
## Beer Game Supply Chain Optimization Agent

**Document Version**: 1.0
**Date**: 2026-01-16
**Status**: Planning / Pre-Implementation

---

## Executive Summary

This document outlines the implementation plan for integrating **Tiny Recursive Models (TRM)** as a new agent strategy in The Beer Game supply chain simulation. TRM is an emerging machine learning paradigm that achieves superior reasoning performance using extremely small neural networks (7M parameters) through recursive refinement, offering significant advantages over current GNN, RL, and LLM-based approaches.

### Key Value Propositions

- **18-20x parameter reduction** compared to current GNN agents (7M vs 128M parameters)
- **50-100x faster inference** than LLM agents (<10ms vs 1-5s)
- **10-100x training efficiency** compared to RL approaches (1K episodes vs 1M timesteps)
- **Superior generalization** to unseen supply chain topologies through learned reasoning processes
- **CPU-compatible** deployment without GPU infrastructure requirements

---

## Table of Contents

1. [Background](#background)
2. [Technical Overview](#technical-overview)
3. [Architecture Design](#architecture-design)
4. [Integration Strategy](#integration-strategy)
5. [Implementation Roadmap](#implementation-roadmap)
6. [Training Pipeline](#training-pipeline)
7. [Performance Benchmarks](#performance-benchmarks)
8. [Risk Analysis](#risk-analysis)
9. [API Specifications](#api-specifications)
10. [Testing Strategy](#testing-strategy)
11. [Deployment Plan](#deployment-plan)
12. [References](#references)

---

## Background

### What are Tiny Recursive Models?

**Tiny Recursive Models (TRM)** are a novel ML architecture introduced in the paper "Less is More: Recursive Reasoning with Tiny Networks" (October 2025). Key characteristics:

- **Architecture**: 2-layer transformer with recursive refinement
- **Parameters**: Only 7 million (vs billions in LLMs)
- **Performance**: 45% accuracy on ARC-AGI-1, 8% on ARC-AGI-2
- **Training**: ~1,000 examples using curriculum learning
- **Philosophy**: Learns *reasoning processes* rather than memorizing patterns

#### Core Innovation

TRM separates reasoning into two components:
- **Latent thought process (z)**: Internal reasoning state, updated recursively
- **Visible output (y)**: Answer/decision, refined after reasoning updates

This enables iterative "check and adjust" behavior similar to human problem-solving.

### Current Beer Game Agent Landscape

| Agent Type | Parameters | Inference Time | Training Cost | Generalization |
|------------|-----------|----------------|---------------|----------------|
| **Naive/PID** | 0 (rules) | <1ms | None | Moderate |
| **GNN (Temporal)** | 128M+ | 50-100ms | High (GPU) | Low (overfits) |
| **RL (PPO/SAC)** | 2-5M | 10-20ms | Very High (1M steps) | Moderate |
| **LLM (GPT)** | 1B+ | 1-5s | API costs | High (expensive) |
| **TRM (Proposed)** | 7M | <10ms | Low (1K episodes) | **High** |

### Why TRM for Supply Chain Optimization?

1. **Natural alignment**: Recursive refinement mirrors supply chain planning (iterative adjustment)
2. **Multi-horizon reasoning**: Inner loops for tactical, outer loops for strategic decisions
3. **Parameter efficiency**: Runs on CPU without GPU infrastructure
4. **Generalization**: Learns reasoning *process* not just specific patterns
5. **Interpretability**: Can inspect intermediate reasoning states

---

## Technical Overview

### TRM Architecture Principles

#### 1. State Representation

```
x: Input state (supply chain snapshot)
   - Node features: inventory, backlog, costs
   - Graph structure: lanes, connections
   - Temporal history: demand patterns, order history

y: Answer embedding (current order decision)
   - Continuous representation of order quantity
   - Refined iteratively through reasoning cycles

z: Latent reasoning state (thought process)
   - Internal representation of planning logic
   - Updated recursively considering x, y, z
```

#### 2. Recursive Refinement Process

```python
# Pseudo-code for TRM reasoning
def trm_decision(x_state):
    y = initialize_answer(x_state)  # Initial guess
    z = initialize_latent()          # Empty reasoning state

    for cycle in range(K_refinement_cycles):
        # Inner loop: Recursive reasoning
        for step in range(N_reasoning_steps):
            z = update_latent(x_state, y, z)  # Refine thought process

        # Outer loop: Answer refinement
        y = update_answer(x_state, z)  # Adjust order based on reasoning

    order_quantity = decode_answer(y)
    return order_quantity
```

#### 3. Key Advantages Over Current Approaches

**vs Graph Neural Networks (GNN):**
- **Size**: 7M params vs 128M+ for EnhancedTemporalGNN
- **Reasoning**: Multi-step refinement vs single forward pass
- **Generalization**: Process learning vs pattern matching
- **Hardware**: CPU-compatible vs GPU-required

**vs Reinforcement Learning (RL):**
- **Sample efficiency**: 1K episodes vs 1M timesteps for PPO
- **Stability**: Supervised learning vs unstable policy gradients
- **Training time**: Hours vs days/weeks
- **Interpretability**: Inspect reasoning vs black-box policy

**vs Large Language Models (LLM):**
- **Cost**: No API fees, local inference
- **Speed**: <10ms vs 1-5s per decision
- **Reliability**: Deterministic vs prompt-sensitive
- **Privacy**: On-premise vs cloud dependency

---

## Architecture Design

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Beer Game Engine                          │
│                   (BeerLine, Nodes)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Manager                             │
│  (Selects strategy: naive, bullwhip, gnn, rl, llm, **trm**)│
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐           ┌─────────────────────┐
│  Existing       │           │  NEW: TRM Agent     │
│  Strategies     │           │                     │
│                 │           │  - State Encoder    │
│  - Naive        │           │  - Reasoning Cell   │
│  - Bullwhip     │           │  - Answer Refiner   │
│  - Conservative │           │  - Order Decoder    │
│  - PID          │           │                     │
│  - GNN          │           │  Runtime: <10ms     │
│  - RL           │           │  Memory: ~50MB      │
│  - LLM          │           │  Device: CPU/GPU    │
└─────────────────┘           └─────────────────────┘
```

### Component Specifications

#### 1. TRM Core Module

**File**: `backend/app/models/trm/tiny_recursive_model.py`

```python
class TinyRecursiveModel(nn.Module):
    """
    Tiny Recursive Model for supply chain order optimization.

    Architecture:
    - 2-layer transformer encoder (state encoding)
    - Recursive reasoning cell (latent updates)
    - Answer refinement cell (decision updates)
    - Linear decoder (order quantity)

    Parameters: ~7M
    Inference: <10ms on CPU
    """

    def __init__(
        self,
        node_feature_dim: int = 16,      # Inventory, backlog, costs, etc.
        edge_feature_dim: int = 4,       # Lane properties
        hidden_dim: int = 64,            # Embedding dimension
        num_layers: int = 2,             # Transformer layers
        num_heads: int = 4,              # Attention heads
        num_refinement_cycles: int = 5,  # K outer loops
        num_reasoning_steps: int = 3,    # N inner loops per cycle
        dropout: float = 0.1
    )
```

**Key Methods:**
- `forward(x_state, x_graph) -> order_quantities`
- `encode_state(node_features, edge_index) -> x_encoded`
- `recursive_reasoning(x, y, z, n_steps) -> z_refined`
- `refine_answer(x, z) -> y_updated`
- `decode_order(y) -> order_quantity`

#### 2. Recursive Reasoning Cell

**File**: `backend/app/models/trm/reasoning_cell.py`

```python
class RecursiveReasoningCell(nn.Module):
    """
    Updates latent reasoning state z based on:
    - Input state x (supply chain snapshot)
    - Current answer y (order decision)
    - Previous reasoning z (thought process)

    This implements the "check and adjust" logic.
    """

    def __init__(self, hidden_dim: int, dropout: float = 0.1):
        self.reasoning_update = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=4,
            dim_feedforward=hidden_dim * 2,
            dropout=dropout,
            batch_first=True
        )

        # Combine x, y, z for reasoning
        self.state_projector = nn.Linear(hidden_dim * 3, hidden_dim)

    def forward(self, x_state, y_answer, z_latent):
        # Concatenate all information sources
        combined = torch.cat([x_state, y_answer, z_latent], dim=-1)
        projected = self.state_projector(combined)

        # Update reasoning state
        z_next = self.reasoning_update(projected)

        # Residual connection for stability
        z_next = z_next + z_latent

        return z_next
```

#### 3. Answer Refinement Cell

**File**: `backend/app/models/trm/answer_refiner.py`

```python
class AnswerRefinementCell(nn.Module):
    """
    Refines answer y based on:
    - Input state x (supply chain conditions)
    - Refined reasoning z (updated thought process)

    Produces improved order decision.
    """

    def __init__(self, hidden_dim: int, dropout: float = 0.1):
        self.answer_update = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim)
        )

    def forward(self, x_state, z_reasoning):
        # Combine state and reasoning
        combined = torch.cat([x_state, z_reasoning], dim=-1)

        # Update answer embedding
        y_delta = self.answer_update(combined)

        return y_delta  # Will be added to previous y
```

#### 4. Supply Chain State Encoder

**File**: `backend/app/models/trm/state_encoder.py`

```python
class SupplyChainStateEncoder(nn.Module):
    """
    Encodes supply chain state into fixed-size representation.

    Handles:
    - Node features (inventory, backlog, costs)
    - Graph structure (DAG topology)
    - Temporal history (demand patterns, order history)
    """

    def __init__(
        self,
        node_feature_dim: int = 16,
        edge_feature_dim: int = 4,
        hidden_dim: int = 64,
        window_size: int = 10  # Temporal lookback
    ):
        # Node feature encoder
        self.node_encoder = nn.Linear(node_feature_dim, hidden_dim)

        # Graph attention for structure
        self.graph_attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=4,
            batch_first=True
        )

        # Temporal pooling for history
        self.temporal_pooler = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True
        )

    def forward(self, node_features, edge_index, temporal_history=None):
        # Encode nodes
        node_embeds = self.node_encoder(node_features)

        # Apply graph attention
        graph_embeds, _ = self.graph_attention(
            node_embeds, node_embeds, node_embeds
        )

        # Pool temporal history if available
        if temporal_history is not None:
            _, (h_n, _) = self.temporal_pooler(temporal_history)
            graph_embeds = graph_embeds + h_n.squeeze(0)

        return graph_embeds
```

---

## Integration Strategy

### 1. Agent System Integration

**File**: `backend/app/services/agents.py`

```python
class AgentStrategy(Enum):
    # Existing strategies
    NAIVE = "naive"
    BULLWHIP = "bullwhip"
    CONSERVATIVE = "conservative"
    PID = "pid_heuristic"
    LLM = "llm"
    # ... other strategies ...

    # NEW: TRM strategies
    TRM = "trm"                    # Pure TRM agent
    TRM_HYBRID = "trm_hybrid"      # TRM with heuristic fallback
    TRM_ENSEMBLE = "trm_ensemble"  # Ensemble of TRM + GNN
```

**Implementation in `BeerGameAgent.make_decision()`:**

```python
def make_decision(
    self,
    current_round: int,
    current_demand: Optional[int] = None,
    upstream_data: Optional[Dict] = None,
    local_state: Optional[Dict[str, Any]] = None,
) -> AgentDecision:
    # ... existing strategy handling ...

    # NEW: TRM strategy
    elif self.strategy == AgentStrategy.TRM:
        order = self._trm_strategy(
            current_round,
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            processed_shipments,
        )
    elif self.strategy == AgentStrategy.TRM_HYBRID:
        try:
            order = self._trm_strategy(...)
        except Exception as e:
            logger.warning(f"TRM failed, falling back to PID: {e}")
            order = self._pid_strategy(...)

    # ... rest of implementation ...
```

### 2. TRM Policy Implementation

**File**: `backend/app/models/trm/trm_policy.py`

```python
class TRMPolicy(BasePolicy):
    """
    TRM-based policy for Beer Game agent decisions.

    Implements BasePolicy interface for seamless integration.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        refinement_cycles: int = 5,
        reasoning_steps: int = 3
    ):
        super().__init__()
        self.model = TinyRecursiveModel(
            num_refinement_cycles=refinement_cycles,
            num_reasoning_steps=reasoning_steps
        )
        self.device = device

        if model_path and Path(model_path).exists():
            self.load_checkpoint(model_path)

        self.model.to(device)
        self.model.eval()

    def compute_order(self, node: Any, context: Dict[str, Any]) -> int:
        """
        Compute order quantity using TRM.

        Args:
            node: BeerLine node with state
            context: Game context (round, demand, etc.)

        Returns:
            order_quantity: Optimized order amount
        """
        # Prepare state representation
        state = self._prepare_state(node, context)

        # Run TRM inference
        with torch.no_grad():
            order_tensor = self.model(state)

        # Convert to integer order
        order_quantity = int(torch.round(order_tensor).item())
        order_quantity = max(0, order_quantity)  # Non-negative

        return order_quantity

    def _prepare_state(self, node, context) -> torch.Tensor:
        """Convert node state to TRM input format."""
        features = torch.tensor([
            node.inventory,
            node.backlog,
            sum(node.pipeline_shipments),
            context.get("incoming_orders", 0),
            context.get("round_number", 0) / 52,  # Normalized
            # ... additional features ...
        ], dtype=torch.float32)

        return features.unsqueeze(0).to(self.device)
```

### 3. Service Layer Integration

**File**: `backend/app/services/agent_service.py` (new)

```python
class TRMAgentService:
    """
    Service for managing TRM agent lifecycle.

    Handles:
    - Model loading/caching
    - Batch inference for multiple nodes
    - Performance monitoring
    """

    _instance = None
    _models: Dict[str, TRMPolicy] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_model(self, config_name: str = "default") -> TRMPolicy:
        """Get or load TRM model."""
        if config_name not in self._models:
            model_path = f"checkpoints/trm/{config_name}_trm.pt"
            self._models[config_name] = TRMPolicy(model_path=model_path)
        return self._models[config_name]

    def batch_inference(
        self,
        nodes: List[Any],
        contexts: List[Dict[str, Any]],
        config_name: str = "default"
    ) -> List[int]:
        """Efficient batch processing for multiple nodes."""
        model = self.get_model(config_name)

        # Batch preparation
        states = [model._prepare_state(n, c) for n, c in zip(nodes, contexts)]
        batch_states = torch.cat(states, dim=0)

        # Batch inference
        with torch.no_grad():
            orders = model.model(batch_states)

        # Convert to list
        return [int(torch.round(o).item()) for o in orders]
```

---

## Implementation Roadmap

### Phase 1: Core TRM Implementation (2-3 weeks)

**Week 1: Foundation**
- [ ] Set up TRM module structure (`backend/app/models/trm/`)
- [ ] Implement 2-layer transformer encoder
- [ ] Create basic state encoder for single-node scenario
- [ ] Write unit tests for encoder
- [ ] Document architecture decisions

**Week 2: Recursive Components**
- [ ] Implement `RecursiveReasoningCell` (z-update)
- [ ] Implement `AnswerRefinementCell` (y-update)
- [ ] Create order quantity decoder
- [ ] Integrate refinement loops
- [ ] Unit tests for reasoning and refinement

**Week 3: Integration & Testing**
- [ ] Assemble full `TinyRecursiveModel`
- [ ] Test end-to-end forward pass
- [ ] Implement gradient checkpointing for memory efficiency
- [ ] Add model serialization (save/load)
- [ ] Performance profiling (inference time, memory)

**Deliverables:**
- `backend/app/models/trm/tiny_recursive_model.py`
- `backend/app/models/trm/reasoning_cell.py`
- `backend/app/models/trm/answer_refiner.py`
- `backend/app/models/trm/state_encoder.py`
- Unit test suite with >80% coverage
- Performance benchmark report

### Phase 2: Beer Game Integration (1-2 weeks)

**Week 4: Agent System Integration**
- [ ] Add `AgentStrategy.TRM` to enum
- [ ] Implement `_trm_strategy()` method in `BeerGameAgent`
- [ ] Create `TRMPolicy` class implementing `BasePolicy`
- [ ] Handle multi-node supply chain inference
- [ ] Add fallback mechanisms

**Week 5: Service Layer**
- [ ] Create `TRMAgentService` for model management
- [ ] Implement model caching and lifecycle
- [ ] Add batch inference capabilities
- [ ] API endpoint for TRM configuration
- [ ] Integration tests with BeerLine engine

**Deliverables:**
- `backend/app/services/agents.py` (updated)
- `backend/app/models/trm/trm_policy.py`
- `backend/app/services/trm_agent_service.py`
- Integration test suite
- API documentation

### Phase 3: Training Infrastructure (2 weeks)

**Week 6: Data Pipeline**
- [ ] Extend SimPy generator for TRM training format
- [ ] Create curriculum learning data loader
- [ ] Implement staged difficulty progression
- [ ] Data augmentation strategies
- [ ] Validation set generation

**Week 7: Training Loop**
- [ ] Loss function design (order optimality + cost)
- [ ] Implement curriculum training scheduler
- [ ] Add gradient clipping and regularization
- [ ] Checkpointing and early stopping
- [ ] TensorBoard logging integration

**Deliverables:**
- `backend/scripts/training/train_trm.py`
- `backend/app/data/trm_dataset.py`
- `backend/app/training/trm_trainer.py`
- Training configuration templates
- Data generation pipeline

### Phase 4: Evaluation & Tuning (1-2 weeks)

**Week 8: Benchmarking**
- [ ] Benchmark vs Naive baseline
- [ ] Compare with GNN agents (temporal, graphsage)
- [ ] Compare with RL agents (PPO)
- [ ] Compare with LLM agents
- [ ] Measure inference speed, memory, cost

**Week 9: Optimization**
- [ ] Hyperparameter tuning (cycles, steps, hidden_dim)
- [ ] Ablation studies (remove components)
- [ ] Test generalization to unseen configs
- [ ] Optimize inference speed (ONNX export?)
- [ ] Final model selection

**Deliverables:**
- Benchmark report with metrics
- Ablation study results
- Trained TRM checkpoints
- Performance comparison dashboard
- Recommendations document

### Phase 5: Production Deployment (1 week)

**Week 10: Production Readiness**
- [ ] ONNX export for optimized inference
- [ ] Docker container with TRM support
- [ ] Update admin UI for TRM strategy selection
- [ ] Production monitoring and logging
- [ ] Documentation and tutorials

**Deliverables:**
- Production-ready TRM agent
- Deployment documentation
- Admin UI updates
- Example games and tutorials
- User guide

---

## Training Pipeline

### Curriculum Learning Strategy

TRM training uses staged curriculum to build from simple to complex scenarios:

#### Stage 1: Foundation (Easy) - 300 episodes
**Objectives**: Learn basic inventory management

- **Demand**: Constant (4 units/round)
- **Lead Time**: Short (2 rounds)
- **Network**: Linear chain (Retailer → Wholesaler → Distributor → Factory)
- **Noise**: None
- **Success Criteria**: Average cost < 50 per round

#### Stage 2: Adaptation (Medium) - 400 episodes
**Objectives**: Handle demand changes

- **Demand**: Step function (4 → 8 units at round 10)
- **Lead Time**: Standard (2-3 rounds)
- **Network**: Linear + simple branching
- **Noise**: Low (±1 unit)
- **Success Criteria**: Average cost < 100 per round, bullwhip metric < 1.5

#### Stage 3: Mastery (Hard) - 300 episodes
**Objectives**: Optimize in volatile conditions

- **Demand**: Stochastic (mean=8, std=4)
- **Lead Time**: Variable (2-4 rounds)
- **Network**: Complex DAG topologies
- **Noise**: High (±3 units)
- **Success Criteria**: Average cost < 150, handle bullwhip effect

### Training Configuration

**File**: `backend/configs/trm_training_config.yaml`

```yaml
model:
  node_feature_dim: 16
  edge_feature_dim: 4
  hidden_dim: 64
  num_layers: 2
  num_heads: 4
  num_refinement_cycles: 5
  num_reasoning_steps: 3
  dropout: 0.1

training:
  total_episodes: 1000
  batch_size: 32
  learning_rate: 0.001
  weight_decay: 0.0001
  max_grad_norm: 1.0

  # Curriculum stages
  curriculum:
    - name: "foundation"
      episodes: 300
      difficulty: "easy"
    - name: "adaptation"
      episodes: 400
      difficulty: "medium"
    - name: "mastery"
      episodes: 300
      difficulty: "hard"

loss:
  # Multi-objective loss
  order_optimality_weight: 1.0   # Proximity to optimal order
  cost_minimization_weight: 0.5  # Total supply chain cost
  stability_weight: 0.3          # Reduce order variance (bullwhip)
  service_level_weight: 0.2      # Maintain high fill rate

optimizer:
  type: "AdamW"
  betas: [0.9, 0.999]
  eps: 1.0e-8

scheduler:
  type: "CosineAnnealingWarmRestarts"
  T_0: 100  # Restart every 100 episodes
  T_mult: 2
  eta_min: 1.0e-6

device: "cpu"  # TRM is efficient on CPU
checkpoint_dir: "checkpoints/trm"
log_dir: "logs/trm"
```

### Loss Function Design

**File**: `backend/app/training/trm_loss.py`

```python
class TRMSupplyChainLoss(nn.Module):
    """
    Multi-objective loss for TRM training.

    Components:
    1. Order Optimality: L1 distance to theoretical optimal order
    2. Cost Minimization: Total supply chain cost (inventory + backlog)
    3. Stability: Variance penalty to reduce bullwhip effect
    4. Service Level: Penalty for backlog/stockouts
    """

    def __init__(
        self,
        order_weight: float = 1.0,
        cost_weight: float = 0.5,
        stability_weight: float = 0.3,
        service_weight: float = 0.2
    ):
        super().__init__()
        self.order_weight = order_weight
        self.cost_weight = cost_weight
        self.stability_weight = stability_weight
        self.service_weight = service_weight

    def forward(
        self,
        predicted_orders: torch.Tensor,
        optimal_orders: torch.Tensor,
        inventory_costs: torch.Tensor,
        backlog_costs: torch.Tensor,
        order_variance: torch.Tensor,
        service_level: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        # 1. Order optimality loss
        order_loss = F.l1_loss(predicted_orders, optimal_orders)

        # 2. Cost minimization loss
        total_costs = inventory_costs + backlog_costs
        cost_loss = total_costs.mean()

        # 3. Stability loss (penalize high variance)
        stability_loss = order_variance.mean()

        # 4. Service level loss (penalize stockouts)
        service_loss = F.relu(0.95 - service_level).mean()

        # Combined loss
        total_loss = (
            self.order_weight * order_loss +
            self.cost_weight * cost_loss +
            self.stability_weight * stability_loss +
            self.service_weight * service_loss
        )

        return {
            "total": total_loss,
            "order": order_loss,
            "cost": cost_loss,
            "stability": stability_loss,
            "service": service_loss
        }
```

### Training Script

**File**: `backend/scripts/training/train_trm.py`

```python
#!/usr/bin/env python3
"""
Train Tiny Recursive Model for Beer Game.

Usage:
    python -m scripts.training.train_trm \\
        --config configs/trm_training_config.yaml \\
        --supply-chain "Default TBG" \\
        --device cpu
"""

import argparse
import logging
from pathlib import Path

import torch
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter

from app.models.trm import TinyRecursiveModel
from app.data.trm_dataset import TRMSupplyChainDataset
from app.training.trm_trainer import TRMTrainer
from app.training.trm_loss import TRMSupplyChainLoss

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True)
    parser.add_argument("--supply-chain", type=str, default="Default TBG")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Initialize model
    model = TinyRecursiveModel(**config["model"])
    model.to(args.device)

    # Load checkpoint if resuming
    start_episode = 0
    if args.resume and args.checkpoint:
        checkpoint = torch.load(args.checkpoint)
        model.load_state_dict(checkpoint["model_state_dict"])
        start_episode = checkpoint["episode"]
        logger.info(f"Resumed from episode {start_episode}")

    # Create datasets with curriculum
    datasets = create_curriculum_datasets(
        supply_chain_config=args.supply_chain,
        curriculum_stages=config["training"]["curriculum"]
    )

    # Loss function
    loss_fn = TRMSupplyChainLoss(**config["loss"])

    # Optimizer
    optimizer = optim.AdamW(
        model.parameters(),
        lr=config["training"]["learning_rate"],
        weight_decay=config["training"]["weight_decay"]
    )

    # Learning rate scheduler
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer,
        T_0=config["scheduler"]["T_0"],
        T_mult=config["scheduler"]["T_mult"],
        eta_min=config["scheduler"]["eta_min"]
    )

    # Trainer
    trainer = TRMTrainer(
        model=model,
        loss_fn=loss_fn,
        optimizer=optimizer,
        scheduler=scheduler,
        device=args.device,
        checkpoint_dir=config["checkpoint_dir"],
        log_dir=config["log_dir"]
    )

    # Train with curriculum
    for stage_name, dataset in datasets.items():
        logger.info(f"Training stage: {stage_name}")
        trainer.train_stage(
            dataset=dataset,
            stage_name=stage_name,
            start_episode=start_episode
        )
        start_episode = 0  # Reset for next stage

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
```

### Makefile Integration

**File**: `Makefile` (additions)

```makefile
# TRM Training targets

.PHONY: train-trm
train-trm: ## Train TRM agent on default config
	docker compose exec backend python -m scripts.training.train_trm \\
		--config configs/trm_training_config.yaml \\
		--supply-chain "Default TBG" \\
		--device cpu

.PHONY: train-trm-gpu
train-trm-gpu: ## Train TRM agent on GPU
	docker compose exec backend python -m scripts.training.train_trm \\
		--config configs/trm_training_config.yaml \\
		--supply-chain "Default TBG" \\
		--device cuda

.PHONY: trm-eval
trm-eval: ## Evaluate trained TRM agent
	docker compose exec backend python -m scripts.evaluation.eval_trm \\
		--checkpoint checkpoints/trm/best_model.pt \\
		--supply-chain "Default TBG" \\
		--n-episodes 100

.PHONY: trm-benchmark
trm-benchmark: ## Benchmark TRM vs other agents
	docker compose exec backend python -m scripts.benchmark.compare_agents \\
		--agents naive,pid,gnn,rl,llm,trm \\
		--supply-chain "Default TBG" \\
		--n-games 50
```

---

## Performance Benchmarks

### Target Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Inference Time** | <10ms | Per-node order decision |
| **Model Size** | <50MB | On-disk checkpoint |
| **Memory Usage** | <100MB | Runtime (CPU) |
| **Training Time** | <4 hours | 1K episodes on CPU |
| **Cost Reduction** | 10-20% | vs Naive baseline |
| **Service Level** | >90% | Fill rate |
| **Bullwhip Metric** | <1.5 | Order variance ratio |

### Expected Performance Comparison

#### Inference Speed (per decision)
```
Naive/PID:    <1ms     ████
TRM:          8ms      ████████
GNN:          50ms     ██████████████████████████████████████████████████
RL (PPO):     15ms     ███████████████
LLM (GPT):    2500ms   ████████████████████████████████████████████... (off chart)
```

#### Model Size
```
TRM:          7M params   ███████
GNN:          128M params ████████████████████████████████████████████████████████████████████
RL:           5M params   █████
LLM:          1B+ params  ████████████████████████████████████████████... (off chart)
```

#### Training Efficiency (episodes to convergence)
```
TRM:          1K episodes     ████████
RL (PPO):     1M episodes     ████████████████████████████████████████████... (100x more)
```

### Benchmark Scenarios

#### Scenario 1: Stable Demand
- **Demand**: Constant 4 units/round
- **Expected Winner**: Naive/PID (simple is optimal)
- **TRM Goal**: Match optimal within 5%

#### Scenario 2: Step Demand
- **Demand**: 4 → 8 units at round 10
- **Expected Winner**: GNN/TRM (adaptive)
- **TRM Goal**: 10-15% better than Naive

#### Scenario 3: Stochastic Demand
- **Demand**: N(8, 4) normal distribution
- **Expected Winner**: RL/TRM (robust optimization)
- **TRM Goal**: 15-20% better than Naive, match RL

#### Scenario 4: Complex Network
- **Topology**: 3-level tree with 12 nodes
- **Expected Winner**: TRM (generalization)
- **TRM Goal**: Handle unseen topology, <20% from optimal

### Evaluation Script

**File**: `backend/scripts/evaluation/eval_trm.py`

```python
#!/usr/bin/env python3
"""
Evaluate TRM agent performance.

Generates comprehensive metrics:
- Total cost
- Service level
- Bullwhip ratio
- Inference time
- Comparison with other agents
"""

import time
import numpy as np
from typing import Dict, List

from app.models.trm import TRMPolicy
from app.services.engine import BeerLine
from app.services.agents import AgentStrategy, BeerGameAgent


def evaluate_trm(
    checkpoint_path: str,
    supply_chain_config: str,
    n_episodes: int = 100,
    max_rounds: int = 52
) -> Dict[str, float]:
    """Run evaluation suite for TRM agent."""

    # Load TRM policy
    trm_policy = TRMPolicy(model_path=checkpoint_path)

    results = {
        "total_costs": [],
        "service_levels": [],
        "bullwhip_ratios": [],
        "inference_times": []
    }

    for episode in range(n_episodes):
        # Create game instance
        game = create_beer_game(supply_chain_config)

        # Replace agent strategies with TRM
        for node in game.nodes:
            node.agent = BeerGameAgent(
                agent_type=node.role,
                strategy=AgentStrategy.TRM
            )
            node.agent.trm_policy = trm_policy

        # Run simulation
        episode_cost = 0
        episode_inference_times = []

        for round_num in range(max_rounds):
            # Time TRM inference
            start = time.perf_counter()
            game.step()
            inference_time = time.perf_counter() - start

            episode_inference_times.append(inference_time)
            episode_cost += game.total_cost_this_round

        # Compute metrics
        service_level = compute_service_level(game)
        bullwhip_ratio = compute_bullwhip_ratio(game)

        results["total_costs"].append(episode_cost)
        results["service_levels"].append(service_level)
        results["bullwhip_ratios"].append(bullwhip_ratio)
        results["inference_times"].extend(episode_inference_times)

    # Aggregate statistics
    metrics = {
        "mean_cost": np.mean(results["total_costs"]),
        "std_cost": np.std(results["total_costs"]),
        "mean_service_level": np.mean(results["service_levels"]),
        "mean_bullwhip": np.mean(results["bullwhip_ratios"]),
        "mean_inference_time_ms": np.mean(results["inference_times"]) * 1000,
        "p95_inference_time_ms": np.percentile(results["inference_times"], 95) * 1000
    }

    return metrics
```

---

## Risk Analysis

### Technical Risks

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **TRM underperforms GNN** | Medium | Medium | Implement hybrid TRM+GNN ensemble |
| **Slow convergence in training** | Medium | Low | Use curriculum learning, pre-training |
| **Poor generalization** | Low | High | Extensive validation on diverse configs |
| **Integration bugs** | High | Medium | Comprehensive integration tests |
| **Memory issues in production** | Low | Medium | Implement model quantization |

### Operational Risks

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **User confusion** | Medium | Low | Clear documentation, gradual rollout |
| **Model maintenance** | Medium | Medium | Version control, A/B testing framework |
| **Performance regression** | Low | High | Continuous benchmarking, alerts |
| **Dependency conflicts** | Low | Low | Pin versions, containerization |

### Research Risks

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **TRM not suitable for supply chains** | Medium | High | Early prototype validation (Phase 1) |
| **Recursive reasoning overhead** | Low | Medium | Adaptive cycle count based on complexity |
| **Training instability** | Medium | Medium | Gradient clipping, careful initialization |
| **Interpretability challenges** | Low | Low | Visualize reasoning states, attention weights |

### Mitigation: Hybrid Fallback Strategy

Always provide fallback to proven heuristics:

```python
def _trm_hybrid_strategy(self, *args, **kwargs) -> int:
    """TRM with automatic fallback to PID on failure."""
    try:
        # Attempt TRM inference
        order = self._trm_strategy(*args, **kwargs)

        # Sanity check
        if order < 0 or order > 1000:
            raise ValueError(f"Invalid TRM order: {order}")

        return order

    except Exception as e:
        logger.warning(f"TRM failed, using PID fallback: {e}")
        return self._pid_strategy(*args, **kwargs)
```

---

## API Specifications

### REST API Endpoints

#### 1. Load TRM Model

```http
POST /api/v1/trm/load
Content-Type: application/json

{
  "model_name": "default_trm",
  "checkpoint_path": "checkpoints/trm/best_model.pt",
  "device": "cpu"
}

Response 200:
{
  "status": "success",
  "model_name": "default_trm",
  "parameters": 7234567,
  "device": "cpu",
  "loaded_at": "2026-01-16T10:30:00Z"
}
```

#### 2. Set Agent Strategy to TRM

```http
PUT /api/v1/mixed-games/{game_id}/agent-strategy
Content-Type: application/json

{
  "node_id": "retailer",
  "strategy": "trm",
  "config": {
    "model_name": "default_trm",
    "refinement_cycles": 5,
    "reasoning_steps": 3,
    "fallback": "pid"
  }
}

Response 200:
{
  "status": "success",
  "node_id": "retailer",
  "strategy": "trm",
  "model_loaded": true
}
```

#### 3. Get TRM Performance Metrics

```http
GET /api/v1/trm/metrics/{game_id}

Response 200:
{
  "game_id": 123,
  "trm_nodes": ["retailer", "wholesaler"],
  "metrics": {
    "mean_inference_time_ms": 8.5,
    "p95_inference_time_ms": 12.3,
    "total_decisions": 104,
    "fallback_count": 2,
    "cost_improvement_vs_naive": 0.15
  }
}
```

#### 4. Train TRM Model

```http
POST /api/v1/trm/train
Content-Type: application/json

{
  "supply_chain_config": "Default TBG",
  "training_config": {
    "total_episodes": 1000,
    "batch_size": 32,
    "learning_rate": 0.001,
    "device": "cpu"
  },
  "curriculum": [
    {"name": "foundation", "episodes": 300, "difficulty": "easy"},
    {"name": "adaptation", "episodes": 400, "difficulty": "medium"},
    {"name": "mastery", "episodes": 300, "difficulty": "hard"}
  ]
}

Response 202:
{
  "status": "training_started",
  "job_id": "trm_train_20260116_103000",
  "estimated_duration_minutes": 180,
  "status_url": "/api/v1/trm/train/status/trm_train_20260116_103000"
}
```

#### 5. Get Training Status

```http
GET /api/v1/trm/train/status/{job_id}

Response 200:
{
  "job_id": "trm_train_20260116_103000",
  "status": "running",
  "progress": 0.45,
  "current_stage": "adaptation",
  "episodes_completed": 450,
  "total_episodes": 1000,
  "current_loss": 45.3,
  "estimated_time_remaining_minutes": 90
}
```

### Python API

#### Agent Configuration

```python
from app.services.agents import AgentStrategy, BeerGameAgent
from app.models.trm import TRMPolicy

# Configure TRM agent
agent = BeerGameAgent(
    agent_type=AgentType.RETAILER,
    strategy=AgentStrategy.TRM
)

# Load TRM policy
trm_policy = TRMPolicy(
    model_path="checkpoints/trm/best_model.pt",
    device="cpu",
    refinement_cycles=5,
    reasoning_steps=3
)

# Attach to agent
agent.trm_policy = trm_policy

# Make decision
decision = agent.make_decision(
    current_round=10,
    current_demand=8,
    upstream_data={...},
    local_state={...}
)

print(f"TRM ordered: {decision.quantity}")
print(f"Reasoning: {decision.reason}")
```

#### Training API

```python
from app.training.trm_trainer import TRMTrainer
from app.models.trm import TinyRecursiveModel
from app.data.trm_dataset import TRMSupplyChainDataset

# Initialize model
model = TinyRecursiveModel(
    hidden_dim=64,
    num_refinement_cycles=5,
    num_reasoning_steps=3
)

# Create dataset
dataset = TRMSupplyChainDataset(
    supply_chain_config="Default TBG",
    num_episodes=1000,
    curriculum_stage="medium"
)

# Train
trainer = TRMTrainer(model=model, device="cpu")
trainer.train(
    dataset=dataset,
    epochs=10,
    batch_size=32
)

# Save checkpoint
trainer.save_checkpoint("checkpoints/trm/my_model.pt")
```

---

## Testing Strategy

### Unit Tests

**File**: `backend/tests/models/trm/test_tiny_recursive_model.py`

```python
import pytest
import torch
from app.models.trm import TinyRecursiveModel

class TestTinyRecursiveModel:
    """Unit tests for TRM core model."""

    def test_initialization(self):
        """Test model initializes correctly."""
        model = TinyRecursiveModel(hidden_dim=64)
        assert model.hidden_dim == 64
        assert model.num_refinement_cycles == 5

    def test_forward_pass(self):
        """Test forward pass produces valid output."""
        model = TinyRecursiveModel(hidden_dim=64)

        # Mock input
        batch_size = 4
        node_features = torch.randn(batch_size, 16)
        edge_index = torch.tensor([[0, 1], [1, 0]])

        # Forward pass
        output = model(node_features, edge_index)

        # Check output shape
        assert output.shape == (batch_size, 1)
        assert torch.all(output >= 0)  # Non-negative orders

    def test_reasoning_cycles(self):
        """Test recursive reasoning cycles execute."""
        model = TinyRecursiveModel(
            hidden_dim=64,
            num_refinement_cycles=3
        )

        # Should complete 3 refinement cycles
        with torch.no_grad():
            output = model(torch.randn(1, 16), torch.tensor([[0], [0]]))

        assert output is not None

    def test_gradient_flow(self):
        """Test gradients flow through model."""
        model = TinyRecursiveModel(hidden_dim=64)

        # Forward pass with gradients
        node_features = torch.randn(2, 16, requires_grad=True)
        edge_index = torch.tensor([[0, 1], [1, 0]])
        output = model(node_features, edge_index)

        # Backward pass
        loss = output.sum()
        loss.backward()

        # Check gradients exist
        assert node_features.grad is not None
```

### Integration Tests

**File**: `backend/tests/integration/test_trm_agent.py`

```python
import pytest
from app.services.agents import AgentStrategy, BeerGameAgent, AgentType
from app.models.trm import TRMPolicy
from app.services.engine import BeerLine

class TestTRMAgentIntegration:
    """Integration tests for TRM agent in Beer Game."""

    def test_trm_agent_decision(self):
        """Test TRM agent makes valid decisions."""
        # Create agent with TRM strategy
        agent = BeerGameAgent(
            agent_id=1,
            agent_type=AgentType.RETAILER,
            strategy=AgentStrategy.TRM
        )

        # Load mock TRM policy
        agent.trm_policy = TRMPolicy(model_path=None)  # Uses default

        # Make decision
        decision = agent.make_decision(
            current_round=5,
            current_demand=8,
            local_state={"inventory": 10, "backlog": 2}
        )

        assert decision.quantity >= 0
        assert isinstance(decision.reason, str)

    def test_trm_in_game_simulation(self):
        """Test TRM agent in full game simulation."""
        # Create beer game with TRM agents
        game = BeerLine.create_default()

        # Set all agents to TRM
        for node in game.nodes:
            node.agent_strategy = AgentStrategy.TRM

        # Run 10 rounds
        for round_num in range(10):
            game.tick(round_num)

        # Check game completed successfully
        assert game.current_round == 10
        assert all(node.total_cost >= 0 for node in game.nodes)

    def test_trm_fallback_on_error(self):
        """Test TRM falls back to PID on error."""
        agent = BeerGameAgent(
            agent_id=1,
            agent_type=AgentType.RETAILER,
            strategy=AgentStrategy.TRM_HYBRID
        )

        # Don't load TRM policy - should trigger fallback
        agent.trm_policy = None

        # Should not raise, should fall back
        decision = agent.make_decision(
            current_round=1,
            current_demand=4,
            local_state={"inventory": 12, "backlog": 0}
        )

        assert decision.quantity >= 0
        assert "fallback" in decision.reason.lower() or "pid" in decision.reason.lower()
```

### Performance Tests

**File**: `backend/tests/performance/test_trm_speed.py`

```python
import time
import pytest
import torch
from app.models.trm import TinyRecursiveModel

class TestTRMPerformance:
    """Performance benchmarks for TRM."""

    def test_inference_speed(self):
        """Test inference meets <10ms target."""
        model = TinyRecursiveModel(hidden_dim=64)
        model.eval()

        # Warm-up
        with torch.no_grad():
            for _ in range(10):
                model(torch.randn(1, 16), torch.tensor([[0], [0]]))

        # Benchmark
        inference_times = []
        with torch.no_grad():
            for _ in range(100):
                start = time.perf_counter()
                model(torch.randn(1, 16), torch.tensor([[0], [0]]))
                inference_times.append(time.perf_counter() - start)

        mean_time_ms = sum(inference_times) / len(inference_times) * 1000
        p95_time_ms = sorted(inference_times)[94] * 1000

        print(f"Mean inference: {mean_time_ms:.2f}ms")
        print(f"P95 inference: {p95_time_ms:.2f}ms")

        assert mean_time_ms < 10, f"Mean inference {mean_time_ms:.2f}ms exceeds 10ms target"
        assert p95_time_ms < 15, f"P95 inference {p95_time_ms:.2f}ms exceeds 15ms target"

    def test_memory_usage(self):
        """Test model memory footprint."""
        model = TinyRecursiveModel(hidden_dim=64)

        # Count parameters
        num_params = sum(p.numel() for p in model.parameters())

        # Estimate memory (4 bytes per float32)
        memory_mb = (num_params * 4) / (1024 * 1024)

        print(f"Model parameters: {num_params:,}")
        print(f"Estimated memory: {memory_mb:.2f}MB")

        assert num_params < 10_000_000, f"Parameters {num_params:,} exceed 10M target"
        assert memory_mb < 50, f"Memory {memory_mb:.2f}MB exceeds 50MB target"
```

### Test Execution

```bash
# Run all TRM tests
make test-trm

# Run unit tests only
pytest backend/tests/models/trm/ -v

# Run integration tests
pytest backend/tests/integration/test_trm_agent.py -v

# Run performance benchmarks
pytest backend/tests/performance/test_trm_speed.py -v --benchmark

# Generate coverage report
pytest backend/tests/models/trm/ --cov=app.models.trm --cov-report=html
```

---

## Deployment Plan

### Phase 1: Alpha Deployment (Week 10)

**Audience**: Internal testing only

1. Deploy TRM as experimental feature
2. Enable only via explicit configuration
3. Add feature flag: `ENABLE_TRM_AGENTS=false`
4. Monitor performance metrics closely

### Phase 2: Beta Deployment (Week 11-12)

**Audience**: Selected beta testers

1. Announce TRM availability in admin UI
2. Provide documentation and tutorials
3. Collect user feedback
4. A/B test TRM vs existing strategies

### Phase 3: General Availability (Week 13+)

**Audience**: All users

1. Enable TRM in strategy selector by default
2. Publish case studies and benchmarks
3. Offer pre-trained models for common configs
4. Continuous monitoring and improvement

### Monitoring & Observability

**Key Metrics to Track:**

```python
# backend/app/monitoring/trm_metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Inference metrics
trm_inference_time = Histogram(
    'trm_inference_seconds',
    'Time spent in TRM inference',
    buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.1]
)

trm_decisions_total = Counter(
    'trm_decisions_total',
    'Total TRM decisions made',
    ['supply_chain_config', 'node_type']
)

trm_fallback_total = Counter(
    'trm_fallback_total',
    'Times TRM fell back to heuristic',
    ['reason']
)

# Performance metrics
trm_cost_improvement = Gauge(
    'trm_cost_improvement_ratio',
    'Cost improvement vs naive baseline',
    ['supply_chain_config']
)

trm_service_level = Gauge(
    'trm_service_level',
    'Service level achieved',
    ['supply_chain_config']
)
```

**Logging:**

```python
# Structured logging for TRM decisions
logger.info(
    "TRM decision",
    extra={
        "game_id": game.id,
        "round": current_round,
        "node": node.name,
        "order": order_quantity,
        "inference_time_ms": inference_time * 1000,
        "refinement_cycles": 5,
        "reasoning_steps": 3
    }
)
```

### Rollback Plan

If critical issues arise:

1. **Immediate**: Disable TRM via feature flag
2. **Short-term**: Revert to previous agent strategies
3. **Investigation**: Analyze logs and metrics
4. **Fix**: Patch and redeploy
5. **Validation**: Extensive testing before re-enabling

---

## References

### Academic Papers

1. **Less is More: Recursive Reasoning with Tiny Networks**
   - arXiv: https://arxiv.org/abs/2510.04871
   - Authors: Samsung SAIL Montreal
   - Published: October 2025

2. **Accelerating Training Speed of Tiny Recursive Models via Curriculum-Guided Adaptive Recursion**
   - arXiv: https://arxiv.org/abs/2511.08653
   - Published: November 2025

3. **Recursive Language Models: The Paradigm of 2026**
   - Blog: https://www.primeintellect.ai/blog/rlm
   - Author: Alex L. Zhang
   - Published: January 2026

### Code Repositories

1. **TinyRecursiveModels (Official)**
   - GitHub: https://github.com/SamsungSAILMontreal/TinyRecursiveModels
   - License: MIT

2. **Beer Game Implementation Reference**
   - Local: `/home/trevor/Projects/The_Beer_Game/`

### Technical Articles

1. **The End of the Scaling Era: How Recursive Reasoning Outperforms Billion-Parameter Models**
   - Medium: https://machine-learning-made-simple.medium.com/the-end-of-the-scaling-era-how-recursive-reasoning-outperforms-billion-parameter-models-36d7e3274049

2. **Let's Build a Tiny Recursive Model from Scratch**
   - Medium: https://moazharu.medium.com/building-tiny-recursive-model-from-scratch-when-tiny-networks-beat-giants-at-their-own-game-68d9df9e1fdb

3. **Less Is More: TRM Paper Explained**
   - AI Papers Academy: https://aipapersacademy.com/tiny-recursive-model/

### Beer Game Documentation

- `AGENT_SYSTEM.md` - Current agent system documentation
- `CLAUDE.md` - Project overview and development commands
- `DAG_Logic.md` - Supply chain network topology

---

## Appendix A: TRM Mathematics

### Recursive Refinement Formulation

For a supply chain state $\mathbf{x}$, the TRM computes order quantity $q$ through:

1. **Initialization:**
   $$
   \mathbf{y}_0 = f_{\text{init}}(\mathbf{x}), \quad \mathbf{z}_0 = \mathbf{0}
   $$

2. **Refinement Loop** (for $k = 1, \ldots, K$):

   a. **Recursive Reasoning** (for $n = 1, \ldots, N$):
   $$
   \mathbf{z}_n = f_{\text{reason}}(\mathbf{x}, \mathbf{y}_{k-1}, \mathbf{z}_{n-1})
   $$

   b. **Answer Update:**
   $$
   \mathbf{y}_k = \mathbf{y}_{k-1} + f_{\text{refine}}(\mathbf{x}, \mathbf{z}_N)
   $$

3. **Decoding:**
   $$
   q = \text{ReLU}(\mathbf{W}_{\text{out}} \mathbf{y}_K + b_{\text{out}})
   $$

Where:
- $\mathbf{x} \in \mathbb{R}^{d_x}$: Encoded supply chain state
- $\mathbf{y}_k \in \mathbb{R}^{d_h}$: Answer embedding at refinement cycle $k$
- $\mathbf{z}_n \in \mathbb{R}^{d_h}$: Latent reasoning state at step $n$
- $f_{\text{reason}}$: Transformer encoder layer
- $f_{\text{refine}}$: MLP refinement network
- $q \in \mathbb{R}_+$: Final order quantity

### Loss Function

Multi-objective loss for training:

$$
\mathcal{L} = \lambda_1 \mathcal{L}_{\text{order}} + \lambda_2 \mathcal{L}_{\text{cost}} + \lambda_3 \mathcal{L}_{\text{stability}} + \lambda_4 \mathcal{L}_{\text{service}}
$$

Where:

- **Order Optimality Loss:**
  $$
  \mathcal{L}_{\text{order}} = \frac{1}{T} \sum_{t=1}^T |q_t - q_t^*|
  $$

- **Cost Minimization Loss:**
  $$
  \mathcal{L}_{\text{cost}} = \frac{1}{T} \sum_{t=1}^T (c_h \cdot I_t + c_b \cdot B_t)
  $$

- **Stability Loss (Bullwhip):**
  $$
  \mathcal{L}_{\text{stability}} = \text{Var}(q_1, \ldots, q_T)
  $$

- **Service Level Loss:**
  $$
  \mathcal{L}_{\text{service}} = \max(0, 0.95 - \text{FillRate})
  $$

Terms:
- $q_t$: Predicted order at time $t$
- $q_t^*$: Optimal order (from oracle)
- $I_t$: Inventory at time $t$
- $B_t$: Backlog at time $t$
- $c_h, c_b$: Holding and backlog costs

---

## Appendix B: Configuration Examples

### TRM Agent Configuration (YAML)

```yaml
# configs/agents/trm_retailer.yaml
agent:
  type: "trm"
  node: "retailer"

model:
  checkpoint: "checkpoints/trm/best_model.pt"
  device: "cpu"

inference:
  refinement_cycles: 5
  reasoning_steps: 3
  batch_size: 1

fallback:
  enabled: true
  strategy: "pid"
  trigger_on_error: true
  trigger_on_high_latency: true
  max_inference_time_ms: 50

monitoring:
  log_decisions: true
  log_reasoning_states: false  # Debug only
  track_metrics: true
```

### Multi-Node TRM Configuration

```yaml
# configs/games/trm_supply_chain.yaml
game:
  name: "TRM Supply Chain Demo"
  supply_chain_config: "Default TBG"
  max_rounds: 52

agents:
  retailer:
    strategy: "trm"
    model: "default_trm"
    refinement_cycles: 5

  wholesaler:
    strategy: "trm"
    model: "default_trm"
    refinement_cycles: 5

  distributor:
    strategy: "trm_hybrid"  # With fallback
    model: "default_trm"
    refinement_cycles: 4
    fallback: "pid"

  factory:
    strategy: "trm"
    model: "default_trm"
    refinement_cycles: 6  # More complex planning
```

---

## Appendix C: Training Logs (Expected)

```
=== TRM Training Started ===
Model: TinyRecursiveModel (7,234,567 parameters)
Device: cpu
Curriculum: 3 stages, 1000 total episodes

=== Stage 1: Foundation (Easy) ===
Episodes: 300
Demand: Constant (4 units)
Lead Time: 2 rounds

Ep   50/300 | Loss: 125.4 | Cost: 487.2 | Service: 0.82 | Time: 0.8s
Ep  100/300 | Loss:  89.3 | Cost: 312.5 | Service: 0.89 | Time: 0.7s
Ep  150/300 | Loss:  67.1 | Cost: 245.8 | Service: 0.93 | Time: 0.7s
Ep  200/300 | Loss:  54.2 | Cost: 198.3 | Service: 0.95 | Time: 0.7s
Ep  250/300 | Loss:  48.7 | Cost: 176.4 | Service: 0.96 | Time: 0.7s
Ep  300/300 | Loss:  45.1 | Cost: 164.2 | Service: 0.97 | Time: 0.7s

✓ Stage 1 Complete | Final Cost: 164.2 | Service: 97%

=== Stage 2: Adaptation (Medium) ===
Episodes: 400
Demand: Step function (4→8)
Lead Time: 2-3 rounds

Ep  100/400 | Loss: 112.5 | Cost: 398.7 | Service: 0.85 | Time: 0.8s
Ep  200/400 | Loss:  78.9 | Cost: 287.3 | Service: 0.91 | Time: 0.8s
Ep  300/400 | Loss:  61.2 | Cost: 234.6 | Service: 0.94 | Time: 0.7s
Ep  400/400 | Loss:  52.8 | Cost: 203.1 | Service: 0.95 | Time: 0.7s

✓ Stage 2 Complete | Final Cost: 203.1 | Service: 95%

=== Stage 3: Mastery (Hard) ===
Episodes: 300
Demand: Stochastic N(8,4)
Lead Time: 2-4 rounds

Ep  100/300 | Loss:  95.3 | Cost: 345.8 | Service: 0.88 | Time: 0.8s
Ep  200/300 | Loss:  71.4 | Cost: 276.2 | Service: 0.92 | Time: 0.8s
Ep  300/300 | Loss:  58.6 | Cost: 238.5 | Service: 0.94 | Time: 0.8s

✓ Stage 3 Complete | Final Cost: 238.5 | Service: 94%

=== Training Complete ===
Total Time: 3.2 hours
Best Model: checkpoints/trm/best_model.pt (Episode 950)
Final Metrics:
  - Mean Cost: 238.5
  - Service Level: 94%
  - Bullwhip Ratio: 1.42
  - Mean Inference: 7.8ms

Ready for deployment!
```

---

**End of Document**

---

**Document Metadata:**
- **Title**: Tiny Recursive Models (TRM) Implementation Plan for Beer Game
- **Version**: 1.0
- **Date**: 2026-01-16
- **Authors**: Claude Code AI Assistant, Trevor (Project Lead)
- **Status**: Planning Phase - Pre-Implementation
- **Next Review**: After Phase 1 Prototype (Week 3)
- **Contact**: See repository maintainers

**Change Log:**
- 2026-01-16: Initial document creation
