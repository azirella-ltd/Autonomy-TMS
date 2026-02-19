#!/usr/bin/env python3
"""
Train TRM models for Food Dist using generated training data.

This script:
1. Loads replay buffer data from database
2. Creates TRM models for each type (ATP, PO, Order Tracking)
3. Trains using hybrid method (BC warm-start + RL fine-tune)
4. Saves checkpoints

Usage:
    docker compose exec backend python scripts/train_food_dist_trms.py
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
from pathlib import Path
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("WARNING: PyTorch not available. Training will use heuristic fallback.")

from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.group import Group
from app.models.trm_training_data import TRMReplayBuffer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SimpleTRM(nn.Module):
    """
    Simple TRM model for narrow execution decisions.

    Architecture:
    - 2-layer MLP with recursive refinement
    - Per Powell: "7M parameters, 2-layer transformer"
    - Simplified here for demonstration
    """

    def __init__(self, state_dim: int, hidden_dim: int = 128, output_dim: int = 1):
        super().__init__()
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim

        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1)
        )

        # Recursive refinement (3 steps)
        self.refine = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Output head
        self.output = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, output_dim)
        )

        # Value head (for RL)
        self.value = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(self, x: torch.Tensor, return_value: bool = False):
        # Encode
        h = self.encoder(x)

        # 3-step recursive refinement
        for _ in range(3):
            h = h + self.refine(h)  # Residual connection

        # Output
        action = self.output(h)

        if return_value:
            value = self.value(h)
            return action, value
        return action


async def load_replay_buffer_data(db, group_id: int, trm_type: str, limit: int = 10000):
    """Load replay buffer data for a specific TRM type."""
    result = await db.execute(
        select(TRMReplayBuffer).where(
            TRMReplayBuffer.group_id == group_id,
            TRMReplayBuffer.trm_type == trm_type
        ).order_by(TRMReplayBuffer.priority.desc()).limit(limit)
    )
    records = result.scalars().all()

    # Convert to training tensors
    states = []
    actions = []
    rewards = []
    next_states = []
    dones = []
    is_expert = []

    for record in records:
        if record.state_vector and len(record.state_vector) > 0:
            states.append(record.state_vector)
            actions.append(record.action_discrete or 0)
            rewards.append(record.reward or 0)
            next_states.append(record.next_state_vector or record.state_vector)
            dones.append(record.done or False)
            is_expert.append(record.is_expert or False)

    if not states:
        return None, None, None, None, None, None

    # Pad state vectors to uniform length (some TRM types may have variable dims)
    max_dim = max(len(s) for s in states)
    padded_states = [s + [0.0] * (max_dim - len(s)) if len(s) < max_dim else s for s in states]
    padded_next = [s + [0.0] * (max_dim - len(s)) if len(s) < max_dim else s for s in next_states]

    return (
        np.array(padded_states, dtype=np.float32),
        np.array(actions, dtype=np.int64),
        np.array(rewards, dtype=np.float32),
        np.array(padded_next, dtype=np.float32),
        np.array(dones, dtype=np.bool_),
        np.array(is_expert, dtype=np.bool_)
    )


def train_behavioral_cloning(model, states, actions, epochs=20, batch_size=64, lr=1e-4, output_dim=1):
    """Train model via behavioral cloning."""
    if not TORCH_AVAILABLE:
        logger.warning("PyTorch not available, skipping BC training")
        return []

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    # Clamp actions to valid range
    actions = np.clip(actions, 0, output_dim - 1)

    losses = []
    n_samples = len(states)

    for epoch in range(epochs):
        # Shuffle
        indices = np.random.permutation(n_samples)

        epoch_losses = []
        for i in range(0, n_samples, batch_size):
            batch_idx = indices[i:i+batch_size]

            batch_states = torch.tensor(states[batch_idx])
            batch_actions = torch.tensor(actions[batch_idx])

            optimizer.zero_grad()

            # Forward
            predictions = model(batch_states)

            # For classification, reshape
            if predictions.shape[-1] > 1:
                loss = criterion(predictions, batch_actions)
            else:
                # Regression
                loss = nn.functional.mse_loss(predictions.squeeze(), batch_actions.float())

            loss.backward()
            optimizer.step()

            epoch_losses.append(loss.item())

        avg_loss = np.mean(epoch_losses)
        losses.append(avg_loss)

        if (epoch + 1) % 5 == 0:
            logger.info(f"  BC Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

    return losses


def train_td_learning(model, states, actions, rewards, next_states, dones,
                      epochs=80, batch_size=64, lr=1e-4, gamma=0.99, output_dim=1):
    """Train model via TD learning (DQN-style)."""
    if not TORCH_AVAILABLE:
        logger.warning("PyTorch not available, skipping TD training")
        return []

    # Clamp actions to valid range
    actions = np.clip(actions, 0, output_dim - 1)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # Create target network with same architecture
    target_model = SimpleTRM(model.state_dim, model.hidden_dim, output_dim=output_dim)
    target_model.load_state_dict(model.state_dict())

    losses = []
    n_samples = len(states)
    tau = 0.005  # Soft update rate

    for epoch in range(epochs):
        # Shuffle
        indices = np.random.permutation(n_samples)

        epoch_losses = []
        for i in range(0, n_samples, batch_size):
            batch_idx = indices[i:i+batch_size]

            batch_states = torch.tensor(states[batch_idx])
            batch_actions = torch.tensor(actions[batch_idx])
            batch_rewards = torch.tensor(rewards[batch_idx])
            batch_next_states = torch.tensor(next_states[batch_idx])
            batch_dones = torch.tensor(dones[batch_idx].astype(np.float32))

            optimizer.zero_grad()

            # Current Q values (select based on actions taken)
            q_values = model(batch_states)  # [batch, output_dim]
            if q_values.shape[-1] > 1:
                # Index into Q values by action
                q_values_selected = q_values.gather(1, batch_actions.unsqueeze(1)).squeeze()
            else:
                q_values_selected = q_values.squeeze()

            # Target Q values (max over actions)
            with torch.no_grad():
                next_q = target_model(batch_next_states)  # [batch, output_dim]
                if next_q.shape[-1] > 1:
                    max_next_q = next_q.max(dim=1).values
                else:
                    max_next_q = next_q.squeeze()
                target_q = batch_rewards + gamma * max_next_q * (1 - batch_dones)

            # TD loss
            loss = nn.functional.mse_loss(q_values_selected, target_q)

            loss.backward()
            optimizer.step()

            epoch_losses.append(loss.item())

        # Soft update target network
        for target_param, param in zip(target_model.parameters(), model.parameters()):
            target_param.data.copy_(tau * param.data + (1 - tau) * target_param.data)

        avg_loss = np.mean(epoch_losses)
        losses.append(avg_loss)

        if (epoch + 1) % 10 == 0:
            logger.info(f"  TD Epoch {epoch + 1}/{epochs}, Loss: {avg_loss:.4f}")

    return losses


async def train_trm_models():
    """Main training function for TRM models."""

    print("="*60)
    print("FOOD DIST TRM TRAINING")
    print("="*60)

    if not TORCH_AVAILABLE:
        print("\nERROR: PyTorch is required for training. Please install PyTorch.")
        return

    async with async_session_factory() as db:
        # Find Food Dist group
        result = await db.execute(
            select(Group).where(Group.name == "Food Dist")
        )
        group = result.scalar_one_or_none()

        if not group:
            print("ERROR: Food Dist group not found")
            return

        print(f"\nFound Food Dist group: id={group.id}")

        # TRM types to train
        trm_types = {
            'atp_executor': {'state_dim': 26, 'output_dim': 4},  # fulfill/partial/defer/reject
            'po_creation': {'state_dim': 9, 'output_dim': 2},  # order/skip
            'order_tracking': {'state_dim': 7, 'output_dim': 4}  # escalate/contact/monitor/resolve
        }

        checkpoint_dir = Path("/app/checkpoints/trm_food_dist")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        training_results = {}

        for trm_type, config in trm_types.items():
            print(f"\n{'='*60}")
            print(f"Training {trm_type.upper()}")
            print("="*60)

            # Load data
            logger.info(f"Loading replay buffer data for {trm_type}...")
            data = await load_replay_buffer_data(db, group.id, trm_type, limit=5000)

            states, actions, rewards, next_states, dones, is_expert = data

            if states is None or len(states) < 100:
                logger.warning(f"Insufficient data for {trm_type}, skipping")
                continue

            logger.info(f"Loaded {len(states)} training samples")
            logger.info(f"  Expert samples: {is_expert.sum()}")
            logger.info(f"  Average reward: {rewards.mean():.4f}")

            # Adjust state_dim based on actual data
            actual_state_dim = states.shape[1] if len(states.shape) > 1 else 1

            # Create model
            model = SimpleTRM(
                state_dim=actual_state_dim,
                hidden_dim=128,
                output_dim=config['output_dim']
            )

            logger.info(f"Created TRM model with state_dim={actual_state_dim}")

            # Phase 1: Behavioral Cloning (warm-start)
            logger.info("\nPhase 1: Behavioral Cloning (warm-start)")
            bc_losses = train_behavioral_cloning(
                model, states, actions, epochs=20, output_dim=config['output_dim']
            )

            # Phase 2: TD Learning (fine-tune)
            logger.info("\nPhase 2: TD Learning (fine-tune)")
            td_losses = train_td_learning(
                model, states, actions, rewards, next_states, dones, epochs=50,
                output_dim=config['output_dim']
            )

            # Save checkpoint
            checkpoint_path = checkpoint_dir / f"trm_{trm_type}.pt"
            torch.save({
                'model_state_dict': model.state_dict(),
                'state_dim': actual_state_dim,
                'output_dim': config['output_dim'],
                'trm_type': trm_type,
                'bc_losses': bc_losses,
                'td_losses': td_losses,
                'trained_at': datetime.now().isoformat(),
                'num_samples': len(states)
            }, checkpoint_path)

            logger.info(f"Saved checkpoint: {checkpoint_path}")

            training_results[trm_type] = {
                'samples': len(states),
                'final_bc_loss': bc_losses[-1] if bc_losses else None,
                'final_td_loss': td_losses[-1] if td_losses else None,
                'checkpoint': str(checkpoint_path)
            }

        # Summary
        print("\n" + "="*60)
        print("TRAINING COMPLETE")
        print("="*60)

        for trm_type, result in training_results.items():
            print(f"\n{trm_type}:")
            print(f"  Samples: {result['samples']}")
            print(f"  Final BC Loss: {result['final_bc_loss']:.4f}" if result['final_bc_loss'] else "  BC skipped")
            print(f"  Final TD Loss: {result['final_td_loss']:.4f}" if result['final_td_loss'] else "  TD skipped")
            print(f"  Checkpoint: {result['checkpoint']}")

        return training_results


if __name__ == "__main__":
    print("Starting TRM training for Food Dist...")
    asyncio.run(train_trm_models())
